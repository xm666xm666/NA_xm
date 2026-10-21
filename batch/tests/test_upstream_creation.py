# -*- coding: utf-8 -*-
"""火山云上游创建 API 参数测试（无网络）。"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from lib import upstream_creation


class FakeClient:
    calls: list[dict] = []

    def __init__(self, access_key_id: str, secret_access_key: str, *, region: str = "cn-beijing") -> None:
        self.access_key_id = access_key_id
        self.secret_access_key = secret_access_key
        self.region = region
        type(self).calls = []

    def create_project(self, **kwargs):
        self.calls.append(("create_project", kwargs))
        return {}

    def update_project(self, **kwargs):
        self.calls.append(("update_project", kwargs))
        return {}

    def delete_project(self, project_name: str):
        self.calls.append(("delete_project", {"project_name": project_name}))
        return {}

    def list_projects(self):
        self.calls.append(("list_projects", {}))
        return [
            {
                "ProjectName": "AIOps",
                "DisplayName": "AIOps-张三",
                "Description": "AI 运维",
                "ParentProjectName": "default",
                "CreateDate": "2026-10-14T14:40:00+08:00",
            }
        ]

    def list_foundation_models(self, **kwargs):
        self.calls.append(("list_foundation_models", kwargs))
        return (
            [
                {
                    "Name": "Doubao-Seedance-2.5",
                    "DisplayName": "Doubao-Seedance-2.5",
                    "PrimaryVersion": "260628",
                    "FoundationModelVersions": [
                        {"ModelVersion": "260628", "State": "Available"}
                    ],
                }
            ],
            1,
        )

    def list_foundation_model_versions(self, model_name: str, **kwargs):
        self.calls.append(("list_foundation_model_versions", {"model_name": model_name, **kwargs}))
        return [{"ModelVersion": "260628", "State": "Available"}]

    def list_endpoints(self, project_name: str, **kwargs):
        self.calls.append(("list_endpoints", {"project_name": project_name, **kwargs}))
        return [
            {
                "Id": "ep-20261014144019-smrv7",
                "Name": "glm5.3-flash",
                "ProjectName": project_name,
                "Status": "Running",
                "ModelReference": {
                    "FoundationModel": {"Name": "GLM-5.3-Flash", "ModelVersion": "260828"}
                },
                "CreateTime": "2026-10-14T14:40:19+08:00",
            }
        ]

    def list_api_keys(self, project_name: str, **kwargs):
        self.calls.append(("list_api_keys", {"project_name": project_name, **kwargs}))
        return [{"Id": 12, "Name": "token-prd", "Status": "Enabled"}]

    def create_api_key(self, **kwargs):
        self.calls.append(("create_api_key", kwargs))
        return {"Id": "apikey-new", "Name": kwargs["name"], "ApiKey": "sk-new"}

    def update_api_key(self, **kwargs):
        self.calls.append(("update_api_key", kwargs))
        return {}

    def delete_api_key(self, *, api_key_id: int | str):
        self.calls.append(("delete_api_key", {"api_key_id": api_key_id}))
        return {}

    def get_raw_api_key(self, api_key_id: int | str):
        self.calls.append(("get_raw_api_key", {"id": api_key_id}))
        return "sk-test"

    def create_endpoint(self, **kwargs):
        self.calls.append(("create_endpoint", kwargs))
        return {"Id": "ep-new"}


class FakeClientFactory:
    def __init__(self, client: FakeClient):
        self.client = client

    def __call__(self, *args, **kwargs):
        return self.client


class UpstreamCreationTests(unittest.TestCase):
    def test_build_project_display_name_uses_project_owner_rule(self):
        self.assertEqual(upstream_creation.build_project_display_name("AIOps", "张三"), "AIOps-张三")
        self.assertEqual(upstream_creation.build_project_display_name("AIOps"), "AIOps-N/A")

    def test_create_project_defaults_to_sub_project(self):
        fake = FakeClient("ak", "sk")
        original = upstream_creation.VolcOpenAPIClient
        upstream_creation.VolcOpenAPIClient = FakeClientFactory(fake)
        try:
            result = upstream_creation.create_project(
                "ak",
                "sk",
                project_name="demo",
                owner="张三",
                description="说明",
            )
        finally:
            upstream_creation.VolcOpenAPIClient = original
        self.assertEqual(fake.calls, [
            (
                "create_project",
                {
                    "project_name": "demo",
                    "display_name": "demo-张三",
                    "description": "说明",
                    "parent_project_name": "default",
                },
            )
        ])
        self.assertEqual(result["parent_project_name"], "default")

    def test_create_project_validates_volcano_name_rules(self):
        with self.assertRaisesRegex(ValueError, "项目名称"):
            upstream_creation.create_project(
                "ak", "sk", project_name="invalid name", owner="张三"
            )

    def test_update_and_delete_project(self):
        fake = FakeClient("ak", "sk")
        original = upstream_creation.VolcOpenAPIClient
        upstream_creation.VolcOpenAPIClient = FakeClientFactory(fake)
        try:
            updated = upstream_creation.update_project(
                "ak",
                "sk",
                project_name="demo",
                display_name="demo-李四",
                description="新备注",
            )
            deleted = upstream_creation.delete_project("ak", "sk", project_name="demo")
        finally:
            upstream_creation.VolcOpenAPIClient = original
        self.assertEqual(updated["display_name"], "demo-李四")
        self.assertEqual(deleted["project_name"], "demo")
        self.assertEqual(fake.calls, [
            ("update_project", {"project_name": "demo", "display_name": "demo-李四", "description": "新备注"}),
            ("delete_project", {"project_name": "demo"}),
        ])

    def test_normalize_project_and_search(self):
        fake = FakeClient("ak", "sk")
        original = upstream_creation.VolcOpenAPIClient
        upstream_creation.VolcOpenAPIClient = FakeClientFactory(fake)
        try:
            rows = upstream_creation.list_projects("ak", "sk", search="张三")
        finally:
            upstream_creation.VolcOpenAPIClient = original
        self.assertEqual(rows[0]["project_name"], "AIOps")
        self.assertEqual(rows[0]["owner"], "张三")

    def test_list_models_and_versions(self):
        fake = FakeClient("ak", "sk")
        original = upstream_creation.VolcOpenAPIClient
        upstream_creation.VolcOpenAPIClient = FakeClientFactory(fake)
        try:
            models = upstream_creation.list_foundation_models("ak", "sk")
            versions = upstream_creation.list_foundation_model_versions("ak", "sk", model_name="Doubao-Seedance-2.5")
        finally:
            upstream_creation.VolcOpenAPIClient = original
        self.assertEqual(models["items"][0]["primary_version"], "260628")
        self.assertEqual(models["items"][0]["versions"][0]["model_version"], "260628")
        self.assertEqual(versions[0]["model_version"], "260628")

    def test_list_endpoints_and_create_endpoint(self):
        fake = FakeClient("ak", "sk")
        original = upstream_creation.VolcOpenAPIClient
        upstream_creation.VolcOpenAPIClient = FakeClientFactory(fake)
        try:
            rows = upstream_creation.list_endpoints("ak", "sk", project_name="AIOps")
            created = upstream_creation.create_endpoint(
                "ak",
                "sk",
                name="demo-ep",
                project_name="AIOps",
                model_name="Doubao-Seedance-2.5",
                model_version="260628",
            )
        finally:
            upstream_creation.VolcOpenAPIClient = original
        self.assertEqual(rows[0]["id"], "ep-20261014144019-smrv7")
        self.assertEqual(rows[0]["model_service"], "GLM-5.3-Flash｜260828")
        self.assertEqual(created["endpoint_id"], "ep-new")

    def test_list_api_keys_does_not_expose_plain_key(self):
        fake = FakeClient("ak", "sk")
        original = upstream_creation.VolcOpenAPIClient
        upstream_creation.VolcOpenAPIClient = FakeClientFactory(fake)
        try:
            rows = upstream_creation.list_api_keys("ak", "sk", project_name="AIOps")
        finally:
            upstream_creation.VolcOpenAPIClient = original
        self.assertEqual(rows[0]["id"], "12")
        self.assertEqual(rows[0]["name"], "token-prd")
        self.assertNotIn("api_key", rows[0])
        self.assertFalse(any(call[0] == "get_raw_api_key" for call in fake.calls))

    def test_create_api_key_ip_whitelist_requires_custom_permission(self):
        fake = FakeClient("ak", "sk")
        original = upstream_creation.VolcOpenAPIClient
        upstream_creation.VolcOpenAPIClient = FakeClientFactory(fake)
        try:
            with self.assertRaisesRegex(ValueError, "自定义"):
                upstream_creation.create_api_key(
                    "ak",
                    "sk",
                    project_name="AIOps",
                    name="api-key-demo",
                    ip_whitelist=["192.168.1.10/24"],
                    ip_whitelist_enabled=True,
                )
            row = upstream_creation.create_api_key(
                "ak",
                "sk",
                project_name="AIOps",
                name="api-key-demo",
                permission="custom",
                model_ids=["Doubao-Seedance-2.5"],
                ip_whitelist=["192.168.1.10/24"],
                ip_whitelist_enabled=True,
            )
        finally:
            upstream_creation.VolcOpenAPIClient = original
        create_call = next(call for call in fake.calls if call[0] == "create_api_key")
        self.assertEqual(create_call[1]["project_name"], "AIOps")
        self.assertEqual(create_call[1]["name"], "api-key-demo")
        self.assertEqual(create_call[1]["access_control_info"], {
            "AllowAll": False,
            "AccessRules": {
                "model": {"Effect": "allow", "EffectToAll": False, "Ids": ["Doubao-Seedance-2.5"]},
                "endpoint": {"Effect": "allow", "EffectToAll": False, "Ids": []},
            },
        })
        self.assertEqual(create_call[1]["ip_whitelist_info"], {
            "Enabled": True,
            "Contents": [{"Subnet": "192.168.1.10/24"}],
        })
        self.assertEqual(row["permission"], "custom")
        self.assertNotIn("api_key", row)

    def test_update_api_key_custom_permission_and_ip_whitelist(self):
        fake = FakeClient("ak", "sk")
        original = upstream_creation.VolcOpenAPIClient
        upstream_creation.VolcOpenAPIClient = FakeClientFactory(fake)
        try:
            upstream_creation.update_api_key(
                "ak",
                "sk",
                api_key_id="apikey-new",
                name="restricted",
                permission="custom",
                model_ids="Doubao-Seedance-2.5,GLM-5.3-Flash",
                endpoint_ids=["ep-new"],
                ip_whitelist_enabled=True,
                ip_whitelist="192.168.1.1 192.168.1.10-192.168.1.100",
            )
        finally:
            upstream_creation.VolcOpenAPIClient = original
        update_call = next(call for call in fake.calls if call[0] == "update_api_key")
        self.assertEqual(update_call[1]["api_key_id"], "apikey-new")
        self.assertEqual(update_call[1]["access_control_info"], {
            "AllowAll": False,
            "AccessRules": {
                "model": {"Effect": "allow", "EffectToAll": False, "Ids": ["Doubao-Seedance-2.5", "GLM-5.3-Flash"]},
                "endpoint": {"Effect": "allow", "EffectToAll": False, "Ids": ["ep-new"]},
            },
        })
        self.assertEqual(update_call[1]["ip_whitelist_info"], {
            "Enabled": True,
            "Contents": [
                {"IP": "192.168.1.1"},
                {"IPRange": {"StartIP": "192.168.1.10", "EndIP": "192.168.1.100"}},
            ],
        })

    def test_set_api_key_disabled(self):
        fake = FakeClient("ak", "sk")
        original = upstream_creation.VolcOpenAPIClient
        upstream_creation.VolcOpenAPIClient = FakeClientFactory(fake)
        try:
            result = upstream_creation.set_api_key_disabled(
                "ak",
                "sk",
                api_key_id="12",
                disabled=True,
            )
        finally:
            upstream_creation.VolcOpenAPIClient = original
        update_call = next(call for call in fake.calls if call[0] == "update_api_key")
        self.assertEqual(update_call[1]["disable"], True)
        self.assertEqual(result, {"id": "12", "disabled": True})

    def test_delete_api_key_uses_console_action_id(self):
        fake = FakeClient("ak", "sk")
        original = upstream_creation.VolcOpenAPIClient
        upstream_creation.VolcOpenAPIClient = FakeClientFactory(fake)
        try:
            result = upstream_creation.delete_api_key("ak", "sk", api_key_id="12")
        finally:
            upstream_creation.VolcOpenAPIClient = original
        self.assertEqual(fake.calls, [("delete_api_key", {"api_key_id": "12"})])
        self.assertEqual(result, {"id": "12", "deleted": True})


if __name__ == "__main__":
    unittest.main()
