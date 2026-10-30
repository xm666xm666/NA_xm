"""火山方舟推理 Token 用量查询与 CSV 导出。"""

from __future__ import annotations

import csv
import datetime as dt
import hashlib
import hmac
import io
import json
import ssl
import urllib.error
import urllib.parse
import urllib.request
from typing import Any


HOST = "ark.cn-beijing.volcengineapi.com"
REGION = "cn-beijing"
SERVICE = "ark"
VERSION = "2024-01-01"
ACTION = "GetInferenceUsage"
CONTENT_TYPE = "application/json"

_FILTER_FIELDS = {
    "none": None,
    "model_name": "ModelName",
    "model_version": "ModelVersion",
    "endpoint": "ModelEndpoint",
    "apikey_id": "ApikeyID",
}
_FALLBACK_FIELDS = (
    "AccountID",
    "Day",
    "Hour",
    "InputTokens",
    "OutputTokens",
    "TotalTokens",
    "ReqCnt",
)


def _sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _hmac_sha256(key: bytes, text: str) -> bytes:
    return hmac.new(key, text.encode("utf-8"), hashlib.sha256).digest()


def _canonical_query(params: dict[str, str]) -> str:
    return "&".join(
        f"{urllib.parse.quote(key, safe='-_.~')}={urllib.parse.quote(params[key], safe='-_.~')}"
        for key in sorted(params)
    )


def _redact(text: str, *secrets: str) -> str:
    redacted = str(text or "")
    for secret in secrets:
        if secret:
            redacted = redacted.replace(secret, "***")
    return redacted


def _extract_api_error(response: dict[str, Any]) -> str:
    metadata = response.get("ResponseMetadata") or {}
    error = metadata.get("Error") or response.get("Error") or {}
    code = error.get("Code") or "UnknownError"
    message = error.get("Message") or response.get("Message") or "请求失败"
    return f"{code} - {message}"


