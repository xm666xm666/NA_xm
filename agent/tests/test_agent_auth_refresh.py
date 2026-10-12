"""智能体任务刷新登录 2FA；规划上下文脱敏。"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import agent_jobs  # noqa: E402
from agent.lib.pipeline_llm import _default_plan  # noqa: E402
from pipeline_runner import _redact_plan_context  # noqa: E402


def test_apply_auth_refresh_updates_otp_without_dropping_password():
    job = agent_jobs.STORE.create(
        goal="",
        raw_text="x",
        connection={"base_url": "https://na.example.com", "username": "admin", "password": "secret"},
        sites=[{"base_url": "https://na.example.com", "username": "admin", "password": "secret"}],
        options={},
        llm_config={"api_base": "https://llm.example.com"},
    )
    agent_jobs.apply_auth_refresh(
        job,
        otp_code="654321",
        sites=[{"base_url": "https://na.example.com", "username": "admin", "otp_code": "111111"}],
    )
    assert job.connection["otp_code"] == "654321"
    assert job.connection["password"] == "secret"
    assert job.sites[0]["otp_code"] == "111111"
    snap = job.to_dict()
    assert snap["connection"]["otp_code"] == "***"
    assert snap["connection"]["password"] == "***"


def test_confirm_job_accepts_otp():
    job = agent_jobs.STORE.create(
        goal="",
        raw_text="x",
        connection={"username": "admin", "password": "p"},
        sites=[],
        options={"require_confirm": True},
        llm_config={"api_base": "https://llm.example.com"},
        channel_lines="old",
    )
    updated = agent_jobs.confirm_job(
        job.id,
        "new-line",
        otp_code="123456",
    )
    assert updated is not None
    assert updated.channel_lines == "new-line"
    assert updated.confirmed is True
    assert updated.connection["otp_code"] == "123456"


def test_redact_plan_context_hides_secrets():
    ctx = _redact_plan_context(
        raw_text="demo",
        goal="go",
        connection={
            "base_url": "https://na.example.com",
            "username": "admin",
            "password": "pw",
            "access_token": "tok",
            "otp_code": "999999",
        },
        sites=[{"base_url": "https://na-test.example.com", "password": "spw", "otp_code": "888888"}],
        options={"run_batch": True},
    )
    assert ctx["connection"]["password"] == "***"
    assert ctx["connection"]["access_token"] == "***"
    assert ctx["connection"]["otp_code"] == "(已填写)"
    assert ctx["connection"]["has_login_otp"] is True
    assert ctx["sites"][0]["password"] == "***"
    assert ctx["sites"][0]["otp_code"] == "(已填写)"
    assert "999999" not in str(ctx)
    assert "888888" not in str(ctx)


def test_default_plan_warns_when_write_without_otp():
    plan = _default_plan(
        {
            "raw_text": "demo-a",
            "connection": {"base_url": "https://na.example.com", "username": "admin"},
            "sites": [],
            "options": {"run_extract": True, "run_batch": True, "run_summary": False},
        }
    )
    assert "batch" in plan.steps
    assert any("两步验证" in w for w in plan.warnings)


if __name__ == "__main__":
    test_apply_auth_refresh_updates_otp_without_dropping_password()
    test_confirm_job_accepts_otp()
    test_redact_plan_context_hides_secrets()
    test_default_plan_warns_when_write_without_otp()
    print("ok")
