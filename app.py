"""NA 自动配置工具 - 融合 Web 入口（智能提取 + 批量配置）。"""

from __future__ import annotations

import atexit
import importlib
import json
import re
import sys
import threading
import time
import uuid
import webbrowser
from datetime import datetime
from pathlib import Path
from typing import Any

from flask import Flask, Response, g, jsonify, request, send_from_directory, stream_with_context

import na_logger

NEW_DIR = Path(__file__).resolve().parent
AGENT_DIR = NEW_DIR / "agent"
BATCH_DIR = NEW_DIR / "batch"
STATIC_DIR = NEW_DIR / "static"
BATCH_STATIC = BATCH_DIR / "static"
AGENT_CONFIG = AGENT_DIR / "config.json"
BATCH_CONFIG = BATCH_DIR / "config.json"
ENV_DIR = NEW_DIR / "env"
ENV_SITES_FILE = ENV_DIR / "sites.json"
ENV_UPSTREAM_FILE = ENV_DIR / "upstream.json"
EXCEL_DIR = NEW_DIR / "excel"
_LIB_LOCK = threading.RLock()
ENV_SITE_KEYS = ("test", "uat", "prod")


def _ensure_excel_dir() -> Path:
    EXCEL_DIR.mkdir(parents=True, exist_ok=True)
    return EXCEL_DIR


def _store_excel_bytes(filename: str, data: bytes) -> Path:
    safe_name = Path(str(filename or "")).name
    if not safe_name:
        raise ValueError("Excel 文件名无效")
    path = _ensure_excel_dir() / safe_name
    path.write_bytes(data)
    return path


def _rel_to_root(path: Path) -> str:
    return str(path.relative_to(NEW_DIR)).replace("\\", "/")


def _send_excel_attachment(path: Path, extra_headers: dict[str, str] | None = None):
    resp = send_from_directory(
        path.parent,
        path.name,
        as_attachment=True,
        download_name=path.name,
    )
    if extra_headers:
        for key, value in extra_headers.items():
            resp.headers[key] = value
    return resp


def _clear_lib_modules() -> None:
    for key in list(sys.modules):
        if key == "lib" or key.startswith("lib."):
            del sys.modules[key]


def _pin_lib_root(root: Path) -> None:
    """agent/batch 均有 lib 包名，须独占 sys.path[0] 避免 namespace 混用。"""
    _clear_lib_modules()
    for p in (str(AGENT_DIR), str(BATCH_DIR)):
        while p in sys.path:
            sys.path.remove(p)
    sys.path.insert(0, str(root))


def _load_batch_modules():
    with _LIB_LOCK:
        _pin_lib_root(BATCH_DIR)
        api_client = importlib.import_module("lib.api_client")
        batch_processor = importlib.import_module("lib.batch_processor")
        channel_types = importlib.import_module("lib.channel_types")
        channel_batch_delete = importlib.import_module("lib.channel_batch_delete")
        channel_batch_status = importlib.import_module("lib.channel_batch_status")
        channel_batch_update = importlib.import_module("lib.channel_batch_update")
        channel_remark_sync = importlib.import_module("lib.channel_remark_sync")
        channel_balance_query = importlib.import_module("lib.channel_balance_query")
        channel_test = importlib.import_module("lib.channel_test")
        group_batch_processor = importlib.import_module("lib.group_batch_processor")
        group_batch_switch = importlib.import_module("lib.group_batch_switch")
        token_batch_delete = importlib.import_module("lib.token_batch_delete")
        token_batch_status = importlib.import_module("lib.token_batch_status")
        token_batch_update = importlib.import_module("lib.token_batch_update")
        token_batch_processor = importlib.import_module("lib.token_batch_processor")
        token_export = importlib.import_module("lib.token_export")
        agent_token_helper = importlib.import_module("lib.agent_token_helper")
        log_exporter = importlib.import_module("lib.log_exporter")
        url_utils = importlib.import_module("lib.url_utils")
        data_summary = importlib.import_module("lib.data_summary")
        data_summary_exporter = importlib.import_module("lib.data_summary_exporter")
        upstream_volc = importlib.import_module("lib.upstream_volc")
        upstream_azure = importlib.import_module("lib.upstream_azure")
        upstream_exporter = importlib.import_module("lib.upstream_exporter")
        overview_exporter = importlib.import_module("lib.overview_exporter")
        overview_analyzer = importlib.import_module("lib.overview_analyzer")
        totp = importlib.import_module("lib.totp")
        hygiene_policy = importlib.import_module("lib.hygiene_policy")
        artifacts = importlib.import_module("lib.artifacts")
        hygiene_actions = importlib.import_module("lib.hygiene_actions")
        azure_arm = importlib.import_module("lib.azure_arm")
        azure_billing = importlib.import_module("lib.azure_billing")
        volc_billing = importlib.import_module("lib.volc_billing")
        bill_combined = importlib.import_module("lib.bill_combined")
        volc_openapi = importlib.import_module("lib.volc_openapi")
        env_clusters = importlib.import_module("lib.env_clusters")
        return {
            "NewAPIClient": api_client.NewAPIClient,
            "authenticate_client": api_client.authenticate_client,
            "run_batch_create": batch_processor.run_batch_create,
            "run_channel_test": channel_test.run_channel_test,
            "get_channel_types": channel_types.get_channel_types,
            "run_channel_batch_delete": channel_batch_delete.run_channel_batch_delete,
            "run_channel_batch_update": channel_batch_update.run_channel_batch_update,
            "run_channel_remark_sync": channel_remark_sync.run_channel_remark_sync,
            "run_channel_batch_status": channel_batch_status.run_channel_batch_status,
            "run_channel_balance_query": channel_balance_query.run_channel_balance_query,
            "run_multi_site_channel_balance_query": channel_balance_query.run_multi_site_channel_balance_query,
            "export_channel_balance_xlsx": channel_balance_query.export_channel_balance_xlsx,
            "latest_balance_excel_path": channel_balance_query.latest_balance_excel_path,
            "list_site_groups": group_batch_processor.list_site_groups,
            "run_group_create": group_batch_processor.run_group_create,
            "run_group_delete": group_batch_processor.run_group_delete,
            "list_group_members": group_batch_switch.list_group_members,
            "run_group_switch": group_batch_switch.run_group_switch,
            "run_token_batch_delete": token_batch_delete.run_token_batch_delete,
            "run_token_batch_status": token_batch_status.run_token_batch_status,
            "run_token_batch_quota_update": token_batch_update.run_token_batch_quota_update,
            "fetch_channel_models": token_batch_processor.fetch_channel_models,
            "run_token_batch_create": token_batch_processor.run_token_batch_create,
            "export_all_tokens_text": token_export.export_all_tokens_text,
            "build_token_batch_text": agent_token_helper.build_token_batch_text,
            "run_logs_export": log_exporter.run_logs_export,
            "LogExportCancelled": log_exporter.LogExportCancelled,
            "coerce_verify_ssl": api_client.coerce_verify_ssl,
            "normalize_na_base_url": url_utils.normalize_na_base_url,
            "parse_summary_sites": data_summary.parse_sites,
            "inspect_summary_sites_auth": data_summary.inspect_summary_sites_auth,
            "login_site_auth": data_summary.login_site_auth,
            "session_cache_alive": api_client.session_cache_alive,
            "run_data_summary_collect": data_summary.run_data_summary_collect,
            "fill_missing_channel_keys": data_summary.fill_missing_channel_keys,
            "scan_channel_key_status": data_summary.scan_channel_key_status,
            "enrich_auth_totp": data_summary.enrich_auth_totp,
            "enrich_auth_from_env": data_summary.enrich_auth_from_env,
            "pick_totp_secret": totp.pick_totp_secret,
            "has_otp_source": totp.has_otp_source,
            "default_excel_path": data_summary_exporter.default_excel_path,
            "latest_excel_path": data_summary_exporter.latest_excel_path,
            "build_timestamped_path": data_summary_exporter.build_timestamped_path,
            "publish_staging_excel": data_summary_exporter.publish_staging_excel,
            "is_staging_excel": data_summary_exporter.is_staging_excel,
            "summary_workbook_stats": data_summary_exporter.workbook_summary,
            "EXCEL_STEM": data_summary.EXCEL_STEM,
            "ENVS": data_summary.ENVS,
            "test_volc_connection": upstream_volc.test_volc_connection,
            "collect_volc_upstream": upstream_volc.collect_volc_upstream,
            "find_real_token_reference": upstream_volc.find_real_token_reference,
            "load_real_tokens_by_deploy_id": upstream_volc.load_real_tokens_by_deploy_id,
            "UPSTREAM_HEADERS": upstream_volc.UPSTREAM_HEADERS,
            "AZURE_HEADERS": upstream_azure.AZURE_HEADERS,
            "test_azure_connection": upstream_azure.test_azure_connection,
            "collect_azure_upstream": upstream_azure.collect_azure_upstream,
            "build_upstream_path": upstream_exporter.build_upstream_path,
            "latest_upstream_excel_path": upstream_exporter.latest_upstream_excel_path,
            "save_upstream_workbook": upstream_exporter.save_upstream_workbook,
            "upstream_workbook_stats": upstream_exporter.upstream_workbook_stats,
            "UPSTREAM_EXCEL_STEM": upstream_exporter.UPSTREAM_EXCEL_STEM,
            "SHEET_VOLC": upstream_exporter.SHEET_VOLC,
            "build_azure_upstream_path": upstream_exporter.build_azure_upstream_path,
            "latest_azure_upstream_excel_path": upstream_exporter.latest_azure_upstream_excel_path,
            "UPSTREAM_AZURE_STEM": upstream_exporter.UPSTREAM_AZURE_STEM,
            "SHEET_AZURE": upstream_exporter.SHEET_AZURE,
            "build_combined_upstream_path": upstream_exporter.build_combined_upstream_path,
            "latest_combined_upstream_excel_path": upstream_exporter.latest_combined_upstream_excel_path,
            "save_combined_upstream_workbook": upstream_exporter.save_combined_upstream_workbook,
            "UPSTREAM_COMBINED_STEM": upstream_exporter.UPSTREAM_COMBINED_STEM,
            "build_overview_path": overview_exporter.build_overview_path,
            "latest_overview_excel_path": overview_exporter.latest_overview_excel_path,
            "save_overview_workbook": overview_exporter.save_overview_workbook,
            "overview_workbook_stats": overview_exporter.overview_workbook_stats,
            "resolve_gateway_source": overview_exporter.resolve_gateway_source,
            "resolve_volc_rows": overview_exporter.resolve_volc_rows,
            "resolve_azure_rows": overview_exporter.resolve_azure_rows,
            "describe_overview_sources": overview_exporter.describe_overview_sources,
            "refresh_overview_index": overview_exporter.refresh_overview_index,
            "run_overview_analysis": overview_analyzer.run_overview_analysis,
            "latest_analysis_excel_path": overview_analyzer.latest_analysis_excel_path,
            "latest_balance_excel_for_analysis": overview_analyzer.latest_balance_excel_for_analysis,
            "analysis_workbook_stats": overview_analyzer.analysis_workbook_stats,
            "ANALYSIS_STEM": overview_analyzer.ANALYSIS_STEM,
            "OVERVIEW_STEM": overview_exporter.OVERVIEW_STEM,
            "SHEET_INDEX": overview_exporter.SHEET_INDEX,
            "load_policy": hygiene_policy.load_policy,
            "save_policy": hygiene_policy.save_policy,
            "policy_summary_text": hygiene_policy.policy_summary_text,
            "list_artifacts": artifacts.list_artifacts,
            "latest_artifacts_bundle": artifacts.latest_artifacts_bundle,
            "resolve_excel_path": artifacts.resolve_excel_path,
            "list_summary_excel_files": data_summary_exporter.list_summary_excel_files,
            "load_analysis_payload": hygiene_actions.load_analysis_payload,
            "select_actions": hygiene_actions.select_actions,
            "preview_disable_from_actions": hygiene_actions.preview_disable_from_actions,
            "mark_actions_done": hygiene_actions.mark_actions_done,
            "filename_timestamp": data_summary_exporter.filename_timestamp,
            "run_volc_bill_export": volc_billing.run_volc_bill_export,
            "collect_volc_bills": volc_billing.collect_volc_bills,
            "latest_bill_excel_path": volc_billing.latest_bill_excel_path,
            "bill_workbook_stats": volc_billing.bill_workbook_stats,
            "BILL_EXCEL_STEM": volc_billing.EXCEL_STEM,
            "SHEET_BILL_DAY": volc_billing.SHEET_DAY,
            "default_bill_period": volc_billing.default_bill_period,
            "parse_bill_period": volc_billing.parse_bill_period,
            "bill_periods_from_payload": volc_billing.bill_periods_from_payload,
            "excel_cost_headers": volc_billing.excel_cost_headers,
            "VOLC_BILL_HEADERS": volc_billing.DAY_HEADERS,
            "VolcOpenAPIError": volc_openapi.VolcOpenAPIError,
            "AzureARMError": azure_arm.AzureARMError,
            "run_azure_bill_export": azure_billing.run_azure_bill_export,
            "collect_azure_bills": azure_billing.collect_azure_bills,
            "latest_azure_bill_excel_path": azure_billing.latest_azure_bill_excel_path,
            "azure_bill_workbook_stats": azure_billing.azure_bill_workbook_stats,
            "AZURE_BILL_EXCEL_STEM": azure_billing.EXCEL_STEM,
            "AZURE_BILL_HEADERS": azure_billing.DAY_HEADERS,
            "build_combined_bill_path": bill_combined.build_combined_bill_path,
            "latest_combined_bill_excel_path": bill_combined.latest_combined_bill_excel_path,
            "save_combined_bill_workbook": bill_combined.save_combined_bill_workbook,
            "combined_bill_workbook_stats": bill_combined.combined_bill_workbook_stats,
            "BILL_COMBINED_STEM": bill_combined.COMBINED_STEM,
            "SHEET_BILL_VOLC_DAY": bill_combined.SHEET_VOLC_DAY,
            "SHEET_BILL_VOLC_MONTH": bill_combined.SHEET_VOLC_MONTH,
            "SHEET_BILL_AZURE_DAY": bill_combined.SHEET_AZURE_DAY,
            "SHEET_BILL_AZURE_MONTH": bill_combined.SHEET_AZURE_MONTH,
            "cluster_label": env_clusters.cluster_label,
            "public_host": env_clusters.public_host,
            "ordered_site_keys": env_clusters.ordered_site_keys,
        }


def _reload_batch_modules():
    """agent 与 batch 共用 lib 包名，加载 agent 后会清掉 batch 的 lib；数据汇总等需重新加载。"""
    global BATCH
    BATCH = _load_batch_modules()
    return BATCH


def _lib_is_batch() -> bool:
    lib = sys.modules.get("lib")
    lib_file = getattr(lib, "__file__", None)
    if not lib_file:
        return False
    try:
        return Path(lib_file).resolve().parent == (BATCH_DIR / "lib").resolve()
    except OSError:
        return False


def _ensure_batch():
    """首页会请求 /api/llm-presets（切到 agent/lib），之后批量接口的延迟 import 会失败。"""
    with _LIB_LOCK:
        if not _lib_is_batch():
            _reload_batch_modules()
        return BATCH


def _user_facing_error(exc: BaseException) -> str:
    """把内部异常转成页面可执行的中文故障说明。"""
    text = str(exc).strip() or type(exc).__name__
    missing = str(getattr(exc, "name", "") or "")
    combined = f"{missing} {text}"
    if isinstance(exc, (ModuleNotFoundError, ImportError)) or "No module named" in text:
        if "lib." in combined or "lib'" in combined or "lib\"" in combined:
            return (
                f"批量配置模块未就绪（{text}）。"
                "首页加载 LLM 预设或智能提取会切到另一套 lib，导致找不到 batch 模块"
                "（例如 lib.rate_budget）。请关闭本页后重新运行 run.bat，再用当前代码重试。"
            )
        return f"依赖缺失（{text}）。请确认已安装项目依赖，并重启 run.bat。"
    if (
        "CERTIFICATE_VERIFY_FAILED" in combined
        or "SSLCertVerificationError" in combined
        or "Hostname mismatch" in combined
        or "certificate is not valid for" in combined
    ):
        return (
            "HTTPS 证书校验失败：站点证书域名与填写的地址不一致"
            "（证书不是签发给当前主机名）。"
            "若这是公司内网网关，请在左侧连接配置勾选「跳过 SSL 证书校验」后重试。"
        )
    return text


def _load_agent_extractor():
    with _LIB_LOCK:
        _pin_lib_root(AGENT_DIR)
        channel_extractor = importlib.import_module("lib.channel_extractor")
        return channel_extractor.extract_channels


def _load_agent_token_extractor():
    with _LIB_LOCK:
        _pin_lib_root(AGENT_DIR)
        token_extractor = importlib.import_module("lib.token_extractor")
        return token_extractor.extract_tokens


def _reload_agent_modules():
    """batch 与 agent 共用 lib 包名，互相加载后需重新加载 agent 模块。"""
    global extract_channels, extract_tokens
    extract_channels = _load_agent_extractor()
    extract_tokens = _load_agent_token_extractor()
    return extract_channels


BATCH = _load_batch_modules()
extract_channels = _load_agent_extractor()
extract_tokens = _load_agent_token_extractor()
_reload_batch_modules()

app = Flask(__name__, static_folder=None, static_url_path=None)


def _request_client_ip() -> str:
    forwarded = (request.headers.get("X-Forwarded-For") or "").split(",")[0].strip()
    return forwarded or (request.remote_addr or "-")


@app.before_request
def _na_log_before_request():
    g._na_log_t0 = time.perf_counter()
    path = request.path or ""
    if not path.startswith("/api/"):
        return None
    body_summary = ""
    if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
        raw = request.get_json(silent=True)
        if raw is not None:
            body_summary = na_logger.dumps_safe(raw, max_len=2500)
        elif request.data:
            body_summary = na_logger.dumps_safe(request.data[:500].decode("utf-8", errors="replace"))
    na_logger.info(
        f"API 请求 → {request.method} {path} | client={_request_client_ip()}"
        + (f" | body={body_summary}" if body_summary else "")
    )
    return None


@app.after_request
def _na_log_after_request(response: Response):
    path = request.path or ""
    if not path.startswith("/api/"):
        return response

    elapsed_ms = (time.perf_counter() - float(getattr(g, "_na_log_t0", time.perf_counter()))) * 1000.0
    status = int(response.status_code)
    ctype = (response.mimetype or "").lower()
    detail = f"HTTP {status} | {elapsed_ms:.1f}ms"

    # SSE / 流式：不读完整 body
    if "text/event-stream" in ctype or path.endswith("/events"):
        na_logger.info(f"API 响应 ← {request.method} {path} | {detail} | stream=SSE")
        return response

    body_text = ""
    try:
        if "json" in ctype or path.startswith("/api/"):
            raw = response.get_data(as_text=True)
            if raw:
                try:
                    parsed = json.loads(raw)
                    detail = f"{detail} | {na_logger.summarize_api_result(parsed)}"
                    # 逐条 warning / fail 再落一行，便于审查
                    data = parsed.get("data") if isinstance(parsed, dict) else None
                    items = None
                    if isinstance(data, dict):
                        items = data.get("items") or data.get("results")
                    if isinstance(items, list):
                        for item in items:
                            if not isinstance(item, dict):
                                continue
                            if item.get("success") is False:
                                na_logger.fail(
                                    f"操作明细 FAIL | {path} | "
                                    f"#{item.get('index', '?')} {item.get('name') or item.get('id')}: "
                                    f"{item.get('message') or item.get('error') or ''}"
                                )
                            elif item.get("warning") or item.get("skipped") or str(item.get("status", "")).lower() in {
                                "skip",
                                "warn",
                                "warning",
                            }:
                                na_logger.warn(
                                    f"操作明细 WARN | {path} | "
                                    f"#{item.get('index', '?')} {item.get('name') or item.get('id')}: "
                                    f"{item.get('message') or item.get('warning') or ''}"
                                )
                    success = parsed.get("success") if isinstance(parsed, dict) else None
                    if success is False or status >= 400:
                        na_logger.fail(f"API 响应 ← {request.method} {path} | {detail}")
                        return response
                    if success is True:
                        na_logger.ok(f"API 响应 ← {request.method} {path} | {detail}")
                        return response
                except json.JSONDecodeError:
                    body_text = raw[:500]
    except Exception as exc:  # noqa: BLE001
        na_logger.warn(f"API 响应日志解析失败 | {path} | {exc}")

    if status >= 400:
        na_logger.fail(f"API 响应 ← {request.method} {path} | {detail}" + (f" | body={body_text}" if body_text else ""))
    elif status >= 300:
        na_logger.warn(f"API 响应 ← {request.method} {path} | {detail}")
    else:
        na_logger.info(f"API 响应 ← {request.method} {path} | {detail}" + (f" | body={body_text}" if body_text else ""))
    return response


@app.teardown_request
def _na_log_teardown_request(exc: BaseException | None):
    if exc is None:
        return
    path = getattr(request, "path", "") or ""
    if path.startswith("/api/"):
        na_logger.error(f"API 未捕获异常 | {request.method} {path} | {type(exc).__name__}: {exc}")


@app.get("/")
def index():
    return send_from_directory(STATIC_DIR, "index.html")


@app.get("/favicon.ico")
def favicon_ico():
    return send_from_directory(STATIC_DIR, "favicon.svg", mimetype="image/svg+xml")


@app.get("/static/<path:filename>")
def static_files(filename: str):
    if filename == "batch_ui.html":
        return send_from_directory(BATCH_STATIC, "index.html")
    if filename == "summary_ui.html":
        return send_from_directory(STATIC_DIR, "summary_ui.html")
    if filename == "agent_ui.html":
        return send_from_directory(STATIC_DIR, "agent_ui.html")
    if filename == "upstream_ui.html":
        return send_from_directory(STATIC_DIR, "upstream_ui.html")
    if filename == "overview_ui.html":
        return send_from_directory(STATIC_DIR, "overview_ui.html")
    if filename == "bill_ui.html":
        return send_from_directory(STATIC_DIR, "bill_ui.html")
    for folder in (STATIC_DIR, BATCH_STATIC):
        if (folder / filename).is_file():
            return send_from_directory(folder, filename)
    return jsonify({"success": False, "message": "文件不存在"}), 404


def _load_llm_config() -> dict:
    if not AGENT_CONFIG.exists():
        return {}
    try:
        with AGENT_CONFIG.open(encoding="utf-8") as f:
            data = json.load(f)
        return {
            "api_base": data.get("llm_api_base", ""),
            "api_key": data.get("llm_api_key", ""),
            "model": data.get("llm_model", "gpt-4o-mini"),
            "provider": data.get("llm_provider", ""),
            "timeout": data.get("llm_timeout", 60),
        }
    except (json.JSONDecodeError, OSError):
        return {}


def _load_batch_config() -> dict:
    if not BATCH_CONFIG.exists():
        return {}
    try:
        with BATCH_CONFIG.open(encoding="utf-8") as f:
            data = json.load(f)
        return {
            "base_url": BATCH["normalize_na_base_url"](str(data.get("base_url") or "").strip()),
            "username": str(data.get("username") or "").strip(),
            "password": data.get("password") or "",
            "access_token": str(data.get("access_token") or "").strip(),
            "user_id": data.get("user_id"),
            "default_key": str(data.get("default_key") or "").strip(),
        }
    except (json.JSONDecodeError, OSError):
        return {}


@app.get("/api/batch-config")
def batch_config():
    data = _load_batch_config()
    return jsonify(
        {
            "success": True,
            "source": "file" if data else "none",
            "data": data,
        }
    )


