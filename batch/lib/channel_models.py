"""从渠道提取可用于令牌模型限制的模型名。"""

from __future__ import annotations

import json
from typing import Any


def _channel_groups(channel: dict[str, Any]) -> list[str]:
    raw = str(channel.get("group") or "").strip()
    if not raw:
        return []
    return [part.strip() for part in raw.split(",") if part.strip()]


def extract_channel_models(channel: dict[str, Any]) -> list[str]:
    """提取渠道对外模型名（models 字段 + 模型重定向左侧源模型）。"""
    models: set[str] = set()

    models_raw = str(channel.get("models") or "").strip()
    if models_raw:
        for part in models_raw.split(","):
            part = part.strip()
            if part:
                models.add(part)

    mapping_raw = channel.get("model_mapping")
    if mapping_raw:
        try:
            mapping = (
                json.loads(mapping_raw)
                if isinstance(mapping_raw, str)
                else mapping_raw
            )
            if isinstance(mapping, dict):
                for key in mapping:
                    key_text = str(key).strip()
                    if key_text:
                        models.add(key_text)
        except (json.JSONDecodeError, TypeError):
            pass

    return sorted(models)


def build_group_model_index(
    channels: list[dict[str, Any]],
) -> dict[str, set[str]]:
    """按分组汇总渠道可用模型。"""
    index: dict[str, set[str]] = {}
    for channel in channels:
        models = extract_channel_models(channel)
        if not models:
            continue
        for group in _channel_groups(channel):
            index.setdefault(group, set()).update(models)
    return index


def get_models_for_group(
    channels: list[dict[str, Any]], group: str
) -> set[str]:
    group = group.strip()
    if not group:
        return set()
    return set(build_group_model_index(channels).get(group, set()))


def serialize_group_model_index(
    index: dict[str, set[str]],
) -> dict[str, list[str]]:
    return {
        group: sorted(models)
        for group, models in sorted(index.items())
    }
