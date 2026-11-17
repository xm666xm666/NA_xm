from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import agent_jobs
import app as app_module


class FakeIdentity:
    def __init__(self, user_id: int = 1, role: str = "user"):
        self.user = SimpleNamespace(id=user_id, role=role)

    def current_user(self):
        return self.user

    def has_feature(self, _feature: str) -> bool:
        return True


def _create_job(store: agent_jobs.AgentJobStore, owner_user_id: int, goal: str):
    return store.create(
        goal=goal,
        raw_text="private text",
        connection={},
        sites=[],
        options={},
        llm_config={},
        owner_user_id=owner_user_id,
    )


@pytest.fixture
def owned_jobs(monkeypatch):
    store = agent_jobs.AgentJobStore()
    own = _create_job(store, 1, "own job")
    other = _create_job(store, 2, "other job")
    monkeypatch.setattr(agent_jobs, "STORE", store)
    monkeypatch.setattr(app_module, "IDENTITY", FakeIdentity())
    return own, other


def test_job_list_and_detail_are_limited_to_current_owner(owned_jobs):
    own, other = owned_jobs
    with app_module.app.test_request_context("/api/agent/jobs"):
        response = app_module.api_agent_jobs_list()
        assert [item["id"] for item in response.get_json()["jobs"]] == [own.id]

    with app_module.app.test_request_context(f"/api/agent/jobs/{other.id}"):
        response, status = app_module.api_agent_jobs_get(other.id)
        assert status == 404
        assert "private text" not in response.get_data(as_text=True)

    with app_module.app.test_request_context(f"/api/agent/jobs/{other.id}/events"):
        _response, status = app_module.api_agent_jobs_events(other.id)
        assert status == 404


@pytest.mark.parametrize(
    ("method", "path", "payload"),
    [
        ("GET", "/api/agent/jobs/{job_id}/artifacts/summary/download", None),
        ("POST", "/api/agent/jobs/{job_id}/preflight", {}),
        ("PATCH", "/api/agent/jobs/{job_id}/plan", {"channel_lines": "attacker edit"}),
        ("POST", "/api/agent/jobs/{job_id}/confirm", {"channel_lines": "attacker edit"}),
        ("POST", "/api/agent/jobs/{job_id}/start", {}),
        ("POST", "/api/agent/jobs/{job_id}/cancel", {}),
        ("POST", "/api/agent/jobs/{job_id}/retry", {}),
    ],
)
def test_cross_owner_job_operations_return_404_without_mutation(owned_jobs, method, path, payload):
    _own, other = owned_jobs
    other.status = "failed"
    other.channel_lines = "original"
    other.confirmed = False
    url = path.format(job_id=other.id)
    handlers = {
        "GET": app_module.api_agent_job_artifact_download,
        "PATCH": app_module.api_agent_jobs_patch_plan,
    }
    with app_module.app.test_request_context(url, method=method, json=payload):
        if method == "GET":
            response, status = handlers[method](other.id, "summary")
        elif method == "PATCH":
            response, status = handlers[method](other.id)
        elif url.endswith("/preflight"):
            response, status = app_module.api_agent_jobs_preflight(other.id)
        elif url.endswith("/confirm"):
            response, status = app_module.api_agent_jobs_confirm(other.id)
        elif url.endswith("/start"):
            response, status = app_module.api_agent_jobs_start(other.id)
        elif url.endswith("/cancel"):
            response, status = app_module.api_agent_jobs_cancel(other.id)
        else:
            response, status = app_module.api_agent_jobs_retry(other.id)
        assert status == 404
        assert response.get_json()["message"] == "任务不存在"
    assert other.channel_lines == "original"
    assert other.confirmed is False
    assert other.cancel_requested is False
    assert other.status == "failed"


def test_superadmin_can_explicitly_access_all_jobs(owned_jobs, monkeypatch):
    own, other = owned_jobs
    monkeypatch.setattr(app_module, "IDENTITY", FakeIdentity(user_id=99, role="superadmin"))
    with app_module.app.test_request_context("/api/agent/jobs"):
        response = app_module.api_agent_jobs_list()
        assert {item["id"] for item in response.get_json()["jobs"]} == {own.id, other.id}
    with app_module.app.test_request_context(f"/api/agent/jobs/{other.id}"):
        response = app_module.api_agent_jobs_get(other.id)
        assert response.get_json()["job"]["id"] == other.id


def test_missing_identity_fails_closed(owned_jobs, monkeypatch):
    _own, other = owned_jobs
    monkeypatch.setattr(app_module, "IDENTITY", SimpleNamespace(current_user=lambda: None))
    with app_module.app.test_request_context(f"/api/agent/jobs/{other.id}"):
        _response, status = app_module.api_agent_jobs_get(other.id)
        assert status == 404
