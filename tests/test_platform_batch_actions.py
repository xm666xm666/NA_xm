"""NA 信息渠道与令牌批量操作回归测试。"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, call

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

_tempdir = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
os.environ.setdefault("DATABASE_URL", f"sqlite:///{Path(_tempdir.name, 'platform-batch.db').as_posix()}")
os.environ["WEB_AUTO_CREATE_SCHEMA"] = "true"
os.environ["BOOTSTRAP_ADMIN_PASSWORD"] = "platform-batch-test-password-2026"

import app as server  # noqa: E402


def _invoke(kind: str, body: dict):
    with server.app.test_request_context(f"/api/platform/test/{kind}/batch", method="POST", json=body):
        result = server.api_platform_batch_action("test", kind)
    if isinstance(result, tuple):
        response, status = result
    else:
        response, status = result, result.status_code
    return status, response.get_json()


@pytest.fixture
def platform_client(monkeypatch):
    client = MagicMock()
    audit = MagicMock()
    monkeypatch.setattr(server, "_platform_site_client", lambda env: (env, {}, client))
    monkeypatch.setattr(server.IDENTITY.store, "audit", audit)
    return client, audit


def test_channel_batch_enable_deduplicates_and_reports_item_failure(platform_client, monkeypatch):
    _client, audit = platform_client
    update_status = MagicMock(side_effect=[{}, RuntimeError("上游拒绝操作")])
    monkeypatch.setitem(server.BATCH, "platform_update_channel_status", update_status)

    status, payload = _invoke("channels", {"action": "enable", "ids": [11, 12, 11]})

    assert status == 200
    assert payload["success"] is True
    assert payload["data"]["total"] == 2
    assert payload["data"]["succeeded"] == 1
    assert payload["data"]["failed"] == 1
    assert payload["data"]["items"] == [
        {"id": 11, "success": True},
        {"id": 12, "success": False, "message": "上游拒绝操作"},
    ]
    assert update_status.call_args_list == [call(_client, 11, 1), call(_client, 12, 1)]
    assert audit.call_args.kwargs["outcome"] == "partial"
    assert audit.call_args.kwargs["detail"]["ids"] == [11, 12]


def test_token_batch_disable_uses_one_authenticated_client(platform_client, monkeypatch):
    client, audit = platform_client
    update_status = MagicMock()
    monkeypatch.setitem(server.BATCH, "platform_update_token_status", update_status)

    status, payload = _invoke("tokens", {"action": "disable", "ids": [5, 6]})

    assert status == 200
    assert payload["data"]["succeeded"] == 2
    assert payload["data"]["failed"] == 0
    assert update_status.call_args_list == [call(client, 5, 2), call(client, 6, 2)]
    assert audit.call_args.args[0] == "platform.token.batch_status_updated"
    assert audit.call_args.kwargs["outcome"] == "success"


@pytest.mark.parametrize(
    ("kind", "method_name", "audit_action"),
    [
        ("channels", "delete_channels_batch", "platform.channel.batch_deleted"),
        ("tokens", "delete_tokens_batch", "platform.token.batch_deleted"),
    ],
)
def test_batch_delete_uses_upstream_bulk_endpoint(platform_client, kind, method_name, audit_action):
    client, audit = platform_client
    delete_batch = getattr(client, method_name)
    delete_batch.return_value = 2

    status, payload = _invoke(kind, {"action": "delete", "ids": [3, 4]})

    assert status == 200
    assert payload["data"]["succeeded"] == 2
    assert payload["data"]["failed"] == 0
    assert payload["data"]["items"] == [{"id": 3, "success": True}, {"id": 4, "success": True}]
    delete_batch.assert_called_once_with([3, 4])
    assert audit.call_args.args[0] == audit_action


def test_batch_delete_reports_upstream_count_mismatch(platform_client):
    client, audit = platform_client
    client.delete_channels_batch.return_value = 1

    status, payload = _invoke("channels", {"action": "delete", "ids": [3, 4]})

    assert status == 200
    assert payload["data"]["succeeded"] == 1
    assert payload["data"]["failed"] == 1
    assert payload["data"]["items"] == []
    assert audit.call_args.kwargs["outcome"] == "partial"


@pytest.mark.parametrize(
    ("kind", "body"),
    [
        ("users", {"action": "enable", "ids": [1]}),
        ("channels", {"action": "restart", "ids": [1]}),
        ("channels", {"action": "enable", "ids": []}),
        ("channels", {"action": "enable", "ids": [1, "2"]}),
        ("tokens", {"action": "delete", "ids": [True]}),
    ],
)
def test_batch_action_rejects_invalid_parameters_before_connecting(monkeypatch, kind, body):
    connect = MagicMock()
    monkeypatch.setattr(server, "_platform_site_client", connect)

    status, payload = _invoke(kind, body)

    assert status == 400
    assert payload["success"] is False
    connect.assert_not_called()
