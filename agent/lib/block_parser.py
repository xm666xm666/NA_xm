"""将杂乱输入拆分为多条渠道记录块。"""

from __future__ import annotations

from .patterns import (
    ARK_KEY_RE,
    AZURE_KEY_RE,
    EP_MODEL_RE,
    MODEL_MAPPING_RE,
    NOISE_LINE_RE,
    PROJECT_NAME_RE,
    SK_KEY_RE,
    URL_RE,
    UUID_RE,
    VERSION_TAG_RE,
)
from .azure_utils import is_azure_host
from .channel_line_parser import (
    expand_volcano_space_line,
    looks_like_channel_line,
    split_prefilled_blocks,
)
from .text_splitter import normalize_raw_text, split_input_lines, split_input_paragraphs


def _is_noise_line(line: str) -> bool:
    return bool(NOISE_LINE_RE.match(line) or VERSION_TAG_RE.match(line))


def _normalize_line(raw: str) -> str:
    return raw.strip()


def _score_project_name(line: str) -> float:
    if not PROJECT_NAME_RE.match(line):
        return 0.0
    return 1.0 + line.count("-") * 0.1


def _line_has_azure_key(text: str) -> bool:
    for token in text.split():
        if AZURE_KEY_RE.match(token):
            return True
    return bool(AZURE_KEY_RE.match(text.strip()))


def _block_has_mapping(block: list[str]) -> bool:
    return any(MODEL_MAPPING_RE.match(line.strip()) for line in block)


def _block_has_anchor(block: list[str]) -> bool:
    """有效渠道块须含 ep- 模型，或 Azure URL+密钥，或项目名+密钥，或完整渠道行。

    更新原配置场景：项目名 +「模型->上游」映射即可，不要求密钥。
    """
    if not block:
        return False
    joined = "\n".join(block)
    if len(block) == 1 and (
        looks_like_channel_line(block[0]) or expand_volcano_space_line(block[0])
    ):
        return True
    if EP_MODEL_RE.search(joined):
        return True
    has_key = bool(
        ARK_KEY_RE.search(joined)
        or UUID_RE.search(joined)
        or SK_KEY_RE.search(joined)
    )
    has_azure_key = any(_line_has_azure_key(line) for line in block)
    if is_azure_host(joined) and (has_key or has_azure_key):
        return True
    if SK_KEY_RE.search(joined) and URL_RE.search(joined):
        return True
    has_name = any(_score_project_name(line) >= 1.0 for line in block)
    if has_name and _block_has_mapping(block):
        return True
    return has_key and has_name


def _is_title_only_block(block: list[str]) -> bool:
    """仅含渠道标题、无密钥与 ep-/Azure 数据的前置块。"""
    if not block:
        return False
    joined = "\n".join(block)
    if EP_MODEL_RE.search(joined) or ARK_KEY_RE.search(joined) or UUID_RE.search(joined):
        return False
    if is_azure_host(joined):
        return False
    if any(AZURE_KEY_RE.match(line.strip()) for line in block):
        return False
    if SK_KEY_RE.search(joined) or URL_RE.search(joined):
        return False
    if _block_has_mapping(block):
        return False
    return any(_score_project_name(line) >= 1.0 for line in block)


def _merge_title_blocks(blocks: list[list[str]]) -> list[list[str]]:
    """将版本标注行前的标题行并入后续数据块。"""
    merged: list[list[str]] = []
    pending_titles: list[str] = []

    for block in blocks:
        if _is_title_only_block(block):
            pending_titles.extend(block)
            continue
        if pending_titles:
            merged.append(pending_titles + block)
            pending_titles = []
        else:
            merged.append(block)

    return merged


def _collect_block_lines(paragraph: str) -> list[list[str]]:
    """从单个段落收集渠道块（空行已在段落级处理）。

    物理行若为火山空格单行（名称 [类型] ep- ark-），先按空格展开为多行，
    避免类型名中的顿号被 split_input_lines 误拆。
    """
    blocks: list[list[str]] = []
    current: list[str] = []

    def flush() -> None:
        nonlocal current
        if current:
            blocks.append(current)
            current = []

    for physical in normalize_raw_text(paragraph).split("\n"):
        physical = physical.strip()
        if not physical or physical.startswith("#"):
            flush()
            continue

        expanded = expand_volcano_space_line(physical)
        if expanded:
            flush()
            blocks.append(expanded)
            continue

        for raw in split_input_lines(physical):
            line = _normalize_line(raw)
            if not line or line.startswith("#"):
                flush()
                continue
            if _is_noise_line(line):
                if VERSION_TAG_RE.match(line) and current:
                    flush()
                continue
            current.append(line)

    flush()
    return blocks


def split_into_blocks(raw_text: str) -> list[list[str]]:
    """按空行、版本标注行、多条 ep- 模型拆分为独立渠道块。"""
    paragraphs = split_input_paragraphs(raw_text)
    if not paragraphs:
        paragraphs = [raw_text] if raw_text.strip() else []

    blocks: list[list[str]] = []
    for paragraph in paragraphs:
        blocks.extend(_collect_block_lines(paragraph))

    expanded: list[list[str]] = []
    for block in blocks:
        ep_indices = [i for i, line in enumerate(block) if EP_MODEL_RE.search(line)]
        if len(ep_indices) <= 1:
            expanded.append(block)
            continue

        prefix = block[: ep_indices[0]]
        for j, ep_idx in enumerate(ep_indices):
            end = ep_indices[j + 1] if j + 1 < len(ep_indices) else len(block)
            expanded.append(prefix + block[ep_idx:end])

    anchored = _merge_title_blocks(expanded)
    result = [block for block in anchored if _block_has_anchor(block)]
    if result:
        return result
    return split_prefilled_blocks(raw_text)
