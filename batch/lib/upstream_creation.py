# -*- coding: utf-8 -*-
"""火山云上游创建：项目/接入点管控面写入与模型目录读取。"""

from __future__ import annotations

import ipaddress
from typing import Any

from .volc_openapi import VolcOpenAPIClient
from .upstream_volc import format_model_service


def build_project_display_name(project_name: str, owner: str = "") -> str:
    """沿用上游信息的项目方约定：项目名-负责人；无负责人记 N/A。"""
    name = str(project_name or "").strip()
    person = str(owner or "").strip() or "N/A"
    return f"{name}-{person}" if name else ""


def normalize_project(item: dict[str, Any]) -> dict[str, Any]:
    name = str(item.get("ProjectName") or "").strip()
    display = str(item.get("DisplayName") or "").strip()
    owner = display[len(f"{name}-") :] if display.startswith(f"{name}-") and len(display) > len(name) + 1 else ""
    return {
        "project_name": name,
        "display_name": display,
        "owner": owner or "N/A",
        "description": str(item.get("Description") or "").strip(),
        "parent_project_name": str(item.get("ParentProjectName") or "").strip(),
        "status": str(item.get("Status") or "").strip(),
        "create_date": str(item.get("CreateDate") or "").strip(),
        "update_date": str(item.get("UpdateDate") or "").strip(),
    }


def _first(*values: Any) -> str:
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return ""


def normalize_model(item: dict[str, Any]) -> dict[str, Any]:
    versions = item.get("FoundationModelVersions") or item.get("Versions") or []
    if not isinstance(versions, list):
        versions = []
    return {
        "name": str(item.get("Name") or "").strip(),
        "display_name": str(item.get("DisplayName") or "").strip(),
        "vendor": str(item.get("VendorName") or item.get("Vendor") or "").strip(),
        "primary_version": str(item.get("PrimaryVersion") or "").strip(),
        "state": str(item.get("State") or item.get("Status") or "").strip(),
        "domains": [str(x) for x in (item.get("Domains") or []) if x],
        "versions": [
            {
                "model_version": str(version.get("ModelVersion") or version.get("Version") or "").strip(),
                "display_name": str(version.get("DisplayName") or "").strip(),
                "state": str(version.get("State") or version.get("Status") or "").strip(),
                "domains": [str(x) for x in (version.get("Domains") or []) if x],
            }
            for version in versions
            if isinstance(version, dict)
        ],
        "raw": item,
    }


def normalize_endpoint(item: dict[str, Any]) -> dict[str, Any]:
    reference = item.get("ModelReference") or {}
    model = reference.get("FoundationModel") or {} if isinstance(reference, dict) else {}
    return {
        "id": str(item.get("Id") or "").strip(),
        "name": str(item.get("Name") or "").strip(),
        "project_name": str(item.get("ProjectName") or "").strip(),
        "model_name": str(model.get("Name") or "").strip(),
        "model_version": str(model.get("ModelVersion") or "").strip(),
        "model_service": format_model_service(item),
        "status": str(item.get("Status") or "").strip(),
        "status_reason": str(item.get("StatusReason") or "").strip(),
        "description": str(item.get("Description") or "").strip(),
        "create_time": str(item.get("CreateTime") or "").strip(),
        "update_time": str(item.get("UpdateTime") or "").strip(),
    }


def normalize_api_key(item: dict[str, Any]) -> dict[str, Any]:
    access_control = item.get("AccessControlInfo") if isinstance(item.get("AccessControlInfo"), dict) else {}
    access_rules = access_control.get("AccessRules") if isinstance(access_control.get("AccessRules"), dict) else {}
    model_rule = access_rules.get("model") if isinstance(access_rules.get("model"), dict) else {}
    endpoint_rule = access_rules.get("endpoint") if isinstance(access_rules.get("endpoint"), dict) else {}
    ip_raw = item.get("IPWhiteListInfo") if isinstance(item.get("IPWhiteListInfo"), dict) else {}
    ip_contents = ip_raw.get("Contents") if isinstance(ip_raw.get("Contents"), list) else []
    normalized_ips: list[str] = []
    for content in ip_contents:
        if isinstance(content, str):
            normalized_ips.append(content.strip())
        elif isinstance(content, dict):
            if content.get("IP"):
                normalized_ips.append(str(content["IP"]).strip())
            elif content.get("Subnet"):
                normalized_ips.append(str(content["Subnet"]).strip())
            elif isinstance(content.get("IPRange"), dict):
                ip_range = content["IPRange"]
                normalized_ips.append(f"{ip_range.get('StartIP', '')}-{ip_range.get('EndIP', '')}")
    return {
        "id": str(item.get("Id") or item.get("ID") or "").strip(),
        "name": str(item.get("Name") or item.get("DisplayName") or "").strip(),
        "project_name": str(item.get("ProjectName") or "").strip(),
        "description": str(item.get("Description") or "").strip(),
        "status": str(item.get("Status") or item.get("State") or "").strip(),
        "expired_time": str(item.get("ExpiredTime") or item.get("ExpireTime") or "").strip(),
        "create_time": str(item.get("CreateTime") or item.get("CreatedAt") or "").strip(),
        "api_key": str(item.get("ApiKey") or item.get("APIKey") or "").strip(),
        "permission": "all" if access_control.get("AllowAll") is not False else "custom",
        "model_ids": [str(value) for value in (model_rule.get("Ids") or []) if str(value).strip()],
        "endpoint_ids": [str(value) for value in (endpoint_rule.get("Ids") or []) if str(value).strip()],
        "ip_whitelist_enabled": bool(ip_raw.get("Enabled")),
        "ip_whitelist": [value for value in normalized_ips if value],
    }


