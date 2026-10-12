"""LLM 多厂商客户端：Ollama、OpenAI 及主流 OpenAI 兼容 API。"""

from __future__ import annotations

import json
import re
from typing import Any
from urllib.parse import urlparse

import requests

# 预设：label 用于 UI 展示
LLM_PROVIDER_PRESETS: dict[str, dict[str, Any]] = {
    "openai": {
        "label": "OpenAI",
        "api_base": "https://api.openai.com/v1",
        "model": "gpt-4o-mini",
        "api_key_required": True,
        "json_mode": True,
    },
    "deepseek": {
        "label": "DeepSeek",
        "api_base": "https://api.deepseek.com/v1",
        "model": "deepseek-chat",
        "api_key_required": True,
        "json_mode": True,
    },
    "dashscope": {
        "label": "阿里云百炼（DashScope 兼容）",
        "api_base": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "model": "qwen-plus",
        "api_key_required": True,
        "json_mode": True,
    },
    "volcengine": {
        "label": "火山方舟（豆包）",
        "api_base": "https://ark.cn-beijing.volces.com/api/v3",
        "model": "doubao-1-5-pro-32k",
        "api_key_required": True,
        "json_mode": True,
    },
    "zhipu": {
        "label": "智谱 AI",
        "api_base": "https://open.bigmodel.cn/api/paas/v4",
        "model": "glm-4-flash",
        "api_key_required": True,
        "json_mode": True,
    },
    "moonshot": {
        "label": "Moonshot / Kimi",
        "api_base": "https://api.moonshot.cn/v1",
        "model": "moonshot-v1-8k",
        "api_key_required": True,
        "json_mode": True,
    },
    "siliconflow": {
        "label": "硅基流动",
        "api_base": "https://api.siliconflow.cn/v1",
        "model": "deepseek-ai/DeepSeek-V3",
        "api_key_required": True,
        "json_mode": True,
    },
    "mimo": {
        "label": "小米 MiMo",
        "api_base": "https://api.xiaomimimo.com/v1",
        "model": "mimo-v2.5-pro",
        "api_key_required": True,
        "json_mode": True,
    },
    "ollama": {
        "label": "Ollama（本地）",
        "api_base": "http://127.0.0.1:11434/v1",
        "model": "llama3.2",
        "api_key_required": False,
        "json_mode": False,
    },
    "custom": {
        "label": "自定义 OpenAI 兼容",
        "api_base": "",
        "model": "gpt-4o-mini",
        "api_key_required": True,
        "json_mode": True,
    },
}


def list_provider_presets() -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for key, preset in LLM_PROVIDER_PRESETS.items():
        items.append(
            {
                "id": key,
                "label": preset["label"],
                "api_base": preset["api_base"],
                "model": preset["model"],
                "api_key_required": bool(preset.get("api_key_required", True)),
                "json_mode": bool(preset.get("json_mode", True)),
            }
        )
    return items


def detect_provider(api_base: str) -> str:
    text = (api_base or "").strip().lower()
    if not text:
        return "custom"
    if "11434" in text or "ollama" in text:
        return "ollama"
    if "deepseek.com" in text:
        return "deepseek"
    if "dashscope.aliyuncs.com" in text:
        return "dashscope"
    if "volces.com" in text or "volcengine" in text:
        return "volcengine"
    if "bigmodel.cn" in text or "zhipu" in text:
        return "zhipu"
    if "moonshot.cn" in text or "kimi" in text:
        return "moonshot"
    if "siliconflow.cn" in text:
        return "siliconflow"
    if "xiaomimimo.com" in text or "mimo.mi.com" in text:
        return "mimo"
    if "openai.com" in text:
        return "openai"
    return "custom"


def resolve_provider(api_base: str, provider: str = "") -> str:
    explicit = (provider or "").strip().lower()
    if explicit and explicit in LLM_PROVIDER_PRESETS:
        return explicit
    return detect_provider(api_base)


def provider_allows_empty_key(provider: str) -> bool:
    preset = LLM_PROVIDER_PRESETS.get(provider) or LLM_PROVIDER_PRESETS["custom"]
    return not bool(preset.get("api_key_required", True))


def is_llm_configured(llm_config: dict[str, Any] | None) -> bool:
    cfg = llm_config or {}
    api_base = str(cfg.get("api_base") or "").strip()
    if not api_base:
        return False
    provider = resolve_provider(api_base, str(cfg.get("provider") or ""))
    api_key = str(cfg.get("api_key") or "").strip()
    if api_key:
        return True
    return provider_allows_empty_key(provider)


