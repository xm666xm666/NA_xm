"""批量创建渠道处理器。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .api_client import NewAPIClient, authenticate_client
from .channel_builder import build_channel_payload, parse_batch_rows, pick_row_value, TYPE_KEYS, MODEL_KEYS, ensure_batch_keys_available
from .channel_models import extract_channel_models
from .channel_types import get_channel_types, resolve_channel_type
from .duplicate_checker import (
    ChannelBatchSeen,
    build_model_index,
    build_name_index,
    find_existing_duplicate,
    is_batch_duplicate,
)
from .group_manager import ensure_groups_for_rows


@dataclass
class BatchResult:
    total: int = 0
    success_count: int = 0
    failed_count: int = 0
    skipped_count: int = 0
    items: list[dict[str, Any]] = field(default_factory=list)


def _row_models(row: dict[str, Any]) -> list[str]:
    raw = pick_row_value(row, MODEL_KEYS)
    seen: set[str] = set()
    models: list[str] = []
    for part in str(raw or "").replace("，", ",").split(","):
        name = part.strip()
        if name and name not in seen:
            seen.add(name)
            models.append(name)
    return models


def _attach_created_channel_refs(client: NewAPIClient, result: BatchResult) -> None:
    pending = [
        item
        for item in result.items
        if item.get("success") and not item.get("skipped") and not item.get("meta")
    ]
    if not pending:
        return
    try:
        latest = client.list_all_channels()
    except Exception:  # noqa: BLE001
        return
    by_name = build_name_index(latest)
    for item in pending:
        found = by_name.get(str(item.get("name") or "").strip())
        if not found:
            continue
        item["channel_id"] = int(found.get("id") or 0)
        models = extract_channel_models(found)
        if models:
            item["models"] = models


def run_batch_create(
    *,
    base_url: str,
    batch_text: str,
    default_key: str,
    auth: dict[str, Any],
) -> BatchResult:
    rows = parse_batch_rows(batch_text)
    if not rows:
        raise ValueError("没有可处理的批量数据，请直接粘贴数据行（无需表头）")

    ensure_batch_keys_available(rows, default_key)

    types, type_source = get_channel_types(base_url)
    client = NewAPIClient(base_url)
    authenticate_client(client, auth)

    client.get_status()
    known_groups = set(client.list_groups())
    created_groups = ensure_groups_for_rows(
        client, rows, known_groups=known_groups
    )
    if not known_groups:
        raise ValueError("未能从站点获取分组列表，请确认管理员权限")

    existing_channels = client.list_all_channels()
    name_index = build_name_index(existing_channels)
    model_index = build_model_index(existing_channels)
    batch_seen = ChannelBatchSeen()

    result = BatchResult(total=len(rows))
    for index, row in enumerate(rows, start=1):
        name = row.get("名称") or row.get("name") or f"row-{index}"
        try:
            skip_reason = is_batch_duplicate(row, batch_seen)
            if skip_reason:
                result.skipped_count += 1
                result.items.append(
                    {
                        "index": index,
                        "name": name,
                        "success": True,
                        "skipped": True,
                        "message": skip_reason,
                    }
                )
                continue

            dup_existing = find_existing_duplicate(row, name_index, model_index)
            if dup_existing:
                raise ValueError(dup_existing)

            channel_type = resolve_channel_type(pick_row_value(row, TYPE_KEYS), types)
            payload = build_channel_payload(
                row,
                channel_type=channel_type,
                default_key=default_key,
                known_groups=known_groups,
            )
            response = client.create_channel(payload)
            message = response.get("message") or "创建成功"
            group = str(row.get("分组") or row.get("group") or "").strip()
            if group in created_groups:
                message = f"已自动创建分组「{group}」；{message}"
            result.success_count += 1
            result.items.append(
                {
                    "index": index,
                    "name": name,
                    "success": True,
                    "message": message,
                    "models": _row_models(row),
                }
            )
        except Exception as exc:  # noqa: BLE001
            result.failed_count += 1
            result.items.append(
                {
                    "index": index,
                    "name": name,
                    "success": False,
                    "message": str(exc),
                }
            )

    _attach_created_channel_refs(client, result)
    result.items.insert(
        0,
        {
            "meta": True,
            "type_source": type_source,
            "type_count": len(types),
            "groups": sorted(known_groups),
            "existing_channel_count": len(existing_channels),
        },
    )
    return result
