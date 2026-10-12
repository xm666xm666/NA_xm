"""将指定分组下的渠道 / 令牌切换到另一个分组。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .api_client import NewAPIClient, authenticate_client
from .token_api_fields import apply_model_limits, read_model_limits


KIND_CHANNEL = "channel"
KIND_TOKEN = "token"
VALID_KINDS = frozenset({KIND_CHANNEL, KIND_TOKEN})


@dataclass
class GroupSwitchResult:
    total: int = 0
    matched_count: int = 0
    updated_count: int = 0
    skipped_count: int = 0
    failed_count: int = 0
    dry_run: bool = True
    kind: str = KIND_CHANNEL
    source_group: str = ""
    target_group: str = ""
    items: list[dict[str, Any]] = field(default_factory=list)
    extra: dict[str, Any] = field(default_factory=dict)


def parse_group_parts(raw: Any) -> list[str]:
    parts: list[str] = []
    seen: set[str] = set()
    for part in str(raw or "").split(","):
        name = part.strip()
        if not name or name in seen:
            continue
        seen.add(name)
        parts.append(name)
    return parts


def channel_in_group(channel: dict[str, Any], group: str) -> bool:
    target = (group or "").strip()
    return bool(target) and target in parse_group_parts(channel.get("group"))


def token_in_group(token: dict[str, Any], group: str) -> bool:
    target = (group or "").strip()
    return bool(target) and str(token.get("group") or "").strip() == target


def rewrite_channel_groups(raw: Any, source: str, target: str) -> str:
    """把渠道多分组字符串中的 source 换成 target；已含 target 则去重。"""
    source = (source or "").strip()
    target = (target or "").strip()
    out: list[str] = []
    seen: set[str] = set()
    for part in parse_group_parts(raw):
        name = target if part == source else part
        if not name or name in seen:
            continue
        seen.add(name)
        out.append(name)
    return ",".join(out)


def _parse_ids(raw: Any) -> list[int]:
    if raw is None:
        return []
    if isinstance(raw, (str, int)):
        raw = [raw]
    ids: list[int] = []
    seen: set[int] = set()
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


def _status_label(status: Any) -> str:
    try:
        value = int(status or 0)
    except (TypeError, ValueError):
        value = 0
    if value == 1:
        return "已启用"
    if value == 2:
        return "已禁用"
    return f"状态{value}" if value else "未知"


def _channel_item(channel: dict[str, Any]) -> dict[str, Any]:
    cid = int(channel.get("id") or 0)
    return {
        "id": cid,
        "target_id": cid,
        "name": str(channel.get("name") or "").strip() or f"id-{cid}",
        "group": str(channel.get("group") or "").strip(),
        "status": int(channel.get("status") or 0),
        "status_label": _status_label(channel.get("status")),
    }


def _token_item(token: dict[str, Any]) -> dict[str, Any]:
    tid = int(token.get("id") or 0)
    return {
        "id": tid,
        "target_id": tid,
        "name": str(token.get("name") or "").strip() or f"id-{tid}",
        "group": str(token.get("group") or "").strip(),
        "status": int(token.get("status") or 0),
        "status_label": _status_label(token.get("status")),
    }


def _token_update_payload(existing: dict[str, Any], new_group: str) -> dict[str, Any]:
    enabled, limits = read_model_limits(existing)
    body: dict[str, Any] = {
        "id": int(existing["id"]),
        "name": existing.get("name"),
        "group": new_group,
        "status": existing.get("status", 1),
        "remain_quota": existing.get("remain_quota", 0),
        "expired_time": existing.get("expired_time", -1),
        "unlimited_quota": existing.get("unlimited_quota", True),
        "cross_group_retry": existing.get("cross_group_retry", False),
        "allow_ips": existing.get("allow_ips") or "",
        "model_limits_enabled": enabled,
        "model_limits": limits,
    }
    if enabled and limits:
        apply_model_limits(body, limits)
    return body


def list_group_members(
    *,
    base_url: str,
    auth: dict[str, Any],
    source_group: str,
) -> dict[str, Any]:
    source = (source_group or "").strip()
    if not source:
        raise ValueError("请选择源分组")

    client = NewAPIClient(base_url)
    authenticate_client(client, auth)
    client.get_status()

    channels = [
        _channel_item(ch)
        for ch in client.list_all_channels()
        if channel_in_group(ch, source)
    ]
    tokens = [
        _token_item(tok)
        for tok in client.list_all_tokens()
        if token_in_group(tok, source)
    ]
    channels.sort(key=lambda row: int(row.get("id") or 0))
    tokens.sort(key=lambda row: int(row.get("id") or 0))
    return {
        "source_group": source,
        "channels": channels,
        "tokens": tokens,
        "channel_count": len(channels),
        "token_count": len(tokens),
    }


def run_group_switch(
    *,
    base_url: str,
    auth: dict[str, Any],
    source_group: str,
    target_group: str,
    kind: str,
    ids: list[int] | None = None,
    dry_run: bool = False,
) -> GroupSwitchResult:
    source = (source_group or "").strip()
    target = (target_group or "").strip()
    kind_id = str(kind or "").strip().lower()
    if kind_id in {"channels", "channel"}:
        kind_id = KIND_CHANNEL
    elif kind_id in {"tokens", "token"}:
        kind_id = KIND_TOKEN
    if kind_id not in VALID_KINDS:
        raise ValueError("kind 须为 channel 或 token")
    if not source:
        raise ValueError("请选择源分组")
    if not target:
        raise ValueError("请选择目标分组")
    if source == target:
        raise ValueError("源分组与目标分组不能相同")

    id_list = _parse_ids(ids)
    if not id_list:
        raise ValueError("请至少勾选一条要切换的记录")

    client = NewAPIClient(base_url)
    authenticate_client(client, auth)
    client.get_status()

    known = set(client.list_groups())
    if source not in known:
        raise ValueError(f"源分组不存在：{source}")
    if target not in known:
        raise ValueError(f"目标分组不存在：{target}。请先在上方创建该分组")

    result = GroupSwitchResult(
        total=len(id_list),
        dry_run=bool(dry_run),
        kind=kind_id,
        source_group=source,
        target_group=target,
    )

    if kind_id == KIND_CHANNEL:
        existing = {int(ch.get("id") or 0): ch for ch in client.list_all_channels()}
        for index, cid in enumerate(id_list, start=1):
            channel = existing.get(cid)
            try:
                if not channel:
                    result.failed_count += 1
                    result.items.append(
                        {
                            "index": index,
                            "target_id": cid,
                            "name": f"id-{cid}",
                            "success": False,
                            "message": "渠道不存在",
                        }
                    )
                    continue
                if not channel_in_group(channel, source):
                    result.skipped_count += 1
                    result.items.append(
                        {
                            "index": index,
                            "target_id": cid,
                            "name": str(channel.get("name") or f"id-{cid}"),
                            "success": True,
                            "skipped": True,
                            "message": f"不属于分组「{source}」，已跳过",
                        }
                    )
                    continue
                old_group = str(channel.get("group") or "").strip()
                new_group = rewrite_channel_groups(old_group, source, target)
                if new_group == old_group:
                    result.skipped_count += 1
                    result.items.append(
                        {
                            "index": index,
                            "target_id": cid,
                            "name": str(channel.get("name") or f"id-{cid}"),
                            "success": True,
                            "skipped": True,
                            "message": "分组无变化，已跳过",
                        }
                    )
                    continue
                result.matched_count += 1
                name = str(channel.get("name") or f"id-{cid}")
                if dry_run:
                    result.items.append(
                        {
                            "index": index,
                            "target_id": cid,
                            "name": name,
                            "success": True,
                            "preview": True,
                            "old_group": old_group,
                            "new_group": new_group,
                            "message": f"将切换分组「{old_group}」→「{new_group}」",
                        }
                    )
                    continue
                payload = dict(channel)
                payload["id"] = cid
                payload["group"] = new_group
                payload.pop("key", None)
                client.update_channel(payload)
                result.updated_count += 1
                result.items.append(
                    {
                        "index": index,
                        "target_id": cid,
                        "name": name,
                        "success": True,
                        "old_group": old_group,
                        "new_group": new_group,
                        "message": f"已切换分组「{old_group}」→「{new_group}」",
                    }
                )
            except Exception as exc:  # noqa: BLE001
                result.failed_count += 1
                result.items.append(
                    {
                        "index": index,
                        "target_id": cid,
                        "name": str((channel or {}).get("name") or f"id-{cid}"),
                        "success": False,
                        "message": str(exc),
                    }
                )
        return result

    existing_tokens = {int(tok.get("id") or 0): tok for tok in client.list_all_tokens()}
    for index, tid in enumerate(id_list, start=1):
        listed = existing_tokens.get(tid)
        try:
            if not listed:
                result.failed_count += 1
                result.items.append(
                    {
                        "index": index,
                        "target_id": tid,
                        "name": f"id-{tid}",
                        "success": False,
                        "message": "令牌不存在",
                    }
                )
                continue
            if not token_in_group(listed, source):
                result.skipped_count += 1
                result.items.append(
                    {
                        "index": index,
                        "target_id": tid,
                        "name": str(listed.get("name") or f"id-{tid}"),
                        "success": True,
                        "skipped": True,
                        "message": f"不属于分组「{source}」，已跳过",
                    }
                )
                continue
            result.matched_count += 1
            name = str(listed.get("name") or f"id-{tid}")
            if dry_run:
                result.items.append(
                    {
                        "index": index,
                        "target_id": tid,
                        "name": name,
                        "success": True,
                        "preview": True,
                        "old_group": source,
                        "new_group": target,
                        "message": f"将切换分组「{source}」→「{target}」",
                    }
                )
                continue
            detail = client.get_token(tid)
            payload = _token_update_payload(detail, target)
            client.update_token(payload)
            result.updated_count += 1
            result.items.append(
                {
                    "index": index,
                    "target_id": tid,
                    "name": name,
                    "success": True,
                    "old_group": source,
                    "new_group": target,
                    "message": f"已切换分组「{source}」→「{target}」",
                }
            )
        except Exception as exc:  # noqa: BLE001
            result.failed_count += 1
            result.items.append(
                {
                    "index": index,
                    "target_id": tid,
                    "name": str((listed or {}).get("name") or f"id-{tid}"),
                    "success": False,
                    "message": str(exc),
                }
            )
    return result
