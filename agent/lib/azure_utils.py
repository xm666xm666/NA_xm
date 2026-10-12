"""Azure OpenAI URL 与版本解析。"""

from __future__ import annotations

import re
from urllib.parse import parse_qs, urlparse

AZURE_HOST_RE = re.compile(r"openai\.azure\.com", re.IGNORECASE)


def is_azure_host(url: str) -> bool:
    return bool(AZURE_HOST_RE.search(url or ""))


def find_azure_url(lines: list[str]) -> str:
    for line in lines:
        if "http" in line.lower() and is_azure_host(line):
            return line.strip()
    return ""


def normalize_azure_base_url(url: str) -> str:
    """仅保留 scheme + host，去掉路径与查询参数。"""
    parsed = urlparse(url.strip())
    if not parsed.scheme or not parsed.netloc:
        return url.strip().rstrip("/")
    return f"{parsed.scheme}://{parsed.netloc}".rstrip("/")


def extract_api_version_from_url(url: str) -> str:
    parsed = urlparse(url.strip())
    versions = parse_qs(parsed.query).get("api-version", [])
    return versions[0].strip() if versions else ""


def parse_azure_url(url: str) -> tuple[str, str]:
    """从 Azure 门户完整链接同时解析 Base URL 与 API 版本。

    示例输入::
        https://sample-azure.example.com/openai/responses?api-version=2025-04-01-preview

    解析结果::
        base_url    -> https://sample-azure.example.com
        api_version -> 2025-04-01-preview

    用户只需粘贴原始链接，无需单独填写版本号；链接变更时两项同步更新。
    """
    return normalize_azure_base_url(url), extract_api_version_from_url(url)
