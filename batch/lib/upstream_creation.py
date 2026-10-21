# -*- coding: utf-8 -*-
"""火山云上游创建：项目/接入点管控面写入与模型目录读取。"""

from __future__ import annotations

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
