"""规则提取：路径型上游模型 /models/..."""

from __future__ import annotations

import sys
from pathlib import Path

AGENT_DIR = Path(__file__).resolve().parent.parent
if str(AGENT_DIR) not in sys.path:
    sys.path.insert(0, str(AGENT_DIR))

from lib.rule_extractor import extract_by_rules  # noqa: E402


SAMPLE = """
biz-agent-platform-uat-glm-5.2
openai
sk-glm52-9b5c75078f084756b6100a83689ca80a
/models/GLM-5.2-FP8
http://111.127.53.163:8000
"""


def test_path_model_openai_block():
    fields = extract_by_rules(SAMPLE)
    assert fields.missing_fields() == []
    assert fields.name == "biz-agent-platform-uat-glm-5.2"
    assert fields.type_label == "OpenAI"
    assert fields.upstream_model == "/models/GLM-5.2-FP8"
    assert fields.base_url == "http://111.127.53.163:8000"
    assert fields.api_key.startswith("sk-glm52-")
    assert fields.model == "biz-agent-platform-uat-glm-5.2"


def test_path_model_without_leading_slash():
    text = SAMPLE.replace("/models/GLM-5.2-FP8", "models/GLM-5.2-FP8")
    fields = extract_by_rules(text)
    assert fields.upstream_model == "/models/GLM-5.2-FP8"


if __name__ == "__main__":
    test_path_model_openai_block()
    test_path_model_without_leading_slash()
    print("ok")
