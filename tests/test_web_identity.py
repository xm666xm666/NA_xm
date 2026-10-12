"""网站账户、RBAC 与 CSRF 的可执行回归测试。"""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

from flask import Flask, jsonify

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from webapp.identity import FEATURE_AGENT, FEATURE_BATCH, FEATURE_DATA_SUMMARY, ROLE_ADMIN, ROLE_USER, User, init_identity


class WebsiteIdentityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.previous_env = {key: os.environ.get(key) for key in ("DATABASE_URL", "APP_ENV", "WEB_AUTO_CREATE_SCHEMA", "BOOTSTRAP_ADMIN_PASSWORD")}
        os.environ.update(
            {
                "DATABASE_URL": f"sqlite:///{Path(self.tempdir.name, 'identity.db').as_posix()}",
                "APP_ENV": "development",
                "WEB_AUTO_CREATE_SCHEMA": "true",
                "BOOTSTRAP_ADMIN_PASSWORD": "Bootstrap-Password-2026",
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
            data={"identity": "admin", "password": "Bootstrap-Password-2026", "csrf_token": self._csrf()},
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.client.get("/auth/me").get_json()["user"]["role"], "superadmin")
        self.assertEqual(self.client.get("/").status_code, 302)
        response = self.client.post(
            "/account",
            data={
                "current_password": "Bootstrap-Password-2026",
                "new_password": "A-new-safe-password-2026",
                "new_password_confirm": "A-new-safe-password-2026",
                "csrf_token": self._csrf(),
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.client.get("/").status_code, 200)
        self.assertEqual(self.client.get("/agent-view").status_code, 200)

        target = self.identity.store.create_user(
            username="operator", email="operator@example.com", password="A-safe-password-2026", role=ROLE_USER, email_verified=True
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
            username="basic-user", email="basic@example.com", password="A-safe-password-2026", role=ROLE_USER, email_verified=True
        )
        csrf = self._assume_user(user)
        self.assertEqual(self.client.get("/").status_code, 200)
        self.assertEqual(self.client.get("/batch-view").status_code, 200)
        self.assertEqual(self.client.get("/summary-view").status_code, 403)
        self.assertEqual(self.client.get("/agent-view").status_code, 403)
        self.assertEqual(self.client.get("/api/data-summary/anything").status_code, 403)
        self.assertEqual(self.client.post("/api/mutation").status_code, 400)
        self.assertEqual(self.client.post("/api/mutation", headers={"X-CSRF-Token": csrf}).status_code, 200)


if __name__ == "__main__":
    unittest.main(verbosity=2)
