"""一表总览已禁用建议重新启用接口回归测试。"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

_tempdir = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
os.environ.setdefault("DATABASE_URL", f"sqlite:///{Path(_tempdir.name, 'hygiene-enable.db').as_posix()}")
os.environ["WEB_AUTO_CREATE_SCHEMA"] = "true"
os.environ["BOOTSTRAP_ADMIN_PASSWORD"] = "hygiene-enable-test-password-2026"

import app as server  # noqa: E402


def install_fake_batch(monkeypatch: pytest.MonkeyPatch) -> dict:
    calls = {"status": [], "marked": []}
    selected_rows = [
        {"key": "channel-key", "disabled_sheet": False},
        {"key": "token-key", "disabled_sheet": True},
    ]

    def select_enable_actions(payload, keys):
        wanted = set(keys or [])
        return [row for row in selected_rows if row["key"] in wanted]

    def preview_enable_from_actions(rows):
        return {
            "channels": {"test": "channel-off\tgateway", "uat": "", "prod": ""},
            "tokens": {"test": "", "uat": "", "prod": "token-off\ttokens"},
            "channel_count": {"test": 1, "uat": 0, "prod": 0},
            "token_count": {"test": 0, "uat": 0, "prod": 1},
            "action_keys": [row["key"] for row in rows],
        }

    def run_status(**kwargs):
        calls["status"].append(kwargs)
        dry_run = kwargs["dry_run"]
        return SimpleNamespace(
            matched_count=1,
            updated_count=0 if dry_run else 1,
            failed_count=0,
            skipped_count=0,
            items=[],
            dry_run=dry_run,
        )

    def mark_actions_enabled(root_dir, filename, rows):
        calls["marked"].append((root_dir, filename, rows))

    monkeypatch.setattr(
        server,
        "BATCH",
        {
            "resolve_excel_path": lambda root_dir, raw: Path("智能分析表格_enable.xlsx"),
            "load_analysis_payload": lambda path, root_dir: {},
            "select_enable_actions": select_enable_actions,
            "preview_enable_from_actions": preview_enable_from_actions,
            "run_channel_batch_status": run_status,
            "run_token_batch_status": run_status,
            "mark_actions_enabled": mark_actions_enabled,
        },
    )
    monkeypatch.setattr(server, "_ensure_batch", lambda: None)
    monkeypatch.setattr(server, "_hygiene_env_body", lambda env, body: {"base_url": "https://na.example.com"})
    monkeypatch.setattr(server, "_parse_base_url", lambda value: value)
    monkeypatch.setattr(server, "_parse_auth", lambda body: {})
    return calls


@pytest.mark.parametrize("dry_run", [True, False])
def test_confirm_enable_uses_enable_action_and_marks_only_after_confirmation(monkeypatch: pytest.MonkeyPatch, dry_run: bool):
    calls = install_fake_batch(monkeypatch)
    with server.app.test_request_context(
        "/api/hygiene/confirm-enable",
        method="POST",
        json={
            "file": "智能分析表格_enable.xlsx",
            "keys": ["channel-key", "token-key"],
            "dry_run": dry_run,
        },
    ):
        response = server.api_hygiene_confirm_enable()

    payload = response.get_json()
    assert response.status_code == 200
    assert payload["success"] is True
    assert payload["data"]["action"] == "enable"
    assert len(calls["status"]) == 2
    assert all(call["action"] == "enable" for call in calls["status"])
    assert all(call["dry_run"] is dry_run for call in calls["status"])
    assert len(calls["marked"]) == (0 if dry_run else 1)
