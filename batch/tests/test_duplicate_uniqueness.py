"""本站内渠道名 / 模型名 / 令牌名唯一性校验。"""

from __future__ import annotations

import sys
from pathlib import Path

BATCH_DIR = Path(__file__).resolve().parents[1]
if str(BATCH_DIR) not in sys.path:
    sys.path.insert(0, str(BATCH_DIR))

from lib.duplicate_checker import (  # noqa: E402
    ChannelBatchSeen,
    build_existing_index,
    build_model_index,
    build_name_index,
    find_existing_duplicate,
    is_batch_duplicate,
)
from lib.token_duplicate_checker import (  # noqa: E402
    build_existing_index as build_token_existing_index,
    build_name_index as build_token_name_index,
    find_existing_duplicate as find_token_existing,
    is_batch_duplicate as is_token_batch_duplicate,
    token_name_group,
)


def test_channel_batch_skips_duplicate_name():
    seen = ChannelBatchSeen()
    assert is_batch_duplicate({"名称": "ch-a", "模型": "m-a"}, seen) is None
    reason = is_batch_duplicate({"名称": "ch-a", "模型": "m-b"}, seen)
    assert reason is not None
    assert "渠道名重复" in reason


def test_channel_batch_skips_duplicate_model():
    seen = ChannelBatchSeen()
    assert is_batch_duplicate({"名称": "ch-a", "模型": "m-a"}, seen) is None
    reason = is_batch_duplicate({"名称": "ch-b", "模型": "m-a"}, seen)
    assert reason is not None
    assert "模型名重复" in reason


def test_channel_site_rejects_existing_name_regardless_of_group():
    channels = [{"id": 11, "name": "ch-a", "group": "g1", "models": "m-old"}]
    reason = find_existing_duplicate(
        {"名称": "ch-a", "分组": "g2", "模型": "m-new"},
        build_name_index(channels),
        build_model_index(channels),
    )
    assert reason is not None
    assert "渠道名已存在" in reason
    assert "ID=11" in reason


def test_channel_site_rejects_existing_model_from_mapping():
    channels = [
        {
            "id": 22,
            "name": "occupied",
            "group": "g1",
            "models": "other",
            "model_mapping": '{"m-a":"upstream"}',
        }
    ]
    reason = find_existing_duplicate(
        {"名称": "ch-new", "模型": "m-a"},
        build_name_index(channels),
        build_model_index(channels),
    )
    assert reason is not None
    assert "模型名已存在" in reason
    assert "occupied" in reason


def test_channel_delete_index_still_uses_name_and_group():
    channels = [{"id": 3, "name": "ch-a", "group": "g1,g2"}]
    index = build_existing_index(channels)
    assert index[("ch-a", "g1")]["id"] == 3
    assert index[("ch-a", "g2")]["id"] == 3
    assert ("ch-a", "g3") not in index


def test_token_batch_skips_duplicate_name_even_if_group_differs():
    seen: set[str] = set()
    assert is_token_batch_duplicate({"名称": "tok-a", "分组": "g1"}, seen) is None
    reason = is_token_batch_duplicate({"名称": "tok-a", "分组": "g2"}, seen)
    assert reason is not None
    assert "令牌名重复" in reason


def test_token_site_rejects_existing_name_regardless_of_group():
    tokens = [{"id": 7, "name": "tok-a", "group": "g1"}]
    reason = find_token_existing(
        {"名称": "tok-a", "分组": "g2"},
        build_token_name_index(tokens),
    )
    assert reason is not None
    assert "令牌名已存在" in reason
    assert "ID=7" in reason


def test_token_delete_index_still_uses_name_and_group():
    tokens = [{"id": 8, "name": "tok-a", "group": "g1"}]
    index = build_token_existing_index(tokens)
    assert index[token_name_group("tok-a", "g1")]["id"] == 8
    assert token_name_group("tok-a", "g2") not in index


if __name__ == "__main__":
    test_channel_batch_skips_duplicate_name()
    test_channel_batch_skips_duplicate_model()
    test_channel_site_rejects_existing_name_regardless_of_group()
    test_channel_site_rejects_existing_model_from_mapping()
    test_channel_delete_index_still_uses_name_and_group()
    test_token_batch_skips_duplicate_name_even_if_group_differs()
    test_token_site_rejects_existing_name_regardless_of_group()
    test_token_delete_index_still_uses_name_and_group()
    print("ok")
