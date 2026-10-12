"""文本模式识别。"""

from __future__ import annotations

import re

UUID_RE = re.compile(
    r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b",
    re.IGNORECASE,
)

SK_KEY_RE = re.compile(r"\bsk-[A-Za-z0-9._-]{8,}\b")

# 火山方舟 ark- 格式密钥（不用尾部 \b，避免在倒数第二段 `-` 处截断）
ARK_KEY_RE = re.compile(r"ark-[\w-]+", re.IGNORECASE)

# ep- 开头模型 ID 视为火山方舟/豆包端点
EP_MODEL_RE = re.compile(r"\bep-[\w-]+\b", re.IGNORECASE)
VOLCANO_ENDPOINT_RE = EP_MODEL_RE

# 路径型上游模型：/models/GLM-5.2-FP8、models/xxx（vLLM / OpenAI 兼容服务常见）
PATH_MODEL_RE = re.compile(
    r"^/?models/[A-Za-z0-9][\w.+-]*$",
    re.IGNORECASE,
)

URL_RE = re.compile(r"https?://[^\s,，;；]+", re.IGNORECASE)

API_VERSION_RE = re.compile(r"^\d{4}-\d{2}-\d{2}(?:[-\w.]*)?$")

# 版本标注行：DeepSeek-V3.2｜251201、GLM-5.2｜260617
VERSION_TAG_RE = re.compile(
    r"^[A-Za-z][\w.+-]*[｜|]\d{6,8}$",
    re.IGNORECASE,
)

# 模型映射：源模型->上游模型（NA 渠道表或批量格式常见）
MODEL_MAPPING_RE = re.compile(r"^(.+?)->(.+)$")

# 项目名：多段连字符 ASCII 核心，可带中文备注后缀（如 -商业百炼）
_PROJECT_NAME_ASCII = r"[a-zA-Z][a-zA-Z0-9_.-]*(?:-[a-zA-Z0-9_.]+){2,}"
_PROJECT_NAME_CJK_REMARK = r"-[\u4e00-\u9fff][\u4e00-\u9fffA-Za-z0-9_.·]*"
PROJECT_NAME_RE = re.compile(
    rf"^{_PROJECT_NAME_ASCII}(?:{_PROJECT_NAME_CJK_REMARK})?$"
)
# 渠道名 ASCII 核心（去掉中文备注），用作模型列
ASCII_CHANNEL_CORE_RE = re.compile(rf"^({_PROJECT_NAME_ASCII})")

# 分组截取：取到环境段（整段精确匹配，避免 product/development 误伤）
# 例：efficiency-ai-uat-product-gpt5.6sol → efficiency-ai-uat
#     ai-train-camp-uat-qwen3.7-plus → ai-train-camp-uat
_ENV_SEGMENT = r"(?:test|uat|prd|prod|stg|dev)"
CHANNEL_ENV_GROUP_RE = re.compile(
    rf"^(.+-{_ENV_SEGMENT})(?:-|$)",
    re.IGNORECASE,
)

# 兼容旧名：环境后紧跟模型族（glm/gpt/...）时的渠道名
CHANNEL_NAME_SUFFIX_RE = re.compile(
    rf"^(.+-{_ENV_SEGMENT})"
    r"-(?:glm|gpt|qwen|deepseek|claude|doubao|kimi|moonshot)"
    r"[a-zA-Z0-9_.+-]*$",
    re.IGNORECASE,
)

# 环境后缀：-prd、-test 等
ENV_SUFFIX_RE = re.compile(rf"-{_ENV_SEGMENT}$", re.IGNORECASE)

# Azure OpenAI
AZURE_HOST_HINT_RE = re.compile(r"openai\.azure\.com", re.IGNORECASE)
# Azure 部署模型名：gpt-4o、text-embedding-ada-002 等（短名称，非渠道项目名）
AZURE_DEPLOY_MODEL_RE = re.compile(
    r"^(?:"
    r"gpt[-.]?\d[\w.-]*"
    r"|gpt-[\w.-]+"
    r"|text-embedding(?:-[\w.]+)+"
    r"|text-ada-\d+"
    r"|whisper(?:-[\w.]+)*"
    r"|dall-e(?:-[\w.]+)*"
    r"|o[1-9](?:-[\w.]+)*"
    r")$",
    re.IGNORECASE,
)
# Azure API Key：长字母数字串
AZURE_KEY_RE = re.compile(r"^[A-Za-z0-9]{40,}$")

NOISE_LINE_RE = re.compile(
    r"^\s*(?:"
    r"\d[\d,]*\s*RPM[\d,\s]*TPM|"
    r"\d+\s*RPM|"
    r"\d[\d,]*\s*TPM|"
    r"[A-Za-z][\w.+-]*[｜|]\d{6,8}|"
    r"部署信息|"
    r"名称|"
    r"已启用|已禁用|"
    r"\d[\d,]*\s+\d+$|"  # 2,006,000 2010
    r"[A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,3}$"  # Sweden Central
    r")\s*$",
    re.IGNORECASE,
)
