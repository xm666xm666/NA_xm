from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import app as app_module


SECRET_VALUES = (
    "server-password-secret",
    "server-token-secret",
    "server-default-key-secret",
    "server-llm-key-secret",
    "server-totp-secret",
)


def _assert_no_secrets(response) -> dict:
    text = response.get_data(as_text=True)
    for secret in SECRET_VALUES:
        assert secret not in text
    return json.loads(text)


def test_batch_config_returns_only_public_preferences():
    private = {
        "base_url": "https://na.example.com",
        "username": "admin",
        "password": "server-password-secret",
        "access_token": "server-token-secret",
        "default_key": "server-default-key-secret",
        "user_id": 1,
    }
    with patch.object(app_module, "_load_batch_config", return_value=private):
        with app_module.app.test_request_context("/api/batch-config"):
            payload = _assert_no_secrets(app_module.batch_config())
    data = payload["data"]
    assert data["has_password"] is True
    assert data["has_access_token"] is True
    assert data["has_default_key"] is True
    assert "password" not in data
    assert "access_token" not in data
    assert "default_key" not in data


def test_env_sites_returns_only_public_site_metadata():
    private = {
        "configured": True,
        "available": ["test"],
        "sites": {
            "test": {
                "base_url": "https://na-test.example.com",
                "username": "admin",
                "password": "server-password-secret",
                "access_token": "server-token-secret",
                "default_key": "server-default-key-secret",
                "totp_secret": "server-totp-secret",
                "auth_mode": "password",
            }
        },
    }
    with patch.object(app_module, "_load_env_sites", return_value=private):
        with app_module.app.test_request_context("/api/env-sites"):
            payload = _assert_no_secrets(app_module.api_env_sites())
    site = payload["sites"]["test"]
    assert site["has_password"] is True
    assert site["has_access_token"] is True
    assert site["has_default_key"] is True
    assert site["has_totp_secret"] is True
    assert set(site).isdisjoint({"password", "access_token", "default_key", "totp_secret"})


def test_llm_presets_do_not_return_server_api_key():
    private = {
        "api_base": "https://llm.example.com/v1",
        "api_key": "server-llm-key-secret",
        "model": "test-model",
        "provider": "openai",
        "timeout": 60,
    }
    fake_module = SimpleNamespace(list_provider_presets=lambda: [])
    with (
        patch.object(app_module, "_load_llm_config", return_value=private),
        patch.object(app_module.importlib, "import_module", return_value=fake_module),
        patch.object(app_module, "_pin_lib_root", lambda _root: None),
    ):
        with app_module.app.test_request_context("/api/llm-presets"):
            payload = _assert_no_secrets(app_module.llm_presets())
    assert payload["data"]["defaults"]["has_api_key"] is True
    assert "api_key" not in payload["data"]["defaults"]


def _auth_batch(enrich=None):
    return {
        "normalize_na_base_url": lambda value: str(value or "").strip().rstrip("/"),
        "coerce_verify_ssl": lambda value, default: default if value is None else bool(value),
        "enrich_auth_from_env": enrich or (lambda auth, **_kwargs: dict(auth)),
    }


def test_parse_auth_backfills_only_matching_batch_site_and_respects_mode():
    private = {
        "base_url": "https://na.example.com",
        "username": "admin",
        "password": "server-password-secret",
        "access_token": "server-token-secret",
        "default_key": "server-default-key-secret",
        "user_id": 12,
    }
    with (
        patch.object(app_module, "_ensure_batch", lambda: None),
        patch.object(app_module, "_load_batch_config", return_value=private),
        patch.object(app_module, "BATCH", _auth_batch()),
    ):
        password_auth = app_module._parse_auth({"base_url": private["base_url"], "auth_mode": "password"})
        assert password_auth["password"] == "server-password-secret"
        assert not password_auth.get("access_token")
        assert password_auth["default_key"] == "server-default-key-secret"

        token_auth = app_module._parse_auth({"base_url": private["base_url"], "auth_mode": "token"})
        assert token_auth["access_token"] == "server-token-secret"
        assert token_auth["user_id"] == 12
        assert "password" not in token_auth

        custom_auth = app_module._parse_auth({"base_url": "https://other.example.com", "auth_mode": "password"})
        assert custom_auth["password"] == ""
        assert custom_auth["default_key"] == ""


def test_custom_llm_and_agent_endpoints_never_inherit_unrelated_server_keys():
    llm_config = {"api_base": "https://llm.example.com/v1", "api_key": "server-llm-key-secret"}
    with patch.object(app_module, "_load_llm_config", return_value=llm_config):
        same = app_module._merge_llm_config({"llm_api_base": "https://llm.example.com/v1/"})
        custom = app_module._merge_llm_config({"llm_api_base": "https://other-llm.example.com/v1"})
    assert same["api_key"] == "server-llm-key-secret"
    assert custom["api_key"] == ""

    batch_config = {
        "base_url": "https://na.example.com",
        "username": "admin",
        "password": "server-password-secret",
        "access_token": "server-token-secret",
        "default_key": "server-default-key-secret",
    }
    with (
        patch.object(app_module, "_ensure_batch", lambda: None),
        patch.object(app_module, "_load_batch_config", return_value=batch_config),
        patch.object(app_module, "BATCH", _auth_batch()),
    ):
        same = app_module._merge_agent_connection({"base_url": "https://na.example.com", "auth_mode": "password"})
        custom = app_module._merge_agent_connection({"base_url": "https://other.example.com", "auth_mode": "password"})
    assert same["password"] == "server-password-secret"
    assert same["access_token"] == ""
    assert custom["password"] == ""
    assert custom["access_token"] == ""
    assert custom["default_key"] == ""
