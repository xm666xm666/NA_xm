"""pipeline_runner 步骤求交与剩余步骤。"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipeline_runner import intersect_plan_steps, remaining_steps, normalize_step_order, run_step


def test_intersect_respects_user_checks():
    final, warnings = intersect_plan_steps(
        ["extract", "batch", "summary"],
        {"run_extract": True, "run_batch": False, "run_summary": True},
    )
    assert final == ["extract", "summary"]
    assert any("裁掉" in w for w in warnings)


def test_intersect_keeps_downstream_when_checked():
    final, _ = intersect_plan_steps(
        ["extract", "summary"],
        {
            "run_extract": True,
            "run_batch": False,
            "run_summary": True,
            "run_upstream": False,
            "run_overview": True,
            "run_analyze": True,
        },
    )
    assert final == ["extract", "summary", "overview", "analyze"]


def test_user_wanted_defaults_exclude_downstream():
    from pipeline_runner import user_wanted_steps

    assert user_wanted_steps({}) == ["extract", "batch", "summary"]


def test_remaining_from_batch():
    assert remaining_steps(["extract", "batch", "summary"], "batch") == ["batch", "summary"]
    assert remaining_steps(["extract", "batch", "summary"], "plan") == [
        "extract",
        "batch",
        "summary",
    ]


def test_normalize_order():
    assert normalize_step_order(["analyze", "summary", "extract", "overview", "foo"]) == [
        "extract",
        "summary",
        "overview",
        "analyze",
    ]


def _dummy_step_kwargs(**batch):
    return dict(
        raw_text="",
        connection={},
        sites=[],
        options={},
        llm_config={},
        channel_lines="",
        extract_channels=lambda *a, **k: None,
        batch=batch,
        project_dir=Path("."),
    )


def test_overview_skips_without_files():
    sr, _ = run_step(
        "overview",
        **_dummy_step_kwargs(
            agent_build_overview=lambda _p: {
                "ok": False,
                "skipped": True,
                "message": "excel/ 中没有③网关汇总或⑤上游文件，跳过⑥总览",
            }
        ),
    )
    assert sr.status == "skipped"
    assert "跳过" in sr.message


def test_analyze_skips_without_overview():
    sr, _ = run_step(
        "analyze",
        **_dummy_step_kwargs(
            agent_run_analysis=lambda _p: {
                "ok": False,
                "skipped": True,
                "message": "未找到一表总览，跳过智能分析",
            }
        ),
    )
    assert sr.status == "skipped"


def test_upstream_dry_run_skips():
    kwargs = _dummy_step_kwargs()
    kwargs["options"] = {"dry_run": True}
    sr, _ = run_step("upstream", **kwargs)
    assert sr.status == "skipped"
    assert "试运行" in sr.message


def test_overview_ok_returns_file():
    sr, _ = run_step(
        "overview",
        **_dummy_step_kwargs(
            agent_build_overview=lambda _p: {
                "ok": True,
                "file": "excel/ai网关令牌及渠道列表_一表总览_20260825120000.xlsx",
                "message": "已写入总览",
            }
        ),
    )
    assert sr.status == "ok"
    assert sr.data["file"].endswith(".xlsx")


if __name__ == "__main__":
    test_intersect_respects_user_checks()
    test_intersect_keeps_downstream_when_checked()
    test_user_wanted_defaults_exclude_downstream()
    test_remaining_from_batch()
    test_normalize_order()
    test_overview_skips_without_files()
    test_analyze_skips_without_overview()
    test_upstream_dry_run_skips()
    test_overview_ok_returns_file()
    print("ok")
