"""第 1、2 天验收：认证闭环、角色准入、订单归属与分页 —— 全部走真实路由。

和 `test_refund_flow.py` 的**关键区别**：这里不覆盖 `get_current_user`。
那条依赖本身就是第 1 天的验收对象（Cookie → SHA-256 摘要 → auth_sessions 行 → 用户），
把它换成替身等于把要验的链路换掉，测完什么也没证明。

所以本文件里每个请求都真的带 Cookie、真的查库、真的做归属过滤。
只有数据库是离线的（内存 SQLite），HTTP 与业务两层都是真的。
"""

from datetime import timedelta
from http.cookies import SimpleCookie
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from supportflow.core.auth import AuthSettings, SESSION_COOKIE_NAME
from supportflow.core.security import get_password_hash, hash_session_token
from supportflow.db.base import utc_now
from supportflow.db.session import get_db
from supportflow.main import app
from supportflow.models import AuthSession, Order, User
from supportflow.models.enums import FulfillmentStatus, PaymentStatus, UserRole
from offline_db import OfflineSession, make_engine


class ApiAcceptanceTests(unittest.TestCase):
    PASSWORD = "acceptance-password"

    @classmethod
    def setUpClass(cls):
        # 三个账号共用一份哈希：bcrypt 是故意慢的，没必要为每个账号付一次代价。
        cls.password_hash = get_password_hash(cls.PASSWORD)

    def setUp(self):
        self.engine = make_engine()
        self.session = Session(self.engine, expire_on_commit=False)
        self.session.add_all([
            User(id=1, username="customer1", password_hash=self.password_hash,
                 role=UserRole.CUSTOMER),
            User(id=2, username="customer2", password_hash=self.password_hash,
                 role=UserRole.CUSTOMER),
            User(id=3, username="admin", password_hash=self.password_hash,
                 role=UserRole.ADMIN),
        ])
        # 必须先 flush：SQLite 的外键是立即生效的，用户还没落库时插订单会直接报 FK 失败。
        self.session.flush()
        self.session.add_all([
            Order(order_no=number, user_id=owner, paid_amount_cents=29900,
                  payment_status=PaymentStatus.PAID,
                  fulfillment_status=FulfillmentStatus.DELIVERED,
                  delivered_at=utc_now() - timedelta(days=days))
            for number, owner, days in [
                ("1260918430020001", 1, 2), ("1260918430020002", 1, 3), ("1260918430020003", 1, 5), ("1270189029630001", 2, 2),
            ]
        ])
        self.session.commit()

        async def db_override():
            try:
                yield OfflineSession(self.session)
            finally:
                # 每个请求结束都回滚未提交的改动，请求之间不互相污染。
                self.session.rollback()

        self.old_overrides = app.dependency_overrides.copy()
        app.dependency_overrides[get_db] = db_override

        # 固定 Cookie 属性，测试结果不受本地 .env 影响。
        settings = AuthSettings(
            _env_file=None, SESSION_TTL_SECONDS=3600, SESSION_COOKIE_SECURE=False,
        )
        self.settings_patch = patch("supportflow.api.auth.login.auth_settings", settings)
        self.logout_patch = patch("supportflow.api.auth.logout.auth_settings", settings)
        self.settings_patch.start()
        self.logout_patch.start()

        self.clients: list[TestClient] = []

    def tearDown(self):
        for client in self.clients:
            client.close()
        self.settings_patch.stop()
        self.logout_patch.stop()
        app.dependency_overrides.clear()
        app.dependency_overrides.update(self.old_overrides)
        self.session.close()
        self.engine.dispose()

    # ------------------------------ 小工具 ------------------------------

    def anonymous(self) -> TestClient:
        """没有任何 Cookie 的客户端。"""
        client = TestClient(app)
        self.clients.append(client)
        return client

    def login_as(self, username: str) -> tuple[TestClient, dict]:
        """真的走一次 `POST /login`，把 Cookie 留在客户端的 jar 里。"""
        client = TestClient(app)
        self.clients.append(client)
        response = client.post("/login", json={"username": username, "password": self.PASSWORD})
        self.assertEqual(response.status_code, 200, response.text)
        return client, response.json()["data"]

    def expire_session(self, client: TestClient) -> None:
        """把客户端当前这条会话改成已过期 —— 会话行还在，只是时间过了。"""
        token = client.cookies[SESSION_COOKIE_NAME]
        row = self.session.scalar(
            select(AuthSession).where(AuthSession.token_hash == hash_session_token(token))
        )
        row.expires_at = utc_now() - timedelta(seconds=1)
        self.session.commit()

    def set_active(self, user_id: int, active: bool) -> None:
        self.session.get(User, user_id).is_active = active
        self.session.commit()

    def replay(self, token: str) -> TestClient:
        """带着**指定的** Cookie 发请求，模拟"浏览器还留着旧凭证"。"""
        client = self.anonymous()
        client.cookies.set(SESSION_COOKIE_NAME, token)
        return client

    # --------------------------- 第 1 天：认证 ---------------------------

    def test_me_restores_identity_from_the_cookie_alone(self):
        """刷新页面后前端什么都不记得，只能靠这个接口向服务端要回身份。"""
        self.assertEqual(self.anonymous().get("/me").status_code, 401)

        client, identity = self.login_as("customer1")
        self.assertEqual(identity, {"id": 1, "username": "customer1", "role": "customer"})

        me = client.get("/me")
        self.assertEqual(me.status_code, 200)
        self.assertEqual(me.json()["data"], identity)

        # 身份来自服务端而不是客户端自带的东西：把 Cookie 扔掉，立刻就不认了。
        client.cookies.clear()
        self.assertEqual(client.get("/me").status_code, 401)

    def test_all_me_failure_modes_return_one_indistinguishable_401(self):
        """没带 / 伪造 / 过期 / 停用 —— 四种情况的响应必须逐字节相同。

        差一个字都等于告诉调用方"这个凭证是真的，只是过期了"，成了凭证探测器。
        """
        cases = {}

        cases["missing"] = self.anonymous().get("/me")

        forged = self.anonymous()
        forged.cookies.set(SESSION_COOKIE_NAME, "x" * 43)
        cases["forged"] = forged.get("/me")

        expired, _ = self.login_as("customer1")
        self.expire_session(expired)
        cases["expired"] = expired.get("/me")

        # 会话本身仍然有效，是账号被停用了 —— 这条路径也在 resolve_session 里。
        disabled, _ = self.login_as("customer2")
        self.set_active(2, False)
        cases["disabled"] = disabled.get("/me")

        bodies = set()
        for name, response in cases.items():
            with self.subTest(case=name):
                self.assertEqual(response.status_code, 401)
                self.assertEqual(response.json(), {"detail": "未登录或会话已失效"})
            bodies.add(response.text)
        self.assertEqual(len(bodies), 1, "四种失败不能有任何可区分的差别")

    def test_logout_revokes_the_server_side_session(self):
        client, _ = self.login_as("customer1")
        token = client.cookies[SESSION_COOKIE_NAME]
        self.assertEqual(self.session.scalar(select(func.count()).select_from(AuthSession)), 1)
        self.assertEqual(client.get("/customer/orders").status_code, 200)

        response = client.post("/logout")
        self.assertEqual(response.status_code, 200)

        # 真正的撤销发生在数据库：那一行没了。
        self.assertEqual(self.session.scalar(select(func.count()).select_from(AuthSession)), 0)

        # 同时要求浏览器丢掉手上的 Cookie（httponly 的 Cookie 前端删不掉，只能后端发）。
        cookie = SimpleCookie(response.headers["set-cookie"])[SESSION_COOKIE_NAME]
        self.assertEqual(cookie["max-age"], "0")

        # 最关键的一条：浏览器就算不听话、把旧 Cookie 再送一次，也用不了了。
        # 只清浏览器不清库里，被截留过的凭证依然有效 —— 那是假退出。
        old = self.replay(token)
        self.assertEqual(old.get("/me").status_code, 401)
        self.assertEqual(old.get("/customer/orders").status_code, 401)

    def test_logout_is_idempotent_without_a_valid_session(self):
        """退出不该失败：没登录、凭证是假的、凭证已过期，一律 200。

        否则用户在"已过期"的页面上点退出会收到报错，前端卡在"退了但状态没清"。
        """
        self.assertEqual(self.anonymous().post("/logout").status_code, 200)
        self.assertEqual(self.replay("y" * 43).post("/logout").status_code, 200)

    # ------------------------ 第 1、2 天：角色与归属 ------------------------

    def test_role_mismatch_is_403_but_missing_identity_is_401(self):
        customer, _ = self.login_as("customer1")
        admin, _ = self.login_as("admin")

        for path in ("/admin/orders", "/admin/refund-requests", "/admin/refund-records"):
            with self.subTest(path=path):
                response = customer.get(path)
                self.assertEqual(response.status_code, 403)
                self.assertEqual(response.json(), {"detail": "当前账号无权访问该接口"})

        for path in ("/customer/orders", "/customer/refund-requests", "/customer/conversations"):
            with self.subTest(path=path):
                response = admin.get(path)
                self.assertEqual(response.status_code, 403)
                self.assertEqual(response.json(), {"detail": "当前账号无权访问该接口"})

        # "没登录"(401) 与 "身份不对"(403) 必须是两个码：前端靠它区分"去登录"和"到此为止"。
        anonymous = self.anonymous()
        for path in ("/admin/orders", "/customer/orders"):
            with self.subTest(path=path):
                self.assertEqual(anonymous.get(path).status_code, 401)

    def test_each_customer_sees_only_their_own_orders(self):
        first, _ = self.login_as("customer1")
        second, _ = self.login_as("customer2")
        admin, _ = self.login_as("admin")

        mine = first.get("/customer/orders").json()["data"]
        self.assertEqual(mine["total"], 3)
        self.assertEqual(
            {item["order_no"] for item in mine["items"]}, {"1260918430020001", "1260918430020002", "1260918430020003"}
        )

        theirs = second.get("/customer/orders").json()["data"]
        self.assertEqual(theirs["total"], 1)
        self.assertEqual([item["order_no"] for item in theirs["items"]], ["1270189029630001"])

        # 管理员看到全部，这不是"漏过滤"，是接口语义本来就不同 ——
        # 权限由域级 `require_admin` 保证，列表本身不做归属筛选。
        whole = admin.get("/admin/orders").json()["data"]
        self.assertEqual(whole["total"], 4)

    def test_someone_elses_order_is_404_indistinguishable_from_a_missing_one(self):
        client, _ = self.login_as("customer1")
        admin, _ = self.login_as("admin")

        # 1270189029630001 真实存在，属于 customer2；9999999999999999 根本不存在。
        others = client.get("/customer/orders/1270189029630001")
        missing = client.get("/customer/orders/9999999999999999")

        self.assertEqual(others.status_code, 404)
        self.assertEqual(missing.status_code, 404)
        # 逐字相同：任何"这单存在但不是你的"的暗示都会让订单号可被枚举。
        self.assertEqual(others.json(), missing.json())
        self.assertEqual(others.json(), {"detail": "订单不存在"})

        # 管理侧的不存在文案同样一致，不泄露"这单是谁的"。
        self.assertEqual(admin.get("/admin/orders/9999999999999999").json(), {"detail": "订单不存在"})

        # 资格查询走的是同一条规矩，不能因为是 GET 就松口。
        for suffix in ("/refund-eligibility",):
            with self.subTest(suffix=suffix):
                self.assertEqual(
                    client.get(f"/customer/orders/1270189029630001{suffix}").json(),
                    client.get(f"/customer/orders/9999999999999999{suffix}").json(),
                )

    def test_pagination_echoes_parameters_and_rejects_out_of_range(self):
        customer, _ = self.login_as("customer1")
        admin, _ = self.login_as("admin")

        page = customer.get("/customer/orders?limit=2&offset=0").json()["data"]
        self.assertEqual(
            (page["total"], page["offset"], page["limit"], len(page["items"])), (3, 0, 2, 2)
        )
        tail = customer.get("/customer/orders?limit=2&offset=2").json()["data"]
        self.assertEqual((tail["offset"], len(tail["items"])), (2, 1))
        # total 是过滤后的总数，不是当前页条数 —— 界面靠它画页码。
        self.assertEqual(tail["total"], 3)

        default = customer.get("/customer/orders").json()["data"]
        self.assertEqual((default["offset"], default["limit"]), (0, 10))

        # 越界和垃圾值必须在查库之前就被挡掉：`limit=999999` 放进去等于白送一条拖垮服务的方式。
        for client, path in ((customer, "/customer/orders"), (admin, "/admin/orders")):
            for query in ("offset=-1", "limit=0", "limit=101", "limit=abc", "offset=1.5"):
                with self.subTest(path=path, query=query):
                    self.assertEqual(client.get(f"{path}?{query}").status_code, 422)


if __name__ == "__main__":
    unittest.main()
