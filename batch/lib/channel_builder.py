"""将用户输入行转换为 New API 渠道创建请求体。"""

from __future__ import annotations

import json
import re
from typing import Any

from .channel_types import get_all_type_labels_for_parse

DEFAULT_SETTING = {
    "force_format": False,
    "thinking_to_content": False,
    "proxy": "",
    "pass_through_body_enabled": False,
    "system_prompt": "",
    "system_prompt_override": False,
}

REDIRECT_PATTERN = re.compile(r"^\s*(.+?)\s*->\s*(.+?)\s*$")

CHANNEL_TYPE_AZURE = 3
CHANNEL_TYPE_VOLCANO = 45  # 字节火山方舟、豆包通用（上游可能自动升级）
MAX_CHANNEL_REMARK_LENGTH = 255

API_VERSION_KEYS = ("默认API版本", "api_version", "default_api_version", "other")
RESPONSES_VERSION_KEYS = (
    "ResponsesAPI版本",
    "responses_api_version",
    "azure_responses_version",
)
TYPE_KEYS = ("类型", "type")
MODEL_KEYS = ("模型", "models", "model")
KEY_KEYS = ("秘钥", "密钥", "key")


def split_channel_rename(name: str) -> tuple[str, str]:
    """名称列支持 ``原名称=>新名称``（无空格）用于更新时改名；否则匹配名与新名相同。"""
    text = (name or "").strip()
    if "=>" not in text:
        return text, text
    old, new = text.split("=>", 1)
    old, new = old.strip(), new.strip()
    if not old or not new:
        raise ValueError("渠道重命名格式应为 原名称=>新名称")
    return old, new


def parse_model_redirect(value: str) -> tuple[str, str]:
    text = (value or "").strip()
    if not text:
        raise ValueError("模型重定向不能为空，格式: 源模型->目标模型")

    match = REDIRECT_PATTERN.match(text)
    if not match:
        raise ValueError(f"模型重定向格式错误: {value}，应为 源模型->目标模型")

    source = match.group(1).strip()
    target = match.group(2).strip()
    if not source or not target:
        raise ValueError(f"模型重定向格式错误: {value}")
    return source, target


def normalize_base_url(url: str) -> str:
    text = (url or "").strip()
    if not text:
        raise ValueError("base_url 不能为空")
    return text.rstrip("/")


def pick_row_value(row: dict[str, Any], keys: tuple[str, ...]) -> str:
    for key in keys:
        value = row.get(key)
        if value is not None and str(value).strip() != "":
            return str(value).strip()
    return ""


def validate_group_exists(group: str, known_groups: set[str]) -> None:
    if group not in known_groups:
        raise ValueError(f"未找到分组: {group}")


def build_channel_payload(
    row: dict[str, Any],
    *,
    channel_type: int,
    default_key: str,
    known_groups: set[str],
    require_key: bool = True,
) -> dict[str, Any]:
    name = str(row.get("名称") or row.get("name") or "").strip()
    group = str(row.get("分组") or row.get("group") or "").strip()
    model = pick_row_value(row, MODEL_KEYS)
    base_url = normalize_base_url(str(row.get("base_url") or row.get("BaseURL") or ""))
    redirect_raw = str(row.get("模型重定向") or row.get("model_redirect") or "")
    key = pick_row_value(row, KEY_KEYS) or (default_key or "").strip()
    api_version = pick_row_value(row, API_VERSION_KEYS)
    responses_version = pick_row_value(row, RESPONSES_VERSION_KEYS)

    if not name:
        raise ValueError("名称不能为空")
    if not group:
        raise ValueError("分组不能为空")
    validate_group_exists(group, known_groups)
    if not model:
        raise ValueError("模型不能为空")
    if len(base_url) > MAX_CHANNEL_REMARK_LENGTH:
        raise ValueError(
            f"base_url 超过 {MAX_CHANNEL_REMARK_LENGTH} 个字符，无法写入渠道备注"
        )
    if require_key and not key:
        raise ValueError("秘钥不能为空（请在行内填写秘钥列或配置全局密钥）")

    if channel_type == CHANNEL_TYPE_AZURE and not api_version:
        raise ValueError(
            "Azure OpenAI 渠道必须填写「默认API版本」，例如 2025-04-01-preview"
        )

    if not redirect_raw.strip():
        if channel_type == CHANNEL_TYPE_AZURE:
            model_mapping = None
        else:
            raise ValueError("模型重定向不能为空，格式: 源模型->目标模型")
    else:
        source_model, target_model = parse_model_redirect(redirect_raw)
        if source_model != model:
            raise ValueError(
                f"模型重定向左侧「{source_model}」与模型列「{model}」不一致"
            )
        model_mapping = json.dumps({source_model: target_model}, ensure_ascii=False)

    other_settings: dict[str, str] = {}
    if channel_type == CHANNEL_TYPE_AZURE and responses_version:
        other_settings["azure_responses_version"] = responses_version

    channel = {
        "name": name,
        "type": channel_type,
        "key": key,
        "base_url": base_url,
        # 新增渠道时，管理员备注固定记录该渠道的规范化上游地址。
        "remark": base_url,
        "models": model,
        "group": group,
        "status": 1,
        "auto_ban": 1,
        "priority": 0,
        "weight": 0,
        "setting": json.dumps(DEFAULT_SETTING, ensure_ascii=False),
        "settings": json.dumps(other_settings, ensure_ascii=False),
    }

    if model_mapping:
        channel["model_mapping"] = model_mapping
    if channel_type == CHANNEL_TYPE_AZURE:
        channel["other"] = api_version

    return {
        "mode": "single",
        "channel": channel,
    }


