# -*- coding: utf-8 -*-
"""上游账单 · Azure Cost Management（按资源分组，按天 / 按月导出）。"""

from __future__ import annotations

import calendar
import re
import time
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from .azure_arm import (
    AzureARMClient,
    AzureARMError,
    acquire_arm_token,
    parse_resource_group,
    parse_subscription_entries,
)
from .upstream_azure import (
    NA_FALLBACK,
    deployment_model,
    format_location,
    is_openai_account,
    parse_tag_project_owner,
)
from .volc_billing import (
    COST_COL_HEADER,
    COST_FIELD,
    bill_month_label,
    parse_bill_period,
    sheet_data_rows,
    write_bill_sheet,
)

SUB_GAP_SEC = 3.0
EXCEL_STEM = "上游账单_Azure"
TIMESTAMP_FORMAT = "%Y%m%d%H%M%S"
SHEET_DAY = "按天"
SHEET_MONTH = "按月"
SHEET_NOTE = "说明"
DAY_HEADERS = ["日期", "项目名", "项目负责人", "模型名", "配置名称", "地区", "订阅", "费用"]
MONTH_HEADERS = list(DAY_HEADERS)
COST_PORTAL = "https://portal.azure.com/#view/Microsoft_Azure_CostManagement/Menu/~/costanalysis"
PERMISSION_HINT = (
    "当前服务主体调不通成本分析。"
    "凭证仍用 env/sites.json 的 upstream.azure。"
    "请在每个订阅的 IAM 给该应用加「成本管理读取者」（Cost Management Reader），"
    "与上游信息已有的「读取者」可以并存。"
    f"控制台对照：{COST_PORTAL}，分组依据选「资源」，粒度选「每天」或「每月」。"
)
_DATE_DIGITS = re.compile(r"\d+")


@dataclass
class AzureBillStats:
    bill_period: str = ""
    source_action: str = "CostManagement/query ResourceId Daily"
    day_rows: int = 0
    month_rows: int = 0
    raw_count: int = 0
    skipped_empty: int = 0
    currencies: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    rows_day: list[dict[str, Any]] = field(default_factory=list)
    rows_month: list[dict[str, Any]] = field(default_factory=list)


def excel_dir(root_dir: Path) -> Path:
    return Path(root_dir) / "excel"


def build_bill_filename(when: datetime | None = None, *, bill_period: Any = None) -> str:
    stamp = (when or datetime.now()).strftime(TIMESTAMP_FORMAT)
    return f"{EXCEL_STEM}_{bill_month_label(bill_period)}_{stamp}.xlsx"


def build_bill_path(root_dir: Path, when: datetime | None = None, *, bill_period: Any = None) -> Path:
    return excel_dir(root_dir) / build_bill_filename(when, bill_period=bill_period)


def list_azure_bill_excel_files(root_dir: Path) -> list[Path]:
    from .data_summary_exporter import sort_excel_files_latest_first

    directory = excel_dir(root_dir)
    if not directory.exists():
        return []
    return sort_excel_files_latest_first(list(directory.glob(f"{EXCEL_STEM}_*.xlsx")))


def latest_azure_bill_excel_path(root_dir: Path) -> Path | None:
    files = list_azure_bill_excel_files(root_dir)
    return files[0] if files else None


def period_bounds(period: str) -> tuple[str, str]:
    text = parse_bill_period(period)
    year, month = int(text[:4]), int(text[5:7])
    last = calendar.monthrange(year, month)[1]
    return f"{year:04d}-{month:02d}-01", f"{year:04d}-{month:02d}-{last:02d}"


def _parse_money(value: Any) -> Decimal:
    text = (
        str(value or "")
        .strip()
        .replace(",", "")
        .replace("¥", "")
        .replace("￥", "")
        .replace(" ", "")
    )
    if not text:
        return Decimal("0")
    try:
        return Decimal(text)
    except (InvalidOperation, ValueError):
        return Decimal("0")


def _format_money(value: Decimal) -> float:
    quantized = value.quantize(Decimal("0.000001"))
    return float(quantized)


def resource_name_from_id(resource_id: str) -> str:
    text = str(resource_id or "").strip().rstrip("/")
    if not text:
        return ""
    return text.split("/")[-1]


