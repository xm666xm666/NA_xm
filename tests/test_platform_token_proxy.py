"""Platform editor proxy compatibility with New API token encryption."""

from __future__ import annotations

import base64
import json
import os
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

import pytest
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

_tempdir = tempfile.TemporaryDirectory()
os.environ.setdefault("DATABASE_URL", f"sqlite:///{Path(_tempdir.name, 'proxy.db').as_posix()}")
os.environ["WEB_AUTO_CREATE_SCHEMA"] = "true"
os.environ["BOOTSTRAP_ADMIN_PASSWORD"] = "proxy-test-password-2026"

import app as server  # noqa: E402
from batch.lib.api_client import NewAPIClient  # noqa: E402


def _response(status: int, payload: dict):
    response = SimpleNamespace(status_code=status, payload=payload)
    response.json = lambda: response.payload
    return response


def test_token_editor_proxy_falls_back_and_decrypts(monkeypatch):
    token = {"id": 7, "name": "prod", "key": "sk-editor"}
    client = NewAPIClient("https://upstream.example")

    def request(method, url, *, data=None, headers=None, timeout=None):
        assert method == "PUT"
        assert url == "https://upstream.example/api/token/"
        assert json.loads(data)["id"] == 7
        if "X-Token-Crypto-Key" not in headers:
            response = _response(400, {"success": False, "message": "missing X-Token-Crypto-Key header"})
        else:
            public_key = serialization.load_der_public_key(base64.b64decode(headers["X-Token-Crypto-Key"]))
            ciphertext = public_key.encrypt(
                token["key"].encode("utf-8"),
                padding.OAEP(
                    mgf=padding.MGF1(algorithm=hashes.SHA256()),
                    algorithm=hashes.SHA256(),
                    label=None,
                ),
            )
            encrypted = {**token, "key": base64.b64encode(ciphertext).decode("ascii")}
            response = _response(200, {"success": True, "data": encrypted})
        response.headers = {"Content-Type": "application/json"}
        return response

    client.session = SimpleNamespace(request=request)
    monkeypatch.setattr(server, "_platform_site_client", lambda env: (env, {}, client))

    with server.app.test_request_context(
        "/api/platform/test/upstream/api/token/",
        method="PUT",
        json={"id": 7, "name": "prod"},
    ):
        response = server.api_platform_upstream_proxy("test", "api/token/")

    assert response.status_code == 200
    assert json.loads(response.get_data(as_text=True))["data"] == token


def test_token_editor_proxy_converts_v103_fields_for_old_gateway(monkeypatch):
    token = {"id": 8, "name": "prod", "key": "sk-plain"}
    client = NewAPIClient("https://old-upstream.example")
    sent_bodies = []

    def get(url, **kwargs):
        assert url == "https://old-upstream.example/api/token/model_quota_capabilities"
        response = _response(404, {"success": False})
        response.raise_for_status = lambda: None
        return response

    def request(method, url, *, data=None, headers=None, timeout=None):
        assert url == "https://old-upstream.example/api/token/"
        sent_bodies.append(json.loads(data))
        response = _response(200, {"success": True, "data": token})
        response.headers = {"Content-Type": "application/json"}
        return response

    client.session = SimpleNamespace(get=get, request=request)
    monkeypatch.setattr(server, "_platform_site_client", lambda env: (env, {}, client))

    with server.app.test_request_context(
        "/api/platform/test/upstream/api/token/",
        method="PUT",
        json={
            "id": 8,
            "amount_limit_enabled": True,
            "input_token_limit_enabled": True,
            "input_token_period": "month",
            "input_token_limit_k": "500",
        },
    ):
        response = server.api_platform_upstream_proxy("test", "api/token/")

    assert response.status_code == 200
    assert "amount_limit_enabled" not in sent_bodies[0]
    assert "input_token_limit_enabled" not in sent_bodies[0]
    assert "input_token_period" not in sent_bodies[0]
    assert "input_token_limit_k" not in sent_bodies[0]
    assert sent_bodies[0]["unlimited_quota"] is False




def test_status_proxy_is_allowed_for_editor(monkeypatch):
    client = NewAPIClient("https://upstream.example")

    def request(method, url, **kwargs):
        assert method == "GET"
        assert url == "https://upstream.example/api/status"
        response = _response(200, {"success": True, "data": {"quota_per_unit": 500000}})
        response.headers = {"Content-Type": "application/json"}
        response.content = json.dumps({"success": True, "data": {"quota_per_unit": 500000}}).encode("utf-8")
        return response

    client.session = SimpleNamespace(request=request)
    monkeypatch.setattr(server, "_platform_site_client", lambda env: (env, {}, client))

    with server.app.test_request_context("/api/platform/test/upstream/api/status"):
        response = server.api_platform_upstream_proxy("test", "api/status")

    assert response.status_code == 200
    assert json.loads(response.get_data(as_text=True))["data"]["quota_per_unit"] == 500000


