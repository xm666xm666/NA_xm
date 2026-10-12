"""令牌批量导入重复校验（本站内：令牌名唯一）。"""

from __future__ import annotations

from typing import Any


def normalize_model_limits(models: list[str] | str) -> str:
    if isinstance(models, str):
        parts = [part.strip() for part in models.split(",") if part.strip()]
    else:
        parts = [str(part).strip() for part in models if str(part).strip()]
    return ",".join(sorted(set(parts)))


def token_name_group(name: str, group: str) -> tuple[str, str]:
    """删除匹配仍按名称+分组。"""
    return name.strip(), group.strip()


def _row_name(row: dict[str, Any]) -> str:
    return str(row.get("名称") or row.get("name") or "").strip()


def is_batch_duplicate(row: dict[str, str], seen_names: set[str]) -> str | None:
    """批量内令牌名重复则跳过。"""
    name = _row_name(row)
    if name and name in seen_names:
        return f"已跳过：批量内令牌名重复（{name}）"
    if name:
        seen_names.add(name)
    return None


def find_existing_duplicate(
    row: dict[str, str],
    name_index: dict[str, dict[str, Any]],
) -> str | None:
    """与本站已有令牌比对：名称相同则禁止创建。"""
    name = _row_name(row)
    if not name:
        return None
    matched = name_index.get(name)
    if not matched:
        return None
    return (
        f"令牌名已存在：本站已有「{name}」"
        f"（ID={matched.get('id', '?')}），令牌名须全站唯一"
    )


def build_existing_index(
    tokens: list[dict[str, Any]],
) -> dict[tuple[str, str], dict[str, Any]]:
    """名称+分组索引，供删除匹配使用。"""
    index: dict[tuple[str, str], dict[str, Any]] = {}
    for token in tokens:
        name = str(token.get("name") or "").strip()
        group = str(token.get("group") or "").strip()
        if not name:
            continue
        index[token_name_group(name, group)] = token
    return index


def build_name_index(tokens: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    for token in tokens:
        name = str(token.get("name") or "").strip()
        if name and name not in index:
            index[name] = token
    return index