def _normalize_env_site(raw: Any) -> dict[str, Any] | None:
    """单环境站点：至少要有 base_url 才视为已配置。"""
    if not isinstance(raw, dict):
        return None
    base_url = BATCH["normalize_na_base_url"](str(raw.get("base_url") or "").strip())
    if not base_url:
        return None
    site: dict[str, Any] = {
        "base_url": base_url,
        "username": str(raw.get("username") or "").strip(),
        "password": raw.get("password") if raw.get("password") is not None else "",
        "default_key": str(raw.get("default_key") or "").strip(),
        "access_token": str(raw.get("access_token") or "").strip(),
        "user_id": raw.get("user_id"),
    }
    if site["access_token"] and not site["username"] and not site["password"]:
        site["auth_mode"] = "token"
    else:
        site["auth_mode"] = "password"
    if BATCH["pick_totp_secret"](raw.get("otp_code"), mapping=raw):
        site["has_totp_secret"] = True
    return site


def _load_env_sites() -> dict[str, Any]:
    """读取 env/sites.json；不存在或无效则返回空（前端隐藏快捷按钮）。"""
    if not ENV_SITES_FILE.exists():
        return {"configured": False, "sites": {}, "available": []}
    try:
        with ENV_SITES_FILE.open(encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return {"configured": False, "sites": {}, "available": [], "error": "env/sites.json 无法解析"}

    if not isinstance(data, dict):
        return {"configured": False, "sites": {}, "available": []}

    sites: dict[str, Any] = {}
    available: list[str] = []
    for key in BATCH["ordered_site_keys"](data):
        site = _normalize_env_site(data.get(key))
        if site:
            sites[key] = site
            available.append(key)

    return {
        "configured": bool(available),
        "sites": sites,
        "available": available,
        "source": str(ENV_SITES_FILE.relative_to(NEW_DIR)).replace("\\", "/"),
    }


@app.get("/api/env-sites")
def api_env_sites():
    """多环境快捷连接（按 sites.json 已配置站点）。未配置时 configured=false。"""
    payload = _load_env_sites()
    return jsonify({"success": True, **payload})


def _parse_volc_cred_dict(raw: Any) -> dict[str, Any]:
    """从 dict 解析火山 IAM 凭证；无效则返回空字段。"""
    if not isinstance(raw, dict):
        return {"access_key_id": "", "secret_access_key": "", "region": "cn-beijing"}
    ak = str(raw.get("access_key_id") or raw.get("ak") or "").strip()
    sk = str(raw.get("secret_access_key") or raw.get("sk") or "").strip()
    region = str(raw.get("region") or "cn-beijing").strip() or "cn-beijing"
    return {"access_key_id": ak, "secret_access_key": sk, "region": region}


_DEFAULT_AZURE_SUBSCRIPTION = "76c8315b-d084-4f21-8003-cf6365e711bb"


def _parse_subscription_ids(*sources: Any, default: str | None = _DEFAULT_AZURE_SUBSCRIPTION) -> list[str]:
    ids: list[str] = []
    seen: set[str] = set()

    def add(value: Any) -> None:
        if value is None or value is False:
            return
        if isinstance(value, dict):
            add(value.get("id") or value.get("subscription_id") or value.get("guid") or "")
            return
        if isinstance(value, (list, tuple, set)):
            for item in value:
                add(item)
            return
        text = str(value).replace(",", "\n").replace(";", "\n")
        for part in text.splitlines():
            item = part.strip()
            if not item or item.startswith("#"):
                continue
            key = item.lower()
            if key in seen:
                continue
            seen.add(key)
            ids.append(item)

    for src in sources:
        add(src)
    if ids:
        return ids
    fallback = (default or "").strip()
    return [fallback] if fallback else []


def _parse_azure_cred_dict(raw: Any) -> dict[str, Any]:
    """从 dict 解析 Azure 服务主体凭证。"""
    empty_ids = [_DEFAULT_AZURE_SUBSCRIPTION]
    empty = {
        "tenant_id": "",
        "client_id": "",
        "client_secret": "",
        "subscription_id": _DEFAULT_AZURE_SUBSCRIPTION,
        "subscription_ids": list(empty_ids),
    }
    if not isinstance(raw, dict):
        return empty
    tenant = str(raw.get("tenant_id") or raw.get("tenant") or "").strip()
    client_id = str(raw.get("client_id") or raw.get("app_id") or "").strip()
    secret = str(raw.get("client_secret") or raw.get("secret") or "").strip()
    subs = _parse_subscription_ids(
        raw.get("subscription_ids"),
        raw.get("subscriptions"),
        raw.get("subscription_id"),
        raw.get("subscription"),
    )
    return {
        "tenant_id": tenant,
        "client_id": client_id,
        "client_secret": secret,
        "subscription_id": subs[0] if subs else _DEFAULT_AZURE_SUBSCRIPTION,
        "subscription_ids": subs,
    }


def _volc_ready(volc: dict[str, Any]) -> bool:
    return bool(volc.get("access_key_id") and volc.get("secret_access_key"))


def _azure_ready(azure: dict[str, Any]) -> bool:
    return bool(azure.get("tenant_id") and azure.get("client_id") and azure.get("client_secret"))


def _extract_upstream_sections(data: dict[str, Any]) -> tuple[Any, Any]:
    volc_raw = data.get("volc") if isinstance(data.get("volc"), dict) else None
    azure_raw = data.get("azure") if isinstance(data.get("azure"), dict) else None
    upstream = data.get("upstream")
    if isinstance(upstream, dict):
        if isinstance(upstream.get("volc"), dict):
            volc_raw = upstream.get("volc")
        elif volc_raw is None and (upstream.get("access_key_id") or upstream.get("ak")):
            volc_raw = upstream
        if isinstance(upstream.get("azure"), dict):
            azure_raw = upstream.get("azure")
    if volc_raw is None and (data.get("access_key_id") or data.get("ak")):
        volc_raw = data
    if azure_raw is None and data.get("tenant_id") and data.get("client_id"):
        azure_raw = data
    return volc_raw, azure_raw


def _load_upstream_config() -> dict[str, Any]:
    """读取上游凭证：优先 env/upstream.json，其次 env/sites.json。"""
    volc = _parse_volc_cred_dict(None)
    azure = _parse_azure_cred_dict(None)
    source = ""
    error = ""

    def apply_file(data: Any, src: str) -> None:
        nonlocal volc, azure, source
        if not isinstance(data, dict):
            return
        volc_raw, azure_raw = _extract_upstream_sections(data)
        parsed_volc = _parse_volc_cred_dict(volc_raw)
        parsed_azure = _parse_azure_cred_dict(azure_raw)
        if _volc_ready(parsed_volc) and not _volc_ready(volc):
            volc = parsed_volc
            source = src
        if _azure_ready(parsed_azure) and not _azure_ready(azure):
            azure = parsed_azure
            if not source:
                source = src

    if ENV_UPSTREAM_FILE.exists():
        try:
            with ENV_UPSTREAM_FILE.open(encoding="utf-8") as f:
                apply_file(json.load(f), str(ENV_UPSTREAM_FILE.relative_to(NEW_DIR)).replace("\\", "/"))
        except (json.JSONDecodeError, OSError):
            error = "env/upstream.json 无法解析"

    if ENV_SITES_FILE.exists():
        try:
            with ENV_SITES_FILE.open(encoding="utf-8") as f:
                sites_data = json.load(f)
        except json.JSONDecodeError as exc:
            return {
                "configured": False,
                "volc": volc,
                "azure": azure,
                "error": (
                    f"env/sites.json 不是合法 JSON（{exc.msg}，第 {exc.lineno} 行）。"
                    "upstream.volc / upstream.azure 必须写在根对象内。"
                ),
            }
        except OSError:
            sites_data = None
        if isinstance(sites_data, dict):
            apply_file(
                sites_data,
                str(ENV_SITES_FILE.relative_to(NEW_DIR)).replace("\\", "/") + "#upstream",
            )

    return {
        "configured": _volc_ready(volc) or _azure_ready(azure),
        "source": source,
        "error": error,
        "volc": volc,
        "azure": azure,
    }


def _missing_volc_cred_message() -> str:
    """凭证缺失时的说明：example 不会被读取。"""
    cfg = _load_upstream_config()
    if cfg.get("error"):
        return str(cfg["error"])
    if ENV_SITES_FILE.exists() or ENV_UPSTREAM_FILE.exists():
        return (
            "已找到配置文件，但 Access Key ID / Secret 为空。"
            "请在 env/sites.json 的 upstream.volc 填写真实 IAM 密钥（不要用星号占位），或在本页手填。"
        )
    example = ENV_DIR / "sites.example.json"
    if example.exists():
        return (
            "未找到 env/sites.json（程序不会读取 sites.example.json）。"
            "请复制 env/sites.example.json 为 env/sites.json，填写真实的 upstream.volc 后再采集；也可在本页手填。"
        )
    return "请填写 Access Key ID / Secret Access Key，或在 env/sites.json 配置 upstream.volc"


def _missing_azure_cred_message() -> str:
    cfg = _load_upstream_config()
    if cfg.get("error"):
        return str(cfg["error"])
    if ENV_SITES_FILE.exists() or ENV_UPSTREAM_FILE.exists():
        return (
            "已找到配置文件，但 Azure 服务主体不完整。"
            "请在 env/sites.json 的 upstream.azure 填写 tenant_id / client_id / client_secret，或在本页手填。"
        )
    return (
        "请填写 Azure 服务主体（tenant_id、client_id、client_secret），"
        "或在 env/sites.json 配置 upstream.azure。"
        "subscription_ids 可填多个订阅 GUID。"
    )


def _resolve_azure_credentials(body: dict[str, Any]) -> dict[str, Any]:
    file_cfg = _load_upstream_config().get("azure") or {}
    tenant = str(body.get("tenant_id") or body.get("tenant") or file_cfg.get("tenant_id") or "").strip()
    client_id = str(body.get("client_id") or body.get("app_id") or file_cfg.get("client_id") or "").strip()
    secret = str(
        body.get("client_secret") or body.get("secret") or file_cfg.get("client_secret") or ""
    ).strip()
    body_subs = _parse_subscription_ids(
        body.get("subscription_ids"),
        body.get("subscriptions"),
        body.get("subscription_id"),
        body.get("subscription"),
        default="",
    )
    file_subs = list(file_cfg.get("subscription_ids") or []) or _parse_subscription_ids(
        file_cfg.get("subscription_id"),
        default="",
    )
    subs = body_subs or file_subs or [_DEFAULT_AZURE_SUBSCRIPTION]
    return {
        "tenant_id": tenant,
        "client_id": client_id,
        "client_secret": secret,
        "subscription_id": subs[0],
        "subscription_ids": subs,
    }


def _resolve_volc_credentials(body: dict[str, Any]) -> tuple[str, str, str]:
    """优先请求体（页面手填），其次 env/upstream.json 或 sites.json。"""
    file_cfg = _load_upstream_config().get("volc") or {}
    ak = str(body.get("access_key_id") or body.get("ak") or file_cfg.get("access_key_id") or "").strip()
    sk = str(
        body.get("secret_access_key") or body.get("sk") or file_cfg.get("secret_access_key") or ""
    ).strip()
    region = str(body.get("region") or file_cfg.get("region") or "cn-beijing").strip() or "cn-beijing"
    return ak, sk, region


def _run_volc_collect(body: dict[str, Any]) -> tuple[Any, str]:
    """采集火山云。成功返回 (stats, "")，失败返回 (None, message)。"""
    ak, sk, region = _resolve_volc_credentials(body)
    if not ak or not sk:
        return None, _missing_volc_cred_message()
    project_names = body.get("project_names") or body.get("projects") or []
    if isinstance(project_names, str):
        project_names = [x.strip() for x in project_names.replace(",", "\n").splitlines() if x.strip()]
    elif not isinstance(project_names, list):
        project_names = []
    include_api_keys = body.get("include_api_keys")
    if include_api_keys is None:
        include_api_keys = True
    real_token_by_ep: dict = {}
    real_token_file = ""
    if include_api_keys:
        real_path = BATCH["find_real_token_reference"](NEW_DIR / "excel")
        if real_path is not None:
            real_token_by_ep = BATCH["load_real_tokens_by_deploy_id"](real_path)
            real_token_file = real_path.name
    try:
        stats = BATCH["collect_volc_upstream"](
            ak,
            sk,
            region=region,
            project_names=[str(x) for x in project_names],
            include_api_keys=bool(include_api_keys),
            real_token_by_ep=real_token_by_ep or None,
            real_token_file=real_token_file,
        )
    except Exception as exc:  # noqa: BLE001
        return None, _user_facing_error(exc)
    return stats, ""


def _run_azure_collect(body: dict[str, Any]) -> tuple[Any, str]:
    """采集 Azure OpenAI。成功返回 (stats, "")，失败返回 (None, message)。"""
    cred = _resolve_azure_credentials(body)
    if not (cred["tenant_id"] and cred["client_id"] and cred["client_secret"]):
        return None, _missing_azure_cred_message()
    include_api_keys = body.get("include_api_keys")
    if include_api_keys is None:
        include_api_keys = True
    try:
        stats = BATCH["collect_azure_upstream"](
            cred["tenant_id"],
            cred["client_id"],
            cred["client_secret"],
            subscription_ids=cred.get("subscription_ids") or [cred["subscription_id"]],
            include_api_keys=bool(include_api_keys),
        )
    except Exception as exc:  # noqa: BLE001
        return None, _user_facing_error(exc)
    return stats, ""


def _volc_collect_payload(stats: Any) -> dict[str, Any]:
    return {
        "endpoints": getattr(stats, "endpoints", 0),
        "projects_ok": getattr(stats, "projects_ok", 0),
        "projects_failed": getattr(stats, "projects_failed", 0),
        "project_results": getattr(stats, "project_results", []),
        "errors": getattr(stats, "errors", []),
        "preview": (getattr(stats, "rows", None) or [])[:8],
        "headers": list(BATCH["UPSTREAM_HEADERS"]),
        "sheet": BATCH["SHEET_VOLC"],
        "token_overlay": getattr(stats, "token_overlay", 0),
        "token_overlay_file": getattr(stats, "token_overlay_file", "") or "",
    }


def _azure_collect_payload(stats: Any) -> dict[str, Any]:
    return {
        "deployments": getattr(stats, "deployments", 0),
        "accounts_ok": getattr(stats, "accounts_ok", 0),
        "accounts_failed": getattr(stats, "accounts_failed", 0),
        "subscriptions_ok": getattr(stats, "subscriptions_ok", 0),
        "subscriptions_failed": getattr(stats, "subscriptions_failed", 0),
        "account_results": getattr(stats, "account_results", []),
        "subscription_results": getattr(stats, "subscription_results", []),
        "errors": getattr(stats, "errors", []),
        "preview": (getattr(stats, "rows", None) or [])[:8],
        "headers": list(BATCH["AZURE_HEADERS"]),
        "sheet": BATCH["SHEET_AZURE"],
    }


def _env_site_payloads() -> list[dict[str, Any]]:
    """从 env/sites.json 取出已配置站点，供采集（含账密，TOTP 由 parse_sites 补齐）。"""
    _ensure_batch()
    if not ENV_SITES_FILE.exists():
        return []
    try:
        data = json.loads(ENV_SITES_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
    if not isinstance(data, dict):
        return []
    rows: list[dict[str, Any]] = []
    for env in BATCH["ordered_site_keys"](data):
        item = data.get(env)
        if not isinstance(item, dict):
            continue
        if not str(item.get("base_url") or "").strip():
            continue
        row = dict(item)
        row["env"] = env
        row.setdefault("label", env)
        row.setdefault("cluster", BATCH["cluster_label"](env))
        rows.append(row)
    return rows


def _overview_include_keys(body: dict[str, Any]) -> bool:
    """⑥ 默认含渠道密钥；仅当请求显式传入 false 时关闭。"""
    if "include_keys" in body:
        return bool(body.get("include_keys"))
    if "include_channel_keys" in body:
        return bool(body.get("include_channel_keys"))
    return True


def _allow_latest(body: dict[str, Any] | None = None) -> bool:
    text = str(request.args.get("allow_latest") or "").strip().lower()
    if text in {"1", "true", "yes", "on"}:
        return True
    return bool((body or {}).get("allow_latest"))


def _optional_source_excel(raw: Any) -> Path | None:
    text = str(raw or "").strip()
    if not text:
        return None
    _ensure_batch()
    return BATCH["resolve_excel_path"](NEW_DIR, text)


def _excel_query_path(*keys: str, fallback: Path | None = None) -> Path | None:
    for key in keys:
        raw = request.args.get(key)
        if raw:
            return BATCH["resolve_excel_path"](NEW_DIR, raw)
    return fallback


def _merge_overview_sites(body: dict[str, Any]) -> list[dict[str, Any]]:
    """优先用请求里的站点（可带 otp_code）；否则用 env/sites.json，并按 env 叠验证码。"""
    raw = [item for item in (body.get("sites") or []) if isinstance(item, dict)]
    if any(str(item.get("base_url") or "").strip() for item in raw):
        return raw
    otp_by_env = {
        str(item.get("env") or "").strip().lower(): str(item.get("otp_code") or "").strip()
        for item in raw
        if str(item.get("otp_code") or "").strip()
    }
    rows = _env_site_payloads()
    for row in rows:
        otp = otp_by_env.get(str(row.get("env") or "").lower())
        if otp:
            row["otp_code"] = otp
    return rows


def _fill_overview_channel_keys(
    excel_path: Path,
    sites: list[Any],
    warnings: list[str],
) -> list[dict[str, Any]]:
    """对已生成的总览文件按环境补密钥；单站失败不打断其它环境。"""
    fills: list[dict[str, Any]] = []
    for site in sites:
        env = str(getattr(site, "env", "") or "")
        label = str(getattr(site, "label", "") or env or getattr(site, "base_url", "") or "站点")
        try:
            result, _saved = BATCH["fill_missing_channel_keys"](
                site=site,
                root_dir=NEW_DIR,
                excel_path=excel_path,
            )
            fills.append(result)
            if result.get("message"):
                warnings.append(str(result.get("message")))
            for warn in result.get("warnings") or []:
                warnings.append(f"[{label}] {warn}")
        except Exception as exc:  # noqa: BLE001
            item = {
                "env": env,
                "keys_fetched": 0,
                "keys_pending": -1,
                "message": str(exc),
                "error": str(exc),
            }
            fills.append(item)
            warnings.append(f"[{label}] 获取密钥：{exc}")
    try:
        BATCH["refresh_overview_index"](excel_path)
    except Exception:  # noqa: BLE001
        pass
    return fills


def _collect_gateway_workbook(body: dict[str, Any]) -> tuple[Path | None, str, Any]:
    """现场采集③ 网关表到临时文件；失败返回 (None, err, stats)。⑥ 默认含密钥。"""
    raw_sites = _merge_overview_sites(body)
    sites = BATCH["parse_summary_sites"](raw_sites or [])
    if not sites:
        return None, "未配置 NA 站点。请填写 env/sites.json 的 test/uat/prod，或先在③采集一份网关表。", None
    include_keys = _overview_include_keys(body)
    tmp = _ensure_excel_dir() / f"_overview_gw_{datetime.now().strftime('%Y%m%d%H%M%S')}.xlsx"
    try:
        stats, saved = BATCH["run_data_summary_collect"](
            sites=sites,
            excel_path=BATCH["default_excel_path"](NEW_DIR),
            include_keys=include_keys,
            output_path=tmp,
        )
    except Exception as exc:  # noqa: BLE001
        if tmp.exists():
            tmp.unlink()
        return None, _user_facing_error(exc), None
    if getattr(stats, "sites_ok", 0) == 0:
        if tmp.exists():
            tmp.unlink()
        detail = "；".join(list(getattr(stats, "errors", None) or [])[:3])
        return None, detail or "网关站点采集失败", stats
    return Path(saved), "", stats


@app.get("/api/upstream/config")
def api_upstream_config():
    """上游凭证摘要（Secret 脱敏）。"""
    cfg = _load_upstream_config()
    volc = dict(cfg.get("volc") or {})
    azure = dict(cfg.get("azure") or {})
    sk = str(volc.get("secret_access_key") or "")
    azure_secret = str(azure.get("client_secret") or "")
    volc_public = {
        "access_key_id": str(volc.get("access_key_id") or ""),
        "secret_access_key": "***" if sk else "",
        "has_secret": bool(sk),
        "region": str(volc.get("region") or "cn-beijing"),
    }
    azure_subs = list(azure.get("subscription_ids") or []) or [
        str(azure.get("subscription_id") or _DEFAULT_AZURE_SUBSCRIPTION)
    ]
    azure_public = {
        "tenant_id": str(azure.get("tenant_id") or ""),
        "client_id": str(azure.get("client_id") or ""),
        "client_secret": "***" if azure_secret else "",
        "has_secret": bool(azure_secret),
        "subscription_id": azure_subs[0],
        "subscription_ids": azure_subs,
        "ready": _azure_ready(azure),
    }
    return jsonify(
        {
            "success": True,
            "configured": bool(cfg.get("configured")),
            "source": cfg.get("source") or "",
            "error": cfg.get("error") or "",
            "volc": volc_public,
            "azure": azure_public,
        }
    )


@app.get("/api/upstream/volc/info")
def api_upstream_volc_info():
    _ensure_batch()
    excel_path = BATCH["latest_upstream_excel_path"](NEW_DIR)
    exists = bool(excel_path and excel_path.exists())
    stats = BATCH["upstream_workbook_stats"](excel_path) if exists else {"rows": 0, "sheet": BATCH["SHEET_VOLC"]}
    return jsonify(
        {
            "success": True,
            "data": {
                "filename": excel_path.name if exists else "",
                "path": _rel_to_root(excel_path) if exists else "",
                "exists": exists,
                "stem": BATCH["UPSTREAM_EXCEL_STEM"],
                "sheet": BATCH["SHEET_VOLC"],
                "headers": list(BATCH["UPSTREAM_HEADERS"]),
                "summary": stats,
                "note": "与③数据汇总的 ai网关令牌及渠道列表_*.xlsx 相互独立，互不合并。",
            },
        }
    )


@app.post("/api/upstream/volc/test")
def api_upstream_volc_test():
    _ensure_batch()
    body = request.get_json(silent=True) or {}
    ak, sk, region = _resolve_volc_credentials(body)
    if not ak or not sk:
        return jsonify(
            {
                "success": False,
                "message": _missing_volc_cred_message(),
            }
        ), 400
    try:
        data = BATCH["test_volc_connection"](ak, sk, region=region)
        return jsonify(
            {
                "success": True,
                "message": f"连接成功：共 {data.get('project_count', 0)} 个项目",
                "data": data,
            }
        )
    except Exception as exc:  # noqa: BLE001
        return jsonify({"success": False, "message": _user_facing_error(exc)}), 400


@app.post("/api/upstream/volc/collect")
def api_upstream_volc_collect():
    """采集火山云推理接入点，写入独立 Excel（不并入 AI 网关汇总表）。"""
    _ensure_batch()
    body = request.get_json(silent=True) or {}
    stats, err = _run_volc_collect(body)
    if err:
        return jsonify({"success": False, "message": err}), 400
    if not stats.rows:
        return jsonify(
            {
                "success": False,
                "message": "未采集到接入点" + ("：" + "；".join(stats.errors[:3]) if stats.errors else ""),
                "data": {
                    "projects_ok": stats.projects_ok,
                    "projects_failed": stats.projects_failed,
                    "endpoints": 0,
                    "project_results": stats.project_results,
                    "errors": stats.errors,
                },
            }
        ), 400

    excel_path = BATCH["build_upstream_path"](NEW_DIR)
    BATCH["save_upstream_workbook"](excel_path, stats.rows)
    rel = _rel_to_root(excel_path)
    ok = stats.projects_failed == 0
    extra = ""
    if stats.token_overlay:
        extra += f"；已按{stats.token_overlay_file or '火山真实数据'}对齐 token {stats.token_overlay} 条"
    if stats.errors:
        extra += f"；附带警告 {len(stats.errors)} 条"
    payload = _volc_collect_payload(stats)
    payload["file"] = rel
    payload["filename"] = excel_path.name
    return jsonify(
        {
            "success": ok,
            "message": f"已写入 {rel}：{stats.endpoints} 条接入点（项目成功 {stats.projects_ok}，失败 {stats.projects_failed}）{extra}",
            "data": payload,
        }
    )


@app.get("/api/upstream/volc/download")
def api_upstream_volc_download():
    _ensure_batch()
    try:
        excel_path = _excel_query_path("file", "id", fallback=BATCH["latest_upstream_excel_path"](NEW_DIR))
    except (ValueError, FileNotFoundError) as exc:
        return jsonify({"success": False, "message": str(exc)}), 400
    if not excel_path or not excel_path.exists():
        return jsonify({"success": False, "message": "尚未生成上游 Excel，请先采集火山云"}), 404
    return _send_excel_attachment(excel_path)


@app.get("/api/upstream/bill/info")
def api_upstream_bill_info():
    _ensure_batch()
    excel_path = BATCH["latest_bill_excel_path"](NEW_DIR)
    exists = bool(excel_path and excel_path.exists())
    stats = BATCH["bill_workbook_stats"](excel_path) if exists else {"rows": 0, "sheet": BATCH["SHEET_BILL_DAY"]}
    return jsonify(
        {
            "success": True,
            "data": {
                "filename": excel_path.name if exists else "",
                "path": _rel_to_root(excel_path) if exists else "",
                "exists": exists,
                "stem": BATCH["BILL_EXCEL_STEM"],
                "sheet": BATCH["SHEET_BILL_DAY"],
                "default_period": BATCH["default_bill_period"](),
                "summary": stats,
                "note": "使用与上游信息相同的 IAM Access Key 调费用中心。导出两张表：按天、按月。",
            },
        }
    )


@app.post("/api/upstream/bill/collect")
def api_upstream_bill_collect():
    _ensure_batch()
    body = request.get_json(silent=True) or {}
    ak, sk, region = _resolve_volc_credentials(body)
    if not ak or not sk:
        return jsonify({"success": False, "message": _missing_volc_cred_message()}), 400
    try:
        periods = BATCH["bill_periods_from_payload"](body)
    except ValueError as exc:
        return jsonify({"success": False, "message": str(exc)}), 400
    items: list[dict[str, Any]] = []
    failed: list[dict[str, str]] = []
    last_saved = None
    last_stats = None
    for period in periods:
        try:
            saved, stats = BATCH["run_volc_bill_export"](
                NEW_DIR,
                ak,
                sk,
                region=region,
                bill_period=period,
            )
        except ValueError as exc:
            failed.append({"bill_period": period, "error": str(exc)})
            continue
        except BATCH["VolcOpenAPIError"] as exc:
            failed.append({"bill_period": period, "error": str(exc)})
            continue
        except Exception as exc:  # noqa: BLE001
            failed.append({"bill_period": period, "error": _user_facing_error(exc)})
            continue
        last_saved, last_stats = saved, stats
        skip_n = int(stats.skipped_empty_or_default or 0)
        items.append(
            {
                "path": _rel_to_root(saved),
                "filename": saved.name,
                "bill_period": stats.bill_period,
                "source_action": stats.source_action,
                "split_used": stats.split_used,
                "day_rows": stats.day_rows,
                "month_rows": stats.month_rows,
                "raw_count": stats.raw_count,
                "skipped_empty_or_default": skip_n,
                "errors": stats.errors,
            }
        )
    if not items or last_saved is None or last_stats is None:
        detail = "；".join(f"{row['bill_period']}：{row['error']}" for row in failed) or "未采集到账单"
        return jsonify({"success": False, "message": detail, "data": {"failed": failed}}), 400
    stats = last_stats
    rel = _rel_to_root(last_saved)
    extra = ""
    if stats.errors:
        extra = "。" + " ".join(stats.errors)
    skip_n = int(stats.skipped_empty_or_default or 0)
    skip_note = f"，已排除空项目/默认项目 {skip_n} 条" if skip_n else ""
    names = "、".join(row["filename"] for row in items)
    fail_note = f"；失败 {len(failed)} 个月" if failed else ""
    return jsonify(
        {
            "success": True,
            "message": (
                f"已写入 {len(items)} 份（每月一份）：{names}。最新 {rel}：账期 {stats.bill_period}，"
                f"按天 {stats.day_rows} 行、按月 {stats.month_rows} 行（{stats.source_action}）{skip_note}{extra}{fail_note}"
            ),
            "data": {
                "path": rel,
                "filename": last_saved.name,
                "bill_period": stats.bill_period,
                "bill_periods": [row["bill_period"] for row in items],
                "files": items,
                "failed": failed,
                "source_action": stats.source_action,
                "split_used": stats.split_used,
                "day_rows": stats.day_rows,
                "month_rows": stats.month_rows,
                "raw_count": stats.raw_count,
                "skipped_empty_or_default": skip_n,
                "preview_day": stats.rows_day[:20],
                "preview_month": stats.rows_month[:20],
                "headers": list(BATCH["excel_cost_headers"](list(BATCH["VOLC_BILL_HEADERS"]))),
                "errors": stats.errors,
            },
        }
    )


@app.get("/api/upstream/bill/download")
def api_upstream_bill_download():
    _ensure_batch()
    try:
        excel_path = _excel_query_path("file", "id", fallback=BATCH["latest_bill_excel_path"](NEW_DIR))
    except (ValueError, FileNotFoundError) as exc:
        return jsonify({"success": False, "message": str(exc)}), 400
    if not excel_path or not excel_path.exists():
        return jsonify({"success": False, "message": "尚未生成上游账单 Excel，请先采集"}), 404
    return _send_excel_attachment(excel_path)


@app.get("/api/upstream/azure/bill/info")
def api_upstream_azure_bill_info():
    _ensure_batch()
    excel_path = BATCH["latest_azure_bill_excel_path"](NEW_DIR)
    exists = bool(excel_path and excel_path.exists())
    stats = BATCH["azure_bill_workbook_stats"](excel_path) if exists else {"rows": 0, "sheet": BATCH["SHEET_BILL_DAY"]}
    return jsonify(
        {
            "success": True,
            "data": {
                "filename": excel_path.name if exists else "",
                "path": _rel_to_root(excel_path) if exists else "",
                "exists": exists,
                "stem": BATCH["AZURE_BILL_EXCEL_STEM"],
                "sheet": BATCH["SHEET_BILL_DAY"],
                "default_period": BATCH["default_bill_period"](),
                "summary": stats,
                "headers": list(BATCH["excel_cost_headers"](list(BATCH["AZURE_BILL_HEADERS"]))),
                "note": "使用与上游信息相同的 Entra 服务主体调 Cost Management。分组依据资源；导出按天、按月。",
            },
        }
    )


@app.post("/api/upstream/azure/bill/collect")
def api_upstream_azure_bill_collect():
    _ensure_batch()
    body = request.get_json(silent=True) or {}
    cred = _resolve_azure_credentials(body)
    if not (cred["tenant_id"] and cred["client_id"] and cred["client_secret"]):
        return jsonify({"success": False, "message": _missing_azure_cred_message()}), 400
    try:
        periods = BATCH["bill_periods_from_payload"](body)
    except ValueError as exc:
        return jsonify({"success": False, "message": str(exc)}), 400
    items: list[dict[str, Any]] = []
    failed: list[dict[str, str]] = []
    last_saved = None
    last_stats = None
    for period in periods:
        try:
            saved, stats = BATCH["run_azure_bill_export"](
                NEW_DIR,
                cred["tenant_id"],
                cred["client_id"],
                cred["client_secret"],
                subscription_ids=cred.get("subscription_ids") or [cred["subscription_id"]],
                bill_period=period,
            )
        except ValueError as exc:
            failed.append({"bill_period": period, "error": str(exc)})
            continue
        except BATCH["AzureARMError"] as exc:
            failed.append({"bill_period": period, "error": str(exc)})
            continue
        except Exception as exc:  # noqa: BLE001
            failed.append({"bill_period": period, "error": _user_facing_error(exc)})
            continue
        last_saved, last_stats = saved, stats
        items.append(
            {
                "path": _rel_to_root(saved),
                "filename": saved.name,
                "bill_period": stats.bill_period,
                "source_action": stats.source_action,
                "day_rows": stats.day_rows,
                "month_rows": stats.month_rows,
                "raw_count": stats.raw_count,
                "currencies": stats.currencies,
                "errors": stats.errors,
            }
        )
    if not items or last_saved is None or last_stats is None:
        detail = "；".join(f"{row['bill_period']}：{row['error']}" for row in failed) or "未采集到账单"
        return jsonify({"success": False, "message": detail, "data": {"failed": failed}}), 400
    stats = last_stats
    rel = _rel_to_root(last_saved)
    extra = ""
    if stats.errors:
        extra = "。" + " ".join(stats.errors)
    currency = "、".join(stats.currencies) if stats.currencies else "CNY"
    names = "、".join(row["filename"] for row in items)
    fail_note = f"；失败 {len(failed)} 个月" if failed else ""
    return jsonify(
        {
            "success": True,
            "message": (
                f"已写入 {len(items)} 份（每月一份）：{names}。最新 {rel}：账期 {stats.bill_period}，"
                f"按天 {stats.day_rows} 行、按月 {stats.month_rows} 行（{stats.source_action}，{currency}）{extra}{fail_note}"
            ),
            "data": {
                "path": rel,
                "filename": last_saved.name,
                "bill_period": stats.bill_period,
                "bill_periods": [row["bill_period"] for row in items],
                "files": items,
                "failed": failed,
                "source_action": stats.source_action,
                "day_rows": stats.day_rows,
                "month_rows": stats.month_rows,
                "raw_count": stats.raw_count,
                "currencies": stats.currencies,
                "preview_day": stats.rows_day[:20],
                "preview_month": stats.rows_month[:20],
                "headers": list(BATCH["excel_cost_headers"](list(BATCH["AZURE_BILL_HEADERS"]))),
                "errors": stats.errors,
            },
        }
    )


@app.get("/api/upstream/azure/bill/download")
def api_upstream_azure_bill_download():
    _ensure_batch()
    try:
        excel_path = _excel_query_path("file", "id", fallback=BATCH["latest_azure_bill_excel_path"](NEW_DIR))
    except (ValueError, FileNotFoundError) as exc:
        return jsonify({"success": False, "message": str(exc)}), 400
    if not excel_path or not excel_path.exists():
        return jsonify({"success": False, "message": "尚未生成 Azure 账单 Excel，请先采集"}), 404
    return _send_excel_attachment(excel_path)


def _run_volc_bill_collect(body: dict[str, Any], period: str) -> tuple[Any, str]:
    ak, sk, region = _resolve_volc_credentials(body)
    if not ak or not sk:
        return None, _missing_volc_cred_message()
    try:
        stats = BATCH["collect_volc_bills"](ak, sk, region=region, bill_period=period)
    except BATCH["VolcOpenAPIError"] as exc:
        return None, str(exc)
    except Exception as exc:  # noqa: BLE001
        return None, _user_facing_error(exc)
    return stats, ""


def _run_azure_bill_collect(body: dict[str, Any], period: str) -> tuple[Any, str]:
    cred = _resolve_azure_credentials(body)
    if not (cred["tenant_id"] and cred["client_id"] and cred["client_secret"]):
        return None, _missing_azure_cred_message()
    try:
        stats = BATCH["collect_azure_bills"](
            cred["tenant_id"],
            cred["client_id"],
            cred["client_secret"],
            subscription_ids=cred.get("subscription_ids") or [cred["subscription_id"]],
            bill_period=period,
        )
    except BATCH["AzureARMError"] as exc:
        return None, str(exc)
    except Exception as exc:  # noqa: BLE001
        return None, _user_facing_error(exc)
    return stats, ""


@app.get("/api/upstream/bill/combined/info")
def api_upstream_bill_combined_info():
    _ensure_batch()
    excel_path = BATCH["latest_combined_bill_excel_path"](NEW_DIR)
    exists = bool(excel_path and excel_path.exists())
    stats = (
        BATCH["combined_bill_workbook_stats"](excel_path)
        if exists
        else {"rows": 0, "sheet": "", "sheets": {}, "total_rows": 0}
    )
    return jsonify(
        {
            "success": True,
            "data": {
                "filename": excel_path.name if exists else "",
                "path": _rel_to_root(excel_path) if exists else "",
                "exists": exists,
                "stem": BATCH["BILL_COMBINED_STEM"],
                "sheet": stats.get("sheet") or "",
                "sheets": [
                    BATCH["SHEET_BILL_VOLC_DAY"],
                    BATCH["SHEET_BILL_VOLC_MONTH"],
                    BATCH["SHEET_BILL_AZURE_DAY"],
                    BATCH["SHEET_BILL_AZURE_MONTH"],
                ],
                "default_period": BATCH["default_bill_period"](),
                "headers_volc": list(BATCH["excel_cost_headers"](list(BATCH["VOLC_BILL_HEADERS"]))),
                "headers_azure": list(BATCH["excel_cost_headers"](list(BATCH["AZURE_BILL_HEADERS"]))),
                "summary": stats,
                "note": "同一工作簿四张费用表：火山云按天/按月、Azure 按天/按月。费用列标注 ¥，末行 SUM。",
            },
        }
    )


def _collect_combined_bill_one_month(body: dict[str, Any], period: str) -> tuple[dict[str, Any] | None, str | None]:
    """采集单月火山+Azure，写入一份汇总 Excel。成功返回 (data, None)，失败返回 (None, message)。"""
    volc_stats, volc_err = _run_volc_bill_collect(body, period)
    azure_stats, azure_err = _run_azure_bill_collect(body, period)
    if volc_err and azure_err:
        return None, f"两侧凭证均不可用。火山：{volc_err} Azure：{azure_err}"

    volc_day = list(getattr(volc_stats, "rows_day", None) or []) if volc_stats is not None else []
    azure_day = list(getattr(azure_stats, "rows_day", None) or []) if azure_stats is not None else []
    if not volc_day and not azure_day:
        parts = []
        if volc_err:
            parts.append(f"火山：{volc_err}")
        elif volc_stats is not None:
            extra = "；".join((volc_stats.errors or [])[:3])
            parts.append("火山未采集到账单" + (f"（{extra}）" if extra else ""))
        if azure_err:
            parts.append(f"Azure：{azure_err}")
        elif azure_stats is not None:
            extra = "；".join((azure_stats.errors or [])[:3])
            parts.append("Azure 未采集到账单" + (f"（{extra}）" if extra else ""))
        return None, "未写入汇总表：" + "；".join(parts) if parts else "未采集到任何账单数据"

    excel_path = BATCH["build_combined_bill_path"](NEW_DIR, bill_period=period)
    BATCH["save_combined_bill_workbook"](excel_path, volc_stats, azure_stats)
    rel = _rel_to_root(excel_path)
    warnings: list[str] = []
    if volc_err:
        warnings.append(f"火山未写入数据：{volc_err}")
    if azure_err:
        warnings.append(f"Azure 未写入数据：{azure_err}")
    if volc_stats is not None:
        warnings.extend(list(volc_stats.errors or []))
    if azure_stats is not None:
        warnings.extend(list(azure_stats.errors or []))
    volc_n = len(volc_day)
    azure_n = len(azure_day)
    volc_m = len(list(getattr(volc_stats, "rows_month", None) or [])) if volc_stats is not None else 0
    azure_m = len(list(getattr(azure_stats, "rows_month", None) or [])) if azure_stats is not None else 0
    volc_ok = volc_stats is not None and not volc_err
    azure_ok = azure_stats is not None and not azure_err
    return {
        "file": rel,
        "filename": excel_path.name,
        "bill_period": period,
        "both_ok": bool(volc_ok and azure_ok),
        "sheets": [
            BATCH["SHEET_BILL_VOLC_DAY"],
            BATCH["SHEET_BILL_VOLC_MONTH"],
            BATCH["SHEET_BILL_AZURE_DAY"],
            BATCH["SHEET_BILL_AZURE_MONTH"],
        ],
        "volc_day_rows": volc_n,
        "volc_month_rows": volc_m,
        "azure_day_rows": azure_n,
        "azure_month_rows": azure_m,
        "volc_error": volc_err,
        "azure_error": azure_err,
        "errors": warnings,
        "headers_volc": list(BATCH["excel_cost_headers"](list(BATCH["VOLC_BILL_HEADERS"]))),
        "headers_azure": list(BATCH["excel_cost_headers"](list(BATCH["AZURE_BILL_HEADERS"]))),
        "preview_volc_day": volc_day[:20],
        "preview_volc_month": (list(getattr(volc_stats, "rows_month", None) or [])[:20] if volc_stats else []),
        "preview_azure_day": azure_day[:20],
        "preview_azure_month": (list(getattr(azure_stats, "rows_month", None) or [])[:20] if azure_stats else []),
    }, None


@app.post("/api/upstream/bill/collect-all")
def api_upstream_bill_collect_all():
    """按账期逐月采集火山云 + Azure，每月各写一份「上游账单_汇总」Excel。"""
    _ensure_batch()
    body = request.get_json(silent=True) or {}
    try:
        periods = BATCH["bill_periods_from_payload"](body)
    except ValueError as exc:
        return jsonify({"success": False, "message": str(exc)}), 400

    files: list[dict[str, Any]] = []
    failed: list[dict[str, str]] = []
    last_ok: dict[str, Any] | None = None
    for period in periods:
        data, err = _collect_combined_bill_one_month(body, period)
        if err:
            failed.append({"bill_period": period, "error": err})
            continue
        files.append(
            {
                "file": data["file"],
                "filename": data["filename"],
                "bill_period": period,
                "both_ok": data["both_ok"],
                "volc_day_rows": data["volc_day_rows"],
                "volc_month_rows": data["volc_month_rows"],
                "azure_day_rows": data["azure_day_rows"],
                "azure_month_rows": data["azure_month_rows"],
                "volc_error": data["volc_error"],
                "azure_error": data["azure_error"],
            }
        )
        last_ok = data

    if not files or last_ok is None:
        first = failed[0]["error"] if failed else "未采集到任何账单数据"
        return jsonify(
            {
                "success": False,
                "message": first,
                "data": {"bill_periods": periods, "failed": failed},
            }
        ), 400

    n_fail = len(failed)
    names = "、".join(item["filename"] for item in files)
    msg = f"已写入 {len(files)} 份汇总 Excel（每月一份）：{names}"
    if n_fail:
        msg += f"；失败 {n_fail} 个月"
    last_warnings = list(last_ok.get("errors") or [])
    if last_warnings:
        msg += f"；最近一月附带警告 {len(last_warnings)} 条"
    all_both_ok = all(bool(item.get("both_ok")) for item in files)
    return jsonify(
        {
            "success": n_fail == 0 and all_both_ok,
            "message": msg,
            "data": {
                **last_ok,
                "file": last_ok.get("file"),
                "filename": last_ok.get("filename"),
                "bill_period": last_ok.get("bill_period"),
                "bill_periods": [item["bill_period"] for item in files],
                "files": files,
                "failed": failed,
            },
        }
    )


@app.get("/api/upstream/bill/combined/download")
def api_upstream_bill_combined_download():
    _ensure_batch()
    try:
        excel_path = _excel_query_path("file", "id", fallback=BATCH["latest_combined_bill_excel_path"](NEW_DIR))
    except (ValueError, FileNotFoundError) as exc:
        return jsonify({"success": False, "message": str(exc)}), 400
    if not excel_path or not excel_path.exists():
        return jsonify({"success": False, "message": "尚未生成汇总账单 Excel，请先点「一键采集全部账单」"}), 404
    return _send_excel_attachment(excel_path)


@app.get("/api/upstream/azure/info")
def api_upstream_azure_info():
    _ensure_batch()
    excel_path = BATCH["latest_azure_upstream_excel_path"](NEW_DIR)
    exists = bool(excel_path and excel_path.exists())
    stats = BATCH["upstream_workbook_stats"](excel_path) if exists else {"rows": 0, "sheet": BATCH["SHEET_AZURE"]}
    return jsonify(
        {
            "success": True,
            "data": {
                "filename": excel_path.name if exists else "",
                "path": _rel_to_root(excel_path) if exists else "",
                "exists": exists,
                "stem": BATCH["UPSTREAM_AZURE_STEM"],
                "sheet": BATCH["SHEET_AZURE"],
                "headers": list(BATCH["AZURE_HEADERS"]),
                "summary": stats,
                "subscription_id": _DEFAULT_AZURE_SUBSCRIPTION,
                "subscription_ids": [_DEFAULT_AZURE_SUBSCRIPTION],
                "note": "与③数据汇总、⑤火山云 Excel 相互独立。",
            },
        }
    )


@app.post("/api/upstream/azure/test")
def api_upstream_azure_test():
    _ensure_batch()
    cred = _resolve_azure_credentials(request.get_json(silent=True) or {})
    if not (cred["tenant_id"] and cred["client_id"] and cred["client_secret"]):
        return jsonify({"success": False, "message": _missing_azure_cred_message()}), 400
    try:
        data = BATCH["test_azure_connection"](
            cred["tenant_id"],
            cred["client_id"],
            cred["client_secret"],
            subscription_ids=cred.get("subscription_ids") or [cred["subscription_id"]],
        )
        sub_n = len(data.get("subscription_ids") or []) or 1
        failed = [item for item in (data.get("subscription_results") or []) if not item.get("success")]
        msg = f"连接成功：{sub_n} 个订阅，共 {data.get('account_count', 0)} 个 Azure OpenAI 账号"
        if failed:
            msg += f"（其中 {len(failed)} 个订阅失败）"
        return jsonify(
            {
                "success": True,
                "message": msg,
                "data": data,
            }
        )
    except Exception as exc:  # noqa: BLE001
        return jsonify({"success": False, "message": _user_facing_error(exc)}), 400


@app.post("/api/upstream/azure/collect")
def api_upstream_azure_collect():
    """采集 Azure OpenAI 部署，写入独立 Excel。"""
    _ensure_batch()
    body = request.get_json(silent=True) or {}
    stats, err = _run_azure_collect(body)
    if err:
        return jsonify({"success": False, "message": err}), 400
    if not stats.rows:
        return jsonify(
            {
                "success": False,
                "message": "未采集到部署" + ("：" + "；".join(stats.errors[:3]) if stats.errors else ""),
                "data": {
                    "accounts_ok": stats.accounts_ok,
                    "accounts_failed": stats.accounts_failed,
                    "deployments": 0,
                    "subscriptions_ok": stats.subscriptions_ok,
                    "subscriptions_failed": stats.subscriptions_failed,
                    "account_results": stats.account_results,
                    "subscription_results": stats.subscription_results,
                    "errors": stats.errors,
                },
            }
        ), 400
    excel_path = BATCH["build_azure_upstream_path"](NEW_DIR)
    BATCH["save_upstream_workbook"](
        excel_path,
        stats.rows,
        headers=list(BATCH["AZURE_HEADERS"]),
        sheet_name=BATCH["SHEET_AZURE"],
    )
    rel = _rel_to_root(excel_path)
    ok = stats.accounts_failed == 0 and stats.subscriptions_failed == 0
    extra = f"；附带警告 {len(stats.errors)} 条" if stats.errors else ""
    payload = _azure_collect_payload(stats)
    payload["file"] = rel
    payload["filename"] = excel_path.name
    return jsonify(
        {
            "success": ok,
            "message": (
                f"已写入 {rel}：{stats.deployments} 条部署"
                f"（订阅成功 {stats.subscriptions_ok}，失败 {stats.subscriptions_failed}；"
                f"账号成功 {stats.accounts_ok}，失败 {stats.accounts_failed}）{extra}"
            ),
            "data": payload,
        }
    )


@app.get("/api/upstream/azure/download")
def api_upstream_azure_download():
    _ensure_batch()
    try:
        excel_path = _excel_query_path("file", "id", fallback=BATCH["latest_azure_upstream_excel_path"](NEW_DIR))
    except (ValueError, FileNotFoundError) as exc:
        return jsonify({"success": False, "message": str(exc)}), 400
    if not excel_path or not excel_path.exists():
        return jsonify({"success": False, "message": "尚未生成 Azure 上游 Excel，请先采集"}), 404
    return _send_excel_attachment(excel_path)


@app.get("/api/upstream/info")
def api_upstream_combined_info():
    """最新一份「火山云 + Azure」汇总 Excel 摘要。"""
    _ensure_batch()
    excel_path = BATCH["latest_combined_upstream_excel_path"](NEW_DIR)
    exists = bool(excel_path and excel_path.exists())
    stats = (
        BATCH["upstream_workbook_stats"](excel_path)
        if exists
        else {"rows": 0, "sheet": f"{BATCH['SHEET_VOLC']} + {BATCH['SHEET_AZURE']}", "sheets": {}, "total_rows": 0}
    )
    sheets = dict(stats.get("sheets") or {})
    return jsonify(
        {
            "success": True,
            "data": {
                "filename": excel_path.name if exists else "",
                "path": _rel_to_root(excel_path) if exists else "",
                "exists": exists,
                "stem": BATCH["UPSTREAM_COMBINED_STEM"],
                "sheet": stats.get("sheet") or "",
                "sheets": [BATCH["SHEET_VOLC"], BATCH["SHEET_AZURE"]],
                "volc_rows": int(sheets.get(BATCH["SHEET_VOLC"]) or 0),
                "azure_rows": int(sheets.get(BATCH["SHEET_AZURE"]) or 0),
                "headers_volc": list(BATCH["UPSTREAM_HEADERS"]),
                "headers_azure": list(BATCH["AZURE_HEADERS"]),
                "summary": stats,
                "note": "同一工作簿两张工作表：火山云、Azure OpenAI。与③ 网关汇总相互独立。",
            },
        }
    )


@app.post("/api/upstream/collect")
def api_upstream_collect_all():
    """一次采集火山云 + Azure OpenAI，写入同一工作簿的两张工作表。"""
    _ensure_batch()
    body = request.get_json(silent=True) or {}
    volc_stats, volc_err = _run_volc_collect(body)
    azure_stats, azure_err = _run_azure_collect(body)
    if volc_err and azure_err:
        return jsonify(
            {
                "success": False,
                "message": f"两侧凭证均不可用。火山：{volc_err} Azure：{azure_err}",
                "data": {"volc_error": volc_err, "azure_error": azure_err},
            }
        ), 400

    volc_rows = list(getattr(volc_stats, "rows", None) or []) if volc_stats is not None else []
    azure_rows = list(getattr(azure_stats, "rows", None) or []) if azure_stats is not None else []
    if not volc_rows and not azure_rows:
        parts = []
        if volc_err:
            parts.append(f"火山：{volc_err}")
        elif volc_stats is not None:
            extra = "；".join((volc_stats.errors or [])[:3])
            parts.append("火山未采集到接入点" + (f"（{extra}）" if extra else ""))
        if azure_err:
            parts.append(f"Azure：{azure_err}")
        elif azure_stats is not None:
            extra = "；".join((azure_stats.errors or [])[:3])
            parts.append("Azure 未采集到部署" + (f"（{extra}）" if extra else ""))
        return jsonify(
            {
                "success": False,
                "message": "未写入汇总表：" + "；".join(parts) if parts else "未采集到任何上游数据",
                "data": {
                    "volc_error": volc_err,
                    "azure_error": azure_err,
                    "volc": _volc_collect_payload(volc_stats) if volc_stats is not None else None,
                    "azure": _azure_collect_payload(azure_stats) if azure_stats is not None else None,
                },
            }
        ), 400

    excel_path = BATCH["build_combined_upstream_path"](NEW_DIR)
    BATCH["save_combined_upstream_workbook"](excel_path, volc_rows, azure_rows)
    rel = _rel_to_root(excel_path)
    warnings: list[str] = []
    if volc_err:
        warnings.append(f"火山未写入数据：{volc_err}")
    if azure_err:
        warnings.append(f"Azure 未写入数据：{azure_err}")
    if volc_stats is not None:
        warnings.extend(list(volc_stats.errors or []))
    if azure_stats is not None:
        warnings.extend(list(azure_stats.errors or []))
    volc_ok = volc_stats is not None and not volc_err and getattr(volc_stats, "projects_failed", 0) == 0
    azure_ok = (
        azure_stats is not None
        and not azure_err
        and getattr(azure_stats, "accounts_failed", 0) == 0
        and getattr(azure_stats, "subscriptions_failed", 0) == 0
    )
    ok = volc_ok and azure_ok and not volc_err and not azure_err
    volc_n = len(volc_rows)
    azure_n = len(azure_rows)
    msg = f"已写入 {rel}：火山云 {volc_n} 行，Azure OpenAI {azure_n} 行（工作表「火山云」「Azure OpenAI」）"
    if warnings:
        msg += f"；附带警告 {len(warnings)} 条"
    return jsonify(
        {
            "success": ok,
            "message": msg,
            "data": {
                "file": rel,
                "filename": excel_path.name,
                "sheets": [BATCH["SHEET_VOLC"], BATCH["SHEET_AZURE"]],
                "volc_rows": volc_n,
                "azure_rows": azure_n,
                "volc_error": volc_err,
                "azure_error": azure_err,
                "errors": warnings,
                "volc": _volc_collect_payload(volc_stats) if volc_stats is not None else None,
                "azure": _azure_collect_payload(azure_stats) if azure_stats is not None else None,
            },
        }
    )


@app.get("/api/upstream/download")
def api_upstream_combined_download():
    _ensure_batch()
    try:
        excel_path = _excel_query_path("file", "id", fallback=BATCH["latest_combined_upstream_excel_path"](NEW_DIR))
    except (ValueError, FileNotFoundError) as exc:
        return jsonify({"success": False, "message": str(exc)}), 400
    if not excel_path or not excel_path.exists():
        return jsonify({"success": False, "message": "尚未生成汇总 Excel，请先点「一键采集全部上游」"}), 404
    return _send_excel_attachment(excel_path)


@app.get("/api/overview/info")
def api_overview_info():
    _ensure_batch()
    excel_path = BATCH["latest_overview_excel_path"](NEW_DIR)
    exists = bool(excel_path and excel_path.exists())
    stats = (
        BATCH["overview_workbook_stats"](excel_path)
        if exists
        else {"rows": 0, "sheet": BATCH["SHEET_INDEX"], "sheets": {}, "total_rows": 0, "volc_rows": 0, "azure_rows": 0}
    )
    gw = BATCH["resolve_gateway_source"](NEW_DIR)
    sources = BATCH["describe_overview_sources"](NEW_DIR)
    key_status = BATCH["scan_channel_key_status"](excel_path if exists else None)
    source_key_status = BATCH["scan_channel_key_status"](gw)
    analysis_path = BATCH["latest_analysis_excel_path"](NEW_DIR)
    analysis_exists = bool(analysis_path and analysis_path.exists())
    analysis_stats = BATCH["analysis_workbook_stats"](analysis_path) if analysis_exists else {}
    balance_path = BATCH["latest_balance_excel_for_analysis"](NEW_DIR)
    return jsonify(
        {
            "success": True,
            "data": {
                "filename": excel_path.name if exists else "",
                "path": _rel_to_root(excel_path) if exists else "",
                "exists": exists,
                "stem": BATCH["OVERVIEW_STEM"],
                "sheet": stats.get("sheet") or BATCH["SHEET_INDEX"],
                "summary": stats,
                "latest_gateway": _rel_to_root(gw) if gw else "",
                "sources": sources,
                "env_sites": [s.get("env") for s in _env_site_payloads()],
                "key_status": key_status,
                "source_key_status": source_key_status,
                "include_keys_default": True,
                "analysis_exists": analysis_exists,
                "analysis_file": _rel_to_root(analysis_path) if analysis_exists else "",
                "analysis_filename": analysis_path.name if analysis_exists else "",
                "analysis_stem": BATCH["ANALYSIS_STEM"],
                "analysis_summary": analysis_stats,
                "latest_balance": _rel_to_root(balance_path) if balance_path else "",
                "latest_balance_filename": balance_path.name if balance_path else "",
                "note": "test/uat/prod 默认获取渠道密钥。已有③⑤或总览文件按时间戳提取；缺密钥或遇 429 可继续补全。智能分析会读取最新渠道余额表；没有则不识别用量。",
            },
        }
    )


@app.post("/api/overview/collect")
def api_overview_collect():
    """已有文件则提取；test/uat/prod 默认含密钥。缺密钥时按站点补拉，遇 429 可再点继续补全。"""
    _ensure_batch()
    body = request.get_json(silent=True) or {}
    include_keys = _overview_include_keys(body)
    warnings: list[str] = []
    tmp_gateway: Path | None = None
    gw_stats = None
    volc_stats = None
    azure_stats = None
    gw_err = ""
    volc_err = ""
    azure_err = ""
    key_fills: list[dict[str, Any]] = []
    source_summary = _optional_source_excel(body.get("source_summary"))
    source_upstream = _optional_source_excel(body.get("source_upstream"))

    if source_summary:
        gateway_path = source_summary
        warnings.append(f"网关已按所选文件提取：{gateway_path.name}")
    else:
        gateway_path = BATCH["resolve_gateway_source"](NEW_DIR)
        if gateway_path:
            warnings.append(f"网关已从已有文件提取（时间戳最新）：{gateway_path.name}")
        else:
            gateway_path, gw_err, gw_stats = _collect_gateway_workbook(body)
            if gateway_path and gateway_path.name.startswith("_overview_gw_"):
                tmp_gateway = gateway_path
            if not gateway_path and gw_err:
                warnings.append(gw_err)

    if source_upstream:
        volc_rows = BATCH["resolve_volc_rows"](NEW_DIR, source=source_upstream)
        azure_rows = BATCH["resolve_azure_rows"](NEW_DIR, source=source_upstream)
        warnings.append(f"上游已按所选文件提取：{source_upstream.name}")
    else:
        volc_rows = BATCH["resolve_volc_rows"](NEW_DIR)
        if volc_rows:
            warnings.append("火山云已从已有 Excel 提取（时间戳最新）")
        else:
            volc_stats, volc_err = _run_volc_collect(body)
            volc_live = list(getattr(volc_stats, "rows", None) or []) if volc_stats is not None else []
            if volc_err:
                warnings.append(f"火山现场采集：{volc_err}")
            volc_rows = BATCH["resolve_volc_rows"](NEW_DIR, volc_live or None)
            if not volc_live and volc_rows:
                warnings.append("火山云已改用最新上游 Excel")

        azure_rows = BATCH["resolve_azure_rows"](NEW_DIR)
        if azure_rows:
            warnings.append("Azure OpenAI 已从已有 Excel 提取（时间戳最新）")
        else:
            azure_stats, azure_err = _run_azure_collect(body)
            azure_live = list(getattr(azure_stats, "rows", None) or []) if azure_stats is not None else []
            if azure_err:
                warnings.append(f"Azure 现场采集：{azure_err}")
            azure_rows = BATCH["resolve_azure_rows"](NEW_DIR, azure_live or None)
            if not azure_live and azure_rows:
                warnings.append("Azure OpenAI 已改用最新上游 Excel")

    if not gateway_path and not volc_rows and not azure_rows:
        return jsonify(
            {
                "success": False,
                "message": "没有可写入的数据。请先配置 env/sites.json 与上游凭证，或先在③⑤各采集一份。",
                "data": {"errors": warnings},
            }
        ), 400

    excel_path = BATCH["build_overview_path"](NEW_DIR)
    try:
        BATCH["save_overview_workbook"](
            excel_path,
            gateway_path=gateway_path,
            volc_rows=volc_rows,
            azure_rows=azure_rows,
        )
    finally:
        if tmp_gateway and tmp_gateway.exists():
            try:
                tmp_gateway.unlink()
            except OSError:
                pass

    if include_keys and excel_path.exists():
        sites = BATCH["parse_summary_sites"](_merge_overview_sites(body))
        pending = int((BATCH["scan_channel_key_status"](excel_path) or {}).get("pending_total") or 0)
        if sites and pending:
            warnings.append("正在按 test/uat/prod 补拉渠道密钥（遇 429 会停下，可稍后继续）")
            key_fills = _fill_overview_channel_keys(excel_path, sites, warnings)
        elif pending and not sites:
            warnings.append("渠道密钥仍缺，但 env/sites.json 无站点，无法连网补拉。请配置后点「继续补全密钥」。")

    stats = BATCH["overview_workbook_stats"](excel_path)
    key_status = BATCH["scan_channel_key_status"](excel_path)
    rel = _rel_to_root(excel_path)
    gw_ok = gw_stats is not None and getattr(gw_stats, "sites_ok", 0) > 0
    volc_ok = bool(getattr(volc_stats, "rows", None))
    azure_ok = bool(getattr(azure_stats, "rows", None))
    msg = (
        f"已写入 {rel}：网关 {len(stats.get('gateway_sheets') or [])} 张表"
        f"，火山云 {stats.get('volc_rows') or 0} 行，Azure OpenAI {stats.get('azure_rows') or 0} 行"
    )
    if include_keys:
        msg += f"；密钥 {key_status.get('filled_total') or 0}/{key_status.get('channels_total') or 0}"
        if key_status.get("pending_total"):
            msg += f"，仍缺 {key_status.get('pending_total')}（可点「继续补全密钥」）"
    if warnings:
        msg += f"；附带说明 {len(warnings)} 条"
    return jsonify(
        {
            "success": True,
            "message": msg,
            "data": {
                "file": rel,
                "filename": excel_path.name,
                "sheet": BATCH["SHEET_INDEX"],
                "summary": stats,
                "warnings": warnings,
                "errors": warnings,
                "gateway_live": gw_ok,
                "volc_live": volc_ok,
                "azure_live": azure_ok,
                "include_keys": include_keys,
                "key_status": key_status,
                "key_fills": key_fills,
                "volc": _volc_collect_payload(volc_stats) if volc_stats is not None else None,
                "azure": _azure_collect_payload(azure_stats) if azure_stats is not None else None,
                "site_results": list(getattr(gw_stats, "site_results", None) or []),
            },
        }
    )


@app.post("/api/overview/fill-keys")
def api_overview_fill_keys():
    """对最新一份⑥ 总览 Excel 补全某一环境渠道密钥（应对 429）。"""
    _ensure_batch()
    body = request.get_json(silent=True) or {}
    sites = BATCH["parse_summary_sites"](_merge_overview_sites(body))
    if len(sites) != 1:
        return jsonify({"success": False, "message": "继续补全密钥请每次只选 1 个站点（test / uat / prod）"}), 400
    site = sites[0]
    if not BATCH["has_otp_source"](getattr(site, "otp_code", ""), totp_secret=getattr(site, "totp_secret", "")):
        return jsonify({"success": False, "message": "请填写该站点的二次验证码，或在 env/sites.json 预置 totp_secret"}), 400
    excel_path = BATCH["latest_overview_excel_path"](NEW_DIR)
    if not excel_path or not excel_path.exists():
        return jsonify({"success": False, "message": "尚未生成一表总览，请先点「一键生成总览表」"}), 404
    try:
        result, saved_path = BATCH["fill_missing_channel_keys"](
            site=site,
            root_dir=NEW_DIR,
            excel_path=excel_path,
        )
        BATCH["refresh_overview_index"](saved_path)
        key_status = BATCH["scan_channel_key_status"](saved_path)
        return jsonify(
            {
                "success": True,
                "message": result.get("message") or "补全完成",
                "data": {
                    **result,
                    "file": _rel_to_root(saved_path),
                    "filename": saved_path.name,
                    "key_status": key_status,
                },
            }
        )
    except Exception as exc:  # noqa: BLE001
        return jsonify({"success": False, "message": str(exc)}), 400


@app.get("/api/overview/download")
def api_overview_download():
    _ensure_batch()
    try:
        excel_path = _excel_query_path("file", "id", fallback=BATCH["latest_overview_excel_path"](NEW_DIR))
    except (ValueError, FileNotFoundError) as exc:
        return jsonify({"success": False, "message": str(exc)}), 400
    if not excel_path or not excel_path.exists():
        return jsonify({"success": False, "message": "尚未生成一表总览，请先点「一键生成总览表」"}), 404
    return _send_excel_attachment(excel_path)


@app.post("/api/overview/analyze")
def api_overview_analyze():
    """对照所选（或 allow_latest）总览的上下游密钥/部署，写入智能分析表。"""
    _ensure_batch()
    body = request.get_json(silent=True) or {}
    source_raw = body.get("source_overview") or body.get("source")
    try:
        if source_raw:
            source = BATCH["resolve_excel_path"](NEW_DIR, source_raw)
        elif _allow_latest(body):
            source = BATCH["latest_overview_excel_path"](NEW_DIR)
        else:
            return jsonify({"success": False, "message": "请选择总览文件，或传 allow_latest=1"}), 400
        balance = _optional_source_excel(body.get("source_balance"))
        policy = BATCH["load_policy"](NEW_DIR)
        saved, payload = BATCH["run_overview_analysis"](
            NEW_DIR,
            source=source,
            policy=policy,
            balance_path=balance,
        )
    except FileNotFoundError as exc:
        return jsonify({"success": False, "message": str(exc)}), 404
    except ValueError as exc:
        return jsonify({"success": False, "message": str(exc)}), 400
    except Exception as exc:  # noqa: BLE001
        return jsonify({"success": False, "message": _user_facing_error(exc)}), 400
    stats = payload.get("stats") or {}
    rel = _rel_to_root(saved)
    if stats.get("balance_file"):
        bal_note = (
            f"，渠道余额 {stats.get('balance_file')}"
            f"：不用 {stats.get('balance_unused') or 0} 条"
            f"、不常用 {stats.get('balance_uncommon') or 0} 条"
        )
    else:
        bal_note = "（未找到渠道余额表，用量未识别；请先在③导出余额）"
    msg = (
        f"已写入 {rel}：高优先级 {stats.get('high') or 0} 条"
        f"，建议处置 {stats.get('actions') or 0} 条"
        f"，已禁用建议 {stats.get('disabled_actions') or 0} 条"
        f"，下游无上游 {stats.get('down_no_up') or 0} 条"
        f"，上游无下游 {stats.get('up_no_down') or 0} 条"
        f"{bal_note}"
    )
    return jsonify(
        {
            "success": True,
            "message": msg,
            "data": {
                "file": rel,
                "filename": saved.name,
                "source": source.name if source else "",
                "stats": stats,
                "policy": policy,
                "sheets": {
                    "建议处置": stats.get("actions") or 0,
                    "已禁用建议": stats.get("disabled_actions") or 0,
                    "批量禁用": stats.get("disable_rows") or 0,
                    "下游无上游": stats.get("down_no_up") or 0,
                    "上游无下游": stats.get("up_no_down") or 0,
                    "环境覆盖": stats.get("coverage") or 0,
                    "密钥共用": stats.get("shared") or 0,
                    "令牌对照": stats.get("tokens") or 0,
                    "匹配明细": stats.get("channels") or 0,
                    "渠道余额": stats.get("balance_rows") or 0,
                },
            },
        }
    )


@app.get("/api/overview/analyze/download")
def api_overview_analyze_download():
    _ensure_batch()
    try:
        excel_path = _excel_query_path("file", "id", fallback=BATCH["latest_analysis_excel_path"](NEW_DIR))
    except (ValueError, FileNotFoundError) as exc:
        return jsonify({"success": False, "message": str(exc)}), 400
    if not excel_path or not excel_path.exists():
        return jsonify({"success": False, "message": "尚未生成智能分析表，请先点「智能分析」"}), 404
    return _send_excel_attachment(excel_path)


@app.get("/api/artifacts")
def api_artifacts():
    _ensure_batch()
    kind = str(request.args.get("kind") or "").strip()
    try:
        limit = int(request.args.get("limit") or 20)
        items = BATCH["list_artifacts"](NEW_DIR, kind, limit=limit)
    except (TypeError, ValueError) as exc:
        return jsonify({"success": False, "message": str(exc)}), 400
    return jsonify({"success": True, "data": {"kind": kind, "items": items}})


@app.get("/api/artifacts/download")
def api_artifacts_download():
    _ensure_batch()
    try:
        excel_path = _excel_query_path("file", "id")
    except (ValueError, FileNotFoundError) as exc:
        return jsonify({"success": False, "message": str(exc)}), 400
    if not excel_path or not excel_path.exists():
        return jsonify({"success": False, "message": "请指定要下载的产物文件"}), 400
    return _send_excel_attachment(excel_path)


@app.get("/api/policy/hygiene")
def api_policy_hygiene_get():
    _ensure_batch()
    policy = BATCH["load_policy"](NEW_DIR)
    return jsonify(
        {
            "success": True,
            "data": {
                **policy,
                "summary": BATCH["policy_summary_text"](policy),
            },
        }
    )


@app.put("/api/policy/hygiene")
def api_policy_hygiene_put():
    _ensure_batch()
    body = request.get_json(silent=True) or {}
    try:
        policy = BATCH["save_policy"](NEW_DIR, body)
    except (TypeError, ValueError) as exc:
        return jsonify({"success": False, "message": str(exc)}), 400
    return jsonify(
        {
            "success": True,
            "message": "卫生策略已保存，下次分析生效",
            "data": {**policy, "summary": BATCH["policy_summary_text"](policy)},
        }
    )


def _iso_from_job_ts(value: Any) -> str:
    if isinstance(value, (int, float)) and value > 0:
        try:
            return datetime.fromtimestamp(value).isoformat(timespec="seconds")
        except (OSError, OverflowError, ValueError):
            return ""
    return str(value or "").strip()


def _workspace_job_item(job: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(job.get("id") or ""),
        "status": str(job.get("status") or ""),
        "goal": str(job.get("goal") or "").strip()[:80],
        "message": str(job.get("message") or "").strip()[:160],
        "updated_at": _iso_from_job_ts(job.get("updated_at") or job.get("created_at")),
    }


def _artifact_by_kinds(artifacts: list[dict[str, Any]], kinds: tuple[str, ...]) -> dict[str, Any] | None:
    by_kind = {str(item.get("kind") or ""): item for item in artifacts if isinstance(item, dict)}
    for kind in kinds:
        item = by_kind.get(kind)
        if item:
            return item
    return None


@app.get("/api/workspace/summary")
def api_workspace_summary():
    _ensure_batch()
    import agent_jobs

    policy = BATCH["load_policy"](NEW_DIR)
    artifacts = BATCH["latest_artifacts_bundle"](NEW_DIR)
    analysis_items = BATCH["list_artifacts"](NEW_DIR, "analysis", limit=1)
    summary_items = BATCH["list_artifacts"](NEW_DIR, "summary", limit=1)
    analysis_file = analysis_items[0]["filename"] if analysis_items else ""
    pending_high = None
    hold_count = None
    open_count = None
    coverage_open = None
    up_no_down_open = None
    if analysis_file:
        try:
            path = BATCH["resolve_excel_path"](NEW_DIR, analysis_file)
            payload = BATCH["load_analysis_payload"](path, NEW_DIR)
            pending_high = payload.get("pending_high")
            hold_count = payload.get("hold_count")
            open_count = payload.get("open_count")
            actions = payload.get("actions") or []
            coverage_open = sum(
                1
                for row in actions
                if row.get("status") == "open" and str(row.get("类别") or "") == "环境覆盖"
            )
            up_no_down_open = sum(
                1
                for row in actions
                if row.get("status") == "open" and str(row.get("类别") or "") == "上游无下游"
            )
        except Exception:  # noqa: BLE001
            pending_high = None
    jobs = []
    try:
        jobs = [
            j
            for j in agent_jobs.STORE.snapshot_jobs()
            if j.get("status") in {"queued", "planning", "running", "waiting_confirm"}
        ]
    except Exception:  # noqa: BLE001
        jobs = []
    env_pack = _load_env_sites()
    env_status = []
    for key in env_pack.get("available") or []:
        site = (env_pack.get("sites") or {}).get(key) or {}
        if not site:
            continue
        env_status.append(
            {
                "env": key,
                "cluster": BATCH["cluster_label"](key),
                "has_totp_secret": bool(site.get("has_totp_secret")),
                "session_ready": bool(
                    BATCH["session_cache_alive"](
                        site.get("base_url") or "",
                        username=str(site.get("username") or ""),
                        password=str(site.get("password") or ""),
                        access_token=str(site.get("access_token") or ""),
                    )
                ),
                "auth_mode": site.get("auth_mode") or "password",
                "base_url": site.get("base_url") or "",
                "host": BATCH["public_host"](site.get("base_url") or ""),
            }
        )
    last_summary = summary_items[0] if summary_items else None
    last_upstream = _artifact_by_kinds(artifacts, ("upstream",))
    last_bill = _artifact_by_kinds(artifacts, ("bill_combined", "bill", "bill_azure"))
    return jsonify(
        {
            "success": True,
            "data": {
                "pending_high": pending_high,
                "hold_count": hold_count,
                "open_count": open_count,
                "coverage_open": coverage_open,
                "up_no_down_open": up_no_down_open,
                "analysis_missing": not bool(analysis_file),
                "analysis_file": analysis_file,
                "last_summary_at": (last_summary or {}).get("created_at") or "",
                "last_summary_file": (last_summary or {}).get("filename") or "",
                "last_upstream_at": (last_upstream or {}).get("created_at") or "",
                "last_upstream_file": (last_upstream or {}).get("filename") or "",
                "last_bill_at": (last_bill or {}).get("created_at") or "",
                "last_bill_file": (last_bill or {}).get("filename") or "",
                "active_jobs": len(jobs),
                "active_job_list": [_workspace_job_item(j) for j in jobs],
                "latest_artifacts": artifacts,
                "policy": {**policy, "summary": BATCH["policy_summary_text"](policy)},
                "env_sites": env_status,
            },
        }
    )


@app.post("/api/workspace/auth")
def api_workspace_auth():
    """工作台全局认证：按 env/sites.json 已配置站点登录并写入会话缓存。"""
    _reload_batch_modules()
    env_pack = _load_env_sites()
    if not env_pack.get("configured"):
        return jsonify({"success": False, "message": "未配置 env/sites.json"}), 400
    body = request.get_json(silent=True) or {}
    otp_by_env: dict[str, str] = {}
    for item in body.get("sites") or []:
        if not isinstance(item, dict):
            continue
        env = str(item.get("env") or "").strip().lower()
        code = str(item.get("otp_code") or item.get("verification_code") or "").strip()
        if env and code:
            otp_by_env[env] = code
    raw_sites: list[dict[str, Any]] = []
    for key in env_pack.get("available") or []:
        site = dict((env_pack.get("sites") or {}).get(key) or {})
        if not site.get("base_url"):
            continue
        row = {**site, "env": key, "label": site.get("label") or key}
        if otp_by_env.get(key):
            row["otp_code"] = otp_by_env[key]
        raw_sites.append(row)
    sites = BATCH["parse_summary_sites"](raw_sites)
    if not sites:
        return jsonify({"success": False, "message": "没有可认证的站点"}), 400
    items = [BATCH["login_site_auth"](site) for site in sites]
    ready = sum(1 for it in items if it.get("session_ready"))
    need = sum(1 for it in items if it.get("needs_otp_prompt") and not it.get("session_ready"))
    failed = len(items) - ready - need
    ok = ready > 0 and failed == 0
    return jsonify(
        {
            "success": True,
            "message": (
                f"认证完成：已就绪 {ready} 个"
                + (f"，需临时验证码 {need} 个" if need else "")
                + (f"，失败 {failed} 个" if failed else "")
            ),
            "data": {"items": items, "ready": ready, "need_otp": need, "failed": failed, "ok": ok},
        }
    )


@app.get("/api/hygiene/actions")
def api_hygiene_actions():
    _ensure_batch()
    raw = request.args.get("file") or request.args.get("id") or ""
    try:
        if raw:
            path = BATCH["resolve_excel_path"](NEW_DIR, raw)
        elif _allow_latest():
            path = BATCH["latest_analysis_excel_path"](NEW_DIR)
            if not path:
                raise FileNotFoundError("尚未生成智能分析表")
        else:
            return jsonify({"success": False, "message": "请选择分析表，或传 allow_latest=1"}), 400
        payload = BATCH["load_analysis_payload"](path, NEW_DIR)
    except FileNotFoundError as exc:
        return jsonify({"success": False, "message": str(exc)}), 404
    except ValueError as exc:
        return jsonify({"success": False, "message": str(exc)}), 400
    payload["policy"] = BATCH["load_policy"](NEW_DIR)
    payload["policy_summary"] = BATCH["policy_summary_text"](payload["policy"])
    return jsonify({"success": True, "data": payload})


def _hygiene_env_body(env: str, body: dict[str, Any]) -> dict[str, Any]:
    env_pack = _load_env_sites()
    site = dict((env_pack.get("sites") or {}).get(env) or {})
    overlay = {}
    for item in body.get("sites") or []:
        if not isinstance(item, dict):
            continue
        if str(item.get("env") or "").strip().lower() == env:
            overlay = item
            break
    merged = {**site, **{k: v for k, v in overlay.items() if v not in (None, "")}}
    merged["env"] = env
    return merged


@app.post("/api/hygiene/preview-disable")
def api_hygiene_preview_disable():
    _ensure_batch()
    body = request.get_json(silent=True) or {}
    try:
        path = BATCH["resolve_excel_path"](NEW_DIR, body.get("file") or body.get("id") or "")
        payload = BATCH["load_analysis_payload"](path, NEW_DIR)
        selected = BATCH["select_actions"](payload, body.get("keys"))
        preview = BATCH["preview_disable_from_actions"](
            selected,
            force_hold=bool(body.get("force_hold") or body.get("force")),
        )
    except FileNotFoundError as exc:
        return jsonify({"success": False, "message": str(exc)}), 404
    except ValueError as exc:
        return jsonify({"success": False, "message": str(exc)}), 400
    return jsonify({"success": True, "data": {**preview, "filename": path.name, "keys": [r.get("key") for r in selected]}})


@app.post("/api/hygiene/confirm-disable")
def api_hygiene_confirm_disable():
    _ensure_batch()
    body = request.get_json(silent=True) or {}
    dry_run = bool(body.get("dry_run", False))
    try:
        path = BATCH["resolve_excel_path"](NEW_DIR, body.get("file") or body.get("id") or "")
        payload = BATCH["load_analysis_payload"](path, NEW_DIR)
        selected = BATCH["select_actions"](payload, body.get("keys"))
        preview = BATCH["preview_disable_from_actions"](
            selected,
            force_hold=bool(body.get("force_hold") or body.get("force")),
        )
    except FileNotFoundError as exc:
        return jsonify({"success": False, "message": str(exc)}), 404
    except ValueError as exc:
        return jsonify({"success": False, "message": str(exc)}), 400

    results: dict[str, Any] = {}
    failed = False
    for env in ("test", "uat", "prod"):
        ch_text = str((preview.get("channels") or {}).get(env) or "").strip()
        tk_text = str((preview.get("tokens") or {}).get(env) or "").strip()
        if not ch_text and not tk_text:
            continue
        conn = _hygiene_env_body(env, body)
        base_url = _parse_base_url(conn.get("base_url") or "")
        if not base_url:
            results[env] = {"success": False, "message": f"{env} 未配置站点地址"}
            failed = True
            continue
        try:
            auth = _parse_auth({**conn, "base_url": base_url})
            env_result: dict[str, Any] = {"success": True, "channels": None, "tokens": None}
            if ch_text:
                ch = BATCH["run_channel_batch_status"](
                    base_url=base_url,
                    auth=auth,
                    action="disable",
                    dry_run=dry_run,
                    match_mode="name",
                    batch_text=ch_text,
                )
                env_result["channels"] = {
                    "matched": ch.matched_count,
                    "updated": getattr(ch, "updated_count", 0),
                    "failed": ch.failed_count,
                    "skipped": ch.skipped_count,
                    "items": ch.items,
                    "dry_run": ch.dry_run,
                }
                if ch.failed_count:
                    failed = True
            if tk_text:
                tk = BATCH["run_token_batch_status"](
                    base_url=base_url,
                    batch_text=tk_text,
                    auth=auth,
                    action="disable",
                    dry_run=dry_run,
                )
                env_result["tokens"] = {
                    "matched": tk.matched_count,
                    "updated": getattr(tk, "updated_count", 0),
                    "failed": tk.failed_count,
                    "skipped": tk.skipped_count,
                    "items": tk.items,
                    "dry_run": tk.dry_run,
                }
                if tk.failed_count:
                    failed = True
            results[env] = env_result
        except Exception as exc:  # noqa: BLE001
            failed = True
            results[env] = {"success": False, "message": _user_facing_error(exc)}

    if not dry_run and not failed:
        BATCH["mark_actions_done"](NEW_DIR, path.name, [str(r.get("key")) for r in selected if r.get("key")])

    return jsonify(
        {
            "success": not failed,
            "message": "预禁用完成，请确认清单" if dry_run else ("已禁用并记入处理记录" if not failed else "部分环境失败"),
            "data": {"preview": preview, "results": results, "dry_run": dry_run, "filename": path.name},
        }
    )


@app.get("/api/llm-presets")
def llm_presets():
    with _LIB_LOCK:
        _pin_lib_root(AGENT_DIR)
        llm_client = importlib.import_module("lib.llm_client")
        presets = llm_client.list_provider_presets()
    file_config = _load_llm_config()
    return jsonify({"success": True, "data": {"presets": presets, "defaults": file_config}})


@app.post("/api/extract")
def api_extract():
    _reload_agent_modules()
    body = request.get_json(silent=True) or {}
    raw_text = str(body.get("raw_text", "")).strip()
    # 兼容：extract_mode=token 时走令牌提取
    extract_mode = str(body.get("extract_mode") or body.get("mode") or "channel").strip().lower()
    if extract_mode in {"token", "tokens", "令牌"}:
        result = extract_tokens(raw_text)
        return jsonify(result.to_dict())

    use_llm = bool(body.get("use_llm", False))

    llm_override = {
        "api_base": str(body.get("llm_api_base") or "").strip(),
        "api_key": str(body.get("llm_api_key") or "").strip(),
        "model": str(body.get("llm_model") or "").strip() or "gpt-4o-mini",
        "provider": str(body.get("llm_provider") or "").strip(),
    }
    file_config = _load_llm_config()
    llm_config = {
        "api_base": llm_override["api_base"] or file_config.get("api_base", ""),
        "api_key": llm_override["api_key"] or file_config.get("api_key", ""),
        "model": llm_override["model"] or file_config.get("model", "gpt-4o-mini"),
        "provider": llm_override["provider"] or file_config.get("provider", ""),
        "timeout": file_config.get("timeout", 60),
    }

    if "require_key" in body:
        require_key = bool(body.get("require_key"))
    else:
        require_key = not bool(body.get("for_update"))

    result = extract_channels(
        raw_text,
        use_llm=use_llm,
        llm_config=llm_config,
        require_key=require_key,
    )

    payload = {
        "success": result.success,
        "message": result.message,
        "mode": result.mode,
        "count": result.count,
        "channel_line": result.channel_line,
        "channel_lines": result.channel_lines,
        "fields": result.summary,
        "llm": {
            "enabled": result.llm.enabled,
            "configured": result.llm.configured,
            "invoked": result.llm.invoked,
            "success": result.llm.success,
            "provider": result.llm.provider,
            "model": result.llm.model,
            "items_invoked": result.llm.items_invoked,
            "items_succeeded": result.llm.items_succeeded,
            "items_failed": result.llm.items_failed,
            "filled_fields": result.llm.filled_fields,
            "errors": result.llm.errors,
        },
        "items": [
            {
                "index": item.index,
                "success": item.success,
                "message": item.message,
                "channel_line": item.channel_line,
                "fields": item.summary,
                "sources": item.fields.sources,
                "warnings": item.fields.warnings,
                "confidence": round(item.fields.confidence, 2),
                "llm_invoked": item.fields.llm_invoked,
                "llm_success": item.fields.llm_success,
                "llm_provider": item.fields.llm_provider,
                "llm_model": item.fields.llm_model,
                "llm_filled": item.fields.llm_filled,
                "llm_error": item.fields.llm_error,
            }
            for item in result.items
        ],
        "sources": result.fields.sources,
        "warnings": result.fields.warnings,
        "confidence": round(result.fields.confidence, 2),
    }
    status = 200
    if use_llm and not result.success and result.mode == "llm_failed":
        status = 400
    return jsonify(payload), status


@app.post("/api/extract-token")
def api_extract_token():
    """令牌智能提取：多行杂乱输入 → 令牌名\\t分组\\t模型列表。"""
    _reload_agent_modules()
    body = request.get_json(silent=True) or {}
    raw_text = str(body.get("raw_text", "")).strip()
    result = extract_tokens(raw_text)
    return jsonify(result.to_dict())


def _merge_llm_config(body: dict) -> dict:
    provider = str(body.get("llm_provider") or body.get("provider") or "").strip()
    llm_override = {
        "api_base": str(body.get("llm_api_base") or body.get("api_base") or "").strip(),
        "api_key": str(body.get("llm_api_key") or body.get("api_key") or "").strip(),
        "model": str(body.get("llm_model") or body.get("model") or "").strip() or "gpt-4o-mini",
        "provider": provider,
    }
    file_config = _load_llm_config()
    return {
        "api_base": llm_override["api_base"] or file_config.get("api_base", ""),
        "api_key": llm_override["api_key"] or file_config.get("api_key", ""),
        "model": llm_override["model"] or file_config.get("model", "gpt-4o-mini"),
        "provider": llm_override["provider"] or file_config.get("provider", ""),
        "timeout": file_config.get("timeout", 60),
    }


def _merge_agent_connection(connection: dict) -> dict:
    file_batch = _load_batch_config()
    merged = {
        "base_url": _parse_base_url(connection.get("base_url") or file_batch.get("base_url") or ""),
        "username": str(connection.get("username") or file_batch.get("username") or "").strip(),
        "password": connection.get("password") if connection.get("password") not in (None, "") else file_batch.get("password", ""),
        "access_token": str(connection.get("access_token") or file_batch.get("access_token") or "").strip(),
        "user_id": connection.get("user_id") if connection.get("user_id") not in (None, "") else file_batch.get("user_id"),
        "default_key": str(connection.get("default_key") or file_batch.get("default_key") or "").strip(),
        "otp_code": str(connection.get("otp_code") or connection.get("verification_code") or "").strip(),
        "totp_secret": str(connection.get("totp_secret") or connection.get("otp_secret") or "").strip(),
    }
    if connection.get("verify_ssl") is not None:
        merged["verify_ssl"] = BATCH["coerce_verify_ssl"](connection.get("verify_ssl"), True)
    elif file_batch.get("verify_ssl") is not None:
        merged["verify_ssl"] = BATCH["coerce_verify_ssl"](file_batch.get("verify_ssl"), True)
    _ensure_batch()
    return BATCH["enrich_auth_from_env"](merged, base_url=merged.get("base_url") or "")


def _enrich_agent_sites(sites: list) -> list[dict[str, Any]]:
    """汇总站点未填的密码 / TOTP 从 env/sites.json 补齐。"""
    _ensure_batch()
    parsed = BATCH["parse_summary_sites"](sites or [])
    out: list[dict[str, Any]] = []
    for site in parsed:
        row: dict[str, Any] = {
            "base_url": site.base_url,
            "username": site.username,
            "password": site.password,
            "env": site.env,
            "label": site.label,
            "otp_code": site.otp_code,
            "totp_secret": site.totp_secret,
            "access_token": site.access_token,
            "verify_ssl": site.verify_ssl,
        }
        if site.user_id not in (None, 0):
            row["user_id"] = site.user_id
        out.append(row)
    return out


def _enrich_job_from_env(job: Any) -> None:
    job.connection = _merge_agent_connection(job.connection or {})
    if isinstance(job.sites, list) and job.sites:
        job.sites = _enrich_agent_sites(job.sites)


def _agent_collect_upstream(project_dir: Path) -> dict[str, Any]:
    """智能体⑤：一键采集火山 + Azure，写入上游汇总表。无凭证/无数据则跳过。"""
    _ensure_batch()
    volc_stats, volc_err = _run_volc_collect({})
    azure_stats, azure_err = _run_azure_collect({})
    volc_rows = list(getattr(volc_stats, "rows", None) or []) if volc_stats is not None else []
    azure_rows = list(getattr(azure_stats, "rows", None) or []) if azure_stats is not None else []
    if not volc_rows and not azure_rows:
        parts: list[str] = []
        if volc_err:
            parts.append(f"火山：{volc_err}")
        elif volc_stats is not None:
            extra = "；".join((volc_stats.errors or [])[:3])
            parts.append("火山未采集到接入点" + (f"（{extra}）" if extra else ""))
        if azure_err:
            parts.append(f"Azure：{azure_err}")
        elif azure_stats is not None:
            extra = "；".join((azure_stats.errors or [])[:3])
            parts.append("Azure 未采集到部署" + (f"（{extra}）" if extra else ""))
        detail = "；".join(parts) if parts else "未采集到任何上游数据"
        return {
            "ok": False,
            "skipped": True,
            "message": f"未配置上游凭证或未采到数据，跳过⑤：{detail}",
            "volc_error": volc_err,
            "azure_error": azure_err,
        }

    excel_path = BATCH["build_combined_upstream_path"](project_dir)
    BATCH["save_combined_upstream_workbook"](excel_path, volc_rows, azure_rows)
    rel = _rel_to_root(excel_path)
    warnings: list[str] = []
    if volc_err:
        warnings.append(f"火山未写入数据：{volc_err}")
    if azure_err:
        warnings.append(f"Azure 未写入数据：{azure_err}")
    if volc_stats is not None:
        warnings.extend(list(volc_stats.errors or []))
    if azure_stats is not None:
        warnings.extend(list(azure_stats.errors or []))
    volc_ok = volc_stats is not None and not volc_err and getattr(volc_stats, "projects_failed", 0) == 0
    azure_ok = (
        azure_stats is not None
        and not azure_err
        and getattr(azure_stats, "accounts_failed", 0) == 0
        and getattr(azure_stats, "subscriptions_failed", 0) == 0
    )
    ok = volc_ok and azure_ok
    volc_n = len(volc_rows)
    azure_n = len(azure_rows)
    msg = f"已写入 {rel}：火山云 {volc_n} 行，Azure OpenAI {azure_n} 行"
    if warnings:
        msg += f"；附带警告 {len(warnings)} 条"
    return {
        "ok": ok,
        "skipped": False,
        "message": msg,
        "file": rel,
        "filename": excel_path.name,
        "volc_rows": volc_n,
        "azure_rows": azure_n,
        "warnings": warnings,
        "volc_error": volc_err,
        "azure_error": azure_err,
    }


def _agent_build_overview(project_dir: Path) -> dict[str, Any]:
    """智能体⑥：从已有③⑤文件生成总览，不拉渠道明文密钥。"""
    _ensure_batch()
    gw = BATCH["resolve_gateway_source"](project_dir)
    volc_rows = BATCH["resolve_volc_rows"](project_dir)
    azure_rows = BATCH["resolve_azure_rows"](project_dir)
    if not gw and not volc_rows and not azure_rows:
        return {
            "ok": False,
            "skipped": True,
            "message": "excel/ 中没有③网关汇总或⑤上游文件，跳过⑥总览。请先跑③汇总或⑤采集。",
        }
    dest = BATCH["build_overview_path"](project_dir)
    BATCH["save_overview_workbook"](
        dest,
        gateway_path=gw,
        volc_rows=volc_rows,
        azure_rows=azure_rows,
    )
    stats = BATCH["overview_workbook_stats"](dest)
    rel = _rel_to_root(dest)
    parts: list[str] = []
    if gw:
        parts.append(f"网关 {gw.name}")
    if volc_rows:
        parts.append(f"火山 {len(volc_rows)} 行")
    if azure_rows:
        parts.append(f"Azure {len(azure_rows)} 行")
    return {
        "ok": True,
        "skipped": False,
        "message": f"已写入 {rel}（" + "，".join(parts) + "；不含渠道明文密钥）",
        "file": rel,
        "filename": dest.name,
        "summary": stats,
        "warnings": [],
    }


def _agent_run_analysis(project_dir: Path) -> dict[str, Any]:
    """智能体：读最新总览写智能分析表。无总览则跳过。"""
    _ensure_batch()
    try:
        saved, payload = BATCH["run_overview_analysis"](project_dir)
    except FileNotFoundError:
        return {
            "ok": False,
            "skipped": True,
            "message": "未找到一表总览，跳过智能分析。请先勾选⑥总览，或到⑥页生成总览表。",
        }
    stats = payload.get("stats") or {}
    rel = _rel_to_root(saved)
    if stats.get("balance_file"):
        bal_note = (
            f"，渠道余额 {stats.get('balance_file')}"
            f"：不用 {stats.get('balance_unused') or 0} 条"
            f"、不常用 {stats.get('balance_uncommon') or 0} 条"
        )
    else:
        bal_note = "（未找到渠道余额表，用量未识别；请先在③导出余额）"
    msg = (
        f"已写入 {rel}：高优先级 {stats.get('high') or 0} 条"
        f"，建议处置 {stats.get('actions') or 0} 条"
        f"，已禁用建议 {stats.get('disabled_actions') or 0} 条"
        f"，下游无上游 {stats.get('down_no_up') or 0} 条"
        f"，上游无下游 {stats.get('up_no_down') or 0} 条"
        f"{bal_note}"
    )
    return {
        "ok": True,
        "skipped": False,
        "message": msg,
        "file": rel,
        "filename": saved.name,
        "stats": stats,
        "warnings": [],
    }


def _agent_has_standalone_work(opts: dict) -> bool:
    if opts.get("run_token_export") and not opts.get("run_extract", True):
        return True
    return bool(opts.get("run_upstream") or opts.get("run_overview") or opts.get("run_analyze"))


def _agent_options(options: dict, *, require_confirm_default: bool) -> dict:
    return {
        "run_extract": bool(options.get("run_extract", True)),
        "run_batch": bool(options.get("run_batch", True)),
        "run_token": bool(options.get("run_token", False)),
        "run_token_export": bool(options.get("run_token_export", False)),
        "run_summary": bool(options.get("run_summary", True)),
        "run_upstream": bool(options.get("run_upstream", False)),
        "run_overview": bool(options.get("run_overview", False)),
        "run_analyze": bool(options.get("run_analyze", False)),
        "dry_run": bool(options.get("dry_run", False)),
        "use_llm_plan": bool(options.get("use_llm_plan", True)),
        "require_confirm": bool(options.get("require_confirm", require_confirm_default)),
        "token_usernames": str(options.get("token_usernames") or "").strip(),
    }


def _load_agent_job_deps():
    """返回按次重载的 agent/batch 调用包装，避免后台线程执行时 lib 被其它请求替换。"""

    def extract_fn(raw_text: str, *, use_llm: bool = True, llm_config: dict | None = None):
        with _LIB_LOCK:
            _pin_lib_root(AGENT_DIR)
            mod = importlib.import_module("lib.channel_extractor")
            return mod.extract_channels(raw_text, use_llm=use_llm, llm_config=llm_config)

    def plan_fn(context, **kwargs):
        with _LIB_LOCK:
            _pin_lib_root(AGENT_DIR)
            mod = importlib.import_module("lib.pipeline_llm")
            return mod.plan_pipeline(context, **kwargs)

    def _batch_get(name: str):
        def _call(*args, **kwargs):
            with _LIB_LOCK:
                snap = _load_batch_modules()
                op = snap[name]
                if callable(op):
                    return op(*args, **kwargs)
                return op

        return _call

    def _agent_locked_op(fn):
        def _call(project_dir):
            with _LIB_LOCK:
                return fn(project_dir)

        return _call

    batch_snapshot = {
        "normalize_na_base_url": _batch_get("normalize_na_base_url"),
        "run_batch_create": _batch_get("run_batch_create"),
        "run_token_batch_create": _batch_get("run_token_batch_create"),
        "build_token_batch_text": _batch_get("build_token_batch_text"),
        "export_all_tokens_text": _batch_get("export_all_tokens_text"),
        "parse_summary_sites": _batch_get("parse_summary_sites"),
        "run_data_summary_collect": _batch_get("run_data_summary_collect"),
        "default_excel_path": _batch_get("default_excel_path"),
        "agent_collect_upstream": _agent_locked_op(_agent_collect_upstream),
        "agent_build_overview": _agent_locked_op(_agent_build_overview),
        "agent_run_analysis": _agent_locked_op(_agent_run_analysis),
    }
    return extract_fn, plan_fn, batch_snapshot, NEW_DIR


def _create_agent_job_from_body(body: dict, *, require_confirm_default: bool):
    import agent_jobs

    raw_text = str(body.get("raw_text") or "").strip()
    goal = str(body.get("goal") or "").strip()
    options = body.get("options") or {}
    connection = body.get("connection") or {}
    sites = body.get("sites") or []
    llm_config = _merge_llm_config(body)
    merged_conn = _merge_agent_connection(connection if isinstance(connection, dict) else {})
    merged_sites = _enrich_agent_sites(sites) if isinstance(sites, list) else []

    if not raw_text and not merged_sites:
        # 仅导出令牌、⑤上游、⑥总览/分析时允许无原文/站点
        opts = options if isinstance(options, dict) else {}
        if not _agent_has_standalone_work(opts):
            raise ValueError("请提供原始文本（提取）或汇总站点列表")
    if not llm_config.get("api_base"):
        raise ValueError("智能体需要配置 LLM API 地址（用于规划与提取）")

    return agent_jobs.STORE.create(
        goal=goal,
        raw_text=raw_text,
        connection=merged_conn,
        sites=merged_sites,
        options=_agent_options(options, require_confirm_default=require_confirm_default),
        llm_config=llm_config,
        channel_lines=str(body.get("channel_lines") or ""),
    )


@app.post("/api/agent/jobs")
def api_agent_jobs_create():
    """创建异步智能体任务；auto_start 默认 true。"""
    import agent_jobs

    body = request.get_json(silent=True) or {}
    try:
        job = _create_agent_job_from_body(body, require_confirm_default=True)
    except ValueError as exc:
        return jsonify({"success": False, "message": str(exc)}), 400

    auto_start = bool(body.get("auto_start", True))
    if auto_start:
        agent_jobs.start_job_thread(job.id, _load_agent_job_deps)
    return jsonify({"success": True, "job_id": job.id, "job": job.to_dict()}), 201


@app.get("/api/agent/jobs/<job_id>")
def api_agent_jobs_get(job_id: str):
    import agent_jobs

    job = agent_jobs.STORE.get(job_id)
    if not job:
        return jsonify({"success": False, "message": "任务不存在"}), 404
    return jsonify({"success": True, "job": job.to_dict()})


@app.get("/api/agent/jobs/<job_id>/events")
def api_agent_jobs_events(job_id: str):
    """SSE：逐步推送 step/status/log/error/done。"""
    import agent_jobs
    import json as _json

    job = agent_jobs.STORE.get(job_id)
    if not job:
        return jsonify({"success": False, "message": "任务不存在"}), 404

    after = int(request.args.get("after") or 0)

    def stream():
        idx = after
        idle_rounds = 0
        while True:
            events = agent_jobs.STORE.wait_events(job, idx, timeout=12.0)
            if events:
                idle_rounds = 0
                for ev in events:
                    payload = {"type": ev.type, "ts": ev.ts, "data": ev.data, "index": idx}
                    yield f"event: {ev.type}\ndata: {_json.dumps(payload, ensure_ascii=False)}\n\n"
                    idx += 1
                    if ev.type == "done":
                        return
            else:
                idle_rounds += 1
                yield f"event: ping\ndata: {_json.dumps({'ts': time.time()})}\n\n"
                if job.status in agent_jobs.TERMINAL and idx >= len(job.events):
                    yield f"event: done\ndata: {_json.dumps({'type': 'done', 'data': {'status': job.status}})}\n\n"
                    return
                if idle_rounds > 60:
                    return

    return Response(
        stream(),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no", "Connection": "keep-alive"},
    )


@app.patch("/api/agent/jobs/<job_id>/plan")
def api_agent_jobs_patch_plan(job_id: str):
    import agent_jobs

    body = request.get_json(silent=True) or {}
    try:
        job = agent_jobs.patch_plan(job_id, body)
    except RuntimeError as exc:
        return jsonify({"success": False, "message": str(exc)}), 400
    if not job:
        return jsonify({"success": False, "message": "任务不存在"}), 404
    _enrich_job_from_env(job)
    return jsonify({"success": True, "job": job.to_dict()})


@app.post("/api/agent/jobs/<job_id>/confirm")
def api_agent_jobs_confirm(job_id: str):
    import agent_jobs

    body = request.get_json(silent=True) or {}
    lines = body.get("channel_lines")
    conn = body.get("connection") if isinstance(body.get("connection"), dict) else None
    sites = body.get("sites") if isinstance(body.get("sites"), list) else None
    job = agent_jobs.confirm_job(
        job_id,
        None if lines is None else str(lines),
        otp_code=str(body.get("otp_code") or ""),
        connection=conn,
        sites=sites,
    )
    if not job:
        return jsonify({"success": False, "message": "任务不存在"}), 404
    _enrich_job_from_env(job)
    auto_resume = bool(body.get("auto_resume", False))
    if auto_resume and job.confirmed and job.status == "waiting_confirm":
        job.cancel_requested = False
        agent_jobs.start_job_thread(job.id, _load_agent_job_deps, start_from=job.checkpoint or "batch")
    return jsonify({"success": True, "job": job.to_dict()})


@app.post("/api/agent/jobs/<job_id>/start")
def api_agent_jobs_start(job_id: str):
    import agent_jobs

    job = agent_jobs.STORE.get(job_id)
    if not job:
        return jsonify({"success": False, "message": "任务不存在"}), 404
    if job.status in ("running", "planning"):
        return jsonify({"success": False, "message": "任务已在执行"}), 400
    if job.status in agent_jobs.TERMINAL and job.status != "cancelled":
        if job.status == "succeeded":
            return jsonify({"success": False, "message": "任务已成功结束，请创建新任务或 retry"}), 400
    body = request.get_json(silent=True) or {}
    start_from = str(body.get("start_from") or job.checkpoint or "").strip()
    if job.status in ("failed", "cancelled"):
        return jsonify({"success": False, "message": "请先调用 /retry 再 start"}), 400
    job.cancel_requested = False
    if job.status == "waiting_confirm" and not job.confirmed:
        return jsonify({"success": False, "message": "请先 confirm 渠道行"}), 400
    agent_jobs.start_job_thread(job.id, _load_agent_job_deps, start_from=start_from)
    return jsonify({"success": True, "job": job.to_dict()})


@app.post("/api/agent/jobs/<job_id>/cancel")
def api_agent_jobs_cancel(job_id: str):
    import agent_jobs

    job = agent_jobs.request_cancel(job_id)
    if not job:
        return jsonify({"success": False, "message": "任务不存在"}), 404
    return jsonify({"success": True, "job": job.to_dict()})


@app.post("/api/agent/jobs/<job_id>/retry")
def api_agent_jobs_retry(job_id: str):
    import agent_jobs

    try:
        job = agent_jobs.prepare_retry(job_id)
    except RuntimeError as exc:
        return jsonify({"success": False, "message": str(exc)}), 400
    if not job:
        return jsonify({"success": False, "message": "任务不存在"}), 404
    body = request.get_json(silent=True) or {}
    conn = body.get("connection") if isinstance(body.get("connection"), dict) else None
    sites = body.get("sites") if isinstance(body.get("sites"), list) else None
    if body.get("otp_code") or conn or sites:
        agent_jobs.apply_auth_refresh(
            job,
            otp_code=str(body.get("otp_code") or ""),
            connection=conn,
            sites=sites,
        )
    _enrich_job_from_env(job)
    auto_start = bool(body.get("auto_start", True))
    if auto_start:
        agent_jobs.start_job_thread(job.id, _load_agent_job_deps, start_from=job.checkpoint)
    return jsonify({"success": True, "job": job.to_dict()})


@app.post("/api/agent/run")
def api_agent_run():
    """兼容旧接口：创建任务并同步等到终态（默认跳过人工门禁）。"""
    import agent_jobs
    import time as _time

    body = request.get_json(silent=True) or {}
    # 同步 API 默认不停在门禁，除非显式 require_confirm
    opts = dict(body.get("options") or {})
    if "require_confirm" not in opts:
        opts["require_confirm"] = False
    body = {**body, "options": opts}

    try:
        job = _create_agent_job_from_body(body, require_confirm_default=False)
    except ValueError as exc:
        return jsonify({"success": False, "message": str(exc)}), 400

    agent_jobs.start_job_thread(job.id, _load_agent_job_deps)

    deadline = _time.time() + 600
    while _time.time() < deadline:
        if job.status in agent_jobs.TERMINAL:
            break
        if job.status == "waiting_confirm":
            # 同步模式若仍进入门禁，自动确认继续
            agent_jobs.confirm_job(job.id, job.channel_lines)
            agent_jobs.start_job_thread(job.id, _load_agent_job_deps, start_from=job.checkpoint or "batch")
        with job._cond:
            job._cond.wait(timeout=0.5)

    payload = dict(job.result or {})
    payload["success"] = job.status == "succeeded"
    payload["message"] = job.message or payload.get("message") or ""
    payload["steps"] = job.steps
    payload["channel_lines"] = job.channel_lines
    payload["token_lines"] = (job.result or {}).get("token_lines") or ""
    payload["token_export_text"] = (job.result or {}).get("token_export_text") or ""
    payload["plan"] = job.plan
    payload["job_id"] = job.id
    payload["job_status"] = job.status
    status = 200 if payload["success"] else 400
    return jsonify(payload), status


def _parse_base_url(raw: str) -> str:
    _ensure_batch()
    return BATCH["normalize_na_base_url"](str(raw or "").strip())


def _parse_auth(body: dict) -> dict:
    _ensure_batch()
    verify_ssl_explicit = "verify_ssl" in body
    verify_ssl = BATCH["coerce_verify_ssl"](body.get("verify_ssl"), True) if verify_ssl_explicit else None
    totp_secret = str(body.get("totp_secret") or body.get("otp_secret") or "").strip()
    auth: dict[str, Any] = {
        "username": str(body.get("username") or "").strip(),
        "password": body.get("password") or "",
        "otp_code": str(body.get("otp_code") or body.get("verification_code") or "").strip(),
        "access_token": str(body.get("access_token") or "").strip(),
        "user_id": body.get("user_id"),
    }
    if verify_ssl is not None:
        auth["verify_ssl"] = verify_ssl
    if totp_secret:
        auth["totp_secret"] = totp_secret
    auth = BATCH["enrich_auth_from_env"](auth, base_url=body.get("base_url") or "")
    access_token = str(auth.get("access_token") or "").strip()
    if access_token:
        user_id = int(auth.get("user_id") or 0)
        if not user_id:
            raise ValueError("使用 Access Token 时需填写用户 ID")
        out = {
            "access_token": access_token,
            "user_id": user_id,
            "verify_ssl": auth.get("verify_ssl", True),
        }
        if auth.get("totp_secret"):
            out["totp_secret"] = auth["totp_secret"]
        if auth.get("otp_code"):
            out["otp_code"] = auth["otp_code"]
        return out
    return {
        "username": str(auth.get("username") or "").strip(),
        "password": auth.get("password") or "",
        "otp_code": str(auth.get("otp_code") or "").strip(),
        "totp_secret": str(auth.get("totp_secret") or "").strip(),
        "verify_ssl": auth.get("verify_ssl", True),
    }


@app.get("/api/channel-types")
def channel_types():
    base_url = _parse_base_url(request.args.get("base_url", ""))
    types, source = BATCH["get_channel_types"](base_url or None)
    return jsonify({"success": True, "source": source, "data": types})


@app.post("/api/test-connection")
def test_connection():
    body = request.get_json(silent=True) or {}
    base_url = _parse_base_url(body.get("base_url", ""))
    if not base_url:
        return jsonify({"success": False, "message": "请填写 New API 地址"}), 400

    client = BATCH["NewAPIClient"](base_url)
    try:
        auth = _parse_auth(body)
        client.set_verify_ssl(bool(auth.get("verify_ssl", True)))
        BATCH["authenticate_client"](client, auth)
        auth_mode = "access_token" if auth.get("access_token") else "password"

        status = client.get_status()
        groups = client.list_groups()
        user_groups = client.list_user_groups()
        types, source = BATCH["get_channel_types"](base_url)
        return jsonify(
            {
                "success": True,
                "message": "连接成功",
                "user_id": client.user_id,
                "role": client.role,
                "is_admin": client.is_admin(),
                "auth_mode": auth_mode,
                "normalized_base_url": base_url,
                "status": status,
                "groups": groups,
                "user_groups": user_groups,
                "type_source": source,
                "types": types,
            }
        )
    except KeyError as exc:
        return jsonify(
            {
                "success": False,
                "message": (
                    f"认证参数缺失 ({exc})，请填写 Access Token 或用户名密码"
                ),
            }
        ), 400
    except Exception as exc:  # noqa: BLE001
        return jsonify({"success": False, "message": _user_facing_error(exc)}), 400


_LOG_EXPORT_FILE_RE = re.compile(r"^usage_logs_\d{8}_\d{6}\.(xlsx|csv)$")
_LOG_EXPORT_JOB_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
)
_LOG_EXPORT_JOBS: dict[str, dict[str, Any]] = {}
_LOG_EXPORT_JOBS_LOCK = threading.Lock()


def _latest_logs_export_path() -> Path | None:
    if not EXCEL_DIR.exists():
        return None
    files = [
        path
        for path in EXCEL_DIR.iterdir()
        if path.is_file() and _LOG_EXPORT_FILE_RE.fullmatch(path.name)
    ]
    if not files:
        return None
    return max(files, key=lambda path: path.stat().st_mtime)


def _parse_logs_export_request(body: dict[str, Any]) -> tuple[str, str, dict[str, Any], dict[str, Any]]:
    """解析使用日志导出请求，校验失败时抛 ValueError。"""
    base_url = _parse_base_url(body.get("base_url", ""))
    if not base_url:
        raise ValueError("请填写 New API 地址")
    export_format = str(body.get("format") or "xlsx").strip().lower()
    if export_format not in {"csv", "xlsx"}:
        raise ValueError("format 仅支持 csv 或 xlsx")
    filters = {
        "log_type": int(body.get("log_type") or 0),
        "start_timestamp": int(body["start_timestamp"]) if body.get("start_timestamp") else None,
        "end_timestamp": int(body["end_timestamp"]) if body.get("end_timestamp") else None,
        "token_name": str(body.get("token_name") or "").strip(),
        "model_name": str(body.get("model_name") or "").strip(),
        "group": str(body.get("group") or "").strip(),
    }
    channel_raw = body.get("channel")
    if channel_raw not in (None, ""):
        try:
            channel_id = int(channel_raw)
        except (TypeError, ValueError) as exc:
            raise ValueError("渠道 ID 必须是数字") from exc
        if channel_id <= 0:
            raise ValueError("渠道 ID 必须大于 0")
        filters["channel"] = channel_id
    else:
        filters["channel"] = None
    auth = _parse_auth(body)
    return base_url, export_format, filters, auth


def _log_export_job_public(job: dict[str, Any]) -> dict[str, Any]:
    return {
        "success": True,
        "job_id": job["id"],
        "state": job["state"],
        "fetched": int(job.get("fetched") or 0),
        "total": int(job.get("total") or 0),
        "message": job.get("message") or "",
        "filename": job.get("filename") or "",
        "download": "",
        "is_admin": job.get("is_admin"),
        "gateway_total": int(job.get("gateway_total") or 0),
        "model_query": job.get("model_query") or "",
        "error": job.get("error") or "",
    }


def _update_log_export_job(job_id: str, **fields: Any) -> None:
    with _LOG_EXPORT_JOBS_LOCK:
        job = _LOG_EXPORT_JOBS.get(job_id)
        if not job:
            return
        job.update(fields)
        job["updated_at"] = time.time()


def _purge_log_export_jobs() -> None:
    cutoff = time.time() - 3600
    with _LOG_EXPORT_JOBS_LOCK:
        stale = [key for key, job in _LOG_EXPORT_JOBS.items() if float(job.get("updated_at") or 0) < cutoff]
        for key in stale:
            _LOG_EXPORT_JOBS.pop(key, None)


@app.post("/api/logs-export")
def logs_export():
    """启动后台导出任务，立即返回 job_id；进度用 GET /api/logs-export/jobs/<id> 轮询。"""
    _ensure_batch()
    _purge_log_export_jobs()
    body = request.get_json(silent=True) or {}
    try:
        base_url, export_format, filters, auth = _parse_logs_export_request(body)
    except ValueError as exc:
        return jsonify({"success": False, "message": str(exc)}), 400

    job_id = str(uuid.uuid4())
    cancel_event = threading.Event()
    job = {
        "id": job_id,
        "state": "running",
        "fetched": 0,
        "total": 0,
        "message": "正在登录 NA…",
        "filename": "",
        "download": "",
        "is_admin": None,
        "error": "",
        "cancel": cancel_event,
        "updated_at": time.time(),
    }
    with _LOG_EXPORT_JOBS_LOCK:
        _LOG_EXPORT_JOBS[job_id] = job

    def progress(fetched: int, total: int, message: str = "") -> None:
        _update_log_export_job(
            job_id,
            fetched=int(fetched),
            total=int(total),
            message=str(message or ""),
            state="running",
        )

    def should_cancel() -> bool:
        return cancel_event.is_set()

    def worker() -> None:
        cancelled_cls = BATCH.get("LogExportCancelled")
        try:
            if should_cancel():
                raise RuntimeError("已终止导出")
            _update_log_export_job(job_id, message="正在登录 NA…")
            client = BATCH["NewAPIClient"](base_url)
            BATCH["authenticate_client"](client, auth)
            _update_log_export_job(job_id, message="登录成功，开始分页拉取…")
            result = BATCH["run_logs_export"](
                client,
                is_admin=client.is_admin(),
                filters=filters,
                export_format=export_format,
                progress=progress,
                cancel=should_cancel,
                dest_dir=_ensure_excel_dir(),
            )
            if should_cancel():
                raise RuntimeError("已终止导出")
            if result.total == 0:
                if result.gateway_total and result.model_query:
                    msg = (
                        f"网关该条件下有 {result.gateway_total} 条，"
                        f"但模型名「{result.model_query}」一条都没匹配。"
                        f"请清空「模型名称」再导出这 {result.gateway_total} 条，"
                        f"或改成日志里实际出现的模型名。"
                    )
                else:
                    msg = "当前筛选条件下没有使用日志"
                _update_log_export_job(
                    job_id,
                    state="error",
                    error=msg,
                    message=msg,
                    fetched=0,
                    total=int(result.gateway_total or 0),
                    gateway_total=int(result.gateway_total or 0),
                    model_query=result.model_query or "",
                )
                return
            if result.data:
                _store_excel_bytes(result.filename, result.data)
            done_message = "导出完成"
            if result.model_query and result.gateway_total > result.total:
                done_message = (
                    f"导出完成：{result.total} 条"
                    f"（网关共 {result.gateway_total} 条，已按模型名「{result.model_query}」筛选）"
                )
            _update_log_export_job(
                job_id,
                state="done",
                fetched=int(result.total),
                total=int(result.total),
                filename=result.filename,
                is_admin=bool(result.is_admin),
                download=f"/api/logs-export/file/{result.filename}",
                message=done_message,
                gateway_total=int(result.gateway_total or result.total),
                model_query=result.model_query or "",
            )
        except Exception as exc:  # noqa: BLE001
            if should_cancel() or (cancelled_cls and isinstance(exc, cancelled_cls)) or str(exc) == "已终止导出":
                _update_log_export_job(job_id, state="cancelled", error="已终止导出", message="已终止导出")
                return
            _update_log_export_job(
                job_id,
                state="error",
                error=_user_facing_error(exc),
                message=_user_facing_error(exc),
            )

    threading.Thread(target=worker, daemon=True, name=f"logs-export-{job_id[:8]}").start()
    return jsonify(_log_export_job_public(job))


@app.get("/api/logs-export/jobs/<job_id>")
def logs_export_job(job_id: str):
    if not _LOG_EXPORT_JOB_RE.fullmatch(job_id):
        return jsonify({"success": False, "message": "非法任务 ID"}), 400
    with _LOG_EXPORT_JOBS_LOCK:
        job = _LOG_EXPORT_JOBS.get(job_id)
        if not job:
            return jsonify({"success": False, "message": "导出任务不存在或已过期"}), 404
        snapshot = _log_export_job_public(job)
    return jsonify(snapshot)


@app.post("/api/logs-export/jobs/<job_id>/cancel")
def logs_export_job_cancel(job_id: str):
    if not _LOG_EXPORT_JOB_RE.fullmatch(job_id):
        return jsonify({"success": False, "message": "非法任务 ID"}), 400
    with _LOG_EXPORT_JOBS_LOCK:
        job = _LOG_EXPORT_JOBS.get(job_id)
        if not job:
            return jsonify({"success": False, "message": "导出任务不存在或已过期"}), 404
        cancel_event = job.get("cancel")
        if isinstance(cancel_event, threading.Event):
            cancel_event.set()
        if job.get("state") == "running":
            job["message"] = "正在终止导出…"
            job["updated_at"] = time.time()
        snapshot = _log_export_job_public(job)
    return jsonify(snapshot)


@app.get("/api/logs-export/info")
def logs_export_info():
    path = _latest_logs_export_path()
    exists = bool(path and path.is_file())
    return jsonify(
        {
            "success": True,
            "data": {
                "filename": path.name if exists else "",
                "path": _rel_to_root(path) if exists else "",
                "exists": exists,
            },
        }
    )


@app.get("/api/logs-export/download")
def logs_export_download_latest():
    path = _latest_logs_export_path()
    if not path or not path.is_file():
        return jsonify({"success": False, "message": "尚未生成使用日志文件，请先导出"}), 404
    return _send_excel_attachment(path)


@app.get("/api/logs-export/file/<filename>")
def logs_export_file(filename: str):
    if not _LOG_EXPORT_FILE_RE.fullmatch(filename):
        return jsonify({"success": False, "message": "非法文件名"}), 400
    path = EXCEL_DIR / filename
    if not path.is_file():
        return jsonify({"success": False, "message": "导出文件不存在或已清理"}), 404
    return _send_excel_attachment(path)


@app.get("/api/data-summary/info")
def data_summary_info():
    _reload_batch_modules()
    excel_path = BATCH["latest_excel_path"](NEW_DIR)
    exists = bool(excel_path and excel_path.exists())
    summary = BATCH["summary_workbook_stats"](excel_path) if exists else None
    balance_path = BATCH["latest_balance_excel_path"](NEW_DIR)
    balance_exists = bool(balance_path and balance_path.exists())
    return jsonify(
        {
            "success": True,
            "data": {
                "filename": excel_path.name if exists else "",
                "path": _rel_to_root(excel_path) if exists else "",
                "exists": exists,
                "auto_created": False,
                "summary": summary,
                "envs": list(BATCH["ENVS"]),
                "sheets": {
                    "channels": [f"{env}-渠道管理" for env in BATCH["ENVS"]],
                    "tokens": [f"{env}-令牌管理" for env in BATCH["ENVS"]],
                    "duplicate_channels": "重复模型",
                    "duplicate_tokens": "重复模型相关令牌",
                },
                "balance": {
                    "filename": balance_path.name if balance_exists else "",
                    "path": _rel_to_root(balance_path) if balance_exists else "",
                    "exists": balance_exists,
                },
            },
        }
    )


@app.post("/api/data-summary/inspect-auth")
def data_summary_inspect_auth():
    """采集前审查各站是否需要登录两步验证（不带验证码试登录）。"""
    _reload_batch_modules()
    body = request.get_json(silent=True) or {}
    sites = BATCH["parse_summary_sites"](body.get("sites") or [])
    if not sites:
        return jsonify({"success": False, "message": "请至少配置一个网站（地址 + 用户名 + 密码）"}), 400

    include_keys = bool(body.get("include_keys") or body.get("include_channel_keys"))
    items = BATCH["inspect_summary_sites_auth"](sites, include_keys=include_keys)
    collectable = [it for it in items if it.get("collectable")]
    need_prompt = [it for it in collectable if it.get("needs_otp_prompt")]
    skip_prompt = len(collectable) - len(need_prompt)
    return jsonify(
        {
            "success": True,
            "message": (
                f"审查完成：无需验证码 {skip_prompt} 个，需弹窗 {len(need_prompt)} 个"
                + (f"，不可采集 {len(items) - len(collectable)} 个" if len(items) != len(collectable) else "")
            ),
            "data": {"items": items},
        }
    )


@app.post("/api/data-summary/collect")
def data_summary_collect():
    _reload_batch_modules()
    body = request.get_json(silent=True) or {}
    sites = BATCH["parse_summary_sites"](body.get("sites") or [])
    if not sites:
        return jsonify({"success": False, "message": "请至少配置一个网站（地址 + 用户名 + 密码）"}), 400

    include_keys = bool(body.get("include_keys") or body.get("include_channel_keys"))
    if include_keys:
        missing = [
            (s.label or s.base_url)
            for s in sites
            if not BATCH["has_otp_source"](getattr(s, "otp_code", ""), totp_secret=getattr(s, "totp_secret", ""))
        ]
        if missing:
            return jsonify(
                {
                    "success": False,
                    "message": "含渠道密钥导出须为每个站点填写二次验证码（或在 env/sites.json 预置 totp_secret）："
                    + "、".join(missing[:5]),
                }
            ), 400

    output_path = None
    raw_output = str(body.get("output_path") or body.get("target_file") or "").strip()
    if raw_output:
        output_path = (NEW_DIR / raw_output.replace("\\", "/")).resolve()
        try:
            output_path.relative_to(NEW_DIR.resolve())
        except ValueError:
            return jsonify({"success": False, "message": "output_path 无效"}), 400
        if output_path.suffix.lower() != ".xlsx":
            return jsonify({"success": False, "message": "output_path 须为 .xlsx 文件"}), 400
        try:
            output_path.relative_to(_ensure_excel_dir().resolve())
        except ValueError:
            return jsonify({"success": False, "message": "output_path 须位于 excel/ 目录"}), 400

    excel_path = BATCH["default_excel_path"](NEW_DIR)

    try:
        stats, saved_path = BATCH["run_data_summary_collect"](
            sites=sites,
            excel_path=excel_path,
            include_keys=include_keys,
            output_path=output_path,
            staging=bool(body.get("staging")),
        )
        message = (
            f"采集完成：成功 {stats.sites_ok} 个站点"
            + (f"，失败 {stats.sites_failed} 个" if stats.sites_failed else "")
        )
        if include_keys:
            message += f"；密钥获取成功 {stats.keys_fetched}"
            if stats.keys_failed:
                message += f"，失败 {stats.keys_failed}"
        return jsonify(
            {
                "success": stats.sites_ok > 0,
                "message": message,
                "data": {
                    "file": _rel_to_root(saved_path),
                    "filename": saved_path.name,
                    "sites_ok": stats.sites_ok,
                    "sites_failed": stats.sites_failed,
                    "channels_added": stats.channels_added,
                    "tokens_added": stats.tokens_added,
                    "duplicate_channels": stats.duplicate_channels,
                    "duplicate_tokens": stats.duplicate_tokens,
                    "channels_skipped_duplicate": stats.channels_skipped_duplicate,
                    "tokens_skipped_duplicate": stats.tokens_skipped_duplicate,
                    "channels_skipped_by_env": stats.channels_skipped_by_env,
                    "tokens_skipped_by_env": stats.tokens_skipped_by_env,
                    "channels_in_sheet": stats.channels_in_sheet,
                    "tokens_in_sheet": stats.tokens_in_sheet,
                    "site_results": stats.site_results,
                    "errors": stats.errors,
                    "include_keys": include_keys,
                    "keys_fetched": stats.keys_fetched,
                    "keys_failed": stats.keys_failed,
                },
            }
        )
    except Exception as exc:  # noqa: BLE001
        return jsonify({"success": False, "message": str(exc)}), 400


@app.post("/api/data-summary/finalize")
def data_summary_finalize():
    """分站采集结束后，把 .part.xlsx 发布为正式文件，之后「下载 Excel」才指向它。"""
    _reload_batch_modules()
    body = request.get_json(silent=True) or {}
    raw = str(body.get("path") or body.get("file") or body.get("output_path") or "").strip()
    if not raw:
        return jsonify({"success": False, "message": "缺少待发布文件路径"}), 400
    path = (NEW_DIR / raw.replace("\\", "/")).resolve()
    try:
        path.relative_to(_ensure_excel_dir().resolve())
    except ValueError:
        return jsonify({"success": False, "message": "文件须位于 excel/ 目录"}), 400
    try:
        published = BATCH["publish_staging_excel"](path)
    except FileNotFoundError as exc:
        return jsonify({"success": False, "message": str(exc)}), 404
    except Exception as exc:  # noqa: BLE001
        return jsonify({"success": False, "message": str(exc)}), 400
    return jsonify(
        {
            "success": True,
            "message": f"已发布 {_rel_to_root(published)}，请点「下载 Excel」",
            "data": {
                "file": _rel_to_root(published),
                "filename": published.name,
            },
        }
    )


@app.post("/api/data-summary/fill-keys")
def data_summary_fill_keys():
    """对最新 Excel 中缺失的渠道密钥分批补全（应对上游 CriticalRateLimit）。"""
    _reload_batch_modules()
    body = request.get_json(silent=True) or {}
    sites = BATCH["parse_summary_sites"](body.get("sites") or [])
    if len(sites) != 1:
        return jsonify({"success": False, "message": "继续补全密钥请每次只选 1 个站点"}), 400
    site = sites[0]
    if not BATCH["has_otp_source"](getattr(site, "otp_code", ""), totp_secret=getattr(site, "totp_secret", "")):
        return jsonify({"success": False, "message": "请填写该站点的二次验证码，或在 env/sites.json 预置 totp_secret"}), 400

    try:
        result, saved_path = BATCH["fill_missing_channel_keys"](
            site=site,
            root_dir=NEW_DIR,
        )
        return jsonify(
            {
                "success": True,
                "message": result.get("message") or "补全完成",
                "data": {
                    **result,
                    "file": _rel_to_root(saved_path),
                    "filename": saved_path.name,
                },
            }
        )
    except Exception as exc:  # noqa: BLE001
        return jsonify({"success": False, "message": str(exc)}), 400


@app.get("/api/data-summary/download")
def data_summary_download():
    _reload_batch_modules()
    try:
        excel_path = _excel_query_path(
            "file",
            "id",
            fallback=BATCH["latest_excel_path"](NEW_DIR) or BATCH["default_excel_path"](NEW_DIR),
        )
    except (ValueError, FileNotFoundError) as exc:
        return jsonify({"success": False, "message": str(exc)}), 400
    if not excel_path or not excel_path.exists():
        return jsonify({"success": False, "message": "Excel 文件尚未生成，请先执行采集"}), 404
    return _send_excel_attachment(excel_path)


@app.post("/api/batch-create")
def batch_create():
    body = request.get_json(silent=True) or {}
    base_url = _parse_base_url(body.get("base_url", ""))
    default_key = str(body.get("default_key", "")).strip()
    batch_text = str(body.get("batch_text", "")).strip()

    if not base_url:
        return jsonify({"success": False, "message": "请填写 New API 地址"}), 400
    if not batch_text:
        return jsonify({"success": False, "message": "请填写批量数据"}), 400

    auth = _parse_auth(body)

    try:
        result = BATCH["run_batch_create"](
            base_url=base_url,
            batch_text=batch_text,
            default_key=default_key,
            auth=auth,
        )
        return jsonify(
            {
                "success": result.failed_count == 0,
                "message": (
                    f"完成：成功 {result.success_count}，跳过 {result.skipped_count}，"
                    f"失败 {result.failed_count}"
                ),
                "data": {
                    "total": result.total,
                    "success_count": result.success_count,
                    "skipped_count": result.skipped_count,
                    "failed_count": result.failed_count,
                    "items": result.items,
                },
            }
        )
    except Exception as exc:  # noqa: BLE001
        return jsonify({"success": False, "message": _user_facing_error(exc)}), 400


@app.post("/api/channel-test")
def api_channel_test():
    body = request.get_json(silent=True) or {}
    base_url = _parse_base_url(body.get("base_url", ""))
    if not base_url:
        return jsonify({"success": False, "message": "请填写 New API 地址"}), 400
    try:
        channel_id = int(body.get("channel_id") or body.get("id") or 0)
    except (TypeError, ValueError):
        channel_id = 0
    if channel_id <= 0:
        return jsonify({"success": False, "message": "缺少渠道 ID，请先完成创建后再测试"}), 400
    models = body.get("models")
    if models is None:
        models = body.get("model") or ""
    try:
        result = BATCH["run_channel_test"](
            base_url=base_url,
            auth=_parse_auth(body),
            channel_id=channel_id,
            models=models,
            name=str(body.get("name") or "").strip(),
        )
        return jsonify(
            {
                "success": bool(result.get("success")),
                "message": result.get("message") or "",
                "data": result,
            }
        )
    except Exception as exc:  # noqa: BLE001
        return jsonify({"success": False, "message": _user_facing_error(exc)}), 400


@app.post("/api/batch-update-channels")
def batch_update_channels():
    body = request.get_json(silent=True) or {}
    base_url = _parse_base_url(body.get("base_url", ""))
    batch_text = str(body.get("batch_text", "")).strip()
    dry_run = bool(body.get("dry_run", True))
    # 实际写入必须由前端显式确认；预更新的差异展示由业务层统一处理。
    overwrite_remark = body.get("overwrite_remark") is True

    if not base_url:
        return jsonify({"success": False, "message": "请填写 New API 地址"}), 400
    if not batch_text:
        return jsonify({"success": False, "message": "请填写批量数据"}), 400

    try:
        result = BATCH["run_channel_batch_update"](
            base_url=base_url,
            batch_text=batch_text,
            auth=_parse_auth(body),
            dry_run=dry_run,
            overwrite_remark=overwrite_remark,
        )
        if result.dry_run:
            message = (
                f"预更新完成：将更新 {result.matched_count} 条，"
                f"跳过 {result.skipped_count}，失败 {result.failed_count}。"
                "请确认清单后点击「确认更新」"
            )
        else:
            message = (
                f"更新完成：已更新 {result.updated_count} 条，"
                f"跳过 {result.skipped_count}，失败 {result.failed_count}"
            )
        return jsonify(
            {
                "success": result.failed_count == 0,
                "message": message,
                "data": {
                    "total": result.total,
                    "matched_count": result.matched_count,
                    "updated_count": result.updated_count,
                    "skipped_count": result.skipped_count,
                    "failed_count": result.failed_count,
                    "remark_overwrite_candidates": result.remark_overwrite_candidates,
                    "dry_run": result.dry_run,
                    "items": result.items,
                },
            }
        )
    except Exception as exc:  # noqa: BLE001
        return jsonify({"success": False, "message": _user_facing_error(exc)}), 400


@app.post("/api/channel-remark-sync")
def channel_remark_sync():
    """将所有渠道的 base_url 追加到 New API 的管理员备注。"""
    body = request.get_json(silent=True) or {}
    base_url = _parse_base_url(body.get("base_url", ""))
    dry_run = bool(body.get("dry_run", True))
    if not base_url:
        return jsonify({"success": False, "message": "请填写 New API 地址"}), 400

    try:
        result = BATCH["run_channel_remark_sync"](
            base_url=base_url,
            auth=_parse_auth(body),
            dry_run=dry_run,
        )
        if dry_run:
            message = (
                f"备注同步预览完成：将同步 {result.matched_count} 条，"
                f"跳过 {result.skipped_count}，未完成 {result.failed_count} 条。"
            )
            if result.matched_count:
                message += "请核对清单后点击「确认同步备注」"
        else:
            message = (
                f"备注同步完成：已同步 {result.updated_count} 条，"
                f"跳过 {result.skipped_count}，未完成 {result.failed_count} 条。"
            )
        if result.failed_count:
            message += "失败项已列出渠道名称和原因。"
        return jsonify(
            {
                "success": result.failed_count == 0,
                "message": message,
                "data": {
                    "total": result.total,
                    "matched_count": result.matched_count,
                    "updated_count": result.updated_count,
                    "skipped_count": result.skipped_count,
                    "failed_count": result.failed_count,
                    "dry_run": result.dry_run,
                    "items": result.items,
                },
            }
        )
    except Exception as exc:  # noqa: BLE001
        return jsonify({"success": False, "message": _user_facing_error(exc)}), 400


@app.post("/api/channel-models")
def channel_models():
    body = request.get_json(silent=True) or {}
    base_url = _parse_base_url(body.get("base_url", ""))
    if not base_url:
        return jsonify({"success": False, "message": "请填写 New API 地址"}), 400

    try:
        data = BATCH["fetch_channel_models"](base_url=base_url, auth=_parse_auth(body))
        return jsonify({"success": True, "data": data})
    except Exception as exc:  # noqa: BLE001
        return jsonify({"success": False, "message": str(exc)}), 400


@app.post("/api/token-batch-create")
def token_batch_create():
    body = request.get_json(silent=True) or {}
    base_url = _parse_base_url(body.get("base_url", ""))
    batch_text = str(body.get("batch_text", "")).strip()

    if not base_url:
        return jsonify({"success": False, "message": "请填写 New API 地址"}), 400
    if not batch_text:
        return jsonify({"success": False, "message": "请填写批量数据"}), 400

    try:
        result = BATCH["run_token_batch_create"](
            base_url=base_url,
            batch_text=batch_text,
            auth=_parse_auth(body),
        )
        return jsonify(
            {
                "success": result.failed_count == 0,
                "message": (
                    f"完成：成功 {result.success_count}，跳过 {result.skipped_count}，"
                    f"失败 {result.failed_count}"
                ),
                "data": {
                    "total": result.total,
                    "success_count": result.success_count,
                    "skipped_count": result.skipped_count,
                    "failed_count": result.failed_count,
                    "items": result.items,
                },
            }
        )
    except Exception as exc:  # noqa: BLE001
        return jsonify({"success": False, "message": _user_facing_error(exc)}), 400


@app.post("/api/token-batch-update")
def token_batch_update():
    body = request.get_json(silent=True) or {}
    base_url = _parse_base_url(body.get("base_url", ""))
    batch_text = str(body.get("batch_text", "")).strip()
    dry_run = bool(body.get("dry_run", True))

    if not base_url:
        return jsonify({"success": False, "message": "请填写 New API 地址"}), 400
    if not batch_text:
        return jsonify({"success": False, "message": "请填写批量数据"}), 400

    try:
        result = BATCH["run_token_batch_quota_update"](
            base_url=base_url,
            batch_text=batch_text,
            auth=_parse_auth(body),
            dry_run=dry_run,
        )
        if result.dry_run:
            message = (
                f"预更新完成：将更新 {result.matched_count} 条，"
                f"跳过 {result.skipped_count}，失败 {result.failed_count}。"
                "请确认清单后点击「确认更新」"
            )
        else:
            message = (
                f"更新完成：已更新 {result.updated_count} 条，"
                f"跳过 {result.skipped_count}，失败 {result.failed_count}"
            )
        return jsonify(
            {
                "success": result.failed_count == 0,
                "message": message,
                "data": {
                    "total": result.total,
                    "matched_count": result.matched_count,
                    "updated_count": result.updated_count,
                    "skipped_count": result.skipped_count,
                    "failed_count": result.failed_count,
                    "dry_run": result.dry_run,
                    "items": result.items,
                },
            }
        )
    except Exception as exc:  # noqa: BLE001
        return jsonify({"success": False, "message": _user_facing_error(exc)}), 400


@app.post("/api/token-export")
def token_export():
    body = request.get_json(silent=True) or {}
    base_url = _parse_base_url(body.get("base_url", ""))
    if not base_url:
        return jsonify({"success": False, "message": "请填写 New API 地址"}), 400

    pasted_keys = str(body.get("pasted_keys") or "").strip()
    try:
        result = BATCH["export_all_tokens_text"](
            base_url=base_url,
            auth=_parse_auth(body),
            pasted_keys=pasted_keys,
        )
        message = f"已导出 {result.total} 条令牌，明文秘钥 {result.key_resolved} 条"
        if result.key_missing:
            message += f"，{result.key_missing} 条未获取"
            if result.key_api_fetched == 0 and not pasted_keys:
                message += "。列表 API 已脱敏，请确认站点支持 /api/token/batch/keys，或在「从网页粘贴密钥」框粘贴名称+密钥"
            elif not pasted_keys and result.key_api_fetched > 0:
                pass
            elif not pasted_keys:
                message += "。部分秘钥未能通过 key API 获取，可尝试网页「复制密钥」后粘贴"
            elif result.pasted_matched == 0:
                message += "。粘贴内容未匹配到任何 sk- 密钥，请检查格式"
        if result.api_masked and not pasted_keys:
            message += f"（API 样例: {result.sample_api_key or '空'}...）"
        if result.key_sources:
            message += f"（来源: {'、'.join(result.key_sources)}）"
        return jsonify(
            {
                "success": True,
                "message": message,
                "data": {
                    "text": result.text,
                    "total": result.total,
                    "key_resolved": result.key_resolved,
                    "key_missing": result.key_missing,
                    "key_sources": result.key_sources,
                    "api_masked": result.api_masked,
                    "key_api_fetched": result.key_api_fetched,
                    "pasted_matched": result.pasted_matched,
                    "sample_api_key": result.sample_api_key,
                },
            }
        )
    except Exception as exc:  # noqa: BLE001
        return jsonify({"success": False, "message": str(exc)}), 400


@app.post("/api/groups-list")
def groups_list():
    body = request.get_json(silent=True) or {}
    base_url = _parse_base_url(body.get("base_url", ""))
    if not base_url:
        return jsonify({"success": False, "message": "请填写 New API 地址"}), 400

    try:
        groups = BATCH["list_site_groups"](base_url=base_url, auth=_parse_auth(body))
        return jsonify({"success": True, "data": {"groups": groups, "count": len(groups)}})
    except Exception as exc:  # noqa: BLE001
        return jsonify({"success": False, "message": str(exc)}), 400


@app.post("/api/groups-members")
def groups_members():
    """列出某分组下的渠道与令牌（供勾选切换）。"""
    body = request.get_json(silent=True) or {}
    base_url = _parse_base_url(body.get("base_url", ""))
    source_group = str(body.get("source_group") or body.get("group") or "").strip()
    if not base_url:
        return jsonify({"success": False, "message": "请填写 New API 地址"}), 400
    if not source_group:
        return jsonify({"success": False, "message": "请选择源分组"}), 400
    try:
        data = BATCH["list_group_members"](
            base_url=base_url,
            auth=_parse_auth(body),
            source_group=source_group,
        )
        return jsonify(
            {
                "success": True,
                "message": (
                    f"分组「{source_group}」：渠道 {data.get('channel_count') or 0} 条，"
                    f"令牌 {data.get('token_count') or 0} 条"
                ),
                "data": data,
            }
        )
    except ValueError as exc:
        return jsonify({"success": False, "message": str(exc)}), 400
    except Exception as exc:  # noqa: BLE001
        return jsonify({"success": False, "message": str(exc)}), 400


@app.post("/api/groups-switch")
def groups_switch():
    """将勾选的渠道或令牌从源分组切换到目标分组。"""
    body = request.get_json(silent=True) or {}
    base_url = _parse_base_url(body.get("base_url", ""))
    source_group = str(body.get("source_group") or "").strip()
    target_group = str(body.get("target_group") or "").strip()
    kind = str(body.get("kind") or "channel").strip()
    dry_run = bool(body.get("dry_run", False))
    ids = body.get("ids") or body.get("channel_ids") or body.get("token_ids")
    if not base_url:
        return jsonify({"success": False, "message": "请填写 New API 地址"}), 400
    try:
        result = BATCH["run_group_switch"](
            base_url=base_url,
            auth=_parse_auth(body),
            source_group=source_group,
            target_group=target_group,
            kind=kind,
            ids=ids,
            dry_run=dry_run,
        )
        noun = "渠道" if result.kind == "channel" else "令牌"
        if result.dry_run:
            message = (
                f"预切换完成：匹配 {result.matched_count} 条{noun}，"
                f"跳过 {result.skipped_count}，失败 {result.failed_count}"
            )
        else:
            message = (
                f"切换完成：已改 {result.updated_count} 条{noun}，"
                f"跳过 {result.skipped_count}，失败 {result.failed_count}"
            )
        return jsonify(
            {
                "success": result.failed_count == 0,
                "message": message,
                "data": {
                    "total": result.total,
                    "matched_count": result.matched_count,
                    "updated_count": result.updated_count,
                    "skipped_count": result.skipped_count,
                    "failed_count": result.failed_count,
                    "dry_run": result.dry_run,
                    "kind": result.kind,
                    "source_group": result.source_group,
                    "target_group": result.target_group,
                    "items": result.items,
                    **result.extra,
                },
            }
        )
    except ValueError as exc:
        return jsonify({"success": False, "message": str(exc)}), 400
    except Exception as exc:  # noqa: BLE001
        return jsonify({"success": False, "message": str(exc)}), 400


@app.post("/api/groups-create")
def groups_create():
    body = request.get_json(silent=True) or {}
    base_url = _parse_base_url(body.get("base_url", ""))
    groups_text = str(body.get("groups_text", "")).strip()
    default_ratio = float(body.get("default_ratio", 1))

    if not base_url:
        return jsonify({"success": False, "message": "请填写 New API 地址"}), 400
    if not groups_text:
        return jsonify({"success": False, "message": "请填写要创建的分组名"}), 400

    try:
        result = BATCH["run_group_create"](
            base_url=base_url,
            groups_text=groups_text,
            auth=_parse_auth(body),
            default_ratio=default_ratio,
        )
        return jsonify(
            {
                "success": result.failed_count == 0,
                "message": (
                    f"完成：新建 {result.created_count}，已存在 {result.skipped_count}，"
                    f"失败 {result.failed_count}；站点共 {len(result.groups)} 个分组"
                ),
                "data": {
                    "total": result.total,
                    "created_count": result.created_count,
                    "skipped_count": result.skipped_count,
                    "failed_count": result.failed_count,
                    "groups": result.groups,
                    "items": result.items,
                },
            }
        )
    except ValueError as exc:
        return jsonify({"success": False, "message": str(exc)}), 400
    except Exception as exc:  # noqa: BLE001
        return jsonify({"success": False, "message": str(exc)}), 400


def _delete_response(result, *, noun: str):
    if result.dry_run:
        message = (
            f"预删除完成：匹配 {result.matched_count} 条，"
            f"跳过 {result.skipped_count}，失败 {result.failed_count}。"
            "请确认清单后点击「确认删除」"
        )
    else:
        message = (
            f"删除完成：已删 {result.deleted_count} 条，"
            f"跳过 {result.skipped_count}，失败 {result.failed_count}"
        )
    payload = {
        "success": result.failed_count == 0,
        "message": message,
        "data": {
            "total": result.total,
            "matched_count": result.matched_count,
            "deleted_count": result.deleted_count,
            "skipped_count": result.skipped_count,
            "failed_count": result.failed_count,
            "dry_run": result.dry_run,
            "items": result.items,
            **result.extra,
        },
    }
    return jsonify(payload), 200


@app.post("/api/batch-delete-channels")
def batch_delete_channels():
    body = request.get_json(silent=True) or {}
    base_url = _parse_base_url(body.get("base_url", ""))
    batch_text = str(body.get("batch_text", "")).strip()
    dry_run = bool(body.get("dry_run", True))
    channel_ids = body.get("channel_ids") or body.get("ids")

    if not base_url:
        return jsonify({"success": False, "message": "请填写 New API 地址"}), 400
    if not batch_text and not channel_ids:
        return jsonify({"success": False, "message": "请填写批量数据或指定渠道 ID"}), 400

    try:
        result = BATCH["run_channel_batch_delete"](
            base_url=base_url,
            batch_text=batch_text,
            auth=_parse_auth(body),
            dry_run=dry_run,
            channel_ids=channel_ids,
        )
        return _delete_response(result, noun="渠道")
    except Exception as exc:  # noqa: BLE001
        return jsonify({"success": False, "message": str(exc)}), 400


def _status_response(result):
    action_label = "启用" if result.action == "enable" else "禁用"
    mode = getattr(result, "match_mode", "") or result.extra.get("match_mode", "")
    mode_hint = {
        "upstream": "按上游模型",
        "type": "按渠道类型全部",
        "ids": "按勾选/指定 ID",
        "name": "按名称+分组",
    }.get(mode, "")
    prefix = f"[{mode_hint}] " if mode_hint else ""
    if result.dry_run:
        message = (
            f"{prefix}预{action_label}完成：匹配 {result.matched_count} 条，"
            f"跳过 {result.skipped_count}，失败 {result.failed_count}。"
            f"请确认清单后执行确认操作"
        )
    else:
        message = (
            f"{prefix}{action_label}完成：已更新 {result.updated_count} 条，"
            f"跳过 {result.skipped_count}，失败 {result.failed_count}"
        )
    payload = {
        "success": result.failed_count == 0,
        "message": message,
        "data": {
            "total": result.total,
            "matched_count": result.matched_count,
            "updated_count": result.updated_count,
            "skipped_count": result.skipped_count,
            "failed_count": result.failed_count,
            "dry_run": result.dry_run,
            "items": result.items,
            **result.extra,
        },
    }
    return jsonify(payload), 200


@app.post("/api/batch-channel-status")
def batch_channel_status():
    body = request.get_json(silent=True) or {}
    base_url = _parse_base_url(body.get("base_url", ""))
    model_text = str(body.get("model_text") or body.get("models_text") or "").strip()
    models = body.get("models")
    if isinstance(models, str):
        model_text = model_text or models
        models = None
    elif not isinstance(models, list):
        models = None
    channel_type = str(body.get("channel_type") or "").strip()
    action = str(body.get("action") or "").strip()
    dry_run = bool(body.get("dry_run", True))
    match_mode = str(body.get("match_mode") or "upstream").strip() or "upstream"
    channel_ids = body.get("channel_ids") or body.get("ids")
    batch_text = str(body.get("batch_text") or "").strip()
    name_mode = match_mode in {"name", "names", "name_group", "batch"}

    if not base_url:
        return jsonify({"success": False, "message": "请填写 New API 地址"}), 400
    if name_mode:
        if not batch_text:
            return jsonify({"success": False, "message": "请填写批量数据（名称 分组）"}), 400
    elif match_mode in {"upstream", "model", "models"} and not model_text and not models:
        return jsonify({"success": False, "message": "请填写上游模型列表"}), 400
    if not name_mode and match_mode in {"type", "all", "type_all"} and not channel_type:
        return jsonify({"success": False, "message": "请指定渠道类型"}), 400
    if not name_mode and match_mode in {"ids", "id", "channel_ids"} and not channel_ids:
        return jsonify({"success": False, "message": "请指定渠道 ID"}), 400
    if not name_mode and match_mode not in {"ids", "id", "channel_ids"} and not channel_type:
        return jsonify({"success": False, "message": "请指定渠道类型"}), 400
    if not action:
        return jsonify({"success": False, "message": "请指定 action（enable / disable）"}), 400

    try:
        result = BATCH["run_channel_batch_status"](
            base_url=base_url,
            auth=_parse_auth(body),
            model_text=model_text,
            models=models,
            channel_type=channel_type,
            action=action,
            dry_run=dry_run,
            match_mode=match_mode,
            channel_ids=channel_ids,
            batch_text=batch_text,
        )
        return _status_response(result)
    except Exception as exc:  # noqa: BLE001
        return jsonify({"success": False, "message": str(exc)}), 400


def _parse_optional_float(raw: Any) -> float | None:
    if raw in (None, ""):
        return None
    try:
        return float(raw)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"数值无效: {raw}") from exc


