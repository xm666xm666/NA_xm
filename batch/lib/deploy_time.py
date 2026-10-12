# -*- coding: utf-8 -*-
"""部署时间解析与上游表排序。"""

from __future__ import annotations

from datetime import datetime
from typing import Any


def parse_deploy_datetime(value: Any) -> datetime | None:
    """解析上游/总览表里的部署时间；无法解析返回 None。"""
    if isinstance(value, datetime):
        return value.replace(tzinfo=None) if value.tzinfo else value
    text = str(value or "").strip()
    if not text:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%Y/%m/%d %H:%M:%S", "%Y/%m/%d"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    iso = text.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(iso)
    except ValueError:
        return None
    if dt.tzinfo is not None:
        dt = dt.replace(tzinfo=None)
    return dt


def sort_rows_by_deploy_time_desc(rows: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    """按「部署时间」降序，最新在上；空值或无法解析的排最后。"""

    def sort_key(row: dict[str, Any]) -> datetime:
        dt = parse_deploy_datetime((row or {}).get("部署时间"))
        return dt if dt is not None else datetime.min

    return sorted(list(rows or []), key=sort_key, reverse=True)
