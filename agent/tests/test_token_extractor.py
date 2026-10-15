"""令牌智能提取单元测试。"""

from __future__ import annotations

import sys
from pathlib import Path

AGENT_DIR = Path(__file__).resolve().parents[1]
if str(AGENT_DIR) not in sys.path:
    sys.path.insert(0, str(AGENT_DIR))

from lib.token_extractor import (  # noqa: E402
    extract_tokens,
    join_token_name,
    normalize_model_list,
)


def test_join_token_name_no_duplicate():
    assert join_token_name("demo-alpha-uat-gpt-x", "张三") == "demo-alpha-uat-gpt-x-张三"
    assert join_token_name("demo-alpha-uat-gpt-x-张三", "张三") == "demo-alpha-uat-gpt-x-张三"


def test_normalize_model_list_cn_comma():
    assert normalize_model_list("a，b、c;d") == ["a", "b", "c", "d"]


def test_extract_standard_three_lines():
    text = "\n".join(
        [
            "demo-alpha-uat-gpt-x-张三",
            "demo-alpha-uat",
            "demo-alpha-uat-gpt-x，demo-alpha-uat-gpt-y",
        ]
    )
    result = extract_tokens(text)
    assert result.success
    assert result.count == 1
    assert result.items[0].name == "demo-alpha-uat-gpt-x-张三"
    assert result.items[0].group == "demo-alpha-uat"
    assert result.items[0].models == "demo-alpha-uat-gpt-x,demo-alpha-uat-gpt-y"
    assert result.token_lines.startswith("demo-alpha-uat-gpt-x-张三\tdemo-alpha-uat\t")


def test_extract_split_name_and_person():
    text = "\n".join(
        [
            "demo-alpha-uat-gpt-x",
            "张三",
            "demo-alpha-uat",
            "demo-alpha-uat-gpt-x，demo-alpha-uat-gpt-y",
        ]
    )
    result = extract_tokens(text)
    assert result.success
    assert result.items[0].name == "demo-alpha-uat-gpt-x-张三"
    assert "demo-alpha-uat-gpt-x-张三\tdemo-alpha-uat\t" in result.token_lines


def test_extract_labeled_lines():
    text = "\n".join(
        [
            "令牌名：demo-beta-test-claude",
            "人名：李四",
            "分组：demo-beta-test",
            "模型：demo-beta-test-claude-sonnet",
        ]
    )
    result = extract_tokens(text)
    assert result.success
    assert result.items[0].name == "demo-beta-test-claude-李四"
    assert result.items[0].group == "demo-beta-test"
    assert result.items[0].models == "demo-beta-test-claude-sonnet"


def test_extract_multi_blocks():
    text = "\n".join(
        [
            "demo-a-uat-m1-张三",
            "demo-a-uat",
            "m1，m2",
            "",
            "demo-b-test",
            "王五",
            "demo-b-test",
            "m3",
        ]
    )
    result = extract_tokens(text)
    assert result.success, result.message
    assert result.count == 2
    assert result.items[0].name == "demo-a-uat-m1-张三"
    assert result.items[0].group == "demo-a-uat"
    assert result.items[0].models == "m1,m2"
    assert result.items[1].name == "demo-b-test-王五"
    assert result.items[1].group == "demo-b-test"
    assert result.items[1].models == "m3"


def test_extract_already_standard_line():
    text = "tok-name-甲  group-uat  m1,m2"
    result = extract_tokens(text)
    assert result.success
    assert result.items[0].name == "tok-name-甲"
    assert result.items[0].group == "group-uat"
    assert result.items[0].models == "m1,m2"


