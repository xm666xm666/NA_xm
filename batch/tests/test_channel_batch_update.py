"""渠道原配置批量更新。"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

BATCH_DIR = Path(__file__).resolve().parents[1]
if str(BATCH_DIR) not in sys.path:
    sys.path.insert(0, str(BATCH_DIR))

from lib.channel_batch_update import (  # noqa: E402
    _describe_changes,
    _merge_update,
    run_channel_batch_update,
)
from lib.channel_builder import split_channel_rename  # noqa: E402


def test_split_channel_rename():
    assert split_channel_rename("demo-glm-4.7") == ("demo-glm-4.7", "demo-glm-4.7")
    assert split_channel_rename("old=>new") == ("old", "new")


def test_describe_mapping_change():
    before = {
        "name": "demo-glm-4.7",
        "models": "demo-glm-4.7",
        "model_mapping": '{"demo-glm-4.7": "GLM-4.7"}',
        "base_url": "https://ark.example.com",
        "type": 45,
        "group": "g1",
    }
    after = dict(before)
    after["model_mapping"] = '{"demo-glm-4.7": "GLM-5.2"}'
    text = _describe_changes(before, after)
    assert "上游映射" in text
    assert "GLM-5.2" in text


def test_merge_keeps_status_and_omits_empty_key():
    existing = {
        "id": 12,
        "name": "demo-glm-4.7",
        "status": 2,
        "priority": 9,
        "type": 45,
        "models": "demo-glm-4.7",
        "group": "g1",
        "base_url": "https://old.example.com",
        "remark": "历史说明",
        "key": "",
    }
    payload_channel = {
        "type": 45,
        "models": "demo-glm-4.7",
        "group": "g1",
        "base_url": "https://new.example.com",
        "remark": "https://new.example.com",
        "model_mapping": '{"demo-glm-4.7": "GLM-5.2"}',
    }
    merged = _merge_update(
        existing,
        payload_channel=payload_channel,
        new_name="demo-glm-4.7",
        overwrite_remark=True,
    )
    assert merged["id"] == 12
    assert merged["status"] == 2
    assert merged["priority"] == 9
    assert merged["base_url"] == "https://new.example.com"
    assert merged["remark"] == "https://new.example.com"
    assert "key" not in merged

    preserved = _merge_update(
        existing,
        payload_channel=payload_channel,
        new_name="demo-glm-4.7",
        overwrite_remark=False,
    )
    assert preserved["remark"] == "历史说明"

    empty_remark = _merge_update(
        {**existing, "remark": ""},
        payload_channel=payload_channel,
        new_name="demo-glm-4.7",
        overwrite_remark=False,
    )
    assert empty_remark["remark"] == "https://new.example.com"


def test_run_update_dry_run_and_confirm():
    client = MagicMock()
    client.list_groups.return_value = ["g1"]
    client.list_all_channels.return_value = [
        {
            "id": 7,
            "name": "demo-glm-4.7",
            "group": "g1",
            "type": 45,
            "models": "demo-glm-4.7",
            "model_mapping": '{"demo-glm-4.7": "GLM-4.7"}',
            "base_url": "https://ark.example.com",
            "remark": "人工填写的历史备注",
            "status": 1,
        }
    ]
    client.get_status.return_value = {}
    client.update_channel.return_value = {"success": True}

    line = (
        "demo-glm-4.7 g1 字节火山方舟、豆包通用 demo-glm-4.7 "
        "demo-glm-4.7->GLM-5.2 https://ark.example.com"
    )

    import lib.channel_batch_update as mod

    orig_client = mod.NewAPIClient
    orig_auth = mod.authenticate_client
    orig_types = mod.get_channel_types
    mod.NewAPIClient = lambda *a, **k: client
    mod.authenticate_client = lambda *a, **k: None
    mod.get_channel_types = lambda *a, **k: (
        [{"value": 45, "label": "字节火山方舟、豆包通用"}],
        "test",
    )
    try:
        preview = run_channel_batch_update(
            base_url="https://na.example.com",
            batch_text=line,
            auth={"username": "a", "password": "b"},
            dry_run=True,
            overwrite_remark=True,
        )
        assert preview.matched_count == 1
        assert preview.updated_count == 0
        client.update_channel.assert_not_called()
        assert "备注" in preview.items[1]["message"]
        assert preview.remark_overwrite_candidates == 1

        kept = run_channel_batch_update(
            base_url="https://na.example.com",
            batch_text=line,
            auth={"username": "a", "password": "b"},
            dry_run=False,
        )
        assert kept.updated_count == 1
        client.update_channel.assert_called_once()
        sent = client.update_channel.call_args[0][0]
        assert sent["id"] == 7
        assert "GLM-5.2" in str(sent.get("model_mapping"))
        assert sent["remark"] == "人工填写的历史备注"
        assert "key" not in sent

        client.update_channel.reset_mock()
        done = run_channel_batch_update(
            base_url="https://na.example.com",
            batch_text=line,
            auth={"username": "a", "password": "b"},
            dry_run=False,
            overwrite_remark=True,
        )
        assert done.updated_count == 1
        client.update_channel.assert_called_once()
        sent = client.update_channel.call_args[0][0]
        assert sent["remark"] == "https://ark.example.com"
        assert "key" not in sent

        client.update_channel.reset_mock()
        line_with_key = line + " sk-should-be-ignored"
        ignored = run_channel_batch_update(
            base_url="https://na.example.com",
            batch_text=line_with_key,
            auth={"username": "a", "password": "b"},
            dry_run=False,
            default_key="sk-global-should-be-ignored",
            overwrite_remark=True,
        )
        assert ignored.updated_count == 1
        sent2 = client.update_channel.call_args[0][0]
        assert "key" not in sent2
    finally:
        mod.NewAPIClient = orig_client
        mod.authenticate_client = orig_auth
        mod.get_channel_types = orig_types


if __name__ == "__main__":
    test_split_channel_rename()
    test_describe_mapping_change()
    test_merge_keeps_status_and_omits_empty_key()
    test_run_update_dry_run_and_confirm()
    print("ok")
