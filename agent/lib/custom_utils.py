"""自定义渠道解析。"""

from __future__ import annotations

import re

from .azure_utils import is_azure_host
from .patterns import MODEL_MAPPING_RE, PATH_MODEL_RE, SK_KEY_RE, URL_RE
from .type_registry import get_type_by_label, resolve_type_hint

CUSTOM_TYPE_LABEL = "自定义渠道"

# 上游部署模型：glm-5.1、gpt-4o、kimi-k3，以及 Azure embedding / whisper 等
DEPLOY_MODEL_RE = re.compile(
    r"^(?:"
    r"(?:gpt|glm|qwen|deepseek|claude|doubao|kimi)"
    r"(?:[-.][a-zA-Z]*\d[\w.-]*|[-.]?\d[\w.-]*)"
    r"|text-embedding(?:-[\w.]+)+"
    r"|text-ada-\d+"
    r"|embedding(?:-[\w.]+)+"
    r"|whisper(?:-[\w.]+)*"
    r"|dall-e(?:-[\w.]+)*"
    r"|tts(?:-[\w.]+)*"
    r"|o[1-9](?:-[\w.]+)*"
    r")$",
    re.IGNORECASE,
)


def get_custom_type():
    info = get_type_by_label(CUSTOM_TYPE_LABEL)
    if info is None:
        raise RuntimeError(f"未配置自定义渠道类型: {CUSTOM_TYPE_LABEL}")
    return info


def normalize_deploy_model(name: str) -> str:
    """glm5.1 -> glm-5.1"""
    text = (name or "").strip()
    if not text:
        return ""
    match = re.match(r"^(glm|gpt|qwen|deepseek|claude|doubao|kimi)(\d[\w.]*)$", text, re.I)
    if match:
        return f"{match.group(1).lower()}-{match.group(2)}"
    return text


def find_custom_url(lines: list[str]) -> str:
    for line in lines:
        match = URL_RE.search(line)
        if not match:
            continue
        url = match.group(0)
        if is_azure_host(url):
            continue
        if "volces.com" in url.lower() or "ark.cn-beijing" in url.lower():
            continue
        return url
    return ""


def _explicit_type_hint(lines: list[str]):
    """块内显式类型行（跳过渠道名，避免名称中「百炼」等被误匹配）。"""
    from .patterns import PROJECT_NAME_RE

    for line in lines:
        stripped = line.strip()
        if not stripped or PROJECT_NAME_RE.match(stripped):
            continue
        hint = resolve_type_hint(stripped)
        if hint:
            return hint
    return None


def is_custom_channel_block(lines: list[str]) -> bool:
    """sk + 非 Azure/火山 URL 且无 ep- 时推断自定义；显式非自定义类型优先。"""
    joined = "\n".join(lines)
    explicit = _explicit_type_hint(lines)
    if explicit and explicit.label != CUSTOM_TYPE_LABEL:
        return False

    if find_custom_url(lines) and SK_KEY_RE.search(joined):
        if explicit and explicit.label == CUSTOM_TYPE_LABEL:
            return True
        # sk + 非 Azure/火山 URL 且无 ep-，视为自定义
        from .patterns import EP_MODEL_RE

        if not EP_MODEL_RE.search(joined):
            return True
    if explicit and explicit.label == CUSTOM_TYPE_LABEL:
        return bool(find_custom_url(lines) and SK_KEY_RE.search(joined))
    return False


def is_deploy_model_name(value: str) -> bool:
    stripped = (value or "").strip()
    if not stripped:
        return False
    if DEPLOY_MODEL_RE.match(stripped):
        return True
    normalized = normalize_deploy_model(stripped)
    return bool(normalized != stripped and DEPLOY_MODEL_RE.match(normalized))


def pick_model_mapping(lines: list[str], channel_name: str = "") -> tuple[str, str]:
    """解析 源模型->上游模型 映射行（如 NA 渠道表粘贴）。"""
    name = (channel_name or "").strip()
    fallback = ""
    for line in lines:
        stripped = line.strip()
        match = MODEL_MAPPING_RE.match(stripped)
        if not match:
            continue
        source, upstream = match.group(1).strip(), match.group(2).strip()
        if not upstream:
            continue
        if name and source == name:
            return upstream, "rule:model_mapping"
        if not fallback:
            fallback = upstream
    if fallback:
        return fallback, "rule:model_mapping"
    return "", ""


def pick_deploy_model(lines: list[str], channel_name: str) -> tuple[str, str]:
    upstream, src = pick_model_mapping(lines, channel_name)
    if upstream:
        return normalize_deploy_model(upstream), src

    for line in lines:
        stripped = line.strip()
        if stripped == channel_name:
            continue
        if PATH_MODEL_RE.match(stripped):
            value = stripped if stripped.startswith("/") else f"/{stripped}"
            return value, "rule:path_model"
        if is_deploy_model_name(stripped):
            return normalize_deploy_model(stripped), "rule:deploy_model"
    return "", ""


def pick_custom_fields(lines: list[str], channel_name: str) -> dict[str, tuple[str, str]]:
    raw_url = find_custom_url(lines)
    if not raw_url:
        return {}

    type_info = get_custom_type()
    api_key = ""
    key_src = ""
    for line in lines:
        match = SK_KEY_RE.search(line)
        if match:
            api_key = match.group(0)
            key_src = "rule:sk_key"
            break

    upstream, upstream_src = pick_deploy_model(lines, channel_name)
    base_url = raw_url.rstrip("/")

    return {
        "type_label": (type_info.label, "rule:custom_inferred"),
        "type_info": (type_info, "rule:custom_inferred"),
        "base_url": (base_url, "rule:custom_url"),
        "api_key": (api_key, key_src),
        "upstream_model": (upstream, upstream_src),
        "api_version": ("", ""),
    }