def _sign_request(
    payload: dict[str, Any],
    access_key: str,
    secret_key: str,
    session_token: str = "",
    now: dt.datetime | None = None,
) -> urllib.request.Request:
    now = now or dt.datetime.now(dt.timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=dt.timezone.utc)
    x_date = now.astimezone(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    body_hash = _sha256_hex(body)
    query = _canonical_query({"Action": ACTION, "Version": VERSION})
    headers = [
        ("content-type", CONTENT_TYPE),
        ("host", HOST),
        ("x-content-sha256", body_hash),
        ("x-date", x_date),
    ]
    if session_token:
        headers.append(("x-security-token", session_token))
    headers.sort()
    signed_headers = ";".join(name for name, _ in headers)
    canonical_request = "\n".join(
        ["POST", "/", query, "\n".join(f"{name}:{value.strip()}" for name, value in headers), "", signed_headers, body_hash]
    )
    scope = f"{x_date[:8]}/{REGION}/{SERVICE}/request"
    string_to_sign = "\n".join(["HMAC-SHA256", x_date, scope, _sha256_hex(canonical_request.encode("utf-8"))])
    signing_key = _hmac_sha256(_hmac_sha256(_hmac_sha256(_hmac_sha256(secret_key.encode("utf-8"), x_date[:8]), REGION), SERVICE), "request")
    signature = hmac.new(signing_key, string_to_sign.encode("utf-8"), hashlib.sha256).hexdigest()
    request_headers = {
        "Authorization": (
            f"HMAC-SHA256 Credential={access_key}/{scope}, "
            f"SignedHeaders={signed_headers}, Signature={signature}"
        ),
        "Content-Type": CONTENT_TYPE,
        "Host": HOST,
        "User-Agent": "NA-auto-config/1.0",
        "X-Content-Sha256": body_hash,
        "X-Date": x_date,
    }
    if session_token:
        request_headers["X-Security-Token"] = session_token
    return urllib.request.Request(
        url=f"https://{HOST}/?{query}",
        data=body,
        headers=request_headers,
        method="POST",
    )


def call_ark_api(
    payload: dict[str, Any],
    access_key: str,
    secret_key: str,
    session_token: str = "",
    timeout: int = 45,
) -> dict[str, Any]:
    api_request = _sign_request(payload, access_key, secret_key, session_token)
    try:
        with urllib.request.urlopen(
            api_request,
            timeout=timeout,
            context=ssl.create_default_context(),
        ) as response:
            raw = response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            detail = json.loads(raw)
            message = _extract_api_error(detail)
        except json.JSONDecodeError:
            message = raw[:1000] or str(exc)
        raise RuntimeError(_redact(message, access_key, secret_key, session_token)) from exc
    except (urllib.error.URLError, TimeoutError) as exc:
        reason = getattr(exc, "reason", exc)
        raise RuntimeError(_redact(f"网络连接失败：{reason}", access_key, secret_key, session_token)) from exc

    try:
        result = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError("接口返回的内容不是有效 JSON") from exc
    error = (result.get("ResponseMetadata") or {}).get("Error")
    if error:
        raise RuntimeError(_redact(_extract_api_error(result), access_key, secret_key, session_token))
    return result


def usage_payload(body: dict[str, Any]) -> dict[str, Any]:
    """把前端请求转换为 GetInferenceUsage 的请求体。"""
    today = dt.date.today()
    default_start = today.replace(day=1)
    try:
        start = dt.datetime.strptime(
            str(body.get("start_time") or body.get("start") or default_start), "%Y-%m-%d"
        ).date()
        end = dt.datetime.strptime(
            str(body.get("end_time") or body.get("end") or today), "%Y-%m-%d"
        ).date()
    except ValueError as exc:
        raise ValueError("日期格式应为 YYYY-MM-DD") from exc
    if start > end:
        start, end = end, start
    if end > today:
        end = today
    if start > today:
        raise ValueError("开始日期不能晚于今天")

    interval_raw = str(body.get("query_interval") or body.get("interval") or "day").strip().lower()
    interval_map = {"1": "Day", "day": "Day", "2": "Hour", "hour": "Hour"}
    interval = interval_map.get(interval_raw)
    if not interval:
        raise ValueError("查询粒度仅支持 Day 或 Hour")

    filter_raw = str(body.get("filter_type") or "none").strip().lower()
    filter_key = _FILTER_FIELDS.get(filter_raw)
    if filter_raw not in _FILTER_FIELDS:
        raise ValueError("不支持的筛选类型")
    filters: list[dict[str, Any]] = []
    if filter_key:
        values = body.get("filter_values")
        if isinstance(values, str):
            values = values.replace("，", ",").replace("\n", ",").split(",")
        values = [str(value).strip() for value in values or [] if str(value).strip()]
        if not values:
            raise ValueError("使用筛选条件时至少填写一个值")
        filters = [{"Key": filter_key, "Values": values}]

    payload: dict[str, Any] = {
        "StartTime": start.isoformat(),
        "EndTime": end.isoformat(),
        "QueryInterval": interval,
        "ProjectName": str(body.get("project_name") or body.get("project") or "default").strip() or "default",
    }
    if filters:
        payload["Filters"] = filters
    return payload


def usage_table(response: dict[str, Any]) -> tuple[list[str], list[list[str]]]:
    result = response.get("Result")
    if not isinstance(result, dict):
        raise RuntimeError("接口响应缺少 Result")
    fields_raw = result.get("Fields") or []
    data_raw = result.get("Data") or []
    fields = [str(item.get("Name", "")) for item in fields_raw if isinstance(item, dict)]
    rows = [[str(value) if value is not None else "" for value in row] for row in data_raw]
    if rows and (not fields or any(len(row) != len(fields) for row in rows)):
        raise RuntimeError("接口返回的 Fields 与 Data 列数不一致")
    return (fields or list(_FALLBACK_FIELDS)), rows


def usage_totals(fields: list[str], rows: list[list[str]]) -> dict[str, int]:
    index = {name: pos for pos, name in enumerate(fields)}
    totals: dict[str, int] = {}
    for name in ("InputTokens", "OutputTokens", "TotalTokens", "ReqCnt"):
        pos = index.get(name)
        totals[name] = sum(int(row[pos] or 0) for row in rows) if pos is not None else 0
    return totals


def run_query(ak: str, sk: str, session_token: str, body: dict[str, Any]) -> dict[str, Any]:
    payload = usage_payload(body)
    response = call_ark_api(payload, ak, sk, session_token)
    fields, rows = usage_table(response)
    return {
        "fields": fields,
        "rows": rows,
        "totals": usage_totals(fields, rows),
        "query": payload,
    }


def _safe_csv_cell(value: Any) -> str:
    text = "" if value is None else str(value)
    if text.startswith(("=", "+", "-", "@", "\t", "\r", "\n")):
        return "'" + text
    return text


def csv_bytes(fields: list[str], rows: list[list[str]]) -> bytes:
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow([_safe_csv_cell(field) for field in fields])
    writer.writerows([[_safe_csv_cell(cell) for cell in row] for row in rows])
    return output.getvalue().encode("utf-8-sig")