def test_extract_pure_number_line_as_token_quota():
    text = "\n".join(
        [
            "demo-alpha-uat-gpt-x-张三",
            "demo-alpha-uat",
            "demo-alpha-uat-gpt-x，demo-alpha-uat-gpt-y",
            "500000",
        ]
    )
    result = extract_tokens(text)
    assert result.success, result.message
    item = result.items[0]
    assert item.models == "demo-alpha-uat-gpt-x,demo-alpha-uat-gpt-y"
    assert item.quota == "500000"
    assert result.token_lines.endswith(
        "demo-alpha-uat-gpt-x-张三\tdemo-alpha-uat\t"
        "demo-alpha-uat-gpt-x,demo-alpha-uat-gpt-y\t500000"
    )


def test_extract_standard_line_with_quota_column():
    result = extract_tokens("tok-name-甲\tgroup-uat\tm1,m2\t1000000")
    assert result.success, result.message
    item = result.items[0]
    assert item.models == "m1,m2"
    assert item.quota == "1000000"
    assert result.token_lines == "tok-name-甲\tgroup-uat\tm1,m2\t1000000"


def test_extract_channel_block_with_quota_line():
    channel = (
        "finance-prod-doubao-seed-2.0 finance-prod 字节火山方舟、豆包通用 "
        "finance-prod-doubao-seed-2.0 "
        "finance-prod-doubao-seed-2.0->ep-20260810094015-8wzmw "
        "https://ark.cn-beijing.volces.com "
        "ark-test-key"
    )
    result = extract_tokens(f"finance-prod-doubao-seed-2.0-费仕忆\n{channel}\n800000")
    assert result.success, result.message
    item = result.items[0]
    assert item.models == "finance-prod-doubao-seed-2.0"
    assert item.quota == "800000"
    assert result.token_lines.endswith("\t800000")


def test_extract_from_channel_lines():
    text = "\n".join(
        [
            "efficiency-ai-uat-gpt5.6sol-张三",
            "efficiency-ai-uat-product-gpt5.6sol efficiency-ai-uat Azure OpenAI "
            "efficiency-ai-uat-product-gpt5.6sol "
            "efficiency-ai-uat-product-gpt5.6sol->gpt-5.6-sol "
            "https://phc-openai-aiic-pmg.openai.azure.com 2025-04-01-preview "
            "azure-test-key",
            "efficiency-ai-uat-project-gpt5.6sol efficiency-ai-uat Azure OpenAI "
            "efficiency-ai-uat-project-gpt5.6sol "
            "efficiency-ai-uat-project-gpt5.6sol->gpt-5.6-sol "
            "https://phc-openai-aiic-pmo.openai.azure.com 2025-04-01-preview "
            "azure-test-key",
            "efficiency-ai-uat-agent-gpt5.6sol efficiency-ai-uat Azure OpenAI "
            "efficiency-ai-uat-agent-gpt5.6sol "
            "efficiency-ai-uat-agent-gpt5.6sol->gpt-5.6-sol "
            "https://phc-openai-aiic-llmg.openai.azure.com 2025-04-01-preview "
            + ("A" * 40),
        ]
    )
    result = extract_tokens(text)
    assert result.success, result.message
    assert result.count == 1
    item = result.items[0]
    assert item.name == "efficiency-ai-uat-gpt5.6sol-张三"
    assert item.group == "efficiency-ai-uat"
    assert item.models == (
        "efficiency-ai-uat-product-gpt5.6sol,"
        "efficiency-ai-uat-project-gpt5.6sol,"
        "efficiency-ai-uat-agent-gpt5.6sol"
    )


def test_extract_channel_lines_with_blank_gaps():
    """渠道行之间空行仍合并为同一条令牌。"""
    text = "\n".join(
        [
            "demo-alpha-uat-gpt-x-张三",
            "",
            "demo-alpha-uat-gpt-x demo-alpha-uat OpenAI demo-alpha-uat-gpt-x "
            "demo-alpha-uat-gpt-x->gpt-4o https://example.com/v1 "
            "EXAMPLE_API_KEY",
            "",
            "demo-alpha-uat-gpt-y demo-alpha-uat OpenAI demo-alpha-uat-gpt-y "
            "demo-alpha-uat-gpt-y->gpt-4o https://example.com/v1 "
            "EXAMPLE_API_KEY",
        ]
    )
    result = extract_tokens(text)
    assert result.success, result.message
    assert result.count == 1
    assert result.items[0].group == "demo-alpha-uat"
    assert result.items[0].models == "demo-alpha-uat-gpt-x,demo-alpha-uat-gpt-y"


