"""按上游模型 / 渠道类型 / ID 批量启用或禁用渠道。"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from typing import Any

from .api_client import NewAPIClient, authenticate_client
from .channel_batch_delete import parse_channel_delete_rows
from .channel_types import get_channel_types, resolve_channel_type
from .duplicate_checker import build_existing_index, channel_name_group

CHANNEL_STATUS_ENABLED = 1
CHANNEL_STATUS_MANUALLY_DISABLED = 2

ACTION_ENABLE = "enable"
ACTION_DISABLE = "disable"

MATCH_UPSTREAM = "upstream"
MATCH_TYPE = "type"
MATCH_IDS = "ids"
MATCH_NAME = "name"

_SPLIT_RE = re.compile(r"[\s,，;；]+")


@dataclass
class BatchStatusResult:
    total: int = 0
    matched_count: int = 0
    updated_count: int = 0
    skipped_count: int = 0
    failed_count: int = 0
    dry_run: bool = True
    action: str = ""
    target_status: int = 0
    channel_type: str = ""
    type_id: int = 0
    match_mode: str = MATCH_UPSTREAM
    models: list[str] = field(default_factory=list)
    items: list[dict[str, Any]] = field(default_factory=list)
    extra: dict[str, Any] = field(default_factory=dict)


def parse_model_list(text: str) -> list[str]:
    """解析模型列表：换行 / 逗号 / 空格分隔，去重保序。"""
    seen: set[str] = set()
    models: list[str] = []
    for raw_line in (text or "").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        for part in _SPLIT_RE.split(line):
            model = part.strip()
            if not model or model in seen:
                continue
            seen.add(model)
            models.append(model)
    return models


def extract_upstream_models(channel: dict[str, Any]) -> set[str]:
    """从 model_mapping 收集上游模型（映射右侧 values）。"""
    upstreams: set[str] = set()
    mapping_raw = channel.get("model_mapping")
    if not mapping_raw:
        return upstreams
    try:
        mapping = json.loads(mapping_raw) if isinstance(mapping_raw, str) else mapping_raw
    except (json.JSONDecodeError, TypeError):
        return upstreams
    if not isinstance(mapping, dict):
        return upstreams
    for value in mapping.values():
        text = str(value).strip()
        if text:
            upstreams.add(text)
    return upstreams


def _status_label(status: int) -> str:
    if status == CHANNEL_STATUS_ENABLED:
        return "已启用"
    if status == CHANNEL_STATUS_MANUALLY_DISABLED:
        return "手动禁用"
    if status == 3:
        return "自动禁用"
    return f"状态{status}"


def _resolve_action(action: str) -> tuple[str, int, str]:
    normalized = (action or "").strip().lower()
    if normalized in {ACTION_ENABLE, "启用", "1"}:
        return ACTION_ENABLE, CHANNEL_STATUS_ENABLED, "启用"
    if normalized in {ACTION_DISABLE, "禁用", "2"}:
        return ACTION_DISABLE, CHANNEL_STATUS_MANUALLY_DISABLED, "禁用"
    raise ValueError("action 须为 enable 或 disable")


def _resolve_match_mode(match_mode: str) -> str:
    normalized = (match_mode or MATCH_UPSTREAM).strip().lower()
    if normalized in {MATCH_UPSTREAM, "model", "models"}:
        return MATCH_UPSTREAM
    if normalized in {MATCH_TYPE, "all", "type_all"}:
        return MATCH_TYPE
    if normalized in {MATCH_IDS, "id", "channel_ids"}:
        return MATCH_IDS
    if normalized in {MATCH_NAME, "names", "name_group", "batch"}:
        return MATCH_NAME
    raise ValueError("match_mode 须为 upstream / type / ids / name")


def _parse_channel_ids(raw: Any) -> list[int]:
    ids: list[int] = []
    seen: set[int] = set()
    if raw is None:
        return ids
    if isinstance(raw, (int, float, str)):
        raw = [raw]
    if not isinstance(raw, list):
        return ids
    for item in raw:
        try:
            value = int(item)
        except (TypeError, ValueError):
            continue
        if value <= 0 or value in seen:
            continue
        seen.add(value)
        ids.append(value)
    return ids


def _channel_snapshot(channel: dict[str, Any]) -> dict[str, Any]:
    channel_id = int(channel.get("id") or 0)
    name = str(channel.get("name") or "").strip() or f"id-{channel_id}"
    group = str(channel.get("group") or "").strip()
    try:
        current_status = int(channel.get("status") or 0)
    except (TypeError, ValueError):
        current_status = 0
    upstreams = sorted(extract_upstream_models(channel))
    return {
        "target_id": channel_id,
        "name": name,
        "group": group,
        "current_status": current_status,
        "status_label": _status_label(current_status),
        "matched_upstreams": upstreams,
        "enabled": current_status == CHANNEL_STATUS_ENABLED,
    }


def run_channel_batch_status(
    *,
    base_url: str,
    auth: dict[str, Any],
    model_text: str = "",
    models: list[str] | None = None,
    channel_type: str = "",
    action: str,
    dry_run: bool = True,
    match_mode: str = MATCH_UPSTREAM,
    channel_ids: list[int] | None = None,
    batch_text: str = "",
) -> BatchStatusResult:
    mode = _resolve_match_mode(match_mode)
    if mode == MATCH_NAME:
        return _run_channel_status_by_name(
            base_url=base_url,
            auth=auth,
            batch_text=batch_text,
            action=action,
            dry_run=dry_run,
        )
    model_list = list(models) if models else parse_model_list(model_text)
    id_list = _parse_channel_ids(channel_ids)

    if mode == MATCH_UPSTREAM and not model_list:
        raise ValueError("请填写至少一个上游模型")
    if mode == MATCH_IDS and not id_list:
        raise ValueError("请指定至少一个渠道 ID")
    if mode != MATCH_IDS and not str(channel_type or "").strip():
        raise ValueError("请指定渠道类型（默认：自定义渠道）")

    action_id, target_status, action_label = _resolve_action(action)
    types, _source = get_channel_types(base_url)
    type_id = 0
    type_label = ""
    if mode != MATCH_IDS or str(channel_type or "").strip():
        if str(channel_type or "").strip():
            type_id = resolve_channel_type(channel_type, types)
            type_label = next(
                (str(item["label"]) for item in types if int(item["value"]) == type_id),
                str(channel_type).strip(),
            )

    client = NewAPIClient(base_url)
    authenticate_client(client, auth)
    client.get_status()

    existing = client.list_all_channels()
    wanted_models = set(model_list)
    wanted_ids = set(id_list)

    result = BatchStatusResult(
        total=len(id_list) if mode == MATCH_IDS else (len(model_list) if mode == MATCH_UPSTREAM else 0),
        dry_run=dry_run,
        action=action_id,
        target_status=target_status,
        channel_type=type_label,
        type_id=type_id,
        match_mode=mode,
        models=model_list,
    )
    result.extra = {
        "action": action_id,
        "target_status": target_status,
        "channel_type": type_label,
        "type_id": type_id,
        "match_mode": mode,
        "models": model_list,
        "channel_ids": id_list,
    }

    to_update: list[dict[str, Any]] = []
    index_no = 0

    for channel in existing:
        snap = _channel_snapshot(channel)
        channel_id = snap["target_id"]
        if channel_id <= 0:
            continue

        try:
            ch_type = int(channel.get("type") or 0)
        except (TypeError, ValueError):
            continue

        hit: list[str] = []
        if mode == MATCH_IDS:
            if channel_id not in wanted_ids:
                continue
            if type_id and ch_type != type_id:
                continue
            hit = snap["matched_upstreams"]
        elif mode == MATCH_TYPE:
            if ch_type != type_id:
                continue
            hit = snap["matched_upstreams"]
        else:
            if ch_type != type_id:
                continue
            upstreams = set(snap["matched_upstreams"])
            hit = sorted(upstreams & wanted_models)
            if not hit:
                continue

        index_no += 1
        current_status = snap["current_status"]
        result.matched_count += 1
        already_target = current_status == target_status
        item = {
            "index": index_no,
            "name": snap["name"],
            "group": snap["group"],
            "success": True,
            "preview": dry_run,
            "target_id": channel_id,
            "current_status": current_status,
            "status_label": snap["status_label"],
            "enabled": snap["enabled"],
            "target_status": target_status,
            "matched_upstreams": hit,
            "skipped": already_target,
            "message": (
                f"已是目标状态（{snap['status_label']}），将跳过"
                if already_target
                else (
                    f"{'将' if dry_run else '已'}{action_label}渠道 ID={channel_id}"
                    f"（{snap['name']} / {snap['group'] or '-'}）"
                    + (f"，上游: {', '.join(hit)}" if hit else "")
                    + f"；当前{snap['status_label']}"
                )
            ),
        }
        result.items.append(item)
        if already_target:
            result.skipped_count += 1
        else:
            to_update.append(item)

    if mode == MATCH_TYPE:
        result.total = result.matched_count

    if dry_run or not to_update:
        return result

    for index, item in enumerate(to_update):
        if index > 0:
            # 降低连续 PUT 触发网关限流概率
            time.sleep(0.08)
        channel_id = int(item["target_id"])
        try:
            client.update_channel_status(channel_id, target_status)
            result.updated_count += 1
            item["preview"] = False
            item["current_status"] = target_status
            item["status_label"] = _status_label(target_status)
            item["enabled"] = target_status == CHANNEL_STATUS_ENABLED
            item["skipped"] = False
            item["message"] = (
                f"已{action_label}渠道 ID={channel_id}"
                f"（{item['name']} / {item.get('group') or '-'}）"
                + (
                    f"，上游: {', '.join(item.get('matched_upstreams') or [])}"
                    if item.get("matched_upstreams")
                    else ""
                )
            )
        except Exception as exc:  # noqa: BLE001
            result.failed_count += 1
            item["success"] = False
            item["preview"] = False
            item["message"] = f"{action_label}失败: {exc}"

    return result


def _run_channel_status_by_name(
    *,
    base_url: str,
    auth: dict[str, Any],
    batch_text: str,
    action: str,
    dry_run: bool,
) -> BatchStatusResult:
    rows = parse_channel_delete_rows(batch_text)
    if not rows:
        raise ValueError("没有可处理的批量数据")

    action_id, target_status, action_label = _resolve_action(action)
    client = NewAPIClient(base_url)
    authenticate_client(client, auth)
    client.get_status()

    existing = client.list_all_channels()
    index = build_existing_index(existing)
    seen_pairs: set[tuple[str, str]] = set()
    result = BatchStatusResult(
        total=len(rows),
        dry_run=dry_run,
        action=action_id,
        target_status=target_status,
        match_mode=MATCH_NAME,
    )
    result.extra = {
        "action": action_id,
        "target_status": target_status,
        "match_mode": MATCH_NAME,
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

        pair = channel_name_group(name, group)
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
                    "message": f"未找到匹配渠道（{name} / {group}）",
                }
            )
            continue

        snap = _channel_snapshot(matched)
        channel_id = snap["target_id"]
        result.matched_count += 1
        already_target = snap["current_status"] == target_status
        item = {
            "index": index_no,
            "name": snap["name"],
            "group": snap["group"],
            "success": True,
            "preview": dry_run,
            "target_id": channel_id,
            "current_status": snap["current_status"],
            "status_label": snap["status_label"],
            "enabled": snap["enabled"],
            "target_status": target_status,
            "skipped": already_target,
            "message": (
                f"已是目标状态（{snap['status_label']}），将跳过"
                if already_target
                else (
                    f"{'将' if dry_run else '已'}{action_label}渠道 ID={channel_id}"
                    f"（{snap['name']} / {snap['group'] or '-'}）；当前{snap['status_label']}"
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
        channel_id = int(item["target_id"])
        try:
            client.update_channel_status(channel_id, target_status)
            result.updated_count += 1
            item["preview"] = False
            item["current_status"] = target_status
            item["status_label"] = _status_label(target_status)
            item["enabled"] = target_status == CHANNEL_STATUS_ENABLED
            item["skipped"] = False
            item["message"] = (
                f"已{action_label}渠道 ID={channel_id}"
                f"（{item['name']} / {item.get('group') or '-'}）"
            )
        except Exception as exc:  # noqa: BLE001
            result.failed_count += 1
            item["success"] = False
            item["preview"] = False
            item["message"] = f"{action_label}失败: {exc}"

    return result

