# -*- coding: utf-8 -*-
"""Azure Resource Manager 客户端（Cognitive Services / Azure OpenAI 管控面）。"""

from __future__ import annotations

import random
import time
from typing import Any
from urllib.parse import urlparse

import requests

ARM_RESOURCE = "https://management.azure.com"
ARM_SCOPE = "https://management.azure.com/.default"
DEFAULT_API_VERSION = "2024-10-01"
COST_API_VERSION = "2023-11-01"
DEFAULT_SUBSCRIPTION_ID = "76c8315b-d084-4f21-8003-cf6365e711bb"
DEFAULT_TENANT_ID = "6109af82-53f7-4f47-8dc8-4a4d75107e49"
DEFAULT_TENANT_HOST = "PharmaronClinical.onmicrosoft.com"


def parse_subscription_entries(*sources: Any, default: str | None = DEFAULT_SUBSCRIPTION_ID) -> list[dict[str, str]]:
    """解析订阅列表，返回 [{id, label}, ...]；未具名时按顺序标为 订阅1、订阅2。"""
    entries: list[dict[str, str]] = []
    seen: set[str] = set()

    def add_id(sub_id: str, label: str = "") -> None:
        item = str(sub_id or "").strip()
        if not item or item.startswith("#"):
            return
        key = item.lower()
        if key in seen:
            return
        seen.add(key)
        entries.append({"id": item, "label": str(label or "").strip()})

    def add(value: Any) -> None:
        if value is None or value is False:
            return
        if isinstance(value, dict):
            add_id(
                str(value.get("id") or value.get("subscription_id") or value.get("guid") or ""),
                str(value.get("name") or value.get("label") or value.get("alias") or ""),
            )
            return
        if isinstance(value, (list, tuple, set)):
            for item in value:
                add(item)
            return
        text = str(value).replace(",", "\n").replace(";", "\n")
        for part in text.splitlines():
            item = part.strip()
            if not item or item.startswith("#"):
                continue
            if "|" in item:
                left, right = item.split("|", 1)
                if _looks_like_guid(left.strip()):
                    add_id(left.strip(), right.strip())
                elif _looks_like_guid(right.strip()):
                    add_id(right.strip(), left.strip())
                else:
                    add_id(item)
            else:
                add_id(item)

    for src in sources:
        add(src)
    if not entries:
        fallback = (default or "").strip()
        if fallback:
            add_id(fallback)
    for index, entry in enumerate(entries, start=1):
        label = entry["label"]
        if not label:
            entry["label"] = f"订阅{index}"
        elif label.isdigit():
            entry["label"] = f"订阅{label}"
        elif label.lower().startswith("sub") and label[3:].isdigit():
            entry["label"] = f"订阅{label[3:]}"
    return entries


def _looks_like_guid(text: str) -> bool:
    raw = str(text or "").strip()
    if len(raw) < 32:
        return False
    compact = raw.replace("-", "")
    return len(compact) == 32 and all(ch in "0123456789abcdefABCDEF" for ch in compact)


def normalize_subscription_ids(*sources: Any, default: str | None = DEFAULT_SUBSCRIPTION_ID) -> list[str]:
    """从字符串 / 列表 / 多行文本收集订阅 ID，去重且保序。"""
    return [item["id"] for item in parse_subscription_entries(*sources, default=default)]


class AzureARMError(RuntimeError):
    def __init__(self, message: str, *, status: int = 0, raw: Any = None):
        super().__init__(message)
        self.status = status
        self.raw = raw


def acquire_arm_token(tenant_id: str, client_id: str, client_secret: str) -> str:
    """用 Entra ID 服务主体换 ARM Bearer Token。"""
    tenant = (tenant_id or "").strip()
    if not tenant:
        raise AzureARMError("缺少 tenant_id（目录 ID，如 6109af82-53f7-4f47-8dc8-4a4d75107e49）")
    if not (client_id or "").strip() or not (client_secret or "").strip():
        raise AzureARMError("缺少 client_id / client_secret（应用注册密钥）")
    url = f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token"
    try:
        resp = requests.post(
            url,
            data={
                "client_id": client_id.strip(),
                "client_secret": client_secret.strip(),
                "scope": ARM_SCOPE,
                "grant_type": "client_credentials",
            },
            timeout=30,
        )
    except requests.RequestException as exc:
        raise AzureARMError(f"获取 Azure Token 失败: {exc}") from exc
    try:
        payload = resp.json()
    except ValueError:
        payload = {}
    if resp.status_code >= 400:
        desc = (
            str(payload.get("error_description") or payload.get("error") or "").strip()
            or resp.text[:300]
        )
        raise AzureARMError(f"Azure 登录失败 HTTP {resp.status_code}: {desc}", status=resp.status_code, raw=payload)
    token = str(payload.get("access_token") or "").strip()
    if not token:
        raise AzureARMError("Azure 登录成功但未返回 access_token", raw=payload)
    return token


