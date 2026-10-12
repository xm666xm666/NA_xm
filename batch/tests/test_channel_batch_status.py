"""按上游模型 / 类型 / ID 批量启停渠道。"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

BATCH_DIR = Path(__file__).resolve().parents[1]
if str(BATCH_DIR) not in sys.path:
    sys.path.insert(0, str(BATCH_DIR))

from lib.channel_batch_status import (  # noqa: E402
    CHANNEL_STATUS_ENABLED,
    CHANNEL_STATUS_MANUALLY_DISABLED,
    extract_upstream_models,
    parse_model_list,
    run_channel_batch_status,
)


def test_parse_model_list_dedupe_and_split():
    text = "glm-5.1\n# comment\nglm-5.2, glm-5.1  ep-1"
    assert parse_model_list(text) == ["glm-5.1", "glm-5.2", "ep-1"]


def test_extract_upstream_models_from_mapping():
    channel = {
        "model_mapping": '{"pv-agent-uat-glm-5.1":"glm-5.1","other":"ep-1"}',
    }
    assert extract_upstream_models(channel) == {"glm-5.1", "ep-1"}


def test_extract_upstream_models_ignores_models_field():
    channel = {
        "models": "glm-5.1,foo",
        "model_mapping": "",
    }
    assert extract_upstream_models(channel) == set()


def test_run_dry_run_matches_by_upstream_and_type():
    channels = [
        {
            "id": 11,
            "name": "pv-agent-uat-glm-5.1",
            "group": "pv-agent-uat",
            "type": 8,
            "status": 1,
            "model_mapping": '{"pv-agent-uat-glm-5.1":"glm-5.1"}',
        },
        {
            "id": 12,
            "name": "other-openai",
            "group": "g",
            "type": 1,
            "status": 1,
            "model_mapping": '{"m":"glm-5.1"}',
        },
        {
            "id": 13,
            "name": "custom-other",
            "group": "g2",
            "type": 8,
            "status": 1,
            "model_mapping": '{"m":"glm-5.2"}',
        },
    ]
    client = MagicMock()
    client.list_all_channels.return_value = channels
    client.update_channel_status = MagicMock()

    with patch("lib.channel_batch_status.NewAPIClient", return_value=client), patch(
        "lib.channel_batch_status.authenticate_client"
    ), patch(
        "lib.channel_batch_status.get_channel_types",
        return_value=([{"value": 8, "label": "自定义渠道"}, {"value": 1, "label": "OpenAI"}], "bundled"),
    ):
        result = run_channel_batch_status(
            base_url="http://example.com",
            auth={"username": "a", "password": "b"},
            model_text="glm-5.1",
            channel_type="自定义渠道",
            action="disable",
            dry_run=True,
            match_mode="upstream",
        )

    assert result.matched_count == 1
    assert result.items[0]["target_id"] == 11
    assert result.items[0]["matched_upstreams"] == ["glm-5.1"]
    client.update_channel_status.assert_not_called()


def test_run_type_mode_matches_all_of_type():
    channels = [
        {
            "id": 1,
            "name": "a",
            "group": "g",
            "type": 8,
            "status": 1,
            "model_mapping": '{"a":"glm-5.1"}',
        },
        {
            "id": 2,
            "name": "b",
            "group": "g",
            "type": 8,
            "status": 2,
            "model_mapping": "",
        },
        {
            "id": 3,
            "name": "c",
            "group": "g",
            "type": 1,
            "status": 1,
            "model_mapping": '{"c":"x"}',
        },
    ]
    client = MagicMock()
    client.list_all_channels.return_value = channels

    with patch("lib.channel_batch_status.NewAPIClient", return_value=client), patch(
        "lib.channel_batch_status.authenticate_client"
    ), patch(
        "lib.channel_batch_status.get_channel_types",
        return_value=([{"value": 8, "label": "自定义渠道"}], "bundled"),
    ):
        result = run_channel_batch_status(
            base_url="http://example.com",
            auth={"username": "a", "password": "b"},
            channel_type="自定义渠道",
            action="disable",
            dry_run=True,
            match_mode="type",
        )

    assert result.matched_count == 2
    assert {item["target_id"] for item in result.items} == {1, 2}
    assert result.skipped_count == 1  # id=2 already disabled


def test_run_ids_mode_updates_selected():
    channels = [
        {
            "id": 21,
            "name": "a",
            "group": "g",
            "type": 8,
            "status": CHANNEL_STATUS_ENABLED,
            "model_mapping": '{"a":"glm-5.1"}',
        },
        {
            "id": 22,
            "name": "b",
            "group": "g",
            "type": 8,
            "status": CHANNEL_STATUS_ENABLED,
            "model_mapping": '{"b":"glm-5.1"}',
        },
    ]
    client = MagicMock()
    client.list_all_channels.return_value = channels

    with patch("lib.channel_batch_status.NewAPIClient", return_value=client), patch(
        "lib.channel_batch_status.authenticate_client"
    ), patch(
        "lib.channel_batch_status.get_channel_types",
        return_value=([{"value": 8, "label": "自定义渠道"}], "bundled"),
    ):
        result = run_channel_batch_status(
            base_url="http://example.com",
            auth={"username": "a", "password": "b"},
            channel_type="自定义渠道",
            action="disable",
            dry_run=False,
            match_mode="ids",
            channel_ids=[21],
        )

    assert result.matched_count == 1
    assert result.updated_count == 1
    client.update_channel_status.assert_called_once_with(21, CHANNEL_STATUS_MANUALLY_DISABLED)


def test_run_confirm_skips_already_target_and_updates_others():
    channels = [
        {
            "id": 21,
            "name": "a",
            "group": "g",
            "type": 8,
            "status": CHANNEL_STATUS_MANUALLY_DISABLED,
            "model_mapping": '{"a":"glm-5.1"}',
        },
        {
            "id": 22,
            "name": "b",
            "group": "g",
            "type": 8,
            "status": CHANNEL_STATUS_ENABLED,
            "model_mapping": '{"b":"glm-5.1"}',
        },
    ]
    client = MagicMock()
    client.list_all_channels.return_value = channels

    with patch("lib.channel_batch_status.NewAPIClient", return_value=client), patch(
        "lib.channel_batch_status.authenticate_client"
    ), patch(
        "lib.channel_batch_status.get_channel_types",
        return_value=([{"value": 8, "label": "自定义渠道"}], "bundled"),
    ):
        result = run_channel_batch_status(
            base_url="http://example.com",
            auth={"username": "a", "password": "b"},
            models=["glm-5.1"],
            channel_type="自定义渠道",
            action="disable",
            dry_run=False,
        )

    assert result.matched_count == 2
    assert result.skipped_count == 1
    assert result.updated_count == 1
    client.update_channel_status.assert_called_once_with(22, CHANNEL_STATUS_MANUALLY_DISABLED)


def test_run_requires_channel_type():
    try:
        run_channel_batch_status(
            base_url="http://example.com",
            auth={"username": "a", "password": "b"},
            model_text="glm-5.1",
            channel_type="",
            action="enable",
            dry_run=True,
        )
        raise AssertionError("expected ValueError")
    except ValueError as exc:
        assert "渠道类型" in str(exc)


def test_run_name_mode_disables_matched_and_skips_missing():
    channels = [
        {"id": 11, "name": "gpt-4o", "group": "azure", "type": 3, "status": 1},
        {"id": 12, "name": "ceshi", "group": "default", "type": 3, "status": 2},
    ]
    client = MagicMock()
    client.list_all_channels.return_value = channels
    client.update_channel_status = MagicMock()

    with patch("lib.channel_batch_status.NewAPIClient", return_value=client), patch(
        "lib.channel_batch_status.authenticate_client"
    ):
        preview = run_channel_batch_status(
            base_url="http://example.com",
            auth={"username": "a", "password": "b"},
            action="disable",
            dry_run=True,
            match_mode="name",
            batch_text="gpt-4o azure\nmissing x\nceshi default\n",
        )
        confirm = run_channel_batch_status(
            base_url="http://example.com",
            auth={"username": "a", "password": "b"},
            action="disable",
            dry_run=False,
            match_mode="name",
            batch_text="gpt-4o azure\nceshi default\n",
        )

    assert preview.match_mode == "name"
    assert preview.matched_count == 2
    assert preview.skipped_count == 2  # missing + already disabled
    client.update_channel_status.assert_called_once_with(11, CHANNEL_STATUS_MANUALLY_DISABLED)
    assert confirm.updated_count == 1
    assert confirm.skipped_count == 1


if __name__ == "__main__":
    test_parse_model_list_dedupe_and_split()
    test_extract_upstream_models_from_mapping()
    test_extract_upstream_models_ignores_models_field()
    test_run_dry_run_matches_by_upstream_and_type()
    test_run_type_mode_matches_all_of_type()
    test_run_ids_mode_updates_selected()
    test_run_confirm_skips_already_target_and_updates_others()
    test_run_requires_channel_type()
    test_run_name_mode_disables_matched_and_skips_missing()
    print("ok")
