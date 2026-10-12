"""将用户输入行转换为 New API 令牌创建请求体。"""

from __future__ import annotations

import re
from typing import Any

from .channel_models import get_models_for_group
from .token_api_fields import apply_model_limits, extract_model_limit, read_model_limits
from .token_duplicate_checker import normalize_model_limits

MODEL_KEYS = ("模型限制", "模型限制列表", "models", "token_model_limit")
MODEL_SEPARATORS = ("、", "，", ",", ";", "；")
TOKEN_QUOTA_KEYS = (
    "额度(tokens)",
    "额度（tokens）",
    "额度",
    "tokens",
    "token_quota",
    "remain_quota",
)
# New API 的上限：1,000,000,000 * QuotaPerUnit（当前为 500,000 tokens）。
# 与上游 controller/token.go 的校验保持一致，避免请求发出后才得到笼统失败。
MAX_TOKEN_QUOTA = 500_000_000_000_000
_INTEGER_RE = re.compile(r"^[+-]?\d+$")


def parse_model_list(raw: str) -> list[str]:
    text = (raw or "").strip()
    if not text:
        raise ValueError("模型限制列表不能为空")

    normalized = text
    for sep in MODEL_SEPARATORS:
        normalized = normalized.replace(sep, ",")

    models = [part.strip() for part in normalized.split(",") if part.strip()]
    if not models:
        raise ValueError("模型限制列表不能为空，多个模型可用顿号、或英文逗号分隔")
    return models


def _looks_like_quota_value(value: str) -> bool:
    """判断尾列是否像额度，避免把旧格式的多个 Tab 模型列误当作额度。"""
    return bool(re.fullmatch(r"[+-]?\d+(?:\.\d+)?", str(value or "").strip()))


def parse_optional_token_quota(value: Any) -> int | None:
    """解析可选的令牌额度（tokens）；空值表示无限额度。"""
    text = str(value or "").strip()
    if not text:
        return None
    if not _INTEGER_RE.fullmatch(text):
        raise ValueError("额度(tokens)必须是非负整数")

    quota = int(text)
    if quota < 0:
        raise ValueError("额度(tokens)不能为负数")
    if quota > MAX_TOKEN_QUOTA:
        raise ValueError(
            f"额度(tokens)超出 New API 上限（最大 {MAX_TOKEN_QUOTA}）"
        )
    return quota


def split_token_columns(line: str) -> tuple[str, str, str, str]:
    """解析名称、分组、模型列表及可选额度(tokens)。

    前三列为名称、分组、模型列表；第 4 列为可选额度（tokens）。
    列分隔支持 Tab / 空白 / 英文逗号；模型列表内可用顿号或英文逗号。
    空白与 CSV 格式通过末尾纯数字识别可选额度，省略时保持原三列行为。
    """
    text = line.strip()
    if not text:
        raise ValueError("空行")

    if "\t" in text:
        parts = [part.strip() for part in text.split("\t")]
        if len(parts) < 3:
            raise ValueError("Tab 分隔列不足 3 列：名称、分组、模型限制")
        name, group = parts[0], parts[1]
        if not name or not group or not parts[2]:
            raise ValueError("名称、分组、模型限制不能为空")

        # 兼容旧格式：曾允许将多个模型分别放进后续 Tab 列。
        # 只有最后一列看起来是数值时才把它识别为额度。
        if len(parts) > 3 and _looks_like_quota_value(parts[-1]):
            models_raw = "、".join(part for part in parts[2:-1] if part)
            return name, group, models_raw, parts[-1]
        models_raw = "、".join(part for part in parts[2:] if part)
        return name, group, models_raw, ""

    # 空白分列优先（模型列表可含英文逗号）
    ws_parts = re.split(r"\s+", text, maxsplit=2)
    if len(ws_parts) >= 3 and all(ws_parts):
        name, group, tail = (part.strip() for part in ws_parts)
        tail_parts = tail.rsplit(maxsplit=1)
        if len(tail_parts) == 2 and _looks_like_quota_value(tail_parts[-1]):
            return name, group, tail_parts[0].strip(), tail_parts[-1]
        return name, group, tail, ""

    # 整行用英文逗号作列分隔：名称,分组,模型1,模型2[,额度tokens]
    comma_count = text.count(",")
    if comma_count >= 2:
        parts = [part.strip() for part in text.split(",")]
        name, group = parts[0], parts[1]
        remaining = parts[2:]
        tokens_raw = ""
        if len(remaining) > 1 and _looks_like_quota_value(remaining[-1]):
            tokens_raw = remaining.pop()
        models_raw = ",".join(part for part in remaining if part)
        if name and group and models_raw:
            return name, group, models_raw, tokens_raw

    raise ValueError(
        "数据列不足，格式：名称 [Tab/空格/逗号] 分组 [Tab/空格/逗号] 模型列表 [可选额度tokens]"
    )