def _format_arm_http_error(status: int, message: str) -> str:
    text = f"ARM HTTP {status}: {message}"
    blob = (message or "").lower()
    if status == 429 or "too many requests" in blob:
        text += " 请求过于频繁，将自动等待后重试；若仍失败请隔一两分钟再采集。"
    if status == 403 and ("does not have authorization" in blob or "authorization" in blob):
        text += (
            " 凭证已通过，但应用还没有订阅权限。"
            "请打开订阅 76c8315b-d084-4f21-8003-cf6365e711bb → 访问控制(IAM) → 添加角色分配，"
            "成员选应用 na-upstream-collector（不要选个人账号），"
            "每个要采集的订阅都必须同时加「读取者」和「认知服务用户」（Cognitive Services User，才能 listKeys）。"
        )
        if "costmanagement" in blob or "microsoft.costmanagement" in blob:
            text += " 拉成本分析还须加「成本管理读取者」（Cost Management Reader）。"
        text += " 刚加完等 1～2 分钟再测。"
    return text


_RETRY_STATUSES = {429, 503}
_RETRY_HEADER_KEYS = (
    "retry-after",
    "x-ms-ratelimit-microsoft.costmanagement-qpu-retry-after",
    "x-ms-ratelimit-remaining-microsoft.costmanagement-qpu-retry-after",
)


def _header_map(resp: Any) -> dict[str, str]:
    headers = getattr(resp, "headers", None) or {}
    return {str(key).lower(): str(value) for key, value in headers.items()}


def retry_after_seconds(resp: Any, attempt: int) -> float:
    """attempt 从 0 起。优先 Retry-After / Cost Management QPU 头，否则指数退避。"""
    headers = _header_map(resp)
    for key in _RETRY_HEADER_KEYS:
        raw = headers.get(key)
        if not raw:
            continue
        try:
            return min(max(float(raw), 1.0), 60.0)
        except ValueError:
            continue
    return min(45.0, (2.0 ** attempt) + random.uniform(0.4, 1.6))


