"""规则引擎：从杂乱文本中提取渠道核心字段。"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .block_parser import split_into_blocks
from .text_splitter import split_input_lines
from .group_deriver import derive_group_from_name, derive_model_from_name
from .azure_utils import (
    extract_api_version_from_url,
    find_azure_url,
    is_azure_host,
    normalize_azure_base_url,
    parse_azure_url,
)
from .patterns import (
    API_VERSION_RE,
    ARK_KEY_RE,
    AZURE_KEY_RE,
    EP_MODEL_RE,
    ENV_SUFFIX_RE,
    NOISE_LINE_RE,
    PATH_MODEL_RE,
    PROJECT_NAME_RE,
    SK_KEY_RE,
    URL_RE,
    UUID_RE,
    VERSION_TAG_RE,
    VOLCANO_ENDPOINT_RE,
)
from .custom_utils import (
    is_custom_channel_block,
    is_deploy_model_name,
    pick_custom_fields,
    pick_deploy_model,
    pick_model_mapping,
)
from .type_registry import (
    AZURE_TYPE_LABEL,
    ChannelTypeInfo,
    OPENAI_TYPE_LABEL,
    get_azure_type,
    get_openai_type,
    get_volcano_type,
    resolve_type_hint,
)


@dataclass
class ExtractedFields:
    name: str = ""
    group: str = ""
    type_label: str = ""
    model: str = ""
    upstream_model: str = ""
    base_url: str = ""
    api_version: str = ""
    api_key: str = ""
    confidence: float = 0.0
    sources: dict[str, str] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    llm_invoked: bool = False
    llm_success: bool = False
    llm_provider: str = ""
    llm_model: str = ""
    llm_filled: list[str] = field(default_factory=list)
    llm_error: str = ""

    def missing_fields(self, *, require_key: bool = True) -> list[str]:
        required = ["name", "type_label", "model", "upstream_model"]
        if require_key:
            required.append("api_key")
        missing = []
        for key in required:
            if not getattr(self, key, "").strip():
                missing.append(key)
        if self.type_label and not self.base_url:
            from .type_registry import get_type_by_label

            info = get_type_by_label(self.type_label)
            if info and not info.base_url:
                missing.append("base_url")
        return missing


def _split_lines(text: str) -> list[str]:
    lines: list[str] = []
    for raw in split_input_lines(text):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if NOISE_LINE_RE.match(line) or VERSION_TAG_RE.match(line):
            continue
        lines.append(line)
    return lines


def _score_project_name(line: str) -> float:
    if not PROJECT_NAME_RE.match(line):
        return 0.0
    score = 1.0
    segments = line.split("-")
    score += min(len(segments) * 0.15, 1.0)
    if re.search(r"(?:test|prd|prod|uat)", line, re.IGNORECASE):
        score += 0.35
    if re.search(r"(?:glm|gpt|qwen|deepseek)", line, re.IGNORECASE):
        score += 0.5
    if len(segments) <= 3 and not re.search(r"(?:test|prd)", line, re.IGNORECASE):
        score -= 0.4
    return score


def _line_has_secret(line: str) -> bool:
    stripped = line.strip()
    return bool(
        ARK_KEY_RE.search(line)
        or UUID_RE.search(line)
        or SK_KEY_RE.search(line)
        or AZURE_KEY_RE.match(stripped)
    )


def _pick_project_name(lines: list[str]) -> tuple[str, str]:
    best = ""
    best_score = 0.0
    for line in lines:
        if _line_has_secret(line) or VOLCANO_ENDPOINT_RE.search(line) or URL_RE.search(line):
            continue
        score = _score_project_name(line)
        # 部署环境名（-prd/-test）降权，优先采用渠道标题行
        if ENV_SUFFIX_RE.search(line):
            score -= 0.8
        if score > best_score:
            best = line
            best_score = score
    source = "rule:project_name" if best else ""
    return best, source


def _pick_api_key(lines: list[str]) -> tuple[str, str]:
    for line in lines:
        stripped = line.strip()
        if stripped.lower().startswith("ark-"):
            match = ARK_KEY_RE.search(stripped)
            if match:
                return match.group(0), "rule:ark_key"
    for line in lines:
        stripped = line.strip()
        if AZURE_KEY_RE.match(stripped):
            return stripped, "rule:azure_key"
    for line in lines:
        if ARK_KEY_RE.search(line):
            continue
        match = UUID_RE.search(line)
        if match:
            return match.group(0), "rule:uuid"
    for line in lines:
        match = SK_KEY_RE.search(line)
        if match:
            return match.group(0), "rule:sk_key"
    return "", ""


def _pick_azure_deploy_model(lines: list[str], channel_name: str) -> tuple[str, str]:
    upstream, src = pick_deploy_model(lines, channel_name)
    if upstream:
        return upstream, src.replace("deploy_model", "azure_deploy_model")
    return "", ""


def _pick_azure_fields(lines: list[str], channel_name: str) -> dict[str, tuple[str, str]]:
    """从 Azure 门户粘贴信息中提取字段。"""
    raw_url = find_azure_url(lines)
    if not raw_url:
        return {}

    type_info = get_azure_type()
    base_url, api_version = parse_azure_url(raw_url)
    if not api_version:
        api_version, _ = _pick_api_version(lines)

    api_key, key_src = _pick_api_key(lines)
    upstream, upstream_src = _pick_azure_deploy_model(lines, channel_name)

    return {
        "type_label": (type_info.label, "rule:azure_url_inferred"),
        "type_info": (type_info, "rule:azure_url_inferred"),
        "base_url": (base_url, "rule:azure_url_parsed"),
        "api_version": (api_version, "rule:azure_url_parsed" if api_version else ""),
        "api_key": (api_key, key_src),
        "upstream_model": (upstream, upstream_src),
    }


def _is_ep_model(value: str) -> bool:
    return bool(EP_MODEL_RE.fullmatch((value or "").strip()))


def _pick_upstream_model(lines: list[str], *, channel_name: str = "") -> tuple[str, str]:
    upstream, src = pick_model_mapping(lines, channel_name)
    if upstream:
        from .custom_utils import normalize_deploy_model

        return normalize_deploy_model(upstream), src

    for line in lines:
        match = EP_MODEL_RE.search(line)
        if match:
            return match.group(0), "rule:ep_model"

    for line in lines:
        stripped = line.strip()
        if PATH_MODEL_RE.match(stripped):
            return stripped if stripped.startswith("/") else f"/{stripped}", "rule:path_model"

    upstream, src = _pick_azure_deploy_model(lines, channel_name)
    if upstream:
        return upstream, src

    for line in lines:
        if _line_has_secret(line) or URL_RE.search(line):
            continue
        if resolve_type_hint(line):
            continue
        if _score_project_name(line) >= 1.0 and not is_deploy_model_name(line):
            continue
        if re.match(r"^[a-zA-Z0-9][\w.-]{3,}$", line):
            return line, "rule:model_token"
    return "", ""


def _is_technical_line(line: str) -> bool:
    return bool(
        _line_has_secret(line)
        or VOLCANO_ENDPOINT_RE.search(line)
        or URL_RE.search(line)
        or _score_project_name(line) >= 1.0
    )


def _pick_type(lines: list[str]) -> tuple[str, str, ChannelTypeInfo | None]:
    for line in lines:
        if _is_technical_line(line):
            continue
        hint = resolve_type_hint(line)
        if hint:
            return hint.label, "rule:type_line", hint

    descriptive = [line for line in lines if not _is_technical_line(line)]
    if descriptive:
        joined = " ".join(descriptive)
        hint = resolve_type_hint(joined)
        if hint:
            return hint.label, "rule:type_joined", hint

    return "", "", None


def _pick_base_url(lines: list[str], type_info: ChannelTypeInfo | None) -> tuple[str, str]:
    if type_info and type_info.base_url:
        return type_info.base_url, "rule:type_default"

    for line in lines:
        if is_azure_host(line):
            return normalize_azure_base_url(line), "rule:azure_url_normalized"
        match = URL_RE.search(line)
        if match:
            return match.group(0).rstrip("/"), "rule:url"
    return "", ""


def _pick_api_version(lines: list[str]) -> tuple[str, str]:
    for line in lines:
        token = line.strip().split()[0] if line.strip() else ""
        if API_VERSION_RE.match(token):
            return token, "rule:api_version"
    return "", ""


def _build_result_from_lines(lines: list[str]) -> ExtractedFields:
    result = ExtractedFields()
    if not lines:
        result.warnings.append("未检测到有效输入行")
        return result

    name, name_src = _pick_project_name(lines)
    api_key, key_src = _pick_api_key(lines)
    azure_raw_url = find_azure_url(lines)
    explicit_type, explicit_type_src, explicit_type_info = _pick_type(lines)
    is_explicit_openai = bool(
        explicit_type_info and explicit_type_info.label == OPENAI_TYPE_LABEL
    )

    type_label = ""
    type_src = ""
    type_info: ChannelTypeInfo | None = None
    base_url = ""
    url_src = ""
    api_version = ""
    ver_src = ""
    upstream = ""
    upstream_src = ""

    # OpenAI / Azure：显式 OpenAI/openai → OpenAI；
    # 有 Azure / Azure URL，或未写 openai → 默认 Azure（Azure 语境）
    if is_explicit_openai:
        type_info = get_openai_type()
        type_label = type_info.label
        type_src = explicit_type_src or "rule:openai_explicit"
        upstream, upstream_src = _pick_upstream_model(lines, channel_name=name)
        base_url, url_src = _pick_base_url(lines, type_info)
        api_version, ver_src = _pick_api_version(lines)
    elif azure_raw_url or (
        explicit_type_info and explicit_type_info.label == AZURE_TYPE_LABEL
    ):
        if azure_raw_url:
            azure = _pick_azure_fields(lines, name)
            type_label, type_src = azure.get("type_label", ("", ""))
            type_info, _ = azure.get("type_info", (None, ""))
            base_url, url_src = azure.get("base_url", ("", ""))
            api_version, ver_src = azure.get("api_version", ("", ""))
            if azure.get("api_key", ("", ""))[0]:
                api_key, key_src = azure["api_key"]
            upstream, upstream_src = azure.get("upstream_model", ("", ""))
        else:
            type_info = get_azure_type()
            type_label = type_info.label
            type_src = explicit_type_src or "rule:azure_explicit"
            upstream, upstream_src = _pick_upstream_model(lines, channel_name=name)
            base_url, url_src = _pick_base_url(lines, type_info)
            api_version, ver_src = _pick_api_version(lines)
    elif is_custom_channel_block(lines):
        custom = pick_custom_fields(lines, name)
        type_label, type_src = custom.get("type_label", ("", ""))
        type_info, _ = custom.get("type_info", (None, ""))
        base_url, url_src = custom.get("base_url", ("", ""))
        if custom.get("api_key", ("", ""))[0]:
            api_key, key_src = custom["api_key"]
        upstream, upstream_src = custom.get("upstream_model", ("", ""))
    else:
        upstream, upstream_src = _pick_upstream_model(lines, channel_name=name)
        if upstream and _is_ep_model(upstream):
            type_info = get_volcano_type()
            type_label = type_info.label
            type_src = "rule:ep_inferred"
            base_url = type_info.base_url or ""
            url_src = "rule:ep_inferred_default"
        else:
            type_label, type_src, type_info = explicit_type, explicit_type_src, explicit_type_info
            if not type_label:
                type_label, type_src, type_info = _pick_type(lines)
            if not upstream:
                upstream, upstream_src = _pick_upstream_model(lines, channel_name=name)
            base_url, url_src = _pick_base_url(lines, type_info)
            api_version, ver_src = _pick_api_version(lines)
    group = derive_group_from_name(name) if name else ""
    # 名称可含中文备注；模型列固定为前面的 ASCII 段
    model = derive_model_from_name(name) if name else ""
    model_src = ""
    if model:
        model_src = "rule:same_as_name" if model == name else "rule:name_ascii_core"

    result.name = name
    result.group = group
    result.type_label = type_label
    result.model = model
    result.upstream_model = upstream
    result.base_url = base_url
    result.api_version = api_version
    result.api_key = api_key

    for key, src in (
        ("name", name_src),
        ("group", "rule:derived" if group else ""),
        ("type_label", type_src),
        ("model", model_src),
        ("upstream_model", upstream_src),
        ("base_url", url_src),
        ("api_version", ver_src),
        ("api_key", key_src),
    ):
        if src:
            result.sources[key] = src

    filled = sum(
        1 for k in ("name", "type_label", "upstream_model", "api_key") if getattr(result, k)
    )
    result.confidence = filled / 4.0

    if type_info and type_info.api_version_required and not api_version:
        result.warnings.append(f"类型「{type_label}」通常需要填写 API 版本")

    if type_info and not type_info.base_url and not base_url:
        result.warnings.append(f"类型「{type_label}」需用户提供 Base URL")

    return result


def extract_block_by_rules(lines: list[str]) -> ExtractedFields:
    if len(lines) == 1:
        from .channel_line_parser import (
            expand_volcano_space_line,
            looks_like_channel_line,
            parse_to_fields,
        )

        line = lines[0].strip()
        if looks_like_channel_line(line):
            fields = parse_to_fields(line)
            if fields:
                return fields
        expanded = expand_volcano_space_line(line)
        if expanded:
            return _build_result_from_lines(expanded)
    return _build_result_from_lines(lines)


def extract_blocks_by_rules(raw_text: str) -> list[ExtractedFields]:
    blocks = split_into_blocks(raw_text)
    if not blocks:
        lines = _split_lines(raw_text)
        if lines:
            return [_build_result_from_lines(lines)]
        return [ExtractedFields(warnings=["未检测到有效输入行"])]

    return [extract_block_by_rules(block) for block in blocks]


def extract_by_rules(raw_text: str) -> ExtractedFields:
    """单条提取（多条时返回首条，兼容旧接口）。"""
    results = extract_blocks_by_rules(raw_text)
    return results[0] if results else ExtractedFields(warnings=["未检测到有效输入行"])
