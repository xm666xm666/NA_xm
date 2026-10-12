# -*- coding: utf-8 -*-
"""卫生建议读取、处理记录、预禁用清单。不改历史分析 Excel。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .overview_analyzer import (
    SHEET_ACTIONS,
    SHEET_DISABLED_ACTIONS,
    build_batch_disable_rows,
)
from .overview_exporter import load_sheet_rows

STATUS_FILE = "_hygiene_status.json"
STATUS_OPEN = "open"
STATUS_HELD = "held"
STATUS_DONE = "done"
STATUS_SKIPPED = "skipped"


def status_path(root_dir: Path) -> Path:
    return Path(root_dir) / "excel" / STATUS_FILE


def action_key(row: dict[str, Any], *, index: int = 0) -> str:
    parts = [
        str(index),
        str(row.get("站点") or "").strip(),
        str(row.get("渠道名称") or "").strip(),
        str(row.get("令牌名称") or "").strip(),
        str(row.get("分组") or "").strip(),
        str(row.get("类别") or "").strip(),
    ]
    return "|".join(parts)


def is_hold_suggestion(text: str) -> bool:
    return "暂缓禁用" in str(text or "")


def load_status_map(root_dir: Path) -> dict[str, Any]:
    path = status_path(root_dir)
    if not path.exists():
        return {"files": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"files": {}}
    if not isinstance(data, dict):
        return {"files": {}}
    files = data.get("files")
    if not isinstance(files, dict):
        data["files"] = {}
    return data


def save_status_map(root_dir: Path, data: dict[str, Any]) -> None:
    path = status_path(root_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def mark_actions_done(root_dir: Path, filename: str, keys: list[str], *, status: str = STATUS_DONE) -> None:
    store = load_status_map(root_dir)
    files = store.setdefault("files", {})
    bucket = files.setdefault(filename, {})
    for key in keys:
        bucket[key] = {"status": status}
    save_status_map(root_dir, store)


def _decorate_rows(
    rows: list[dict[str, Any]],
    *,
    filename: str,
    status_bucket: dict[str, Any],
    disabled_sheet: bool,
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for idx, row in enumerate(rows):
        item = dict(row)
        key = action_key(item, index=idx)
        saved = status_bucket.get(key) or {}
        hold = is_hold_suggestion(item.get("建议"))
        status = str(saved.get("status") or "")
        if not status:
            if disabled_sheet:
                status = STATUS_DONE
            elif hold:
                status = STATUS_HELD
            else:
                status = STATUS_OPEN
        item["key"] = key
        item["filename"] = filename
        item["status"] = status
        item["hold"] = hold
        item["disabled_sheet"] = disabled_sheet
        out.append(item)
    return out


def load_analysis_payload(path: Path, root_dir: Path) -> dict[str, Any]:
    src = Path(path)
    if not src.exists():
        raise FileNotFoundError("未找到智能分析表")
    store = load_status_map(root_dir)
    bucket = (store.get("files") or {}).get(src.name) or {}
    actions = _decorate_rows(
        load_sheet_rows(src, [SHEET_ACTIONS]),
        filename=src.name,
        status_bucket=bucket,
        disabled_sheet=False,
    )
    disabled = _decorate_rows(
        load_sheet_rows(src, [SHEET_DISABLED_ACTIONS]),
        filename=src.name,
        status_bucket=bucket,
        disabled_sheet=True,
    )
    pending_high = sum(1 for row in actions if row.get("status") == STATUS_OPEN and str(row.get("级别") or "") == "高")
    hold_count = sum(1 for row in actions if row.get("status") == STATUS_HELD)
    return {
        "filename": src.name,
        "actions": actions,
        "disabled_actions": disabled,
        "pending_high": pending_high,
        "hold_count": hold_count,
        "open_count": sum(1 for row in actions if row.get("status") == STATUS_OPEN),
    }


def _batch_text_from_lines(lines: list[str]) -> str:
    return "\n".join(line for line in lines if str(line).strip())


def preview_disable_from_actions(
    actions: list[dict[str, Any]],
    *,
    force_hold: bool = False,
) -> dict[str, Any]:
    usable: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    for row in actions:
        if row.get("disabled_sheet") or row.get("status") == STATUS_DONE:
            skipped.append({"key": row.get("key"), "reason": "已处理或已禁用"})
            continue
        if row.get("hold") and not force_hold:
            skipped.append({"key": row.get("key"), "reason": "新部署宽限期，默认暂缓；勾选「仍要执行」后可预禁用"})
            continue
        usable.append(row)
    disable_rows = build_batch_disable_rows(usable, include_hold=force_hold)
    channels: dict[str, str] = {}
    tokens: dict[str, str] = {}
    for env in ("test", "uat", "prod"):
        ch_lines = [str(item.get(f"{env}渠道") or "").strip() for item in disable_rows]
        tk_lines = [str(item.get(f"{env}令牌") or "").strip() for item in disable_rows]
        channels[env] = _batch_text_from_lines(ch_lines)
        tokens[env] = _batch_text_from_lines(tk_lines)
    return {
        "actions_used": len(usable),
        "skipped": skipped,
        "channels": channels,
        "tokens": tokens,
        "channel_count": {env: len([ln for ln in text.splitlines() if ln]) for env, text in channels.items()},
        "token_count": {env: len([ln for ln in text.splitlines() if ln]) for env, text in tokens.items()},
        "force_hold": bool(force_hold),
    }


def select_actions(payload: dict[str, Any], keys: list[str] | None) -> list[dict[str, Any]]:
    rows = list(payload.get("actions") or [])
    wanted = {str(k) for k in (keys or []) if str(k).strip()}
    if not wanted:
        return [row for row in rows if row.get("status") in {STATUS_OPEN, STATUS_HELD}]
    picked = [row for row in rows if str(row.get("key")) in wanted]
    if not picked:
        raise ValueError("没有匹配的建议，请刷新后重选")
    return picked
