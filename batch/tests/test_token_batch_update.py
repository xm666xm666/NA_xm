"""令牌额度预更新 / 确认更新。"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

BATCH_DIR = Path(__file__).resolve().parents[1]
if str(BATCH_DIR) not in sys.path:
    sys.path.insert(0, str(BATCH_DIR))

from lib.token_batch_update import (  # noqa: E402
    parse_token_quota_update_rows,
    run_token_batch_quota_update,
)
from lib.api_client import NewAPIClient  # noqa: E402


def _existing_token() -> dict:
    return {
        "id": 8,
        "name": "legacy-token",
        "group": "g1",
        "status": 2,
        "remain_quota": 0,
        "unlimited_quota": True,
        "expired_time": -1,
        "cross_group_retry": False,
        "allow_ips": "10.0.0.1",
        "token_model_limit_enabled": True,
        "token_model_limit": "m1,m2",
        "token_model_rate_limits": [{"model_name": "m1", "rpm": 2}],
    }


def test_parse_full_and_compact_quota_rows():
    rows = parse_token_quota_update_rows(
        "legacy-token\tg1\tm1,m2\t500000\n"
        "compact-token g2 1000000\n"
    )
    assert rows == [
        {"名称": "legacy-token", "分组": "g1", "额度(tokens)": "500000"},
        {"名称": "compact-token", "分组": "g2", "额度(tokens)": "1000000"},
    ]


def test_parse_requires_explicit_quota():
    try:
        parse_token_quota_update_rows("legacy-token g1 m1,m2")
    except ValueError as exc:
        assert "缺少额度(tokens)" in str(exc)
    else:
        raise AssertionError("更新额度时应拒绝未填写额度的行")


def test_quota_update_preview_and_confirm_preserve_token_settings():
    existing = _existing_token()
    client = MagicMock()
    client.list_all_tokens.return_value = [existing]
    client.get_token.return_value = existing

    with patch("lib.token_batch_update.NewAPIClient", return_value=client), patch(
        "lib.token_batch_update.authenticate_client"
    ):
        preview = run_token_batch_quota_update(
            base_url="http://example.com",
            batch_text="legacy-token g1 m1,m2 500000",
            auth={"username": "a", "password": "b"},
            dry_run=True,
        )
        assert preview.matched_count == 1
        assert preview.updated_count == 0
        client.update_token.assert_not_called()

        done = run_token_batch_quota_update(
            base_url="http://example.com",
            batch_text="legacy-token g1 m1,m2 500000",
            auth={"username": "a", "password": "b"},
            dry_run=False,
        )

    assert done.updated_count == 1
    sent = client.update_token.call_args.args[0]
    kwargs = client.update_token.call_args.kwargs
    assert sent["id"] == 8
    assert sent["remain_quota"] == 500000
    assert sent["unlimited_quota"] is False
    assert sent["name"] == "legacy-token"
    assert sent["group"] == "g1"
    assert sent["expired_time"] == -1
    assert sent["allow_ips"] == "10.0.0.1"
    assert sent["token_model_limit"] == "m1,m2"
    assert sent["token_model_rate_limits"] == [{"model_name": "m1", "rpm": 2}]
    assert kwargs == {"preserve_token_model_rate_limits": True}


def test_quota_update_skips_same_value_and_missing_token():
    existing = _existing_token()
    existing.update({"remain_quota": 500000, "unlimited_quota": False})
    client = MagicMock()
    client.list_all_tokens.return_value = [existing]

    with patch("lib.token_batch_update.NewAPIClient", return_value=client), patch(
        "lib.token_batch_update.authenticate_client"
    ):
        result = run_token_batch_quota_update(
            base_url="http://example.com",
            batch_text="legacy-token g1 500000\nmissing g1 900000",
            auth={},
            dry_run=True,
        )

    assert result.matched_count == 0
    assert result.skipped_count == 2


def test_api_client_keeps_model_rate_limits_for_quota_update():
    client = NewAPIClient("http://example.com")
    response = MagicMock()
    response.json.return_value = {"success": True, "data": {}}
    client.session.put = MagicMock(return_value=response)

    client.update_token(
        {
            "id": 8,
            "name": "legacy-token",
            "token_model_limit": "m1",
            "token_model_rate_limits": [{"model_name": "m1", "rpm": 2}],
        },
        preserve_token_model_rate_limits=True,
    )

    sent = client.session.put.call_args.kwargs["json"]
    assert sent["token_model_rate_limits"] == [{"model_name": "m1", "rpm": 2}]


if __name__ == "__main__":
    test_parse_full_and_compact_quota_rows()
    test_parse_requires_explicit_quota()
    test_quota_update_preview_and_confirm_preserve_token_settings()
    test_quota_update_skips_same_value_and_missing_token()
    test_api_client_keeps_model_rate_limits_for_quota_update()
    print("ok")
