"""从渠道名称推导分组名与模型列。"""

from __future__ import annotations

import re

from .patterns import ASCII_CHANNEL_CORE_RE, CHANNEL_ENV_GROUP_RE, ENV_SUFFIX_RE

# 与 old 项目示例对齐的常见后缀（无环境段时的兜底剥除）
_SUFFIX_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"-glm[a-zA-Z0-9_.+-]*$", re.IGNORECASE),
    re.compile(r"-gpt[a-zA-Z0-9_.+-]*$", re.IGNORECASE),
    re.compile(r"-qwen[a-zA-Z0-9_.+-]*$", re.IGNORECASE),
    re.compile(r"-deepseek[a-zA-Z0-9_.+-]*$", re.IGNORECASE),
    re.compile(r"-claude[a-zA-Z0-9_.+-]*$", re.IGNORECASE),
    re.compile(r"-doubao[a-zA-Z0-9_.+-]*$", re.IGNORECASE),
    re.compile(r"-kimi[a-zA-Z0-9_.+-]*$", re.IGNORECASE),
    re.compile(r"-moonshot[a-zA-Z0-9_.+-]*$", re.IGNORECASE),
)


def derive_model_from_name(name: str) -> str:
    """模型列：去掉中文备注后的 ASCII 渠道名。

    例：ai-train-camp-uat-kimi-k3-商业百炼 → ai-train-camp-uat-kimi-k3
    """
    text = (name or "").strip()
    if not text:
        return ""
    match = ASCII_CHANNEL_CORE_RE.match(text)
    if match:
        return match.group(1)
    return text


def derive_group_from_name(name: str) -> str:
    """从渠道名称推导分组，截取到环境段（test/uat/prd/prod/stg/dev）。

    命名约定：{项目}-{环境}-[业务段-]{模型...}[-中文备注]
    例：
      demo-alpha-test-glm-x → demo-alpha-test
      ai-train-camp-uat-qwen3.7-plus-商业百炼 → ai-train-camp-uat
      efficiency-ai-uat-product-gpt5.6sol → efficiency-ai-uat
    """
    text = (name or "").strip()
    if not text:
        return ""

    # 先剥中文备注，再推导分组
    base = derive_model_from_name(text)

    # 优先：截到环境段（可夹业务段，如 uat-product-gpt...）
    match = CHANNEL_ENV_GROUP_RE.match(base)
    if match:
        return match.group(1)

    # 环境部署名：demo-model-a-prd -> demo-model-a（整名以环境结尾时上面已覆盖；双保险）
    if ENV_SUFFIX_RE.search(base):
        return ENV_SUFFIX_RE.sub("", base)

    for pattern in _SUFFIX_PATTERNS:
        stripped = pattern.sub("", base)
        if stripped and stripped != base:
            return stripped

    # 兜底：去掉最后一段
    if "-" in base:
        return base.rsplit("-", 1)[0]

    return base
