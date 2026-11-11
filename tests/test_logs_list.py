"""使用日志页面查询接口回归测试。"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

_tempdir = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
os.environ.setdefault("DATABASE_URL", f"sqlite:///{Path(_tempdir.name, 'logs-list.db').as_posix()}")
os.environ["WEB_AUTO_CREATE_SCHEMA"] = "true"
os.environ["BOOTSTRAP_ADMIN_PASSWORD"] = "logs-list-test-password-2026"

import app as server  # noqa: E402


class FakeLogClient:
    def __init__(self, *, admin: bool = True, total: int = 257) -> None:
        self.admin = admin
        self.total = total
        self.calls: list[dict] = []

    def is_admin(self) -> bool:
        return self.admin

    def list_logs(self, **kwargs):
        self.calls.append(kwargs)
        page = kwargs["page"]
        start = (page - 1) * 100
        count = min(100, max(0, self.total - start))
        return {
            "items": [{"id": start + index + 1} for index in range(count)],
            "total": self.total,
            "page": page,
            "page_size": 100,
        }


def install_fake_batch(monkeypatch: pytest.MonkeyPatch, client: FakeLogClient) -> dict:
    context: dict = {}

    def authenticate_client(received_client, auth):
        context["client"] = received_client
        context["auth"] = auth

    batch = {
        "normalize_na_base_url": lambda value: value.rstrip("/"),
        "coerce_verify_ssl": lambda value, default: bool(value),
        "enrich_auth_from_env": lambda auth, base_url: auth,
        "NewAPIClient": lambda base_url: client,
        "authenticate_client": authenticate_client,
    }
    monkeypatch.setattr(server, "_ensure_batch", lambda: batch)
    return context


def test_logs_list_returns_up_to_100_rows_and_forwards_filters(monkeypatch: pytest.MonkeyPatch):
    client = FakeLogClient()
    context = install_fake_batch(monkeypatch, client)

    with server.app.test_request_context(
        "/api/logs/list",
        method="POST",
        json={
            "base_url": "https://na.example.com/",
            "access_token": "test-token",
            "user_id": 1,
            "page": 2,
            "page_size": 500,
            "log_type": 2,
            "start_timestamp": 100,
            "end_timestamp": 200,
            "username": "admin",
            "token_name": "prod-token",
            "model_name": "deepseek-v4-pro",
            "group": "prod",
            "channel": 23,
        },
    ):
        response = server.logs_list()

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["success"] is True
    assert len(payload["items"]) == 100
    assert payload["items"][0]["id"] == 101
    assert payload["total"] == 257
    assert payload["page"] == 2
    assert payload["page_size"] == 100
    assert payload["is_admin"] is True
    assert context["client"] is client
    assert context["auth"]["access_token"] == "test-token"
    assert client.calls == [
        {
            "page": 2,
            "page_size": 100,
            "admin": True,
            "log_type": 2,
            "start_timestamp": 100,
            "end_timestamp": 200,
            "username": "admin",
            "token_name": "prod-token",
            "model_name": "deepseek-v4-pro",
            "group": "prod",
            "channel": 23,
        }
    ]


@pytest.mark.parametrize("page", [0, -1, "invalid"])
def test_logs_list_rejects_invalid_page(monkeypatch: pytest.MonkeyPatch, page):
    client = FakeLogClient()
    install_fake_batch(monkeypatch, client)

    with server.app.test_request_context(
        "/api/logs/list",
        method="POST",
        json={
            "base_url": "https://na.example.com",
            "access_token": "test-token",
            "user_id": 1,
            "page": page,
        },
    ):
        response, status = server.logs_list()

    assert status == 400
    assert response.get_json()["success"] is False
    assert client.calls == []


def test_logs_list_uses_self_scope_for_non_admin(monkeypatch: pytest.MonkeyPatch):
    client = FakeLogClient(admin=False, total=1)
    install_fake_batch(monkeypatch, client)

    with server.app.test_request_context(
        "/api/logs/list",
        method="POST",
        json={
            "base_url": "https://na.example.com",
            "access_token": "test-token",
            "user_id": 1,
        },
    ):
        response = server.logs_list()

    assert response.status_code == 200
    assert response.get_json()["is_admin"] is False
    assert client.calls[0]["admin"] is False
    assert len(response.get_json()["items"]) == 1


def test_logs_list_returns_upstream_error(monkeypatch: pytest.MonkeyPatch):
    client = FakeLogClient()
    install_fake_batch(monkeypatch, client)

    def fail_list_logs(**kwargs):
        raise RuntimeError("gateway unavailable")

    client.list_logs = fail_list_logs
    with server.app.test_request_context(
        "/api/logs/list",
        method="POST",
        json={
            "base_url": "https://na.example.com",
            "access_token": "test-token",
            "user_id": 1,
        },
    ):
        response, status = server.logs_list()

    assert status == 400
    assert response.get_json() == {"success": False, "message": "gateway unavailable"}