def normalize_api_base(api_base: str, provider: str = "") -> str:
    text = (api_base or "").strip().rstrip("/")
    if not text:
        return ""

    if not text.lower().startswith(("http://", "https://")):
        text = f"http://{text}"

    provider = resolve_provider(text, provider)
    if text.endswith("/chat/completions"):
        return text[: -len("/chat/completions")].rstrip("/")

    if provider == "ollama":
        parsed = urlparse(text)
        if parsed.port == 11434 or parsed.hostname in {"127.0.0.1", "localhost"}:
            if not text.endswith("/v1"):
                text = f"{text}/v1"
        elif "/v1" not in text:
            text = f"{text}/v1"
        return text.rstrip("/")

    if provider == "volcengine" and "/api/v3" not in text:
        return f"{text}/api/v3".rstrip("/")

    if provider == "zhipu" and "/paas/v4" not in text:
        if text.endswith("/api"):
            return f"{text}/paas/v4"
        return f"{text}/api/paas/v4"

    # OpenAI 兼容：仅 host 时补 /v1
    parsed = urlparse(text)
    if parsed.path in ("", "/"):
        return f"{text}/v1"

    return text.rstrip("/")


def build_chat_completions_url(api_base: str, provider: str = "") -> str:
    base = normalize_api_base(api_base, provider)
    if not base:
        return ""
    if base.endswith("/chat/completions"):
        return base
    return f"{base}/chat/completions"


def supports_json_mode(provider: str) -> bool:
    preset = LLM_PROVIDER_PRESETS.get(provider) or LLM_PROVIDER_PRESETS["custom"]
    return bool(preset.get("json_mode", True))


def build_headers(api_key: str, provider: str) -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    key = (api_key or "").strip()
    if key:
        bare = key[7:].strip() if key.lower().startswith("bearer ") else key
        if provider == "mimo":
            # MiMo 官方文档同时支持 api-key 与 Bearer
            headers["api-key"] = bare
        headers["Authorization"] = f"Bearer {bare}"
    elif provider == "ollama":
        # Ollama OpenAI 兼容模式通常无需密钥
        pass
    return headers


def _post_chat(
    *,
    url: str,
    headers: dict[str, str],
    payload: dict[str, Any],
    timeout: int,
) -> dict[str, Any]:
    resp = requests.post(url, headers=headers, json=payload, timeout=timeout)
    resp.raise_for_status()
    body = resp.json()
    if not isinstance(body, dict):
        raise RuntimeError("LLM 响应格式无效")
    return body


def _extract_message_content(body: dict[str, Any]) -> str:
    choices = body.get("choices") or []
    if not choices:
        raise RuntimeError("LLM 响应缺少 choices")
    message = choices[0].get("message") or {}
    content = message.get("content")
    if content is None:
        raise RuntimeError("LLM 响应缺少 message.content")
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                parts.append(str(item.get("text") or ""))
        content = "".join(parts)
    return str(content).strip()


def chat_completion(
    *,
    api_base: str,
    api_key: str,
    model: str,
    messages: list[dict[str, str]],
    timeout: int = 60,
    provider: str = "",
    temperature: float = 0.1,
    prefer_json: bool = True,
) -> str:
    provider = resolve_provider(api_base, provider)
    if not is_llm_configured({"api_base": api_base, "api_key": api_key, "provider": provider}):
        raise RuntimeError("LLM 未配置：请填写 API 地址" + (" 与 API Key" if not provider_allows_empty_key(provider) else ""))

    url = build_chat_completions_url(api_base, provider)
    headers = build_headers(api_key, provider)
    base_payload: dict[str, Any] = {
        "model": model,
        "temperature": temperature,
        "messages": messages,
        "stream": False,
    }

    errors: list[str] = []
    attempts: list[dict[str, Any]] = []
    if prefer_json and supports_json_mode(provider):
        attempts.append({**base_payload, "response_format": {"type": "json_object"}})
    attempts.append(dict(base_payload))

    last_exc: Exception | None = None
    for payload in attempts:
        try:
            body = _post_chat(url=url, headers=headers, payload=payload, timeout=timeout)
            return _extract_message_content(body)
        except requests.HTTPError as exc:
            detail = ""
            try:
                detail = exc.response.text[:300] if exc.response is not None else ""
            except Exception:  # noqa: BLE001
                detail = ""
            errors.append(f"HTTP {getattr(exc.response, 'status_code', '?')}: {detail or exc}")
            last_exc = exc
            # json_mode 失败则尝试下一次（无 response_format）
            if "response_format" in payload:
                continue
            raise RuntimeError(errors[-1]) from exc
        except Exception as exc:  # noqa: BLE001
            errors.append(str(exc))
            last_exc = exc
            if "response_format" in payload:
                continue
            raise

    if last_exc:
        raise RuntimeError(errors[-1] if errors else str(last_exc)) from last_exc
    raise RuntimeError("LLM 调用失败")
