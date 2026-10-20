import tempfile
import unittest
from pathlib import Path

from openpyxl import Workbook

from batch.lib.overview_batch_export import build_overview_batch_export


class OverviewBatchExportTests(unittest.TestCase):
    def test_builds_channel_and_token_batch_lines(self):
        workbook = Workbook()
        workbook.active.title = "总览"
        channels = workbook.create_sheet("test-渠道管理")
        channels.append(["名称", "分组", "类型", "状态", "模型列表", "模型重定向", "base_url", "备注", "密钥", "部署时间"])
        channels.append([
            "gateway-alpha", "gateway", "OpenAI", "已启用",
            "model-a, model-b", "model-a->upstream-a", "https://upstream.example.com/", "备注", "sk-test", "",
        ])
        tokens = workbook.create_sheet("test-令牌管理")
        tokens.append(["名称", "项目环境", "状态", "剩余额度", "分组", "可用模型", "包含渠道", "IP限制", "创建时间", "过期时间"])
        tokens.append(["token-alpha", "test", "已启用", "120/500", "gateway", "model-a、model-b", "gateway-alpha", "无限制", "", ""])

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "总览.xlsx"
            workbook.save(path)
            channels, channel_stats = build_overview_batch_export(path, "channels")
            tokens, token_stats = build_overview_batch_export(path, "tokens")

        self.assertEqual(channels, [
            "gateway-alpha\tgateway\tOpenAI\tmodel-a\tmodel-a->upstream-a\thttps://upstream.example.com\tsk-test",
            "gateway-alpha\tgateway\tOpenAI\tmodel-b\tmodel-b->model-b\thttps://upstream.example.com\tsk-test",
        ])
        self.assertEqual(channel_stats["rows"], 1)
        self.assertEqual(channel_stats["lines"], 2)
        self.assertEqual(tokens, ["token-alpha\tgateway\tmodel-a、model-b\t120"])
        self.assertEqual(token_stats["rows"], 1)
        self.assertEqual(token_stats["lines"], 1)

    def test_skips_disabled_rows_by_default(self):
        workbook = Workbook()
        workbook.active.title = "总览"
        channels = workbook.create_sheet("uat-渠道管理")
        channels.append(["名称", "分组", "类型", "状态", "模型列表", "模型重定向", "base_url", "备注", "密钥", "部署时间"])
        channels.append(["disabled", "uat", "OpenAI", "已禁用", "model", "model->model", "https://upstream.example.com", "", "sk-test", ""])

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "总览.xlsx"
            workbook.save(path)
            lines, stats = build_overview_batch_export(path, "channels")

        self.assertEqual(lines, [])
        self.assertEqual(stats["skipped_disabled"], 1)


if __name__ == "__main__":
    unittest.main()
