"""渠道名分组 / 模型列推导。"""

from __future__ import annotations

import sys
from pathlib import Path

AGENT_DIR = Path(__file__).resolve().parents[1]
if str(AGENT_DIR) not in sys.path:
    sys.path.insert(0, str(AGENT_DIR))

from lib.group_deriver import derive_group_from_name, derive_model_from_name  # noqa: E402


def test_qwen37_plus_chinese_remark_group():
    name = "ai-train-camp-uat-qwen3.7-plus-商业百炼"
    assert derive_model_from_name(name) == "ai-train-camp-uat-qwen3.7-plus"
    assert derive_group_from_name(name) == "ai-train-camp-uat"


def test_qwen37_plus_without_remark():
    assert derive_group_from_name("ai-train-camp-uat-qwen3.7-plus") == "ai-train-camp-uat"


def test_kimi_k3_chinese_remark():
    name = "ai-train-camp-uat-kimi-k3-商业百炼"
    assert derive_model_from_name(name) == "ai-train-camp-uat-kimi-k3"
    assert derive_group_from_name(name) == "ai-train-camp-uat"


def test_glm_with_env():
    assert derive_group_from_name("pv-agent-uat-glm-5.1") == "pv-agent-uat"
    assert derive_group_from_name("demo-alpha-test-glm-x") == "demo-alpha-test"


def test_group_cuts_at_env_with_business_segment():
    """环境与模型之间夹业务段时，分组仍截到 uat/test/prod。"""
    cases = [
        "efficiency-ai-uat-product-gpt5.6sol",
        "efficiency-ai-uat-project-gpt5.6sol",
        "efficiency-ai-uat-development-gpt5.6sol",
        "efficiency-ai-uat-agent-gpt5.6sol",
        "efficiency-ai-uat-large-model-gpt5.6sol",
    ]
    for name in cases:
        assert derive_group_from_name(name) == "efficiency-ai-uat", name


def test_env_not_confused_with_product_or_development():
    """product / development 整词不误识别为 prod / dev。"""
    assert derive_group_from_name("demo-x-prod-gpt-4o") == "demo-x-prod"
    assert derive_group_from_name("demo-x-dev-gpt-4o") == "demo-x-dev"


def test_extract_line_group():
    from lib.channel_extractor import extract_channels

    text = (
        "ai-train-camp-uat-qwen3.7-plus-商业百炼\n"
        "OpenAI\n"
        "qwen3.7-plus\n"
        "sk-ws-H.RPXPEDR.lkmn.MEUCIQDi4-EOf2Y6pz7Xoon4y5j_Z9F8M_BXIt25Cx8adFAJ9wIgP0rj9U9kUJCkPHOo6JRflbLh51GjLGMO8prqFEcA7Rs\n"
        "https://ws-b93y1kvf5ojnb71l.cn-beijing.maas.aliyuncs.com/compatible-mode"
    )
    result = extract_channels(text, use_llm=False)
    assert result.success is True
    assert result.fields.group == "ai-train-camp-uat"
    assert result.fields.model == "ai-train-camp-uat-qwen3.7-plus"
    assert "ai-train-camp-uat-qwen3.7-plus->qwen3.7-plus" in result.channel_line


if __name__ == "__main__":
    test_qwen37_plus_chinese_remark_group()
    test_qwen37_plus_without_remark()
    test_kimi_k3_chinese_remark()
    test_glm_with_env()
    test_group_cuts_at_env_with_business_segment()
    test_env_not_confused_with_product_or_development()
    test_extract_line_group()
    print("ok")
