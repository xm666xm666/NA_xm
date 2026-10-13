"""产物类型归属的权限回归测试。"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BATCH_ROOT = PROJECT_ROOT / "batch"
if str(BATCH_ROOT) not in sys.path:
    sys.path.insert(0, str(BATCH_ROOT))

from lib.artifacts import artifact_kind_for_filename


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


if __name__ == "__main__":
    unittest.main(verbosity=2)
