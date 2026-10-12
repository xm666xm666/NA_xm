"""TOTP 动态验证码（RFC 6238 / Google Authenticator）。

把认证器原始密钥（Base32）写成 ``totp_secret``，或把密钥 / otpauth 链接
填进 ``otp_code``，会在请求当下生成 6 位码。
6 位 TOTP 与 8 位备用码仍按一次性验证码原样使用。
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import re
import struct
import time
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

_BASE32_RE = re.compile(r"^[A-Z2-7]+$")
_PLAIN_OTP_RE = re.compile(r"^\d{6,8}$")
_ALGO_MAP = {
    "sha1": hashlib.sha1,
    "sha256": hashlib.sha256,
    "sha512": hashlib.sha512,
}


def is_plain_otp_code(value: Any) -> bool:
    """认证器当前 6 位码，或 8 位备用码。"""
    text = str(value or "").strip()
    return bool(_PLAIN_OTP_RE.fullmatch(text))


def _strip_secret_noise(text: str) -> str:
    return re.sub(r"[\s\-]", "", str(text or "")).upper()


def _normalize_b32(secret: str) -> str:
    compact = _strip_secret_noise(secret)
    pad = (8 - len(compact) % 8) % 8
    return compact + ("=" * pad)


def looks_like_totp_secret(value: Any) -> bool:
    text = str(value or "").strip()
    if not text or is_plain_otp_code(text):
        return False
    return extract_totp_secret(text) is not None


def extract_totp_secret(value: Any) -> str | None:
    """从原始密钥或 otpauth:// 中取出 Base32 secret。"""
    text = str(value or "").strip()
    if not text or is_plain_otp_code(text):
        return None

    lower = text.lower()
    if lower.startswith("otpauth://"):
        parsed = urlparse(text)
        qs = parse_qs(parsed.query)
        secret = unquote((qs.get("secret") or [""])[0] or "")
        return extract_totp_secret(secret)

    compact = _strip_secret_noise(text)
    if len(compact) < 16 or not _BASE32_RE.fullmatch(compact):
        return None
    try:
        raw = base64.b32decode(_normalize_b32(compact), casefold=True)
    except (ValueError, TypeError):
        return None
    if len(raw) < 10:
        return None
    return compact


def pick_totp_secret(*values: Any, mapping: dict[str, Any] | None = None) -> str:
    keys = ("totp_secret", "otp_secret", "totp", "2fa_secret", "otp_code", "verification_code")
    candidates: list[Any] = list(values)
    if mapping:
        for key in keys:
            candidates.append(mapping.get(key))
    for item in candidates:
        secret = extract_totp_secret(item)
        if secret:
            return secret
    return ""


def generate_totp(
    secret: str,
    *,
    digits: int = 6,
    period: int = 30,
    algorithm: str = "sha1",
    timestamp: float | None = None,
) -> str:
    compact = extract_totp_secret(secret) or _strip_secret_noise(secret)
    if not compact:
        raise ValueError("TOTP 密钥为空")
    try:
        key = base64.b32decode(_normalize_b32(compact), casefold=True)
    except (ValueError, TypeError) as exc:
        raise ValueError("TOTP 密钥不是有效的 Base32") from exc
    period = max(1, int(period or 30))
    digits = min(8, max(6, int(digits or 6)))
    algo = _ALGO_MAP.get(str(algorithm or "sha1").lower().replace("-", ""), hashlib.sha1)
    counter = int((time.time() if timestamp is None else timestamp) // period)
    digest = hmac.new(key, struct.pack(">Q", counter), algo).digest()
    offset = digest[-1] & 0x0F
    number = struct.unpack(">I", digest[offset : offset + 4])[0] & 0x7FFFFFFF
    return str(number % (10 ** digits)).zfill(digits)


def resolve_otp_code(*values: Any, totp_secret: Any = "") -> str:
    """把一次性验证码或 TOTP 密钥解析成当前可提交的码。"""
    secret = pick_totp_secret(totp_secret, *values)
    for item in values:
        text = str(item or "").strip()
        if not text:
            continue
        if is_plain_otp_code(text):
            return text
        extracted = extract_totp_secret(text)
        if extracted:
            secret = secret or extracted
    if secret:
        return generate_totp(secret)
    return ""


def has_otp_source(*values: Any, totp_secret: Any = "") -> bool:
    if pick_totp_secret(totp_secret, *values):
        return True
    for item in values:
        if str(item or "").strip():
            return True
    return False
