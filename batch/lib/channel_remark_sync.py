"""将渠道的上游地址同步到 New API 渠道备注。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .api_client import NewAPIClient, authenticate_client


MAX_CHANNEL_REMARK_LENGTH = 255
AZURE_CHANNEL_TYPE = 3


@dataclass
class ChannelRemarkSyncResult:
    total: int = 0
    matched_count: int = 0
    updated_count: int = 0
    skipped_count: int = 0
    failed_count: int = 0
    dry_run: bool = True
    items: list[dict[str, Any]] = field(default_factory=list)


def _channel_id(channel: dict[str, Any]) -> int:
    try:
        return int(channel.get("id") or 0)
    except (TypeError, ValueError):
        return 0


def _channel_type(channel: dict[str, Any]) -> int:
    try:
        return int(channel.get("type") or 0)
    except (TypeError, ValueError):
        return 0


def remark_source_label(channel: dict[str, Any]) -> str:
    """返回控制台中对应地址字段的标签。"""
    return "AZURE_OPENAI_ENDPOINT" if _channel_type(channel) == AZURE_CHANNEL_TYPE else "base_url"


def remark_source_value(channel: dict[str, Any]) -> str:
    """Azure 的 AZURE_OPENAI_ENDPOINT 与其他渠道的地址均存于 base_url。"""
    return str(channel.get("base_url") or "").strip()


def append_remark_url(existing_remark: Any, base_url: str) -> tuple[str, bool]:
    """在现有备注下方追加地址；地址已经独占一行时保持幂等。"""
    current = str(existing_remark or "")
    source = str(base_url or "").strip()
    if not source:
        raise ValueError("地址不能为空")

    existing_lines = {line.strip() for line in current.splitlines() if line.strip()}
    if source in existing_lines:
        return current, False

    trimmed = current.rstrip()
    return (f"{trimmed}\n{source}" if trimmed else source), True


def run_channel_remark_sync(
    *,
    base_url: str,
    auth: dict[str, Any],
    dry_run: bool = True,
) -> ChannelRemarkSyncResult:
    """预览或执行全部渠道的地址备注同步。

    每条渠道独立处理。无法取得地址或追加后超过 New API 备注 255 字符限制
    的渠道保持不变，并在结果中包含渠道名称和失败原因。
    """
    client = NewAPIClient(base_url)
    authenticate_client(client, auth)
    client.get_status()

    channels = client.list_all_channels()
    result = ChannelRemarkSyncResult(total=len(channels), dry_run=dry_run)

    for index, channel in enumerate(channels, start=1):
        channel_id = _channel_id(channel)
        name = str(channel.get("name") or "").strip() or f"id-{channel_id or index}"
        group = str(channel.get("group") or "").strip()
        source_label = remark_source_label(channel)
        source_value = remark_source_value(channel)

        item: dict[str, Any] = {
            "index": index,
            "name": name,
            "group": group,
            "target_id": channel_id or None,
            "source_label": source_label,
        }
        if channel_id <= 0:
            result.failed_count += 1
            item.update(
                success=False,
                message=f"渠道「{name}」备注同步未完成：缺少有效渠道 ID",
            )
            result.items.append(item)
            continue
        if not source_value:
            result.failed_count += 1
            item.update(
                success=False,
                message=(
                    f"渠道「{name}」（ID={channel_id}）备注同步未完成："
                    f"未填写 {source_label}"
                ),
            )
            result.items.append(item)
            continue

        next_remark, should_append = append_remark_url(channel.get("remark"), source_value)
        if not should_append:
            result.skipped_count += 1
            item.update(
                success=True,
                skipped=True,
                message=(
                    f"{source_label} 已存在于备注中，已跳过（ID={channel_id}）"
                ),
            )
            result.items.append(item)
            continue
        remark_length = len(next_remark)
        if remark_length > MAX_CHANNEL_REMARK_LENGTH:
            result.failed_count += 1
            item.update(
                success=False,
                remark_length=remark_length,
                message=(
                    f"渠道「{name}」（ID={channel_id}）备注同步未完成："
                    f"追加后为 {remark_length} 个字符，超过 {MAX_CHANNEL_REMARK_LENGTH} 字符上限"
                ),
            )
            result.items.append(item)
            continue

        result.matched_count += 1
        item.update(
            success=True,
            preview=dry_run,
            remark_length=remark_length,
            message=(
                f"{'将' if dry_run else '已'}把 {source_label}「{source_value}」"
                f"{'写入' if not channel.get('remark') else '追加到'}备注（ID={channel_id}）"
            ),
        )
        if dry_run:
            result.items.append(item)
            continue

        try:
            # 只提交 id 与 remark，避免完整渠道对象的空字段覆盖其他配置。
            client.update_channel({"id": channel_id, "remark": next_remark})
            result.updated_count += 1
        except Exception as exc:  # noqa: BLE001
            result.failed_count += 1
            item.update(
                success=False,
                message=f"渠道「{name}」（ID={channel_id}）备注同步未完成：{exc}",
            )
        result.items.append(item)

    return result