def format_usage_date(value: Any) -> str:
    if value in (None, ""):
        return ""
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d")
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        digits = str(int(value))
    else:
        digits = "".join(_DATE_DIGITS.findall(str(value)))
    if len(digits) >= 8:
        return f"{digits[:4]}-{digits[4:6]}-{digits[6:8]}"
    if len(digits) >= 6:
        return f"{digits[:4]}-{digits[4:6]}"
    return str(value).strip()


def _row_cost(item: dict[str, Any]) -> Decimal:
    for key in ("Cost", "PreTaxCost", "cost", "preTaxCost"):
        if item.get(key) not in (None, ""):
            return _parse_money(item.get(key))
    return Decimal("0")


def _row_currency(item: dict[str, Any]) -> str:
    return str(item.get("Currency") or item.get("currency") or "").strip()


def fetch_daily_cost_rows(client: AzureARMClient, date_from: str, date_to: str) -> list[dict[str, Any]]:
    try:
        return client.query_cost_dicts(
            granularity="Daily",
            date_from=date_from,
            date_to=date_to,
            grouping=["ResourceId", "ResourceLocation"],
        )
    except AzureARMError as exc:
        if exc.status not in {400, 422}:
            raise
        return client.query_cost_dicts(
            granularity="Daily",
            date_from=date_from,
            date_to=date_to,
            grouping=["ResourceId"],
        )


def _account_tags(account: dict[str, Any]) -> Any:
    tags = account.get("tags")
    props = account.get("properties") if isinstance(account.get("properties"), dict) else {}
    if isinstance(props.get("tags"), dict) and not (
        isinstance(tags, dict) and str(tags.get("1") or "").strip()
    ):
        return props.get("tags")
    return tags


def build_resource_catalog(client: AzureARMClient, *, subscription_label: str) -> dict[str, dict[str, str]]:
    catalog: dict[str, dict[str, str]] = {}
    try:
        accounts = client.list_accounts()
    except AzureARMError:
        return catalog
    for account in accounts:
        if not is_openai_account(account):
            continue
        account_id = str(account.get("id") or "").strip()
        name = str(account.get("name") or "").strip()
        if not account_id and not name:
            continue
        rg = parse_resource_group(account_id)
        location = format_location(str(account.get("location") or "").strip())
        project, owner = parse_tag_project_owner(_account_tags(account))
        models: list[str] = []
        if rg and name:
            try:
                for dep in client.list_deployments(rg, name):
                    model_name, _version = deployment_model(dep)
                    text = (model_name or str(dep.get("name") or "")).strip()
                    if text and text not in models:
                        models.append(text)
            except AzureARMError:
                pass
        info = {
            "项目名": project or NA_FALLBACK,
            "项目负责人": owner or NA_FALLBACK,
            "模型名": "，".join(models),
            "配置名称": name,
            "地区": location,
            "订阅": subscription_label,
        }
        if account_id:
            catalog[account_id.lower()] = info
        if name:
            catalog[name.lower()] = info
    return catalog


def _lookup_catalog(catalog: dict[str, dict[str, str]], resource_id: str, resource_name: str) -> dict[str, str]:
    for key in (resource_id.lower(), resource_name.lower()):
        if key and key in catalog:
            return catalog[key]
    return {}


def is_upstream_resource(resource_id: str, name: str, catalog: dict[str, dict[str, str]]) -> bool:
    if _lookup_catalog(catalog, resource_id, name):
        return True
    blob = f"{resource_id} {name}".lower()
    return any(token in blob for token in ("openai", "cognitiveservices", "aiservices", "foundry"))


