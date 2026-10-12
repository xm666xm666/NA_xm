# -*- coding: utf-8 -*-
"""Azure 成本分析账单（无网络）。"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from lib.azure_billing import (
    SHEET_DAY,
    SHEET_MONTH,
    aggregate_azure_rows,
    collect_azure_bills,
    format_usage_date,
    is_upstream_resource,
    map_cost_item,
    period_bounds,
    resource_name_from_id,
    save_azure_bill_workbook,
)


class AzureBillingTests(unittest.TestCase):
    def test_period_bounds_and_dates(self):
        self.assertEqual(period_bounds("2026-08"), ("2026-08-01", "2026-08-31"))
        self.assertEqual(format_usage_date(20260801), "2026-08-01")
        self.assertEqual(format_usage_date("2026-08-02T00:00:00Z"), "2026-08-02")
        self.assertEqual(
            resource_name_from_id(
                "/subscriptions/s/resourceGroups/rg/providers/Microsoft.CognitiveServices/accounts/phc-openai-aic"
            ),
            "phc-openai-aic",
        )

    def test_map_joins_tag_one_and_models(self):
        catalog = {
            "phc-openai-aic".lower(): {
                "项目名": "临床AI",
                "项目负责人": "张三，李四",
                "模型名": "gpt-4o",
                "配置名称": "phc-openai-aic",
                "地区": "East US",
                "订阅": "订阅1",
            }
        }
        row = map_cost_item(
            {
                "Cost": "12.50",
                "ResourceId": "/subscriptions/s/resourceGroups/rg/providers/Microsoft.CognitiveServices/accounts/phc-openai-aic",
                "ResourceLocation": "eastus",
                "UsageDate": 20260815,
                "Currency": "CNY",
            },
            catalog=catalog,
            subscription_label="订阅1",
            bill_period="2026-08",
        )
        self.assertEqual(row["日期"], "2026-08-15")
        self.assertEqual(row["项目名"], "临床AI")
        self.assertEqual(row["项目负责人"], "张三，李四")
        self.assertEqual(row["模型名"], "gpt-4o")
        self.assertEqual(row["配置名称"], "phc-openai-aic")
        self.assertEqual(row["订阅"], "订阅1")
        self.assertEqual(row["费用"], 12.5)

    def test_skips_non_openai_resource(self):
        self.assertFalse(
            is_upstream_resource(
                "/subscriptions/s/resourceGroups/rg/providers/Microsoft.Storage/storageAccounts/logs",
                "logs",
                {},
            )
        )
        self.assertTrue(
            is_upstream_resource(
                "/subscriptions/s/resourceGroups/rg/providers/Microsoft.CognitiveServices/accounts/phc-openai-aic",
                "phc-openai-aic",
                {},
            )
        )

    def test_aggregate_month(self):
        rows = [
            {
                "日期": "2026-08-01",
                "项目名": "临床AI",
                "项目负责人": "张三",
                "模型名": "gpt-4o",
                "配置名称": "phc-openai-aic",
                "地区": "East US",
                "订阅": "订阅1",
                "费用": 12.5,
            },
            {
                "日期": "2026-08-02",
                "项目名": "临床AI",
                "项目负责人": "张三",
                "模型名": "gpt-4o",
                "配置名称": "phc-openai-aic",
                "地区": "East US",
                "订阅": "订阅1",
                "费用": 7.5,
            },
        ]
        month = aggregate_azure_rows(rows, month=True)
        self.assertEqual(len(month), 1)
        self.assertEqual(month[0]["日期"], "2026-08")
        self.assertEqual(month[0]["费用"], 20.0)
        day = aggregate_azure_rows(rows, month=False)
        self.assertEqual(len(day), 2)

    def test_collect_and_workbook(self):
        class FakeClient:
            def list_accounts(self):
                return [
                    {
                        "id": "/subscriptions/s/resourceGroups/rg/providers/Microsoft.CognitiveServices/accounts/phc-openai-aic",
                        "name": "phc-openai-aic",
                        "kind": "OpenAI",
                        "location": "eastus",
                        "tags": {"1": "临床AI-张三，李四"},
                    }
                ]

            def list_deployments(self, rg, name):
                return [{"name": "gpt4", "properties": {"model": {"name": "gpt-4o"}}}]

            def query_cost_dicts(self, **kwargs):
                return [
                    {
                        "Cost": 10,
                        "ResourceId": "/subscriptions/s/resourceGroups/rg/providers/Microsoft.CognitiveServices/accounts/phc-openai-aic",
                        "ResourceLocation": "US East",
                        "UsageDate": 20260801,
                        "Currency": "CNY",
                    },
                    {
                        "Cost": 5,
                        "ResourceId": "/subscriptions/s/resourceGroups/rg/providers/Microsoft.CognitiveServices/accounts/phc-openai-aic",
                        "ResourceLocation": "US East",
                        "UsageDate": 20260801,
                        "Currency": "CNY",
                    },
                ]

        fake = FakeClient()
        with patch("lib.azure_billing.acquire_arm_token", return_value="token"):
            stats = collect_azure_bills(
                "tenant",
                "client",
                "secret",
                subscription_ids=["76c8315b-d084-4f21-8003-cf6365e711bb"],
                bill_period="2026-08",
                client_factory=lambda _sub: fake,
            )
        self.assertEqual(stats.raw_count, 2)
        self.assertEqual(stats.day_rows, 1)
        self.assertEqual(stats.rows_day[0]["费用"], 15.0)
        self.assertEqual(stats.rows_day[0]["项目名"], "临床AI")
        self.assertEqual(stats.rows_day[0]["项目负责人"], "张三，李四")
        self.assertEqual(stats.rows_day[0]["模型名"], "gpt-4o")
        self.assertEqual(stats.rows_month[0]["日期"], "2026-08")
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "azure.xlsx"
            save_azure_bill_workbook(path, stats)
            from openpyxl import load_workbook

            wb = load_workbook(path)
            self.assertEqual([c.value for c in wb[SHEET_DAY][1]], ["日期", "项目名", "项目负责人", "模型名", "配置名称", "地区", "订阅", "费用（¥）"])
            self.assertEqual([c.value for c in wb[SHEET_MONTH][1]], ["日期", "项目名", "项目负责人", "模型名", "配置名称", "地区", "订阅", "费用（¥）"])
            self.assertEqual(wb[SHEET_DAY]["B2"].value, "临床AI")
            self.assertEqual(wb[SHEET_DAY]["A3"].value, "合计")
            self.assertEqual(wb[SHEET_DAY]["H3"].value, "=SUM(H2:H2)")
            self.assertIn("¥", str(wb[SHEET_DAY]["H2"].number_format))
            wb.close()

    def test_retry_after_prefers_header(self):
        from lib.azure_arm import retry_after_seconds

        resp = type("Resp", (), {"headers": {"Retry-After": "8"}})()
        self.assertEqual(retry_after_seconds(resp, 0), 8.0)

    def test_request_retries_429_then_succeeds(self):
        from unittest.mock import Mock

        from lib.azure_arm import AzureARMClient

        limited = Mock()
        limited.status_code = 429
        limited.reason = "Too Many Requests"
        limited.headers = {"Retry-After": "1"}
        limited.text = "Too many requests"
        limited.json.return_value = {"error": {"message": "Too many requests"}}
        ok = Mock()
        ok.status_code = 200
        ok.content = b'{"value":[]}'
        ok.json.return_value = {"value": []}
        with patch("lib.azure_arm.requests.request", side_effect=[limited, ok]) as req, patch(
            "lib.azure_arm.time.sleep"
        ) as slept:
            client = AzureARMClient("token", subscription_id="76c8315b-d084-4f21-8003-cf6365e711bb")
            data = client.request("GET", "https://management.azure.com/x")
        self.assertEqual(data, {"value": []})
        self.assertEqual(req.call_count, 2)
        slept.assert_called()


if __name__ == "__main__":
    unittest.main()
