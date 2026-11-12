from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import agent_jobs


def test_summary_is_safe_filterable_and_contains_only_job_artifacts():
    store = agent_jobs.AgentJobStore()
    job = store.create(
        scenario="new_project",
        goal="接入 alpha 项目",
        raw_text="raw-api-key-should-not-leak",
        connection={"password": "password-should-not-leak"},
        sites=[],
        options={"run_extract": True},
        llm_config={"api_key": "llm-key-should-not-leak"},
        channel_lines="channel-key-should-not-leak",
    )
    job.steps = [
        {
            "id": "summary",
            "status": "ok",
            "data": {"file": "excel/ai网关令牌及渠道列表_20261112000000.xlsx"},
        },
        {
            "id": "token_export",
            "status": "ok",
            "data": {"export_text": "token-plaintext-should-not-leak"},
        },
    ]
    summaries = store.list_summaries(status="queued", search="alpha", limit=30)
    assert len(summaries) == 1
    summary = summaries[0]
    serialized = json.dumps(summary, ensure_ascii=False)
    assert "should-not-leak" not in serialized
    assert "raw_text" not in summary
    assert "channel_lines" not in summary
    assert "connection" not in summary
    assert summary["artifacts"] == [
        {
            "kind": "summary",
            "file": "excel/ai网关令牌及渠道列表_20261112000000.xlsx",
            "filename": "ai网关令牌及渠道列表_20261112000000.xlsx",
            "download_url": f"/api/agent/jobs/{job.id}/artifacts/summary/download",
        }
    ]
    assert store.list_summaries(status="failed") == []


def test_analysis_artifact_is_available_in_history_and_job_detail():
    store = agent_jobs.AgentJobStore()
    job = store.create(
        scenario="overview",
        goal="生成智能分析",
        raw_text="",
        connection={},
        sites=[],
        options={},
        llm_config={},
    )
    file = "excel/智能分析表格_20261112000000.xlsx"
    job.steps = [{"id": "analyze", "status": "ok", "data": {"file": file}}]
    expected = [
        {
            "kind": "analysis",
            "file": file,
            "filename": "智能分析表格_20261112000000.xlsx",
            "download_url": f"/api/agent/jobs/{job.id}/artifacts/analysis/download",
        }
    ]

    assert job.to_summary()["artifacts"] == expected
    assert job.to_dict()["artifacts"] == expected
