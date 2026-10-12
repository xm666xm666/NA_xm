/** Shared deck order for index.html and export scripts */
export const DECK_TOTAL = 18;

export const DECK_MANIFEST = [
  { file: "slides/01-cover.html", label: "封面" },
  { file: "slides/02-agenda.html", label: "演示目录" },
  { file: "slides/02-problem.html", label: "背景与痛点" },
  { file: "slides/03-modules.html", label: "四大模块" },
  { file: "slides/04-architecture.html", label: "系统架构" },
  { file: "slides/05-extract.html", label: "智能提取" },
  { file: "slides/13-channel-types.html", label: "渠道类型" },
  { file: "slides/06-llm.html", label: "LLM 增强" },
  { file: "slides/07-batch-channels.html", label: "渠道管理" },
  { file: "slides/08-batch-tokens.html", label: "令牌与分组" },
  { file: "slides/09-data-summary.html", label: "数据汇总" },
  { file: "slides/10-ui-theme.html", label: "界面与主题" },
  { file: "slides/11-workflow.html", label: "推荐工作流" },
  { file: "slides/17-agent.html", label: "全流程智能体" },
  { file: "slides/12-quickstart.html", label: "快速启动" },
  { file: "slides/14-api-cli.html", label: "API 与 CLI" },
  { file: "slides/15-faq.html", label: "配置与 FAQ" },
  { file: "slides/16-closing.html", label: "结语" },
];

export const DECK_SLIDE_FILES = DECK_MANIFEST.map((item) =>
  item.file.replace(/^slides\//, "")
);
