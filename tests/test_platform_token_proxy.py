"""Platform editor proxy compatibility with New API token encryption."""

from __future__ import annotations

import base64
import json
import os
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

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
