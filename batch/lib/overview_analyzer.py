# -*- coding: utf-8 -*-
"""⑥ 一表总览智能分析：对照上下游密钥/部署，输出建议处置表。"""

from __future__ import annotations

import re
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill

from .channel_activity import activity_allows_disable, disable_blocked_note, parse_activity_label
from .data_summary import ENVS, SHEET_CHANNELS, SHEET_TOKENS
from .data_summary_exporter import excel_dir, sort_excel_files_latest_first
from .deploy_time import parse_deploy_datetime
from .hygiene_policy import (
    default_policy,
    load_policy,
    new_deploy_hold,
    new_deploy_note,
    normalize_policy,
    uncommon_metric_label,
    unused_metric_label,
)
from .overview_exporter import load_sheet_rows
from .upstream_exporter import SHEET_AZURE, SHEET_AZURE_LEGACY, SHEET_VOLC, _apply_style, _write_sheet

ANALYSIS_STEM = "智能分析表格"
TIMESTAMP_FORMAT = "%Y%m%d%H%M%S"
_UUID_RE = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.I)
_EP_RE = re.compile(r"ep-\d{8,14}-[a-z0-9]+", re.I)

VENDOR_VOLC = "火山云"
VENDOR_AZURE = "Azure OpenAI"
VENDOR_OTHER = "外部/其它"

SHEET_SUMMARY = "分析总览"
SHEET_ACTIONS = "建议处置"
SHEET_DISABLED_ACTIONS = "已禁用建议"
SHEET_BATCH_DISABLE = "批量禁用"
SHEET_DOWN_NO_UP = "下游无上游"
SHEET_UP_NO_DOWN = "上游无下游"
SHEET_COVERAGE = "环境覆盖"
SHEET_SHARED = "密钥共用"
SHEET_TOKENS_A = "令牌对照"
SHEET_MATCH = "匹配明细"
SHEET_BALANCE = "渠道余额"

USAGE_UNUSED = "不用"
USAGE_UNCOMMON = "不常用"
USAGE_COMMON = "常用"
USED_UNCOMMON_USD = 1.0
NEW_DEPLOY_DAYS = 10
_RELAX_LEVEL = {"高": "中", "中": "低"}
_NEW_DEPLOY_NOTE = new_deploy_note(NEW_DEPLOY_DAYS)
_NEW_DEPLOY_HOLD = new_deploy_hold(NEW_DEPLOY_DAYS)

_FILL_HIGH = PatternFill("solid", fgColor="FFF4CCCC")
_FILL_MID = PatternFill("solid", fgColor="FFFFF2CC")
_FILL_LOW = PatternFill("solid", fgColor="FFD9EAD3")
_FILL_INFO = PatternFill("solid", fgColor="FFCFE2F3")
_LEVEL_FILLS = {"高": _FILL_HIGH, "中": _FILL_MID, "低": _FILL_LOW, "信息": _FILL_INFO}

ACTION_HEADERS = [
    "级别",
    "类别",
    "站点",
    "渠道名称",
    "令牌名称",
    "密钥摘要",
    "分组",
    "类型",
    "状态",
    "上游类型",
    "问题",
    "建议",
    "匹配线索",
    "base_url",
    "模型列表",
    "近一月活跃",
    "部署时间",
]
BATCH_DISABLE_HEADERS = [
    "test渠道",
    "test令牌",
    "uat渠道",
    "uat令牌",
    "prod渠道",
    "prod令牌",
]
BATCH_DISABLE_CATEGORIES = {"下游无上游", "渠道余额", "令牌对照"}
BATCH_DISABLE_LEVELS = {"高", "中"}
DOWN_HEADERS = [
    "站点",
    "渠道名称",
    "分组",
    "类型",
    "状态",
    "上游类型",
    "匹配方式",
    "上游对象",
    "问题",
    "建议",
    "密钥摘要",
    "base_url",
    "模型列表",
    "模型重定向",
    "部署时间",
]
UP_HEADERS = [
    "上游类型",
    "上游名称",
    "部署名",
    "项目/项目方",
    "负责人/联系人",
    "密钥摘要",
    "出现在test",
    "出现在uat",
    "出现在prod",
    "问题",
    "建议",
    "部署时间",
]
COVER_HEADERS = [
    "渠道名称",
    "上游类型",
    "test",
    "uat",
    "prod",
    "test密钥摘要",
    "uat密钥摘要",
    "prod密钥摘要",
    "密钥是否一致",
    "问题",
    "建议",
]
SHARED_HEADERS = ["上游类型", "密钥摘要", "使用次数", "站点与渠道", "建议"]
TOKEN_HEADERS_A = [
    "站点",
    "令牌名称",
    "状态",
    "分组",
    "可用模型",
    "包含渠道",
    "过期时间",
    "问题",
    "建议",
]
MATCH_HEADERS = [
    "站点",
    "渠道名称",
    "类型",
    "状态",
    "上游类型",
    "是否匹配上游",
    "匹配方式",
    "上游对象",
    "密钥摘要",
    "base_url",
    "模型列表",
]
BALANCE_HEADERS = [
    "站点",
    "渠道名称",
    "分组",
    "类型",
    "状态",
    "已用(USD)",
    "判定",
    "问题",
    "建议",
    "近一月活跃",
    "部署时间",
]
SUMMARY_HEADERS = ["指标", "数量", "说明"]
_USD_NUM_RE = re.compile(r"-?\d+(?:\.\d+)?")


def build_analysis_filename(when: datetime | None = None) -> str:
    stamp = (when or datetime.now()).strftime(TIMESTAMP_FORMAT)
    return f"{ANALYSIS_STEM}_{stamp}.xlsx"


def build_analysis_path(root_dir: Path, when: datetime | None = None) -> Path:
    return excel_dir(root_dir) / build_analysis_filename(when)


def list_analysis_excel_files(root_dir: Path) -> list[Path]:
    directory = excel_dir(root_dir)
    if not directory.exists():
        return []
    return sort_excel_files_latest_first(list(directory.glob(f"{ANALYSIS_STEM}_*.xlsx")))


def latest_analysis_excel_path(root_dir: Path) -> Path | None:
    files = list_analysis_excel_files(root_dir)
    return files[0] if files else None


def latest_balance_excel_for_analysis(root_dir: Path) -> Path | None:
    """智能分析用的最新渠道余额表：按文件名时间戳，没有则 None（不识别用量）。"""
    from .channel_balance_query import BALANCE_EXCEL_STEM, _LEGACY_BALANCE_PREFIX

    directory = excel_dir(root_dir)
    if not directory.exists():
        return None
    files = [p for p in directory.glob(f"{BALANCE_EXCEL_STEM}_*.xlsx") if _is_xlsx_file(p)]
    files.extend(p for p in directory.glob(f"{_LEGACY_BALANCE_PREFIX}*.xlsx") if _is_xlsx_file(p))
    if not files:
        return None
    return sort_excel_files_latest_first(files)[0]


def _is_xlsx_file(path: Path | str | None) -> bool:
    item = Path(path) if path else None
    return bool(item and item.is_file() and item.suffix.lower() == ".xlsx")


def parse_usd(value: Any) -> float | None:
    """把余额表「已用(USD)」解析成数字；空/无法解析返回 None（该行不识别）。"""
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = (
        str(value)
        .strip()
        .replace(",", "")
        .replace("，", "")
        .replace("$", "")
        .replace("USD", "")
        .replace("usd", "")
        .strip()
    )
    if not text or text in {"—", "-", "N/A", "n/a", "无"}:
        return None
    try:
        return float(text)
    except ValueError:
        found = _USD_NUM_RE.search(text)
        if not found:
            return None
        return float(found.group(0))