def test_extract_channel_lines_person_split():
    """令牌名与人名分行 + 渠道批量行。"""
    text = "\n".join(
        [
            "efficiency-ai-uat-gpt5.6sol",
            "张三",
            "efficiency-ai-uat-product-gpt5.6sol efficiency-ai-uat Azure OpenAI "
            "efficiency-ai-uat-product-gpt5.6sol "
            "efficiency-ai-uat-product-gpt5.6sol->gpt-5.6-sol "
            "https://phc-openai-aiic-pmg.openai.azure.com 2025-04-01-preview "
            "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAABACOGdemo1",
            "efficiency-ai-uat-project-gpt5.6sol efficiency-ai-uat Azure OpenAI "
            "efficiency-ai-uat-project-gpt5.6sol "
            "efficiency-ai-uat-project-gpt5.6sol->gpt-5.6-sol "
            "https://phc-openai-aiic-pmo.openai.azure.com 2025-04-01-preview "
            "BBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBABACOGdemo2",
        ]
    )
    result = extract_tokens(text)
    assert result.success, result.message
    assert result.items[0].name == "efficiency-ai-uat-gpt5.6sol-张三"
    assert result.items[0].group == "efficiency-ai-uat"
    assert result.items[0].models == (
        "efficiency-ai-uat-product-gpt5.6sol,efficiency-ai-uat-project-gpt5.6sol"
    )


def test_extract_person_only_before_channel():
    """仅人名 + 渠道行 → 模型-人名。"""
    channel = (
        "finance-prod-doubao-seed-2.0 finance-prod 字节火山方舟、豆包通用 "
        "finance-prod-doubao-seed-2.0 "
        "finance-prod-doubao-seed-2.0->ep-20260810094015-8wzmw "
        "https://ark.cn-beijing.volces.com "
        "ark-test-key"
    )
    result = extract_tokens(f"费仕忆\n{channel}")
    assert result.success, result.message
    assert result.items[0].name == "finance-prod-doubao-seed-2.0-费仕忆"
    assert result.items[0].group == "finance-prod"
    assert result.items[0].models == "finance-prod-doubao-seed-2.0"


def test_extract_token_name_embedded_in_channel_name():
    """渠道名称字段已是 模型-人名（无独立令牌名行）。"""
    channel = (
        "finance-prod-doubao-seed-2.0-费仕忆 finance-prod 字节火山方舟、豆包通用 "
        "finance-prod-doubao-seed-2.0 "
        "finance-prod-doubao-seed-2.0->ep-20260810094015-8wzmw "
        "https://ark.cn-beijing.volces.com "
        "ark-test-key"
    )
    result = extract_tokens(channel)
    assert result.success, result.message
    assert result.items[0].name == "finance-prod-doubao-seed-2.0-费仕忆"
    assert result.items[0].group == "finance-prod"
    assert result.items[0].models == "finance-prod-doubao-seed-2.0"


if __name__ == "__main__":
    test_join_token_name_no_duplicate()
    test_normalize_model_list_cn_comma()
    test_extract_standard_three_lines()
    test_extract_split_name_and_person()
    test_extract_labeled_lines()
    test_extract_multi_blocks()
    test_extract_already_standard_line()
    test_extract_from_channel_lines()
    test_extract_channel_lines_with_blank_gaps()
    test_extract_channel_lines_person_split()
    test_extract_person_only_before_channel()
    test_extract_token_name_embedded_in_channel_name()
    print("ok")
