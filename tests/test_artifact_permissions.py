"""产物类型归属的权限回归测试。"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BATCH_ROOT = PROJECT_ROOT / "batch"
if str(BATCH_ROOT) not in sys.path:
    sys.path.insert(0, str(BATCH_ROOT))

from lib.artifacts import artifact_kind_for_filename
import app as app_module


class FakeIdentity:
    def __init__(self, role: str = "user"):
        self.user = SimpleNamespace(id=1, role=role)

    def current_user(self):
        return self.user

    def has_feature(self, feature: str) -> bool:
        return feature == "overview" or self.user.role == "superadmin"


class ArtifactPermissionTests(unittest.TestCase):
    def test_filename_kind_classification_keeps_privileged_files_separate(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            excel = root / "excel"
            excel.mkdir()
            fixtures = {
                "ai网关令牌及渠道列表_20261013000000.xlsx": "summary",
                "ai网关令牌及渠道列表_一表总览_20261013000000.xlsx": "overview",
                "智能分析表格_20261013000000.xlsx": "analysis",
                "上游信息_火山云_20261013000000.xlsx": "upstream",
                "上游账单_火山云_2026年10月_20261013000000.xlsx": "bill",
            }
            for filename in fixtures:
                (excel / filename).touch()

            for filename, expected_kind in fixtures.items():
                self.assertEqual(artifact_kind_for_filename(root, filename), expected_kind, filename)

            self.assertIsNone(artifact_kind_for_filename(root, "not-an-artifact.xlsx"))

    def test_download_requires_kind_for_non_superadmin_and_checks_actual_type(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            excel = root / "excel"
            excel.mkdir()
            filename = "ai网关令牌及渠道列表_20261013000000.xlsx"
            path = excel / filename
            path.write_bytes(b"workbook")
            batch = {
                "resolve_excel_path": lambda _root, value: excel / Path(str(value)).name,
                "artifact_kind_for_filename": lambda _root, _name: "summary",
            }
            with (
                patch.object(app_module, "NEW_DIR", root),
                patch.object(app_module, "BATCH", batch),
                patch.object(app_module, "_ensure_batch", lambda: None),
                patch.object(app_module, "_send_excel_attachment", lambda value: value),
                patch.object(app_module, "IDENTITY", FakeIdentity()),
            ):
                with app_module.app.test_request_context(f"/api/artifacts/download?file={filename}"):
                    _response, status = app_module.api_artifacts_download()
                    self.assertEqual(status, 403)
                with app_module.app.test_request_context(f"/api/artifacts/download?file={filename}&kind=summary"):
                    _response, status = app_module.api_artifacts_download()
                    self.assertEqual(status, 403)
                with app_module.app.test_request_context(f"/api/artifacts/download?file={filename}&kind=overview"):
                    _response, status = app_module.api_artifacts_download()
                    self.assertEqual(status, 403)

            with (
                patch.object(app_module, "NEW_DIR", root),
                patch.object(app_module, "BATCH", batch),
                patch.object(app_module, "_ensure_batch", lambda: None),
                patch.object(app_module, "_send_excel_attachment", lambda value: value),
                patch.object(app_module, "IDENTITY", FakeIdentity("superadmin")),
            ):
                with app_module.app.test_request_context(f"/api/artifacts/download?file={filename}"):
                    self.assertEqual(app_module.api_artifacts_download(), path)


if __name__ == "__main__":
    unittest.main(verbosity=2)