def _parse_optional_timestamp(raw: Any) -> int | None:
    if raw in (None, ""):
        return None
    if isinstance(raw, bool):
        raise ValueError(f"时间无效: {raw}")
    if isinstance(raw, (int, float)):
        ts = int(raw)
        return ts if ts > 0 else None
    text = str(raw).strip()
    if not text:
        return None
    try:
        ts = int(float(text))
        return ts if ts > 0 else None
    except (TypeError, ValueError) as exc:
        raise ValueError(f"时间无效: {raw}") from exc


@app.post("/api/channel-balance-query")
def channel_balance_query():
    """查询渠道已用额度 / 剩余余额。

    - 传 ``sites``：多站点（数据汇总 Tab）
    - 传 ``base_url``：单站点（兼容）
    """
    body = request.get_json(silent=True) or {}
    query_used = bool(body.get("query_used", True))
    query_remain = bool(body.get("query_remain", True))
    if not query_used and not query_remain:
        return jsonify({"success": False, "message": "请至少勾选「已用」或「剩余」之一"}), 400

    status_raw = body.get("status")
    status_filter: int | None = None
    if status_raw not in (None, ""):
        try:
            status_filter = int(status_raw)
        except (TypeError, ValueError):
            return jsonify({"success": False, "message": "状态筛选无效"}), 400

    try:
        used_min = _parse_optional_float(body.get("used_min"))
        used_max = _parse_optional_float(body.get("used_max"))
        remain_min = _parse_optional_float(body.get("remain_min"))
        remain_max = _parse_optional_float(body.get("remain_max"))
        start_timestamp = _parse_optional_timestamp(
            body.get("start_timestamp", body.get("start_ts"))
        )
        end_timestamp = _parse_optional_timestamp(
            body.get("end_timestamp", body.get("end_ts"))
        )
    except ValueError as exc:
        return jsonify({"success": False, "message": str(exc)}), 400

    common = dict(
        query_used=query_used,
        query_remain=query_remain,
        channel_type=str(body.get("channel_type") or "").strip(),
        group=str(body.get("group") or "").strip(),
        keyword=str(body.get("keyword") or "").strip(),
        status=status_filter,
        used_preset=str(body.get("used_preset") or "all").strip() or "all",
        remain_preset=str(body.get("remain_preset") or "all").strip() or "all",
        used_min=used_min,
        used_max=used_max,
        remain_min=remain_min,
        remain_max=remain_max,
        time_preset=str(body.get("time_preset") or "all").strip() or "all",
        start_timestamp=start_timestamp,
        end_timestamp=end_timestamp,
        sort_by=str(body.get("sort_by") or "used_usd").strip() or "used_usd",
        sort_desc=bool(body.get("sort_desc", True)),
    )

    raw_sites = body.get("sites")
    try:
        if isinstance(raw_sites, list) and raw_sites:
            _reload_batch_modules()
            sites = BATCH["parse_summary_sites"](raw_sites)
            if not sites:
                return jsonify({"success": False, "message": "请至少填写一个有效站点地址"}), 400
            result = BATCH["run_multi_site_channel_balance_query"](sites=sites, **common)
            metrics = []
            if result.query_used:
                metrics.append("已用")
            if result.query_remain:
                metrics.append("剩余")
            message = (
                f"多站点渠道余额查询完成（{'+'.join(metrics)}）："
                f"成功 {result.sites_ok} 站，失败 {result.sites_failed} 站，命中 {result.matched_count} 条"
            )
            return jsonify(
                {
                    "success": result.sites_ok > 0,
                    "message": message,
                    "data": {
                        "multi_site": True,
                        "sites_ok": result.sites_ok,
                        "sites_failed": result.sites_failed,
                        "matched_count": result.matched_count,
                        "count": result.matched_count,
                        "query_used": result.query_used,
                        "query_remain": result.query_remain,
                        "items": result.items,
                        "by_env": {k: len(v) for k, v in result.by_env.items()},
                        "site_results": result.site_results,
                        "errors": result.errors,
                        "presets": result.presets,
                        "sheet_names": result.sheet_names,
                        "time_range": result.time_range,
                    },
                }
            ), 200

        base_url = _parse_base_url(body.get("base_url", ""))
        if not base_url:
            return jsonify({"success": False, "message": "请填写 New API 地址或配置站点列表"}), 400
        result = BATCH["run_channel_balance_query"](
            base_url=base_url,
            auth=_parse_auth(body),
            **common,
        )
        metrics = []
        if result.query_used:
            metrics.append("已用")
        if result.query_remain:
            metrics.append("剩余")
        message = (
            f"渠道余额查询完成（{'+'.join(metrics)}）："
            f"站点共 {result.total} 条，命中 {result.matched_count} 条"
        )
        return jsonify(
            {
                "success": True,
                "message": message,
                "data": {
                    "multi_site": False,
                    "total": result.total,
                    "matched_count": result.matched_count,
                    "count": result.matched_count,
                    "query_used": result.query_used,
                    "query_remain": result.query_remain,
                    "quota_per_unit": result.quota_per_unit,
                    "channel_type": result.channel_type,
                    "type_id": result.type_id,
                    "used_preset": result.used_preset,
                    "remain_preset": result.remain_preset,
                    "items": result.items,
                    "presets": result.presets,
                    **result.extra,
                },
            }
        ), 200
    except ValueError as exc:
        return jsonify({"success": False, "message": str(exc)}), 400
    except Exception as exc:  # noqa: BLE001
        return jsonify({"success": False, "message": str(exc)}), 400


