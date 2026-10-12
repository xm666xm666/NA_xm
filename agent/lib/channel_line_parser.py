"""解析已格式化的 NA 渠道行（空格 / Tab 分隔，与批量配置格式一致）。

支持两种形态：
1. 完整行：名称 [分组] 类型 模型 模型->上游 base_url [API版本] 秘钥
2. 紧凑行（无重定向）：名称 [分组] 类型 模型 base_url [API版本] 秘钥
   此时上游模型默认等于模型。
另支持火山「空格单行」杂乱输入（无 URL）：名称 [类型] ep-… ark-…
与换行多行块等效，在分块阶段展开为多行后再走规则提取。
"""

from __future__ import annotations

import re

from .group_deriver import derive_group_from_name
from .patterns import API_VERSION_RE, ARK_KEY_RE, EP_MODEL_RE, PROJECT_NAME_RE, URL_RE
from .type_registry import all_type_labels

REDIRECT_TOKEN_RE = re.compile(r"\S+->\S+")
AZURE_KEY_TOKEN_RE = re.compile(r"^[A-Za-z0-9]{40,}$")


def normalize_channel_line(text: str) -> str:
    """将 Tab、多空格规范为单空格，便于解析。"""
    return re.sub(r"\s+", " ", (text or "").strip())


def expand_volcano_space_line(text: str) -> list[str] | None:
    """将火山空格/Tab 单行展开为多行字段，与换行块等效。

    识别形态（无 URL）：
      名称 [类型…] ep-xxxxxxxx ark-xxxxxxxx
    类型中可含顿号（如「字节火山方舟、豆包通用」），不会按顿号拆开。
    """
    raw = (text or "").strip()
    if not raw or "\n" in raw or "\r" in raw:
        return None
    if URL_RE.search(raw) or REDIRECT_TOKEN_RE.search(raw):
        return None

    tokens = normalize_channel_line(raw).split(" ")
    if len(tokens) < 3:
        return None

    ep_indices = [i for i, token in enumerate(tokens) if EP_MODEL_RE.fullmatch(token)]
    ark_indices = [i for i, token in enumerate(tokens) if ARK_KEY_RE.fullmatch(token)]
    if len(ep_indices) != 1 or not ark_indices:
        return None

    name = tokens[0]
    if not PROJECT_NAME_RE.match(name):
        return None

    ep_i = ep_indices[0]
    ark_i = next((i for i in ark_indices if i != ep_i), None)
    if ark_i is None:
        return None

    # 名称 / ep / ark 之外的中间字段拼成类型行（保留顿号）
    middle = [tokens[i] for i in range(len(tokens)) if i not in {0, ep_i, ark_i}]
    lines = [name]
    if middle:
        lines.append(" ".join(middle))
    lines.append(tokens[ep_i])
    lines.append(tokens[ark_i])
    return lines


def looks_like_volcano_space_line(text: str) -> bool:
    return expand_volcano_space_line(text) is not None


def _secret_after_url(line: str) -> str:
    url_match = URL_RE.search(line)
    if not url_match:
        return ""
    tail = line[url_match.end() :].strip().split()
    if not tail:
        return ""
    if len(tail) >= 2 and API_VERSION_RE.match(tail[0]):
        return tail[1]
    return tail[-1]


def _is_secret_token(secret: str) -> bool:
    return bool(
        secret.startswith("sk-")
        or secret.startswith("ark-")
        or AZURE_KEY_TOKEN_RE.match(secret)
    )


def looks_like_redirect_channel_line(text: str) -> bool:
    line = normalize_channel_line(text)
    if not line or not REDIRECT_TOKEN_RE.search(line) or not URL_RE.search(line):
        return False
    return _is_secret_token(_secret_after_url(line))


def looks_like_compact_channel_line(text: str) -> bool:
    """无 模型->上游 的紧凑渠道行：名称 [分组] 类型 模型 URL [版本] 秘钥。"""
    line = normalize_channel_line(text)
    if not line or REDIRECT_TOKEN_RE.search(line):
        return False
    url_match = URL_RE.search(line)
    if not url_match or not _is_secret_token(_secret_after_url(line)):
        return False
    front_tokens = line[: url_match.start()].strip().split()
    if len(front_tokens) < 2:
        return False
    return _try_parse_front_compact(front_tokens) is not None


