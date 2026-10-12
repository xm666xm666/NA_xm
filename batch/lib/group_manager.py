"""分组管理：分组不存在时通过系统选项自动创建。"""

from __future__ import annotations

import json
from typing import Any

from .api_client import NewAPIClient


def _parse_json_object(raw: str) -> dict[str, Any]:
    text = (raw or "").strip()
    if not text:
        return {}
    data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError("选项值不是 JSON 对象")
    return data


def collect_row_groups(rows: list[dict[str, Any]]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for row in rows:
        group = str(row.get("分组") or row.get("group") or "").strip()
        if group and group not in seen:
            seen.add(group)
            ordered.append(group)
    return ordered


def ensure_group(
    client: NewAPIClient,
    group: str,
    *,
    known_groups: set[str] | None = None,
    default_ratio: float = 1.0,
) -> bool:
    """确保分组存在。返回 True 表示本次新建了分组。"""
    name = (group or "").strip()
    if not name:
        raise ValueError("分组不能为空")

    if known_groups is not None and name in known_groups:
        return False

    if name in set(client.list_groups()):
        if known_groups is not None:
            known_groups.add(name)
        return False

    options = client.list_options_map()
    group_ratio = _parse_json_object(str(options.get("GroupRatio") or "{}"))
    user_usable = _parse_json_object(str(options.get("UserUsableGroups") or "{}"))

    created = False
    if name not in group_ratio:
        group_ratio[name] = default_ratio
        client.update_option("GroupRatio", json.dumps(group_ratio, ensure_ascii=False))
        created = True

    if name not in user_usable:
        user_usable[name] = name
        client.update_option(
            "UserUsableGroups", json.dumps(user_usable, ensure_ascii=False)
        )
        created = True

    refreshed = set(client.list_groups())
    if name not in refreshed:
        raise RuntimeError(
            f"自动创建分组「{name}」失败，请确认账号具有 Root 权限（/api/option/）"
        )

    if known_groups is not None:
        known_groups.update(refreshed)
    return created


def ensure_groups_for_rows(
    client: NewAPIClient,
    rows: list[dict[str, Any]],
    *,
    known_groups: set[str] | None = None,
) -> list[str]:
    """为批量数据中的分组逐一 ensure，返回本次新建的分组名列表。"""
    created: list[str] = []
    for group in collect_row_groups(rows):
        if ensure_group(client, group, known_groups=known_groups):
            created.append(group)
    return created


PROTECTED_GROUPS = frozenset({"default", "auto"})


def delete_group(client: NewAPIClient, group: str) -> None:
    """从 GroupRatio / UserUsableGroups 移除分组。"""
    name = (group or "").strip()
    if not name:
        raise ValueError("分组不能为空")
    if name in PROTECTED_GROUPS:
        raise ValueError(f"系统保护分组不可删除: {name}")

    options = client.list_options_map()
    group_ratio = _parse_json_object(str(options.get("GroupRatio") or "{}"))
    user_usable = _parse_json_object(str(options.get("UserUsableGroups") or "{}"))

    if name not in group_ratio and name not in user_usable:
        raise ValueError(f"分组不存在: {name}")

    if name in group_ratio:
        del group_ratio[name]
        client.update_option("GroupRatio", json.dumps(group_ratio, ensure_ascii=False))

    if name in user_usable:
        del user_usable[name]
        client.update_option(
            "UserUsableGroups", json.dumps(user_usable, ensure_ascii=False)
        )

    if name in set(client.list_groups()):
        raise RuntimeError(
            f"删除分组「{name}」失败，请确认账号具有 Root 权限（/api/option/）"
        )


def count_group_usage(
    group: str,
    *,
    channels: list[dict[str, Any]],
    tokens: list[dict[str, Any]],
) -> tuple[int, int]:
    target = (group or "").strip()
    channel_count = 0
    for channel in channels:
        parts = [part.strip() for part in str(channel.get("group") or "").split(",")]
        if target in parts:
            channel_count += 1

    token_count = sum(
        1
        for token in tokens
        if str(token.get("group") or "").strip() == target
    )
    return channel_count, token_count
