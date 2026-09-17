"""退款结构重构的离线回归：真实路由、业务和 SQL，SQLite 不验证 MySQL 并发锁。"""
from datetime import timedelta
import unittest

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from supportflow.api.auth.deps import get_current_user
from supportflow.db.base import Base, utc_now
from supportflow.db.session import get_db
from supportflow.main import app
from supportflow.models import Conversation, Order, RefundApproval, RefundRecord, RefundRequest, User
from supportflow.models.enums import FulfillmentStatus, PaymentStatus, RefundStatus, UserRole
from supportflow.services.refunds.eligibility import evaluate_eligibility


class OfflineSession:
    """仅供顺序测试：让异步业务使用内存 SQLite 的同步会话。"""

    def __init__(self, session):
        self.session = session

    def add(self, value):
        self.session.add(value)

    async def scalar(self, statement):
        return self.session.scalar(statement)

    async def execute(self, statement):
        return self.session.execute(statement)

    async def flush(self):
        self.session.flush()

    async def commit(self):
        self.session.commit()

    async def rollback(self):
        self.session.rollback()

    async def refresh(self, value):
        self.session.refresh(value)


class RefundFlowTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False},
        )

        @event.listens_for(self.engine, "connect")
        def enable_foreign_keys(connection, _):
            connection.execute("PRAGMA foreign_keys=ON")

        Base.metadata.create_all(self.engine)
        self.session = Session(self.engine, expire_on_commit=False)
        self.session.add_all([
            User(id=1, username="customer1", password_hash="unused", role=UserRole.CUSTOMER),
            User(id=2, username="customer2", password_hash="unused", role=UserRole.CUSTOMER),
            User(id=3, username="admin", password_hash="unused", role=UserRole.ADMIN),
        ])
        self.session.flush()
        self.session.add_all([
            Order(order_no=number, user_id=owner, paid_amount_cents=29900,
                  payment_status=PaymentStatus.PAID,
                  fulfillment_status=FulfillmentStatus.DELIVERED,
                  delivered_at=utc_now() - timedelta(days=days))
            for number, owner, days in [("A1", 1, 2), ("A2", 1, 3), ("OLD", 1, 15), ("B1", 2, 2)]
        ])
        self.session.add(Conversation(id="owned-chat", user_id=1))
        self.session.commit()
        self.identity = User(id=1, username="customer1", role=UserRole.CUSTOMER)

        async def db_override():
            try:
                yield OfflineSession(self.session)
            finally:
                self.session.rollback()

        async def user_override():
            return self.identity

        self.old_overrides = app.dependency_overrides.copy()
        app.dependency_overrides[get_db] = db_override
        app.dependency_overrides[get_current_user] = user_override
        self.client = TestClient(app)

    def tearDown(self):
        self.client.close()
        app.dependency_overrides.clear()
        app.dependency_overrides.update(self.old_overrides)
        self.session.close()
        self.engine.dispose()

    def as_admin(self):
        self.identity = User(id=3, username="admin", role=UserRole.ADMIN)

    def submit(self, order_no="A1", **extra):
        return self.client.post("/customer/refund-requests", json={
            "order_no": order_no, "reason": "耳机无声", **extra,
        })

    def test_apply_approve_and_read_both_sides(self):
        eligibility = self.client.get("/customer/orders/A1/refund-eligibility").json()["data"]
        self.assertTrue(eligibility["eligible"])
        self.assertEqual(eligibility["amount_cents"], 29900)
        response = self.submit(conversation_id="owned-chat")
        self.assertEqual(response.status_code, 200)
        pending = response.json()["data"]
        self.assertEqual(set(pending), {
            "request_key", "order_no", "amount_cents", "status", "created_at",
            "reason_original", "reason_category", "updated_at", "order", "approval", "refund_record",
        })
        self.assertEqual(pending["status"], "pending")
        self.assertIsNone(pending["approval"])
        self.assertIsNone(pending["refund_record"])
        self.assertTrue(pending["created_at"].endswith("Z"))
        key = pending["request_key"]
        self.as_admin()
        approved = self.client.post(f"/admin/refund-requests/{key}/decision", json={
            "decision": "approved", "comment": "同意退款",
        })
        self.assertEqual(approved.status_code, 200)
        result = approved.json()["data"]
        self.assertEqual(set(result), set(pending) | {"user_id", "username"})
        self.assertEqual(result["username"], "customer1")
        self.assertEqual(result["status"], "refunded")
        self.assertEqual(result["order"]["payment_status"], "refunded")
        self.assertEqual(result["approval"]["admin_username"], "admin")
        self.assertEqual(result["approval"]["comment"], "同意退款")
        self.assertEqual(result["refund_record"]["status"], "succeeded")
        self.assertEqual(result["refund_record"]["amount_cents"], 29900)
        for endpoint, block in [("refund-approvals", "approval"), ("refund-records", "refund_record")]:
            page = self.client.get(f"/admin/{endpoint}").json()["data"]
            self.assertEqual(page["total"], 1)
            self.assertEqual(page["items"], [result[block]])
        self.identity = User(id=1, role=UserRole.CUSTOMER)
        customer = self.client.get(f"/customer/refund-requests/{key}").json()["data"]
        self.assertEqual(customer, {k: v for k, v in result.items() if k not in {"user_id", "username"}})

    def test_reject_then_submit_new_request(self):
        key = self.submit().json()["data"]["request_key"]
        self.as_admin()
        result = self.client.post(f"/admin/refund-requests/{key}/decision", json={
            "decision": "rejected", "comment": "  材料不足  ",
        }).json()["data"]
        self.assertEqual(result["status"], "rejected")
        self.assertEqual(result["approval"]["comment"], "材料不足")
        self.assertIsNone(result["refund_record"])
        self.assertEqual(result["order"]["payment_status"], "paid")
        self.identity = User(id=1, role=UserRole.CUSTOMER)
        new = self.submit().json()["data"]
        self.assertNotEqual(new["request_key"], key)
        self.assertEqual(new["status"], "pending")

    def test_sequential_repeats_keep_existing_result(self):
        first = self.submit().json()["data"]
        self.assertEqual(self.submit().json()["data"], first)
        self.as_admin()
        path = f"/admin/refund-requests/{first['request_key']}/decision"
        approved = self.client.post(path, json={"decision": "approved"})
        self.assertEqual(self.client.post(path, json={"decision": "approved"}).json(), approved.json())
        self.assertEqual(self.client.post(path, json={"decision": "rejected"}).status_code, 409)
        for model in (RefundRequest, RefundApproval, RefundRecord):
            self.assertEqual(self.session.scalar(select(func.count()).select_from(model)), 1)

    def test_ownership_and_role_restrictions(self):
        key = self.submit().json()["data"]["request_key"]
        self.assertEqual(self.client.get("/admin/refund-requests").status_code, 403)
        self.identity = User(id=2, role=UserRole.CUSTOMER)
        self.assertEqual(self.client.get("/customer/refund-requests").json()["data"]["total"], 0)
        for path in (f"/customer/refund-requests/{key}", "/customer/refund-requests/missing"):
            response = self.client.get(path)
            self.assertEqual(response.status_code, 404)
            self.assertEqual(response.json(), {"detail": "退款申请不存在"})
        self.assertEqual(self.submit().json(), self.submit("missing").json())

    def test_list_pagination_filter_and_empty_records(self):
        for number in ("A1", "A2"):
            self.assertEqual(self.submit(number).status_code, 200)
        for endpoint in ("/customer/refund-requests", "/admin/refund-requests"):
            if endpoint.startswith("/admin"):
                self.as_admin()
            page = self.client.get(endpoint + "?limit=1&offset=1&status=pending").json()["data"]
            self.assertEqual((page["total"], page["offset"], page["limit"]), (2, 1, 1))
            self.assertEqual(len(page["items"]), 1)
            self.assertEqual(page["items"][0]["order_no"], "A1")
            self.assertEqual(self.client.get(endpoint + "?status=rejected").json()["data"]["total"], 0)
        for endpoint in ("refund-approvals", "refund-records"):
            self.assertEqual(self.client.get(f"/admin/{endpoint}").json()["data"]["items"], [])

    def test_validation_and_ineligible_order_do_not_create_requests(self):
        self.assertEqual(self.submit(reason=" \n ").status_code, 422)
        self.assertEqual(self.submit("OLD").status_code, 409)
        self.assertEqual(self.submit(conversation_id="missing-chat").status_code, 404)
        self.assertEqual(self.session.scalar(select(func.count()).select_from(RefundRequest)), 0)

    def test_eligibility_boundaries(self):
        now = utc_now()
        order = self.session.scalar(select(Order).where(Order.order_no == "A1"))
        order.delivered_at = now - timedelta(days=14)
        self.assertTrue(evaluate_eligibility(order, None, now).eligible)
        self.assertEqual(evaluate_eligibility(order, None, now + timedelta(microseconds=1)).code, "window_expired")
        order.delivered_at = now + timedelta(seconds=1)
        self.assertEqual(evaluate_eligibility(order, None, now).code, "delivered_time_in_future")
