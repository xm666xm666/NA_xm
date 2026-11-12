"""智能体渠道创建只读预检，不调用任何网关写入接口。"""

from __future__ import annotations

import json
from typing import Any

from .api_client import NewAPIClient, authenticate_client
from .channel_builder import (
    DEFAULT_VOLCANO_BASE_URL,
    KEY_KEYS,
    MODEL_KEYS,
    TYPE_KEYS,
    build_channel_payload,
    is_volcano_channel_type,
    parse_batch_rows,
    pick_row_value,
)
from .channel_types import get_channel_types, resolve_channel_type
from .duplicate_checker import (
    ChannelBatchSeen,
    build_model_index,
    build_name_index,
    find_existing_duplicate,
    is_batch_duplicate,
)


def _models(row: dict[str, Any]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for part in pick_row_value(row, MODEL_KEYS).replace("，", ",").split(","):
        model = part.strip()
        if model and model not in seen:
            seen.add(model)
            result.append(model)
    return result


def _parse_lines(batch_text: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    parsed_rows: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    for source_line, raw_line in enumerate(str(batch_text or "").splitlines(), start=1):
        if not raw_line.strip():
            continue
        try:
            rows = parse_batch_rows(raw_line)
            if not rows:
                continue
            for row in rows:
                parsed_rows.append({"row": row, "source_line": source_line})
        except Exception as exc:
            errors.append(
                {
                    "source_line": source_line,
                    "action": "error",
                    "name": f"第 {source_line} 行",
                    "reason": str(exc),
                    "fields": {},
                    "changes": [],
                }
            )
    return parsed_rows, errors


def _base_item(row: dict[str, Any], source_line: int) -> dict[str, Any]:
    return {
        "source_line": source_line,
        "name": str(row.get("名称") or row.get("name") or f"第 {source_line} 行").strip(),
        "group": str(row.get("分组") or row.get("group") or "").strip(),
        "models": _models(row),
        "fields": {},
        "changes": [],
    }


def run_agent_preflight(
    *,
    base_url: str,
    batch_text: str,
    default_key: str,
    auth: dict[str, Any],
) -> dict[str, Any]:
    parsed_rows, items = _parse_lines(batch_text)
    if not parsed_rows:
        if not items:
            raise ValueError("没有可预检的渠道数据")
        return {
            "total": len(items),
            "create_count": 0,
            "skip_count": 0,
            "error_count": len(items),
            "groups_to_create": [],
            "items": sorted(items, key=lambda item: item["source_line"]),
            "type_source": "",
            "existing_channel_count": 0,
            "read_only": True,
        }

    types, type_source = get_channel_types(base_url)
    client = NewAPIClient(base_url)
    authenticate_client(client, auth)
    client.get_status()
    known_groups = set(client.list_groups())
    existing_channels = client.list_all_channels()
    name_index = build_name_index(existing_channels)
    model_index = build_model_index(existing_channels)
    batch_seen = ChannelBatchSeen()

    requested_groups = {
        str(item["row"].get("分组") or item["row"].get("group") or "").strip()
        for item in parsed_rows
    }
    requested_groups.discard("")
    groups_to_create = sorted(requested_groups - known_groups)
    simulated_groups = known_groups | requested_groups

    for parsed in parsed_rows:
        row = parsed["row"]
        source_line = int(parsed["source_line"])
        item = _base_item(row, source_line)
        try:
            duplicate = is_batch_duplicate(row, batch_seen)
            if duplicate:
                item.update(action="skip", reason=duplicate)
                items.append(item)
                continue
            existing_duplicate = find_existing_duplicate(row, name_index, model_index)
            if existing_duplicate:
                item.update(action="skip", reason=existing_duplicate)
                items.append(item)
                continue

            raw_type = pick_row_value(row, TYPE_KEYS)
            channel_type = resolve_channel_type(raw_type, types)
            payload = build_channel_payload(
                row,
                channel_type=channel_type,
                default_key=default_key,
                known_groups=simulated_groups,
            )
            channel = payload["channel"]
            model_mapping = json.loads(str(channel.get("model_mapping") or "{}"))
            group = str(channel.get("group") or "")
            changes = ["创建新渠道"]
            if group in groups_to_create:
                changes.append(f"自动创建分组「{group}」")
            raw_base_url = str(row.get("base_url") or row.get("BaseURL") or "").strip()
            if not raw_base_url and is_volcano_channel_type(channel_type):
                changes.append(f"Base URL 使用默认值 {DEFAULT_VOLCANO_BASE_URL}")
            item.update(
                action="create",
                reason="校验通过，可创建",
                type=channel_type,
                upstream_models=list(model_mapping.values()),
                base_url=str(channel.get("base_url") or ""),
                key_source="行内密钥" if pick_row_value(row, KEY_KEYS) else "默认密钥",
                fields={
                    "name": str(channel.get("name") or ""),
                    "group": group,
                    "type": channel_type,
                    "models": _models(row),
                    "base_url": str(channel.get("base_url") or ""),
                },
                changes=changes,
            )
        except Exception as exc:
            item.update(action="error", reason=str(exc))
        items.append(item)

    items.sort(key=lambda item: item["source_line"])
    create_count = sum(item.get("action") == "create" for item in items)
    skip_count = sum(item.get("action") == "skip" for item in items)
    error_count = sum(item.get("action") == "error" for item in items)
    return {
        "total": len(items),
        "create_count": create_count,
        "skip_count": skip_count,
        "error_count": error_count,
        "groups_to_create": groups_to_create,
        "items": items,
        "type_source": type_source,
        "existing_channel_count": len(existing_channels),
        "read_only": True,
    }
