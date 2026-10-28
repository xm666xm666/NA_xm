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
