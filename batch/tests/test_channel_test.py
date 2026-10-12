"""渠道一键测试：按模型回报失败项。"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

BATCH_DIR = Path(__file__).resolve().parents[1]
if str(BATCH_DIR) not in sys.path:
    sys.path.insert(0, str(BATCH_DIR))

from lib.batch_processor import run_batch_create  # noqa: E402
from lib.channel_builder import build_channel_payload  # noqa: E402
from lib.channel_test import format_test_failure_message, test_channel_models  # noqa: E402


def test_failure_message_names_models():
    text = format_test_failure_message(
        [
            {"model": "glm-5.1", "message": "connection refused"},
            {"model": "qwen-z", "message": "timeout"},
        ]
    )
    assert "模型 glm-5.1: connection refused" in text
    assert "模型 qwen-z: timeout" in text


def test_channel_models_reports_which_model_failed():
    client = MagicMock()
    client.test_channel.side_effect = [
        {"success": True, "message": "", "time": 0.21, "model": "m1"},
        {"success": False, "message": "upstream 401", "time": 0.08, "model": "m2"},
    ]
    result = test_channel_models(client, 12, ["m1", "m2"], name="demo-ch")
    assert result["success"] is False
    assert result["failed_models"] == ["m2"]
    assert "模型 m2: upstream 401" in result["message"]
    assert client.test_channel.call_count == 2
    client.test_channel.assert_any_call(12, model="m1")
    client.test_channel.assert_any_call(12, model="m2")


def test_channel_models_all_ok():
    client = MagicMock()
    client.test_channel.return_value = {"success": True, "message": "", "time": 0.85, "model": "m1"}
    result = test_channel_models(client, 7, ["m1"], name="ok-ch")
    assert result["success"] is True
    assert result["failed"] == []
    assert "0.85 秒" in result["message"]


def test_build_channel_payload_writes_normalized_base_url_to_remark():
    payload = build_channel_payload(
        {
            "名称": "demo",
            "分组": "g1",
            "类型": "OpenAI",
            "模型": "demo",
            "模型重定向": "demo->upstream-demo",
            "base_url": "https://upstream.example.com/v1/",
            "秘钥": "sk-demo",
        },
        channel_type=1,
        default_key="",
        known_groups={"g1"},
    )
    channel = payload["channel"]
    assert channel["base_url"] == "https://upstream.example.com/v1"
    assert channel["remark"] == channel["base_url"]


def test_batch_create_attaches_channel_id_for_test():
    client = MagicMock()
    client.list_groups.return_value = ["demo-alpha-test"]
    client.get_status.return_value = {}
    client.create_channel.return_value = {"success": True, "message": ""}
    client.list_all_channels.side_effect = [
        [],
        [
            {
                "id": 164,
                "name": "demo-alpha-test-qwen-z",
                "group": "demo-alpha-test",
                "models": "demo-alpha-test-qwen-z",
                "model_mapping": '{"demo-alpha-test-qwen-z":"qwen-z"}',
            }
        ],
    ]
    line = (
        "demo-alpha-test-qwen-z demo-alpha-test OpenAI demo-alpha-test-qwen-z "
        "demo-alpha-test-qwen-z->qwen-z https://llm.example.com/compatible-mode EXAMPLE_API_KEY"
    )
    with patch("lib.batch_processor.NewAPIClient", return_value=client), patch(
        "lib.batch_processor.authenticate_client"
    ), patch(
        "lib.batch_processor.get_channel_types",
        return_value=([{"value": 1, "label": "OpenAI"}], "bundled"),
    ), patch(
        "lib.batch_processor.ensure_groups_for_rows",
        return_value=set(),
    ):
        result = run_batch_create(
            base_url="http://example.com",
            batch_text=line,
            default_key="",
            auth={"username": "a", "password": "b"},
        )
    created = [
        item
        for item in result.items
        if item.get("success") and not item.get("meta") and not item.get("skipped")
    ]
    assert result.success_count == 1
    assert created[0]["channel_id"] == 164
    assert "demo-alpha-test-qwen-z" in created[0]["models"]
    created_payload = client.create_channel.call_args.args[0]
    assert created_payload["channel"]["remark"] == created_payload["channel"]["base_url"]


if __name__ == "__main__":
    test_failure_message_names_models()
    test_channel_models_reports_which_model_failed()
    test_channel_models_all_ok()
    test_build_channel_payload_writes_normalized_base_url_to_remark()
    test_batch_create_attaches_channel_id_for_test()
    print("ok")

