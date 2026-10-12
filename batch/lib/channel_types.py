"""从 New API 站点或本地资源加载渠道类型列表。"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

import requests

ROOT_DIR = Path(__file__).resolve().parent.parent
BUNDLED_TYPES_PATH = ROOT_DIR / "channel_types.json"
PROJECT_CONSTANTS_PATH = (
    ROOT_DIR.parent / "web" / "src" / "constants" / "channel.constants.js"
)

CHANNEL_OPTION_PATTERN = re.compile(
    r"value:\s*(\d+)\s*,\s*color:\s*['\"][^'\"]*['\"]\s*,\s*label:\s*['\"]([^'\"]+)['\"]",
    re.MULTILINE,
)

# 精确别名：OpenAI(1) 与 Azure OpenAI(3) 不可通过模糊匹配混淆
EXACT_TYPE_ALIASES: dict[str, int] = {
    "openai": 1,
    "azure openai": 3,
    "azure_openai": 3,
    "azure": 3,
    "custom": 8,
    "自定义": 8,
    "自定义渠道": 8,
}


def load_bundled_types() -> list[dict[str, Any]]:
    with BUNDLED_TYPES_PATH.open(encoding="utf-8") as f:
        return json.load(f)


def parse_channel_options_from_js(content: str) -> list[dict[str, Any]]:
    matches = CHANNEL_OPTION_PATTERN.findall(content)
    if len(matches) < 5:
        return []
    seen: set[int] = set()
    result: list[dict[str, Any]] = []
    for value_str, label in matches:
        value = int(value_str)
        if value in seen:
            continue
        seen.add(value)
        result.append({"value": value, "label": label})
    return result


def load_from_project_constants() -> list[dict[str, Any]]:
    if not PROJECT_CONSTANTS_PATH.exists():
        return []
    content = PROJECT_CONSTANTS_PATH.read_text(encoding="utf-8")
    return parse_channel_options_from_js(content)


def fetch_from_server(base_url: str, timeout: int = 15) -> list[dict[str, Any]]:
    base_url = base_url.rstrip("/")
    session = requests.Session()

    try:
        index_resp = session.get(f"{base_url}/", timeout=timeout)
        index_resp.raise_for_status()
    except requests.RequestException:
        return []

    script_paths = re.findall(r'<script[^>]+src="([^"]+)"', index_resp.text)
    checked: set[str] = set()
    collected: list[dict[str, Any]] = []

    for script_path in script_paths:
        if script_path in checked:
            continue
        checked.add(script_path)
        script_url = urljoin(f"{base_url}/", script_path.lstrip("/"))
        try:
            js_resp = session.get(script_url, timeout=timeout)
            js_resp.raise_for_status()
        except requests.RequestException:
            continue
        parsed = parse_channel_options_from_js(js_resp.text)
        if len(parsed) > len(collected):
            collected = parsed
        if len(collected) >= 30:
            break

    return collected


def get_channel_types(base_url: str | None = None) -> tuple[list[dict[str, Any]], str]:
    if base_url:
        remote = fetch_from_server(base_url)
        if remote:
            return remote, "server"

    local = load_from_project_constants()
    if local:
        return local, "project"

    return load_bundled_types(), "bundled"


def get_all_type_labels_for_parse() -> list[str]:
    labels = {str(item["label"]) for item in load_bundled_types()}
    labels.update(EXACT_TYPE_ALIASES.keys())
    return sorted(labels, key=lambda item: len(item.split()), reverse=True)


def get_multiword_type_labels() -> list[str]:
    """返回包含空格的渠道类型名称，用于空格分隔行解析时合并字段。"""
    labels: set[str] = set()
    for item in load_bundled_types():
        label = str(item.get("label", "")).strip()
        if " " in label:
            labels.add(label)
    labels.update({"Azure OpenAI", "Anthropic Claude", "Google Gemini"})
    return sorted(labels, key=lambda item: len(item.split()), reverse=True)


def resolve_channel_type(type_input: str, types: list[dict[str, Any]]) -> int:
    raw = (type_input or "").strip()
    if not raw:
        raise ValueError("类型不能为空")

    if raw.isdigit():
        value = int(raw)
        if any(item["value"] == value for item in types):
            return value
        raise ValueError(f"未知渠道类型编号: {value}")

    normalized = raw.lower()

    if normalized in EXACT_TYPE_ALIASES:
        return EXACT_TYPE_ALIASES[normalized]

    for item in types:
        label = item["label"]
        if label == raw or label.lower() == normalized:
            return int(item["value"])

    raise ValueError(f"无法识别渠道类型: {raw}（注意 OpenAI 与 Azure OpenAI 是不同类型）")
