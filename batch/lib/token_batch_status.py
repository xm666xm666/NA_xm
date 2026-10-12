"""按名称+分组批量启用或禁用令牌。"""

from __future__ import annotations

import time
from typing import Any

from .api_client import NewAPIClient, authenticate_client
from .channel_batch_status import (
    ACTION_DISABLE,
    ACTION_ENABLE,
    BatchStatusResult,
    _resolve_action,
)
from .token_batch_delete import parse_token_name_group_rows
from .token_duplicate_checker import build_existing_index, token_name_group

TOKEN_STATUS_ENABLED = 1
TOKEN_STATUS_DISABLED = 2


def _token_status_label(status: int) -> str:
    if status == TOKEN_STATUS_ENABLED:
        return "已启用"
    if status == TOKEN_STATUS_DISABLED:
        return "已禁用"
    if status == 3:
        return "已过期"
    if status == 4:
        return "额度用尽"
    return f"状态{status}"


def _token_status_int(token: dict[str, Any]) -> int:
    try:
        return int(token.get("status") or 0)
    except (TypeError, ValueError):
        return 0


def run_token_batch_status(
    *,
    base_url: str,
    batch_text: str,
    auth: dict[str, Any],
    action: str,
    dry_run: bool = True,
) -> BatchStatusResult:
    rows = parse_token_name_group_rows(batch_text)
    if not rows:
        raise ValueError("没有可处理的批量数据")

    action_id, target_status, action_label = _resolve_action(action)
    if action_id == ACTION_ENABLE:
        target_status = TOKEN_STATUS_ENABLED
    elif action_id == ACTION_DISABLE:
        target_status = TOKEN_STATUS_DISABLED

    client = NewAPIClient(base_url)
    authenticate_client(client, auth)
    client.get_status()

    existing = client.list_all_tokens()
    index = build_existing_index(existing)
    seen_pairs: set[tuple[str, str]] = set()
    result = BatchStatusResult(
        total=len(rows),
        dry_run=dry_run,
        action=action_id,
        target_status=target_status,
        match_mode="name",
    )
    result.extra = {
        "action": action_id,
        "target_status": target_status,
        "match_mode": "name",
    }
    to_update: list[dict[str, Any]] = []

    for index_no, row in enumerate(rows, start=1):
        name = str(row.get("名称") or "").strip()
        group = str(row.get("分组") or "").strip()
        if not name or not group:
            result.failed_count += 1
            result.items.append(
                {
                    "index": index_no,
                    "name": name or f"row-{index_no}",
                    "success": False,
                    "message": "名称或分组不能为空",
                }
            )
            continue

        pair = token_name_group(name, group)
        if pair in seen_pairs:
            result.skipped_count += 1
            result.items.append(
                {
                    "index": index_no,
                    "name": name,
                    "group": group,
                    "success": True,
                    "skipped": True,
                    "message": "批量内重复，已跳过",
                }
            )
            continue
        seen_pairs.add(pair)

        matched = index.get(pair)
        if not matched or matched.get("id") is None:
            result.skipped_count += 1
            result.items.append(
                {
                    "index": index_no,
                    "name": name,
                    "group": group,
                    "success": True,
                    "skipped": True,
                    "message": f"未找到匹配令牌（{name} / {group}）",
                }
            )
            continue

        token_id = int(matched["id"])
        current_status = _token_status_int(matched)
        status_label = _token_status_label(current_status)
        result.matched_count += 1
        already_target = current_status == target_status
        item = {
            "index": index_no,
            "name": name,
            "group": group,
            "success": True,
            "preview": dry_run,
            "target_id": token_id,
            "current_status": current_status,
            "status_label": status_label,
            "enabled": current_status == TOKEN_STATUS_ENABLED,
            "target_status": target_status,
            "skipped": already_target,
            "message": (
                f"已是目标状态（{status_label}），将跳过"
                if already_target
                else (
                    f"{'将' if dry_run else '已'}{action_label}令牌 ID={token_id}"
                    f"（{name} / {group}）；当前{status_label}"
                )
            ),
        }
        result.items.append(item)
        if already_target:
            result.skipped_count += 1
        else:
            to_update.append(item)

    if dry_run or not to_update:
        return result

    for pos, item in enumerate(to_update):
        if pos > 0:
            time.sleep(0.08)
        token_id = int(item["target_id"])
        try:
            client.update_token_status(token_id, target_status)
            result.updated_count += 1
            item["preview"] = False
            item["current_status"] = target_status
            item["status_label"] = _token_status_label(target_status)
            item["enabled"] = target_status == TOKEN_STATUS_ENABLED
            item["skipped"] = False
            item["message"] = (
                f"已{action_label}令牌 ID={token_id}"
                f"（{item['name']} / {item.get('group') or '-'}）"
            )
        except Exception as exc:  # noqa: BLE001
            result.failed_count += 1
            item["success"] = False
            item["preview"] = False
            item["message"] = f"{action_label}失败: {exc}"

    return result