@app.post("/api/channel-balance-export")
def channel_balance_export():
    """导出渠道余额 Excel；多环境时分表名为 test/uat/prod-渠道余额。"""
    body = request.get_json(silent=True) or {}
    include_used = bool(body.get("query_used", body.get("include_used", True)))
    include_remain = bool(body.get("query_remain", body.get("include_remain", True)))
    by_env = bool(body.get("by_env", True))
    raw_items = body.get("items")
    items: list = []
    if isinstance(raw_items, list) and raw_items:
        items = [item for item in raw_items if isinstance(item, dict)]
    else:
        return jsonify({"success": False, "message": "请先查询并传入要导出的渠道列表"}), 400

    if not items:
        return jsonify({"success": False, "message": "没有可导出的渠道数据"}), 400

    try:
        data, filename = BATCH["export_channel_balance_xlsx"](
            items,
            include_used=include_used,
            include_remain=include_remain,
            by_env=by_env,
        )
        path = _store_excel_bytes(filename, data)
        return jsonify(
            {
                "success": True,
                "message": f"已写入 excel/{path.name}，请点「下载 Excel」",
                "data": {
                    "file": _rel_to_root(path),
                    "filename": path.name,
                    "count": len(items),
                },
            }
        )
    except ValueError as exc:
        return jsonify({"success": False, "message": str(exc)}), 400
    except Exception as exc:  # noqa: BLE001
        return jsonify({"success": False, "message": str(exc)}), 400