def parse_token_line(line: str) -> dict[str, str]:
    """无表头单行解析。第 4 列可选：额度(tokens)。"""
    name, group, models_raw, tokens_raw = split_token_columns(line)
    models = parse_model_list(models_raw)
    quota = parse_optional_token_quota(tokens_raw)

    if not name:
        raise ValueError("名称不能为空")
    if not group:
        raise ValueError("分组不能为空")

    row = {
        "名称": name,
        "分组": group,
        "模型限制": ",".join(models),
    }
    if quota is not None:
        row["额度(tokens)"] = str(quota)
    return row


def _is_header_line(line: str) -> bool:
    first = line.strip().lstrip("\ufeff").split()[0] if line.strip() else ""
    return first in ("名称", "name", "分组")


def _is_log_line(line: str) -> bool:
    return bool(re.match(r"^#\d+\s", line))


def parse_batch_rows(text: str) -> list[dict[str, str]]:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    rows: list[dict[str, str]] = []
    for line in lines:
        if _is_log_line(line) or _is_header_line(line):
            continue
        rows.append(parse_token_line(line))
    return rows


def validate_group_exists(group: str, known_groups: set[str]) -> None:
    if group not in known_groups:
        raise ValueError(f"未找到分组: {group}")


def validate_models_in_group(
    models: list[str],
    *,
    group: str,
    channels: list[dict[str, Any]],
) -> None:
    available = get_models_for_group(channels, group)
    if not available:
        raise ValueError(f"分组「{group}」下未找到可用渠道模型，请先创建渠道")

    unknown = [model for model in models if model not in available]
    if unknown:
        hint = "、".join(sorted(available))
        raise ValueError(
            f"模型不在分组渠道模型列表中: {'、'.join(unknown)}。"
            f"可用模型: {hint}"
        )


def build_token_payload(row: dict[str, Any]) -> dict[str, Any]:
    name = str(row.get("名称") or row.get("name") or "").strip()
    group = str(row.get("分组") or row.get("group") or "").strip()
    models_raw = str(row.get("模型限制") or row.get("模型限制列表") or "").strip()
    if not models_raw:
        for key in MODEL_KEYS:
            value = row.get(key)
            if value is not None and str(value).strip():
                models_raw = str(value).strip()
                break

    models = parse_model_list(models_raw)
    model_limit = ",".join(models)

    quota_raw = ""
    for key in TOKEN_QUOTA_KEYS:
        value = row.get(key)
        if value is not None and str(value).strip():
            quota_raw = str(value).strip()
            break
    quota = parse_optional_token_quota(quota_raw)

    payload: dict[str, Any] = {
        "name": name,
        "group": group,
        # New API 以这两个字段控制令牌额度；额度(tokens)缺省即保持无限。
        "unlimited_quota": quota is None,
        "remain_quota": 0 if quota is None else quota,
        "expired_time": -1,
        "cross_group_retry": False,
    }
    return apply_model_limits(payload, model_limit)


def token_has_model_limits(token: dict[str, Any], expected_limit: str) -> bool:
    enabled, current = read_model_limits(token)
    if not enabled or not current:
        return False
    expected = normalize_model_limits(expected_limit)
    return normalize_model_limits(current) == expected
