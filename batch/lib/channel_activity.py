# -*- coding: utf-8 -*-
"""渠道近一月活跃：按模型逐项填写，失败或无信息为 N/A。"""

from __future__ import annotations

from typing import Any

ACTIVITY_NA = "N/A"
ACTIVITY_IDLE = "近一月无活跃"
ACTIVITY_ACTIVE = "有活跃"
ACTIVITY_BATCH_LIMIT = 500

VERDICT_NA = "na"
VERDICT_IDLE = "all_idle"
VERDICT_ACTIVE = "has_active"


def parse_channel_model_names(channel: dict[str, Any] | None) -> list[str]:
    """与网关渠道列表一致：test_model + models 逗号拆分，去重保序。"""
    row = channel or {}
    seen: set[str] = set()
    names: list[str] = []
    test_model = str(row.get("test_model") or "").strip()
    if test_model and test_model not in seen:
        seen.add(test_model)
        names.append(test_model)
    raw = row.get("models") or row.get("模型") or row.get("模型列表") or ""
    for part in str(raw).replace("，", ",").split(","):
        name = part.strip()
        if not name or name in seen:
            continue
        seen.add(name)
        names.append(name)
    return names


def stat_has_activity(stat: Any) -> bool:
    if not isinstance(stat, dict):
        return False
    try:
        if int(stat.get("total_requests") or 0) > 0:
            return True
        if int(stat.get("active_minutes") or 0) > 0:
            return True
    except (TypeError, ValueError):
        pass
    try:
        if float(stat.get("avg_rpm") or 0) > 0:
            return True
        if float(stat.get("avg_tpm") or 0) > 0:
            return True
    except (TypeError, ValueError):
        return False
    return False


def channel_row_id(row: Any) -> int:
    """兼容 API 行 id 与汇总表内部 _sort_id。"""
    try:
        return int((row or {}).get("id") or (row or {}).get("_sort_id") or 0)
    except (TypeError, ValueError):
        return 0


def classify_model_activity(stat: Any, *, fetch_ok: bool) -> str:
    if not fetch_ok:
        return ACTIVITY_NA
    if stat_has_activity(stat):
        return ACTIVITY_ACTIVE
    return ACTIVITY_IDLE


def format_activity_lines(details: list[dict[str, str]]) -> str:
    if not details:
        return ACTIVITY_NA
    return "\n".join(f"{item['model']}: {item['status']}" for item in details if item.get("model"))


def verdict_from_details(details: list[dict[str, str]]) -> str:
    if not details:
        return VERDICT_NA
    statuses = [str(item.get("status") or "").strip() for item in details]
    if any(status == ACTIVITY_NA or not status for status in statuses):
        return VERDICT_NA
    if any(status == ACTIVITY_ACTIVE for status in statuses):
        return VERDICT_ACTIVE
    if statuses and all(status == ACTIVITY_IDLE for status in statuses):
        return VERDICT_IDLE
    return VERDICT_NA


def parse_activity_label(text: Any) -> dict[str, Any]:
    """解析余额表「近一月活跃」单元格。旧表无此列时 text 为空。"""
    raw = str(text or "").strip()
    if not raw:
        return {"details": [], "verdict": "", "label": "", "legacy": True}
    lines = [ln.strip() for ln in raw.replace("\r\n", "\n").split("\n") if ln.strip()]
    details: list[dict[str, str]] = []
    for line in lines:
        if line == ACTIVITY_NA and not details:
            return {
                "details": [{"model": "", "status": ACTIVITY_NA}],
                "verdict": VERDICT_NA,
                "label": ACTIVITY_NA,
                "legacy": False,
            }
        if ":" in line:
            model, status = line.rsplit(":", 1)
            details.append({"model": model.strip(), "status": status.strip() or ACTIVITY_NA})
        else:
            details.append({"model": line, "status": line})
    return {
        "details": details,
        "verdict": verdict_from_details(details),
        "label": "\n".join(lines),
        "legacy": False,
    }


def activity_allows_disable(text: Any) -> bool:
    """仅当每个模型都是「近一月无活跃」时，才允许用量类建议进入禁用清单。

    旧 Excel 没有该列（空）保持原行为。N/A 或部分有活跃 → 不禁渠道/令牌。
    """
    parsed = parse_activity_label(text)
    if parsed.get("legacy"):
        return True
    return parsed.get("verdict") == VERDICT_IDLE


def build_activity_fill(
    channel: dict[str, Any] | None,
    stats_map: dict[tuple[int, str], dict[str, Any]] | None,
    *,
    fetch_ok: bool,
) -> dict[str, Any]:
    models = parse_channel_model_names(channel)
    channel_id = channel_row_id(channel)
    if not models:
        return {
            "details": [],
            "activity_label": ACTIVITY_NA,
            "activity_verdict": VERDICT_NA,
        }
    details: list[dict[str, str]] = []
    for model in models:
        stat = (stats_map or {}).get((channel_id, model))
        details.append(
            {
                "model": model,
                "status": classify_model_activity(stat, fetch_ok=fetch_ok),
            }
        )
    return {
        "details": details,
        "activity_label": format_activity_lines(details),
        "activity_verdict": verdict_from_details(details),
    }


def apply_na_fill(channel: dict[str, Any] | None) -> dict[str, Any]:
    return build_activity_fill(channel, {}, fetch_ok=False)


def disable_blocked_note(verdict: str) -> str:
    if verdict == VERDICT_ACTIVE:
        return "部分或全部模型近一月仍有活跃，不禁用该渠道及关联令牌"
    if verdict == VERDICT_NA:
        return "近一月活跃为 N/A，不据此禁用渠道或令牌"
    return ""
