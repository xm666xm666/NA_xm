# -*- coding: utf-8 -*-
"""火山云上游创建：项目/接入点管控面写入与模型目录读取。"""

from __future__ import annotations

import ipaddress
import re
from datetime import datetime, timezone
from typing import Any

from .volc_openapi import VolcOpenAPIError, VolcOpenAPIClient
from .upstream_volc import format_model_service


def build_project_display_name(project_name: str, owner: str = "") -> str:
    """沿用上游信息的项目方约定：项目名-负责人；无负责人记 N/A。"""
    name = str(project_name or "").strip()
    person = str(owner or "").strip() or "N/A"
    return f"{name}-{person}" if name else ""


PROJECT_NAME_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
_COMPACT_DATETIME_PATTERN = re.compile(
    r"^(\d{4})(\d{2})(\d{2})T(\d{2})(\d{2})(\d{2})(?:\.(\d+))?(Z|[+-]\d{2}:?\d{2})?$"
)


def normalize_project_datetime(value: Any) -> str:
    """标准化火山返回的紧凑时间，确保排序和前端解析一致。"""
    text = str(value or "").strip()
    if not text:
        return ""
    match = _COMPACT_DATETIME_PATTERN.fullmatch(text)
    if not match:
        return text
    year, month, day, hour, minute, second, fraction, zone = match.groups()
    return (
        f"{year}-{month}-{day}T{hour}:{minute}:{second}"
        f"{f'.{fraction}' if fraction else ''}{zone or 'Z'}"
    )


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
        "create_date": normalize_project_datetime(item.get("CreateDate")),
        "update_date": normalize_project_datetime(item.get("UpdateDate")),
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


def _model_is_hidden(item: dict[str, Any]) -> bool:
    tag = item.get("FoundationModelTag") if isinstance(item.get("FoundationModelTag"), dict) else {}
    values = [
        *(tag.get("CustomizedTags") or []),
        *(item.get("CustomizedTags") or []),
    ]

    def collect(value: Any) -> list[str]:
        if isinstance(value, str):
            return [value]
        if isinstance(value, list):
            return [text for child in value for text in collect(child)]
        if isinstance(value, dict):
            return [text for child in value.values() for text in collect(child)]
        return []

    labels = {text.strip() for text in collect(values) if text.strip()}
    return bool(labels & {"体验隐藏", "推理隐藏", "广场隐藏"})


def _is_system_tag_key(key: str) -> bool:
    return bool(re.match(r"^(?:sys|system)(?::|$)|^createdby$", key.lower()))


def _lifecycle_tags_from_state(state: str) -> list[str]:
    state = str(state or "")
    return ["即将下线"] if re.search(r"retiring|deprecat|offline|eol|下线", state, re.IGNORECASE) else []


def _endpoint_tags(item: dict[str, Any]) -> list[str]:
    raw_tags = item.get("Tags") if isinstance(item.get("Tags"), list) else []
    values: list[str] = []
    for raw_tag in raw_tags:
        if isinstance(raw_tag, str):
            value = raw_tag.strip()
            if not _is_system_tag_key(value.split(":", 1)[0]):
                values.append(value)
            continue
        if not isinstance(raw_tag, dict):
            continue
        key = str(raw_tag.get("Key") or raw_tag.get("key") or "").strip()
        value = str(raw_tag.get("Value") or raw_tag.get("value") or "").strip()
        if not key and not value:
            continue
        if _is_system_tag_key(key):
            continue
        if value and key.lower() in {
            "tag", "label", "name", "modelversionstatus",
            "foundationmodelversionstatus", "versionstatus", "statusreason",
        }:
            values.append(value)
        elif key and value and value.lower() not in {"true", "1", "yes"}:
            values.append(f"{key}:{value}")
        else:
            values.append(key or value)
    for key in ("ModelVersionStatus", "FoundationModelVersionStatus", "VersionStatus"):
        value = str(item.get(key) or "").strip()
        if value:
            values.append(value)
    reference = item.get("ModelReference") if isinstance(item.get("ModelReference"), dict) else {}
    foundation = reference.get("FoundationModel") if isinstance(reference.get("FoundationModel"), dict) else {}
    for source in (foundation, foundation.get("FoundationModelVersion") if isinstance(foundation.get("FoundationModelVersion"), dict) else {}):
        for key in ("ModelVersionStatus", "FoundationModelVersionStatus", "VersionStatus", "State", "Status"):
            value = str(source.get(key) or "").strip()
            if value:
                values.append(value)
    normalized_values = [
        value for value in values
        if value and not _is_system_tag_key(value.split(":", 1)[0])
    ]
    tags = list(dict.fromkeys(normalized_values))
    for value in tuple(tags):
        for lifecycle_tag in _lifecycle_tags_from_state(value):
            if lifecycle_tag not in tags:
                tags.append(lifecycle_tag)
    return tags


