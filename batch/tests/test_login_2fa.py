"""登录两步验证：兼容 require_2fa 与 v1.0.1 mfa_action。"""

from __future__ import annotations

import sys
from pathlib import Path

BATCH_DIR = Path(__file__).resolve().parents[1]
if str(BATCH_DIR) not in sys.path:
    sys.path.insert(0, str(BATCH_DIR))

from lib.api_client import login_payload_needs_2fa  # noqa: E402


def test_login_payload_needs_2fa():
    assert login_payload_needs_2fa({"require_2fa": True}) == "verify"
    assert login_payload_needs_2fa({"mfa_action": "verify"}) == "verify"
    assert login_payload_needs_2fa({"mfa_action": "setup"}) == "setup"
    assert login_payload_needs_2fa({"id": 1, "role": 100}) == ""
    assert login_payload_needs_2fa({}) == ""
    assert login_payload_needs_2fa(None) == ""


if __name__ == "__main__":
    test_login_payload_needs_2fa()
    print("ok")
