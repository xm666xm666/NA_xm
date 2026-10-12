"""按名称+分组批量启停令牌。"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

BATCH_DIR = Path(__file__).resolve().parents[1]
if str(BATCH_DIR) not in sys.path:
    sys.path.insert(0, str(BATCH_DIR))

from lib.token_batch_delete import parse_token_name_group_rows  # noqa: E402
from lib.token_batch_status import (  # noqa: E402
    TOKEN_STATUS_DISABLED,
    TOKEN_STATUS_ENABLED,
    run_token_batch_status,
)


def test_parse_token_name_group_two_and_three_columns():
    rows = parse_token_name_group_rows(
        "foo-bar g1\n"
        "tok\tg2\tmodel-a、model-b\n"
        "# comment\n"
        "名称 分组 模型限制\n"
    )
    assert rows == [
        {"名称": "foo-bar", "分组": "g1"},
        {"名称": "tok", "分组": "g2"},
    ]


def test_run_token_status_skips_already_disabled_and_updates():
    tokens = [
        {"id": 5, "name": "a-金鑫", "group": "g1", "status": 1},
        {"id": 6, "name": "b-崔林", "group": "g2", "status": 2},
    ]
    client = MagicMock()
    client.list_all_tokens.return_value = tokens
    client.update_token_status = MagicMock()

    with patch("lib.token_batch_status.NewAPIClient", return_value=client), patch(
        "lib.token_batch_status.authenticate_client"
    ):
        result = run_token_batch_status(
            base_url="http://example.com",
            batch_text="a-金鑫 g1\nb-崔林 g2\nmissing x\n",
            auth={"username": "a", "password": "b"},
            action="disable",
            dry_run=False,
        )

    assert result.matched_count == 2
    assert result.updated_count == 1
    assert result.skipped_count == 2  # already disabled + missing
    client.update_token_status.assert_called_once_with(5, TOKEN_STATUS_DISABLED)


def test_run_token_status_enable_dry_run():
    tokens = [{"id": 9, "name": "t", "group": "g", "status": 2}]
    client = MagicMock()
    client.list_all_tokens.return_value = tokens
    client.update_token_status = MagicMock()

    with patch("lib.token_batch_status.NewAPIClient", return_value=client), patch(
        "lib.token_batch_status.authenticate_client"
    ):
        result = run_token_batch_status(
            base_url="http://example.com",
            batch_text="t g",
            auth={"username": "a", "password": "b"},
            action="enable",
            dry_run=True,
        )

    assert result.matched_count == 1
    assert result.items[0]["target_status"] == TOKEN_STATUS_ENABLED
    client.update_token_status.assert_not_called()


if __name__ == "__main__":
    test_parse_token_name_group_two_and_three_columns()
    test_run_token_status_skips_already_disabled_and_updates()
    test_run_token_status_enable_dry_run()
    print("ok")
