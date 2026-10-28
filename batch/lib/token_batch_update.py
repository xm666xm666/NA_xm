"""按名称+分组预览并更新已有令牌的额度（tokens）。"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from .api_client import NewAPIClient, authenticate_client
from .token_api_fields import apply_model_limits, read_model_limits
from .token_builder import parse_optional_token_quota, parse_token_line
from .token_duplicate_checker import build_existing_index, token_name_group


@dataclass
class TokenQuotaUpdateResult:
    total: int = 0
    matched_count: int = 0
    updated_count: int = 0
    skipped_count: int = 0
    failed_count: int = 0
    dry_run: bool = True
    items: list[dict[str, Any]] = field(default_factory=list)


def _is_header_line(line: str) -> bool:
    text = str(line or "").strip()
    first = text.lstrip("\ufeff").split()[0] if text else ""
    return first in {"名称", "name", "分组"}


def _compact_quota_row(line: str) -> dict[str, str] | None:
    """解析额度更新专用的精简三列：名称、分组、额度(tokens)。"""
    text = str(line or "").strip()
    if "\t" in text:
        parts = [part.strip() for part in text.split("\t")]
    elif text.count(",") == 2:
        parts = [part.strip() for part in text.split(",")]
    else:
        parts = re.split(r"\s+", text)
    if len(parts) != 3 or not parts[0] or not parts[1]:
        return None

    # 三列旧格式的第 3 列是模型；仅当它确实像数值时才把它解释成额度。
    if not re.fullmatch(r"[+-]?\d+(?:\.\d+)?", parts[2]):
        return None
    quota = parse_optional_token_quota(parts[2])
    if quota is None:
        return None
    return {"名称": parts[0], "分组": parts[1], "额度(tokens)": str(quota)}


def parse_token_quota_update_rows(text: str) -> list[dict[str, str]]:
    """解析额度更新数据。

    支持完整令牌行 ``名称 分组 模型列表 额度``，也支持更新专用精简行
    ``名称 分组 额度``。额度必须显式提供，省略时绝不推断为无限额度。
    """
    rows: list[dict[str, str]] = []
    for index, raw in enumerate((text or "").splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#") or _is_header_line(line):
            continue
        try:
            parsed = parse_token_line(line)
        except ValueError as exc:
            try:
                compact = _compact_quota_row(line)
            except ValueError as quota_exc:
                raise ValueError(f"第 {index} 行额度无效：{quota_exc}") from quota_exc
            if compact is None:
                raise ValueError(f"第 {index} 行无法解析：{exc}") from exc
            rows.append(compact)
            continue

        if parsed.get("额度(tokens)"):
            rows.append(
                {
                    "名称": str(parsed.get("名称") or "").strip(),
                    "分组": str(parsed.get("分组") or "").strip(),
                    "额度(tokens)": str(parsed["额度(tokens)"]),
                }
            )
            continue

        try:
            compact = _compact_quota_row(line)
        except ValueError as exc:
            raise ValueError(f"第 {index} 行额度无效：{exc}") from exc
        if compact:
            rows.append(compact)
            continue
        raise ValueError(
            f"第 {index} 行缺少额度(tokens)。更新仅处理明确填写额度的行，"
            "格式：名称 分组 额度，或完整令牌行的第 4 列额度。"
        )
    return rows


def _as_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _quota_label(unlimited: bool, quota: int) -> str:
    return "无限额度" if unlimited else f"{quota} tokens"


def _existing_monthly_tokens(existing: dict[str, Any]) -> int | None:
    if not existing.get("input_token_limit_enabled"):
        return None
    limit_k = str(existing.get("input_token_limit_k") or "").strip()
    if limit_k:
        return _as_int(limit_k) * 1000
    raw_limit = existing.get("input_token_limit")
    return _as_int(raw_limit) if raw_limit not in (None, "") else None


def _describe_quota_change(
    existing: dict[str, Any],
    quota: int,
    *,
    monthly_tokens: bool = False,
) -> str:
    if monthly_tokens:
        old_quota = _existing_monthly_tokens(existing)
        before = "无限月Tokens" if old_quota is None else f"{old_quota} tokens"
        if old_quota == quota:
            return "额度无变化"
        return f"月Tokens「{before}」→「{quota} tokens」"
    old_unlimited = bool(existing.get("unlimited_quota"))
    old_quota = _as_int(existing.get("remain_quota"))
    before = _quota_label(old_unlimited, old_quota)
    after = _quota_label(False, quota)
    if not old_unlimited and old_quota == quota:
        return "额度无变化"
    return f"额度「{before}」→「{after}」"


def _build_quota_update_payload(
    existing: dict[str, Any],
    quota: int,
    *,
    monthly_tokens: bool = False,
) -> dict[str, Any]:
    """构造完整 PUT 请求体，只替换额度字段并原样保留其他令牌配置。"""
    model_limits_enabled, model_limits = read_model_limits(existing)
    payload: dict[str, Any] = {
        "id": _as_int(existing.get("id")),
        "name": str(existing.get("name") or "").strip(),
        "status": _as_int(existing.get("status"), 1),
        "expired_time": _as_int(existing.get("expired_time"), -1),
        "group": str(existing.get("group") or "").strip(),
        "cross_group_retry": bool(existing.get("cross_group_retry")),
        "allow_ips": existing.get("allow_ips"),
        # 上游更新接口会整体写回模型限流；必须带回现有值，不能因调额度而清空。
        "token_model_rate_limits": existing.get("token_model_rate_limits") or [],
    }
    if monthly_tokens:
        if quota % 1000 != 0:
            raise ValueError("v1.0.3 月Tokens额度必须为1000的整数倍")
        payload.update(
            {
                "amount_limit_enabled": False,
                "unlimited_quota": True,
                "remain_quota": 0,
                "input_token_limit_enabled": True,
                "input_token_period": "month",
                "input_token_limit_k": str(quota // 1000),
            }
        )
    else:
        payload.update({"remain_quota": quota, "unlimited_quota": False})
    if model_limits:
        apply_model_limits(payload, model_limits)
    else:
        payload["token_model_limit_enabled"] = bool(model_limits_enabled)
        payload["token_model_limit"] = str(existing.get("token_model_limit") or "")
    return payload


def run_token_batch_quota_update(
    *,
    base_url: str,
    batch_text: str,
    auth: dict[str, Any],
    dry_run: bool = True,
) -> TokenQuotaUpdateResult:
    rows = parse_token_quota_update_rows(batch_text)
    if not rows:
        raise ValueError("没有可处理的额度更新数据")

    client = NewAPIClient(base_url)
    authenticate_client(client, auth)
    client.get_status()

    existing_tokens = client.list_all_tokens()
    existing_index = build_existing_index(existing_tokens)
    seen_pairs: set[tuple[str, str]] = set()
    result = TokenQuotaUpdateResult(total=len(rows), dry_run=dry_run)
    monthly_tokens = client.supports_token_input_quota()

    for index, row in enumerate(rows, start=1):
        name = str(row.get("名称") or "").strip()
        group = str(row.get("分组") or "").strip()
        try:
            quota = parse_optional_token_quota(row.get("额度(tokens)"))
            if quota is None:
                raise ValueError("缺少额度(tokens)")
            if not name or not group:
                raise ValueError("名称或分组不能为空")

            pair = token_name_group(name, group)
            if pair in seen_pairs:
                result.skipped_count += 1
                result.items.append(
                    {
                        "index": index,
                        "name": name,
                        "group": group,
                        "success": True,
                        "skipped": True,
                        "message": "批量内重复，已跳过",
                    }
                )
                continue
            seen_pairs.add(pair)

            existing = existing_index.get(pair)
            if not existing or existing.get("id") is None:
                result.skipped_count += 1
                result.items.append(
                    {
                        "index": index,
                        "name": name,
                        "group": group,
                        "success": True,
                        "skipped": True,
                        "message": f"未找到匹配令牌（{name} / {group}）",
                    }
                )
                continue

            token_id = _as_int(existing.get("id"))
            change = _describe_quota_change(existing, quota, monthly_tokens=monthly_tokens)
            if change == "额度无变化":
                result.skipped_count += 1
                result.items.append(
                    {
                        "index": index,
                        "name": name,
                        "group": group,
                        "success": True,
                        "skipped": True,
                        "target_id": token_id,
                        "message": f"ID={token_id} 额度无变化，已跳过",
                    }
                )
                continue

            result.matched_count += 1
            if dry_run:
                result.items.append(
                    {
                        "index": index,
                        "name": name,
                        "group": group,
                        "success": True,
                        "preview": True,
                        "target_id": token_id,
                        "message": f"预更新 ID={token_id}「{name}」：{change}",
                    }
                )
                continue

            # 使用详情接口拿到完整字段，避免 PUT 时覆盖模型限制、IP 白名单等现有配置。
            current = client.get_token(token_id)
            current_change = _describe_quota_change(current, quota, monthly_tokens=monthly_tokens)
            if current_change == "额度无变化":
                result.skipped_count += 1
                result.items.append(
                    {
                        "index": index,
                        "name": name,
                        "group": group,
                        "success": True,
                        "skipped": True,
                        "target_id": token_id,
                        "message": f"ID={token_id} 额度已在预览后变更，当前无需更新",
                    }
                )
                continue

            payload = _build_quota_update_payload(
                current,
                quota,
                monthly_tokens=monthly_tokens,
            )
            client.update_token(payload, preserve_token_model_rate_limits=True)
            result.updated_count += 1
            result.items.append(
                {
                    "index": index,
                    "name": name,
                    "group": group,
                    "success": True,
                    "target_id": token_id,
                    "message": f"已更新 ID={token_id}「{name}」：{current_change}",
                }
            )
            existing_index[pair] = {
                **current,
            }
            if monthly_tokens:
                existing_index[pair].update(
                    {
                        "amount_limit_enabled": False,
                        "unlimited_quota": True,
                        "remain_quota": 0,
                        "input_token_limit_enabled": True,
                        "input_token_period": "month",
                        "input_token_limit_k": str(quota // 1000),
                    }
                )
            else:
                existing_index[pair].update(
                    {"remain_quota": quota, "unlimited_quota": False}
                )
        except Exception as exc:  # noqa: BLE001
            result.failed_count += 1
            result.items.append(
                {
                    "index": index,
                    "name": name or f"row-{index}",
                    "group": group,
                    "success": False,
                    "message": str(exc),
                }
            )

    return result