def _parse_ip_whitelist(values: list[str] | str | None) -> list[dict[str, Any]]:
    parsed: list[dict[str, Any]] = []
    seen: set[str] = set()
    values = [values] if isinstance(values, str) else (values or [])
    for raw_value in values:
        for candidate in str(raw_value).replace(",", " ").split():
            value = candidate.strip()
            if not value or value in seen:
                continue
            try:
                if value.count("-") == 1 and "-" in value:
                    start, end = [part.strip() for part in value.split("-", 1)]
                    (ipaddress.IPv6Address(start) if ":" in start else ipaddress.IPv4Address(start))
                    (ipaddress.IPv6Address(end) if ":" in end else ipaddress.IPv4Address(end))
                    item: dict[str, Any] = {"IPRange": {"StartIP": start, "EndIP": end}}
                elif "/" in value:
                    ipaddress.ip_network(value, strict=False)
                    item = {"Subnet": value}
                else:
                    (ipaddress.IPv6Address(value) if ":" in value else ipaddress.IPv4Address(value))
                    item = {"IP": value}
            except ValueError as exc:
                raise ValueError(f"IP 白名单格式错误：{value}") from exc
            seen.add(value)
            parsed.append(item)
    return parsed


def _build_access_control(
    permission: str,
    model_ids: list[str] | str | None,
    endpoint_ids: list[str] | str | None,
) -> dict[str, Any]:
    if str(permission or "all").strip().lower() != "custom":
        return {"AllowAll": True}

    def parse_ids(value: list[str] | str | None) -> list[str]:
        if isinstance(value, str):
            raw = value.replace(",", " ").split()
        elif isinstance(value, list):
            raw = value
        else:
            raw = []
        return list(dict.fromkeys(str(item).strip() for item in raw if str(item).strip()))

    model_values = parse_ids(model_ids)
    endpoint_values = parse_ids(endpoint_ids)
    if not model_values and not endpoint_values:
        raise ValueError("自定义权限至少选择一个 Model ID 或推理接入点")
    return {
        "AllowAll": False,
        "AccessRules": {
            "model": {"Effect": "allow", "EffectToAll": False, "Ids": model_values},
            "endpoint": {"Effect": "allow", "EffectToAll": False, "Ids": endpoint_values},
        },
    }


def list_projects(
    access_key_id: str,
    secret_access_key: str,
    *,
    region: str = "cn-beijing",
    search: str = "",
) -> list[dict[str, Any]]:
    client = VolcOpenAPIClient(access_key_id, secret_access_key, region=region)
    keyword = str(search or "").strip().lower()
    projects = [
        normalize_project(item)
        for item in client.list_projects()
        if isinstance(item, dict)
    ]
    if not keyword:
        return projects
    return [
        item
        for item in projects
        if keyword in item["project_name"].lower()
        or keyword in item["display_name"].lower()
        or keyword in item["description"].lower()
    ]