@app.get("/api/channel-balance/download")
def channel_balance_download():
    """下载所选或最新一份渠道余额 Excel。"""
    _ensure_batch()
    try:
        excel_path = _excel_query_path("file", "id", fallback=BATCH["latest_balance_excel_path"](NEW_DIR))
    except (ValueError, FileNotFoundError) as exc:
        return jsonify({"success": False, "message": str(exc)}), 400
    if not excel_path or not excel_path.exists():
        return jsonify({"success": False, "message": "尚未生成渠道余额 Excel，请先导出"}), 404
    return _send_excel_attachment(excel_path)


@app.post("/api/token-batch-delete")
def token_batch_delete():
    body = request.get_json(silent=True) or {}
    base_url = _parse_base_url(body.get("base_url", ""))
    batch_text = str(body.get("batch_text", "")).strip()
    dry_run = bool(body.get("dry_run", True))

    if not base_url:
        return jsonify({"success": False, "message": "请填写 New API 地址"}), 400
    if not batch_text:
        return jsonify({"success": False, "message": "请填写批量数据"}), 400

    try:
        result = BATCH["run_token_batch_delete"](
            base_url=base_url,
            batch_text=batch_text,
            auth=_parse_auth(body),
            dry_run=dry_run,
        )
        return _delete_response(result, noun="令牌")
    except Exception as exc:  # noqa: BLE001
        return jsonify({"success": False, "message": str(exc)}), 400


