"""按名称+分组匹配已有渠道，更新模型 / 上游映射等原配置。

用于火山方舟、豆包等上游自动升级后，在收到升级申请单时同步网关登记。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from .api_client import NewAPIClient, authenticate_client
from .channel_builder import (
    MODEL_KEYS,
    TYPE_KEYS,
    build_channel_payload,
    parse_batch_rows,
    pick_row_value,
    split_channel_rename,
)
from .channel_models import extract_channel_models
from .channel_types import get_channel_types, resolve_channel_type
from .duplicate_checker import build_existing_index, build_model_index, build_name_index, channel_name_group


@dataclass
class BatchUpdateResult:
    total: int = 0
    matched_count: int = 0
    updated_count: int = 0
    skipped_count: int = 0
    failed_count: int = 0
    remark_overwrite_candidates: int = 0
    dry_run: bool = True
    items: list[dict[str, Any]] = field(default_factory=list)
    extra: dict[str, Any] = field(default_factory=dict)


def _norm_mapping(raw: Any) -> str:
    if raw in (None, ""):
        return ""
    if isinstance(raw, dict):
        obj = raw
    else:
        try:
            obj = json.loads(str(raw))
        except (json.JSONDecodeError, TypeError):
            return str(raw).strip()
    if isinstance(obj, dict):
        return json.dumps(obj, ensure_ascii=False, sort_keys=True)
    return str(raw).strip()


def _describe_changes(before: dict[str, Any], after: dict[str, Any]) -> str:
    parts: list[str] = []
    fields = (
        ("名称", "name"),
        ("模型", "models"),
        ("上游映射", "model_mapping"),
        ("base_url", "base_url"),
        ("备注", "remark"),
        ("类型", "type"),
        ("分组", "group"),
    )
    for label, key in fields:
        old = before.get(key)
        new = after.get(key)
        if key == "model_mapping":
            old_s, new_s = _norm_mapping(old), _norm_mapping(new)
        else:
            old_s, new_s = str(old or "").strip(), str(new or "").strip()
        if old_s != new_s:
            parts.append(f"{label}「{old_s or '空'}」→「{new_s or '空'}」")
    return "；".join(parts) if parts else "配置无变化"


def _merge_update(
    existing: dict[str, Any],
    *,
    payload_channel: dict[str, Any],
    new_name: str,
    overwrite_remark: bool = False,
) -> dict[str, Any]:
    merged = dict(existing)
    merged["id"] = int(existing.get("id") or 0)
    merged["name"] = new_name
    merged["type"] = payload_channel.get("type", existing.get("type"))
    merged["models"] = payload_channel.get("models", existing.get("models"))
    merged["group"] = payload_channel.get("group", existing.get("group"))
    merged["base_url"] = payload_channel.get("base_url", existing.get("base_url"))
    # 空备注始终补写本行地址；已有备注仅在用户确认后覆盖。
    # 未设置该字段时保留原对象中的 remark，避免向上游提交无意覆盖。
    if overwrite_remark or not str(existing.get("remark") or "").strip():
        merged["remark"] = payload_channel.get("base_url", "")
    if payload_channel.get("model_mapping"):
        merged["model_mapping"] = payload_channel["model_mapping"]
    if "other" in payload_channel:
        merged["other"] = payload_channel.get("other")
    if payload_channel.get("settings"):
        merged["settings"] = payload_channel["settings"]
    # 更新不改密钥：不传 key，上游 GORM 会跳过空字段并保留原密钥
    merged.pop("key", None)
    return merged


def run_channel_batch_update(
    *,
    base_url: str,
    batch_text: str,
    auth: dict[str, Any],
    dry_run: bool = True,
    default_key: str = "",
    overwrite_remark: bool = False,
) -> BatchUpdateResult:
    _ = default_key  # 更新从不改密钥，忽略行内与全局秘钥
    # 预更新必须展示“选择覆盖”后的完整差异，实际写入才服从用户选择。
    effective_overwrite_remark = bool(overwrite_remark or dry_run)
    rows = parse_batch_rows(batch_text, require_secret=False)
    if not rows:
        raise ValueError("没有可处理的批量数据，请直接粘贴数据行（无需表头）")

    types, type_source = get_channel_types(base_url)
    client = NewAPIClient(base_url)
    authenticate_client(client, auth)
    client.get_status()
    known_groups = set(client.list_groups())
    if not known_groups:
        raise ValueError("未能从站点获取分组列表，请确认管理员权限")

    existing_channels = client.list_all_channels()
    name_group_index = build_existing_index(existing_channels)
    name_index = build_name_index(existing_channels)
    model_index = build_model_index(existing_channels)

    result = BatchUpdateResult(total=len(rows), dry_run=dry_run)
    result.extra = {"type_source": type_source, "type_count": len(types)}

    for index, row in enumerate(rows, start=1):
        raw_name = str(row.get("名称") or row.get("name") or "").strip()
        group = str(row.get("分组") or row.get("group") or "").strip()
        try:
            match_name, new_name = split_channel_rename(raw_name)
            if not match_name:
                raise ValueError("名称不能为空")
            if not group:
                raise ValueError("分组不能为空")
            if group not in known_groups:
                raise ValueError(f"未找到分组: {group}")

            existing = name_group_index.get(channel_name_group(match_name, group))
            if not existing:
                raise ValueError(
                    f"未找到原渠道「{match_name}」+分组「{group}」，无法更新。"
                    "名称列可写 原名称=>新名称 以改名"
                )

            target_id = int(existing.get("id") or 0)
            row_for_payload = dict(row)
            row_for_payload["名称"] = new_name
            row_for_payload["秘钥"] = ""
            row_for_payload["密钥"] = ""
            row_for_payload["key"] = ""
            channel_type = resolve_channel_type(pick_row_value(row, TYPE_KEYS), types)
            payload = build_channel_payload(
                row_for_payload,
                channel_type=channel_type,
                default_key="",
                known_groups=known_groups,
                require_key=False,
            )
            payload_channel = payload.get("channel") or {}
            existing_remark = str(existing.get("remark") or "").strip()
            target_remark = str(payload_channel.get("base_url") or "").strip()
            remark_overwrite_candidate = bool(
                existing_remark and existing_remark != target_remark
            )
            merged = _merge_update(
                existing,
                payload_channel=payload_channel,
                new_name=new_name,
                overwrite_remark=effective_overwrite_remark,
            )

            other = name_index.get(new_name)
            if other and int(other.get("id") or 0) != target_id:
                raise ValueError(
                    f"新渠道名「{new_name}」已被 ID={other.get('id')} 占用，无法改名"
                )
            for model in extract_channel_models(merged) or [
                m.strip()
                for m in str(pick_row_value(row, MODEL_KEYS) or "").split(",")
                if m.strip()
            ]:
                occupied = model_index.get(model)
                if occupied and int(occupied.get("id") or 0) != target_id:
                    raise ValueError(
                        f"模型「{model}」已被渠道「{occupied.get('name')}」"
                        f"（ID={occupied.get('id')}）占用"
                    )

            change = _describe_changes(existing, merged)
            if change == "配置无变化":
                result.skipped_count += 1
                remark_note = "；已按选择保留原备注" if remark_overwrite_candidate else ""
                result.items.append(
                    {
                        "index": index,
                        "name": match_name,
                        "success": True,
                        "skipped": True,
                        "target_id": target_id,
                        "message": f"ID={target_id} 配置无变化，已跳过{remark_note}",
                    }
                )
                continue

            result.matched_count += 1
            if remark_overwrite_candidate:
                result.remark_overwrite_candidates += 1
            if dry_run:
                result.items.append(
                    {
                        "index": index,
                        "name": new_name,
                        "success": True,
                        "preview": True,
                        "target_id": target_id,
                        "remark_overwrite_candidate": remark_overwrite_candidate,
                        "message": f"预更新 ID={target_id}「{match_name}」：{change}",
                    }
                )
                continue

            client.update_channel(merged)
            result.updated_count += 1
            remark_note = "；已覆盖原备注" if remark_overwrite_candidate and overwrite_remark else ""
            result.items.append(
                {
                    "index": index,
                    "name": new_name,
                    "success": True,
                    "target_id": target_id,
                    "message": f"已更新 ID={target_id}「{match_name}」：{change}{remark_note}",
                }
            )
            name_index[new_name] = merged
            if match_name != new_name and name_index.get(match_name, {}).get("id") == target_id:
                name_index.pop(match_name, None)
            name_group_index[channel_name_group(new_name, group)] = merged
        except Exception as exc:  # noqa: BLE001
            result.failed_count += 1
            result.items.append(
                {
                    "index": index,
                    "name": raw_name or f"row-{index}",
                    "success": False,
                    "message": str(exc),
                }
            )

    result.items.insert(
        0,
        {
            "meta": True,
            "type_source": type_source,
            "type_count": len(types),
            "existing_channel_count": len(existing_channels),
        },
    )
    return result
