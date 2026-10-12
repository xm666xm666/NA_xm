# -*- coding: utf-8 -*-
"""卫生策略：宽限期、用量阈值。存 env/hygiene_policy.json，缺省与现网分析规则一致。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

POLICY_FILENAME = "hygiene_policy.json"

DEFAULT_POLICY: dict[str, Any] = {
    "new_deploy_days": 10,
    "unused_used_usd": 0.0,
    "uncommon_used_usd": 1.0,
    "relax_on_new_deploy": True,
    "external_vendors_in_scope": False,
}


def policy_path(root_dir: Path) -> Path:
    return Path(root_dir) / "env" / POLICY_FILENAME


def default_policy() -> dict[str, Any]:
    return dict(DEFAULT_POLICY)


def new_deploy_note(days: int) -> str:
    return f"新部署未满 {int(days)} 天，评估已放宽。"


def new_deploy_hold(days: int) -> str:
    return f"部署未满 {int(days)} 天，暂缓禁用/停用，观察后再处置"


def normalize_policy(raw: Any | None) -> dict[str, Any]:
    data = default_policy()
    if not isinstance(raw, dict):
        return data
    if "new_deploy_days" in raw:
        days = int(raw["new_deploy_days"])
        if days < 0 or days > 3650:
            raise ValueError("new_deploy_days 须在 0–3650 之间")
        data["new_deploy_days"] = days
    if "unused_used_usd" in raw:
        data["unused_used_usd"] = float(raw["unused_used_usd"])
    if "uncommon_used_usd" in raw:
        data["uncommon_used_usd"] = float(raw["uncommon_used_usd"])
    if data["uncommon_used_usd"] < data["unused_used_usd"]:
        raise ValueError("uncommon_used_usd 不能小于 unused_used_usd")
    if "relax_on_new_deploy" in raw:
        data["relax_on_new_deploy"] = bool(raw["relax_on_new_deploy"])
    if "external_vendors_in_scope" in raw:
        data["external_vendors_in_scope"] = bool(raw["external_vendors_in_scope"])
    return data


def load_policy(root_dir: Path) -> dict[str, Any]:
    path = policy_path(root_dir)
    if not path.exists():
        return default_policy()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return default_policy()
    try:
        return normalize_policy(raw)
    except (TypeError, ValueError):
        return default_policy()


def save_policy(root_dir: Path, raw: Any) -> dict[str, Any]:
    data = normalize_policy(raw)
    path = policy_path(root_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return data


def format_usd(value: float) -> str:
    return f"${float(value):g}"


def unused_metric_label(policy: dict[str, Any] | None = None) -> str:
    data = normalize_policy(policy)
    return f"不用（已用≤{format_usd(data['unused_used_usd'])}）"


def uncommon_metric_label(policy: dict[str, Any] | None = None) -> str:
    data = normalize_policy(policy)
    return f"不常用（已用<{format_usd(data['uncommon_used_usd'])}）"


def policy_summary_text(policy: dict[str, Any] | None = None) -> str:
    data = normalize_policy(policy)
    return (
        f"宽限 {data['new_deploy_days']} 天"
        f" · 不用 ≤ {format_usd(data['unused_used_usd'])}"
        f" · 不常用 < {format_usd(data['uncommon_used_usd'])}"
    )