def test_group_proxy_falls_back_to_user_groups(monkeypatch):
    client = NewAPIClient("https://upstream.example")

    def request(method, url, **kwargs):
        assert method == "GET"
        assert url == "https://upstream.example/api/group/"
        response = _response(404, {"success": False})
        response.headers = {"Content-Type": "application/json"}
        response.content = b'{"success":false}'
        return response

    client.session = SimpleNamespace(request=request)
    monkeypatch.setattr(client, "list_user_groups", lambda: ["default", "vip"])
    monkeypatch.setattr(server, "_platform_site_client", lambda env: (env, {}, client))

    with server.app.test_request_context(
        "/api/platform/test/upstream/api/group/",
        method="GET",
    ):
        response = server.api_platform_upstream_proxy("test", "api/group/")

    assert response.status_code == 200
    assert json.loads(response.get_data(as_text=True))["data"] == ["default", "vip"]


@pytest.mark.parametrize(
    "dashboard_path",
    [
        "api/status",
        "api/user/self",
        "api/data",
        "api/data/",
        "api/data/self",
        "api/data/self/",
        "api/uptime/status",
    ],
)
def test_dashboard_proxy_allows_only_upstream_dashboard_reads(monkeypatch, dashboard_path):
    client = NewAPIClient("https://upstream.example", user_id=17)
    calls = []

    def request(method, url, **kwargs):
        calls.append((method, url, kwargs))
        response = _response(200, {"success": True, "data": []})
        response.headers = {"Content-Type": "application/json; charset=utf-8"}
        response.content = b'{"success":true,"data":[]}'
        return response

    client.session = SimpleNamespace(request=request)
    monkeypatch.setattr(server, "_platform_site_client", lambda env: (env, {}, client))

    with server.app.test_request_context(f"/api/platform/test/dashboard/{dashboard_path}"):
        response = server.api_platform_dashboard_proxy("test", dashboard_path)

    assert response.status_code == 200
    assert response.content_type == "application/json; charset=utf-8"
    method, url, kwargs = calls[0]
    assert method == "GET"
    assert url == f"https://upstream.example/{dashboard_path}"
    assert kwargs["headers"] == {"New-Api-User": "17", "Accept": "application/json"}
    assert kwargs["timeout"] == 120


def test_dashboard_proxy_preserves_query_and_extends_existing_timeout(monkeypatch):
    client = NewAPIClient("https://upstream.example", timeout=180)
    captured = {}

    def request(method, url, **kwargs):
        captured.update(method=method, url=url, **kwargs)
        response = _response(200, {"success": True, "data": []})
        response.headers = {"Content-Type": "application/json"}
        response.content = b'{"success":true,"data":[]}'
        return response

    client.session = SimpleNamespace(request=request)
    monkeypatch.setattr(server, "_platform_site_client", lambda env: (env, {}, client))
    query = "token_name=my%20token&start_timestamp=100&end_timestamp=200"

    with server.app.test_request_context(f"/api/platform/test/dashboard/api/data/self/?{query}"):
        response = server.api_platform_dashboard_proxy("test", "api/data/self/")

    assert response.status_code == 200
    assert captured["url"] == f"https://upstream.example/api/data/self/?{query}"
    assert captured["timeout"] == 180


@pytest.mark.parametrize("dashboard_path", ["api/channel/", "api/data/export", "../api/status"])
def test_dashboard_proxy_rejects_unlisted_paths(monkeypatch, dashboard_path):
    def fail_if_called(env):
        raise AssertionError("未白名单路径不应创建上游会话")

    monkeypatch.setattr(server, "_platform_site_client", fail_if_called)
    with server.app.test_request_context(f"/api/platform/test/dashboard/{dashboard_path}"):
        response, status = server.api_platform_dashboard_proxy("test", dashboard_path)

    assert status == 404
    assert response.get_json()["message"] == "不支持的看板接口"


def test_dashboard_proxy_returns_bad_gateway_for_upstream_timeout(monkeypatch):
    client = NewAPIClient("https://upstream.example")

    def request(method, url, **kwargs):
        raise server.requests.Timeout("dashboard timed out")

    client.session = SimpleNamespace(request=request)
    monkeypatch.setattr(server, "_platform_site_client", lambda env: (env, {}, client))

    with server.app.test_request_context("/api/platform/test/dashboard/api/data/"):
        response, status = server.api_platform_dashboard_proxy("test", "api/data/")

    assert status == 502
    assert response.get_json()["success"] is False


def test_dashboard_html_requires_platform_feature_and_disables_cache(monkeypatch):
    guarded_features = []

    def allow_and_record(feature=None):
        guarded_features.append(feature)
        return None

    monkeypatch.setattr(server.IDENTITY, "page_guard", allow_and_record)
    with server.app.test_request_context("/static/platform-dashboard/platform-dashboard.html?env=test"):
        response = server.static_files("platform-dashboard/platform-dashboard.html")

    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "no-store"
    assert guarded_features == [server.FEATURE_PLATFORM]
