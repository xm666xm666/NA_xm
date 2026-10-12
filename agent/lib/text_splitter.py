"""将杂乱输入拆分为逻辑行，支持换行、Tab、逗号与顿号等分隔符。"""

from __future__ import annotations

import re

# 千分位逗号：15,000、1,500,000、2,006,000
_NUMERIC_COMMA_RE = re.compile(r"\d{1,3}(?:,\d{3})+")
# 字段分隔符：Tab、换行、顿号、中英文逗号（千分位逗号会先被占位保护）
_FIELD_DELIMITER_RE = re.compile(r"[\t\r\n、,，]+")
# 空行分段：多条批量记录之间仍以空行分隔
_PARAGRAPH_SPLIT_RE = re.compile(r"\n(?:[ \t]*\n)+")
_PLACEHOLDER = "\x00"
_TYPE_PLACEHOLDER_FMT = "\x01TYPE{idx}\x01"


def _protect_numeric_commas(text: str) -> str:
    return _NUMERIC_COMMA_RE.sub(
        lambda match: match.group(0).replace(",", _PLACEHOLDER),
        text,
    )


def _restore_numeric_commas(text: str) -> str:
    return text.replace(_PLACEHOLDER, ",")


def _type_labels_with_delimiters() -> list[str]:
    """含顿号/逗号的类型标准名，拆行前需保护以免被误拆。"""
    try:
        from .type_registry import all_type_labels
    except Exception:
        return []
    labels = []
    for label in all_type_labels():
        if any(ch in label for ch in ("、", ",", "，")):
            labels.append(label)
    return sorted(labels, key=len, reverse=True)


def _protect_type_labels(text: str) -> tuple[str, dict[str, str]]:
    mapping: dict[str, str] = {}
    protected = text
    for idx, label in enumerate(_type_labels_with_delimiters()):
        if label not in protected:
            continue
        token = _TYPE_PLACEHOLDER_FMT.format(idx=idx)
        mapping[token] = label
        protected = protected.replace(label, token)
    return protected, mapping


def _restore_type_labels(text: str, mapping: dict[str, str]) -> str:
    restored = text
    for token, label in mapping.items():
        restored = restored.replace(token, label)
    return restored


def normalize_raw_text(raw_text: str) -> str:
    """统一换行符，便于后续分段与拆行。"""
    return (raw_text or "").replace("\r\n", "\n").replace("\r", "\n")


def split_input_lines(text: str) -> list[str]:
    """把段落内文本拆成逻辑行。

    支持的分隔符：换行、Tab、英文逗号、中文逗号、顿号。
    数字千分位中的逗号（如 15,000）不会被误拆。
    标准类型名中的顿号/逗号（如「字节火山方舟、豆包通用」）不会被误拆。
    """
    normalized = normalize_raw_text(text).strip()
    if not normalized:
        return []

    protected, type_map = _protect_type_labels(normalized)
    protected = _protect_numeric_commas(protected)
    lines: list[str] = []
    for segment in _FIELD_DELIMITER_RE.split(protected):
        line = _restore_numeric_commas(segment.strip())
        line = _restore_type_labels(line, type_map)
        if line:
            lines.append(line)
    return lines


def split_input_paragraphs(raw_text: str) -> list[str]:
    """按空行拆成多个段落，用于多条批量提取。"""
    normalized = normalize_raw_text(raw_text).strip()
    if not normalized:
        return []
    parts = [part.strip() for part in _PARAGRAPH_SPLIT_RE.split(normalized)]
    return [part for part in parts if part]
