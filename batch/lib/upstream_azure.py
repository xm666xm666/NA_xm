# -*- coding: utf-8 -*-
"""上游信息 · Azure OpenAI 采集（ARM 管控面，与火山云相互独立）。"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

from .azure_arm import (
    DEFAULT_API_VERSION,
    AzureARMClient,
    AzureARMError,
    acquire_arm_token,
    parse_subscription_entries,
    parse_resource_group,
)
from .deploy_time import sort_rows_by_deploy_time_desc

_CN_TZ = timezone(timedelta(hours=8))

AZURE_HEADERS = [
    "订阅",
    "区域",
    "Azure OpenAI",
    "部署名",
    "模型名",
    "模型版本",
    "部署类型",
    "TPM",
    "RPM",
    "接口",
    "密钥一",
    "项目",
    "负责人",
    "部署时间",
]
TAG_PROJECT_KEY = "1"
NA_FALLBACK = "N/A"
OWNER_SEPARATORS = re.compile(r"[，,、]+")

OPENAI_KINDS = {"openai", "aiservices"}
DEFAULT_INFERENCE_API_VERSION = "2025-04-01-preview"
EMBEDDING_API_VERSION = "2023-05-15"

LOCATION_LABELS = {
    "eastus": "East US",
    "eastus2": "East US2",
    "westus": "West US",
    "westus2": "West US2",
    "westus3": "West US3",
    "koreacentral": "Korea Central",
    "southeastasia": "Southeast Asia",
    "eastasia": "East Asia",
    "swedencentral": "Sweden Central",
    "northeurope": "North Europe",
    "westeurope": "West Europe",
    "japaneast": "Japan East",
    "australiaeast": "Australia East",
}

SKU_LABELS = {
    "globalstandard": "全局标准",
    "standard": "标准",
    "datazonestandard": "数据区标准",
    "globalbatch": "全局批处理",
    "provisionedmanaged": "预配吞吐",
}


@dataclass
class AzureCollectStats:
    accounts_ok: int = 0
    accounts_failed: int = 0
    deployments: int = 0
    subscriptions_ok: int = 0
    subscriptions_failed: int = 0
    account_results: list[dict[str, Any]] = field(default_factory=list)
    subscription_results: list[dict[str, Any]] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    rows: list[dict[str, Any]] = field(default_factory=list)


def format_location(location: str) -> str:
    raw = str(location or "").strip()
    if not raw:
        return ""
    key = raw.lower().replace(" ", "")
    return LOCATION_LABELS.get(key, raw)


def format_sku_label(sku_name: str) -> str:
    raw = str(sku_name or "").strip()
    if not raw:
        return ""
    return SKU_LABELS.get(raw.lower(), raw)


def resolve_tpm(deployment: dict[str, Any]) -> Any:
    sku = deployment.get("sku") if isinstance(deployment.get("sku"), dict) else {}
    capacity = sku.get("capacity")
    try:
        value = int(capacity)
    except (TypeError, ValueError):
        return ""
    if value <= 0:
        return ""
    return value * 1000


def resolve_rpm(deployment: dict[str, Any]) -> Any:
    props = deployment.get("properties") if isinstance(deployment.get("properties"), dict) else {}
    rules = props.get("rateLimits")
    if isinstance(rules, list):
        for rule in rules:
            if not isinstance(rule, dict):
                continue
            key = str(rule.get("key") or "").lower()
            if "token" in key:
                continue
            count = rule.get("count")
            try:
                value = int(float(count))
            except (TypeError, ValueError):
                continue
            if value > 0:
                return value
    call = props.get("callRateLimit")
    if isinstance(call, dict):
        count = call.get("count")
        try:
            value = int(float(count))
        except (TypeError, ValueError):
            value = 0
        if value > 0:
            return value
    return ""


def deployment_model(deployment: dict[str, Any]) -> tuple[str, str]:
    props = deployment.get("properties") if isinstance(deployment.get("properties"), dict) else {}
    model = props.get("model") if isinstance(props.get("model"), dict) else {}
    name = str(model.get("name") or "").strip()
    version = str(model.get("version") or "").strip()
    return name, version


def is_embedding_model(model_name: str, deployment_name: str = "") -> bool:
    blob = f"{model_name} {deployment_name}".lower()
    return "embedding" in blob


def build_endpoint_url(account_endpoint: str, account_name: str, deployment_name: str, model_name: str) -> str:
    base = str(account_endpoint or "").strip().rstrip("/")
    if not base:
        host = str(account_name or "").strip()
        base = f"https://{host}.openai.azure.com" if host else ""
    if not base:
        return ""
    if is_embedding_model(model_name, deployment_name):
        dep = (deployment_name or model_name).strip()
        return f"{base}/openai/deployments/{dep}/embeddings?api-version={EMBEDDING_API_VERSION}"
    return f"{base}/openai/responses?api-version={DEFAULT_INFERENCE_API_VERSION}"


def _tag_map(tags: Any) -> dict[str, str]:
    mapping: dict[str, str] = {}
    if isinstance(tags, dict):
        for key, value in tags.items():
            mapping[str(key).strip()] = str(value or "").strip()
        return mapping
    if isinstance(tags, list):
        for item in tags:
            if not isinstance(item, dict):
                continue
            key = str(item.get("name") or item.get("key") or "").strip()
            if not key:
                continue
            mapping[key] = str(item.get("value") or item.get("val") or "").strip()
    return mapping


def normalize_owners(raw: str) -> str:
    """多名负责人：识别中文逗号 ``，``、英文逗号 ``,``、顿号 ``、``，导出时统一为 ``，``。"""
    parts = [item.strip() for item in OWNER_SEPARATORS.split(str(raw or "")) if item.strip()]
    if not parts:
        return NA_FALLBACK
    return "，".join(parts)


def parse_tag_project_owner(tags: Any) -> tuple[str, str]:
    """从账号标记名 ``1`` 解析 ``项目-负责人1，负责人2``。

    按**最后一个** ``-`` 拆开：前面整段是项目名（可含多个 ``-``），最后一段才是负责人。
    负责人之间可用 ``，`` / ``,`` / ``、``。没有该标记、值为空时，项目与负责人均为 ``N/A``。
    """
    mapping = _tag_map(tags)
    text = str(mapping.get(TAG_PROJECT_KEY) or "").strip()
    if not text:
        return NA_FALLBACK, NA_FALLBACK
    sep = -1
    for ch in ("-", "－", "—", "–"):
        idx = text.rfind(ch)
        if idx > sep:
            sep = idx
    if sep < 0:
        return text, NA_FALLBACK
    project = text[:sep].strip() or NA_FALLBACK
    owners = normalize_owners(text[sep + 1 :])
    return project, owners


def format_deploy_time(value: Any) -> str:
    """统一写成 YYYY-MM-DD HH:MM:SS（东八区）。"""
    if value in (None, ""):
        return ""
    if isinstance(value, datetime):
        dt = value
        if dt.tzinfo is not None:
            dt = dt.astimezone(_CN_TZ)
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    if isinstance(value, (int, float)):
        ts = float(value)
        if ts > 1e12:
            ts /= 1000.0
        if ts <= 0:
            return ""
        return datetime.fromtimestamp(ts, _CN_TZ).strftime("%Y-%m-%d %H:%M:%S")
    text = str(value).strip()
    if not text:
        return ""
    if re.fullmatch(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}", text):
        return text
    if re.fullmatch(r"\d{10,13}", text):
        return format_deploy_time(int(text))
    iso = text.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(iso)
    except ValueError:
        return ""
    if dt.tzinfo is not None:
        dt = dt.astimezone(_CN_TZ)
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def format_deployment_deploy_time(deployment: dict[str, Any]) -> str:
    system = deployment.get("systemData") or deployment.get("system_data")
    if isinstance(system, dict):
        formatted = format_deploy_time(system.get("createdAt") or system.get("created_at"))
        if formatted:
            return formatted
    props = deployment.get("properties") if isinstance(deployment.get("properties"), dict) else {}
    return format_deploy_time(
        props.get("createdAt") or props.get("created_at") or props.get("provisioningStartTime")
    )


def is_openai_account(account: dict[str, Any]) -> bool:
    kind = str(account.get("kind") or "").strip().lower()
    if kind in OPENAI_KINDS:
        return True
    sku = account.get("sku") if isinstance(account.get("sku"), dict) else {}
    sku_name = str(sku.get("name") or "").lower()
    if "openai" in sku_name:
        return True
    name = str(account.get("name") or "").lower()
    return "openai" in name


def deployment_to_row(
    *,
    subscription_id: str,
    subscription_label: str = "",
    location: str,
    account_name: str,
    account_endpoint: str,
    deployment: dict[str, Any],
    api_key: str = "",
    project: str = "",
    owner: str = "",
    tags: Any = None,
) -> dict[str, Any]:
    dep_name = str(deployment.get("name") or "").strip()
    model_name, model_version = deployment_model(deployment)
    sku = deployment.get("sku") if isinstance(deployment.get("sku"), dict) else {}
    sku_name = str(sku.get("name") or "").strip()
    parsed_project, parsed_owner = parse_tag_project_owner(tags)
    project = str(project or "").strip() or parsed_project
    owner = str(owner or "").strip() or parsed_owner
    return {
        "订阅": subscription_label or subscription_id,
        "区域": format_location(location),
        "Azure OpenAI": account_name,
        "部署名": dep_name,
        "模型名": model_name,
        "模型版本": model_version,
        "部署类型": format_sku_label(sku_name),
        "TPM": resolve_tpm(deployment),
        "RPM": resolve_rpm(deployment),
        "接口": build_endpoint_url(account_endpoint, account_name, dep_name, model_name),
        "密钥一": api_key,
        "项目": project,
        "负责人": owner,
        "部署时间": format_deployment_deploy_time(deployment),
    }


def test_azure_connection(
    tenant_id: str,
    client_id: str,
    client_secret: str,
    *,
    subscription_id: str = "",
    subscription_ids: list[str] | str | None = None,
) -> dict[str, Any]:
    token = acquire_arm_token(tenant_id, client_id, client_secret)
    entries = parse_subscription_entries(subscription_ids, subscription_id)
    per_sub: list[dict[str, Any]] = []
    names: list[str] = []
    for entry in entries:
        sub = entry["id"]
        label = entry["label"]
        try:
            client = AzureARMClient(token, subscription_id=sub)
            accounts = [item for item in client.list_accounts() if is_openai_account(item)]
            sub_names = [
                str(item.get("name") or "").strip() for item in accounts if str(item.get("name") or "").strip()
            ]
            names.extend(sub_names)
            per_sub.append(
                {
                    "subscription_id": sub,
                    "subscription": label,
                    "success": True,
                    "account_count": len(sub_names),
                    "accounts": sub_names,
                }
            )
        except AzureARMError as exc:
            per_sub.append(
                {
                    "subscription_id": sub,
                    "subscription": label,
                    "success": False,
                    "account_count": 0,
                    "accounts": [],
                    "message": str(exc),
                }
            )
    if not any(item.get("success") for item in per_sub):
        detail = "；".join(str(item.get("message") or item.get("subscription")) for item in per_sub)
        raise AzureARMError(detail or "全部订阅连接失败")
    return {
        "account_count": len(names),
        "accounts": names,
        "subscription_id": entries[0]["id"] if entries else "",
        "subscription_ids": [item["id"] for item in entries],
        "subscription_results": per_sub,
        "api_version": DEFAULT_API_VERSION,
    }


def _collect_subscription_accounts(
    client: AzureARMClient,
    stats: AzureCollectStats,
    *,
    include_api_keys: bool,
    subscription_label: str,
) -> int:
    tag = subscription_label or client.subscription_id
    accounts = client.list_accounts()
    openai_accounts = [item for item in accounts if is_openai_account(item)]
    if not openai_accounts:
        stats.errors.append(f"[{tag}] 订阅下未找到 Azure OpenAI 账号（kind=OpenAI / AIServices）")
        return 0

    found = 0
    for account in openai_accounts:
        name = str(account.get("name") or "").strip()
        account_id = str(account.get("id") or "")
        rg = parse_resource_group(account_id)
        location = str(account.get("location") or "").strip()
        props = account.get("properties") if isinstance(account.get("properties"), dict) else {}
        endpoint = str(props.get("endpoint") or "").strip()
        if not name or not rg:
            stats.accounts_failed += 1
            stats.errors.append(f"[{tag}] 账号缺少名称或资源组: {account_id or name or '(unknown)'}")
            continue
        tags = account.get("tags")
        if isinstance(props.get("tags"), dict) and not _tag_map(tags).get(TAG_PROJECT_KEY):
            tags = props.get("tags")
        if not _tag_map(tags).get(TAG_PROJECT_KEY):
            try:
                detail = client.get_account(rg, name)
                if isinstance(detail, dict) and detail.get("tags") is not None:
                    tags = detail.get("tags")
            except AzureARMError as exc:
                stats.errors.append(f"[{tag}/{name}] 读取标记: {exc}")
        project, owner = parse_tag_project_owner(tags)
        try:
            deployments = client.list_deployments(rg, name)
            api_key = ""
            if include_api_keys:
                try:
                    api_key = client.list_keys(rg, name).get("key1") or ""
                except AzureARMError as exc:
                    stats.errors.append(f"[{tag}/{name}] listKeys: {exc}")
            rows: list[dict[str, Any]] = []
            for dep in deployments:
                dep_name = str(dep.get("name") or "").strip()
                if not dep_name:
                    continue
                rows.append(
                    deployment_to_row(
                        subscription_id=client.subscription_id,
                        subscription_label=tag,
                        location=location,
                        account_name=name,
                        account_endpoint=endpoint,
                        deployment=dep,
                        api_key=api_key,
                        project=project,
                        owner=owner,
                    )
                )
            stats.rows.extend(rows)
            stats.deployments += len(rows)
            stats.accounts_ok += 1
            found += 1
            stats.account_results.append(
                {
                    "subscription_id": client.subscription_id,
                    "subscription": tag,
                    "account": name,
                    "resource_group": rg,
                    "success": True,
                    "deployments": len(rows),
                    "message": f"采集 {len(rows)} 条部署" + ("（密钥未授权）" if include_api_keys and not api_key else ""),
                }
            )
        except AzureARMError as exc:
            stats.accounts_failed += 1
            stats.errors.append(f"[{tag}/{name}] {exc}")
            stats.account_results.append(
                {
                    "subscription_id": client.subscription_id,
                    "subscription": tag,
                    "account": name,
                    "resource_group": rg,
                    "success": False,
                    "deployments": 0,
                    "message": str(exc),
                }
            )
        except Exception as exc:  # noqa: BLE001
            stats.accounts_failed += 1
            msg = f"[{tag}/{name}] {exc}"
            stats.errors.append(msg)
            stats.account_results.append(
                {
                    "subscription_id": client.subscription_id,
                    "subscription": tag,
                    "account": name,
                    "resource_group": rg,
                    "success": False,
                    "deployments": 0,
                    "message": str(exc),
                }
            )
    return found


def collect_azure_upstream(
    tenant_id: str,
    client_id: str,
    client_secret: str,
    *,
    subscription_id: str = "",
    subscription_ids: list[str] | str | None = None,
    include_api_keys: bool = True,
) -> AzureCollectStats:
    stats = AzureCollectStats()
    entries = parse_subscription_entries(subscription_ids, subscription_id)
    try:
        token = acquire_arm_token(tenant_id, client_id, client_secret)
    except AzureARMError as exc:
        stats.errors.append(str(exc))
        return stats
    except Exception as exc:  # noqa: BLE001
        stats.errors.append(f"获取 Azure Token 失败: {exc}")
        return stats

    for entry in entries:
        sub = entry["id"]
        label = entry["label"]
        try:
            client = AzureARMClient(token, subscription_id=sub)
            found = _collect_subscription_accounts(
                client, stats, include_api_keys=include_api_keys, subscription_label=label
            )
            stats.subscriptions_ok += 1
            stats.subscription_results.append(
                {
                    "subscription_id": sub,
                    "subscription": label,
                    "success": True,
                    "accounts": found,
                    "message": f"{label} 采集到 {found} 个 OpenAI 账号",
                }
            )
        except AzureARMError as exc:
            stats.subscriptions_failed += 1
            stats.errors.append(f"[{label}] {exc}")
            stats.subscription_results.append(
                {
                    "subscription_id": sub,
                    "subscription": label,
                    "success": False,
                    "accounts": 0,
                    "message": str(exc),
                }
            )
        except Exception as exc:  # noqa: BLE001
            stats.subscriptions_failed += 1
            msg = f"[{label}] {exc}"
            stats.errors.append(msg)
            stats.subscription_results.append(
                {
                    "subscription_id": sub,
                    "subscription": label,
                    "success": False,
                    "accounts": 0,
                    "message": str(exc),
                }
            )

    stats.rows = sort_rows_by_deploy_time_desc(stats.rows)
    return stats
