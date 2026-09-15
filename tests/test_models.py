"""离线验证关键唯一约束；不连接或修改本地 MySQL。"""
import unittest

from sqlalchemy import create_engine, event
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from supportflow.db.base import Base
from supportflow.models import Conversation, Order, RefundApproval, RefundRecord, RefundRequest, User
from supportflow.models.enums import ApprovalDecision, RefundStatus


class ModelConstraintTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://")

        @event.listens_for(self.engine, "connect")
        def enable_foreign_keys(connection, _):
            connection.execute("PRAGMA foreign_keys=ON")

        Base.metadata.create_all(self.engine)
        self.session = Session(self.engine)
        self.session.add(User(id=1, username="customer", password_hash="test-hash"))
        self.session.flush()
        self.session.add_all([
            Order(id=1, order_no="A1001", user_id=1, paid_amount_cents=29900),
            Conversation(id="conversation-1", user_id=1),
        ])
        self.session.commit()

    def tearDown(self):
        self.session.close()
        self.engine.dispose()

    def request(self, key, status=RefundStatus.PENDING):
        return RefundRequest(request_key=key, order_id=1, conversation_id="conversation-1",
                             amount_cents=29900, reason_original="左耳无声", status=status)

    def test_active_and_refunded_requests_block_duplicates(self):
        for status in (RefundStatus.PENDING, RefundStatus.APPROVED, RefundStatus.REFUNDED):
            with self.subTest(status=status):
                self.session.add(self.request("first", status))
                self.session.flush()
                self.session.add(self.request("second"))
                with self.assertRaises(IntegrityError):
                    self.session.flush()
                self.session.rollback()

    def test_rejected_history_allows_new_request(self):
        self.session.add_all([self.request("rejected-1", RefundStatus.REJECTED),
                              self.request("rejected-2", RefundStatus.REJECTED),
                              self.request("new")])
        self.session.commit()

    def test_operation_key_cannot_be_reused(self):
        self.session.add_all([self.request("same", RefundStatus.REJECTED), self.request("same")])
        with self.assertRaises(IntegrityError):
            self.session.flush()

    def test_one_execution_and_one_approval_per_request(self):
        request = self.request("first")
        self.session.add(request)
        self.session.commit()
        request_id = request.id
        for model, fields in (
            (RefundRecord, {"amount_cents": 29900}),
            (RefundApproval, {"admin_id": 1, "decision": ApprovalDecision.APPROVED}),
        ):
            with self.subTest(model=model.__name__):
                self.session.add_all([model(refund_request_id=request_id, **fields),
                                      model(refund_request_id=request_id, **fields)])
                with self.assertRaises(IntegrityError):
                    self.session.flush()
                self.session.rollback()

    def test_invalid_amount_reason_and_foreign_key(self):
        for fields in ({"amount_cents": -1}, {"reason_original": "   "}, {"order_id": 999}):
            with self.subTest(fields=fields):
                request = self.request("invalid")
                for name, value in fields.items():
                    setattr(request, name, value)
                self.session.add(request)
                with self.assertRaises(IntegrityError):
                    self.session.flush()
                self.session.rollback()


if __name__ == "__main__":
    unittest.main()
