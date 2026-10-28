"""New API v1.0.3 token response encryption fallback."""

from __future__ import annotations

import base64
import sys
from pathlib import Path
from types import SimpleNamespace

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding

BATCH_DIR = Path(__file__).resolve().parents[1]
if str(BATCH_DIR) not in sys.path:
    sys.path.insert(0, str(BATCH_DIR))

from lib.api_client import NewAPIClient  # noqa: E402


def _response(status: int, payload: dict) -> SimpleNamespace:
    response = SimpleNamespace(status_code=status, payload=payload)
    response.json = lambda: response.payload
    response.raise_for_status = lambda: None if status < 400 else None
    return response


def _encrypted_payload(client: NewAPIClient, header: str, token: dict) -> dict:
    public_key = serialization.load_der_public_key(base64.b64decode(header))
    ciphertext = public_key.encrypt(
        str(token["key"]).encode("utf-8"),
        padding.OAEP(
            mgf=padding.MGF1(algorithm=hashes.SHA256()),
            algorithm=hashes.SHA256(),
            label=None,
        ),
    )
    return {**token, "key": base64.b64encode(ciphertext).decode("ascii")}


def _fallback_session(client: NewAPIClient, token: dict):
    calls = []

    def request(method, url, *, params=None, json=None, headers=None, timeout=None):
        calls.append({"method": method, "url": url, "headers": headers})
        if "X-Token-Crypto-Key" not in headers:
            return _response(400, {"success": False, "message": "missing X-Token-Crypto-Key header"})
        encrypted = _encrypted_payload(client, headers["X-Token-Crypto-Key"], token)
        if method == "GET" and url.endswith("/api/token/"):
            data = {"items": [encrypted], "total": 1}
        elif method == "GET" and url.endswith("/api/token/search"):
            data = [encrypted]
        else:
            data = encrypted
        return _response(200, {"success": True, "data": data})

    return SimpleNamespace(request=request), calls


def test_token_list_falls_back_to_rsa_response_encryption():
    token = {"id": 1, "name": "prod", "key": "sk-secret"}
    client = NewAPIClient("https://new-api.example/")
    session, calls = _fallback_session(client, token)
    client.session = session

    items = client.list_all_tokens()

    assert items == [token]
    assert [call["headers"].get("X-Token-Crypto-Key") for call in calls] == [None, client._token_crypto_key_header]
    public_key = serialization.load_der_public_key(base64.b64decode(client._token_crypto_key_header))
    assert getattr(public_key, "key_size", 0) == 2048


def test_token_detail_update_and_search_decrypt_key():
    token = {"id": 2, "name": "uat", "key": "sk-new"}
    client = NewAPIClient("https://new-api.example")
    session, _ = _fallback_session(client, token)
    client.session = session

    assert client.get_token(2) == token
    assert client.update_token({"id": 2})["data"] == token
    assert client.search_tokens("uat") == [token]
