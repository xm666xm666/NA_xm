# -*- coding: utf-8 -*-
"""火山引擎 OpenAPI 签名客户端（IAM / Ark 管控面）。"""

from __future__ import annotations

import datetime
import hashlib
import hmac
import json
from typing import Any
from urllib.parse import quote

import requests

DEFAULT_REGION = "cn-beijing"
IAM_HOST = "iam.volcengineapi.com"
ARK_HOST = "ark.cn-beijing.volcengineapi.com"
BILLING_HOST = "billing.volcengineapi.com"


class VolcOpenAPIError(RuntimeError):
    def __init__(self, message: str, *, code: str = "", request_id: str = "", raw: Any = None):
        super().__init__(message)
        self.code = code
        self.request_id = request_id
        self.raw = raw


def _hmac_sha256(key: bytes, content: str) -> bytes:
    return hmac.new(key, content.encode("utf-8"), hashlib.sha256).digest()


def _hash_sha256(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _norm_query(params: dict[str, Any]) -> str:
    items: list[str] = []
    for key in sorted(params.keys()):
        val = params[key]
        if isinstance(val, list):
            for item in val:
                items.append(f"{quote(str(key), safe='-_.~')}={quote(str(item), safe='-_.~')}")
        else:
            items.append(f"{quote(str(key), safe='-_.~')}={quote(str(val), safe='-_.~')}")
    return "&".join(items).replace("+", "%20")


class VolcOpenAPIClient:
    """用 Access Key / Secret Key 调用火山管控面 API。"""

    def __init__(
        self,
        access_key_id: str,
        secret_access_key: str,
        *,
        region: str = DEFAULT_REGION,
        timeout: float = 45.0,
        session: requests.Session | None = None,
    ) -> None:
        self.access_key_id = (access_key_id or "").strip()
        self.secret_access_key = (secret_access_key or "").strip()
        self.region = (region or DEFAULT_REGION).strip() or DEFAULT_REGION
        self.timeout = timeout
        self.session = session or requests.Session()
        if not self.access_key_id or not self.secret_access_key:
            raise ValueError("请填写 Access Key ID 与 Secret Access Key")

    @staticmethod
    def _api_key_id_value(api_key_id: int | str) -> int | str:
        value = str(api_key_id or "").strip()
        if not value:
            raise ValueError("API Key ID 不能为空")
        try:
            return int(value)
        except ValueError:
            return value

    def request(
        self,
        *,
        method: str,
        host: str,
        service: str,
        action: str,
        version: str,
        query: dict[str, Any] | None = None,
        body: Any = None,
        content_type: str | None = None,
    ) -> dict[str, Any]:
        method_u = method.upper()
        query_params: dict[str, Any] = {"Action": action, "Version": version, **dict(query or {})}

        if body is None or body == "":
            body_text = ""
            ctype = content_type or "application/x-www-form-urlencoded"
        elif isinstance(body, (dict, list)):
            body_text = json.dumps(body, ensure_ascii=False, separators=(",", ":"))
            ctype = content_type or "application/json; charset=UTF-8"
        else:
            body_text = str(body)
            ctype = content_type or "application/x-www-form-urlencoded"

        now = datetime.datetime.now(datetime.timezone.utc)
        x_date = now.strftime("%Y%m%dT%H%M%SZ")
        short_date = x_date[:8]
        payload_hash = _hash_sha256(body_text)
        signed_headers = "content-type;host;x-content-sha256;x-date"
        canonical = "\n".join(
            [
                method_u,
                "/",
                _norm_query(query_params),
                f"content-type:{ctype}",
                f"host:{host}",
                f"x-content-sha256:{payload_hash}",
                f"x-date:{x_date}",
                "",
                signed_headers,
                payload_hash,
            ]
        )
        scope = f"{short_date}/{self.region}/{service}/request"
        string_to_sign = "\n".join(
            ["HMAC-SHA256", x_date, scope, _hash_sha256(canonical)]
        )
        signing_key = _hmac_sha256(self.secret_access_key.encode("utf-8"), short_date)
        signing_key = _hmac_sha256(signing_key, self.region)
        signing_key = _hmac_sha256(signing_key, service)
        signing_key = _hmac_sha256(signing_key, "request")
        signature = _hmac_sha256(signing_key, string_to_sign).hex()

        headers = {
            "Host": host,
            "Content-Type": ctype,
            "X-Date": x_date,
            "X-Content-Sha256": payload_hash,
            "Authorization": (
                f"HMAC-SHA256 Credential={self.access_key_id}/{scope}, "
                f"SignedHeaders={signed_headers}, Signature={signature}"
            ),
        }
        resp = self.session.request(
            method_u,
            f"https://{host}/",
            headers=headers,
            params=query_params,
            data=body_text if body_text else None,
            timeout=self.timeout,
        )
        try:
            data = resp.json()
        except Exception as exc:  # noqa: BLE001
            raise VolcOpenAPIError(
                f"火山 API 响应非 JSON（HTTP {resp.status_code}）: {resp.text[:300]}",
                raw=resp.text[:1000],
            ) from exc

        meta = data.get("ResponseMetadata") if isinstance(data, dict) else None
        err = meta.get("Error") if isinstance(meta, dict) else None
        if err or resp.status_code >= 400:
            if isinstance(err, dict):
                code = str(err.get("Code") or "")
                message = str(err.get("Message") or err)
                request_id = str(meta.get("RequestId") or "") if isinstance(meta, dict) else ""
            else:
                code = str(resp.status_code)
                message = str(data)[:400]
                request_id = ""
            raise VolcOpenAPIError(
                f"{action} 失败: {message}" + (f"（{code}）" if code else ""),
                code=code,
                request_id=request_id,
                raw=data,
            )
        result = data.get("Result") if isinstance(data, dict) else None
        return result if isinstance(result, dict) else {"_raw": result}

    def list_projects(self, *, limit: int = 100, offset: int = 0) -> list[dict[str, Any]]:
        projects: list[dict[str, Any]] = []
        cur = max(0, int(offset))
        page_size = max(1, min(int(limit), 1000))
        while True:
            result = self.request(
                method="GET",
                host=IAM_HOST,
                service="iam",
                action="ListProjects",
                version="2021-08-01",
                query={"Limit": str(page_size), "Offset": str(cur)},
                body="",
                content_type="application/x-www-form-urlencoded",
            )
            batch = result.get("Projects") or []
            if not isinstance(batch, list):
                batch = []
            projects.extend([p for p in batch if isinstance(p, dict)])
            total = int(result.get("Total") or 0)
            cur += len(batch)
            if not batch or cur >= total:
                break
        return projects

    def create_project(
        self,
        *,
        project_name: str,
        display_name: str = "",
        description: str = "",
        parent_project_name: str = "",
    ) -> dict[str, Any]:
        query: dict[str, Any] = {"ProjectName": project_name}
        if display_name:
            query["DisplayName"] = display_name
        if description:
            query["Description"] = description
        if parent_project_name:
            query["ParentProjectName"] = parent_project_name
        return self.request(
            method="GET",
            host=IAM_HOST,
            service="iam",
            action="CreateProject",
            version="2021-08-01",
            query=query,
            body="",
            content_type="application/x-www-form-urlencoded",
        )

    def update_project(
        self,
        *,
        project_name: str,
        display_name: str = "",
        description: str = "",
    ) -> dict[str, Any]:
        query: dict[str, Any] = {
            "ProjectName": project_name,
            "DisplayName": display_name,
            "Description": description,
        }
        return self.request(
            method="GET",
            host=IAM_HOST,
            service="iam",
            action="UpdateProject",
            version="2021-08-01",
            query=query,
            body="",
            content_type="application/x-www-form-urlencoded",
        )

    def delete_project(self, project_name: str) -> dict[str, Any]:
        return self.request(
            method="GET",
            host=IAM_HOST,
            service="iam",
            action="DeleteProject",
            version="2021-08-01",
            query={"ProjectName": project_name},
            body="",
            content_type="application/x-www-form-urlencoded",
        )

    def list_endpoints(
        self,
        project_name: str,
        *,
        page_size: int = 100,
    ) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        page = 1
        size = max(1, min(int(page_size), 100))
        while True:
            result = self.request(
                method="POST",
                host=ARK_HOST,
                service="ark",
                action="ListEndpoints",
                version="2024-01-01",
                body={
                    "PageNumber": page,
                    "PageSize": size,
                    "ProjectName": project_name,
                },
            )
            batch = result.get("Items") or []
            if not isinstance(batch, list):
                batch = []
            items.extend([it for it in batch if isinstance(it, dict)])
            total = int(result.get("TotalCount") or 0)
            if not batch or page * size >= total:
                break
            page += 1
        return items

    def list_api_keys(self, project_name: str, *, page_size: int = 50) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        page = 1
        size = max(1, min(int(page_size), 100))
        while True:
            result = self.request(
                method="POST",
                host=ARK_HOST,
                service="ark",
                action="ListApiKeys",
                version="2024-01-01",
                body={
                    "PageNumber": page,
                    "PageSize": size,
                    "ProjectName": project_name,
                },
            )
            batch = result.get("Items") or []
            if not isinstance(batch, list):
                batch = []
            items.extend([it for it in batch if isinstance(it, dict)])
            total = int(result.get("TotalCount") or 0)
            if not batch or page * size >= total:
                break
            page += 1
        return items

    def create_api_key(
        self,
        *,
        project_name: str,
        name: str,
        access_control_info: dict[str, Any] | None = None,
        ip_whitelist_info: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {
            "Name": name,
            "ProjectName": project_name,
            "ResourceInstances": [{"ResourceId": "*", "ResourceType": "all"}],
            "AccessControlInfo": access_control_info or {"AllowAll": True},
        }
        if ip_whitelist_info is not None:
            body["IPWhiteListInfo"] = ip_whitelist_info
        return self.request(
            method="POST",
            host=ARK_HOST,
            service="ark",
            action="CreateApiKey",
            version="2024-01-01",
            body=body,
        )

    def update_api_key(
        self,
        *,
        api_key_id: str,
        name: str = "",
        disable: bool | None = None,
        access_control_info: dict[str, Any] | None = None,
        ip_whitelist_info: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {"Id": self._api_key_id_value(api_key_id)}
        if name:
            body["Name"] = name
        if disable is not None:
            body["Disable"] = bool(disable)
        if access_control_info is not None:
            body["AccessControlInfo"] = access_control_info
        if ip_whitelist_info is not None:
            body["IPWhiteListInfo"] = ip_whitelist_info
        return self.request(
            method="POST",
            host=ARK_HOST,
            service="ark",
            action="UpdateApiKey",
            version="2024-01-01",
            body=body,
        )

    def list_model_rate_limits(self, *, page_size: int = 100) -> list[dict[str, Any]]:
        """账号级模型限流（RPM/TPM）。控制台多数数字来自此处，而非接入点 RateLimit。"""
        by_name: dict[str, dict[str, Any]] = {}
        page = 1
        size = max(1, min(int(page_size), 100))
        while True:
            result = self.request(
                method="POST",
                host=ARK_HOST,
                service="ark",
                action="ListModelRateLimit",
                version="2024-01-01",
                body={"PageNumber": page, "PageSize": size},
            )
            batch = result.get("Items") or []
            if not isinstance(batch, list):
                batch = []
            for item in batch:
                if not isinstance(item, dict):
                    continue
                name = str(item.get("FoundationModelName") or "").strip()
                if name:
                    by_name[name] = item
            total = int(result.get("TotalCount") or 0)
            # 部分环境分页参数无效会重复返回，用去重后数量兜底退出
            if not batch or len(by_name) >= total or len(batch) < size:
                break
            page += 1
            if page > 50:
                break
        return list(by_name.values())

    def get_raw_api_key(self, api_key_id: int | str) -> str:
        """获取 API Key 明文（对应控制台「查看 API Key → 选择使用」）。"""
        result = self.request(
            method="POST",
            host=ARK_HOST,
            service="ark",
            action="GetRawApiKey",
            version="2024-01-01",
            body={"Id": self._api_key_id_value(api_key_id)},
        )
        return str(result.get("ApiKey") or result.get("Key") or "").strip()

    def list_foundation_models(
        self,
        *,
        page_number: int = 1,
        page_size: int = 100,
        search: str = "",
        filter_names: list[str] | None = None,
    ) -> tuple[list[dict[str, Any]], int]:
        body: dict[str, Any] = {
            "PageNumber": max(1, int(page_number)),
            "PageSize": max(1, min(int(page_size), 100)),
            "SortBy": "CreateTime",
            "SortOrder": "Desc",
        }
        search = search.strip()
        if search:
            body["FuzzySearchKeyword"] = search
        names = [str(name).strip() for name in (filter_names or []) if str(name).strip()]
        if names:
            body["Filter"] = {"Names": names}
        result = self.request(
            method="POST",
            host=ARK_HOST,
            service="ark",
            action="ListFoundationModels",
            version="2024-01-01",
            body=body,
        )
        items = result.get("Items") or []
        return ([item for item in items if isinstance(item, dict)], int(result.get("TotalCount") or 0))

    def list_foundation_model_versions(
        self,
        model_name: str,
        *,
        page_number: int = 1,
        page_size: int = 100,
    ) -> list[dict[str, Any]]:
        result = self.request(
            method="POST",
            host=ARK_HOST,
            service="ark",
            action="ListFoundationModelVersions",
            version="2024-01-01",
            body={
                "FoundationModelName": model_name,
                "PageNumber": max(1, int(page_number)),
                "PageSize": max(1, min(int(page_size), 100)),
            },
        )
        items = result.get("Items") or []
        return [item for item in items if isinstance(item, dict)]

    def create_endpoint(
        self,
        *,
        name: str,
        project_name: str,
        model_name: str,
        model_version: str,
        description: str = "",
        rpm: int | None = None,
        tpm: int | None = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {
            "Name": name,
            "ProjectName": project_name,
            "ModelReference": {
                "FoundationModel": {"Name": model_name, "ModelVersion": model_version}
            },
        }
        if description:
            body["Description"] = description
        if rpm or tpm:
            body["RateLimit"] = {"Rpm": int(rpm or 0), "Tpm": int(tpm or 0)}
        return self.request(
            method="POST",
            host=ARK_HOST,
            service="ark",
            action="CreateEndpoint",
            version="2024-01-01",
            body=body,
        )
