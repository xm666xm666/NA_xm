"""TOTP 解析与生成。"""

from __future__ import annotations

import hmac
import hashlib
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "batch"))

from lib.totp import (  # noqa: E402
    extract_totp_secret,
    generate_totp,
    has_otp_source,
    is_plain_otp_code,
    looks_like_totp_secret,
    resolve_otp_code,
)


def test_rfc6238_sha1_6digits():
        # Low-entropy Base32 fixture: 10 zero bytes.
    secret = "AAAAAAAAAAAAAAAA"
    assert generate_totp(secret, digits=6, timestamp=59) == "812658"
    assert generate_totp(secret, digits=8, timestamp=59) == "30812658"


def test_plain_code_passthrough():
    assert is_plain_otp_code("123456")
    assert is_plain_otp_code("12345678")
    assert not is_plain_otp_code("12345")
    assert resolve_otp_code("654321") == "654321"
    assert resolve_otp_code("87654321") == "87654321"


def test_extract_secret_and_urls():
    secret = "AAAAAAAAAAAAAAAA"
    assert extract_totp_secret(secret) == secret
    assert extract_totp_secret("aaaa aaaa-aaaa aaaa") == secret
    assert extract_totp_secret(f"otpauth://totp/NA:admin?secret={secret}&issuer=NA") == secret
    assert looks_like_totp_secret(secret)
    assert not looks_like_totp_secret("123456")
    assert extract_totp_secret("short") is None


def test_resolve_generates_six_digits():
    secret = "AAAAAAAAAAAAAAAA"
    code = resolve_otp_code(secret)
    assert len(code) == 6 and code.isdigit()
    assert resolve_otp_code("111111", totp_secret=secret) == "111111"
    assert resolve_otp_code(totp_secret=secret) == code or len(resolve_otp_code(totp_secret=secret)) == 6


def test_has_otp_source():
    secret = "AAAAAAAAAAAAAAAA"
    assert has_otp_source(totp_secret=secret)
    assert has_otp_source("123456")
    assert has_otp_source(secret)
    assert not has_otp_source("", totp_secret="")


def test_hmac_matches_stdlib():
    secret = "AAAAAAAAAAAAAAAA"
    import base64

    key = base64.b32decode(secret)
    counter = int(59 // 30)
    digest = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    number = struct.unpack(">I", digest[offset : offset + 4])[0] & 0x7FFFFFFF
    assert str(number % 1_000_000).zfill(6) == generate_totp(secret, timestamp=59)


if __name__ == "__main__":
    test_rfc6238_sha1_6digits()
    test_plain_code_passthrough()
    test_extract_secret_and_urls()
    test_resolve_generates_six_digits()
    test_has_otp_source()
    test_hmac_matches_stdlib()
    print("ok")
