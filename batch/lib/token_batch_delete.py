"""按名称+分组批量删除令牌。"""

from __future__ import annotations

from typing import Any

from .api_client import NewAPIClient, authenticate_client
from .batch_delete_result import BatchDeleteResult
from .channel_builder import _is_header_line, _is_log_line
from .token_duplicate_checker import build_existing_index, token_name_group


def parse_token_name_group_rows(text: str) -> list[dict[str, str]]:
    """删除/启停行：名称+分组；完整创建行（名称 分组 模型）也可。"""
    rows: list[dict[str, str]] = []
    for index, raw in enumerate((text or "").splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if _is_log_line(line) or _is_header_line(line):
            continue
        if "\t" in line:
            parts = [part.strip() for part in line.split("\t") if part.strip()]
        else:
            parts = line.split()
        if len(parts) < 2:
            raise ValueError(f"第 {index} 行无法解析，格式：名称 [Tab/空格] 分组")
        rows.append({"名称": parts[0], "分组": parts[1]})
    return rows


def run_token_batch_delete(
    *,
    base_url: str,
    batch_text: str,
    auth: dict[str, Any],
    dry_run: bool = True,
) -> BatchDeleteResult:
    rows = parse_token_name_group_rows(batch_text)
    if not rows:
        raise ValueError("没有可处理的批量数据")

    client = NewAPIClient(base_url)
    authenticate_client(client, auth)
    client.get_status()

    existing = client.list_all_tokens()
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

        pair = token_name_group(name, group)
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
                    "message": f"未找到匹配令牌（{name} / {group}）",
                }
            )
            continue

        token_id = int(matched["id"])
        ids_to_delete.append(token_id)
        result.matched_count += 1
        result.items.append(
            {
                "index": index_no,
                "name": name,
                "success": True,
                "preview": dry_run,
                "target_id": token_id,
                "message": (
                    f"{'将删除' if dry_run else '已删除'}令牌 ID={token_id}（{name} / {group}）"
                ),
            }
        )

    if dry_run or not ids_to_delete:
        return result

    try:
        result.deleted_count = client.delete_tokens_batch(ids_to_delete)
    except Exception as exc:  # noqa: BLE001
        result.failed_count += len(ids_to_delete)
        for item in result.items:
            if item.get("target_id"):
                item["success"] = False
                item["preview"] = False
                item["message"] = f"删除失败: {exc}"

    return result
