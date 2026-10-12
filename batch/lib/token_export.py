"""导出全部令牌：申请人、秘钥、base_url、可用模型。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .api_client import NewAPIClient, authenticate_client
from .token_api_fields import read_model_limits
from .token_key_import import parse_pasted_token_keys
from .token_key_resolver import TokenKeyResolver, is_masked_key
from .url_utils import normalize_na_base_url


def parse_applicant(name: str) -> str:
    """名称最后一个「-」后的字段为申请人，例如 demo-alpha-test-glm-x-样例甲 → 样例甲。"""
    text = (name or "").strip()
    if not text:
        return ""
    if "-" in text:
        return text.rsplit("-", 1)[-1].strip()
    return text


def normalize_export_base_url(base_url: str) -> str:
    text = normalize_na_base_url(base_url)
    if not text:
        return ""
    return f"{text}/"


def format_token_key(raw_key: str) -> str:
    key = (raw_key or "").strip()
    if not key or is_masked_key(key):
        return ""
    if key.lower().startswith("sk-"):
        return key
    return f"sk-{key}"


def _parse_models(limits: str) -> list[str]:
    return [part.strip() for part in limits.split(",") if part.strip()]



def _resolve_token_record(client: NewAPIClient, token: dict[str, Any]) -> dict[str, Any]:
    record = dict(token)
    token_id = record.get("id")
    if token_id is None:
        return record

    need_detail = is_masked_key(str(record.get("key") or ""))
    _enabled, limits = read_model_limits(record)
    if not limits:
        need_detail = True

    if not need_detail:
        return record

    try:
        detail = client.get_token(int(token_id))
    except Exception:  # noqa: BLE001
        return record

    if is_masked_key(str(record.get("key") or "")):
        record["key"] = detail.get("key") or record.get("key")
    if not read_model_limits(record)[1]:
        for field in (
            "model_limits",
            "token_model_limit",
            "model_limits_enabled",
            "token_model_limit_enabled",
        ):
            if field in detail:
                record[field] = detail[field]
    return record


def format_token_block(token: dict[str, Any], base_url: str) -> str:
    name = str(token.get("name") or "").strip()
    applicant = parse_applicant(name)
    secret = format_token_key(str(token.get("key") or ""))
    site_url = normalize_export_base_url(base_url)

    _enabled, limits = read_model_limits(token)
    models = _parse_models(limits)

    lines = [applicant, secret, f"base_url={site_url}", "模型名："]
    if models:
        lines.extend(models)
    else:
        lines.append("无限制")

    return "\n".join(lines)


@dataclass
class ExportResult:
    text: str
    total: int
    key_resolved: int
    key_missing: int
    key_sources: list[str]
    api_masked: bool = False
    pasted_matched: int = 0
    key_api_fetched: int = 0
    sample_api_key: str = ""


def export_all_tokens_text(
    *,
    base_url: str,
    auth: dict[str, Any],
    pasted_keys: str = "",
) -> ExportResult:
    base_url = normalize_na_base_url(base_url)
    if not base_url:
        raise RuntimeError("请填写 New API 地址")

    client = NewAPIClient(base_url)
    authenticate_client(client, auth)

    tokens = client.list_all_tokens()
    api_masked = any(is_masked_key(str(t.get("key") or "")) for t in tokens)
    sample_api_key = str((tokens[0] or {}).get("key") or "")[:24]

    resolver = TokenKeyResolver.build(
        base_url=base_url,
        user_id=client.user_id,
    )
    pasted_matched = 0
    if pasted_keys.strip():
        resolver.load_pasted_keys(pasted_keys, tokens)
        parsed = parse_pasted_token_keys(pasted_keys)
        pasted_matched = sum(
            1
            for name in parsed
            if not name.startswith("__sk_only__:")
        )
    key_api_count = resolver.fetch_plain_keys(client, tokens)
    if not resolver.sources and not is_masked_key(str((tokens[0] or {}).get("key") or "")):
        resolver.sources.append("api")

    blocks: list[str] = []
    key_resolved = 0
    key_missing = 0

    for token in tokens:
        record = _resolve_token_record(client, token)
        plain_key = resolver.resolve(record)
        record["key"] = plain_key
        secret = format_token_key(plain_key)
        if secret:
            key_resolved += 1
            if is_masked_key(str(token.get("key") or "")):
                resolver.remember_created(record, plain_key)
        else:
            key_missing += 1
        blocks.append(format_token_block(record, base_url))

    return ExportResult(
        text="\n\n".join(blocks),
        total=len(tokens),
        key_resolved=key_resolved,
        key_missing=key_missing,
        key_sources=resolver.sources,
        api_masked=api_masked,
        pasted_matched=pasted_matched,
        key_api_fetched=key_api_count,
        sample_api_key=sample_api_key,
    )