def looks_like_channel_line(text: str) -> bool:
    return looks_like_redirect_channel_line(text) or looks_like_compact_channel_line(text)


def _type_labels_for_parse() -> list[str]:
    return sorted(all_type_labels(), key=lambda label: len(label.split()), reverse=True)


def _match_type(tokens: list[str], start: int) -> tuple[str, int] | None:
    for label in _type_labels_for_parse():
        words = label.split()
        end = start + len(words)
        if end <= len(tokens) and tokens[start:end] == words:
            return label, len(words)
    return None


def _parse_front_standard(front_tokens: list[str]) -> tuple[str, str, str, str]:
    if len(front_tokens) < 4:
        raise ValueError("数据列不足")
    name = front_tokens[0]
    group = front_tokens[1]
    model = front_tokens[-1]
    type_tokens = front_tokens[2:-1]
    matched = _match_type(type_tokens, 0)
    if not matched or matched[1] != len(type_tokens):
        raise ValueError("无法识别渠道类型")
    return name, group, matched[0], model


def _parse_name_type_model_with_redirect(
    front_tokens: list[str], redirect: str
) -> tuple[str, str, str, str]:
    """名称 类型 模型 模型->上游（第三列为 Azure 部署名，分组由名称推导）。"""
    if len(front_tokens) < 3:
        raise ValueError("数据列不足")
    name = front_tokens[0]
    matched = _match_type(front_tokens, 1)
    if not matched:
        raise ValueError("无法识别渠道类型")
    type_label, used = matched
    idx = 1 + used
    if len(front_tokens) != idx + 1:
        raise ValueError("缺少模型")
    model = front_tokens[idx]
    source_model, _ = _parse_redirect(redirect)
    if source_model != model:
        raise ValueError("模型与模型重定向左侧不一致")
    return name, derive_group_from_name(name), type_label, model


def _try_parse_front_compact(front_tokens: list[str]) -> tuple[str, str, str, str] | None:
    """紧凑前置：名称 [分组] 类型 [上游模型]。

    返回 (name, group, type_label, upstream)。
    对外「模型」列固定为渠道名，与批量格式 名称->上游 一致。
    """
    if len(front_tokens) < 2:
        return None

    # 名称 类型 [上游]
    matched = _match_type(front_tokens, 1)
    if matched:
        type_label, used = matched
        idx = 1 + used
        if len(front_tokens) == idx + 1:
            name = front_tokens[0]
            upstream = front_tokens[idx]
            return name, derive_group_from_name(name), type_label, upstream
        if len(front_tokens) == idx:
            name = front_tokens[0]
            return name, derive_group_from_name(name), type_label, name

    # 名称 分组 类型 [上游]
    if len(front_tokens) >= 3:
        matched = _match_type(front_tokens, 2)
        if matched:
            type_label, used = matched
            idx = 2 + used
            if len(front_tokens) == idx + 1:
                name = front_tokens[0]
                group = front_tokens[1]
                upstream = front_tokens[idx]
                derived = derive_group_from_name(name)
                return name, derived or group, type_label, upstream
            if len(front_tokens) == idx:
                name = front_tokens[0]
                group = front_tokens[1]
                derived = derive_group_from_name(name)
                return name, derived or group, type_label, name

    return None


def _parse_front_compact(front_tokens: list[str]) -> tuple[str, str, str, str]:
    """紧凑前置：名称 [分组] 类型 [上游模型]。"""
    parsed = _try_parse_front_compact(front_tokens)
    if not parsed:
        raise ValueError("无法解析紧凑前置字段")
    return parsed


def _parse_front_section(front_tokens: list[str], redirect: str = "") -> tuple[str, str, str, str]:
    parsers: list = []
    if redirect and _match_type(front_tokens, 1):
        parsers.append(lambda tokens: _parse_name_type_model_with_redirect(tokens, redirect))
    parsers.append(_parse_front_standard)

    errors: list[ValueError] = []
    for parser in parsers:
        try:
            name, group, channel_type, model = parser(front_tokens)
            derived_group = derive_group_from_name(name)
            if derived_group:
                group = derived_group
            return name, group, channel_type, model
        except ValueError as exc:
            errors.append(exc)
    raise errors[0] if errors else ValueError("无法解析前置字段")


