"""LLM 客户端单元测试（无需网络）。"""

from __future__ import annotations

import sys
from pathlib import Path

AGENT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(AGENT_DIR))

from lib.llm_client import (  # noqa: E402
    build_chat_completions_url,
    detect_provider,
    is_llm_configured,
    list_provider_presets,
    normalize_api_base,
    resolve_provider,
    supports_json_mode,
)


def test_list_presets():
    presets = list_provider_presets()
    ids = {p["id"] for p in presets}
    assert "openai" in ids
    assert "ollama" in ids
    assert "mimo" in ids
    assert "custom" in ids


def test_detect_provider():
    assert detect_provider("https://api.deepseek.com/v1") == "deepseek"
    assert detect_provider("http://127.0.0.1:11434") == "ollama"
    assert detect_provider("https://dashscope.aliyuncs.com/compatible-mode/v1") == "dashscope"
    assert detect_provider("https://ark.cn-beijing.volces.com/api/v3") == "volcengine"
    assert detect_provider("https://open.bigmodel.cn/api/paas/v4") == "zhipu"
    assert detect_provider("https://api.xiaomimimo.com/v1") == "mimo"
    assert detect_provider("https://token-plan-cn.xiaomimimo.com/v1") == "mimo"


def test_normalize_api_base():
    assert normalize_api_base("https://api.openai.com", "openai") == "https://api.openai.com/v1"
    assert normalize_api_base("http://127.0.0.1:11434", "ollama") == "http://127.0.0.1:11434/v1"
    assert (
        normalize_api_base("https://ark.cn-beijing.volces.com", "volcengine")
        == "https://ark.cn-beijing.volces.com/api/v3"
    )
    assert (
        normalize_api_base("https://open.bigmodel.cn", "zhipu")
        == "https://open.bigmodel.cn/api/paas/v4"
    )
    assert (
        build_chat_completions_url("https://api.xiaomimimo.com/v1", "mimo")
        == "https://api.xiaomimimo.com/v1/chat/completions"
    )


def test_is_llm_configured():
    assert is_llm_configured({"api_base": "http://127.0.0.1:11434/v1", "api_key": "", "provider": "ollama"})
    assert not is_llm_configured({"api_base": "", "api_key": "sk-x"})
    assert not is_llm_configured({"api_base": "https://api.openai.com/v1", "api_key": ""})
    assert is_llm_configured({"api_base": "https://api.openai.com/v1", "api_key": "sk-test"})


def test_resolve_and_json_mode():
    assert resolve_provider("https://api.openai.com/v1", "deepseek") == "deepseek"
    assert supports_json_mode("ollama") is False
    assert supports_json_mode("openai") is True


def run():
    test_list_presets()
    test_detect_provider()
    test_normalize_api_base()
    test_is_llm_configured()
    test_resolve_and_json_mode()
    print("all llm_client tests passed")


if __name__ == "__main__":
    run()
