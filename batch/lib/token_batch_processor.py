"""批量创建令牌处理器。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .api_client import NewAPIClient, authenticate_client
from .channel_models import build_group_model_index, serialize_group_model_index
from .token_api_fields import extract_model_limit, read_model_limits
from .token_builder import (
    build_token_payload,
    parse_batch_rows,
    parse_model_list,
    token_has_model_limits,
    validate_group_exists,
    validate_models_in_group,
)
from .group_manager import ensure_groups_for_rows
from .token_duplicate_checker import (
    build_name_index,
    find_existing_duplicate,
    is_batch_duplicate,
)
from .token_key_resolver import TokenKeyResolver, is_masked_key
from .token_export import format_token_key


@dataclass
class TokenBatchResult:
    total: int = 0
    success_count: int = 0
    failed_count: int = 0
    skipped_count: int = 0
    items: list[dict[str, Any]] = field(default_factory=list)



def _find_token_by_name_group(
    tokens: list[dict[str, Any]], name: str, group: str
) -> dict[str, Any] | None:
    for token in tokens:
        if str(token.get("name") or "").strip() != name:
            continue
        if str(token.get("group") or "").strip() != group:
            continue
        return token
    return None


def _build_update_payload(
    existing: dict[str, Any], limits_payload: dict[str, Any]
) -> dict[str, Any]:
    payload = {
        "id": int(existing["id"]),
        "name": existing.get("name") or limits_payload.get("name"),
        "group": existing.get("group") or limits_payload.get("group"),
        "status": existing.get("status", 1),
        "remain_quota": existing.get("remain_quota", 0),
        "expired_time": existing.get("expired_time", -1),
        "unlimited_quota": existing.get("unlimited_quota", True),
        "cross_group_retry": existing.get("cross_group_retry", False),
        **limits_payload,
    }
    for key in (
        "amount_limit_enabled",
        "unlimited_quota",
        "remain_quota",
        "input_token_limit_enabled",
        "input_token_period",
        "input_token_limit_k",
    ):
        if key in limits_payload:
            payload[key] = limits_payload[key]
    return payload


def _ensure_token_model_limits(
    client: NewAPIClient,
    payload: dict[str, Any],
    *,
    name: str,
    group: str,
) -> None:
    expected = extract_model_limit(payload)
    if not expected:
        raise ValueError("模型限制不能为空")

    tokens = client.list_all_tokens()
    created = _find_token_by_name_group(tokens, name, group)
    if not created:
        raise RuntimeError(f"创建后未找到令牌: {name}")

    if token_has_model_limits(created, expected):
        return

    update_payload = _build_update_payload(created, payload)
    client.update_token(update_payload)

    verified = client.get_token(int(created["id"]))
    if not token_has_model_limits(verified, expected):
        enabled, current = read_model_limits(verified)
        raise RuntimeError(
            f"模型限制写入失败（enabled={enabled}, limits={current or '空'}）"
        )


def _capture_created_key(
    resolver: TokenKeyResolver,
    client: NewAPIClient,
    *,
    name: str,
    group: str,
) -> str:
    tokens = client.list_all_tokens()
    created = _find_token_by_name_group(tokens, name, group)
    if not created:
        return ""

    plain = resolver.resolve(created)
    if plain and not is_masked_key(plain):
        resolver.remember_created(created, plain)
        return format_token_key(plain)

    token_id = created.get("id")
    if token_id is not None:
        try:
            fetched = client.fetch_token_key(int(token_id))
            if fetched and not is_masked_key(fetched):
                plain_key = format_token_key(fetched)
                resolver.remember_created(created, plain_key)
                return plain_key
        except Exception:  # noqa: BLE001
            pass

    return ""


def run_token_batch_create(
    *,
    base_url: str,
    batch_text: str,
    auth: dict[str, Any],
) -> TokenBatchResult:
    rows = parse_batch_rows(batch_text)
    if not rows:
        raise ValueError("没有可处理的批量数据，请直接粘贴数据行（无需表头）")

    client = NewAPIClient(base_url)
    authenticate_client(client, auth)
    client.get_status()

    key_resolver = TokenKeyResolver.build(
        base_url=base_url,
        user_id=client.user_id,
    )

    created_groups = ensure_groups_for_rows(client, rows)
    known_groups = set(client.list_user_groups())
    if not known_groups:
        raise ValueError("未能从站点获取用户可用分组，请确认登录凭据")

    channels = client.list_all_channels()
    group_models = build_group_model_index(channels)
    existing_tokens = client.list_all_tokens()
    name_index = build_name_index(existing_tokens)
    batch_seen: set[str] = set()

    result = TokenBatchResult(total=len(rows))
    for index, row in enumerate(rows, start=1):
        name = row.get("名称") or row.get("name") or f"row-{index}"
        try:
            skip_reason = is_batch_duplicate(row, batch_seen)
            if skip_reason:
                result.skipped_count += 1
                result.items.append(
                    {
                        "index": index,
                        "name": name,
                        "success": True,
                        "skipped": True,
                        "message": skip_reason,
                    }
                )
                continue

            dup_existing = find_existing_duplicate(row, name_index)
            if dup_existing:
                raise ValueError(dup_existing)

            group = str(row.get("分组") or "").strip()
            validate_group_exists(group, known_groups)

            models = parse_model_list(str(row.get("模型限制") or ""))
            validate_models_in_group(models, group=group, channels=channels)

            payload = build_token_payload(
                row,
                monthly_tokens=client.supports_token_input_quota(),
            )
            if not extract_model_limit(payload):
                raise ValueError("模型限制列表不能为空")

            client.create_token(payload)
            _ensure_token_model_limits(
                client, payload, name=str(name), group=group
            )
            captured_key = _capture_created_key(
                key_resolver, client, name=str(name), group=group
            )

            model_hint = extract_model_limit(payload).replace(",", "、")
            quota_hint = (
                "无限额度"
                if payload.get("unlimited_quota")
                else f"额度 {payload.get('remain_quota')} tokens"
            )
            result.success_count += 1
            message = f"创建成功（{quota_hint}），可用模型: {model_hint}"
            if group in created_groups:
                message = f"已自动创建分组「{group}」；{message}"
            if captured_key:
                message += "（秘钥已写入本地库）"
            elif key_resolver.sources:
                message += "（秘钥来源: " + "、".join(key_resolver.sources) + "）"
            result.items.append(
                {
                    "index": index,
                    "name": name,
                    "success": True,
                    "unlimited_quota": bool(payload.get("unlimited_quota")),
                    "remain_quota": int(payload.get("remain_quota") or 0),
                    "message": message,
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

    result.items.insert(
        0,
        {
            "meta": True,
            "user_groups": sorted(known_groups),
            "group_models": serialize_group_model_index(group_models),
            "existing_token_count": len(existing_tokens),
        },
    )
    return result


def fetch_channel_models(
    *,
    base_url: str,
    auth: dict[str, Any],
) -> dict[str, Any]:
    client = NewAPIClient(base_url)
    authenticate_client(client, auth)
    channels = client.list_all_channels()
    group_models = serialize_group_model_index(build_group_model_index(channels))
    user_groups = sorted(client.list_user_groups())
    return {
        "user_groups": user_groups,
        "group_models": group_models,
        "channel_count": len(channels),
    }