def _model_version_status_map(client: VolcOpenAPIClient, model_names: set[str]) -> dict[tuple[str, str], str]:
    statuses: dict[tuple[str, str], str] = {}
    for model_name in sorted(model_names, key=str.casefold):
        page = 1
        while True:
            try:
                items = client.list_foundation_model_versions(model_name, page_number=page, page_size=100)
            except Exception:  # noqa: BLE001
                break
            for item in items:
                if not isinstance(item, dict):
                    continue
                version_name = str(item.get("ModelVersion") or item.get("Version") or "").strip()
                state = str(item.get("State") or item.get("Status") or item.get("FoundationModelVersionStatus") or "").strip()
                if version_name and state:
                    statuses[(model_name.casefold(), version_name.casefold())] = state
            if len(items) < 100:
                break
            page += 1
            if page > 50:
                break
    return statuses


def _model_names_from_endpoints(items: list[Any]) -> set[str]:
    names: set[str] = set()
    for item in items:
        if not isinstance(item, dict):
            continue
        reference = item.get("ModelReference") if isinstance(item.get("ModelReference"), dict) else {}
        foundation = reference.get("FoundationModel") if isinstance(reference.get("FoundationModel"), dict) else {}
        name = str(foundation.get("Name") or "").strip()
        if name:
            names.add(name)
    return names


def _merge_endpoint_lifecycle_tags(row: dict[str, Any], version_statuses: dict[tuple[str, str], str]) -> dict[str, Any]:
    state = version_statuses.get((
        str(row.get("model_name") or "").casefold(),
        str(row.get("model_version") or "").casefold(),
    ))
    for lifecycle_tag in _lifecycle_tags_from_state(state):
        tags = row.setdefault("tags", [])
        if lifecycle_tag not in tags:
            tags.append(lifecycle_tag)
    return row


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
        "tags": _endpoint_tags(item),
        "status": str(item.get("Status") or "").strip(),
        "status_reason": str(item.get("StatusReason") or "").strip(),
        "description": str(item.get("Description") or "").strip(),
        "create_time": str(item.get("CreateTime") or "").strip(),
        "update_time": str(item.get("UpdateTime") or "").strip(),
        "support_rolling": bool(item.get("SupportRolling")),
        "rolling_id": str(item.get("RollingId") or "").strip(),
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
        "last_access_time": str(item.get("LastAccessTime") or item.get("LastUsedTime") or "").strip(),
        "disabled": str(item.get("Status") or item.get("State") or "").strip().lower() in {"disabled", "inactive", "restricted", "banned"},
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
    projects.sort(
        key=lambda item: datetime.fromisoformat(
            str(item.get("create_date") or "").replace("Z", "+00:00")
        ).astimezone(timezone.utc).timestamp()
        if item.get("create_date")
        else 0,
        reverse=True,
    )
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
    if not PROJECT_NAME_PATTERN.fullmatch(name):
        raise ValueError("项目名称仅支持英文字母、数字、下划线和短横线，长度1-64位")
    if len(str(parent_project_name or "").strip()) > 64:
        raise ValueError("父级项目名称长度不能超过64个字符")
    display = str(display_name or "").strip() or build_project_display_name(name, owner)
    if len(display) > 64:
        raise ValueError("显示名称长度不能超过64个字符")
    if len(str(description or "").strip()) > 128:
        raise ValueError("备注长度不能超过128个字符")
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


