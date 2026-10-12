"""使用日志模型名称模糊匹配。"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from lib.log_exporter import model_name_matches  # noqa: E402


def test_substring_match():
    log = {"model_name": "demo-alpha-test-glm-x"}
    assert model_name_matches(log, "glm-x")
    assert model_name_matches(log, "GLM-X")
    assert model_name_matches(log, "demo-alpha-test-glm-x")
    assert not model_name_matches(log, "glm-y")


def test_upstream_model_match():
    log = {
        "model_name": "alias-a",
        "other": {"upstream_model_name": "demo-proj-glm-x-prod", "is_model_mapped": True},
    }
    assert model_name_matches(log, "glm-x")


def test_empty_query_matches_all():
    assert model_name_matches({"model_name": "anything"}, "")
    assert model_name_matches({"model_name": "anything"}, "  ")


def test_matches_model_alias_field():
    assert model_name_matches({"model": "deepseek-v3.2"}, "deepseek-v3.2")
    assert model_name_matches({"other": {"model_name": "deepseek-v3.2"}}, "v3.2")


if __name__ == "__main__":
    test_substring_match()
    test_upstream_model_match()
    test_empty_query_matches_all()
    test_matches_model_alias_field()
    print("ok")