def classify_usage(
    usd: float,
    unused: float = 0.0,
    uncommon: float = USED_UNCOMMON_USD,
) -> str:
    """已用 ≤ unused → 不用；unused < 已用 < uncommon → 不常用；否则常用。"""
    if usd <= unused + 1e-9:
        return USAGE_UNUSED
    if usd < uncommon:
        return USAGE_UNCOMMON
    return USAGE_COMMON


def usage_action_level(usage: str, *, month_idle: bool) -> str:
    """用量类建议级别：不用为中；不常用且近一月无活跃升为中；其余不常用为低。"""
    if usage == USAGE_UNUSED:
        return "中"
    if usage == USAGE_UNCOMMON and month_idle:
        return "中"
    return "低"


def is_new_deploy(
    value: Any,
    *,
    now: datetime | None = None,
    days: int = NEW_DEPLOY_DAYS,
) -> bool:
    """部署时间距今小于 days 天（不含恰好满 days）。无时间或解析失败视为非新部署。"""
    dt = parse_deploy_datetime(value)
    if dt is None:
        return False
    clock = now or datetime.now()
    if clock.tzinfo is not None:
        clock = clock.replace(tzinfo=None)
    age = clock - dt
    return timedelta(0) <= age < timedelta(days=days)


def newest_deploy_time(values: list[Any]) -> str:
    best: datetime | None = None
    best_text = ""
    for value in values:
        dt = parse_deploy_datetime(value)
        if dt is None:
            continue
        if best is None or dt > best:
            best = dt
            best_text = str(value or "").strip()
    return best_text


def relax_for_new_deploy(
    row: dict[str, Any],
    deploy_time: str,
    *,
    now: datetime | None = None,
    days: int = NEW_DEPLOY_DAYS,
) -> dict[str, Any]:
    """新部署未满 days 天：级别高→中、中→低；建议改为暂缓处置。"""
    out = dict(row)
    text = str(deploy_time or "").strip()
    if text:
        out["部署时间"] = text
    if not is_new_deploy(text, now=now, days=days):
        return out
    note = new_deploy_note(days)
    hold = new_deploy_hold(days)
    level = str(out.get("级别") or "")
    if level in _RELAX_LEVEL:
        out["级别"] = _RELAX_LEVEL[level]
    problem = str(out.get("问题") or "")
    if note not in problem:
        out["问题"] = note + problem
    suggestion = str(out.get("建议") or "")
    if hold not in suggestion:
        out["建议"] = (suggestion + "；" if suggestion else "") + hold
    return out


def _env_from_balance_sheet(title: str) -> str:
    text = str(title or "").strip().lower()
    for env in ENVS:
        if text.startswith(env):
            return env
    return ""


def load_balance_workbook_rows(path: Path) -> list[dict[str, Any]]:
    from openpyxl import load_workbook

    src = Path(path)
    if not src.exists():
        return []
    wb = load_workbook(src, read_only=True, data_only=True)
    try:
        titles = list(wb.sheetnames)
    finally:
        wb.close()
    out: list[dict[str, Any]] = []
    for title in titles:
        sheet_env = _env_from_balance_sheet(title)
        for row in load_sheet_rows(src, [title]):
            env = sheet_env or str(row.get("环境") or "").strip().lower()
            row["_env"] = env
            out.append(row)
    return out


def _cell(row: dict[str, Any], *names: str) -> str:
    for name in names:
        value = row.get(name)
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return ""


