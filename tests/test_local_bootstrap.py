"""Windows 本机启动时的管理员引导回归测试。"""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

from flask import Flask

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from webapp.identity import init_identity
from webapp.local_bootstrap import ensure_local_bootstrap_env, load_project_env


class LocalBootstrapTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        self.previous_env = {
            key: os.environ.get(key)
            for key in (
                "APP_ENV",
                "WEB_AUTO_CREATE_SCHEMA",
                "APP_SECRET_KEY",
                "BOOTSTRAP_ADMIN_PASSWORD",
                "BOOTSTRAP_ADMIN_EMAIL",
                "DATABASE_URL",
            )
        }
        for key in self.previous_env:
            os.environ.pop(key, None)

    def tearDown(self) -> None:
        for key, value in self.previous_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        self.tempdir.cleanup()

    def test_first_local_start_creates_loginable_admin(self) -> None:
        result = ensure_local_bootstrap_env(self.root)

        self.assertTrue(result.created_file)
        self.assertIsNotNone(result.generated_admin_password)
        self.assertTrue((self.root / ".env").exists())

        load_project_env(self.root)
        app = Flask(__name__, template_folder=str(PROJECT_ROOT / "templates"))
        app.testing = True
        identity = init_identity(app, self.root)
        try:
            with app.app_context():
                user, message = identity.store.authenticate("admin", str(result.generated_admin_password))

                self.assertEqual(message, "")
                self.assertIsNotNone(user)
                self.assertEqual(user.role, "superadmin")
                self.assertTrue(user.is_bootstrap_superadmin)
        finally:
            identity.store.close()
            identity.store.engine.dispose()

    def test_existing_password_is_not_overwritten(self) -> None:
        (self.root / ".env").write_text(
            "APP_ENV=development\nBOOTSTRAP_ADMIN_PASSWORD=existing-local-password\n",
            encoding="utf-8",
        )

        result = ensure_local_bootstrap_env(self.root)

        self.assertFalse(result.created_file)
        self.assertIsNone(result.generated_admin_password)
        self.assertIn(
            "BOOTSTRAP_ADMIN_PASSWORD=existing-local-password",
            (self.root / ".env").read_text(encoding="utf-8"),
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
