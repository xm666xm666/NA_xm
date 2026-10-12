"""令牌智能提取：将杂乱多行输入拼成批量令牌行。

常见输入：
1) 令牌名-人名 / 分组 / 模型1，模型2
2) 令牌名 / 人名 / 分组 / 模型1，模型2
3) 令牌名-人名 + 多行渠道批量行（自动识别分组与模型）

输出（与②令牌管理一致）：
  令牌名-人名\\t分组\\t模型1,模型2
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Any

from .channel_line_parser import parse_channel_line
from .group_deriver import derive_group_from_name

_PERSON_RE = re.compile(r"^[\u4e00-\u9fff·•]{2,12}$")
_LABEL_RE = re.compile(
    r"^(?:令牌名|令牌名称|名称|人名|姓名|用户|用户名|分组|令牌分组|模型|模型限制|模型列表)\s*[：:]\s*",
    re.IGNORECASE,
)
_MODEL_SEP_RE = re.compile(r"[,，、;；]")
_ENV_GROUP_RE = re.compile(
    r"(?:^|-)(?:test|uat|prd|prod|stg|dev)(?:-|$)",
    re.IGNORECASE,
)
_PERSON_SUFFIX_RE = re.compile(r"-([\u4e00-\u9fff·•]{2,12})$")


@dataclass
class TokenExtractItem:
    index: int
    success: bool
    name: str = ""
    group: str = ""
    models: str = ""
    token_line: str = ""
    message: str = ""


@dataclass
class TokenExtractResult:
    success: bool
    message: str
    count: int = 0
    token_lines: str = ""
    items: list[TokenExtractItem] = field(default_factory=list)
    mode: str = "token_rules"
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "message": self.message,
            "count": self.count,
            "token_lines": self.token_lines,
            "token_line": self.token_lines.splitlines()[0] if self.token_lines else "",
            # 与渠道提取字段对齐，便于同一套前端渲染
            "channel_lines": self.token_lines,
            "channel_line": self.token_lines.splitlines()[0] if self.token_lines else "",
            "mode": self.mode,
            "warnings": self.warnings,
            "items": [
                {
                    "index": it.index,
                    "success": it.success,
                    "name": it.name,
                    "group": it.group,
                    "models": it.models,
                    "token_line": it.token_line,
                    "channel_line": it.token_line,
                    "message": it.message,
                    "fields": {
                        "名称": it.name,
                        "分组": it.group,
                        "模型": it.models,
                    }
                    if it.success
                    else {},
                }
                for it in self.items
            ],
        }


def _strip_label(line: str) -> str:
    return _LABEL_RE.sub("", (line or "").strip())


def _looks_like_person(text: str) -> bool:
    return bool(_PERSON_RE.fullmatch((text or "").strip()))


def _looks_like_models_line(text: str, *, allow_single: bool = False) -> bool:
    """识别模型列表行。

    含中英文逗号/顿号的行优先；单模型仅在 allow_single=True（通常为块末行）时接受，
    避免把分组名（如 demo-b-test）误当成模型。
    """
    s = (text or "").strip()
    if not s or _looks_like_person(s):
        return False
    if _MODEL_SEP_RE.search(s):
        return True
    if not allow_single:
        return False
    # 单模型：字母数字/点/连字符（含无连字符短名如 m3、gpt4）
    return bool(re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_.+-]*", s))


def _looks_like_group(text: str) -> bool:
    s = (text or "").strip()
    if not s or _looks_like_person(s) or _MODEL_SEP_RE.search(s):
        return False
    if _ENV_GROUP_RE.search(s):
        return True
    # 短分组名 / 项目名
    return bool(re.fullmatch(r"[a-zA-Z0-9][\w.-]{1,80}", s))


def normalize_model_list(raw: str) -> list[str]:
    text = (raw or "").strip()
    if not text:
        return []
    normalized = _MODEL_SEP_RE.sub(",", text)
    return [part.strip() for part in normalized.split(",") if part.strip()]


def join_token_name(base: str, person: str = "") -> str:
    """拼接令牌名与人名，避免重复追加。"""
    base = (base or "").strip()
    person = (person or "").strip()
    if not base:
        return person
    if not person:
        return base
    if base == person:
        return base
    if base.endswith(f"-{person}") or base.endswith(person):
        return base
    return f"{base}-{person}"


def format_token_line(name: str, group: str, models: list[str] | str) -> str:
    if isinstance(models, str):
        model_list = normalize_model_list(models)
    else:
        model_list = [str(m).strip() for m in models if str(m).strip()]
    if not name or not group or not model_list:
        raise ValueError("令牌名、分组、模型均不能为空")
    return f"{name}\t{group}\t{','.join(model_list)}"


def _split_paragraphs(raw_text: str) -> list[list[str]]:
    text = (raw_text or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    if not text:
        return []
    blocks: list[list[str]] = []
    current: list[str] = []
    for raw in text.split("\n"):
        line = _strip_label(raw)
        if not line or line.startswith("#"):
            if current:
                blocks.append(current)
                current = []
            continue
        current.append(line)
    if current:
        blocks.append(current)
    return blocks


def _parse_standard_line(line: str) -> tuple[str, str, list[str]] | None:
    """已是「名称 分组 模型」单行时直接解析。"""
    text = (line or "").strip()
    if not text:
        return None
    # 完整渠道行不是令牌标准行
    if _try_parse_channel_line(text) is not None:
        return None
    if "\t" in text:
        parts = [p.strip() for p in text.split("\t") if p.strip()]
        if len(parts) >= 3:
            models = normalize_model_list("、".join(parts[2:]))
            if models:
                return parts[0], parts[1], models
    ws = re.split(r"\s+", text, maxsplit=2)
    if len(ws) >= 3 and normalize_model_list(ws[2]):
        return ws[0], ws[1], normalize_model_list(ws[2])
    return None


def _try_parse_channel_line(line: str) -> dict[str, str] | None:
    text = (line or "").strip()
    if not text or "://" not in text:
        return None
    try:
        return parse_channel_line(text)
    except ValueError:
        return None


def _token_name_from_parts(name_parts: list[str]) -> str:
    if not name_parts:
        return ""
    if len(name_parts) == 1:
        token_name = name_parts[0]
    elif len(name_parts) >= 2 and _looks_like_person(name_parts[-1]):
        token_name = join_token_name("-".join(name_parts[:-1]), name_parts[-1])
    elif len(name_parts) == 2:
        token_name = join_token_name(name_parts[0], name_parts[1])
    else:
        token_name = "-".join(name_parts)
    return token_name.strip("-").strip()


def _person_suffix(text: str) -> str:
    """若以 -人名 结尾则返回人名，否则空串。"""
    match = _PERSON_SUFFIX_RE.search((text or "").strip())
    if not match:
        return ""
    person = match.group(1)
    return person if _looks_like_person(person) else ""


def _token_name_from_channel_rows(channel_rows: list[dict[str, str]]) -> str:
    """渠道「名称」已写成 模型-人名 时，直接作为令牌名。"""
    for row in channel_rows:
        name = str(row.get("名称") or "").strip()
        model = str(row.get("模型") or "").strip()
        person = _person_suffix(name)
        if not person:
            continue
        # 名称 = 模型-人名，或名称本身以 -人名 结尾
        if not model or name == join_token_name(model, person) or name.endswith(f"-{person}"):
            return name
    return ""


def _extract_from_channel_bundle(
    other_lines: list[str],
    channel_rows: list[dict[str, str]],
) -> tuple[str, str, list[str]]:
    """令牌名(+可选分组) + 渠道批量行 → 分组与模型列表。"""
    models: list[str] = []
    seen: set[str] = set()
    groups: list[str] = []
    for row in channel_rows:
        # 模型列优先；若名称误带 -人名，仍用无中文后缀的模型列
        model = str(row.get("模型") or "").strip()
        if not model:
            name = str(row.get("名称") or "").strip()
            person = _person_suffix(name)
            model = name[: -(len(person) + 1)] if person else name
        if model and model not in seen:
            seen.add(model)
            models.append(model)
        group = str(row.get("分组") or "").strip()
        if group:
            groups.append(group)
    if not models:
        raise ValueError("渠道行中未识别到模型")

    group_from_channels = Counter(groups).most_common(1)[0][0] if groups else ""

    name_parts: list[str] = []
    explicit_group = ""
    for line in other_lines:
        # 显式分组行：与渠道分组一致，或整行本身就是环境分组名
        if group_from_channels and line == group_from_channels:
            explicit_group = line
            continue
        if (
            _looks_like_group(line)
            and not _looks_like_person(line)
            and derive_group_from_name(line) == line
        ):
            explicit_group = line
            continue
        name_parts.append(line)

    token_name = _token_name_from_parts(name_parts)

    # 仅人名（可多行但全是人名）：拼到首个渠道模型上
    # 例：费仕忆 + finance-prod-doubao-seed-2.0 渠道行
    #   → finance-prod-doubao-seed-2.0-费仕忆
    if name_parts and all(_looks_like_person(p) for p in name_parts):
        token_name = join_token_name(models[0], name_parts[-1])
    elif token_name and _looks_like_person(token_name):
        token_name = join_token_name(models[0], token_name)

    # 无独立令牌名行：渠道名称字段已含 -人名
    # 例：finance-prod-doubao-seed-2.0-费仕忆 … ->ep-… https://…
    if not token_name:
        token_name = _token_name_from_channel_rows(channel_rows)

    if not token_name:
        raise ValueError(
            "请提供令牌名或人名：可在渠道行前单独写「模型名 / 人名」，"
            "或仅写人名（将拼到首个渠道模型后），"
            "或把渠道名称写成「模型-人名」"
        )

    group = explicit_group or group_from_channels or derive_group_from_name(token_name)
    if not group:
        raise ValueError("未识别到分组（请确认渠道行含分组，或令牌名含 -uat/-test/-prod）")
    return token_name, group, models


def _merge_channel_continuation_blocks(blocks: list[list[str]]) -> list[list[str]]:
    """空行隔开的纯渠道行块并入上一块（同属一条令牌的模型来源）。"""
    if not blocks:
        return blocks
    merged: list[list[str]] = [list(blocks[0])]
    for block in blocks[1:]:
        if block and all(_try_parse_channel_line(line) is not None for line in block):
            merged[-1].extend(block)
        else:
            merged.append(list(block))
    return merged


def extract_token_block(lines: list[str]) -> tuple[str, str, list[str]]:
    """从多行块提取 (令牌名, 分组, 模型列表)。"""
    cleaned = [_strip_label(x) for x in lines if _strip_label(x)]
    if not cleaned:
        raise ValueError("空块")

    channel_rows: list[dict[str, str]] = []
    other_lines: list[str] = []
    for line in cleaned:
        row = _try_parse_channel_line(line)
        if row is not None:
            channel_rows.append(row)
        else:
            other_lines.append(line)

    if channel_rows:
        return _extract_from_channel_bundle(other_lines, channel_rows)

    if len(cleaned) == 1:
        parsed = _parse_standard_line(cleaned[0])
        if parsed:
            return parsed
        raise ValueError("单行格式需为：令牌名 分组 模型1,模型2")

    # 优先：带分隔符的模型行；否则默认最后一行为模型
    models_idx = None
    for i in range(len(cleaned) - 1, -1, -1):
        if _looks_like_models_line(cleaned[i], allow_single=False):
            models_idx = i
            break
    if models_idx is None:
        last = len(cleaned) - 1
        if _looks_like_models_line(cleaned[last], allow_single=True):
            models_idx = last
        else:
            models_idx = last
    models = normalize_model_list(cleaned[models_idx])
    if not models:
        raise ValueError("未识别到模型列表")

    before = cleaned[:models_idx]
    if len(before) < 2:
        raise ValueError("至少需要：令牌名、分组、模型列表")

    # 优先：倒数第二行是分组；若末段是人名，则从 name_parts 里找分组
    group = before[-1]
    name_parts = before[:-1]
    if _looks_like_person(group) and len(before) >= 3:
        # 异常顺序：… / 分组 / 人名 / 模型 → 取倒数第二为分组
        for i in range(len(before) - 2, -1, -1):
            if _looks_like_group(before[i]) and not _looks_like_person(before[i]):
                group = before[i]
                name_parts = [x for j, x in enumerate(before) if j != i]
                break
    elif not _looks_like_group(group) and len(before) >= 3:
        # 分组可能夹在中间：令牌名 / 人名 / 分组
        for i in range(len(before) - 1, 0, -1):
            if _looks_like_group(before[i]) and not _looks_like_person(before[i]):
                group = before[i]
                name_parts = before[:i] + before[i + 1 :]
                break

    if not group:
        raise ValueError("未识别到分组")

    token_name = _token_name_from_parts(name_parts)
    if not token_name:
        raise ValueError("令牌名不能为空")
    return token_name, group.strip(), models


def extract_tokens(raw_text: str) -> TokenExtractResult:
    blocks = _merge_channel_continuation_blocks(_split_paragraphs(raw_text))
    if not blocks:
        return TokenExtractResult(success=False, message="请输入令牌信息")

    items: list[TokenExtractItem] = []
    lines_out: list[str] = []
    warnings: list[str] = []

    for index, block in enumerate(blocks, start=1):
        try:
            name, group, models = extract_token_block(block)
            line = format_token_line(name, group, models)
            items.append(
                TokenExtractItem(
                    index=index,
                    success=True,
                    name=name,
                    group=group,
                    models=",".join(models),
                    token_line=line,
                    message=f"#{index} 提取成功",
                )
            )
            lines_out.append(line)
        except ValueError as exc:
            items.append(
                TokenExtractItem(
                    index=index,
                    success=False,
                    message=f"#{index} {exc}",
                )
            )
            warnings.append(f"#{index} {exc}")

    ok_count = sum(1 for it in items if it.success)
    if ok_count == 0:
        return TokenExtractResult(
            success=False,
            message=warnings[0] if warnings else "未能提取令牌",
            count=0,
            items=items,
            warnings=warnings,
        )
    if ok_count < len(items):
        msg = f"部分成功：{ok_count}/{len(items)} 条"
    else:
        msg = f"提取成功，共 {ok_count} 条令牌（已拼接为批量格式）"
    return TokenExtractResult(
        success=True,
        message=msg,
        count=ok_count,
        token_lines="\n".join(lines_out),
        items=items,
        warnings=warnings,
    )
