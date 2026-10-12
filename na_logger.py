"""NA 自动配置工具 — 按次启动文件日志。

每次进程启动在项目根目录 ``log/`` 下生成一个独立 ``.txt``，
记录详细操作（成功 / 失败 / 警告），行内含可读时间与 Unix 时间戳。
"""

from __future__ import annotations

import json
import logging
import os
import re
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parent
LOG_DIR = ROOT_DIR / "log"

_SECRET_KEYS = {
    "password",
    "passwd",
    "pwd",
    "access_token",
    "access_key_id",
    "secret_access_key",
    "token",
    "api_key",
    "apikey",
    "key",
    "secret",
    "authorization",
    "cookie",
    "session",
    "session_id",
    "new_api_user",
    "sk",
    "ak",
    "密钥",
    "秘钥",
    "otp",
    "otp_code",
    "totp_secret",
    "otp_secret",
    "verification_code",
}

_SECRET_RE = re.compile(
    r"(?i)(sk-[a-z0-9_\-]{8,}|bearer\s+[a-z0-9\-_.]+|"
    r"password\s*[:=]\s*\S+|access_token\s*[:=]\s*\S+)"
)

_lock = threading.RLock()
_session_path: Path | None = None
_started = False
_file_handler: logging.Handler | None = None


def log_dir() -> Path:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    return LOG_DIR


def current_log_path() -> Path | None:
    return _session_path


def _now_parts() -> tuple[str, float]:
    now = datetime.now()
    readable = now.strftime("%Y-%m-%d %H:%M:%S.") + f"{int(now.microsecond / 1000):03d}"
    return readable, time.time()


def _format_line(level: str, message: str) -> str:
    readable, ts = _now_parts()
    safe = str(message).replace("\r\n", "\n").replace("\r", "\n")
    if "\n" in safe:
        indent = " " * 4
        safe = "\n".join(
            (line if i == 0 else f"{indent}{line}") for i, line in enumerate(safe.split("\n"))
        )
    return f"[{readable}] [{ts:.3f}] [{level}] {safe}\n"


def _write(level: str, message: str) -> None:
    global _session_path, _started
    with _lock:
        if not _started or _session_path is None:
            return
        line = _format_line(level, message)
        try:
            with _session_path.open("a", encoding="utf-8") as fh:
                fh.write(line)
                fh.flush()
        except OSError:
            pass


def info(message: str) -> None:
    _write("INFO", message)


def ok(message: str) -> None:
    _write("OK", message)


def warn(message: str) -> None:
    _write("WARN", message)


def fail(message: str) -> None:
    _write("FAIL", message)


def error(message: str) -> None:
    _write("ERROR", message)


def operation(
    action: str,
    *,
    success: bool | None = None,
    detail: str = "",
    level: str | None = None,
) -> None:
    """记录一次业务操作。success=True→OK，False→FAIL，None→INFO；可强制 level。"""
    if level is None:
        if success is True:
            level = "OK"
        elif success is False:
            level = "FAIL"
        else:
            level = "INFO"
    msg = action if not detail else f"{action} | {detail}"
    _write(level, msg)


def redact(value: Any, *, max_len: int = 4000) -> Any:
    """脱敏嵌套结构中的敏感字段，并截断过长文本。"""
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for k, v in value.items():
            key_l = str(k).lower().replace("-", "_")
            if key_l in _SECRET_KEYS or any(s in key_l for s in ("password", "token", "secret", "api_key", "密钥", "秘钥")):
                if v in (None, "", []):
                    out[k] = v
                else:
                    text = str(v)
                    out[k] = f"<redacted len={len(text)}>"
            else:
                out[k] = redact(v, max_len=max_len)
        return out
    if isinstance(value, list):
        if len(value) > 80:
            head = [redact(x, max_len=max_len) for x in value[:40]]
            return head + [f"...(+{len(value) - 40} more)"]
        return [redact(x, max_len=max_len) for x in value]
    if isinstance(value, str):
        text = _SECRET_RE.sub("<redacted>", value)
        if len(text) > max_len:
            return text[:max_len] + f"...(+{len(text) - max_len} chars)"
        return text
    return value


def dumps_safe(value: Any, *, max_len: int = 4000) -> str:
    try:
        return json.dumps(redact(value, max_len=max_len), ensure_ascii=False, default=str)
    except Exception:  # noqa: BLE001
        return str(redact(value, max_len=max_len))


