"""更新原配置提取：须显式 require_key=False；默认创建提取仍要求密钥。"""

from __future__ import annotations

import sys
from pathlib import Path

AGENT_DIR = Path(__file__).resolve().parents[1]
ROOT = AGENT_DIR.parent
if str(AGENT_DIR) not in sys.path:
    sys.path.insert(0, str(AGENT_DIR))

from lib.channel_extractor import extract_channels  # noqa: E402

UPGRADE_SAMPLE = (ROOT / "examples" / "agent" / "volcano-upgrade" / "input.txt").read_text(
    encoding="utf-8"
)


def test_default_extract_still_requires_key():
    result = extract_channels(UPGRADE_SAMPLE, use_llm=False)
    assert result.success is False
    combined = " ".join([result.message] + [item.message for item in result.items])
    assert "api_key" in combined


def test_update_extract_omits_key():
    result = extract_channels(UPGRADE_SAMPLE, use_llm=False, require_key=False)
    assert result.success is True
    assert "更新" in result.message
    line = result.channel_line
    assert "demo-alpha-test-glm-4.7" in line
    assert "demo-alpha-test" in line
    assert "字节火山方舟、豆包通用" in line
    assert "demo-alpha-test-glm-4.7->GLM-5.2" in line
    assert "ark.cn-beijing.volces.com" in line
    tokens = line.split()
    assert not any(t.startswith("sk-") or t.startswith("ark-") for t in tokens)


def test_update_extract_ignores_existing_key():
    text = UPGRADE_SAMPLE.rstrip() + "\nark-00000000-0000-4000-8000-000000000001-demo\n"
    result = extract_channels(text, use_llm=False, require_key=False)
    assert result.success is True
    assert "ark-" not in result.channel_line


def test_create_extract_with_key_still_keeps_key():
    text = (ROOT / "examples" / "agent" / "volcano" / "input.txt").read_text(encoding="utf-8")
    result = extract_channels(text, use_llm=False)
    assert result.success is True
    assert "00000000-0000-4000-8000-000000000001" in result.channel_line
    assert "更新原配置" not in result.message


if __name__ == "__main__":
    test_default_extract_still_requires_key()
    test_update_extract_omits_key()
    test_update_extract_ignores_existing_key()
    test_create_extract_with_key_still_keeps_key()
    print("ok")