REDIRECT_TOKEN_RE = re.compile(r"\S+->\S+")
URL_TOKEN_RE = re.compile(r"https?://\S+")
API_VERSION_TOKEN_RE = re.compile(r"^\d{4}-\d{2}-\d{2}(?:[-\w.]*)?$")


def _match_multiword_type(tokens: list[str], start: int) -> tuple[str, int] | None:
    """从 tokens[start:] 匹配最长渠道类型名，返回 (类型名, 消耗 token 数)。"""
    for label in get_all_type_labels_for_parse():
        words = label.split()
        end = start + len(words)
        if end <= len(tokens) and tokens[start:end] == words:
            return label, len(words)
    if start < len(tokens):
        return tokens[start], 1
    return None


def _parse_front_section(front_tokens: list[str]) -> tuple[str, str, str, str]:
    if len(front_tokens) < 4:
        raise ValueError("数据列不足，至少需要：名称 分组 类型 模型")

    name = front_tokens[0]
    group = front_tokens[1]
    model = front_tokens[-1]

    type_tokens = front_tokens[2:-1]
    if not type_tokens:
        raise ValueError("缺少渠道类型")

    matched = _match_multiword_type(type_tokens, 0)
    if not matched:
        raise ValueError("无法识别渠道类型")
    channel_type, used = matched
    if used != len(type_tokens):
        raise ValueError(f"类型字段解析异常: {' '.join(type_tokens)}")

    return name, group, channel_type, model


def _parse_tail_section(
    tail: str, *, require_api_version: bool, require_secret: bool = True
) -> tuple[str, str, str]:
    url_match = URL_TOKEN_RE.search(tail)
    if not url_match:
        raise ValueError("缺少 base_url（https://...）")

    base_url = url_match.group(0).rstrip("/")
    rest = tail[url_match.end() :].strip().split()

    api_version = ""
    secret = ""
    if not rest:
        if require_secret:
            raise ValueError("缺少秘钥")
        return base_url, "", ""

    if len(rest) >= 2 and API_VERSION_TOKEN_RE.match(rest[0]):
        api_version = rest[0]
        secret = rest[1]
    elif len(rest) == 1 and API_VERSION_TOKEN_RE.match(rest[0]):
        api_version = rest[0]
    else:
        secret = rest[-1]

    if require_secret and not secret:
        raise ValueError("缺少秘钥")
    if require_api_version and not api_version:
        raise ValueError("Azure OpenAI 渠道缺少默认API版本，例如 2025-04-01-preview")

    return base_url, api_version, secret


def _requires_api_version(channel_type: str) -> bool:
    normalized = channel_type.strip().lower()
    if normalized in {"azure openai", "azure", "azure_openai"}:
        return True
    return normalized.isdigit() and int(normalized) == CHANNEL_TYPE_AZURE


def parse_data_line(line: str, *, require_secret: bool = True) -> dict[str, str]:
    """无表头单行解析。列顺序：名称 分组 类型 模型 模型->上游 base_url [默认API版本] 秘钥

    更新原配置时可将 ``require_secret=False``：未填秘钥则保留渠道原密钥。
    """
    redirect_match = REDIRECT_TOKEN_RE.search(line)
    if not redirect_match:
        raise ValueError("无法解析：缺少 模型->上游 格式")

    redirect = redirect_match.group(0)
    front_tokens = line[: redirect_match.start()].strip().split()
    name, group, channel_type, model = _parse_front_section(front_tokens)

    if parse_model_redirect(redirect)[0] != model:
        raise ValueError(f"模型重定向左侧与模型不一致：{redirect} / {model}")

    base_url, api_version, secret = _parse_tail_section(
        line[redirect_match.end() :].strip(),
        require_api_version=_requires_api_version(channel_type),
        require_secret=require_secret,
    )

    return {
        "名称": name,
        "分组": group,
        "类型": channel_type,
        "模型": model,
        "模型重定向": redirect,
        "base_url": base_url,
        "默认API版本": api_version,
        "秘钥": secret,
    }


def _is_header_line(line: str) -> bool:
    first = line.strip().lstrip("\ufeff").split()[0] if line.strip() else ""
    return first in ("名称", "name", "分组", "类型")


def _is_log_line(line: str) -> bool:
    return bool(re.match(r"^#\d+\s", line))


def ensure_batch_keys_available(
    rows: list[dict[str, Any]], default_key: str
) -> None:
    """行内末列有秘钥则无需全局秘钥；仅当某行缺秘钥且未配置全局秘钥时报错。"""
    for index, row in enumerate(rows, start=1):
        key = pick_row_value(row, KEY_KEYS)
        if not key and not (default_key or "").strip():
            name = str(row.get("名称") or row.get("name") or f"row-{index}")
            raise ValueError(
                f"第 {index} 行「{name}」缺少秘钥，请在行末填写秘钥或配置全局秘钥"
            )


def parse_batch_rows(text: str, *, require_secret: bool = True) -> list[dict[str, str]]:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return []

    rows: list[dict[str, str]] = []
    for line in lines:
        if _is_log_line(line) or _is_header_line(line):
            continue
        rows.append(parse_data_line(line, require_secret=require_secret))
    return rows
