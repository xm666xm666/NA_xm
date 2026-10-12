"""渠道类型注册表：标准名称、别名、默认 Base URL。"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class ChannelTypeInfo:
    label: str
    aliases: tuple[str, ...]
    base_url: str | None = None
    api_version_required: bool = False


# 与 old/channel_types.json 对齐；已知 Base URL 的类型在此配置
CHANNEL_TYPES: tuple[ChannelTypeInfo, ...] = (
    ChannelTypeInfo(
        label="字节火山方舟、豆包通用",
        aliases=(
            "字节火山方舟、豆包通用",
            "字节火山方舟",
            "火山方舟",
            "火山",
            "豆包",
            "豆包通用",
            "volcengine",
            "volces",
            "ark",
            "doubao",
        ),
        base_url="https://ark.cn-beijing.volces.com",
    ),
    ChannelTypeInfo(
        label="OpenAI",
        # 仅显式 OpenAI/openai 识别为 OpenAI；勿用 gpt 等短别名误匹配
        aliases=("openai",),
        base_url=None,
    ),
    ChannelTypeInfo(
        label="Azure OpenAI",
        aliases=("azure openai", "azure", "azure_openai"),
        base_url=None,
        api_version_required=True,
    ),
    ChannelTypeInfo(
        label="阿里通义千问",
        aliases=("通义", "千问", "qwen", "dashscope", "百炼"),
        base_url=None,
    ),
    ChannelTypeInfo(
        label="DeepSeek",
        aliases=("deepseek",),
        base_url=None,
    ),
    ChannelTypeInfo(
        label="智谱 GLM-4V",
        aliases=("智谱", "glm", "chatglm", "zhipu"),
        base_url=None,
    ),
    ChannelTypeInfo(
        label="自定义渠道",
        aliases=("自定义", "自定义渠道", "custom"),
        base_url=None,
    ),
)


AZURE_TYPE_LABEL = "Azure OpenAI"
OPENAI_TYPE_LABEL = "OpenAI"


def get_type_by_label(label: str) -> ChannelTypeInfo | None:
    normalized = (label or "").strip()
    for item in CHANNEL_TYPES:
        if item.label == normalized:
            return item
    return None


def resolve_type_hint(hint: str) -> ChannelTypeInfo | None:
    """根据用户零散描述匹配标准渠道类型。

    OpenAI / Azure 消歧：
    - 显式 OpenAI / openai → OpenAI
    - 含 Azure，或仅有 openai.azure.com 等语境且未写 OpenAI → Azure OpenAI
    """
    text = (hint or "").strip()
    if not text:
        return None

    normalized = text.lower()

    # OpenAI 必须显式写出，避免被 Azure / 自定义路径吞掉
    if normalized == "openai":
        return get_type_by_label(OPENAI_TYPE_LABEL)

    # 含 azure 优先 Azure（含 Azure OpenAI）
    if "azure" in normalized:
        return get_type_by_label(AZURE_TYPE_LABEL)

    best: ChannelTypeInfo | None = None
    best_score = 0

    for item in CHANNEL_TYPES:
        if item.label == "OpenAI":
            # 已在上方精确处理，避免子串误匹配
            continue
        for alias in item.aliases:
            alias_lower = alias.lower()
            if alias_lower == normalized or alias == text:
                return item

            # 短英文别名（如 glm）易与项目名混淆，要求独立出现
            if len(alias_lower) <= 4 and alias_lower.isascii():
                if not re.search(
                    rf"(?<![a-z0-9_-]){re.escape(alias_lower)}(?![a-z0-9_-])",
                    normalized,
                ):
                    continue
            elif alias_lower not in normalized and text not in alias:
                continue

            score = len(alias_lower)
            if alias in text:
                score += 10
            if score > best_score:
                best = item
                best_score = score

    return best


def get_azure_type() -> ChannelTypeInfo:
    info = get_type_by_label(AZURE_TYPE_LABEL)
    if info is None:
        raise RuntimeError(f"未配置 Azure 类型: {AZURE_TYPE_LABEL}")
    return info


def get_openai_type() -> ChannelTypeInfo:
    info = get_type_by_label(OPENAI_TYPE_LABEL)
    if info is None:
        raise RuntimeError(f"未配置 OpenAI 类型: {OPENAI_TYPE_LABEL}")
    return info


VOLCANO_TYPE_LABEL = "字节火山方舟、豆包通用"


def get_volcano_type() -> ChannelTypeInfo:
    info = get_type_by_label(VOLCANO_TYPE_LABEL)
    if info is None:
        raise RuntimeError(f"未配置火山类型: {VOLCANO_TYPE_LABEL}")
    return info


def all_type_labels() -> list[str]:
    return [item.label for item in CHANNEL_TYPES]