def list_enabled_models(
    access_key_id: str,
    secret_access_key: str,
    *,
    region: str = "cn-beijing",
) -> dict[str, Any]:
    client = VolcOpenAPIClient(access_key_id, secret_access_key, region=region)
    available_names: set[str] = set()
    sub_services_by_name: dict[str, list[str]] = {}
    for item in client.list_model_charge_items():
        name = str(item.get("FoundationModelName") or item.get("Name") or "").strip()
        if not name:
            continue
        raw_sub_services = item.get("SubServices") or []
        sub_services: list[str] = []
        for value in raw_sub_services if isinstance(raw_sub_services, list) else []:
            if isinstance(value, dict):
                sub_service = str(value.get("SubService") or value.get("Name") or "").strip()
                status = str(value.get("Status") or value.get("State") or "").strip()
                sub_services.append(f"{sub_service}:{status}" if sub_service and status else sub_service)
            elif str(value).strip():
                sub_services.append(str(value).strip())
        sub_services_by_name[name] = [value for value in sub_services if value]
        base_available = not sub_services or any(
            value.lower().startswith("base:") and value.lower().endswith("available")
            for value in sub_services
        )
        if str(item.get("State") or "").strip() == "Available" and base_available:
            available_names.add(name)

    items: list[dict[str, Any]] = []
    page = 1
    while True:
        catalog_items, total = client.list_foundation_models(page_number=page, page_size=100)
        for catalog_item in catalog_items:
            if _model_is_hidden(catalog_item):
                continue
            model = normalize_model(catalog_item)
            name = model["name"]
            if name not in available_names:
                continue
            available_versions = [
                version for version in model["versions"]
                if not version["state"] or version["state"].lower() == "available"
            ]
            if model["versions"] and not available_versions:
                continue
            model["versions"] = available_versions or model["versions"]
            model["state"] = "Available"
            model["sub_services"] = sub_services_by_name.get(name, [])
            items.append(model)
        if not catalog_items or page * 100 >= total:
            break
        page += 1
        if page > 50:
            break
    return {"items": items, "total": len(items)}


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
    raw_endpoints = client.list_endpoints(name)
    version_statuses = _model_version_status_map(client, _model_names_from_endpoints(raw_endpoints))
    rows = [
        normalize_endpoint(item)
        for item in raw_endpoints
        if isinstance(item, dict)
    ]
    return [_merge_endpoint_lifecycle_tags(row, version_statuses) for row in rows]


def list_deployed_models(
    access_key_id: str,
    secret_access_key: str,
    *,
    project_name: str = "",
    region: str = "cn-beijing",
) -> dict[str, Any]:
    client = VolcOpenAPIClient(access_key_id, secret_access_key, region=region)
    if project_name:
        project_names = [project_name]
    else:
        project_names = [
            normalize_project(item)["project_name"]
            for item in client.list_projects()
            if isinstance(item, dict) and normalize_project(item)["project_name"]
        ]

    deployments: dict[tuple[str, str], dict[str, Any]] = {}
    raw_endpoint_items: list[Any] = []
    normalized_rows: list[dict[str, Any]] = []
    for name in project_names:
        for item in client.list_endpoints(name):
            if not isinstance(item, dict):
                continue
            raw_endpoint_items.append(item)
            row = normalize_endpoint(item)
            row["project_name"] = row.get("project_name") or name
            normalized_rows.append(row)
    version_statuses = _model_version_status_map(client, _model_names_from_endpoints(raw_endpoint_items))
    for row in normalized_rows:
        row = _merge_endpoint_lifecycle_tags(row, version_statuses)
        model_name = row.get("model_name", "")
        model_version = row.get("model_version", "")
        if not model_name or not model_version:
            continue
        key = (model_name.casefold(), model_version.casefold())
        deployment = deployments.setdefault(key, {
            "model_name": model_name,
            "model_version": model_version,
            "endpoint_count": 0,
            "projects": [],
            "tags": [],
        })
        deployment["endpoint_count"] += 1
        project_name = str(row.get("project_name") or "").strip()
        if project_name and project_name not in deployment["projects"]:
            deployment["projects"].append(project_name)
        for tag in row.get("tags", []):
            if tag not in deployment["tags"]:
                deployment["tags"].append(tag)

    items = sorted(
        deployments.values(),
        key=lambda row: (row["model_name"].casefold(), row["model_version"].casefold()),
    )
    for row in items:
        row["projects"].sort(key=str.casefold)
    return {"items": items, "project_count": len(project_names)}


