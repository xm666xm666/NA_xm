from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import agent_jobs
import app as app_module


def test_summary_only_job_loads_env_sites_without_llm(tmp_path, monkeypatch):
    store = agent_jobs.AgentJobStore()
    env_sites = [
        {
            "env": "test",
            "label": "test",
            "base_url": "https://na-test.example.com",
            "username": "admin",
        }
    ]
    monkeypatch.setattr(agent_jobs, "STORE", store)
    monkeypatch.setattr(app_module, "NEW_DIR", tmp_path)
    monkeypatch.setattr(app_module, "_merge_agent_connection", lambda connection: dict(connection))
    monkeypatch.setattr(app_module, "_merge_llm_config", lambda body: {})
    monkeypatch.setattr(app_module, "_env_site_payloads", lambda: [dict(site) for site in env_sites])
    monkeypatch.setattr(app_module, "_enrich_agent_sites", lambda sites: [dict(site) for site in sites])

    job = app_module._create_agent_job_from_body(
        {
            "scenario": "inspection",
            "goal": "三站数据巡检",
            "raw_text": "",
            "sites": [],
            "options": {
                "run_extract": False,
                "run_batch": False,
                "run_summary": True,
                "use_llm_plan": False,
            },
        },
        require_confirm_default=True,
    )

    assert job.scenario == "inspection"
    assert job.sites == env_sites
    assert job.options["run_summary"] is True
    assert job.options["use_llm_plan"] is False
    assert job.llm_config == {}
