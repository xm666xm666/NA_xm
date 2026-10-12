# -*- coding: utf-8 -*-
"""站点 key → 生产 / 非生产。过渡期识别 test / uat / prod，不以三站为产品不变式。"""

from __future__ import annotations

from urllib.parse import urlparse

LEGACY_ORDER = ("test", "uat", "prod")
CLUSTER_BY_LEGACY = {"test": "非生产", "uat": "非生产", "prod": "生产"}
SKIP_KEYS = frozenset({"upstream"})


def cluster_label(env_key: str) -> str:
    raw = str(env_key or "").strip()
    key = raw.lower()
    if key in CLUSTER_BY_LEGACY:
        return CLUSTER_BY_LEGACY[key]
    if "非生产" in raw:
        return "非生产"
    if "生产" in raw:
        return "生产"
    if key in {"production", "prd"} or key.startswith("prod") or key.endswith("-prod"):
        return "生产"
    if any(tok in key for tok in ("test", "uat", "dev", "stage", "nonprod", "non-prod", "np-")):
        return "非生产"
    return raw or "未命名"


def public_host(url: str) -> str:
    text = str(url or "").strip()
    if not text:
        return ""
    try:
        parsed = urlparse(text if "://" in text else f"https://{text}")
        return parsed.netloc or text
    except Exception:  # noqa: BLE001
        return text


def is_site_config_key(key: str) -> bool:
    text = str(key or "").strip()
    if not text or text.startswith("_"):
        return False
    return text.lower() not in SKIP_KEYS


def ordered_site_keys(data: dict | None) -> list[str]:
    """sites.json 顶层站点 key：旧 test/uat/prod 优先，其后追加其它已出现的站点键。"""
    if not isinstance(data, dict):
        return []
    keys: list[str] = []
    seen: set[str] = set()
    for key in LEGACY_ORDER:
        if key in data and is_site_config_key(key) and key not in seen:
            keys.append(key)
            seen.add(key)
    for key in data:
        sk = str(key)
        if sk in seen or not is_site_config_key(sk):
            continue
        keys.append(sk)
        seen.add(sk)
    return keys
