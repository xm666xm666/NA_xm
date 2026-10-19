"""ai-cloud / New API 平台信息的读取与编辑适配。"""

from __future__ import annotations

import hashlib
import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import requests

from .api_client import NewAPIClient, authenticate_client

_CLIENT_CACHE: dict[str, tuple[NewAPIClient, float]] = {}
_CLIENT_CACHE_LOCK = threading.Lock()
_CLIENT_CACHE_TTL_SEC = 2 * 60 * 60.0
_CAPABILITY_CACHE: dict[str, tuple[dict[str, bool], float]] = {}
_CAPABILITY_CACHE_LOCK = threading.Lock()
_CAPABILITY_CACHE_TTL_SEC = 10 * 60.0


def _api_data(response: Any, fallback_message: str) -> Any:
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict) or not payload.get("success"):
        message = payload.get("message") if isinstance(payload, dict) else ""
        raise RuntimeError(str(message or fallback_message))
    return payload.get("data")


_CAPABILITY_PROBES: tuple[tuple[str, str, str, dict[str, Any] | None], ...] = (
    ("channels", "GET", "/api/channel/", {"p": 1, "size": 1}),
    ("tokens", "GET", "/api/token/", {"p": 1, "size": 1}),
    ("admin_groups", "GET", "/api/group/", None),
    ("user_groups", "GET", "/api/user/self/groups", None),
    ("legacy_user_groups", "GET", "/api/user/groups", None),
    ("user_models", "GET", "/api/user/models", None),
    ("dashboard_models", "GET", "/api/models", {"p": 1, "size": 1}),
    ("channel_models", "GET", "/api/channel/models", None),
    ("prefill_groups", "GET", "/api/prefill_group/", {"type": "model"}),
    ("two_factor", "GET", "/api/user/2fa/status", None),
    ("passkey", "GET", "/api/user/passkey", None),
    ("token_quota_capabilities", "GET", "/api/token/model_quota_capabilities", None),
    ("token_quota_candidates", "GET", "/api/token/model_quota_candidates", None),
    ("model_quotas", "GET", "/api/model_quota/", None),
)


def _capability_cache_key(client: NewAPIClient) -> str:
    return f"{client.base_url.rstrip('/')}#user:{int(client.user_id or 0)}"


def _probe_capability(
    client: NewAPIClient,
    method: str,
    path: str,
    params: dict[str, Any] | None,
) -> bool:
    session = requests.Session()
    try:
        session.headers.update(client.session.headers)
        session.cookies.update(client.session.cookies)
        session.verify = client.session.verify
        response = session.request(
            method,
            f"{client.base_url.rstrip('/')}{path}",
            params=params,
            headers=client._headers(),
            timeout=min(float(client.timeout), 8.0),
        )
        return response.status_code != 404 and response.status_code < 500
    except Exception:
        return False
    finally:
        session.close()


def probe_capabilities(client: NewAPIClient, *, force_refresh: bool = False) -> dict[str, bool]:
    """探测当前上游版本是否提供编辑器主要接口；只使用只读 GET 请求。"""
    cache_key = _capability_cache_key(client)
    now = time.time()
    if not force_refresh:
        with _CAPABILITY_CACHE_LOCK:
            entry = _CAPABILITY_CACHE.get(cache_key)
            if entry and entry[1] > now:
                return dict(entry[0])

    with ThreadPoolExecutor(max_workers=6) as executor:
        futures = {
            name: executor.submit(_probe_capability, client, method, path, params)
            for name, method, path, params in _CAPABILITY_PROBES
        }
        capabilities = {name: bool(future.result()) for name, future in futures.items()}

    with _CAPABILITY_CACHE_LOCK:
        _CAPABILITY_CACHE[cache_key] = (dict(capabilities), now + _CAPABILITY_CACHE_TTL_SEC)
    return capabilities


def connected_client(base_url: str, auth: dict[str, Any]) -> NewAPIClient:
    """建立并复用已认证的管理端会话；同一站点凭据不重复登录。"""
    signature_payload = {
        "base_url": base_url,
        "username": str(auth.get("username") or ""),
        "password": str(auth.get("password") or ""),
        "access_token": str(auth.get("access_token") or ""),
        "user_id": auth.get("user_id"),
        "totp_secret": str(auth.get("totp_secret") or ""),
        "verify_ssl": auth.get("verify_ssl", True),
    }
    signature = hashlib.sha256(
        json.dumps(signature_payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()
    now = time.time()
    with _CLIENT_CACHE_LOCK:
        entry = _CLIENT_CACHE.get(signature)
        if entry:
            client, expires_at = entry
            if expires_at >= now and client.is_admin():
                client.session_cache_hit = True
                client.session_cache_expires_at = expires_at
                return client
            _CLIENT_CACHE.pop(signature, None)

    client = NewAPIClient(base_url)
    authenticate_client(client, auth)
    if not client.is_admin():
        raise RuntimeError("ai-cloud 账号没有管理端权限，无法读取渠道或令牌管理")
    with _CLIENT_CACHE_LOCK:
        _CLIENT_CACHE[signature] = (client, now + _CLIENT_CACHE_TTL_SEC)
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
    pairs: list[dict[str, Any]] = []
    seen: set[tuple[int, str]] = set()
    for row in rows:
        models_raw = str(row.get("models") or "")
        for model_name in models_raw.split(","):
            model_name = model_name.strip()
            if not model_name:
                continue
            key = (int(row.get("id") or 0), model_name)
            if key in seen:
                continue
            seen.add(key)
            pairs.append({"channel_id": key[0], "model_name": model_name})
    stat_map: dict[tuple[int, str], dict[str, Any]] = {}
    if pairs:
        try:
            stats = client.fetch_channel_activity_stats(pairs)
        except Exception:
            stats = []
        for entry in stats:
            if isinstance(entry, dict) and entry.get("channel_id") and entry.get("model_name"):
                stat_map[(int(entry["channel_id"]), str(entry["model_name"]))] = entry
    for row in rows:
        row_id = int(row.get("id") or 0)
        model_names = [m.strip() for m in str(row.get("models") or "").split(",") if m.strip()]
        row["activity_stats_models"] = model_names
        matched = [stat_map[(row_id, m)] for m in model_names if (row_id, m) in stat_map]
        row["activity_stats"] = matched if matched else None
    rows.sort(key=lambda row: int(row.get("id") or 0), reverse=True)
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


def delete_channel(client: NewAPIClient, channel_id: int) -> dict[str, Any]:
    """删除单个渠道，复用 ai-cloud 的批量删除接口。"""
    deleted = client.delete_channels_batch([int(channel_id)])
    if deleted < 1:
        raise RuntimeError("渠道删除失败")
    return {"deleted": deleted}


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


def update_token_status(client: NewAPIClient, token_id: int, status: int) -> dict[str, Any]:
    """更新令牌状态：1=启用，2=手动禁用。"""
    return client.update_token_status(int(token_id), status)


def delete_token(client: NewAPIClient, token_id: int) -> dict[str, Any]:
    """删除单个令牌，复用 ai-cloud 的批量删除接口。"""
    deleted = client.delete_tokens_batch([int(token_id)])
    if deleted < 1:
        raise RuntimeError("令牌删除失败")
    return {"deleted": deleted}