def map_cost_item(
    item: dict[str, Any],
    *,
    catalog: dict[str, dict[str, str]],
    subscription_label: str,
    bill_period: str,
) -> dict[str, Any]:
    resource_id = str(item.get("ResourceId") or item.get("ResourceID") or "").strip()
    name = str(item.get("ResourceName") or "").strip() or resource_name_from_id(resource_id)
    if not name and not resource_id:
        return {}
    date = format_usage_date(item.get("UsageDate") or item.get("Date") or bill_period)
    if len(date) == 7:
        date = f"{date}-01"
    extra = _lookup_catalog(catalog, resource_id, name)
    location = extra.get("地区") or format_location(str(item.get("ResourceLocation") or item.get("Location") or ""))
    return {
        "日期": date or bill_period,
        "项目名": extra.get("项目名") or NA_FALLBACK,
        "项目负责人": extra.get("项目负责人") or NA_FALLBACK,
        "模型名": extra.get("模型名") or "",
        "配置名称": extra.get("配置名称") or name,
        "地区": location,
        "订阅": extra.get("订阅") or subscription_label,
        "费用": _format_money(_row_cost(item)),
        "Currency": _row_currency(item),
    }


def _row_key(row: dict[str, Any], *, month: bool = False) -> tuple[str, ...]:
    date = str(row.get("日期") or "")
    if month:
        date = date[:7]
    return (
        date,
        str(row.get("项目名") or ""),
        str(row.get("项目负责人") or ""),
        str(row.get("模型名") or ""),
        str(row.get("配置名称") or ""),
        str(row.get("地区") or ""),
        str(row.get("订阅") or ""),
    )


def aggregate_azure_rows(rows: list[dict[str, Any]], *, month: bool = False) -> list[dict[str, Any]]:
    buckets: dict[tuple[str, ...], Decimal] = {}
    for row in rows:
        if not row:
            continue
        key = _row_key(row, month=month)
        buckets[key] = buckets.get(key, Decimal("0")) + _parse_money(row.get("费用"))
    out = [
        {
            "日期": key[0],
            "项目名": key[1],
            "项目负责人": key[2],
            "模型名": key[3],
            "配置名称": key[4],
            "地区": key[5],
            "订阅": key[6],
            "费用": _format_money(amount),
        }
        for key, amount in buckets.items()
    ]
    out.sort(
        key=lambda r: (
            str(r["日期"]),
            str(r["订阅"]),
            str(r["配置名称"]),
            str(r["项目名"]),
        )
    )
    return out


def _is_permission_error(exc: AzureARMError) -> bool:
    text = str(exc).lower()
    return exc.status == 403 or any(
        token in text for token in ("authorization", "forbidden", "permission", "denied")
    )


def collect_azure_bills(
    tenant_id: str,
    client_id: str,
    client_secret: str,
    *,
    subscription_id: str = "",
    subscription_ids: list[str] | str | None = None,
    bill_period: str | None = None,
    client_factory: Any = None,
) -> AzureBillStats:
    period = parse_bill_period(bill_period)
    date_from, date_to = period_bounds(period)
    stats = AzureBillStats(bill_period=period)
    entries = parse_subscription_entries(subscription_ids, subscription_id)
    try:
        token = acquire_arm_token(tenant_id, client_id, client_secret)
    except AzureARMError as exc:
        stats.errors.append(str(exc))
        return stats

    mapped: list[dict[str, Any]] = []
    currencies: set[str] = set()
    factory = client_factory or (lambda sub: AzureARMClient(token, subscription_id=sub))
    for index, entry in enumerate(entries):
        if index:
            time.sleep(SUB_GAP_SEC)
        sub = entry["id"]
        label = entry["label"]
        try:
            client = factory(sub)
            catalog = build_resource_catalog(client, subscription_label=label)
            raw = fetch_daily_cost_rows(client, date_from, date_to)
            stats.raw_count += len(raw)
            for item in raw:
                row = map_cost_item(
                    item,
                    catalog=catalog,
                    subscription_label=label,
                    bill_period=period,
                )
                if not row or not row.get("配置名称"):
                    stats.skipped_empty += 1
                    continue
                if not is_upstream_resource(str(item.get("ResourceId") or ""), str(row.get("配置名称") or ""), catalog):
                    stats.skipped_empty += 1
                    continue
                currency = str(row.pop("Currency", "") or "").strip()
                if currency:
                    currencies.add(currency)
                mapped.append(row)
        except AzureARMError as exc:
            message = str(exc)
            if _is_permission_error(exc):
                message = f"{PERMISSION_HINT} 原始错误：{exc}"
            stats.errors.append(f"[{label}] {message}")
        except Exception as exc:  # noqa: BLE001
            stats.errors.append(f"[{label}] {exc}")

    stats.currencies = sorted(currencies)
    stats.rows_day = aggregate_azure_rows(mapped, month=False)
    stats.rows_month = aggregate_azure_rows(mapped, month=True)
    stats.day_rows = len(stats.rows_day)
    stats.month_rows = len(stats.rows_month)
    return stats


