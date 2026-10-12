"""令牌行解析：空格分列 + 逗号分隔多模型。"""

from __future__ import annotations

import sys
from pathlib import Path

BATCH_DIR = Path(__file__).resolve().parents[1]
if str(BATCH_DIR) not in sys.path:
    sys.path.insert(0, str(BATCH_DIR))

from lib.token_builder import (  # noqa: E402
    build_token_payload,
    parse_token_line,
    split_token_columns,
)


def test_space_columns_comma_models():
    line = (
        "ai-train-camp-uat-glm5.2&qwen3.7&gpt5.5-朱思婕 "
        "ai-train-camp-uat "
        "ai-train-camp-uat-glm-5.2,ai-train-camp-uat-qwen3.7-plus,ai-train-camp-uat-gpt-5.5"
    )
    name, group, models_raw, tokens_raw = split_token_columns(line)
    assert name == "ai-train-camp-uat-glm5.2&qwen3.7&gpt5.5-朱思婕"
    assert group == "ai-train-camp-uat"
    assert "ai-train-camp-uat-qwen3.7-plus" in models_raw
    assert tokens_raw == ""

    row = parse_token_line(line)
    assert row["名称"] == name
    assert row["分组"] == "ai-train-camp-uat"
    assert row["模型限制"] == (
        "ai-train-camp-uat-glm-5.2,ai-train-camp-uat-qwen3.7-plus,ai-train-camp-uat-gpt-5.5"
    )


def test_tab_columns():
    line = "tok-a\tg1\tm1,m2"
    assert split_token_columns(line) == ("tok-a", "g1", "m1,m2", "")


def test_csv_columns_still_work():
    line = "tok-a,g1,m1,m2"
    name, group, models_raw, tokens_raw = split_token_columns(line)
    assert name == "tok-a"
    assert group == "g1"
    assert models_raw == "m1,m2"
    assert tokens_raw == ""


def test_顿号_models():
    line = "tok-a g1 m1、m2"
    row = parse_token_line(line)
    assert row["分组"] == "g1"
    assert row["模型限制"] == "m1,m2"


def test_optional_tokens_create_limited_quota():
    row = parse_token_line("tok-a\tg1\tm1,m2\t500000")
    assert row["额度(tokens)"] == "500000"

    payload = build_token_payload(row)
    assert payload["unlimited_quota"] is False
    assert payload["remain_quota"] == 500000


def test_optional_tokens_support_space_and_csv_input():
    space_row = parse_token_line("tok-a g1 m1,m2 1000000")
    csv_row = parse_token_line("tok-b,g1,m1,m2,2000000")
    assert space_row["额度(tokens)"] == "1000000"
    assert csv_row["额度(tokens)"] == "2000000"


def test_missing_tokens_stays_unlimited():
    payload = build_token_payload(parse_token_line("tok-a g1 m1,m2"))
    assert payload["unlimited_quota"] is True
    assert payload["remain_quota"] == 0


def test_negative_tokens_rejected():
    try:
        parse_token_line("tok-a\tg1\tm1\t-1")
    except ValueError as exc:
        assert "不能为负数" in str(exc)
    else:
        raise AssertionError("负额度应被拒绝")


if __name__ == "__main__":
    test_space_columns_comma_models()
    test_tab_columns()
    test_csv_columns_still_work()
    test_顿号_models()
    test_optional_tokens_create_limited_quota()
    test_optional_tokens_support_space_and_csv_input()
    test_missing_tokens_stays_unlimited()
    test_negative_tokens_rejected()
    print("ok")