def create_project(
    access_key_id: str,
    secret_access_key: str,
    *,
    project_name: str,
    owner: str = "",
    display_name: str = "",
    description: str = "",
    parent_project_name: str = "default",
    region: str = "cn-beijing",
) -> dict[str, Any]:
    name = str(project_name or "").strip()
    if not name:
        raise ValueError("项目名称不能为空")
    display = str(display_name or "").strip() or build_project_display_name(name, owner)
    client = VolcOpenAPIClient(access_key_id, secret_access_key, region=region)
    client.create_project(
        project_name=name,
        display_name=display,
        description=str(description or "").strip(),
        parent_project_name=str(parent_project_name or "").strip(),
    )
    return {
        "project_name": name,
        "display_name": display,
        "owner": str(owner or "").strip() or "N/A",
        "description": str(description or "").strip(),
        "parent_project_name": str(parent_project_name or "").strip(),
    }


def update_project(
    access_key_id: str,
    secret_access_key: str,
    *,
    project_name: str,
    display_name: str = "",
    description: str = "",
    region: str = "cn-beijing",
) -> dict[str, Any]:
    name = str(project_name or "").strip()
    if not name:
        raise ValueError("项目名称不能为空")
    client = VolcOpenAPIClient(access_key_id, secret_access_key, region=region)
    client.update_project(
        project_name=name,
        display_name=str(display_name or "").strip(),
        description=str(description or "").strip(),
    )
    return {
        "project_name": name,
        "display_name": str(display_name or "").strip(),
        "description": str(description or "").strip(),
    }


def delete_project(
    access_key_id: str,
    secret_access_key: str,
    *,
    project_name: str,
    region: str = "cn-beijing",
) -> dict[str, Any]:
    name = str(project_name or "").strip()
    if not name:
        raise ValueError("项目名称不能为空")
    client = VolcOpenAPIClient(access_key_id, secret_access_key, region=region)
    client.delete_project(name)
    return {"project_name": name}


def list_foundation_models(
    access_key_id: str,
    secret_access_key: str,
    *,
    search: str = "",
    page_number: int = 1,
    page_size: int = 100,
    region: str = "cn-beijing",
) -> dict[str, Any]:
    client = VolcOpenAPIClient(access_key_id, secret_access_key, region=region)
    items, total = client.list_foundation_models(
        page_number=page_number,
        page_size=page_size,
        search=search,
    )
    return {"items": [normalize_model(item) for item in items], "total": total}


def list_foundation_model_versions(
    access_key_id: str,
    secret_access_key: str,
    *,
    model_name: str,
    page_number: int = 1,
    page_size: int = 100,
    region: str = "cn-beijing",
) -> list[dict[str, Any]]:
    name = str(model_name or "").strip()
    if not name:
        raise ValueError("模型名称不能为空")
    client = VolcOpenAPIClient(access_key_id, secret_access_key, region=region)
    items = client.list_foundation_model_versions(
        name,
        page_number=page_number,
        page_size=page_size,
    )
    return [
        {
            "model_version": str(item.get("ModelVersion") or item.get("Version") or "").strip(),
            "display_name": str(item.get("DisplayName") or "").strip(),
            "state": str(item.get("State") or item.get("Status") or "").strip(),
            "domains": [str(x) for x in (item.get("Domains") or []) if x],
            "raw": item,
        }
        for item in items
        if isinstance(item, dict)
    ]


def list_endpoints(
    access_key_id: str,
    secret_access_key: str,
    *,
    project_name: str,
    region: str = "cn-beijing",
) -> list[dict[str, Any]]:
    name = str(project_name or "").strip()
    if not name:
        raise ValueError("项目名称不能为空")
    client = VolcOpenAPIClient(access_key_id, secret_access_key, region=region)
    return [normalize_endpoint(item) for item in client.list_endpoints(name) if isinstance(item, dict)]


def list_api_keys(
    access_key_id: str,
    secret_access_key: str,
    *,
    project_name: str,
    include_raw: bool = True,
    region: str = "cn-beijing",
) -> list[dict[str, Any]]:
    name = str(project_name or "").strip()
    if not name:
        raise ValueError("项目名称不能为空")
    client = VolcOpenAPIClient(access_key_id, secret_access_key, region=region)
    rows: list[dict[str, Any]] = []
    for item in client.list_api_keys(name):
        if not isinstance(item, dict):
            continue
        row = normalize_api_key(item)
        if include_raw and row["id"]:
            try:
                row["api_key"] = client.get_raw_api_key(row["id"])
            except Exception:
                row["api_key"] = row["api_key"]
        rows.append(row)
    return rows


def get_raw_api_key(
    access_key_id: str,
    secret_access_key: str,
    *,
    api_key_id: str,
    region: str = "cn-beijing",
) -> dict[str, Any]:
    key_id = str(api_key_id or "").strip()
    if not key_id:
        raise ValueError("API Key ID 不能为空")
    client = VolcOpenAPIClient(access_key_id, secret_access_key, region=region)
    return {"api_key": client.get_raw_api_key(key_id)}


