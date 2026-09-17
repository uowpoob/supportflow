"""真实 HTTP 路由、密码校验和会话构造；模拟数据库访问以覆盖失败分支。"""
from datetime import timedelta
from http.cookies import SimpleCookie
import unittest
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

from supportflow.core.auth import AuthSettings, SESSION_COOKIE_NAME
from supportflow.core.security import get_password_hash, hash_session_token
from supportflow.db.base import utc_now
from supportflow.db.session import get_db
from supportflow.main import app
from supportflow.models import User
from supportflow.models.enums import UserRole


class LoginTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.password = "test-login-password"
        cls.password_hash = get_password_hash(cls.password)

    def setUp(self):
        self.db = MagicMock(spec=AsyncSession)
        self.user = User(id=42, username="test-user", password_hash=self.password_hash,
                         role=UserRole.CUSTOMER, is_active=True)
        self.db.scalar.return_value = self.user

        async def override_db():
            yield self.db

        app.dependency_overrides[get_db] = override_db
        self.settings_patch = patch("supportflow.api.auth.login.auth_settings", AuthSettings(
            _env_file=None, SESSION_TTL_SECONDS=3600, SESSION_COOKIE_SECURE=False,
        ))
        self.settings_patch.start()
        self.client = TestClient(app, raise_server_exceptions=False)

    def tearDown(self):
        self.client.close()
        self.settings_patch.stop()
        app.dependency_overrides.pop(get_db, None)

    def login(self, **changes):
        payload = {"username": self.user.username, "password": self.password}
        payload.update(changes)
        return self.client.post("/login", json=payload)

    def test_success_saves_hash_and_sets_cookie_without_exposing_secrets_in_json(self):
        before = utc_now()
        response = self.login()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {
            "code": "200", "message": "ok",
            "data": {"id": 42, "username": "test-user", "role": "customer"},
        })
        token = response.cookies[SESSION_COOKIE_NAME]
        self.assertEqual(len(token), 43)
        saved = self.db.add.call_args.args[0]
        self.assertEqual(saved.token_hash, hash_session_token(token))
        self.assertNotEqual(saved.token_hash, token)
        self.assertEqual(saved.user_id, 42)
        self.assertGreaterEqual(saved.expires_at, before + timedelta(seconds=3600))
        self.assertLessEqual(saved.expires_at, utc_now() + timedelta(seconds=3600))
        self.db.commit.assert_awaited_once()
        cookie = SimpleCookie(response.headers["set-cookie"])[SESSION_COOKIE_NAME]
        self.assertTrue(cookie["httponly"])
        self.assertFalse(cookie["secure"])
        self.assertEqual(cookie["samesite"], "lax")
        self.assertEqual(cookie["path"], "/")
        self.assertEqual(cookie["max-age"], "3600")
        self.assertTrue(cookie["expires"])
        self.assertEqual(response.headers["cache-control"], "no-store")
        self.assertEqual(self.client.cookies[SESSION_COOKIE_NAME], token)

    def test_unknown_user_bad_password_and_disabled_user_have_same_401(self):
        for case in ("unknown", "wrong-password", "disabled"):
            with self.subTest(case=case):
                self.db.scalar.return_value = None if case == "unknown" else self.user
                self.user.is_active = case != "disabled"
                response = self.login(password="wrong" if case == "wrong-password" else self.password)
                self.assertEqual(response.status_code, 401)
                self.assertEqual(response.json()["detail"], "用户名或密码错误，或账号不可用")
                self.assertNotIn("set-cookie", response.headers)
        self.db.add.assert_not_called()
        self.db.commit.assert_not_awaited()

    def test_invalid_input_is_rejected_before_database_access(self):
        for payload in ({"username": " "}, {"password": ""}, {"password": "密" * 25},
                        {"username": "a" * 65}, {"role": "admin"}):
            with self.subTest(payload=payload):
                response = self.login(**payload)
                self.assertEqual(response.status_code, 422)
                self.assertNotIn("set-cookie", response.headers)
        self.db.scalar.assert_not_awaited()
        self.db.commit.assert_not_awaited()

    def test_commit_failure_rolls_back_and_does_not_issue_cookie(self):
        self.db.commit.side_effect = RuntimeError("simulated database failure")
        response = self.login()
        self.assertEqual(response.status_code, 500)
        self.assertNotIn("set-cookie", response.headers)
        self.db.rollback.assert_awaited_once()

    def test_each_login_generates_a_new_token(self):
        first = self.login().cookies[SESSION_COOKIE_NAME]
        second = self.login().cookies[SESSION_COOKIE_NAME]
        self.assertNotEqual(first, second)
        self.assertEqual(self.db.commit.await_count, 2)

    def test_secure_cookie_configuration(self):
        with patch("supportflow.api.auth.login.auth_settings", AuthSettings(
            _env_file=None, SESSION_TTL_SECONDS=3600, SESSION_COOKIE_SECURE=True,
        )):
            response = self.login()
        cookie = SimpleCookie(response.headers["set-cookie"])[SESSION_COOKIE_NAME]
        self.assertTrue(cookie["secure"])

    def test_response_schema_declares_typed_user_data(self):
        schema = app.openapi()
        ref = schema["paths"]["/login"]["post"]["responses"]["200"]["content"]["application/json"]["schema"]["$ref"]
        envelope = schema["components"]["schemas"][ref.rsplit("/", 1)[1]]
        self.assertEqual(envelope["properties"]["data"]["$ref"], "#/components/schemas/LoginResponse")


if __name__ == "__main__":
    unittest.main()
