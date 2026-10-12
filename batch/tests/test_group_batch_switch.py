"""分组切换：渠道多分组替换与令牌单分组替换。"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

BATCH_DIR = Path(__file__).resolve().parents[1]
if str(BATCH_DIR) not in sys.path:
    sys.path.insert(0, str(BATCH_DIR))

from lib.group_batch_switch import (  # noqa: E402
    channel_in_group,
    list_group_members,
    rewrite_channel_groups,
    run_group_switch,
    token_in_group,
)


def test_rewrite_channel_groups_replaces_and_dedupes():
    assert rewrite_channel_groups("alpha,beta", "alpha", "gamma") == "gamma,beta"
    assert rewrite_channel_groups("alpha,beta", "alpha", "beta") == "beta"
    assert rewrite_channel_groups("alpha", "alpha", "gamma") == "gamma"
    assert rewrite_channel_groups("beta", "alpha", "gamma") == "beta"


def test_membership_helpers():
    assert channel_in_group({"group": "a,b"}, "b")
    assert not channel_in_group({"group": "a,b"}, "c")
    assert token_in_group({"group": "uat"}, "uat")
    assert not token_in_group({"group": "uat"}, "test")


def _client_with(groups, channels, tokens):
    client = MagicMock()
    client.list_groups.return_value = list(groups)
    client.list_all_channels.return_value = list(channels)
    client.list_all_tokens.return_value = list(tokens)
    client.get_token.side_effect = lambda tid: next(
        tok for tok in tokens if int(tok["id"]) == int(tid)
    )
    return client


@patch("lib.group_batch_switch.authenticate_client")
@patch("lib.group_batch_switch.NewAPIClient")
def test_list_group_members(mock_client_cls, _auth):
    client = _client_with(
        ["g1", "g2"],
        [
            {"id": 2, "name": "ch-g1", "group": "g1", "status": 1},
            {"id": 1, "name": "ch-both", "group": "g1,g2", "status": 1},
            {"id": 9, "name": "ch-g2", "group": "g2", "status": 1},
        ],
        [
            {"id": 5, "name": "tok-g1", "group": "g1", "status": 1},
            {"id": 6, "name": "tok-g2", "group": "g2", "status": 1},
        ],
    )
    mock_client_cls.return_value = client
    data = list_group_members(
        base_url="https://na.example.com",
        auth={"username": "a", "password": "b"},
        source_group="g1",
    )
    assert [row["name"] for row in data["channels"]] == ["ch-both", "ch-g1"]
    assert [row["name"] for row in data["tokens"]] == ["tok-g1"]
    assert data["channel_count"] == 2
    assert data["token_count"] == 1


@patch("lib.group_batch_switch.authenticate_client")
@patch("lib.group_batch_switch.NewAPIClient")
def test_switch_channels_selected_ids(mock_client_cls, _auth):
    client = _client_with(
        ["g1", "g2"],
        [
            {"id": 1, "name": "keep", "group": "g1", "status": 1, "models": "m"},
            {"id": 2, "name": "move", "group": "g1", "status": 1, "models": "m"},
        ],
        [],
    )
    mock_client_cls.return_value = client
    result = run_group_switch(
        base_url="https://na.example.com",
        auth={"username": "a", "password": "b"},
        source_group="g1",
        target_group="g2",
        kind="channel",
        ids=[2],
        dry_run=False,
    )
    assert result.updated_count == 1
    assert result.failed_count == 0
    client.update_channel.assert_called_once()
    sent = client.update_channel.call_args[0][0]
    assert sent["id"] == 2
    assert sent["group"] == "g2"
    assert "key" not in sent


@patch("lib.group_batch_switch.authenticate_client")
@patch("lib.group_batch_switch.NewAPIClient")
def test_switch_tokens_keeps_other_fields(mock_client_cls, _auth):
    tokens = [
        {
            "id": 8,
            "name": "tok",
            "group": "g1",
            "status": 1,
            "remain_quota": 100,
            "expired_time": -1,
            "unlimited_quota": False,
            "model_limits_enabled": True,
            "model_limits": "m1,m2",
        }
    ]
    client = _client_with(["g1", "g2"], [], tokens)
    mock_client_cls.return_value = client
    result = run_group_switch(
        base_url="https://na.example.com",
        auth={"username": "a", "password": "b"},
        source_group="g1",
        target_group="g2",
        kind="token",
        ids=[8],
        dry_run=False,
    )
    assert result.updated_count == 1
    client.update_token.assert_called_once()
    sent = client.update_token.call_args[0][0]
    assert sent["group"] == "g2"
    assert sent["name"] == "tok"
    assert sent["remain_quota"] == 100
    assert sent["model_limits"] == "m1,m2"


@patch("lib.group_batch_switch.authenticate_client")
@patch("lib.group_batch_switch.NewAPIClient")
def test_switch_same_group_rejected(mock_client_cls, _auth):
    try:
        run_group_switch(
            base_url="https://na.example.com",
            auth={"username": "a", "password": "b"},
            source_group="g1",
            target_group="g1",
            kind="channel",
            ids=[1],
        )
        assert False, "expected ValueError"
    except ValueError as exc:
        assert "不能相同" in str(exc)
    mock_client_cls.assert_not_called()


if __name__ == "__main__":
    test_rewrite_channel_groups_replaces_and_dedupes()
    test_membership_helpers()
    test_list_group_members()
    test_switch_channels_selected_ids()
    test_switch_tokens_keeps_other_fields()
    test_switch_same_group_rejected()
    print("ok")
