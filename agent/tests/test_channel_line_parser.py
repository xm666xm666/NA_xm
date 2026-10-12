"""已格式化渠道行解析。"""

from __future__ import annotations

import sys
from pathlib import Path

AGENT_DIR = Path(__file__).resolve().parents[1]
if str(AGENT_DIR) not in sys.path:
    sys.path.insert(0, str(AGENT_DIR))

from lib.channel_extractor import extract_channels  # noqa: E402
from lib.channel_line_parser import (  # noqa: E402
    expand_volcano_space_line,
    looks_like_channel_line,
    looks_like_compact_channel_line,
    looks_like_volcano_space_line,
    parse_channel_line,
)

VOLCANO_SPACE = (
    "ai-train-camp-uat-glm-5.2 字节火山方舟、豆包通用 "
    "ep-20260708113825-d45qv ark-test-key"
)
VOLCANO_MULTILINE = (
    "ai-train-camp-uat-glm-5.2\n"
    "字节火山方舟、豆包通用\n"
    "ep-20260708113825-d45qv\n"
    "ark-test-key"
)

SAMPLE = (
    "sample-azure-test-gpt-x Azure OpenAI sample-azure-test-gpt-x "
    "sample-azure-test-gpt-x->gpt-x https://sample-azure.example.com "
    "2025-04-01-preview REPLACEMEAZUREKEYNOTREAL0000000000000000XX"
)

COMPACT_CUSTOM = (
    "pv-agent-uat-glm-5.1 自定义渠道 glm-5.1 "
    "https://ai-model.r2ai.com.cn/glm/v1/chat/completions "
    "sk-glm51c19d4a73e60c1f9a2d8e7b6c4f1"
)


def test_looks_like_channel_line():
    assert looks_like_channel_line(SAMPLE)


def test_parse_channel_line_group_from_name():
    row = parse_channel_line(SAMPLE)
    assert row["名称"] == "sample-azure-test-gpt-x"
    assert row["类型"] == "Azure OpenAI"
    assert row["分组"] == "sample-azure-test"
    assert row["模型"] == "sample-azure-test-gpt-x"
    assert row["默认API版本"] == "2025-04-01-preview"


def test_extract_channels_from_space_separated_line():
    result = extract_channels(SAMPLE, use_llm=False)
    assert result.success is True
    assert result.count == 1
    assert result.mode == "rules"
    assert result.llm.invoked is False
    assert "sample-azure-test-gpt-x sample-azure-test Azure OpenAI" in result.channel_line
    assert "sample-azure-test-gpt-x->gpt-x" in result.channel_line


def test_extract_channels_from_tab_separated_line():
    tabbed = SAMPLE.replace(" ", "\t")
    result = extract_channels(tabbed, use_llm=False)
    assert result.success is True
    assert result.count == 1


def test_looks_like_compact_custom_line():
    assert looks_like_compact_channel_line(COMPACT_CUSTOM)
    assert looks_like_channel_line(COMPACT_CUSTOM)


def test_parse_compact_custom_line():
    row = parse_channel_line(COMPACT_CUSTOM)
    assert row["名称"] == "pv-agent-uat-glm-5.1"
    assert row["分组"] == "pv-agent-uat"
    assert row["类型"] == "自定义渠道"
    assert row["模型"] == "pv-agent-uat-glm-5.1"
    assert row["模型重定向"] == "pv-agent-uat-glm-5.1->glm-5.1"
    assert row["base_url"] == "https://ai-model.r2ai.com.cn/glm/v1/chat/completions"
    assert row["秘钥"] == "sk-glm51c19d4a73e60c1f9a2d8e7b6c4f1"


def test_extract_compact_custom_line():
    result = extract_channels(COMPACT_CUSTOM, use_llm=False)
    assert result.success is True
    assert result.count == 1
    expected = (
        "pv-agent-uat-glm-5.1 pv-agent-uat 自定义渠道 pv-agent-uat-glm-5.1 "
        "pv-agent-uat-glm-5.1->glm-5.1 "
        "https://ai-model.r2ai.com.cn/glm/v1/chat/completions "
        "sk-glm51c19d4a73e60c1f9a2d8e7b6c4f1"
    )
    assert result.channel_line == expected


def test_parse_compact_with_explicit_group():
    line = (
        "demo-alpha-test-glm-x demo-alpha-test 自定义渠道 glm-x "
        "https://example.com/v1 sk-abcdefghijklmnop"
    )
    row = parse_channel_line(line)
    assert row["名称"] == "demo-alpha-test-glm-x"
    assert row["分组"] == "demo-alpha-test"
    assert row["模型"] == "demo-alpha-test-glm-x"
    assert row["模型重定向"] == "demo-alpha-test-glm-x->glm-x"


def test_expand_volcano_space_line():
    assert looks_like_volcano_space_line(VOLCANO_SPACE)
    lines = expand_volcano_space_line(VOLCANO_SPACE)
    assert lines == [
        "ai-train-camp-uat-glm-5.2",
        "字节火山方舟、豆包通用",
        "ep-20260708113825-d45qv",
        "ark-test-key",
    ]


def test_volcano_space_line_equals_multiline():
    one = extract_channels(VOLCANO_SPACE, use_llm=False)
    multi = extract_channels(VOLCANO_MULTILINE, use_llm=False)
    assert one.success is True
    assert multi.success is True
    assert one.channel_line == multi.channel_line
    assert "ai-train-camp-uat-glm-5.2" in one.channel_line
    assert "ep-20260708113825-d45qv" in one.channel_line
    assert "ark-test-key" in one.channel_line
    assert "字节火山方舟、豆包通用" in one.channel_line


