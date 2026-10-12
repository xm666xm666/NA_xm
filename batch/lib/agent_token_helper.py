"""由渠道行 + 用户名生成令牌批量文本。

令牌名默认：{渠道名}-{用户名}
例如：demo-alpha-test-glm-x-样例甲
多条渠道 × 多个用户名 → 各自一条令牌。
"""

from __future__ import annotations

from typing import Any

from .channel_builder import parse_data_line


def parse_token_usernames(raw: str) -> list[str]:
    """解析用户名：每行一个，也支持中英文逗号/顿号分隔。"""
    text = (raw or "").strip()
    if not text:
        return []
    names: list[str] = []
    seen: set[str] = set()
    for line in text.replace("，", "\n").replace(",", "\n").replace("、", "\n").splitlines():
        name = line.strip()
        if not name or name in seen:
            continue
        seen.add(name)
        names.append(name)
    return names


def _channel_fields_from_line(line: str) -> dict[str, str]:
    text = (line or "").strip()
    if not text or text.startswith("#"):
        raise ValueError("空行")
    # 优先完整渠道行解析
    try:
        return parse_data_line(text)
    except ValueError:
        pass
    # 退化：Tab 分隔至少 名称/分组/模型
    if "\t" in text:
        parts = [p.strip() for p in text.split("\t") if p.strip()]
        if len(parts) >= 3:
            return {"名称": parts[0], "分组": parts[1], "模型": parts[2] if len(parts) == 3 else parts[3]}
    parts = text.split()
    if len(parts) >= 4:
        # 名称 分组 类型 模型 …
        return {"名称": parts[0], "分组": parts[1], "模型": parts[3]}
    raise ValueError(f"无法从渠道行解析名称/分组/模型: {text[:80]}")


def iter_channel_rows(channel_lines: str) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for raw in (channel_lines or "").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        try:
            rows.append(_channel_fields_from_line(line))
        except ValueError:
            continue
    return rows


def build_token_batch_text(channel_lines: str, usernames: list[str] | str) -> str:
    """生成令牌批量文本：名称\\t分组\\t模型限制（多模型可用、）。"""
    users = parse_token_usernames(usernames) if isinstance(usernames, str) else [
        str(u).strip() for u in (usernames or []) if str(u).strip()
    ]
    if not users:
        raise ValueError("请填写令牌用户名（将拼到渠道名后）")
    channels = iter_channel_rows(channel_lines)
    if not channels:
        raise ValueError("没有可用的渠道行，无法生成令牌")

    out: list[str] = []
    for ch in channels:
        ch_name = str(ch.get("名称") or "").strip()
        group = str(ch.get("分组") or "").strip()
        model = str(ch.get("模型") or "").strip()
        if not ch_name or not group or not model:
            continue
        for user in users:
            token_name = f"{ch_name}-{user}"
            out.append(f"{token_name}\t{group}\t{model}")

    if not out:
        raise ValueError("未能生成任何令牌行（请检查渠道名称/分组/模型）")
    return "\n".join(out)


def preview_token_plans(channel_lines: str, usernames: list[str] | str) -> list[dict[str, Any]]:
    """预览将创建的令牌清单（不写网关）。"""
    text = build_token_batch_text(channel_lines, usernames)
    plans: list[dict[str, Any]] = []
    for line in text.splitlines():
        name, group, models = line.split("\t", 2)
        plans.append({"名称": name, "分组": group, "模型限制": models})
    return plans
