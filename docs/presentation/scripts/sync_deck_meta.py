#!/usr/bin/env python3
"""Sync masthead-meta and footer page numbers to manifest order."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SLIDES = ROOT / "slides"
TOTAL = 18

DECK = [
    ("01-cover.html", "封面", "NA 自动配置工具", f"01 / {TOTAL} · 封面"),
    ("02-agenda.html", "演示目录", "演示目录", f"02 / {TOTAL}"),
    ("02-problem.html", "背景与痛点", "背景与痛点", f"03 / {TOTAL}"),
    ("03-modules.html", "四大模块", "四大模块", f"04 / {TOTAL}"),
    ("04-architecture.html", "系统架构", "系统架构", f"05 / {TOTAL}"),
    ("05-extract.html", "智能提取", "智能提取", f"06 / {TOTAL}"),
    ("13-channel-types.html", "渠道类型", "渠道类型", f"07 / {TOTAL}"),
    ("06-llm.html", "LLM 增强", "LLM 增强", f"08 / {TOTAL}"),
    ("07-batch-channels.html", "渠道管理", "批量配置 · 渠道", f"09 / {TOTAL}"),
    ("08-batch-tokens.html", "令牌与分组", "令牌 · 分组 · 日志", f"10 / {TOTAL}"),
    ("09-data-summary.html", "数据汇总", "数据汇总", f"11 / {TOTAL}"),
    ("10-ui-theme.html", "界面与主题", "界面与主题", f"12 / {TOTAL}"),
    ("11-workflow.html", "推荐工作流", "推荐工作流", f"13 / {TOTAL}"),
    ("17-agent.html", "全流程智能体", "全流程智能体", f"14 / {TOTAL}"),
    ("12-quickstart.html", "快速启动", "快速启动", f"15 / {TOTAL}"),
    ("14-api-cli.html", "API 与 CLI", "API 与 CLI", f"16 / {TOTAL}"),
    ("15-faq.html", "配置与 FAQ", "配置与 FAQ", f"17 / {TOTAL}"),
    ("16-closing.html", "结语", "NA 自动配置工具", f"18 / {TOTAL} · 结语"),
]

META_RE = re.compile(
    r'(<div class="masthead-meta">)[^<]*(</div>)',
    re.DOTALL,
)
FOOTER_RE = re.compile(
    r'(<footer class="footer[^"]*">)\s*<span>[^<]*</span>\s*<span>[^<]*</span>\s*(</footer>)',
    re.DOTALL,
)
TITLE_RE = re.compile(r"<title>[^<]*</title>")


def main():
    for i, (fname, label, foot_left, foot_right) in enumerate(DECK, start=1):
        path = SLIDES / fname
        if not path.exists():
            print("missing", fname)
            continue
        text = path.read_text(encoding="utf-8")
        num = f"{i:02d}"
        meta = f"{num} / {TOTAL} · {label}"
        title = f"<title>{num} · {label}</title>"

        text = META_RE.sub(lambda m: f"{m.group(1)}{meta}{m.group(2)}", text, count=1)
        text = FOOTER_RE.sub(
            lambda m: f'{m.group(1)}<span>{foot_left}</span><span>{foot_right}</span>{m.group(2)}',
            text,
            count=1,
        )
        text = TITLE_RE.sub(title, text, count=1)
        path.write_text(text, encoding="utf-8")
        print("synced", fname, "→", meta)


if __name__ == "__main__":
    main()
