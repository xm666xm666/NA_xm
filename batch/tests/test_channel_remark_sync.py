"""渠道 Base URL 同步备注测试。"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

BATCH_DIR = Path(__file__).resolve().parents[1]
if str(BATCH_DIR) not in sys.path:
    sys.path.insert(0, str(BATCH_DIR))

from lib.channel_remark_sync import (  # noqa: E402
    MAX_CHANNEL_REMARK_LENGTH,
    append_remark_url,
    remark_source_label,
    run_channel_remark_sync,
)


def test_append_remark_url_keeps_existing_content_and_is_idempotent():
    assert append_remark_url("已有说明", "https://api.example.com") == (
        "已有说明\nhttps://api.example.com",
        True,
    )
    assert append_remark_url("已有说明\nhttps://api.example.com", "https://api.example.com") == (
        "已有说明\nhttps://api.example.com",
        False,
    )


def test_azure_uses_endpoint_label():
    assert remark_source_label({"type": 3}) == "AZURE_OPENAI_ENDPOINT"
    assert remark_source_label({"type": 45}) == "base_url"


def test_preview_reports_missing_url_and_oversized_remark():
    client = MagicMock()
    client.get_status.return_value = {}
    client.list_all_channels.return_value = [
        {"id": 1, "name": "normal", "group": "g1", "type": 45, "base_url": "https://a.example.com"},
        {"id": 2, "name": "azure", "group": "g1", "type": 3, "base_url": "https://az.example.com", "remark": "已有"},
        {"id": 3, "name": "empty-url", "group": "g1", "type": 45, "base_url": ""},
        {"id": 4, "name": "too-long", "group": "g1", "type": 45, "base_url": "https://long.example.com", "remark": "x" * MAX_CHANNEL_REMARK_LENGTH},
    ]

    import lib.channel_remark_sync as mod

    original_client = mod.NewAPIClient
    original_auth = mod.authenticate_client
    mod.NewAPIClient = lambda *args, **kwargs: client
    mod.authenticate_client = lambda *args, **kwargs: None
    try:
        result = run_channel_remark_sync(
            base_url="https://na.example.com",
            auth={"username": "admin", "password": "secret"},
            dry_run=True,
        )
    finally:
        mod.NewAPIClient = original_client
        mod.authenticate_client = original_auth

    assert result.total == 4
    assert result.matched_count == 2
    assert result.failed_count == 2
    assert "AZURE_OPENAI_ENDPOINT" in result.items[1]["message"]
    assert "empty-url" in result.items[2]["message"]
    assert "too-long" in result.items[3]["message"]
    assert "超过 255 字符上限" in result.items[3]["message"]
    client.update_channel.assert_not_called()


def test_confirm_only_submits_remark_field_and_preserves_failures():
    client = MagicMock()
    client.get_status.return_value = {}
    client.list_all_channels.return_value = [
        {"id": 8, "name": "normal", "group": "g1", "type": 45, "base_url": "https://api.example.com", "remark": "已存在内容"},
        {"id": 9, "name": "missing", "group": "g1", "type": 45, "base_url": ""},
    ]
    client.update_channel.return_value = {"success": True}

    import lib.channel_remark_sync as mod

    original_client = mod.NewAPIClient
    original_auth = mod.authenticate_client
    mod.NewAPIClient = lambda *args, **kwargs: client
    mod.authenticate_client = lambda *args, **kwargs: None
    try:
        result = run_channel_remark_sync(
            base_url="https://na.example.com",
            auth={"username": "admin", "password": "secret"},
            dry_run=False,
        )
    finally:
        mod.NewAPIClient = original_client
        mod.authenticate_client = original_auth

    assert result.updated_count == 1
    assert result.failed_count == 1
    client.update_channel.assert_called_once_with(
        {"id": 8, "remark": "已存在内容\nhttps://api.example.com"}
    )


if __name__ == "__main__":
    test_append_remark_url_keeps_existing_content_and_is_idempotent()
    test_azure_uses_endpoint_label()
    test_preview_reports_missing_url_and_oversized_remark()
    test_confirm_only_submits_remark_field_and_preserves_failures()
    print("ok")