def _write_sheet(ws, headers: list[str], rows: list[dict[str, Any]], *, add_sum: bool | None = None) -> None:
    has_cost = COST_FIELD in headers
    write_bill_sheet(ws, headers, rows, add_sum=has_cost if add_sum is None else add_sum)


def save_azure_bill_workbook(path: Path, stats: AzureBillStats) -> Path:
    from openpyxl import Workbook

    dest = Path(path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    wb = Workbook()
    ws_day = wb.active
    ws_day.title = SHEET_DAY
    _write_sheet(ws_day, DAY_HEADERS, stats.rows_day)
    ws_month = wb.create_sheet(SHEET_MONTH)
    _write_sheet(ws_month, MONTH_HEADERS, stats.rows_month)
    currency = "、".join(stats.currencies) if stats.currencies else "账单币种（国内订阅一般为 CNY）"
    note = wb.create_sheet(SHEET_NOTE)
    _write_sheet(
        note,
        ["项", "说明"],
        [
            {"项": "账期", "说明": stats.bill_period},
            {"项": "接口", "说明": stats.source_action},
            {
                "项": "分组",
                "说明": "Cost Management Query，分组依据 ResourceId（门户「资源」）",
            },
            {
                "项": "按天",
                "说明": "粒度 Daily；日期 YYYY-MM-DD。项目名/负责人来自账号标记「1」（项目-负责人），与上游信息相同。",
            },
            {
                "项": "按月",
                "说明": "由按天按 项目名+负责人+模型名+配置名称+地区+订阅 汇总，日期 YYYY-MM，对应门户粒度「每月」。",
            },
            {
                "项": "配置名称",
                "说明": "Azure 资源名（OpenAI 账号名）。费用在资源级，不按部署拆分。",
            },
            {
                "项": "模型名",
                "说明": "该账号下全部部署模型，顿号拼接；无部署则为空。",
            },
            {"项": COST_COL_HEADER, "说明": f"ActualCost 的 Cost，币种：{currency}；列头与单元格均标注 ¥，末行为 SUM 合计"},
            {"项": "原始条数", "说明": str(stats.raw_count)},
            {"项": "对照控制台", "说明": COST_PORTAL},
        ],
    )
    wb.save(dest)
    wb.close()
    return dest


def run_azure_bill_export(
    root_dir: Path,
    tenant_id: str,
    client_id: str,
    client_secret: str,
    *,
    subscription_id: str = "",
    subscription_ids: list[str] | str | None = None,
    bill_period: str | None = None,
    client_factory: Any = None,
) -> tuple[Path, AzureBillStats]:
    stats = collect_azure_bills(
        tenant_id,
        client_id,
        client_secret,
        subscription_id=subscription_id,
        subscription_ids=subscription_ids,
        bill_period=bill_period,
        client_factory=client_factory,
    )
    if not stats.rows_day and stats.errors and stats.raw_count == 0:
        raise AzureARMError("；".join(stats.errors))
    dest = build_bill_path(root_dir, bill_period=stats.bill_period)
    save_azure_bill_workbook(dest, stats)
    return dest, stats


def azure_bill_workbook_stats(path: Path) -> dict[str, Any]:
    if not path or not Path(path).exists():
        return {"rows": 0, "sheet": SHEET_DAY, "sheets": {}, "total_rows": 0}
    from openpyxl import load_workbook

    wb = load_workbook(path, read_only=True, data_only=True)
    try:
        sheets = {name: sheet_data_rows(wb[name]) for name in wb.sheetnames}
        return {
            "rows": sheets.get(SHEET_DAY, 0),
            "sheet": SHEET_DAY,
            "sheets": sheets,
            "total_rows": sheets.get(SHEET_DAY, 0) + sheets.get(SHEET_MONTH, 0),
        }
    finally:
        wb.close()