def test_volcano_space_line_without_type_label():
    line = (
        "ai-train-camp-uat-glm-5.2 "
        "ep-20260708113825-d45qv ark-test-key"
    )
    result = extract_channels(line, use_llm=False)
    assert result.success is True
    assert "字节火山方舟、豆包通用" in result.channel_line
    assert "ep-20260708113825-d45qv" in result.channel_line


OPENAI_KIMI_BLOCK = (
    "ai-train-camp-uat-kimi-k3\n"
    "OpenAI\n"
    "kimi-k3\n"
    "sk-ws-H.EIXXMLE.jkz4.MEUCIDzeI1r7TLZJ--DvN7QZZjQ-loqLpCR6PbQuEGlcBDf6AiEA4xYu-g_IxM_O1kXXS0wtYyDW0dWtg5Xvu0732AAnVB0\n"
    "https://ws-wqeewhpvjmrkfcbm.cn-beijing.maas.aliyuncs.com/compatible-mode/v1"
)


def test_explicit_openai_not_custom():
    result = extract_channels(OPENAI_KIMI_BLOCK, use_llm=False)
    assert result.success is True
    assert result.fields.type_label == "OpenAI"
    assert result.fields.upstream_model == "kimi-k3"
    assert "OpenAI" in result.channel_line
    assert "kimi-k3" in result.channel_line
    assert "compatible-mode/v1" in result.channel_line


def test_explicit_openai_lowercase():
    text = OPENAI_KIMI_BLOCK.replace("OpenAI", "openai")
    result = extract_channels(text, use_llm=False)
    assert result.success is True
    assert result.fields.type_label == "OpenAI"


def test_azure_url_defaults_to_azure_not_openai():
    text = (
        "sample-azure-test-gpt-4o\n"
        "https://your-resource.openai.azure.com/openai/responses?api-version=2025-04-01-preview\n"
        "yourAzureApiKeyReplaceMe00000000000000000000000000\n"
        "gpt-4o"
    )
    result = extract_channels(text, use_llm=False)
    assert result.success is True
    assert result.fields.type_label == "Azure OpenAI"
    assert "Azure OpenAI" in result.channel_line
    assert result.fields.upstream_model == "gpt-4o"


def test_azure_text_embedding_ada_002_is_upstream():
    text = (
        "clinai-uat-ctd-ncdp-text-ada-002\n"
        + ("A" * 40)  # 符合 Azure 密钥形态的无效测试占位符
        + "\n"
        + "https://phc-openai-clinai-uat.openai.azure.com/openai/responses?api-version=2025-04-01-preview\n"
        + "text-embedding-ada-002\n"
    )
    result = extract_channels(text, use_llm=False)
    assert result.success is True
    assert result.fields.type_label == "Azure OpenAI"
    assert result.fields.name == "clinai-uat-ctd-ncdp-text-ada-002"
    assert result.fields.group == "clinai-uat"
    assert result.fields.model == "clinai-uat-ctd-ncdp-text-ada-002"
    assert result.fields.upstream_model == "text-embedding-ada-002"
    assert result.fields.base_url == "https://phc-openai-clinai-uat.openai.azure.com"
    assert result.fields.api_version == "2025-04-01-preview"
    assert "clinai-uat-ctd-ncdp-text-ada-002->text-embedding-ada-002" in result.channel_line


def test_channel_name_with_chinese_remark():
    text = (
        "ai-train-camp-uat-kimi-k3-商业百炼\n"
        "OpenAI\n"
        "kimi-k3\n"
        "sk-ws-H.EIXXMLE.jkz4.MEUCIDzeI1r7TLZJ--DvN7QZZjQ-loqLpCR6PbQuEGlcBDf6AiEA4xYu-g_IxM_O1kXXS0wtYyDW0dWtg5Xvu0732AAnVB0\n"
        "https://ws-wqeewhpvjmrkfcbm.cn-beijing.maas.aliyuncs.com/compatible-mode/v1"
    )
    result = extract_channels(text, use_llm=False)
    assert result.success is True
    assert result.fields.name == "ai-train-camp-uat-kimi-k3-商业百炼"
    assert result.fields.group == "ai-train-camp-uat"
    assert result.fields.type_label == "OpenAI"
    assert result.fields.model == "ai-train-camp-uat-kimi-k3"
    assert result.fields.upstream_model == "kimi-k3"
    expected = (
        "ai-train-camp-uat-kimi-k3-商业百炼 ai-train-camp-uat OpenAI "
        "ai-train-camp-uat-kimi-k3 ai-train-camp-uat-kimi-k3->kimi-k3 "
        "https://ws-wqeewhpvjmrkfcbm.cn-beijing.maas.aliyuncs.com/compatible-mode/v1 "
        "sk-ws-H.EIXXMLE.jkz4.MEUCIDzeI1r7TLZJ--DvN7QZZjQ-loqLpCR6PbQuEGlcBDf6AiEA4xYu-g_IxM_O1kXXS0wtYyDW0dWtg5Xvu0732AAnVB0"
    )
    assert result.channel_line == expected


if __name__ == "__main__":
    test_looks_like_channel_line()
    test_parse_channel_line_group_from_name()
    test_extract_channels_from_space_separated_line()
    test_extract_channels_from_tab_separated_line()
    test_looks_like_compact_custom_line()
    test_parse_compact_custom_line()
    test_extract_compact_custom_line()
    test_parse_compact_with_explicit_group()
    test_expand_volcano_space_line()
    test_volcano_space_line_equals_multiline()
    test_volcano_space_line_without_type_label()
    test_explicit_openai_not_custom()
    test_explicit_openai_lowercase()
    test_azure_url_defaults_to_azure_not_openai()
    test_azure_text_embedding_ada_002_is_upstream()
    test_channel_name_with_chinese_remark()
    print("ok")
