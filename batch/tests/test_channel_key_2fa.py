"""渠道密钥二次验证采集。"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

BATCH_DIR = Path(__file__).resolve().parents[1]
if str(BATCH_DIR) not in sys.path:
    sys.path.insert(0, str(BATCH_DIR))

from lib.api_client import SecureVerificationError  # noqa: E402
from lib.data_summary import (  # noqa: E402
    CHANNEL_HEADERS_WITH_KEY,
    channel_to_row,
    _fetch_channel_keys,
)
from lib import rate_budget as rb  # noqa: E402


def test_channel_to_row_optional_key():
    base = {"id": 1, "name": "demo", "type": 1, "status": 1, "models": "m"}
    without = channel_to_row(base, {1: "OpenAI"})
    assert "密钥" not in without
    with_key = channel_to_row(base, {1: "OpenAI"}, api_key="ark-xxx")
    assert with_key["密钥"] == "ark-xxx"
    assert "密钥" in CHANNEL_HEADERS_WITH_KEY


def test_fetch_force_verifies():
    client = MagicMock()
    client.base_url = "https://example.test"
    client.is_root.return_value = True
    client.ensure_secure_verified.return_value = {"verified": True}
    client.fetch_channel_key.side_effect = lambda cid: f"key-{cid}"
    rb.reset_budget()

    keys, warnings, meta = _fetch_channel_keys(
        client,
        [{"id": 10}, {"id": 11}],
        otp_code="123456",
    )
    client.ensure_secure_verified.assert_called_with("123456", force=True)
    assert keys == {10: "key-10", 11: "key-11"}
    assert meta["stop_reason"] == "done"


def test_fetch_retries_once_on_secure_error():
    client = MagicMock()
    client.base_url = "https://example-retry.test"
    client.is_root.return_value = True
    client.ensure_secure_verified.return_value = {"verified": True}
    client.fetch_channel_key.side_effect = [
        SecureVerificationError("需要安全验证 [VERIFICATION_REQUIRED]"),
        "key-1",
        "key-2",
    ]
    rb.reset_budget()

    keys, warnings, meta = _fetch_channel_keys(
        client,
        [{"id": 1}, {"id": 2}],
        otp_code="654321",
    )
    assert client.ensure_secure_verified.call_count >= 2
    assert keys == {1: "key-1", 2: "key-2"}
    assert any("强制重验" in w or "重试" in w for w in warnings)


def test_fetch_keeps_going_until_all_keys():
    client = MagicMock()
    client.base_url = "https://example-full.test"
    client.is_root.return_value = True
    client.ensure_secure_verified.return_value = {"verified": True}
    client.fetch_channel_key.side_effect = lambda cid: f"k-{cid}"
    rb.reset_budget()
    rb.note_used(client.base_url, 2)
    channels = [{"id": i} for i in range(1, 40)]
    with patch("time.sleep", return_value=None):
        keys, warnings, meta = _fetch_channel_keys(client, channels, otp_code="222222")
    assert len(keys) == 39
    assert meta["stop_reason"] == "done"
    assert not warnings


def test_fetch_channel_keys_requires_root():
    client = MagicMock()
    client.base_url = "https://example.test"
    client.is_root.return_value = False
    client.role = 10
    try:
        _fetch_channel_keys(client, [{"id": 1}], otp_code="123456")
        assert False, "expected RuntimeError"
    except RuntimeError as exc:
        assert "Root" in str(exc)


def test_fetch_skips_when_already_429():
    client = MagicMock()
    client.base_url = "https://example-blocked.test"
    client.is_root.return_value = True
    rb.reset_budget()
    rb.note_rate_limited(client.base_url)
    try:
        _fetch_channel_keys(client, [{"id": 1}], otp_code="111111")
        assert False, "expected RuntimeError"
    except RuntimeError as exc:
        assert "429" in str(exc)
    client.fetch_channel_key.assert_not_called()


def test_fetch_channel_keys_stops_on_rate_limit():
    client = MagicMock()
    client.base_url = "https://example-rate.test"
    client.is_root.return_value = True
    client.ensure_secure_verified.return_value = {}
    client.fetch_channel_key.side_effect = [
        "k1",
        RuntimeError("429 Too Many Requests"),
    ]
    rb.reset_budget()
    keys, warnings, meta = _fetch_channel_keys(
        client,
        [{"id": 1}, {"id": 2}, {"id": 3}, {"id": 4}],
        otp_code="111111",
    )
    assert keys == {1: "k1"}
    assert meta["stop_reason"] == "rate_limit"


def test_fill_missing_requires_auth():
    from lib.data_summary import SiteConfig, fill_missing_channel_keys

    try:
        fill_missing_channel_keys(
            site=SiteConfig(
                base_url="https://ai-cloud-test.example.com",
                username="root",
                password="",
                env="test",
                otp_code="123456",
            ),
            root_dir=BATCH_DIR.parent,
        )
        assert False, "expected ValueError"
    except ValueError as exc:
        assert "密码" in str(exc) or "Access Token" in str(exc)


def test_fill_missing_bootstraps_empty_env_into_existing_workbook():
    import tempfile

    from lib.data_summary import (
        DUP_CHANNEL_HEADERS_WITH_KEY,
        SiteConfig,
        _read_channel_sheet_with_keys,
        fill_missing_channel_keys,
    )
    from lib.data_summary_exporter import save_workbook_data

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        excel_dir = root / "excel"
        excel_dir.mkdir()
        path = excel_dir / "ai网关令牌及渠道列表_20260824110000.xlsx"
        save_workbook_data(
            path,
            channel_env_rows={
                "test": [{"名称": "t-ch", "分组": "g", "密钥": "k-test"}],
                "uat": [{"名称": "u-ch", "分组": "g", "密钥": "k-uat"}],
                "prod": [],
            },
            token_env_rows={
                "test": [{"名称": "t-tk", "分组": "g"}],
                "uat": [{"名称": "u-tk", "分组": "g"}],
                "prod": [],
            },
            channel_headers=CHANNEL_HEADERS_WITH_KEY,
            dup_channel_headers=DUP_CHANNEL_HEADERS_WITH_KEY,
        )
        site = SiteConfig(
            base_url="https://ai-cloud-prod.example.com",
            username="admin",
            password="secret",
            env="prod",
            otp_code="123456",
        )
        channels = [{"名称": "p-ch", "分组": "g", "密钥": "k-prod", "_sort_id": 9}]
        tokens = [{"名称": "p-tk", "分组": "g", "_sort_id": 3}]
        with patch(
            "lib.data_summary.fetch_site_data",
            return_value=(
                "prod",
                channels,
                tokens,
                {"keys_fetched": 1, "keys_pending": 0, "key_warnings": []},
            ),
        ):
            result, saved = fill_missing_channel_keys(site=site, root_dir=root)
        assert saved == path
        assert result.get("bootstrapped") is True
        assert "工作表原为空" in result["message"]
        _, prod_rows = _read_channel_sheet_with_keys(path, "prod")
        assert [r["名称"] for r in prod_rows] == ["p-ch"]
        assert prod_rows[0]["密钥"] == "k-prod"
        _, test_rows = _read_channel_sheet_with_keys(path, "test")
        assert test_rows[0]["密钥"] == "k-test"


if __name__ == "__main__":
    test_channel_to_row_optional_key()
    test_fetch_force_verifies()
    test_fetch_retries_once_on_secure_error()
    test_fetch_keeps_going_until_all_keys()
    test_fetch_channel_keys_requires_root()
    test_fetch_skips_when_already_429()
    test_fetch_channel_keys_stops_on_rate_limit()
    test_fill_missing_requires_auth()
    test_fill_missing_bootstraps_empty_env_into_existing_workbook()
    print("ok")