@app.post("/api/token-batch-status")
def token_batch_status():
    body = request.get_json(silent=True) or {}
    base_url = _parse_base_url(body.get("base_url", ""))
    batch_text = str(body.get("batch_text", "")).strip()
    action = str(body.get("action") or "").strip()
    dry_run = bool(body.get("dry_run", True))

    if not base_url:
        return jsonify({"success": False, "message": "请填写 New API 地址"}), 400
    if not batch_text:
        return jsonify({"success": False, "message": "请填写批量数据"}), 400
    if not action:
        return jsonify({"success": False, "message": "请指定 action（enable / disable）"}), 400

    try:
        result = BATCH["run_token_batch_status"](
            base_url=base_url,
            batch_text=batch_text,
            auth=_parse_auth(body),
            action=action,
            dry_run=dry_run,
        )
        return _status_response(result)
    except Exception as exc:  # noqa: BLE001
        return jsonify({"success": False, "message": str(exc)}), 400


@app.post("/api/groups-delete")
def groups_delete():
    body = request.get_json(silent=True) or {}
    base_url = _parse_base_url(body.get("base_url", ""))
    groups_text = str(body.get("groups_text", "")).strip()
    dry_run = bool(body.get("dry_run", True))

    if not base_url:
        return jsonify({"success": False, "message": "请填写 New API 地址"}), 400
    if not groups_text:
        return jsonify({"success": False, "message": "请填写要删除的分组名"}), 400

    try:
        result = BATCH["run_group_delete"](
            base_url=base_url,
            groups_text=groups_text,
            auth=_parse_auth(body),
            dry_run=dry_run,
        )
        return _delete_response(result, noun="分组")
    except ValueError as exc:
        return jsonify({"success": False, "message": str(exc)}), 400
    except Exception as exc:  # noqa: BLE001
        return jsonify({"success": False, "message": str(exc)}), 400