def list_api_keys(
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
    rows: list[dict[str, Any]] = []
    for item in client.list_api_keys(name):
        if not isinstance(item, dict):
            continue
        row = normalize_api_key(item)
        row.pop("api_key", None)
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
    permission_value = "custom" if str(permission or "all").strip().lower() == "custom" else "all"
    if not project:
        raise ValueError("项目名称不能为空")
    if not key_name:
        raise ValueError("API Key 名称不能为空")
    if ip_whitelist_enabled and permission_value != "custom":
        raise ValueError("火山云 IP 白名单需要将权限切换为自定义")
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
    row.pop("api_key", None)
    row.update({
        "project_name": project,
        "name": key_name,
        "permission": permission_value,
        "ip_whitelist_enabled": bool(ip_whitelist_enabled),
        "ip_whitelist": [str(item).strip() for item in whitelist if str(item).strip()],
    })
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
    permission_value = "custom" if str(permission or "all").strip().lower() == "custom" else "all"
    if ip_whitelist_enabled and permission_value != "custom":
        raise ValueError("火山云 IP 白名单需要将权限切换为自定义")
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


def set_api_key_disabled(
    access_key_id: str,
    secret_access_key: str,
    *,
    api_key_id: str,
    disabled: bool,
    region: str = "cn-beijing",
) -> dict[str, Any]:
    key_id = str(api_key_id or "").strip()
    if not key_id:
        raise ValueError("API Key ID 不能为空")
    client = VolcOpenAPIClient(access_key_id, secret_access_key, region=region)
    client.update_api_key(
        api_key_id=key_id,
        disable=bool(disabled),
    )
    return {"id": key_id, "disabled": bool(disabled)}


def delete_api_key(
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
    client.delete_api_key(api_key_id=key_id)
    return {"id": key_id, "deleted": True}


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
    create_kwargs = {
        "name": str(name).strip(),
        "project_name": str(project_name).strip(),
        "model_name": str(model_name).strip(),
        "model_version": str(model_version).strip(),
        "description": str(description or "").strip(),
        "rpm": rpm,
        "tpm": tpm,
    }
    try:
        result = client.create_endpoint(**create_kwargs)
    except VolcOpenAPIError as exc:
        if exc.code != "OperationDenied.ServiceNotOpen":
            raise
        client.activate_model_service(model_name=str(model_name).strip(), sub_services=["base"])
        result = client.create_endpoint(**create_kwargs)
    return {
        "endpoint_id": str(result.get("Id") or result.get("EndpointId") or "").strip(),
        "request": {
            "name": name,
            "project_name": project_name,
            "model_name": model_name,
            "model_version": model_version,
        },
    }


def update_endpoint(
    access_key_id: str,
    secret_access_key: str,
    *,
    endpoint_id: str,
    name: str = "",
    description: str = "",
    region: str = "cn-beijing",
) -> dict[str, Any]:
    if not str(endpoint_id or "").strip():
        raise ValueError("接入点 ID 不能为空")
    if len(str(description or "")) > 300:
        raise ValueError("接入点描述长度不能超过300个字符")
    client = VolcOpenAPIClient(access_key_id, secret_access_key, region=region)
    client.update_endpoint(
        endpoint_id=str(endpoint_id).strip(),
        name=str(name or "").strip(),
        description=str(description or "").strip(),
    )
    return {"id": str(endpoint_id).strip(), "name": str(name or "").strip(), "description": str(description or "").strip()}


def stop_endpoint(
    access_key_id: str,
    secret_access_key: str,
    *,
    endpoint_id: str,
    region: str = "cn-beijing",
) -> dict[str, Any]:
    if not str(endpoint_id or "").strip():
        raise ValueError("接入点 ID 不能为空")
    client = VolcOpenAPIClient(access_key_id, secret_access_key, region=region)
    client.stop_endpoint(endpoint_id=str(endpoint_id).strip())
    return {"id": str(endpoint_id).strip(), "status": "Stopped"}


def start_endpoint(
    access_key_id: str,
    secret_access_key: str,
    *,
    endpoint_id: str,
    region: str = "cn-beijing",
) -> dict[str, Any]:
    if not str(endpoint_id or "").strip():
        raise ValueError("接入点 ID 不能为空")
    client = VolcOpenAPIClient(access_key_id, secret_access_key, region=region)
    client.start_endpoint(endpoint_id=str(endpoint_id).strip())
    return {"id": str(endpoint_id).strip(), "status": "Running"}


def delete_endpoint(
    access_key_id: str,
    secret_access_key: str,
    *,
    endpoint_id: str,
    region: str = "cn-beijing",
) -> dict[str, Any]:
    if not str(endpoint_id or "").strip():
        raise ValueError("接入点 ID 不能为空")
    client = VolcOpenAPIClient(access_key_id, secret_access_key, region=region)
    client.delete_endpoint(endpoint_id=str(endpoint_id).strip())
    return {"id": str(endpoint_id).strip(), "deleted": True}


def _rolling_endpoint_result(
    *,
    project_name: str,
    row: dict[str, Any],
    status: str,
    message: str,
) -> dict[str, Any]:
    return {
        "project_name": project_name,
        "endpoint_id": row.get("id", ""),
        "endpoint_name": row.get("name", ""),
        "model_name": row.get("model_name", ""),
        "model_version": row.get("model_version", ""),
        "tags": row.get("tags", []),
        "endpoint_status": row.get("status", ""),
        "support_rolling": bool(row.get("support_rolling")),
        "rolling_id": row.get("rolling_id", ""),
        "action": status,
        "message": message,
    }


def rolling_update_all_endpoints(
    access_key_id: str,
    secret_access_key: str,
    *,
    old_model_name: str,
    old_model_version: str,
    new_model_name: str,
    new_model_version: str,
    project_names: list[str] | None = None,
    dry_run: bool = True,
    region: str = "cn-beijing",
) -> dict[str, Any]:
    old_name = str(old_model_name or "").strip()
    old_version = str(old_model_version or "").strip()
    target_name = str(new_model_name or "").strip()
    target_version = str(new_model_version or "").strip()
    if not old_name:
        raise ValueError("旧模型名称不能为空")
    if not old_version:
        raise ValueError("旧模型版本不能为空")
    if not target_name:
        raise ValueError("目标模型名称不能为空")
    if not target_version:
        raise ValueError("目标模型版本不能为空")
    if (
        old_name.casefold() == target_name.casefold()
        and old_version.casefold() == target_version.casefold()
    ):
        raise ValueError("旧模型/版本与目标模型/版本相同，无需切换")

    client = VolcOpenAPIClient(access_key_id, secret_access_key, region=region)
    all_projects = [
        normalize_project(item)
        for item in client.list_projects()
        if isinstance(item, dict)
    ]
    selected_names = {
        str(item or "").strip()
        for item in (project_names or [])
        if str(item or "").strip()
    }
    projects = [
        item for item in all_projects
        if not selected_names or item["project_name"] in selected_names
    ]
    if selected_names:
        found_names = {item["project_name"] for item in projects}
        missing = selected_names - found_names
        if missing:
            raise ValueError(f"项目不存在: {', '.join(sorted(missing))}")

    items: list[dict[str, Any]] = []
    updated = 0
    failed = 0
    for project in projects:
        project_name = project["project_name"]
        try:
            raw_endpoints = client.list_endpoints(project_name)
        except VolcOpenAPIError as exc:
            items.append({
                "project_name": project_name,
                "endpoint_id": "",
                "endpoint_name": "",
                "model_name": "",
                "model_version": "",
                "endpoint_status": "",
                "support_rolling": False,
                "rolling_id": "",
                "action": "failed",
                "message": f"获取接入点失败: {exc}",
            })
            failed += 1
            continue

        rows = [
            normalize_endpoint(item)
            for item in raw_endpoints
            if isinstance(item, dict)
        ]
        candidates = [
            row for row in rows
            if row["model_name"].casefold() == old_name.casefold()
            and row["model_version"].casefold() == old_version.casefold()
        ]
        if not candidates:
            continue

        for row in candidates:
            try:
                detail = client.get_endpoint(row["id"])
                detail_row = normalize_endpoint(detail) if isinstance(detail, dict) else {}
                row.update({
                    key: value
                    for key, value in detail_row.items()
                    if value not in ("", None)
                })
                row["project_name"] = row.get("project_name") or project_name
                if row.get("rolling_id"):
                    items.append(_rolling_endpoint_result(
                        project_name=project_name,
                        row=row,
                        status="skipped",
                        message="已存在滚动切换任务",
                    ))
                    continue
                if not row.get("support_rolling"):
                    items.append(_rolling_endpoint_result(
                        project_name=project_name,
                        row=row,
                        status="skipped",
                        message="上游返回不支持平滑切换",
                    ))
                    continue
                if dry_run:
                    items.append(_rolling_endpoint_result(
                        project_name=project_name,
                        row=row,
                        status="candidate",
                        message="扫描通过，等待确认执行",
                    ))
                    continue

                result = client.create_endpoint_rolling(
                    endpoint_id=row["id"],
                    model_name=target_name,
                    model_version=target_version,
                )
                row["rolling_id"] = str(
                    result.get("Id") or result.get("RollingId") or ""
                ).strip()
                updated += 1
                items.append(_rolling_endpoint_result(
                    project_name=project_name,
                    row=row,
                    status="updated",
                    message="滚动切换任务已创建",
                ))
            except VolcOpenAPIError as exc:
                failed += 1
                items.append(_rolling_endpoint_result(
                    project_name=project_name,
                    row=row,
                    status="failed",
                    message=str(exc),
                ))

    candidates = sum(1 for item in items if item["action"] == "candidate")
    skipped = sum(1 for item in items if item["action"] == "skipped")
    return {
        "project_total": len(projects),
        "matched_total": sum(1 for item in items if item["action"] != "failed"),
        "candidate_total": candidates,
        "updated_total": updated,
        "skipped_total": skipped,
        "failed_total": failed,
        "dry_run": bool(dry_run),
        "items": items,
    }
