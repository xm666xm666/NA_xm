"""本地令牌秘钥库：本工具创建令牌时持久化明文，供后续导出。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .url_utils import normalize_na_base_url

ROOT_DIR = Path(__file__).resolve().parent.parent
VAULT_PATH = ROOT_DIR / "data" / "token_keys.json"


def _normalize_site(base_url: str) -> str:
    text = normalize_na_base_url(base_url)
    if not text:
        return ""
    return f"{text}/"


def _load_all() -> dict[str, Any]:
    if not VAULT_PATH.exists():
        return {}
    try:
        data = json.loads(VAULT_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _save_all(data: dict[str, Any]) -> None:
    VAULT_PATH.parent.mkdir(parents=True, exist_ok=True)
    VAULT_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def load_site_keys(base_url: str) -> tuple[dict[int, str], dict[str, str]]:
    site = _normalize_site(base_url)
    bucket = _load_all().get(site) or {}
    by_id_raw = bucket.get("by_id") or {}
    by_name_raw = bucket.get("by_name") or {}

    by_id: dict[int, str] = {}
    for key, value in by_id_raw.items():
        text = str(value or "").strip()
        if text and "***" not in text:
            by_id[int(key)] = text

    by_name: dict[str, str] = {}
    for key, value in by_name_raw.items():
        text = str(value or "").strip()
        if text and "***" not in text:
            by_name[str(key)] = text
    return by_id, by_name


def save_token_key(
    base_url: str,
    *,
    token_id: int | None = None,
    name: str | None = None,
    key: str,
) -> None:
    secret = (key or "").strip()
    if not secret or "***" in secret:
        return

    site = _normalize_site(base_url)
    data = _load_all()
    bucket = dict(data.get(site) or {})
    by_id = dict(bucket.get("by_id") or {})
    by_name = dict(bucket.get("by_name") or {})

    if token_id is not None:
        by_id[str(int(token_id))] = secret
    if name:
        by_name[str(name).strip()] = secret

    bucket["by_id"] = by_id
    bucket["by_name"] = by_name
    data[site] = bucket
    _save_all(data)
