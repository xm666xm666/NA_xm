"""NA 信息上游会话失效恢复回归测试。"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, call

import pytest
import requests

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

_tempdir = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
os.environ.setdefault("DATABASE_URL", f"sqlite:///{Path(_tempdir.name, 'platform-session.db').as_posix()}")
os.environ["WEB_AUTO_CREATE_SCHEMA"] = "true"
os.environ["BOOTSTRAP_ADMIN_PASSWORD"] = "platform-session-test-password-2026"

import app as server  # noqa: E402
from batch.lib import platform_info  # noqa: E402


def _http_error(status: int) -> requests.HTTPError:
    response = requests.Response()
    response.status_code = status
    response.url = "https://upstream.example/api/channel/"
    return requests.HTTPError(f"{status} Client Error", response=response)


def _invoke(endpoint, *args):
    with server.app.test_request_context("/api/platform/test/channels"):
        result = endpoint("test", *args)
    if isinstance(result, tuple):
        response, status = result
    else:
        response, status = result, result.status_code
    return status, response.get_json()


def test_force_refresh_replaces_only_the_matching_memory_client(monkeypatch):
    cache = {}
    monkeypatch.setattr(platform_info, "_CLIENT_CACHE", cache)
    clients = []

    class Client:
        def __init__(self, base_url):
            self.base_url = base_url
            clients.append(self)

        def is_admin(self):
            return True

    authenticate = MagicMock()
    monkeypatch.setattr(platform_info, "NewAPIClient", Client)
    monkeypatch.setattr(platform_info, "authenticate_client", authenticate)
    auth = {"username": "admin", "password": "secret"}

    original = platform_info.connected_client("https://upstream.example", auth)
    assert platform_info.connected_client("https://upstream.example", auth) is original
    refreshed = platform_info.connected_client("https://upstream.example", auth, force_refresh=True)

    assert refreshed is not original
    assert clients == [original, refreshed]
    assert authenticate.call_count == 2
    assert len(cache) == 1
    assert platform_info.connected_client("https://upstream.example", auth) is refreshed


@pytest.mark.parametrize(
    ("endpoint", "operation_key", "rows"),
    [
        (server.api_platform_channels, "platform_list_channels", [{"id": 1, "name": "channel"}]),
        (server.api_platform_tokens, "platform_list_tokens", [{"id": 2, "name": "token"}]),
        (server.api_platform_groups, "platform_list_groups", ["default"]),
    ],
)
def test_read_reconnects_and_retries_once_after_401(monkeypatch, endpoint, operation_key, rows):
    stale_client = MagicMock(name="stale_client")
    refreshed_client = MagicMock(name="refreshed_client")
    connect = MagicMock(side_effect=[("test", {}, stale_client), ("test", {}, refreshed_client)])
    operation = MagicMock(side_effect=[_http_error(401), rows])
    monkeypatch.setattr(server, "_platform_site_client", connect)
    monkeypatch.setitem(server.BATCH, operation_key, operation)

    status, payload = _invoke(endpoint)

    assert status == 200
    assert payload == {"success": True, "env": "test", "data": rows}
    assert connect.call_args_list == [call("test"), call("test", force_refresh=True)]
    assert operation.call_args_list == [call(stale_client), call(refreshed_client)]


@pytest.mark.parametrize("status_code", [400, 403, 500])
def test_read_does_not_reconnect_for_non_401_errors(monkeypatch, status_code):
    client = MagicMock()
    connect = MagicMock(return_value=("test", {}, client))
    operation = MagicMock(side_effect=_http_error(status_code))
    monkeypatch.setattr(server, "_platform_site_client", connect)
    monkeypatch.setitem(server.BATCH, "platform_list_channels", operation)

    status, payload = _invoke(server.api_platform_channels)

    assert status == 400
    assert payload["success"] is False
    connect.assert_called_once_with("test")
    operation.assert_called_once_with(client)


def test_read_retries_401_only_once(monkeypatch):
    stale_client = MagicMock(name="stale_client")
    refreshed_client = MagicMock(name="refreshed_client")
    connect = MagicMock(side_effect=[("test", {}, stale_client), ("test", {}, refreshed_client)])
    operation = MagicMock(side_effect=[_http_error(401), _http_error(401)])
    monkeypatch.setattr(server, "_platform_site_client", connect)
    monkeypatch.setitem(server.BATCH, "platform_list_channels", operation)

    status, payload = _invoke(server.api_platform_channels)

    assert status == 400
    assert payload["success"] is False
    assert connect.call_count == 2
    assert operation.call_count == 2