def _import_module_from_path(module_name: str, file_path: Path):
    import importlib.util

    spec = importlib.util.spec_from_file_location(module_name, file_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"无法加载模块: {file_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run_agent_cli(argv: list[str], *, mode_label: str = "extract") -> int:
    log_path = na_logger.init_session_log(mode=mode_label, extra=" ".join(argv[:12]))
    na_logger.info(f"CLI 智能提取启动 | mode={mode_label} | argv={argv}")
    print(f"本次运行日志: {log_path}")
    try:
        with _LIB_LOCK:
            _pin_lib_root(AGENT_DIR)
            agent_main = _import_module_from_path("agent_cli_main", AGENT_DIR / "main.py")
        code = int(agent_main.main(argv) or 0)
        if code == 0:
            na_logger.ok(f"CLI 智能提取结束 | mode={mode_label} | exit={code}")
        else:
            na_logger.fail(f"CLI 智能提取结束 | mode={mode_label} | exit={code}")
        return code
    except Exception as exc:  # noqa: BLE001
        na_logger.error(f"CLI 智能提取异常 | mode={mode_label} | {type(exc).__name__}: {exc}")
        raise
    finally:
        na_logger.shutdown_session_log("CLI 智能提取会话结束")


def _run_batch_cli(argv: list[str], *, mode_label: str = "batch") -> int:
    log_path = na_logger.init_session_log(mode=mode_label, extra=" ".join(argv[:12]))
    na_logger.info(f"CLI 批量配置启动 | mode={mode_label} | argv={argv}")
    print(f"本次运行日志: {log_path}")
    try:
        with _LIB_LOCK:
            _pin_lib_root(BATCH_DIR)
            batch_main = _import_module_from_path("batch_cli_main", BATCH_DIR / "main.py")
        code = int(batch_main.main(argv) or 0)
        if code == 0:
            na_logger.ok(f"CLI 批量配置结束 | mode={mode_label} | exit={code}")
        else:
            na_logger.fail(f"CLI 批量配置结束 | mode={mode_label} | exit={code}")
        return code
    except Exception as exc:  # noqa: BLE001
        na_logger.error(f"CLI 批量配置异常 | mode={mode_label} | {type(exc).__name__}: {exc}")
        raise
    finally:
        na_logger.shutdown_session_log("CLI 批量配置会话结束")


def _run_serve(argv: list[str]) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="启动 NA 自动配置 Web 服务")
    parser.add_argument("--host", default="0.0.0.0", help="监听地址（默认 0.0.0.0）")
    parser.add_argument("--port", type=int, default=8765, help="监听端口（默认 8765）")
    parser.add_argument("--no-browser", action="store_true", help="启动后不自动打开浏览器")
    args = parser.parse_args(argv)

    local_url = f"http://127.0.0.1:{args.port}/"
    bind_url = f"http://{args.host}:{args.port}/"
    log_path = na_logger.init_session_log(
        mode="serve",
        extra=f"host={args.host} port={args.port} no_browser={args.no_browser}",
    )
    atexit.register(lambda: na_logger.shutdown_session_log("Web 服务进程退出"))

    print(f"NA 自动配置工具已启动: {bind_url}")
    print(f"本机浏览器请访问: {local_url}")
    print("包含：智能提取 Agent + 渠道/令牌/分组批量配置")
    print(f"本次启动日志: {log_path}")
    na_logger.info(f"Web 服务启动 | bind={bind_url} | local={local_url}")
    na_logger.ok(f"日志目录就绪 | {na_logger.log_dir()}")

    if not args.no_browser and sys.platform != "linux":
        webbrowser.open(local_url)
        na_logger.info(f"已尝试打开浏览器: {local_url}")

    try:
        app.run(host=args.host, port=args.port, debug=False, threaded=True)
        na_logger.ok("Web 服务正常停止")
    except Exception as exc:  # noqa: BLE001
        na_logger.error(f"Web 服务异常退出 | {type(exc).__name__}: {exc}")
        raise
    return 0


