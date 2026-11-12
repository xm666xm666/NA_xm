from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import agent_jobs
import app as app_module


class FakeIdentity:
    def __init__(self, allowed: bool):
        self.allowed = allowed

    def has_feature(self, feature: str) -> bool:
        return self.allowed


def _job_with_summary(store, filename: str):
    job = store.create(
        goal="summary",
        raw_text="",
        connection={},
        sites=[],
        options={},
        llm_config={},
    )
    job.steps = [
        {
            "id": "summary",
            "status": "ok",
            "data": {"file": f"excel/{filename}"},
        }
    ]
    return job


def test_job_artifact_download_enforces_ownership_and_permissions(tmp_path, monkeypatch):
    filename = "ai网关令牌及渠道列表_20261112000000.xlsx"
    excel = tmp_path / "excel"
    excel.mkdir()
    path = excel / filename
    path.write_bytes(b"workbook")
    store = agent_jobs.AgentJobStore()
    job = _job_with_summary(store, filename)
    other = store.create(
        goal="other",
        raw_text="",
        connection={},
        sites=[],
        options={},
        llm_config={},
    )
    monkeypatch.setattr(agent_jobs, "STORE", store)
    monkeypatch.setattr(app_module, "NEW_DIR", tmp_path)
    monkeypatch.setattr(
        app_module,
        "BATCH",
        {
            "resolve_excel_path": lambda root, raw: excel / Path(str(raw)).name,
            "artifact_kind_for_filename": lambda root, name: "summary" if name == filename else None,
        },
    )
    monkeypatch.setattr(app_module, "_send_excel_attachment", lambda value: value)

    with app_module.app.test_request_context(f"/api/agent/jobs/{job.id}/artifacts/summary/download"):
        monkeypatch.setattr(app_module, "IDENTITY", FakeIdentity(True))
        assert app_module.api_agent_job_artifact_download(job.id, "summary") == path

    with app_module.app.test_request_context(f"/api/agent/jobs/{job.id}/artifacts/summary/download"):
        monkeypatch.setattr(app_module, "IDENTITY", FakeIdentity(False))
        response, status = app_module.api_agent_job_artifact_download(job.id, "summary")
        assert status == 403
        assert response.get_json()["code"] == "FORBIDDEN"

    with app_module.app.test_request_context(f"/api/agent/jobs/{other.id}/artifacts/summary/download"):
        monkeypatch.setattr(app_module, "IDENTITY", FakeIdentity(True))
        _response, status = app_module.api_agent_job_artifact_download(other.id, "summary")
        assert status == 404


def test_analysis_job_artifact_download_uses_task_owned_file(tmp_path, monkeypatch):
    filename = "智能分析表格_20261112000000.xlsx"
    excel = tmp_path / "excel"
    excel.mkdir()
    path = excel / filename
    path.write_bytes(b"analysis-workbook")
    store = agent_jobs.AgentJobStore()
    job = store.create(
        goal="analysis",
        raw_text="",
        connection={},
        sites=[],
        options={},
        llm_config={},
    )
    job.steps = [{"id": "analyze", "status": "ok", "data": {"file": f"excel/{filename}"}}]
    monkeypatch.setattr(agent_jobs, "STORE", store)
    monkeypatch.setattr(app_module, "NEW_DIR", tmp_path)
    monkeypatch.setattr(app_module, "IDENTITY", FakeIdentity(True))
    monkeypatch.setattr(
        app_module,
        "BATCH",
        {
            "resolve_excel_path": lambda root, raw: excel / Path(str(raw)).name,
            "artifact_kind_for_filename": lambda root, name: "analysis" if name == filename else None,
        },
    )
    monkeypatch.setattr(app_module, "_send_excel_attachment", lambda value: value)

    with app_module.app.test_request_context(
        f"/api/agent/jobs/{job.id}/artifacts/analysis/download?file=excel/{filename}"
    ):
        assert app_module.api_agent_job_artifact_download(job.id, "analysis") == path
