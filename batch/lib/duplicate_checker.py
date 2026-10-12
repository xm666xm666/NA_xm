"""批量导入重复校验（本站内：渠道名、模型名唯一）。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .channel_models import extract_channel_models


def channel_name_group(name: str, group: str) -> tuple[str, str]:
    """删除匹配仍按名称+分组。"""
    return name.strip(), group.strip()


def _row_name(row: dict[str, Any]) -> str:
    return str(row.get("名称") or row.get("name") or "").strip()


def _row_models(row: dict[str, Any]) -> list[str]:
    raw = ""
    for key in ("模型", "models", "model"):
        value = str(row.get(key) or "").strip()
        if value:
            raw = value
            break
    if not raw:
        return []
    models: list[str] = []
    seen: set[str] = set()
    for part in raw.split(","):
        part = part.strip()
        if part and part not in seen:
            seen.add(part)
            models.append(part)
    return models


@dataclass
class ChannelBatchSeen:
    names: set[str] = field(default_factory=set)
    models: set[str] = field(default_factory=set)


def is_batch_duplicate(row: dict[str, str], seen: ChannelBatchSeen) -> str | None:
    """批量文本内：渠道名或模型名与前面行重复则跳过（返回原因）。"""
    name = _row_name(row)
    models = _row_models(row)
    if name and name in seen.names:
        return f"已跳过：批量内渠道名重复（{name}）"
    for model in models:
        if model in seen.models:
            return f"已跳过：批量内模型名重复（{model}）"
    if name:
        seen.names.add(name)
    seen.models.update(models)
    return None


def find_existing_duplicate(
    row: dict[str, str],
    name_index: dict[str, dict[str, Any]],
    model_index: dict[str, dict[str, Any]],
) -> str | None:
    """与本站已有渠道比对：渠道名、模型名任一冲突则禁止创建。"""
    name = _row_name(row)
    models = _row_models(row)

    if name:
        matched = name_index.get(name)
        if matched:
            return (
                f"渠道名已存在：本站已有「{name}」"
                f"（ID={matched.get('id', '?')}），渠道名须全站唯一"
            )

    for model in models:
        matched = model_index.get(model)
        if matched:
            occupied = str(matched.get("name") or "").strip() or "?"
            return (
                f"模型名已存在：本站渠道「{occupied}」"
                f"（ID={matched.get('id', '?')}）已占用模型「{model}」，模型名须全站唯一"
            )
    return None


def build_existing_index(channels: list[dict[str, Any]]) -> dict[tuple[str, str], dict[str, Any]]:
    """名称+分组索引，供删除匹配使用。"""
    index: dict[tuple[str, str], dict[str, Any]] = {}
    for channel in channels:
        name = str(channel.get("name") or "").strip()
        group = str(channel.get("group") or "").strip()
        if not name:
            continue
        index[channel_name_group(name, group)] = channel
        for part in group.split(","):
            part = part.strip()
            if part:
                index[channel_name_group(name, part)] = channel
    return index


def build_name_index(channels: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    for channel in channels:
        name = str(channel.get("name") or "").strip()
        if name and name not in index:
            index[name] = channel
    return index


def build_model_index(channels: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    for channel in channels:
        for model in extract_channel_models(channel):
            if model and model not in index:
                index[model] = channel
    return index
