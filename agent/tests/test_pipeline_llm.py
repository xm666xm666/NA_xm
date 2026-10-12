"""pipeline_llm 默认规划测试。"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
AGENT = ROOT / "agent"
if str(AGENT) not in sys.path:
    sys.path.insert(0, str(AGENT))

from lib.pipeline_llm import _default_plan, plan_pipeline


def test_default_plan_extract_only():
    plan = _default_plan({
        "raw_text": "ep-123",
        "connection": {},
        "sites": [],
        "options": {"run_extract": True, "run_batch": True, "run_summary": True},
    })
    assert "extract" in plan.steps
    assert "batch" not in plan.steps
    assert any("New API" in w for w in plan.warnings)


def test_default_plan_all_steps():
    plan = _default_plan({
        "raw_text": "ep-123",
        "connection": {"base_url": "http://localhost:3000"},
        "sites": [{"base_url": "http://a", "username": "admin", "password": "x"}],
        "options": {"run_extract": True, "run_batch": True, "run_summary": True},
    })
    assert plan.steps == ["extract", "batch", "summary"]
    assert plan.proceed
    assert "overview" not in plan.steps
    assert "analyze" not in plan.steps


def test_default_plan_overview_analyze_standalone():
    plan = _default_plan({
        "raw_text": "",
        "connection": {},
        "sites": [],
        "options": {
            "run_extract": False,
            "run_batch": False,
            "run_summary": False,
            "run_overview": True,
            "run_analyze": True,
        },
    })
    assert plan.steps == ["overview", "analyze"]
    assert plan.proceed


def test_plan_without_llm_config():
    plan = plan_pipeline(
        {"raw_text": "x", "connection": {}, "sites": [], "options": {}},
        api_base="",
        api_key="",
        model="gpt-4o-mini",
        use_llm=True,
    )
    assert not plan.invoked
    assert "extract" in plan.steps


if __name__ == "__main__":
    test_default_plan_extract_only()
    test_default_plan_all_steps()
    test_default_plan_overview_analyze_standalone()
    test_plan_without_llm_config()
    print("ok")
