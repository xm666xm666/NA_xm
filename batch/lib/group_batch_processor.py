"""批量创建分组（仅写入 GroupRatio / UserUsableGroups）。"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from .api_client import NewAPIClient, authenticate_client
from .batch_delete_result import BatchDeleteResult
from .group_manager import (
    PROTECTED_GROUPS,
    count_group_usage,
    delete_group,
    ensure_group,
)


def parse_group_names(text: str) -> list[str]:
    """解析分组名：每行一个，同行可用逗号/Tab 分隔；# 开头为注释。"""
    seen: set[str] = set()
    ordered: list[str] = []
    for raw_line in (text or "").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        for part in re.split(r"[,，\t]+", line):
            name = part.strip()
            if not name or name in seen:
                continue
            seen.add(name)
            ordered.append(name)
    return ordered


@dataclass
class GroupCreateResult:
    total: int = 0
    created_count: int = 0
    skipped_count: int = 0
    failed_count: int = 0
    items: list[dict[str, Any]] = field(default_factory=list)
    groups: list[str] = field(default_factory=list)


def list_site_groups(*, base_url: str, auth: dict[str, Any]) -> list[str]:
    client = NewAPIClient(base_url)
    authenticate_client(client, auth)
    return sorted(client.list_groups())


def run_group_create(
    *,
    base_url: str,
    groups_text: str,
    auth: dict[str, Any],
    default_ratio: float = 1.0,
) -> GroupCreateResult:
    names = parse_group_names(groups_text)
    if not names:
        raise ValueError("没有可处理的分组名，请每行填写一个分组")

    if default_ratio < 0:
        raise ValueError("分组倍率不能为负数")

    client = NewAPIClient(base_url)
    authenticate_client(client, auth)
    client.get_status()

    known_groups = set(client.list_groups())
    result = GroupCreateResult(total=len(names))

    for index, name in enumerate(names, start=1):
        try:
            if name in known_groups:
                result.skipped_count += 1
                result.items.append(
                    {
                        "index": index,
                        "name": name,
                        "success": True,
                        "skipped": True,
                        "message": "已存在，跳过",
                    }
                )
                continue

            created = ensure_group(
                client,
                name,
                known_groups=known_groups,
                default_ratio=default_ratio,
            )
            if created:
                result.created_count += 1
                result.items.append(
                    {
                        "index": index,
                        "name": name,
                        "success": True,
                        "message": f"已创建（倍率 {default_ratio:g}）",
                    }
                )
            else:
                result.skipped_count += 1
                result.items.append(
                    {
                        "index": index,
                        "name": name,
                        "success": True,
                        "skipped": True,
                        "message": "已存在，跳过",
                    }
                )
        except Exception as exc:  # noqa: BLE001
            result.failed_count += 1
            result.items.append(
                {
                    "index": index,
                    "name": name,
                    "success": False,
                    "message": str(exc),
                }
            )

    result.groups = sorted(client.list_groups())
    return result


def run_group_delete(
    *,
    base_url: str,
    groups_text: str,
    auth: dict[str, Any],
    dry_run: bool = True,
) -> BatchDeleteResult:
    names = parse_group_names(groups_text)
    if not names:
        raise ValueError("没有可处理的分组名，请每行填写一个分组")

    client = NewAPIClient(base_url)
    authenticate_client(client, auth)
    client.get_status()

    known_groups = set(client.list_groups())
    channels = client.list_all_channels()
    tokens = client.list_all_tokens()

    result = BatchDeleteResult(total=len(names), dry_run=dry_run)

    for index, name in enumerate(names, start=1):
        try:
            if name in PROTECTED_GROUPS:
                result.skipped_count += 1
                result.items.append(
                    {
                        "index": index,
                        "name": name,
                        "success": True,
                        "skipped": True,
                        "message": "系统保护分组，不可删除",
                    }
                )
                continue

            if name not in known_groups:
                result.skipped_count += 1
                result.items.append(
                    {
                        "index": index,
                        "name": name,
                        "success": True,
                        "skipped": True,
                        "message": "分组不存在，跳过",
                    }
                )
                continue

            channel_count, token_count = count_group_usage(
                name, channels=channels, tokens=tokens
            )
            usage_hint = ""
            if channel_count or token_count:
                usage_hint = f"（仍有 {channel_count} 渠道 / {token_count} 令牌引用）"

            if dry_run:
                result.matched_count += 1
                result.items.append(
                    {
                        "index": index,
                        "name": name,
                        "success": True,
                        "preview": True,
                        "message": f"将从配置中删除分组{usage_hint}",
                    }
                )
                continue

            delete_group(client, name)
            known_groups.discard(name)
            result.deleted_count += 1
            result.matched_count += 1
            result.items.append(
                {
                    "index": index,
                    "name": name,
                    "success": True,
                    "message": f"已从配置中删除分组{usage_hint}",
                }
            )
        except Exception as exc:  # noqa: BLE001
            result.failed_count += 1
            result.items.append(
                {
                    "index": index,
                    "name": name,
                    "success": False,
                    "message": str(exc),
                }
            )

    result.extra["groups"] = sorted(known_groups)
    return result
