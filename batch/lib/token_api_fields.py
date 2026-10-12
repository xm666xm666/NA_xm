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