def _mask_secret(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if len(text) <= 10:
        return text[:2] + "…"
    return f"{text[:6]}…{text[-4:]}"


def secret_tokens(value: str) -> set[str]:
    text = str(value or "").strip()
    if not text:
        return set()
    out = {text.lower()}
    if text.lower().startswith("ark-"):
        out.add(text[4:].lower())
    for match in _UUID_RE.findall(text):
        out.add(match.lower())
        out.add(match.lower().replace("-", ""))
    return {item for item in out if item}


def secrets_match(left: str, right: str) -> bool:
    a = str(left or "").strip()
    b = str(right or "").strip()
    if not a or not b:
        return False
    if secret_tokens(a) & secret_tokens(b):
        return True
    la, lb = a.lower(), b.lower()
    if len(a) >= 8 and la in lb:
        return True
    if len(b) >= 8 and lb in la:
        return True
    return False


def _host(url: str) -> str:
    text = str(url or "").strip()
    if not text:
        return ""
    if "://" not in text:
        text = "https://" + text
    try:
        return (urlparse(text).netloc or "").lower()
    except Exception:  # noqa: BLE001
        return ""


def classify_vendor(row: dict[str, Any]) -> str:
    type_name = _cell(row, "类型")
    url = _cell(row, "base_url").lower()
    if "azure" in type_name.lower() or "openai.azure.com" in url:
        return VENDOR_AZURE
    if "火山" in type_name or "豆包" in type_name or "volces.com" in url or "ark.cn" in url:
        return VENDOR_VOLC
    return VENDOR_OTHER


def _extract_eps(*texts: str) -> set[str]:
    found: set[str] = set()
    for text in texts:
        found.update(item.lower() for item in _EP_RE.findall(str(text or "")))
    return found


def _index_volc(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    indexed = []
    for row in rows:
        keys = [_cell(row, "API Key")]
        catalog = _cell(row, "API Key汇总")
        for part in re.split(r"[\n|,;；]+", catalog):
            part = part.strip()
            if "|" in part:
                part = part.split("|")[-1].strip()
            if part:
                keys.append(part)
        indexed.append(
            {
                "row": row,
                "name": _cell(row, "接入点名称"),
                "ep": _cell(row, "部署名"),
                "keys": [k for k in keys if k],
                "owner": _cell(row, "项目方"),
                "contact": _cell(row, "联系人"),
                "deploy_time": _cell(row, "部署时间"),
            }
        )
    return indexed


def _index_azure(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    indexed = []
    for row in rows:
        endpoint = _cell(row, "接口")
        account = _cell(row, "Azure OpenAI")
        hosts = {_host(endpoint)}
        if account:
            hosts.add(f"{account.lower()}.openai.azure.com")
        indexed.append(
            {
                "row": row,
                "name": _cell(row, "部署名"),
                "model": _cell(row, "模型名"),
                "key": _cell(row, "密钥一"),
                "hosts": {h for h in hosts if h},
                "account": account,
                "project": _cell(row, "项目"),
                "owner": _cell(row, "负责人"),
                "deploy_time": _cell(row, "部署时间"),
            }
        )
    return indexed


def match_channel(
    channel: dict[str, Any],
    volc_index: list[dict[str, Any]],
    azure_index: list[dict[str, Any]],
) -> dict[str, str]:
    vendor = classify_vendor(channel)
    name = _cell(channel, "名称")
    secret = _cell(channel, "密钥")
    models = _cell(channel, "模型列表")
    redirect = _cell(channel, "模型重定向")
    host = _host(_cell(channel, "base_url"))
    eps = _extract_eps(models, redirect, name)

    if vendor == VENDOR_VOLC:
        for item in volc_index:
            reasons: list[str] = []
            if secret and any(secrets_match(secret, key) for key in item["keys"]):
                reasons.append("密钥")
            if item["ep"] and item["ep"].lower() in eps:
                reasons.append("部署名")
            if item["name"] and item["name"].lower() == name.lower():
                reasons.append("接入点名称")
            if reasons:
                return {
                    "vendor": VENDOR_VOLC,
                    "matched": "是",
                    "how": "、".join(reasons),
                    "target": item["name"] or item["ep"],
                }
        return {"vendor": VENDOR_VOLC, "matched": "否", "how": "", "target": ""}

    if vendor == VENDOR_AZURE:
        for item in azure_index:
            reasons: list[str] = []
            if secret and secrets_match(secret, item["key"]):
                reasons.append("密钥")
            if item["name"] and (
                item["name"].lower() == name.lower()
                or item["name"].lower() in models.lower()
                or item["name"].lower() in redirect.lower()
            ):
                reasons.append("部署名")
            if host and host in item["hosts"]:
                reasons.append("接口主机")
            if reasons:
                return {
                    "vendor": VENDOR_AZURE,
                    "matched": "是",
                    "how": "、".join(dict.fromkeys(reasons)),
                    "target": item["name"] or item["account"],
                }
        return {"vendor": VENDOR_AZURE, "matched": "否", "how": "", "target": ""}

    return {"vendor": VENDOR_OTHER, "matched": "不适用", "how": "", "target": ""}


def _token_mentions(tokens: list[dict[str, Any]], channel_name: str) -> int:
    return len(_token_name_list(tokens, channel_name))


def _split_listed_names(text: str) -> list[str]:
    return [part.strip() for part in re.split(r"[,，;；|/]+", str(text or "")) if part.strip()]


def _token_refers_to_channel(
    token: dict[str, Any],
    channel_name: str,
    channel_group: str = "",
) -> bool:
    needle = (channel_name or "").strip()
    if not needle:
        return False
    included = _cell(token, "包含渠道")
    listed = _split_listed_names(included)
    if needle in listed:
        return True
    if included in {"无限制", "无限"}:
        token_group = _cell(token, "分组")
        if not token_group or not channel_group:
            return True
        groups = {part.strip() for part in channel_group.split(",") if part.strip()}
        return token_group in groups or any(token_group == item or token_group in item.split(",") for item in groups)
    return False


def _token_name_list(
    tokens: list[dict[str, Any]],
    channel_name: str,
    channel_group: str = "",
) -> list[str]:
    names: list[str] = []
    seen: set[str] = set()
    for token in tokens:
        if not _token_refers_to_channel(token, channel_name, channel_group):
            continue
        name = _cell(token, "名称")
        if name and name not in seen:
            seen.add(name)
            names.append(name)
    return names


def _token_names_for_channel(
    tokens: list[dict[str, Any]],
    channel_name: str,
    channel_group: str = "",
) -> str:
    return "，".join(_token_name_list(tokens, channel_name, channel_group))


def _envs_from_action_site(site: str) -> list[str]:
    text = str(site or "").strip()
    if not text or text in {"三站皆无"}:
        return []
    found = [env for env in ENVS if env in text]
    return found or [part.strip() for part in re.split(r"[,，、/\s]+", text) if part.strip() in ENVS]


def _fill_action_token_names(
    actions: list[dict[str, Any]],
    tokens_by_env: dict[str, list[dict[str, Any]]],
) -> None:
    """给建议处置补「令牌名称」：渠道右侧列出引用该渠道的令牌。"""
    for row in actions:
        if str(row.get("类别") or "") == "令牌对照" and str(row.get("令牌名称") or "").strip():
            continue
        channel = str(row.get("渠道名称") or "").strip()
        group = str(row.get("分组") or "").strip()
        names: list[str] = []
        seen: set[str] = set()
        envs = _envs_from_action_site(row.get("站点"))
        for env in envs or list(ENVS):
            for name in _token_name_list(tokens_by_env.get(env) or [], channel, group):
                if name not in seen:
                    seen.add(name)
                    names.append(name)
        if not envs and not names:
            row.setdefault("令牌名称", "")
            continue
        row["令牌名称"] = "，".join(names)


_ARCHIVE_SKIP_CATEGORIES = {"上游无下游", "环境覆盖"}


def _action_has_live_restricted_token(
    row: dict[str, Any],
    tokens_by_env: dict[str, list[dict[str, Any]]] | None = None,
) -> bool:
    """建议行列出的令牌里，是否还有未禁用的非无限制令牌。"""
    names = _split_listed_names(row.get("令牌名称"))
    if not names:
        return False
    index = _token_index_by_env(tokens_by_env or {})
    envs = _envs_from_action_site(row.get("站点")) or list(ENVS)
    for name in names:
        for env in envs:
            token = (index.get(env) or {}).get(name)
            if not token:
                continue
            if _token_is_unrestricted(token):
                continue
            if str(_cell(token, "状态") or "") != "已禁用":
                return True
    return False


def is_action_already_disabled(
    row: dict[str, Any],
    tokens_by_env: dict[str, list[dict[str, Any]]] | None = None,
) -> bool:
    """渠道（及列出的令牌）已禁用，不必再出现在建议处置。"""
    category = str(row.get("类别") or "")
    if category in _ARCHIVE_SKIP_CATEGORIES:
        return False
    status = str(row.get("状态") or "")
    if category == "令牌对照":
        return status == "已禁用"
    if status != "已禁用":
        return False
    return not _action_has_live_restricted_token(row, tokens_by_env)


def partition_disabled_actions(
    actions: list[dict[str, Any]],
    tokens_by_env: dict[str, list[dict[str, Any]]] | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """拆成待处置 / 已禁用建议。"""
    pending: list[dict[str, Any]] = []
    archived: list[dict[str, Any]] = []
    for row in actions or []:
        if is_action_already_disabled(row, tokens_by_env):
            archived.append(row)
        else:
            pending.append(row)
    return pending, archived


def format_name_group_line(name: Any, group: Any) -> str:
    """网关批量禁用/删除粘贴行：名称 + Tab + 分组。"""
    name_text = str(name or "").strip()
    group_text = str(group or "").strip()
    if not name_text or not group_text:
        return ""
    return f"{name_text}\t{group_text}"


def _token_is_unrestricted(token: dict[str, Any]) -> bool:
    return _cell(token, "包含渠道") in {"无限制", "无限"}


def _token_has_remaining_live_channel(
    token: dict[str, Any],
    *,
    disable_names: set[str],
    channels: list[dict[str, Any]] | None = None,
) -> bool:
    """令牌还挂着未进入本次禁用清单、且仍启用的渠道时，不能整条禁用。"""
    if _token_is_unrestricted(token):
        return True
    included = _split_listed_names(_cell(token, "包含渠道"))
    if not included:
        return False
    by_name = {_cell(ch, "名称"): ch for ch in channels or []}
    for name in included:
        if name in disable_names:
            continue
        channel = by_name.get(name)
        if not channel:
            continue
        if str(_cell(channel, "状态") or "") == "已禁用":
            continue
        return True
    return False


def _append_unique_line(bucket: list[str], seen: set[str], line: str) -> None:
    if not line or line in seen:
        return
    seen.add(line)
    bucket.append(line)


def _token_index_by_env(
    tokens_by_env: dict[str, list[dict[str, Any]]],
) -> dict[str, dict[str, dict[str, Any]]]:
    indexed: dict[str, dict[str, dict[str, Any]]] = {}
    for env, tokens in (tokens_by_env or {}).items():
        by_name: dict[str, dict[str, Any]] = {}
        for token in tokens or []:
            name = _cell(token, "名称")
            if name and name not in by_name:
                by_name[name] = token
        indexed[env] = by_name
    return indexed


def build_batch_disable_rows(
    actions: list[dict[str, Any]],
    tokens_by_env: dict[str, list[dict[str, Any]]] | None = None,
    channels_by_env: dict[str, list[dict[str, Any]]] | None = None,
    *,
    include_hold: bool = False,
) -> list[dict[str, str]]:
    """从建议处置抽出 test/uat/prod 渠道、令牌禁用清单（名称 Tab 分组）。"""
    tokens_by_env = tokens_by_env or {}
    channels_by_env = channels_by_env or {}
    cols: dict[str, list[str]] = {header: [] for header in BATCH_DISABLE_HEADERS}
    seen: dict[str, set[str]] = {header: set() for header in BATCH_DISABLE_HEADERS}
    token_index = _token_index_by_env(tokens_by_env)
    disable_names: dict[str, set[str]] = {env: set() for env in ENVS}
    token_actions: list[dict[str, Any]] = []
    channel_actions: list[tuple[dict[str, Any], list[str]]] = []

    for row in actions or []:
        if str(row.get("级别") or "") not in BATCH_DISABLE_LEVELS:
            continue
        category = str(row.get("类别") or "")
        if category not in BATCH_DISABLE_CATEGORIES:
            continue
        if "暂缓禁用" in str(row.get("建议") or "") and not include_hold:
            continue
        if "不禁用" in str(row.get("建议") or "") or "不据此禁用" in str(row.get("建议") or ""):
            continue
        if category == "渠道余额" and not activity_allows_disable(row.get("近一月活跃")):
            continue
        envs = _envs_from_action_site(row.get("站点"))
        if not envs:
            continue

        if category == "令牌对照":
            token_actions.append(row)
            continue

        channel_name = str(row.get("渠道名称") or "").strip()
        channel_group = str(row.get("分组") or "").strip()
        if str(row.get("状态") or "") != "已禁用" and channel_name and channel_group:
            for env in envs:
                disable_names[env].add(channel_name)
                _append_unique_line(
                    cols[f"{env}渠道"],
                    seen[f"{env}渠道"],
                    format_name_group_line(channel_name, channel_group),
                )
        channel_actions.append((row, envs))

    for row, envs in channel_actions:
        channel_name = str(row.get("渠道名称") or "").strip()
        channel_group = str(row.get("分组") or "").strip()
        listed = _split_listed_names(row.get("令牌名称"))
        for env in envs:
            header = f"{env}令牌"
            names = listed or _token_name_list(tokens_by_env.get(env) or [], channel_name, channel_group)
            for token_name in names:
                token = (token_index.get(env) or {}).get(token_name)
                if not token:
                    continue
                if str(_cell(token, "状态") or "") == "已禁用":
                    continue
                if _token_is_unrestricted(token):
                    continue
                if _token_has_remaining_live_channel(
                    token,
                    disable_names=disable_names.get(env) or set(),
                    channels=channels_by_env.get(env) or [],
                ):
                    continue
                _append_unique_line(
                    cols[header],
                    seen[header],
                    format_name_group_line(token_name, _cell(token, "分组")),
                )

    for row in token_actions:
        token_name = str(row.get("令牌名称") or "").strip()
        group = str(row.get("分组") or "").strip()
        for env in _envs_from_action_site(row.get("站点")):
            header = f"{env}令牌"
            token = (token_index.get(env) or {}).get(token_name)
            if token:
                if str(_cell(token, "状态") or "") == "已禁用":
                    continue
                group = group or _cell(token, "分组")
            _append_unique_line(cols[header], seen[header], format_name_group_line(token_name, group))

    height = max((len(cols[header]) for header in BATCH_DISABLE_HEADERS), default=0)
    return [
        {header: cols[header][idx] if idx < len(cols[header]) else "" for header in BATCH_DISABLE_HEADERS}
        for idx in range(height)
    ]


def analyze_overview_workbook(
    path: Path,
    *,
    balance_path: Path | None = None,
    root_dir: Path | None = None,
    now: datetime | None = None,
    policy: dict[str, Any] | None = None,
) -> dict[str, Any]:
    src = Path(path)
    if not src.exists():
        raise FileNotFoundError("未找到一表总览，请先点「一键生成总览表」")
    clock = now or datetime.now()
    policy_data = normalize_policy(policy if policy is not None else (load_policy(root_dir) if root_dir else default_policy()))
    deploy_days = int(policy_data["new_deploy_days"])
    unused_usd = float(policy_data["unused_used_usd"])
    uncommon_usd = float(policy_data["uncommon_used_usd"])
    include_external = bool(policy_data["external_vendors_in_scope"])
    include_activity = bool(policy_data.get("na_channel_activity_enabled"))
    _apply_relax = globals()["relax_for_new_deploy"]

    def _relax(row: dict[str, Any], deploy_time: str, *, now: datetime | None = None, days: int | None = None) -> dict[str, Any]:
        if not policy_data.get("relax_on_new_deploy", True):
            out = dict(row)
            text = str(deploy_time or "").strip()
            if text:
                out["部署时间"] = text
            return out
        return _apply_relax(row, deploy_time, now=clock, days=deploy_days)

    relax_for_new_deploy = _relax

    volc_rows = load_sheet_rows(src, [SHEET_VOLC])
    azure_rows = load_sheet_rows(src, [SHEET_AZURE, SHEET_AZURE_LEGACY])
    volc_index = _index_volc(volc_rows)
    azure_index = _index_azure(azure_rows)

    channels_by_env: dict[str, list[dict[str, Any]]] = {}
    tokens_by_env: dict[str, list[dict[str, Any]]] = {}
    match_rows: list[dict[str, Any]] = []
    down_rows: list[dict[str, Any]] = []
    actions: list[dict[str, Any]] = []
    other_count = 0

    for env in ENVS:
        channels_by_env[env] = load_sheet_rows(src, [SHEET_CHANNELS[env]])
        tokens_by_env[env] = load_sheet_rows(src, [SHEET_TOKENS[env]])
        tokens = tokens_by_env[env]
        for channel in channels_by_env[env]:
            name = _cell(channel, "名称")
            if not name:
                continue
            hit = match_channel(channel, volc_index, azure_index)
            vendor = hit["vendor"]
            status = _cell(channel, "状态") or "未知"
            secret = _cell(channel, "密钥")
            match_rows.append(
                {
                    "站点": env,
                    "渠道名称": name,
                    "类型": _cell(channel, "类型"),
                    "状态": status,
                    "上游类型": vendor,
                    "是否匹配上游": hit["matched"],
                    "匹配方式": hit["how"],
                    "上游对象": hit["target"],
                    "密钥摘要": _mask_secret(secret),
                    "base_url": _cell(channel, "base_url"),
                    "模型列表": _cell(channel, "模型列表"),
                }
            )
            if vendor == VENDOR_OTHER and not include_external:
                other_count += 1
                continue
            if hit["matched"] == "是":
                if status == "已禁用":
                    actions.append(
                        {
                            "级别": "低",
                            "类别": "已禁用仍登记",
                            "站点": env,
                            "渠道名称": name,
                            "分组": _cell(channel, "分组"),
                            "类型": _cell(channel, "类型"),
                            "状态": status,
                            "上游类型": vendor,
                            "问题": "渠道已禁用，但上游仍能匹配到对应部署/密钥",
                            "建议": "若业务已下线，可删除网关渠道；若只是临时停用可保留",
                            "匹配线索": hit["how"],
                            "密钥摘要": _mask_secret(secret),
                            "base_url": _cell(channel, "base_url"),
                            "模型列表": _cell(channel, "模型列表"),
                        }
                    )
                continue
            reason = "上游采集表中找不到该渠道的密钥或部署"
            if not secret:
                reason = "网关未填密钥，且无法按部署名/名称匹配到上游"
            suggestion = f"建议在 {env} 禁用或删除该渠道"
            token_hits = _token_mentions(tokens, name)
            if token_hits:
                suggestion += f"（有 {token_hits} 条令牌引用，删除前请先改令牌）"
            row = {
                "站点": env,
                "渠道名称": name,
                "分组": _cell(channel, "分组"),
                "类型": _cell(channel, "类型"),
                "状态": status,
                "上游类型": vendor,
                "匹配方式": hit["how"] or "未匹配",
                "上游对象": hit["target"],
                "问题": reason,
                "建议": suggestion,
                "密钥摘要": _mask_secret(secret),
                "base_url": _cell(channel, "base_url"),
                "模型列表": _cell(channel, "模型列表"),
                "模型重定向": _cell(channel, "模型重定向"),
            }
            deploy_time = _cell(channel, "部署时间")
            row = relax_for_new_deploy(row, deploy_time, now=clock)
            down_rows.append(row)
            actions.append(
                relax_for_new_deploy(
                    {
                        "级别": "高",
                        "类别": "下游无上游",
                        "站点": env,
                        "渠道名称": name,
                        "分组": row["分组"],
                        "类型": row["类型"],
                        "状态": status,
                        "上游类型": vendor,
                        "问题": reason + "（密钥可能已过期、轮换或上游已禁用）",
                        "建议": suggestion,
                        "匹配线索": "密钥/部署名/名称均未命中",
                        "密钥摘要": row["密钥摘要"],
                        "base_url": row["base_url"],
                        "模型列表": row["模型列表"],
                    },
                    deploy_time,
                    now=clock,
                )
            )

    up_rows: list[dict[str, Any]] = []
    for item in volc_index:
        envs_hit = {env: False for env in ENVS}
        for env, channels in channels_by_env.items():
            for channel in channels:
                if classify_vendor(channel) != VENDOR_VOLC:
                    continue
                secret = _cell(channel, "密钥")
                eps = _extract_eps(_cell(channel, "模型列表"), _cell(channel, "模型重定向"), _cell(channel, "名称"))
                name_hit = item["name"] and item["name"].lower() == _cell(channel, "名称").lower()
                key_hit = secret and any(secrets_match(secret, key) for key in item["keys"])
                ep_hit = item["ep"] and item["ep"].lower() in eps
                if key_hit or ep_hit or name_hit:
                    envs_hit[env] = True
                    break
        if any(envs_hit.values()):
            continue
        deploy_time = str(item.get("deploy_time") or "")
        up_rows.append(
            relax_for_new_deploy(
                {
                    "上游类型": VENDOR_VOLC,
                    "上游名称": item["name"],
                    "部署名": item["ep"],
                    "项目/项目方": item["owner"],
                    "负责人/联系人": item["contact"],
                    "密钥摘要": _mask_secret(item["keys"][0] if item["keys"] else ""),
                    "出现在test": "否",
                    "出现在uat": "否",
                    "出现在prod": "否",
                    "问题": "火山上游有接入点，test/uat/prod 均无对应渠道密钥或部署",
                    "建议": "确认是否已下线；若仍有效可补登记网关渠道，否则可在火山侧停用密钥",
                },
                deploy_time,
                now=clock,
            )
        )
        actions.append(
            relax_for_new_deploy(
                {
                    "级别": "中",
                    "类别": "上游无下游",
                    "站点": "三站皆无",
                    "渠道名称": item["name"],
                    "分组": "",
                    "类型": VENDOR_VOLC,
                    "状态": "",
                    "上游类型": VENDOR_VOLC,
                    "问题": "上游存在，网关三站都没有对应密钥/部署",
                    "建议": "未使用的上游密钥建议停用；需要的话在对应环境补渠道",
                    "匹配线索": item["ep"],
                    "密钥摘要": _mask_secret(item["keys"][0] if item["keys"] else ""),
                    "base_url": "",
                    "模型列表": "",
                },
                deploy_time,
                now=clock,
            )
        )

    for item in azure_index:
        envs_hit = {env: False for env in ENVS}
        for env, channels in channels_by_env.items():
            for channel in channels:
                if classify_vendor(channel) != VENDOR_AZURE:
                    continue
                secret = _cell(channel, "密钥")
                host = _host(_cell(channel, "base_url"))
                name = _cell(channel, "名称")
                blob = f"{name} {_cell(channel, '模型列表')} {_cell(channel, '模型重定向')}".lower()
                key_hit = secret and secrets_match(secret, item["key"])
                name_hit = item["name"] and item["name"].lower() in blob
                host_hit = host and host in item["hosts"] and name_hit
                if key_hit or name_hit or host_hit:
                    envs_hit[env] = True
                    break
        if any(envs_hit.values()):
            continue
        deploy_time = str(item.get("deploy_time") or "")
        up_rows.append(
            relax_for_new_deploy(
                {
                    "上游类型": VENDOR_AZURE,
                    "上游名称": item["name"] or item["account"],
                    "部署名": item["name"],
                    "项目/项目方": item["project"],
                    "负责人/联系人": item["owner"],
                    "密钥摘要": _mask_secret(item["key"]),
                    "出现在test": "否",
                    "出现在uat": "否",
                    "出现在prod": "否",
                    "问题": "Azure 上游有部署，test/uat/prod 均无对应渠道密钥或部署名",
                    "建议": "确认是否已下线；若仍有效可补登记网关渠道，否则可在 Azure 停用密钥",
                },
                deploy_time,
                now=clock,
            )
        )
        actions.append(
            relax_for_new_deploy(
                {
                    "级别": "中",
                    "类别": "上游无下游",
                    "站点": "三站皆无",
                    "渠道名称": item["name"] or item["account"],
                    "分组": "",
                    "类型": VENDOR_AZURE,
                    "状态": "",
                    "上游类型": VENDOR_AZURE,
                    "问题": "上游存在，网关三站都没有对应密钥/部署",
                    "建议": "未使用的上游密钥建议停用；需要的话在对应环境补渠道",
                    "匹配线索": item["account"],
                    "密钥摘要": _mask_secret(item["key"]),
                    "base_url": "",
                    "模型列表": "",
                },
                deploy_time,
                now=clock,
            )
        )

    names: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
    for env, channels in channels_by_env.items():
        for channel in channels:
            name = _cell(channel, "名称")
            if name:
                names[name][env] = channel
    cover_rows: list[dict[str, Any]] = []
    for name, by_env in sorted(names.items()):
        vendors = {classify_vendor(ch) for ch in by_env.values()}
        vendor = next(iter(vendors)) if len(vendors) == 1 else "、".join(sorted(vendors))
        secrets = {env: _cell(by_env[env], "密钥") if env in by_env else "" for env in ENVS}
        present = [env for env in ENVS if env in by_env]
        missing = [env for env in ENVS if env not in by_env]
        filled = [secrets[env] for env in present if secrets[env]]
        same_key = len({item.lower() for item in filled}) <= 1
        problem = ""
        suggestion = ""
        if len(present) >= 2 and missing:
            problem = f"在 {('、'.join(present))} 有渠道，缺少 {('、'.join(missing))}"
            suggestion = "三站应对齐时，请在缺的站点补渠道或确认该名称只用于部分环境"
        if filled and not same_key:
            extra = "跨站点同名渠道密钥不一致"
            problem = f"{problem}；{extra}" if problem else extra
            suggestion = (suggestion + "；" if suggestion else "") + "核对是否用了过期密钥"
        if not problem:
            continue
        deploy_time = newest_deploy_time([_cell(by_env[env], "部署时间") for env in present])
        cover_rows.append(
            {
                "渠道名称": name,
                "上游类型": vendor,
                "test": "有" if "test" in by_env else "无",
                "uat": "有" if "uat" in by_env else "无",
                "prod": "有" if "prod" in by_env else "无",
                "test密钥摘要": _mask_secret(secrets["test"]),
                "uat密钥摘要": _mask_secret(secrets["uat"]),
                "prod密钥摘要": _mask_secret(secrets["prod"]),
                "密钥是否一致": "是" if same_key else "否",
                "问题": problem,
                "建议": suggestion or "核对环境差异",
            }
        )
        actions.append(
            relax_for_new_deploy(
                {
                    "级别": "中" if not same_key else "低",
                    "类别": "环境覆盖",
                    "站点": "、".join(present),
                    "渠道名称": name,
                    "分组": _cell(next(iter(by_env.values())), "分组"),
                    "类型": _cell(next(iter(by_env.values())), "类型"),
                    "状态": "",
                    "上游类型": vendor,
                    "问题": problem,
                    "建议": suggestion or "核对环境差异",
                    "匹配线索": "",
                    "密钥摘要": "",
                    "base_url": "",
                    "模型列表": "",
                },
                deploy_time,
                now=clock,
            )
        )

    shared_map: dict[str, list[str]] = defaultdict(list)
    shared_vendor: dict[str, str] = {}
    for env, channels in channels_by_env.items():
        for channel in channels:
            secret = _cell(channel, "密钥")
            if not secret:
                continue
            key = next(iter(sorted(secret_tokens(secret))), secret.lower())
            shared_map[key].append(f"{env}/{_cell(channel, '名称')}")
            shared_vendor[key] = classify_vendor(channel)
    shared_rows = []
    for key, uses in shared_map.items():
        if len(uses) < 3:
            continue
        shared_rows.append(
            {
                "上游类型": shared_vendor.get(key, ""),
                "密钥摘要": _mask_secret(key if len(key) > 12 else uses[0]),
                "使用次数": len(uses),
                "站点与渠道": "；".join(uses[:20]) + ("…" if len(uses) > 20 else ""),
                "建议": "多渠道共用同一密钥，轮换时需一并更新；泄露影响面大",
            }
        )

    token_rows: list[dict[str, Any]] = []
    for env, tokens in tokens_by_env.items():
        channel_names = {_cell(ch, "名称") for ch in channels_by_env.get(env, [])}
        for token in tokens:
            name = _cell(token, "名称")
            included = _cell(token, "包含渠道")
            status = _cell(token, "状态")
            expire = _cell(token, "过期时间")
            problems: list[str] = []
            suggestions: list[str] = []
            unlimited = {"无限制", "无限", "永不过期", "无", "-", "never", "Never"}
            if status == "已禁用":
                problems.append("令牌已禁用")
                suggestions.append("确认是否仍需保留")
            if expire and expire not in unlimited:
                problems.append(f"过期时间 {expire}")
                suggestions.append("过期后请续期或删除")
            if included and included not in {"无限制", "无"}:
                missing = []
                for part in re.split(r"[,，;；|/\s]+", included):
                    part = part.strip()
                    if part and part not in channel_names and part not in {"无限制", "无"}:
                        missing.append(part)
                if missing:
                    problems.append("包含渠道在本环境渠道表中找不到：" + "、".join(missing[:8]))
                    suggestions.append("渠道已删或改名时，同步改令牌或删除令牌")
            if not problems:
                continue
            token_rows.append(
                {
                    "站点": env,
                    "令牌名称": name,
                    "状态": status,
                    "分组": _cell(token, "分组"),
                    "可用模型": _cell(token, "可用模型"),
                    "包含渠道": included,
                    "过期时间": expire,
                    "问题": "；".join(problems),
                    "建议": "；".join(suggestions),
                }
            )
            actions.append(
                {
                    "级别": "中" if "找不到" in "；".join(problems) else "低",
                    "类别": "令牌对照",
                    "站点": env,
                    "渠道名称": included,
                    "令牌名称": name,
                    "分组": _cell(token, "分组"),
                    "类型": "令牌",
                    "状态": status,
                    "上游类型": "",
                    "问题": f"令牌 {name}：" + "；".join(problems),
                    "建议": "；".join(suggestions),
                    "匹配线索": "",
                    "密钥摘要": "",
                    "base_url": "",
                    "模型列表": _cell(token, "可用模型"),
                }
            )

    resolved_balance = Path(balance_path) if balance_path else None
    if resolved_balance is None:
        if root_dir:
            resolved_balance = latest_balance_excel_for_analysis(root_dir)
        else:
            parent = src.parent
            resolved_balance = (
                latest_balance_excel_for_analysis(parent.parent)
                if parent.name == "excel"
                else latest_balance_excel_for_analysis(parent)
            )
    if resolved_balance is not None and not _is_xlsx_file(resolved_balance):
        resolved_balance = None

    balance_out: list[dict[str, Any]] = []
    unused_count = 0
    uncommon_count = 0
    if resolved_balance is not None:
        try:
            raw_balance = load_balance_workbook_rows(resolved_balance)
        except Exception:  # noqa: BLE001
            raw_balance = []
        has_used = any(parse_usd(_cell(row, "已用(USD)", "已用")) is not None for row in raw_balance)
        if has_used:
            for row in raw_balance:
                usd = parse_usd(_cell(row, "已用(USD)", "已用"))
                if usd is None:
                    continue
                env = str(row.get("_env") or "").strip().lower()
                name = _cell(row, "名称")
                if not name:
                    continue
                usage = classify_usage(usd, unused=unused_usd, uncommon=uncommon_usd)
                channel = next(
                    (ch for ch in channels_by_env.get(env, []) if _cell(ch, "名称") == name),
                    {},
                )
                status = _cell(channel, "状态") or _cell(row, "状态") or "未知"
                group = _cell(channel, "分组") or _cell(row, "分组")
                type_name = _cell(channel, "类型") or _cell(row, "类型")
                used_label = _cell(row, "已用(USD)", "已用") or f"${usd:g}"
                activity_label = _cell(row, "近一月活跃") if include_activity else ""
                if include_activity and not activity_label:
                    activity_label = _cell(channel, "近一月活跃")
                activity_parsed = parse_activity_label(activity_label)
                allow_disable = activity_allows_disable(activity_label)
                block_note = ""
                if not activity_parsed.get("legacy") and not allow_disable:
                    block_note = disable_blocked_note(str(activity_parsed.get("verdict") or "na"))
                if usage == USAGE_UNUSED:
                    problem = f"已用 ≤ ${unused_usd:g}，视为不用"
                    suggestion = f"建议在 {env or '对应站点'} 禁用或删除该渠道"
                    unused_count += 1
                elif usage == USAGE_UNCOMMON:
                    problem = f"已用 < ${uncommon_usd:g}，视为不常用"
                    suggestion = "确认是否仍需保留；长期不用可禁用"
                    uncommon_count += 1
                else:
                    problem = f"已用 ≥ ${uncommon_usd:g}，用量正常"
                    suggestion = ""
                month_idle = bool(allow_disable and not activity_parsed.get("legacy"))
                if usage == USAGE_UNCOMMON and month_idle:
                    problem = f"{problem}；近一月无活跃"
                    suggestion = f"建议在 {env or '对应站点'} 禁用或删除该渠道"
                if block_note:
                    suggestion = block_note
                    problem = f"{problem}；{block_note}"
                deploy_time = _cell(channel, "部署时间") if channel else ""
                activity_display = (
                    activity_label if activity_parsed.get("legacy") else (activity_label or "N/A")
                )
                item = relax_for_new_deploy(
                    {
                        "站点": env or _cell(row, "环境"),
                        "渠道名称": name,
                        "分组": group,
                        "类型": type_name,
                        "状态": status,
                        "已用(USD)": used_label,
                        "判定": usage,
                        "问题": problem,
                        "建议": suggestion,
                        "近一月活跃": activity_display,
                        "部署时间": deploy_time,
                    },
                    deploy_time,
                    now=clock,
                )
                balance_out.append(item)
                if usage == USAGE_COMMON:
                    continue
                if not allow_disable:
                    continue
                actions.append(
                    relax_for_new_deploy(
                        {
                            "级别": usage_action_level(usage, month_idle=month_idle),
                            "类别": "渠道余额",
                            "站点": item["站点"],
                            "渠道名称": name,
                            "分组": group,
                            "类型": type_name,
                            "状态": status,
                            "上游类型": classify_vendor(channel) if channel else "",
                            "问题": problem,
                            "建议": suggestion,
                            "匹配线索": used_label,
                            "密钥摘要": "",
                            "base_url": _cell(channel, "base_url") if channel else "",
                            "模型列表": _cell(channel, "模型列表") if channel else "",
                            "近一月活跃": activity_display,
                        },
                        deploy_time,
                        now=clock,
                    )
                )

    _fill_action_token_names(actions, tokens_by_env)
    actions, disabled_actions = partition_disabled_actions(actions, tokens_by_env)
    disable_rows = build_batch_disable_rows(actions, tokens_by_env, channels_by_env)
    level_rank = {"高": 0, "中": 1, "低": 2, "信息": 3}
    sort_key = lambda row: (
        level_rank.get(str(row.get("级别") or ""), 9),
        str(row.get("站点") or ""),
        str(row.get("渠道名称") or ""),
        str(row.get("令牌名称") or ""),
    )
    actions.sort(key=sort_key)
    disabled_actions.sort(key=sort_key)

    stats = {
        "source": src.name,
        "channels": sum(len(v) for v in channels_by_env.values()),
        "volc": len(volc_rows),
        "azure": len(azure_rows),
        "actions": len(actions),
        "disabled_actions": len(disabled_actions),
        "high": sum(1 for row in actions if row.get("级别") == "高"),
        "mid": sum(1 for row in actions if row.get("级别") == "中"),
        "low": sum(1 for row in actions if row.get("级别") == "低"),
        "down_no_up": len(down_rows),
        "up_no_down": len(up_rows),
        "coverage": len(cover_rows),
        "shared": len(shared_rows),
        "tokens": len(token_rows),
        "other": other_count,
        "matched": sum(1 for row in match_rows if row.get("是否匹配上游") == "是"),
        "balance_file": resolved_balance.name if resolved_balance else "",
        "balance_rows": len(balance_out),
        "balance_unused": unused_count,
        "balance_uncommon": uncommon_count,
        "relaxed_new_deploy": sum(
            1 for row in actions if "评估已放宽" in str(row.get("问题") or "")
        )
        + sum(
            1 for row in disabled_actions if "评估已放宽" in str(row.get("问题") or "")
        ),
        "disable_rows": len(disable_rows),
        "disable_channels": sum(1 for row in disable_rows for env in ENVS if row.get(f"{env}渠道")),
        "disable_tokens": sum(1 for row in disable_rows for env in ENVS if row.get(f"{env}令牌")),
    }
    return {
        "stats": stats,
        "policy": policy_data,
        "actions": actions,
        "disabled_actions": disabled_actions,
        "disable_rows": disable_rows,
        "down_rows": down_rows,
        "up_rows": up_rows,
        "cover_rows": cover_rows,
        "shared_rows": shared_rows,
        "token_rows": token_rows,
        "match_rows": match_rows,
        "balance_rows": balance_out,
    }


def _write_summary(ws, stats: dict[str, Any], policy: dict[str, Any] | None = None) -> None:
    policy_data = normalize_policy(policy)
    unused_usd = float(policy_data["unused_used_usd"])
    uncommon_usd = float(policy_data["uncommon_used_usd"])
    headers = SUMMARY_HEADERS
    rows = [
        {"指标": "来源总览", "数量": stats.get("source") or "", "说明": "本次分析读取的一表总览文件"},
        {"指标": "网关渠道行数", "数量": int(stats.get("channels") or 0), "说明": "test+uat+prod 渠道合计"},
        {"指标": "火山上游行数", "数量": int(stats.get("volc") or 0), "说明": "工作表 火山云"},
        {"指标": "Azure 上游行数", "数量": int(stats.get("azure") or 0), "说明": "工作表 Azure OpenAI"},
        {
            "指标": "已匹配上游的网关渠道",
            "数量": int(stats.get("matched") or 0),
            "说明": "密钥/部署名/名称命中火山或 Azure",
        },
        {
            "指标": "外部渠道（不对照过期）",
            "数量": int(stats.get("other") or 0),
            "说明": "DeepSeek/GLM/阿里云等，不在火山/Azure 采集范围",
        },
        {
            "指标": "高优先级建议",
            "数量": f"=COUNTIF('{SHEET_ACTIONS}'!A:A,\"高\")",
            "说明": "网关火山/Azure 渠道在上游找不到 → 建议禁用或删除",
        },
        {
            "指标": "中优先级建议",
            "数量": f"=COUNTIF('{SHEET_ACTIONS}'!A:A,\"中\")",
            "说明": "上游无下游、环境缺口、令牌引用丢失、不用渠道等",
        },
        {
            "指标": "低优先级建议",
            "数量": f"=COUNTIF('{SHEET_ACTIONS}'!A:A,\"低\")",
            "说明": "共用密钥、新部署放宽后的提示等（已禁用项见右侧工作表）",
        },
        {
            "指标": "已禁用建议",
            "数量": int(stats.get("disabled_actions") or 0),
            "说明": f"工作表 {SHEET_DISABLED_ACTIONS}：渠道和相关令牌均已禁用，不再出现在建议处置",
        },
        {
            "指标": "批量禁用行",
            "数量": int(stats.get("disable_rows") or 0),
            "说明": f"工作表 {SHEET_BATCH_DISABLE}：test/uat/prod 渠道 {int(stats.get('disable_channels') or 0)} 条、令牌 {int(stats.get('disable_tokens') or 0)} 条，复制整列到②预禁用",
        },
        {
            "指标": "下游无上游条数",
            "数量": f"=COUNTA('{SHEET_DOWN_NO_UP}'!A:A)-1",
            "说明": "建议在对应站点禁用或删除渠道",
        },
        {
            "指标": "上游无下游条数",
            "数量": f"=COUNTA('{SHEET_UP_NO_DOWN}'!A:A)-1",
            "说明": "上游有、三站都没有对应渠道",
        },
        {
            "指标": "渠道余额文件",
            "数量": stats.get("balance_file") or "未找到，用量未识别",
            "说明": "读取 excel/渠道余额_时间戳.xlsx；没有该文件则跳过用量判定",
        },
        {
            "指标": unused_metric_label(policy_data),
            "数量": int(stats.get("balance_unused") or 0),
            "说明": f"有余额表时：已用 ≤ ${unused_usd:g} 视为不用，建议禁用或删除",
        },
        {
            "指标": uncommon_metric_label(policy_data),
            "数量": int(stats.get("balance_uncommon") or 0),
            "说明": (
                f"有余额表时：${unused_usd:g} < 已用 < ${uncommon_usd:g} 视为不常用；"
                "同时近一月无活跃则建议级别为中"
            ),
        },
    ]
    _write_sheet(ws, headers, rows)


def _color_level_column(ws) -> None:
    for row_idx in range(2, (ws.max_row or 1) + 1):
        level = str(ws.cell(row=row_idx, column=1).value or "").strip()
        fill = _LEVEL_FILLS.get(level)
        if not fill:
            continue
        for col_idx in range(1, ws.max_column + 1):
            ws.cell(row=row_idx, column=col_idx).fill = fill
            if level == "高":
                ws.cell(row=row_idx, column=col_idx).font = Font(name="宋体", size=11, color="FF990000")


def save_analysis_workbook(path: Path, payload: dict[str, Any]) -> Path:
    dest = Path(path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    wb = Workbook()
    ws_sum = wb.active
    ws_sum.title = SHEET_SUMMARY
    policy = normalize_policy(payload.get("policy"))
    _write_summary(ws_sum, payload.get("stats") or {}, policy)

    sheets = (
        (SHEET_ACTIONS, ACTION_HEADERS, payload.get("actions") or []),
        (SHEET_DISABLED_ACTIONS, ACTION_HEADERS, payload.get("disabled_actions") or []),
        (SHEET_BATCH_DISABLE, BATCH_DISABLE_HEADERS, payload.get("disable_rows") or []),
        (SHEET_DOWN_NO_UP, DOWN_HEADERS, payload.get("down_rows") or []),
        (SHEET_UP_NO_DOWN, UP_HEADERS, payload.get("up_rows") or []),
        (SHEET_COVERAGE, COVER_HEADERS, payload.get("cover_rows") or []),
        (SHEET_SHARED, SHARED_HEADERS, payload.get("shared_rows") or []),
        (SHEET_TOKENS_A, TOKEN_HEADERS_A, payload.get("token_rows") or []),
        (SHEET_MATCH, MATCH_HEADERS, payload.get("match_rows") or []),
        (SHEET_BALANCE, BALANCE_HEADERS, payload.get("balance_rows") or []),
    )
    for title, headers, rows in sheets:
        ws = wb.create_sheet(title)
        _write_sheet(ws, headers, rows)
        if title in {SHEET_ACTIONS, SHEET_DISABLED_ACTIONS}:
            _color_level_column(ws)

    activity_note = (
        (
            "近一月活跃按模型逐项评估：全部无活跃才允许用量类禁用；不常用且近一月无活跃升为中。"
            "任一模型有活跃或 N/A 则不禁用渠道/令牌。旧表无该列时不常用仍为低。"
        )
        if policy.get("na_channel_activity_enabled")
        else "近一月活跃统计未开启，不读取该列；保持旧版用量规则。"
    )
    note = wb.create_sheet("说明")
    _write_sheet(
        note,
        ["项", "说明"],
        [
            {"项": "匹配规则（火山）", "说明": "网关密钥与上游 API Key 按 UUID/ark- 前后缀相容匹配；或模型列表含 ep- 部署名；或渠道名=接入点名称"},
            {"项": "匹配规则（Azure）", "说明": "密钥一相等（忽略大小写）；或部署名出现在渠道名/模型列表/重定向；或接口主机相同"},
            {"项": "下游无上游", "说明": "网关已有火山/Azure 渠道，但总览里的上游表找不到对应密钥或部署 → 视为过期/禁用/已轮换，建议在该站点禁用或删除渠道"},
            {"项": "上游无下游", "说明": "上游仍有接入点/部署，test/uat/prod 都没有对应渠道 → 可能未接入或已从网关删除"},
            {
                "项": "外部渠道",
                "说明": (
                    "自定义 / OpenAI / GLM 等已纳入过期对照"
                    if policy.get("external_vendors_in_scope")
                    else "自定义 / OpenAI / GLM 等不在本次火山+Azure 采集范围，不判过期"
                ),
            },
            {
                "项": "新部署放宽",
                "说明": (
                    (
                        f"网关渠道或上游「部署时间」距今小于 {int(policy['new_deploy_days'])} 天时，"
                        "建议处置降一级（高→中、中→低），暂缓禁用/停用；无部署时间则不放宽"
                    )
                    if policy.get("relax_on_new_deploy", True)
                    else "当前策略未开启新部署放宽"
                ),
            },
            {
                "项": "渠道余额",
                "说明": (
                    "读取 excel/ 下最新一份 渠道余额_时间戳.xlsx。没有该文件则不识别用量。"
                    f"已用 ≤ ${float(policy['unused_used_usd']):g} 视为不用（中）；"
                    f"{float(policy['unused_used_usd']):g} < 已用 < ${float(policy['uncommon_used_usd']):g} 视为不常用。"
                    + activity_note
                    + "渠道和相关令牌均已禁用时不进建议处置，改写入「已禁用建议」"
                ),
            },
            {"项": "建议处置列", "说明": "渠道名称右侧为引用该渠道的令牌名称（按该环境令牌「包含渠道」匹配；无限制且分组相同也列出），令牌旁为密钥摘要。渠道及列出的令牌均已禁用时不写本表"},
            {"项": "已禁用建议", "说明": "紧挨建议处置右侧。列结构与建议处置相同。存放渠道已禁用、且列出的非无限制令牌也全部已禁用（或没有这类令牌）的原建议，以及已禁用的令牌对照。便于对照，不必再处置"},
            {"项": "批量禁用", "说明": "紧挨已禁用建议右侧。从建议处置里高/中优先级且建议禁用的项生成 test/uat/prod 渠道与令牌粘贴列，格式为 名称[Tab]分组。复制整列到②渠道管理/令牌管理即可预禁用。令牌仅当其仍启用的「包含渠道」全部进入本次渠道禁用清单时才写入（避免一条令牌挂了多条渠道、只废其中一条却整条禁用）。不含上游无下游、环境覆盖、新部署暂缓、无限制共享令牌、已禁用项"},
            {"项": "密钥展示", "说明": "分析表只写密钥摘要，完整密钥仍在总览原表"},
        ],
    )
    wb.save(dest)
    wb.close()
    return dest


def run_overview_analysis(
    root_dir: Path,
    source: Path | None = None,
    policy: dict[str, Any] | None = None,
    balance_path: Path | None = None,
) -> tuple[Path, dict[str, Any]]:
    src = Path(source) if source else None
    if src is None or not src.exists():
        from .overview_exporter import latest_overview_excel_path

        src = latest_overview_excel_path(root_dir)
    if src is None or not src.exists():
        raise FileNotFoundError("未找到一表总览，请先点「一键生成总览表」")
    payload = analyze_overview_workbook(
        src,
        root_dir=root_dir,
        policy=policy if policy is not None else load_policy(root_dir),
        balance_path=balance_path,
    )
    dest = build_analysis_path(root_dir)
    save_analysis_workbook(dest, payload)
    return dest, payload


def analysis_workbook_stats(path: Path) -> dict[str, Any]:
    if not path or not Path(path).exists():
        return {"rows": 0, "sheet": SHEET_SUMMARY, "sheets": {}, "high": 0, "actions": 0, "disabled_actions": 0}
    from openpyxl import load_workbook

    wb = load_workbook(path, read_only=True, data_only=True)
    try:
        sheets = {name: max(0, int(wb[name].max_row or 1) - 1) for name in wb.sheetnames}
        return {
            "rows": sheets.get(SHEET_ACTIONS, 0),
            "sheet": SHEET_SUMMARY,
            "sheets": sheets,
            "high": 0,
            "actions": sheets.get(SHEET_ACTIONS, 0),
            "disabled_actions": sheets.get(SHEET_DISABLED_ACTIONS, 0),
            "down_no_up": sheets.get(SHEET_DOWN_NO_UP, 0),
            "up_no_down": sheets.get(SHEET_UP_NO_DOWN, 0),
            "balance": sheets.get(SHEET_BALANCE, 0),
        }
    finally:
        wb.close()
