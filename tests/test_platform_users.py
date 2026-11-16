"""NA 信息上游用户管理适配与路由回归测试。"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

_tempdir = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
os.environ.setdefault("DATABASE_URL", f"sqlite:///{Path(_tempdir.name, 'platform-users.db').as_posix()}")
os.environ["WEB_AUTO_CREATE_SCHEMA"] = "true"
os.environ["BOOTSTRAP_ADMIN_PASSWORD"] = "platform-users-test-password-2026"

import app as server  # noqa: E402
from batch.lib.api_client import NewAPIClient  # noqa: E402
from webapp import platform_users  # noqa: E402


def _response(payload, status: int = 200):
    response = SimpleNamespace(status_code=status, payload=payload)
    response.json = lambda: response.payload
    response.raise_for_status = lambda: None
    return response


def _client(handler) -> NewAPIClient:
    client = NewAPIClient("https://upstream.example", user_id=17, timeout=120)
    client.session = SimpleNamespace(request=handler)
    return client


def _invoke(route: str, method: str = "GET", body: dict | None = None, query: str = ""):
    with server.app.test_request_context(f"/api/platform/test/{route}{query}", method=method, json=body):
        endpoint = {
            "users": server.api_platform_users,
            "users/options": server.api_platform_user_options,
            "users/create": server.api_platform_user_create,
        }.get(route)
        if endpoint:
            result = endpoint("test")
        elif route.startswith("users/") and route.endswith("/manage"):
            result = server.api_platform_user_manage("test", int(route.split("/")[1]))
        elif route.startswith("users/") and route.rsplit("/", 1)[-1] in {"passkey", "2fa"}:
            result = server.api_platform_user_security_reset("test", int(route.split("/")[1]), route.rsplit("/", 1)[-1])
        elif route.startswith("users/"):
            user_id = int(route.split("/")[1])
            result = (
                server.api_platform_user_update("test", user_id)
                if method == "PUT"
                else server.api_platform_user_detail("test", user_id)
            )
        else:
            raise AssertionError(f"未登记的测试路由：{route}")
    if isinstance(result, tuple):
        response, status = result
    else:
        response, status = result, result.status_code
    return status, response.get_json()


@pytest.fixture
def upstream(monkeypatch):
    calls = []

    def handler(method, url, **kwargs):
        calls.append({"method": method, "url": url, **kwargs})
        return _response({"success": True, "data": None})

    client = _client(handler)
    audit = MagicMock()
    monkeypatch.setattr(server, "_platform_site_client", lambda env: (env, {}, client))
    monkeypatch.setattr(server.IDENTITY.store, "audit", audit)
    return client, calls, audit


def test_normalize_list_query_and_reject_invalid_values():
    assert platform_users.normalize_list_query("2", "100", " alice ", " vip ") == {
        "page": 2,
        "page_size": 100,
        "keyword": "alice",
        "group": "vip",
    }
    for values in [("0", "20", "", ""), ("1.5", "20", "", ""), ("1", "101", "", ""), ("1", "20", "x" * 101, "")]:
        with pytest.raises(ValueError):
            platform_users.normalize_list_query(*values)


def test_create_record_is_restricted_to_common_user_and_strong_password():
    record = platform_users.validate_create_record(
        {"username": " alice ", "display_name": "", "password": "Strong-pass-2026", "remark": "测试"}
    )
    assert record["username"] == "alice"
    assert record["display_name"] == "alice"
    assert record["role"] == 1

    for payload in [
        {"username": "alice", "password": "weak"},
        {"username": "alice", "password": "Strong-pass-2026", "role": 100},
        {"username": "alice", "password": "Password1!", "remark": 1},
    ]:
        with pytest.raises(ValueError):
            platform_users.validate_create_record(payload)


def test_update_record_requires_complete_safe_fields_and_validates_quota():
    record = platform_users.validate_update_record(
        7,
        {"username": "alice", "display_name": "Alice", "password": "", "remark": "", "group": "vip", "quota": "-500"},
    )
    assert record == {
        "id": 7,
        "username": "alice",
        "display_name": "Alice",
        "password": "",
        "remark": "",
        "group": "vip",
        "quota": -500,
    }
    base = dict(record)
    base.pop("id")
    for changes in [{"quota": "1.5"}, {"role": 100}, {"password": "weak"}, {"group": ""}]:
        with pytest.raises(ValueError):
            platform_users.validate_update_record(7, {**base, **changes})


def test_list_uses_zero_based_first_page_and_filters_sensitive_fields():
    def handler(method, url, **kwargs):
        assert method == "GET"
        assert url == "https://upstream.example/api/user/"
        assert kwargs["params"] == {"p": 0, "page_size": 20}
        assert kwargs["headers"] == {"New-Api-User": "17", "Accept": "application/json"}
        assert kwargs["timeout"] == 120
        return _response(
            {
                "success": True,
                "data": {
                    "items": [{"id": 2, "username": "alice", "password": "secret", "access_token": "token", "status": 1}],
                    "total": 2,
                },
            }
        )

    result = platform_users.list_users(_client(handler), platform_users.normalize_list_query(1, 20, "", ""))

    assert result == {"items": [{"id": 2, "username": "alice", "status": 1}], "page": 1, "page_size": 20, "total": 2}


def test_search_uses_keyword_group_and_second_page():
    def handler(method, url, **kwargs):
        assert url == "https://upstream.example/api/user/search"
        assert kwargs["params"] == {"p": 2, "page_size": 50, "keyword": "alice", "group": "vip"}
        return _response({"success": True, "data": [{"id": 1, "username": "alice", "totp_secret": "secret"}]})

    result = platform_users.list_users(_client(handler), platform_users.normalize_list_query(2, 50, "alice", "vip"))

    assert result["items"] == [{"id": 1, "username": "alice"}]
    assert result["total"] == 1


def test_detail_adds_empty_password_without_exposing_upstream_secrets():
    client = _client(
        lambda method, url, **kwargs: _response(
            {"success": True, "data": {"id": 7, "username": "alice", "password": "hash", "access_token": "secret"}}
        )
    )

    assert platform_users.get_user(client, 7) == {"id": 7, "username": "alice", "password": ""}


@pytest.mark.parametrize(
    ("route", "method", "body", "upstream_method", "upstream_url", "upstream_body"),
    [
        ("users/create", "POST", {"username": "alice", "display_name": "Alice", "password": "Strong-pass-2026", "remark": "note"}, "POST", "/api/user/", {"username": "alice", "display_name": "Alice", "password": "Strong-pass-2026", "remark": "note", "role": 1}),
        ("users/7", "PUT", {"username": "alice", "display_name": "Alice", "password": "", "remark": "note", "group": "vip", "quota": 100}, "PUT", "/api/user/", {"id": 7, "username": "alice", "display_name": "Alice", "password": "", "remark": "note", "group": "vip", "quota": 100}),
        *[("users/7/manage", "POST", {"action": action}, "POST", "/api/user/manage", {"id": 7, "action": action}) for action in sorted(platform_users.MANAGE_ACTIONS)],
        ("users/7/passkey", "DELETE", None, "DELETE", "/api/user/7/reset_passkey", None),
        ("users/7/2fa", "DELETE", None, "DELETE", "/api/user/7/2fa", None),
    ],
)
def test_write_routes_call_expected_upstream_api(upstream, route, method, body, upstream_method, upstream_url, upstream_body):
    _client, calls, audit = upstream

    status, payload = _invoke(route, method, body)

    assert status == 200
    assert payload["success"] is True
    assert len(calls) == 1
    assert calls[0]["method"] == upstream_method
    assert calls[0]["url"] == f"https://upstream.example{upstream_url}"
    assert calls[0].get("json") == upstream_body
    audit.assert_called_once()
    assert "Strong-pass-2026" not in str(audit.call_args)


def test_write_response_filters_sensitive_upstream_fields(upstream):
    def handler(method, url, **kwargs):
        return _response({"success": True, "data": {"id": 7, "username": "alice", "password": "secret", "access_token": "token", "role": 10}})

    client = _client(handler)

    assert platform_users.update_user(client, {"id": 7}) == {"id": 7, "username": "alice", "role": 10}


def test_upstream_error_is_returned_without_auditing_success(upstream, monkeypatch):
    _upstream_client, _calls, audit = upstream

    def handler(method, url, **kwargs):
        return _response({"success": False, "message": "无权更新同权限用户"})

    client = _client(handler)
    monkeypatch.setattr(server, "_platform_site_client", lambda env: (env, {}, client))

    status, payload = _invoke("users/7/manage", "POST", {"action": "promote"})

    assert status == 400
    assert payload == {"success": False, "message": "无权更新同权限用户"}
    audit.assert_not_called()


def test_network_error_uses_bad_gateway(monkeypatch):
    client = NewAPIClient("https://upstream.example")
    client.session = SimpleNamespace(request=MagicMock(side_effect=server.requests.Timeout("timed out")))
    monkeypatch.setattr(server, "_platform_site_client", lambda env: (env, {}, client))

    status, payload = _invoke("users", query="?page=1&page_size=20")

    assert status == 502
    assert payload["success"] is False


def test_invalid_write_is_rejected_before_connecting(monkeypatch):
    connect = MagicMock()
    monkeypatch.setattr(server, "_platform_site_client", connect)

    status, payload = _invoke("users/7/manage", "POST", {"action": "make_root"})

    assert status == 400
    assert payload["success"] is False
    connect.assert_not_called()


def test_options_tolerates_group_and_status_failures():
    def handler(method, url, **kwargs):
        if url.endswith("/api/group/"):
            return _response({"success": False, "message": "旧版无此接口"}, 404)
        return _response({"success": False, "message": "状态不可用"}, 404)

    client = _client(handler)
    client.list_user_groups = MagicMock(return_value=["default", "vip"])

    result = platform_users.get_user_options(client)

    assert result["groups"] == ["default", "vip"]
    assert result["quota_per_unit"] == 500000
    assert result["warnings"] == ["状态不可用"]


def test_options_reads_group_and_quota_settings():
    def handler(method, url, **kwargs):
        if url.endswith("/api/group/"):
            return _response({"success": True, "data": ["default", {"name": "vip"}]})
        return _response({"success": True, "data": {"quota_per_unit": 1000000, "quota_display_type": "TOKENS"}})

    result = platform_users.get_user_options(_client(handler))

    assert result["groups"] == ["default", "vip"]
    assert result["quota_per_unit"] == 1000000
    assert result["quota_display_type"] == "TOKENS"
    assert result["warnings"] == []


def test_users_html_requires_platform_feature_and_disables_cache(monkeypatch):
    guarded_features = []

    def allow_and_record(feature=None):
        guarded_features.append(feature)
        return None

    monkeypatch.setattr(server.IDENTITY, "page_guard", allow_and_record)
    with server.app.test_request_context("/static/platform-users/platform-users.html?env=test"):
        response = server.static_files("platform-users/platform-users.html")

    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "no-store"
    assert guarded_features == [server.FEATURE_PLATFORM]


def test_na_information_entry_opens_user_management_page():
    html = (PROJECT_ROOT / "static" / "platform_ui.html").read_text(encoding="utf-8")

    assert 'id="userManagementBtn"' in html
    assert "platform-users/platform-users.html?env=" in html
