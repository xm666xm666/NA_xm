"""令牌 API 模型限制字段兼容（新旧命名）。"""

from __future__ import annotations

from typing import Any


def read_model_limits(token: dict[str, Any]) -> tuple[bool, str]:
    """读取令牌模型限制。兼容 model_limits* 与 token_model_limit* 两套字段名。"""
    candidates = (
        (
            bool(token.get("model_limits_enabled")),
            str(token.get("model_limits") or "").strip(),
        ),
        (
            bool(token.get("token_model_limit_enabled")),
            str(token.get("token_model_limit") or "").strip(),
        ),
    )
    for enabled, limits in candidates:
        if enabled and limits:
            return enabled, limits
    for enabled, limits in candidates:
        if limits:
            return enabled, limits
    return False, ""


def apply_model_limits(body: dict[str, Any], model_limit: str) -> dict[str, Any]:
    """写入请求体，同时携带新旧两套字段名以兼容不同 New API 版本。"""
    model_limit = (model_limit or "").strip()
    if not model_limit:
        return body

    body["model_limits"] = model_limit
    body["model_limits_enabled"] = True
    body["token_model_limit"] = model_limit
    body["token_model_limit_enabled"] = True
    return body


def extract_model_limit(body: dict[str, Any]) -> str:
    return str(
        body.get("model_limits")
        or body.get("token_model_limit")
        or ""
    ).strip()


def apply_monthly_token_quota(body: dict[str, Any], tokens: int | None) -> dict[str, Any]:
    """把批量配置第 4 列写入 v1.0.3 的自然月 Token 限制。"""
    payload = dict(body)
    payload.update(
        {
            "amount_limit_enabled": False,
            "unlimited_quota": True,
            "remain_quota": 0,
            "input_token_limit_enabled": tokens is not None,
            "input_token_period": "month" if tokens is not None else "",
            "input_token_limit_k": str(tokens // 1000) if tokens is not None else "",
        }
    )
    return payload


def legacy_token_quota_payload(body: dict[str, Any]) -> dict[str, Any]:
    """将 v1.0.3 编辑器字段降级为老版本 New API 字段。"""
    payload = dict(body)
    amount_limit_enabled = payload.pop("amount_limit_enabled", None)
    unlimited_quota = payload.pop("unlimited_quota", None)
    if amount_limit_enabled is not None:
        unlimited_quota = not bool(amount_limit_enabled)
    if unlimited_quota is not None:
        payload["unlimited_quota"] = bool(unlimited_quota)
    payload.pop("input_token_limit_enabled", None)
    payload.pop("input_token_period", None)
    payload.pop("input_token_limit_k", None)
    return payload