class AzureARMClient:
    def __init__(self, access_token: str, *, subscription_id: str = "", api_version: str = DEFAULT_API_VERSION):
        self.access_token = (access_token or "").strip()
        self.subscription_id = (subscription_id or DEFAULT_SUBSCRIPTION_ID).strip()
        self.api_version = api_version or DEFAULT_API_VERSION
        if not self.access_token:
            raise AzureARMError("缺少 ARM access_token")
        if not self.subscription_id:
            raise AzureARMError("缺少 subscription_id")

    def request(self, method: str, url: str, *, json_body: Any = None, timeout: int | None = None) -> Any:
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
            "ClientType": "NA-auto-configuration",
        }
        last_error: AzureARMError | None = None
        for attempt in range(6):
            try:
                resp = requests.request(
                    method,
                    url,
                    headers=headers,
                    json=json_body,
                    timeout=timeout if timeout is not None else 60,
                )
            except requests.RequestException as exc:
                raise AzureARMError(f"ARM 请求失败: {exc}") from exc
            if resp.status_code in _RETRY_STATUSES:
                wait = retry_after_seconds(resp, attempt)
                try:
                    payload = resp.json()
                except ValueError:
                    payload = {"text": resp.text[:400]}
                err = payload.get("error") if isinstance(payload, dict) else None
                if isinstance(err, dict):
                    msg = str(err.get("message") or err.get("code") or payload)
                else:
                    msg = str(payload)[:400] or resp.reason or "Too many requests"
                last_error = AzureARMError(
                    _format_arm_http_error(resp.status_code, msg),
                    status=resp.status_code,
                    raw=payload,
                )
                if attempt >= 5:
                    break
                time.sleep(wait)
                continue
            if resp.status_code >= 400:
                try:
                    payload = resp.json()
                except ValueError:
                    payload = {"text": resp.text[:400]}
                err = payload.get("error") if isinstance(payload, dict) else None
                if isinstance(err, dict):
                    msg = str(err.get("message") or err.get("code") or payload)
                else:
                    msg = str(payload)[:400]
                raise AzureARMError(_format_arm_http_error(resp.status_code, msg), status=resp.status_code, raw=payload)
            if not resp.content:
                return {}
            try:
                return resp.json()
            except ValueError as exc:
                raise AzureARMError("ARM 返回不是 JSON") from exc
        raise last_error or AzureARMError("ARM HTTP 429: Too many requests. Please retry.", status=429)

    def _arm_url(self, path: str, extra_query: str = "") -> str:
        url = f"{ARM_RESOURCE}{path}?api-version={self.api_version}"
        if extra_query:
            url += f"&{extra_query}"
        return url

    def _paged(self, method: str, url: str, *, json_body: Any = None) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        next_url = url
        body = json_body
        while next_url:
            result = self.request(method, next_url, json_body=body)
            body = None
            method = "GET"
            if isinstance(result, dict):
                batch = result.get("value")
                if isinstance(batch, list):
                    items.extend([x for x in batch if isinstance(x, dict)])
                next_url = str(result.get("nextLink") or "").strip()
            else:
                break
        return items

    def list_accounts(self) -> list[dict[str, Any]]:
        path = f"/subscriptions/{self.subscription_id}/providers/Microsoft.CognitiveServices/accounts"
        return self._paged("GET", self._arm_url(path))

    def get_account(self, resource_group: str, account_name: str) -> dict[str, Any]:
        path = (
            f"/subscriptions/{self.subscription_id}/resourceGroups/{resource_group}"
            f"/providers/Microsoft.CognitiveServices/accounts/{account_name}"
        )
        result = self.request("GET", self._arm_url(path))
        return result if isinstance(result, dict) else {}

    def list_deployments(self, resource_group: str, account_name: str) -> list[dict[str, Any]]:
        path = (
            f"/subscriptions/{self.subscription_id}/resourceGroups/{resource_group}"
            f"/providers/Microsoft.CognitiveServices/accounts/{account_name}/deployments"
        )
        return self._paged("GET", self._arm_url(path))

    def list_keys(self, resource_group: str, account_name: str) -> dict[str, str]:
        path = (
            f"/subscriptions/{self.subscription_id}/resourceGroups/{resource_group}"
            f"/providers/Microsoft.CognitiveServices/accounts/{account_name}/listKeys"
        )
        result = self.request("POST", self._arm_url(path), json_body={})
        if not isinstance(result, dict):
            return {"key1": "", "key2": ""}
        return {
            "key1": str(result.get("key1") or "").strip(),
            "key2": str(result.get("key2") or "").strip(),
        }

    def query_cost(
        self,
        *,
        granularity: str,
        date_from: str,
        date_to: str,
        grouping: list[str] | None = None,
    ) -> dict[str, Any]:
        """Cost Management Query：订阅范围、按维度分组。granularity 为 Daily / Monthly。"""
        names = [str(item).strip() for item in (grouping or ["ResourceId"]) if str(item).strip()]
        if not names:
            names = ["ResourceId"]
        url = (
            f"{ARM_RESOURCE}/subscriptions/{self.subscription_id}"
            f"/providers/Microsoft.CostManagement/query?api-version={COST_API_VERSION}"
        )
        body = {
            "type": "ActualCost",
            "timeframe": "Custom",
            "timePeriod": {
                "from": f"{date_from}T00:00:00Z",
                "to": f"{date_to}T23:59:59Z",
            },
            "dataset": {
                "granularity": granularity,
                "aggregation": {"totalCost": {"name": "Cost", "function": "Sum"}},
                "grouping": [{"type": "Dimension", "name": name} for name in names],
            },
        }
        rows: list[list[Any]] = []
        columns: list[dict[str, Any]] = []
        next_url: str | None = url
        json_body: Any = body
        method = "POST"
        pages = 0
        while next_url:
            pages += 1
            if pages > 200:
                break
            result = self.request(method, next_url, json_body=json_body, timeout=120)
            json_body = None
            method = "GET"
            if not isinstance(result, dict):
                break
            props = result.get("properties") if isinstance(result.get("properties"), dict) else result
            if not columns:
                raw_cols = props.get("columns") if isinstance(props, dict) else None
                if isinstance(raw_cols, list):
                    columns = [item for item in raw_cols if isinstance(item, dict)]
            batch = props.get("rows") if isinstance(props, dict) else None
            if isinstance(batch, list):
                rows.extend(item for item in batch if isinstance(item, list))
            next_url = str(result.get("nextLink") or (props.get("nextLink") if isinstance(props, dict) else "") or "").strip() or None
        return {"columns": columns, "rows": rows}

    def query_cost_dicts(
        self,
        *,
        granularity: str,
        date_from: str,
        date_to: str,
        grouping: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        payload = self.query_cost(
            granularity=granularity,
            date_from=date_from,
            date_to=date_to,
            grouping=grouping,
        )
        names = [str(col.get("name") or "").strip() for col in payload.get("columns") or []]
        out: list[dict[str, Any]] = []
        for raw in payload.get("rows") or []:
            if not isinstance(raw, list):
                continue
            item: dict[str, Any] = {}
            for idx, name in enumerate(names):
                if name:
                    item[name] = raw[idx] if idx < len(raw) else ""
            if item:
                out.append(item)
        return out


def parse_resource_group(account_id: str) -> str:
    text = str(account_id or "")
    marker = "/resourceGroups/"
    idx = text.lower().find(marker.lower())
    if idx < 0:
        return ""
    rest = text[idx + len(marker) :]
    return rest.split("/", 1)[0]


def parse_subscription_id_from_resource(account_id: str) -> str:
    text = str(account_id or "")
    marker = "/subscriptions/"
    idx = text.lower().find(marker.lower())
    if idx < 0:
        return ""
    rest = text[idx + len(marker) :]
    return rest.split("/", 1)[0]


def host_from_endpoint(endpoint: str) -> str:
    parsed = urlparse(str(endpoint or "").strip())
    return (parsed.netloc or "").strip()
