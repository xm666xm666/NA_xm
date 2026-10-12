"""按名称+分组 或 按渠道 ID 批量删除渠道。"""

from __future__ import annotations

from typing import Any

from .api_client import NewAPIClient, authenticate_client
from .batch_delete_result import BatchDeleteResult
from .channel_builder import (
    _is_header_line,
    _is_log_line,
    parse_data_line,
)
from .duplicate_checker import build_existing_index, channel_name_group


def parse_channel_delete_rows(text: str) -> list[dict[str, str]]:
    """删除行：优先「名称 分组」；完整创建行（含 模型->上游）也可。"""
    rows: list[dict[str, str]] = []
    for index, raw in enumerate((text or "").splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if _is_log_line(line) or _is_header_line(line):
            continue
        if "->" in line:
            parsed = parse_data_line(line, require_secret=False)
            rows.append({"名称": parsed["名称"], "分组": parsed["分组"]})
            continue
        if "\t" in line:
            parts = [part.strip() for part in line.split("\t") if part.strip()]
            if len(parts) < 2:
                raise ValueError(f"第 {index} 行无法解析，格式：名称 [Tab] 分组")
            rows.append({"名称": parts[0], "分组": parts[1]})
            continue
        parts = line.split()
        if len(parts) < 2:
            raise ValueError(f"第 {index} 行无法解析，格式：名称 [空格] 分组")
        rows.append({"名称": " ".join(parts[:-1]), "分组": parts[-1]})
    return rows


def _parse_channel_ids(raw: Any) -> list[int]:
    if raw is None:
        return []
    if isinstance(raw, (int, float, str)):
        raw = [raw]
    if not isinstance(raw, list):
        return []
    out: list[int] = []
    seen: set[int] = set()
    for item in raw:
        try:
            cid = int(item)
        except (TypeError, ValueError):
            continue
        if cid <= 0 or cid in seen:
            continue
        seen.add(cid)
        out.append(cid)
    return out


def run_channel_batch_delete_by_ids(
    *,
    base_url: str,
    auth: dict[str, Any],
    channel_ids: list[int] | Any,
    dry_run: bool = True,
) -> BatchDeleteResult:
    """按渠道 ID 预删除 / 确认删除。"""
    id_list = _parse_channel_ids(channel_ids)
    if not id_list:
        raise ValueError("请指定要删除的渠道 ID")

    client = NewAPIClient(base_url)
    authenticate_client(client, auth)
    client.get_status()

    existing = {
        int(ch.get("id") or 0): ch
        for ch in client.list_all_channels()
        if ch.get("id") is not None
    }
    result = BatchDeleteResult(total=len(id_list), dry_run=dry_run)
    ids_to_delete: list[int] = []

    for index_no, channel_id in enumerate(id_list, start=1):
        ch = existing.get(channel_id)
        if not ch:
            result.skipped_count += 1
            result.items.append(
                {
                    "index": index_no,
                    "name": f"id={channel_id}",
                    "success": True,
                    "skipped": True,
                    "target_id": channel_id,
                    "message": f"未找到渠道 ID={channel_id}",
                }
            )
            continue

        name = str(ch.get("name") or "")
        group = str(ch.get("group") or "")
        ids_to_delete.append(channel_id)
        result.matched_count += 1
        result.items.append(
            {
                "index": index_no,
                "name": name or f"id={channel_id}",
                "success": True,
                "preview": dry_run,
                "target_id": channel_id,
                "group": group,
                "message": (
                    f"{'将删除' if dry_run else '已删除'}渠道 ID={channel_id}"
                    f"（{name or '—'} / {group or '—'}）"
                ),
            }
        )

    if dry_run or not ids_to_delete:
        return result

    try:
        result.deleted_count = client.delete_channels_batch(ids_to_delete)
    except Exception as exc:  # noqa: BLE001
        result.failed_count += len(ids_to_delete)
        for item in result.items:
            if item.get("target_id") and not item.get("skipped"):
                item["success"] = False
                item["preview"] = False
                item["message"] = f"删除失败: {exc}"

    return result


def run_channel_batch_delete(
    *,
    base_url: str,
    batch_text: str = "",
    auth: dict[str, Any],
    dry_run: bool = True,
    channel_ids: list[int] | Any | None = None,
) -> BatchDeleteResult:
    """优先按 channel_ids 删除；否则按批量文本（名称+分组）删除。"""
    id_list = _parse_channel_ids(channel_ids)
    if id_list:
        return run_channel_batch_delete_by_ids(
            base_url=base_url,
            auth=auth,
            channel_ids=id_list,
            dry_run=dry_run,
        )

    rows = parse_channel_delete_rows(batch_text)
    if not rows:
        raise ValueError("没有可处理的批量数据")

    client = NewAPIClient(base_url)
    authenticate_client(client, auth)
    client.get_status()

    existing = client.list_all_channels()
    index = build_existing_index(existing)
    seen_pairs: set[tuple[str, str]] = set()
    ids_to_delete: list[int] = []

    result = BatchDeleteResult(total=len(rows), dry_run=dry_run)

    for index_no, row in enumerate(rows, start=1):
        name = str(row.get("名称") or row.get("name") or "").strip()
        group = str(row.get("分组") or row.get("group") or "").strip()
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
                    "success": True,
                    "skipped": True,
                    "message": f"未找到匹配渠道（{name} / {group}）",
                }
            )
            continue

        channel_id = int(matched["id"])
        ids_to_delete.append(channel_id)
        result.matched_count += 1
        result.items.append(
            {
                "index": index_no,
                "name": name,
                "success": True,
                "preview": dry_run,
                "target_id": channel_id,
                "message": (
                    f"{'将删除' if dry_run else '已删除'}渠道 ID={channel_id}（{name} / {group}）"
                ),
            }
        )

    if dry_run or not ids_to_delete:
        return result

    try:
        result.deleted_count = client.delete_channels_batch(ids_to_delete)
    except Exception as exc:  # noqa: BLE001
        result.failed_count += len(ids_to_delete)
        for item in result.items:
            if item.get("target_id"):
                item["success"] = False
                item["preview"] = False
                item["message"] = f"删除失败: {exc}"

    return result