def main(argv: list[str] | None = None):
    import argparse

    argv = list(sys.argv[1:] if argv is None else argv)

    root = argparse.ArgumentParser(
        description="NA 自动配置工具（智能提取 + 批量配置）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
子命令:
  serve          启动 Web 服务（默认）
  extract        智能提取渠道行（CLI）
  extract-token  智能提取令牌行（CLI，规则拼接）
  batch          批量创建：channel（默认）/ token / group
  token-batch    批量创建令牌（等价于 batch token）
  group-batch    批量创建分组（等价于 batch group）

示例:
  python app.py
  python app.py serve --port 9000 --no-browser
  python app.py extract -f examples/agent/volcano/input.txt --json
  python app.py extract --use-llm --llm-provider mimo --llm-api-key sk-xxx -f input.txt
  python app.py extract-token -f draft.txt --json
  python app.py batch -c batch/config.json -f examples/batch/mixed/input.tsv
  python app.py batch token -c batch/config.json -f examples/batch/tokens/input.txt
  python app.py batch group -c batch/config.json -f examples/batch/groups/input.txt
  python app.py token-batch -c batch/config.json -f examples/batch/tokens/input.txt
  python app.py group-batch -c batch/config.json -f examples/batch/groups/input.txt
""",
    )
    subparsers = root.add_subparsers(dest="command")

    serve_parser = subparsers.add_parser("serve", help="启动 Web 服务")
    serve_parser.add_argument("--host", default="0.0.0.0")
    serve_parser.add_argument("--port", type=int, default=8765)
    serve_parser.add_argument("--no-browser", action="store_true")

    subparsers.add_parser("extract", help="渠道智能提取（CLI，参数见 agent/main.py -h）", add_help=False)
    subparsers.add_parser("extract-token", help="令牌智能提取（CLI）", add_help=False)
    subparsers.add_parser("batch", help="批量创建渠道/令牌/分组（CLI，见 batch/main.py -h）", add_help=False)
    subparsers.add_parser("token-batch", help="批量创建令牌（CLI）", add_help=False)
    subparsers.add_parser("group-batch", help="批量创建分组（CLI）", add_help=False)

    cli_commands = {"serve", "extract", "extract-token", "batch", "token-batch", "group-batch"}

    if argv == ["-h"] or argv == ["--help"]:
        root.print_help()
        return 0

    if not argv:
        return _run_serve([])

    legacy_serve = argv[0].startswith("-") or argv[0] not in cli_commands
    if legacy_serve:
        return _run_serve(argv)

    args, remaining = root.parse_known_args(argv)
    if args.command == "serve":
        return _run_serve(remaining)
    if args.command == "extract":
        if remaining[:1] == ["-h"] or remaining[:1] == ["--help"]:
            return _run_agent_cli(["--help"])
        return _run_agent_cli(remaining)
    if args.command == "extract-token":
        if remaining[:1] == ["-h"] or remaining[:1] == ["--help"]:
            return _run_agent_cli(["--mode", "token", "--help"], mode_label="extract-token")
        return _run_agent_cli(["--mode", "token", *remaining], mode_label="extract-token")
    if args.command == "batch":
        if remaining[:1] == ["-h"] or remaining[:1] == ["--help"]:
            return _run_batch_cli(["--help"])
        return _run_batch_cli(remaining)
    if args.command == "token-batch":
        if remaining[:1] == ["-h"] or remaining[:1] == ["--help"]:
            return _run_batch_cli(["token", "--help"], mode_label="token-batch")
        return _run_batch_cli(["token", *remaining], mode_label="token-batch")
    if args.command == "group-batch":
        if remaining[:1] == ["-h"] or remaining[:1] == ["--help"]:
            return _run_batch_cli(["group", "--help"], mode_label="group-batch")
        return _run_batch_cli(["group", *remaining], mode_label="group-batch")

    return _run_serve([])


if __name__ == "__main__":
    raise SystemExit(main())