def _parse_redirect(value: str) -> tuple[str, str]:
    match = re.match(r"^\s*(.+?)\s*->\s*(.+?)\s*$", value)
    if not match:
        raise ValueError(f"模型重定向格式错误: {value}")
    source = match.group(1).strip()
    target = match.group(2).strip()
    if not source or not target:
        raise ValueError(f"模型重定向格式错误: {value}")
    return source, target


def _requires_api_version(channel_type: str) -> bool:
    return channel_type.strip().lower() in {"azure openai", "azure", "azure_openai"}


def _parse_tail_section(tail: str, *, require_api_version: bool) -> tuple[str, str, str]:
    url_match = URL_RE.search(tail)
    if not url_match:
        raise ValueError("缺少 base_url")

    base_url = url_match.group(0).rstrip("/")
    rest = tail[url_match.end() :].strip().split()
    if not rest:
        raise ValueError("缺少秘钥")

    api_version = ""
    secret = ""
    if len(rest) >= 2 and API_VERSION_RE.match(rest[0]):
        api_version = rest[0]
        secret = rest[1]
    else:
        secret = rest[-1]

    if require_api_version and not api_version:
        raise ValueError("Azure OpenAI 缺少 API 版本")

    return base_url, api_version, secret


def _parse_compact_channel_line(line: str) -> dict[str, str]:
    url_match = URL_RE.search(line)
    if not url_match:
        raise ValueError("缺少 base_url")

    front_tokens = line[: url_match.start()].strip().split()
    name, group, channel_type, upstream = _parse_front_compact(front_tokens)
    # 与批量样例一致：模型列 = 渠道名，重定向 = 渠道名->上游
    model = name
    redirect = f"{model}->{upstream}"
    base_url, api_version, secret = _parse_tail_section(
        line[url_match.start() :].strip(),
        require_api_version=_requires_api_version(channel_type),
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


def parse_channel_line(text: str) -> dict[str, str]:
    line = normalize_channel_line(text)
    redirect_match = REDIRECT_TOKEN_RE.search(line)
    if not redirect_match:
        return _parse_compact_channel_line(line)

    redirect = redirect_match.group(0)
    front_tokens = line[: redirect_match.start()].strip().split()
    name, group, channel_type, model = _parse_front_section(front_tokens, redirect)

    source_model, target_model = _parse_redirect(redirect)
    if source_model != model:
        raise ValueError("模型与模型重定向左侧不一致")

    base_url, api_version, secret = _parse_tail_section(
        line[redirect_match.end() :].strip(),
        require_api_version=_requires_api_version(channel_type),
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


def parse_to_fields(text: str):
    from .rule_extractor import ExtractedFields

    try:
        row = parse_channel_line(text)
    except ValueError:
        return None

    _, target_model = _parse_redirect(row["模型重定向"])
    fields = ExtractedFields(
        name=row["名称"],
        group=row["分组"],
        type_label=row["类型"],
        model=row["模型"],
        upstream_model=target_model,
        base_url=row["base_url"],
        api_version=row["默认API版本"],
        api_key=row["秘钥"],
        confidence=1.0,
    )
    for key in ("name", "group", "type_label", "model", "upstream_model", "base_url", "api_version", "api_key"):
        fields.sources[key] = "prefilled"
    return fields


def split_prefilled_blocks(raw_text: str) -> list[list[str]]:
    """从文本中识别已格式化的渠道行块。"""
    from .text_splitter import normalize_raw_text, split_input_lines, split_input_paragraphs

    blocks: list[list[str]] = []
    normalized = normalize_raw_text(raw_text).strip()
    if not normalized:
        return blocks

    paragraphs = split_input_paragraphs(normalized) or [normalized]
    for paragraph in paragraphs:
        coalesced = _coalesce_tab_separated_row(paragraph)
        if looks_like_channel_line(coalesced):
            blocks.append([normalize_channel_line(coalesced)])
            continue

        for raw in split_input_lines(coalesced):
            line = normalize_channel_line(raw)
            if looks_like_channel_line(line):
                blocks.append([line])

    return blocks


def _coalesce_tab_separated_row(paragraph: str) -> str:
    stripped = paragraph.strip()
    if "\t" not in stripped:
        return stripped
    joined = normalize_channel_line(stripped.replace("\t", " "))
    if looks_like_channel_line(joined):
        return joined
    return stripped
