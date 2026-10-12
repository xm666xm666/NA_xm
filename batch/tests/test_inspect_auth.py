"""数据汇总：采集前审查各站是否需要登录验证码。"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

BATCH_DIR = Path(__file__).resolve().parents[1]
if str(BATCH_DIR) not in sys.path:
    sys.path.insert(0, str(BATCH_DIR))

from lib.data_summary import (  # noqa: E402
    SiteConfig,
    _classify_login_probe_error,
    inspect_site_auth,
    inspect_summary_sites_auth,
    login_site_auth,
)


def test_classify_setup_before_need_otp():
    assert (
        _classify_login_probe_error(
            RuntimeError("该账号尚未绑定登录两步验证，请先在 NA 控制台完成 MFA 绑定后再采集。")
        )
        == "setup"
    )


def test_classify_need_otp_and_rate_limit():
    assert (
        _classify_login_probe_error(
            RuntimeError("账号启用了登录两步验证，请填写认证器当前 6 位验证码")
        )
        == "need_otp"
    )
    assert _classify_login_probe_error(RuntimeError("429 Too Many Requests")) == "rate_limited"
    assert _classify_login_probe_error(RuntimeError("本站 CriticalRateLimit 配额不足")) == "rate_limited"
    assert _classify_login_probe_error(RuntimeError("用户名或密码错误")) == "error"


def test_inspect_missing_credentials():
    row = inspect_site_auth(SiteConfig(base_url="https://na-test.example.com", env="test"))
    assert row["status"] == "error"
    assert row["collectable"] is False
    assert row["needs_otp_prompt"] is False
    assert "用户名" in row["message"] or "Access Token" in row["message"]


@patch("lib.data_summary.authenticate_client")
@patch("lib.data_summary.NewAPIClient")
def test_inspect_ready_without_otp(mock_client, mock_auth):
    mock_auth.return_value = None
    site = SiteConfig(
        base_url="https://na-test.example.com",
        username="admin",
        password="x",
        env="test",
    )
    row = inspect_site_auth(site)
    assert row["status"] == "ready"
    assert row["collectable"] is True
    assert row["needs_login_otp"] is False
    assert row["needs_otp_prompt"] is False
    mock_auth.assert_called_once()
    auth = mock_auth.call_args[0][1]
    assert auth.get("otp_code") == ""


@patch("lib.data_summary.authenticate_client")
@patch("lib.data_summary.NewAPIClient")
def test_inspect_need_login_otp(mock_client, mock_auth):
    mock_auth.side_effect = RuntimeError("账号启用了登录两步验证，请填写认证器当前 6 位验证码")
    site = SiteConfig(
        base_url="https://na-uat.example.com",
        username="admin",
        password="x",
        env="uat",
    )
    row = inspect_site_auth(site)
    assert row["status"] == "need_otp"
    assert row["collectable"] is True
    assert row["needs_login_otp"] is True
    assert row["needs_otp_prompt"] is True


@patch("lib.data_summary.authenticate_client")
@patch("lib.data_summary.NewAPIClient")
def test_inspect_include_keys_still_needs_verify(mock_client, mock_auth):
    mock_auth.return_value = None
    site = SiteConfig(
        base_url="https://na-prod.example.com",
        username="admin",
        password="x",
        env="prod",
    )
    items = inspect_summary_sites_auth([site], include_keys=True)
    assert items[0]["status"] == "ready"
    assert items[0]["needs_verify_otp"] is True
    assert items[0]["needs_otp_prompt"] is True
    assert "密钥" in items[0]["message"]


@patch("lib.data_summary.authenticate_client")
@patch("lib.data_summary.NewAPIClient")
def test_inspect_include_keys_totp_skips_prompt(mock_client, mock_auth):
    mock_auth.return_value = None
    site = SiteConfig(
        base_url="https://na-prod.example.com",
        username="admin",
        password="x",
        env="prod",
        totp_secret="AAAAAAAAAAAAAAAA",
    )
    items = inspect_summary_sites_auth([site], include_keys=True)
    assert items[0]["needs_verify_otp"] is True
    assert items[0]["needs_otp_prompt"] is False
    assert items[0]["has_totp_secret"] is True


@patch("lib.data_summary.authenticate_client")
@patch("lib.data_summary.NewAPIClient")
def test_login_site_auth_sends_otp(mock_client, mock_auth):
    mock_auth.return_value = None
    site = SiteConfig(
        base_url="https://na-prod.example.com",
        username="admin",
        password="x",
        env="prod",
        otp_code="654321",
    )
    row = login_site_auth(site)
    assert row["status"] == "ready"
    assert row["session_ready"] is True
    auth = mock_auth.call_args[0][1]
    assert auth.get("otp_code") == "654321"


if __name__ == "__main__":
    test_classify_setup_before_need_otp()
    test_classify_need_otp_and_rate_limit()
    test_inspect_missing_credentials()
    test_inspect_ready_without_otp()
    test_inspect_need_login_otp()
    test_inspect_include_keys_still_needs_verify()
    test_inspect_include_keys_totp_skips_prompt()
    test_login_site_auth_sends_otp()
    print("ok")
