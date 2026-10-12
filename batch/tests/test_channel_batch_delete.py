"""渠道批量删除行解析。"""

from __future__ import annotations

import sys
from pathlib import Path

BATCH_DIR = Path(__file__).resolve().parents[1]
if str(BATCH_DIR) not in sys.path:
    sys.path.insert(0, str(BATCH_DIR))

from lib.channel_batch_delete import parse_channel_delete_rows  # noqa: E402


def test_parse_name_group_space_and_tab():
    rows = parse_channel_delete_rows(
        "gpt-4o azure\n"
        "Doubao-Seed-1. 6-aies doubao\n"
        "AI_Product-test-gpt-5.5\tAI_Product-test\n"
        "# skip comment\n"
        "名称 分组 类型\n"
    )
    assert rows == [
        {"名称": "gpt-4o", "分组": "azure"},
        {"名称": "Doubao-Seed-1. 6-aies", "分组": "doubao"},
        {"名称": "AI_Product-test-gpt-5.5", "分组": "AI_Product-test"},
    ]


def test_parse_full_create_line_without_secret():
    line = (
        "gpt-4o azure Azure OpenAI gpt-4o gpt-4o->gpt-4o "
        "https://example.openai.azure.com 2025-04-01-preview"
    )
    rows = parse_channel_delete_rows(line)
    assert rows == [{"名称": "gpt-4o", "分组": "azure"}]


if __name__ == "__main__":
    test_parse_name_group_space_and_tab()
    test_parse_full_create_line_without_secret()
    print("ok")
