"""ai-cloud / New API 平台信息的读取与编辑适配。"""

from __future__ import annotations

from typing import Any

from .api_client import NewAPIClient, authenticate_client


def _api_data(response: Any, fallback_message: str) -> Any:
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict) or not payload.get("success"):
        message = payload.get("message") if isinstance(payload, dict) else ""
        raise RuntimeError(str(message or fallback_message))
    return payload.get("data")


def connected_client(base_url: str, auth: dict[str, Any]) -> NewAPIClient:
    """建立已认证的管理端会话，复用项目原有的登录与 TOTP 会话缓存。"""
    client = NewAPIClient(base_url)
    authenticate_client(client, auth)
    if not client.is_admin():
        raise RuntimeError("ai-cloud 账号没有管理端权限，无法读取模型或令牌管理")
    return client


def list_models(client: NewAPIClient, page_size: int = 100) -> list[dict[str, Any]]:
    """拉取模型管理分页列表，兼容旧版数组与新版 items 响应。"""
    page = 1
    page_size = min(max(1, int(page_size)), 100)
    rows: list[dict[str, Any]] = []
    while True:
        response = client.session.get(
            f"{client.base_url}/api/models/",
            params={"p": page, "size": page_size},
            headers=client._headers(),
            timeout=client.timeout,
        )
        data = _api_data(response, "获取模型列表失败")
        if isinstance(data, list):
            batch = data
            total = len(batch)
        elif isinstance(data, dict):
            batch = data.get("items") or []
            total = data.get("total", len(rows) + len(batch))
        else:
            batch = []
            total = 0
        if not isinstance(batch, list):
            raise RuntimeError("模型列表格式异常")
        rows.extend(item for item in batch if isinstance(item, dict))
        try:
            done = len(rows) >= int(total)
        except (TypeError, ValueError):
            done = len(batch) < page_size
        if done or not batch:
            break
        page += 1
    rows.sort(key=lambda row: int(row.get("id") or 0), reverse=True)
    return rows


def get_model(client: NewAPIClient, model_id: int) -> dict[str, Any]:
    response = client.session.get(
        f"{client.base_url}/api/models/{int(model_id)}",
        headers=client._headers(),
        timeout=client.timeout,
    )
    data = _api_data(response, "获取模型详情失败")
    if not isinstance(data, dict):
        raise RuntimeError("模型详情格式异常")
    return data


def update_model(client: NewAPIClient, model_id: int, record: dict[str, Any]) -> dict[str, Any]:
    body = dict(record)
    body["id"] = int(model_id)
    response = client.session.put(
        f"{client.base_url}/api/models/",
        json=body,
        headers=client._headers(),
        timeout=client.timeout,
    )
    data = _api_data(response, "更新模型失败")
    return data if isinstance(data, dict) else {"result": data}


def list_tokens(client: NewAPIClient) -> list[dict[str, Any]]:
    """令牌列表直接沿用项目已验证的 NewAPIClient 分页实现。"""
    return client.list_all_tokens()


def get_token(client: NewAPIClient, token_id: int) -> dict[str, Any]:
    return client.get_token(int(token_id))


def update_token(client: NewAPIClient, token_id: int, record: dict[str, Any]) -> dict[str, Any]:
    body = dict(record)
    body["id"] = int(token_id)
    return client.update_token(body, preserve_token_model_rate_limits=True)