def summarize_api_result(data: Any) -> str:
    """从 API JSON 结果提炼审查要点。"""
    if not isinstance(data, dict):
        return dumps_safe(data, max_len=800)

    parts: list[str] = []
    if "success" in data:
        parts.append(f"success={data.get('success')}")
    msg = data.get("message") or data.get("error") or data.get("msg")
    if msg:
        parts.append(f"message={msg}")

    payload = data.get("data")
    if isinstance(payload, dict):
        for key in (
            "count",
            "total",
            "matched",
            "updated",
            "created",
            "deleted",
            "enabled",
            "disabled",
            "skipped",
            "failed",
            "ok",
            "fail",
            "warn",
            "dry_run",
            "match_mode",
            "action",
            "channel_type",
            "filename",
            "path",
            "source",
        ):
            if key in payload and payload[key] not in (None, "", []):
                parts.append(f"{key}={payload[key]}")
        items = payload.get("items") or payload.get("results") or payload.get("channels")
        if isinstance(items, list):
            parts.append(f"items={len(items)}")
            ok_n = sum(1 for x in items if isinstance(x, dict) and x.get("success") is True)
            fail_n = sum(1 for x in items if isinstance(x, dict) and x.get("success") is False)
            warn_n = sum(
                1
                for x in items
                if isinstance(x, dict)
                and (x.get("warning") or x.get("skipped") or str(x.get("status", "")).lower() in {"skip", "warn", "warning"})
            )
            if ok_n or fail_n or warn_n:
                parts.append(f"item_stats ok={ok_n} fail={fail_n} warn/skip={warn_n}")
            # 逐条摘要（最多 30 条）
            for i, item in enumerate(items[:30]):
                if not isinstance(item, dict):
                    continue
                idx = item.get("index", i + 1)
                name = item.get("name") or item.get("channel_name") or item.get("id") or ""
                st = "OK" if item.get("success") is True else ("FAIL" if item.get("success") is False else "INFO")
                imsg = item.get("message") or item.get("error") or item.get("warning") or ""
                parts.append(f"  #{idx} [{st}] {name}: {imsg}".rstrip(": "))
            if len(items) > 30:
                parts.append(f"  ...(+{len(items) - 30} items)")
    elif isinstance(payload, list):
        parts.append(f"data_list={len(payload)}")
    elif payload is not None:
        parts.append(f"data={dumps_safe(payload, max_len=400)}")

    return " | ".join(parts) if parts else dumps_safe(data, max_len=800)


class _SessionLogHandler(logging.Handler):
    """将标准 logging 记录写入当前启动日志文件。"""

    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = self.format(record)
            level_map = {
                logging.DEBUG: "DEBUG",
                logging.INFO: "INFO",
                logging.WARNING: "WARN",
                logging.ERROR: "ERROR",
                logging.CRITICAL: "ERROR",
            }
            level = level_map.get(record.levelno, "INFO")
            # 已自带时间的消息直接按业务级别写
            if record.name.startswith("na."):
                _write(level, msg)
            else:
                _write(level, f"[{record.name}] {msg}")
        except Exception:  # noqa: BLE001
            self.handleError(record)


def init_session_log(*, mode: str = "serve", extra: str = "") -> Path:
    """创建本次启动的日志文件，并挂接标准 logging。可重复调用（仅首次生效）。"""
    global _session_path, _started, _file_handler

    with _lock:
        if _started and _session_path is not None:
            info(f"复用本次启动日志: {_session_path.name} ({extra or mode})")
            return _session_path

        log_dir()
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        pid = os.getpid()
        safe_mode = re.sub(r"[^\w\-]+", "_", mode)[:32] or "app"
        path = LOG_DIR / f"na_{stamp}_{safe_mode}_pid{pid}.txt"
        _session_path = path
        _started = True

        header_lines = [
            "=" * 72,
            "NA 自动配置工具 — 启动会话日志",
            f"启动时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]}",
            f"Unix 时间戳: {time.time():.3f}",
            f"进程 PID: {pid}",
            f"模式: {mode}",
            f"工作目录: {ROOT_DIR}",
            f"日志文件: {path}",
        ]
        if extra:
            header_lines.append(f"附加信息: {extra}")
        header_lines.append("=" * 72)
        header_lines.append("")
        path.write_text("\n".join(header_lines), encoding="utf-8")

        # 挂接标准库 logging → 同一文件
        root = logging.getLogger()
        if _file_handler is not None:
            root.removeHandler(_file_handler)
        handler = _SessionLogHandler()
        handler.setLevel(logging.INFO)
        handler.setFormatter(logging.Formatter("%(message)s"))
        root.addHandler(handler)
        if root.level > logging.INFO or root.level == logging.NOTSET:
            root.setLevel(logging.INFO)
        _file_handler = handler

        # 业务命名空间
        logging.getLogger("na").setLevel(logging.INFO)
        logging.getLogger("na.api_client").setLevel(logging.INFO)

        info(f"会话日志已创建: {path.name}")
        return path


def shutdown_session_log(message: str = "服务停止") -> None:
    info(message)
    info("=" * 40 + " 会话结束 " + "=" * 40)
