"""LLM 增强真实调用行为测试。"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

AGENT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(AGENT_DIR))

from lib.channel_extractor import extract_channels, validate_llm_config  # noqa: E402
from lib.llm_agent import _merge_llm_into_fields  # noqa: E402
from lib.rule_extractor import ExtractedFields  # noqa: E402


def test_validate_llm_config_requires_base():
    err = validate_llm_config({"api_base": "", "api_key": "sk-x"})
    assert err and "API 地址" in err


def test_validate_llm_config_allows_ollama_without_key():
    assert validate_llm_config({
        "api_base": "http://127.0.0.1:11434/v1",
        "api_key": "",
        "provider": "ollama",
    }) is None


def test_use_llm_requires_configuration():
    result = extract_channels("ep-20260709112335-demo1\nark-demo-key", use_llm=True, llm_config={})
    assert not result.success
    assert result.mode == "llm_failed"
    assert not result.llm.configured


def test_merge_override_replaces_rule_field():
    fields = ExtractedFields(name="rule-name", type_label="OpenAI")
    filled = _merge_llm_into_fields(
        fields,
        {"name": "ai-name", "type_label": "自定义渠道", "upstream_model": "ep-1", "api_key": "sk-1"},
        override=True,
    )
    assert fields.name == "ai-name"
    assert fields.type_label == "自定义渠道"
    assert "name" in filled
    assert fields.sources["name"] == "llm:override"


@patch("lib.llm_agent.chat_completion")
def test_use_llm_invokes_real_api(mock_chat):
    mock_chat.return_value = (
        '{"name":"ai-channel","group":"ai","type_label":"字节火山方舟、豆包通用",'
        '"model":"ai-channel","upstream_model":"ep-20260709112335-demo1",'
        '"api_key":"ark-demo","base_url":"https://ark.cn-beijing.volces.com","api_version":""}'
    )
    result = extract_channels(
        "ep-20260709112335-demo1\nark-demo-key",
        use_llm=True,
        llm_config={
            "api_base": "https://api.xiaomimimo.com/v1",
            "api_key": "sk-test",
            "model": "mimo-v2.5-pro",
            "provider": "mimo",
        },
    )
    assert mock_chat.called
    assert result.llm.invoked
    assert result.llm.items_invoked == 1
    assert result.llm.items_succeeded == 1
    assert result.mode == "llm"
    assert result.items[0].fields.llm_invoked
    assert result.items[0].fields.llm_success


@patch("lib.llm_agent.chat_completion")
def test_use_llm_failure_is_reported(mock_chat):
    mock_chat.side_effect = RuntimeError("HTTP 401")
    result = extract_channels(
        "ep-20260709112335-demo1",
        use_llm=True,
        llm_config={
            "api_base": "https://api.xiaomimimo.com/v1",
            "api_key": "sk-test",
            "model": "mimo-v2.5-pro",
            "provider": "mimo",
        },
    )
    assert mock_chat.called
    assert not result.success
    assert result.mode == "llm_failed"
    assert result.llm.items_failed == 1
    assert result.items[0].fields.llm_error


def run():
    test_validate_llm_config_requires_base()
    test_validate_llm_config_allows_ollama_without_key()
    test_use_llm_requires_configuration()
    test_merge_override_replaces_rule_field()
    test_use_llm_invokes_real_api()
    test_use_llm_failure_is_reported()
    print("all llm enhance tests passed")


if __name__ == "__main__":
    run()
