"""渠道行 + 用户名 → 令牌批量文本。"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from lib.agent_token_helper import build_token_batch_text, parse_token_usernames  # noqa: E402


SAMPLE = (
    "demo-alpha-test-glm-x demo-alpha-test OpenAI "
    "demo-alpha-test-glm-x "
    "demo-alpha-test-glm-x->ep-demo "
    "https://ark.example.com ark-key"
)


def test_parse_usernames():
    assert parse_token_usernames("样例甲\n样例乙,样例丙") == ["样例甲", "样例乙", "样例丙"]


def test_build_one_user_multi_channel():
    ch2 = (
        "demo-alpha-test-glm-y demo-alpha-test OpenAI demo-alpha-test-glm-y "
        "demo-alpha-test-glm-y->ep-2 https://ark.example.com ark-key"
    )
    text = build_token_batch_text(SAMPLE + "\n" + ch2, "样例甲")
    lines = text.splitlines()
    assert len(lines) == 2
    assert lines[0].startswith("demo-alpha-test-glm-x-样例甲\t")
    assert lines[1].startswith("demo-alpha-test-glm-y-样例甲\t")


if __name__ == "__main__":
    test_parse_usernames()
    test_build_one_user_multi_channel()
    print("ok")
