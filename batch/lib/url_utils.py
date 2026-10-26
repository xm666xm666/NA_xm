"""New API 站点地址规范化。"""

from __future__ import annotations

import re
from urllib.parse import urlparse, urlunparse

_INVISIBLE_SPACES_RE = re.compile(r"[\s\u00a0\u200b-\u200f\u2060\u3000\ufeff]+")


def normalize_na_base_url(raw: str) -> str:
    """将控制台页面或 API 路径还原为站点根地址。

    例如 ``https://host/console/log`` → ``https://host``
    """
    text = _INVISIBLE_SPACES_RE.sub("", str(raw or "")).strip()
    if not text:
        return ""

    if not text.lower().startswith(("http://", "https://")):
        text = f"https://{text}"

    parsed = urlparse(text)
    if not parsed.netloc:
        return (raw or "").strip().rstrip("/")

    path = parsed.path or ""
    lower_path = path.lower()
    if lower_path.startswith("/console") or lower_path.startswith("/api"):
        path = ""

    normalized = urlunparse(
        (
            parsed.scheme or "https",
            parsed.netloc,
            path.rstrip("/") if path else "",
            "",
            "",
            "",
        )
    )
    return normalized.rstrip("/")
