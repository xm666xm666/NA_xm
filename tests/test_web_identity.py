"""网站账户、RBAC 与 CSRF 的可执行回归测试。"""

from __future__ import annotations

import os
import re
import sys
import tempfile
import unittest
from pathlib import Path

from flask import Flask, jsonify

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from webapp.identity import FEATURE_AGENT, FEATURE_BATCH, FEATURE_DATA_SUMMARY, FEATURE_UPSTREAM, ROLE_ADMIN, ROLE_USER, User, init_identity


class WebsiteIdentityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.previous_env = {key: os.environ.get(key) for key in ("DATABASE_URL", "APP_ENV", "WEB_AUTO_CREATE_SCHEMA", "BOOTSTRAP_ADMIN_PASSWORD")}
        os.environ.update(
            {
                "DATABASE_URL": f"sqlite:///{Path(self.tempdir.name, 'identity.db').as_posix()}",
                "APP_ENV": "development",
                "WEB_AUTO_CREATE_SCHEMA": "true",
                "BOOTSTRAP_ADMIN_PASSWORD": "test-password-2026",
            }
        )
        self.app = Flask(__name__, template_folder=str(PROJECT_ROOT / "templates"))
        self.app.testing = True
        self.identity = init_identity(self.app, Path(self.tempdir.name))

        @self.app.post("/api/mutation")
        def mutation():
            return jsonify({"success": True})

        @self.app.get("/")
        def dashboard():
            blocked = self.identity.page_guard()
            return blocked or "dashboard"

        @self.app.get("/batch-view")
        def batch_view():
            blocked = self.identity.page_guard(FEATURE_BATCH)
            return blocked or "batch"

        @self.app.get("/summary-view")
        def summary_view():
            blocked = self.identity.page_guard(FEATURE_DATA_SUMMARY)
            return blocked or "summary"

        @self.app.get("/agent-view")
        def agent_view():
            blocked = self.identity.page_guard(FEATURE_AGENT)
            return blocked or "agent"

        self.client = self.app.test_client()

    def tearDown(self) -> None:
        self.identity.store.close()
        self.identity.store.engine.dispose()
        for key, value in self.previous_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        self.tempdir.cleanup()

    def _csrf(self) -> str:
        with self.client.session_transaction() as session:
            return str(session.get("csrf_token") or "")

    def _assume_user(self, user: User) -> str:
        with self.client.session_transaction() as session:
            session.clear()
            session["user_id"] = user.id
            session["csrf_token"] = "test-csrf-token"
        return "test-csrf-token"

    def test_bootstrap_admin_login_and_user_management(self) -> None:
        login_page = self.client.get("/login")
        self.assertEqual(login_page.status_code, 200)
        response = self.client.post(
            "/login",
            data={"identity": "admin", "password": "test-password-2026", "csrf_token": self._csrf()},
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.client.get("/auth/me").get_json()["user"]["role"], "superadmin")
        self.assertEqual(self.client.get("/").status_code, 302)
        response = self.client.post(
            "/account",
            data={
                "current_password": "test-password-2026",
                "new_password": "test-password-2026",
                "new_password_confirm": "test-password-2026",
                "csrf_token": self._csrf(),
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.client.get("/").status_code, 200)
        self.assertEqual(self.client.get("/agent-view").status_code, 200)
        admin_page = self.client.get("/admin/users")
        self.assertEqual(admin_page.status_code, 200)
        self.assertIn("用户目录", admin_page.get_data(as_text=True))

        target = self.identity.store.create_user(
            username="operator", email="operator@example.com", password="test-password-2026", role=ROLE_USER, email_verified=True
        )
        response = self.client.post(
            f"/admin/users/{target.id}/role", data={"role": ROLE_ADMIN, "csrf_token": self._csrf()}
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.identity.store.session().get(User, target.id).role, ROLE_ADMIN)

        response = self.client.post(
            f"/admin/users/{target.id}/status", data={"is_active": "false", "csrf_token": self._csrf()}
        )
        self.assertEqual(response.status_code, 302)
        self.assertFalse(self.identity.store.session().get(User, target.id).is_active)

    def test_user_permission_boundary_and_csrf(self) -> None:
        user = self.identity.store.create_user(
            username="basic-user", email="basic@example.com", password="test-password-2026", role=ROLE_USER, email_verified=True
        )
        csrf = self._assume_user(user)
        self.assertEqual(self.client.get("/").status_code, 200)
        self.assertEqual(self.client.get("/batch-view").status_code, 200)
        self.assertEqual(self.client.get("/summary-view").status_code, 403)
        self.assertEqual(self.client.get("/agent-view").status_code, 403)
        self.assertEqual(self.client.get("/api/data-summary/anything").status_code, 403)
        self.assertNotIn(FEATURE_UPSTREAM, self.client.get("/auth/me").get_json()["features"])
        self.assertFalse(self.identity.has_feature(FEATURE_UPSTREAM, user))
        self.assertEqual(self.client.post("/api/mutation").status_code, 400)
        self.assertEqual(self.client.post("/api/mutation", headers={"X-CSRF-Token": csrf}).status_code, 200)

    def test_logout_clears_the_session_and_returns_to_login(self) -> None:
        user = self.identity.store.create_user(
            username="logout-user", email="logout@example.com", password="test-password-2026", role=ROLE_USER, email_verified=True
        )
        csrf = self._assume_user(user)

        response = self.client.post("/logout", headers={"X-CSRF-Token": csrf}, follow_redirects=False)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["Location"], "/login")
        self.assertEqual(self.client.get("/auth/me").status_code, 401)
        self.assertEqual(self.client.get("/").status_code, 302)

    def test_registration_and_password_recovery_code_flow(self) -> None:
        self.assertEqual(self.client.get("/register").status_code, 200)
        registration = self.client.post(
            "/register",
            data={
                "username": "recovery-user",
                "email": "recovery@example.com",
                "password": "registration-password-2026",
                "password_confirm": "registration-password-2026",
                "csrf_token": self._csrf(),
            },
        )
        self.assertEqual(registration.status_code, 200)
        initial_code_match = re.search(r'data-recovery-code>([A-Z0-9-]+)<', registration.get_data(as_text=True))
        self.assertIsNotNone(initial_code_match)
        initial_code = str(initial_code_match.group(1))
        self.assertRegex(initial_code, r"^[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{4}$")

        reset = self.client.post(
            "/forgot-password",
            data={
                "identity": "recovery@example.com",
                "recovery_code": initial_code,
                "password": "replacement-password-2026",
                "password_confirm": "replacement-password-2026",
                "csrf_token": self._csrf(),
            },
        )
        self.assertEqual(reset.status_code, 200)
        self.assertIn("密码已更新", reset.get_data(as_text=True))
        next_code_match = re.search(r'data-recovery-code>([A-Z0-9-]+)<', reset.get_data(as_text=True))
        self.assertIsNotNone(next_code_match)
        self.assertNotEqual(initial_code, str(next_code_match.group(1)))

        with self.app.app_context():
            user, error = self.identity.store.authenticate("recovery-user", "replacement-password-2026")
        self.assertIsNotNone(user, error)

        old_code = self.client.post(
            "/forgot-password",
            data={
                "identity": "recovery-user",
                "recovery_code": initial_code,
                "password": "another-password-2026",
                "password_confirm": "another-password-2026",
                "csrf_token": self._csrf(),
            },
        )
        self.assertIn("账号或恢复验证码不正确", old_code.get_data(as_text=True))

    def test_recovery_code_locks_after_five_failed_attempts(self) -> None:
        user = self.identity.store.create_user(
            username="locked-recovery", email="locked-recovery@example.com", password="test-password-2026", email_verified=True
        )
        self.identity.store.issue_password_recovery_code(user)
        with self.app.app_context():
            for _ in range(5):
                _, error, _ = self.identity.store.reset_password_with_recovery_code(
                    identity="locked-recovery",
                    recovery_code="2222-2222-2222",
                    new_password="replacement-password-2026",
                )
                self.assertEqual(error, "账号或恢复验证码不正确")
            _, error, _ = self.identity.store.reset_password_with_recovery_code(
                identity="locked-recovery",
                recovery_code="2222-2222-2222",
                new_password="replacement-password-2026",
            )
        self.assertEqual(error, "恢复验证码已临时锁定，请 15 分钟后再试")


if __name__ == "__main__":
    unittest.main(verbosity=2)