def create_api_key(
    access_key_id: str,
    secret_access_key: str,
    *,
    project_name: str,
    name: str,
    permission: str = "all",
    model_ids: list[str] | str | None = None,
    endpoint_ids: list[str] | str | None = None,
    ip_whitelist_enabled: bool = False,
    ip_whitelist: list[str] | str | None = None,
    region: str = "cn-beijing",
) -> dict[str, Any]:
    project = str(project_name or "").strip()
    key_name = str(name or "").strip()
    if not project:
        raise ValueError("项目名称不能为空")
    if not key_name:
        raise ValueError("API Key 名称不能为空")
    whitelist = [ip_whitelist] if isinstance(ip_whitelist, str) else list(ip_whitelist or [])
    if ip_whitelist_enabled and not whitelist:
        raise ValueError("启用 IP 白名单时至少填写一个 IP")
    ip_info = {
        "Enabled": bool(ip_whitelist_enabled),
        "Contents": _parse_ip_whitelist(whitelist) if ip_whitelist_enabled else [],
    }
    client = VolcOpenAPIClient(access_key_id, secret_access_key, region=region)
    result = client.create_api_key(
        project_name=project,
        name=key_name,
        access_control_info=_build_access_control(permission, model_ids, endpoint_ids),
        ip_whitelist_info=ip_info,
    )
    row = normalize_api_key(result if isinstance(result, dict) else {})
    row.update({
        "project_name": project,
        "name": key_name,
        "permission": "all" if str(permission or "all").lower() != "custom" else "custom",
        "ip_whitelist_enabled": bool(ip_whitelist_enabled),
        "ip_whitelist": [str(item).strip() for item in whitelist if str(item).strip()],
    })
    if row["id"] and not row["api_key"]:
        try:
            row["api_key"] = client.get_raw_api_key(row["id"])
        except Exception:
            pass
    return row


def update_api_key(
    access_key_id: str,
    secret_access_key: str,
    *,
    api_key_id: str,
    name: str = "",
    permission: str = "all",
    model_ids: list[str] | str | None = None,
    endpoint_ids: list[str] | str | None = None,
    ip_whitelist_enabled: bool = False,
    ip_whitelist: list[str] | str | None = None,
    region: str = "cn-beijing",
) -> dict[str, Any]:
    key_id = str(api_key_id or "").strip()
    if not key_id:
        raise ValueError("API Key ID 不能为空")
    whitelist = [ip_whitelist] if isinstance(ip_whitelist, str) else list(ip_whitelist or [])
    if ip_whitelist_enabled and not whitelist:
        raise ValueError("启用 IP 白名单时至少填写一个 IP")
    ip_info = {
        "Enabled": bool(ip_whitelist_enabled),
        "Contents": _parse_ip_whitelist(whitelist) if ip_whitelist_enabled else [],
    }
    client = VolcOpenAPIClient(access_key_id, secret_access_key, region=region)
    client.update_api_key(
        api_key_id=key_id,
        name=str(name or "").strip(),
        access_control_info=_build_access_control(permission, model_ids, endpoint_ids),
        ip_whitelist_info=ip_info,
    )
    return {"id": key_id, "name": str(name or "").strip()}


def create_endpoint(
    access_key_id: str,
    secret_access_key: str,
    *,
    name: str,
    project_name: str,
    model_name: str,
    model_version: str,
    description: str = "",
    rpm: int | None = None,
    tpm: int | None = None,
    region: str = "cn-beijing",
) -> dict[str, Any]:
    if not str(name or "").strip():
        raise ValueError("接入点名称不能为空")
    if not str(project_name or "").strip():
        raise ValueError("项目名称不能为空")
    if not str(model_name or "").strip():
        raise ValueError("模型名称不能为空")
    if not str(model_version or "").strip():
        raise ValueError("模型版本不能为空")
    client = VolcOpenAPIClient(access_key_id, secret_access_key, region=region)
    result = client.create_endpoint(
        name=str(name).strip(),
        project_name=str(project_name).strip(),
        model_name=str(model_name).strip(),
        model_version=str(model_version).strip(),
        description=str(description or "").strip(),
        rpm=rpm,
        tpm=tpm,
    )
    return {
        "endpoint_id": str(result.get("Id") or result.get("EndpointId") or "").strip(),
        "request": {
            "name": name,
            "project_name": project_name,
            "model_name": model_name,
            "model_version": model_version,
        },
    }
