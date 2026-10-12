"""解析从 New API 网页复制的密钥文本。"""

from __future__ import annotations

import re

_SK_PREFIX_RE = re.compile(r"sk-[A-Za-z0-9_\-./+=]+")
_NAME_KEY_SPLIT_RE = re.compile(r"\s{2,}|\t")


def parse_pasted_token_keys(text: str) -> dict[str, str]:
    """从网页「名称+密钥」或纯密钥粘贴内容解析 name -> key。

    支持格式：
    - demo-alpha-test-glm-x-样例甲    sk-xxx
    - demo-alpha-test-glm-x-样例甲\\tsk-xxx
    - 仅 sk- 行（按出现顺序，需与 API 名称顺序匹配时使用）
    """
    by_name: dict[str, str] = {}
    for raw_line in (text or "").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue

        sk_match = _SK_PREFIX_RE.search(line)
        if not sk_match:
            continue
        secret = sk_match.group(0).strip()
        if "***" in secret:
            continue

        prefix = line[: sk_match.start()].strip()
        if prefix:
            by_name[prefix] = secret
            continue

        # 纯密钥行：用 sk- 后片段作临时键，供顺序匹配
        by_name[f"__sk_only__:{secret}"] = secret

    return by_name


def merge_pasted_keys(
    tokens: list[dict],
    pasted: dict[str, str],
) -> dict[int, str]:
    """将粘贴内容合并为 token_id -> plain_key。"""
    resolved: dict[int, str] = {}
    sk_only = [
        key
        for name, key in pasted.items()
        if name.startswith("__sk_only__:")
    ]

    sk_idx = 0
    for token in tokens:
        token_id = token.get("id")
        if token_id is None:
            continue
        name = str(token.get("name") or "").strip()
        if name and name in pasted:
            resolved[int(token_id)] = pasted[name]
            continue
        if sk_idx < len(sk_only):
            resolved[int(token_id)] = sk_only[sk_idx]
            sk_idx += 1
    return resolved
