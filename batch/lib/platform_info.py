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
        raise RuntimeError("ai-cloud 账号没有管理端权限，无法读取渠道或令牌管理")
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


def list_channels(client: NewAPIClient) -> list[dict[str, Any]]:
    """拉取渠道管理列表（不含明文密钥），附带近一月活跃统计。"""
    rows = client.list_all_channels()
    try:
        stats = client.fetch_channel_activity_stats(rows)
    except Exception:
        stats = []
    stat_map: dict[int, dict[str, Any]] = {}
    for entry in stats:
        if isinstance(entry, dict) and entry.get("channel_id"):
            stat_map.setdefault(int(entry["channel_id"]), entry)
    for row in rows:
        stat = stat_map.get(int(row.get("id") or 0))
        if stat:
            row["activity_stats"] = stat
    return rows


def get_channel(client: NewAPIClient, channel_id: int) -> dict[str, Any]:
    """拉取单个渠道完整记录（不含明文密钥）。"""
    response = client.session.get(
        f"{client.base_url}/api/channel/{int(channel_id)}",
        headers=client._headers(),
        timeout=client.timeout,
    )
    data = _api_data(response, "获取渠道详情失败")
    if not isinstance(data, dict):
        raise RuntimeError("渠道详情格式异常")
    return data


def update_channel(client: NewAPIClient, channel_id: int, record: dict[str, Any]) -> dict[str, Any]:
    body = dict(record)
    body["id"] = int(channel_id)
    return client.update_channel(body)


def test_channel(client: NewAPIClient, channel_id: int, model: str = "") -> dict[str, Any]:
    """测试指定渠道连通性，与 ai-cloud 渠道管理「测试」按钮一致。"""
    return client.test_channel(int(channel_id), model=model)


def update_channel_status(client: NewAPIClient, channel_id: int, status: int) -> dict[str, Any]:
    """更新渠道状态：1=启用，2=手动禁用。"""
    return client.update_channel_status(int(channel_id), status)


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
