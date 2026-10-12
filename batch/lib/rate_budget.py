"""本地 CriticalRateLimit 状态（按站点 base_url）。

上游规则（New API middleware CriticalRateLimit）：
- 标记 ``CT`` + ClientIP，登录 / ``/api/verify`` / ``/api/channel/{id}/key`` 共用
- 次数以服务端为准（环境变量 CRITICAL_RATE_LIMIT，缺省随镜像为 20 或 300）

本模块不再按次数预估截断。一直请求，直到上游返回 429 才停，并封锁至窗口结束，
避免紧接着空耗登录/验证。
"""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Any

# 仅用于 429 后的等待文案与兼容旧引用；不再作为拉密钥条数上限
CT_LIMIT = 300
CT_WINDOW_SEC = 20 * 60
SAFE_KEY_BATCH = CT_LIMIT
# remaining() 未遇 429 时视为不截断
_UNLIMITED = 10**9

_LOCK = threading.Lock()
_CACHE_DIR = Path(__file__).resolve().parents[2] / ".cache" / "rate_budget"
_STATE: dict[str, dict[str, Any]] = {}


def _key(base_url: str) -> str:
    return (base_url or "").rstrip("/").lower()


def _path_for(base_url: str) -> Path:
    digest = "".join(ch if ch.isalnum() else "_" for ch in _key(base_url))[:80]
    return _CACHE_DIR / f"{digest}.json"


def _load(base_url: str) -> dict[str, Any]:
    k = _key(base_url)
    if k in _STATE:
        return _STATE[k]
    path = _path_for(base_url)
    data: dict[str, Any] = {
        "used": 0,
        "window_start": 0.0,
        "blocked_until": 0.0,
        "rate_limited": False,
    }
    if path.exists():
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                data.update(raw)
        except Exception:  # noqa: BLE001
            pass
    _STATE[k] = data
    return data


def _save(base_url: str, data: dict[str, Any]) -> None:
    k = _key(base_url)
    _STATE[k] = data
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    _path_for(base_url).write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _roll_window(data: dict[str, Any], now: float) -> None:
    start = float(data.get("window_start") or 0)
    if start <= 0 or now - start >= CT_WINDOW_SEC:
        data["window_start"] = now
        data["used"] = 0
    blocked = float(data.get("blocked_until") or 0)
    if blocked and now >= blocked:
        data["blocked_until"] = 0.0
        data["rate_limited"] = False


def _blocked_by_429(data: dict[str, Any], now: float) -> bool:
    """只有上游真实 429 才封锁；旧版按次数写的 blocked_until 忽略。"""
    if not data.get("rate_limited"):
        return False
    return float(data.get("blocked_until") or 0) > now


def remaining(base_url: str) -> int:
    with _LOCK:
        now = time.time()
        data = _load(base_url)
        _roll_window(data, now)
        if _blocked_by_429(data, now):
            return 0
        return _UNLIMITED


def seconds_until_reset(base_url: str) -> int:
    with _LOCK:
        now = time.time()
        data = _load(base_url)
        if _blocked_by_429(data, now):
            return int(float(data["blocked_until"]) - now) + 1
        return 0


def note_used(base_url: str, n: int = 1) -> None:
    if n <= 0:
        return
    with _LOCK:
        now = time.time()
        data = _load(base_url)
        _roll_window(data, now)
        if not float(data.get("window_start") or 0):
            data["window_start"] = now
        data["used"] = int(data.get("used") or 0) + int(n)
        _save(base_url, data)


def note_rate_limited(base_url: str) -> None:
    """遇上游 429：停止继续拉取，封锁至窗口结束。"""
    with _LOCK:
        now = time.time()
        data = _load(base_url)
        _roll_window(data, now)
        start = float(data.get("window_start") or now)
        data["window_start"] = start
        data["used"] = CT_LIMIT
        data["rate_limited"] = True
        data["blocked_until"] = max(now + CT_WINDOW_SEC, start + CT_WINDOW_SEC)
        _save(base_url, data)


def assert_can_proceed(base_url: str, *, need: int = 2) -> None:
    """仅在刚收到上游 429、窗口未恢复时拒绝再打登录/验证。"""
    rem = remaining(base_url)
    if rem >= need:
        return
    wait = seconds_until_reset(base_url)
    mins = max(1, (wait + 59) // 60)
    raise RuntimeError(
        f"上游刚返回 429 限流，请等待约 {mins} 分钟（≈{wait}s）后再「继续补全密钥」。"
    )


def recommend_batch_size(base_url: str, pending: int, *, reserve_verify: bool = True) -> int:
    """未遇 429 时一次拉完全部 pending；遇 429 则返回 0。"""
    del reserve_verify
    if remaining(base_url) < 1:
        return 0
    return max(0, int(pending))


def reset_budget(base_url: str | None = None) -> None:
    """测试或排障时清空本地配额台账。"""
    with _LOCK:
        if base_url is None:
            _STATE.clear()
            if _CACHE_DIR.exists():
                for path in _CACHE_DIR.glob("*.json"):
                    try:
                        path.unlink(missing_ok=True)
                    except Exception:  # noqa: BLE001
                        pass
            return
        k = _key(base_url)
        _STATE.pop(k, None)
        try:
            _path_for(base_url).unlink(missing_ok=True)
        except Exception:  # noqa: BLE001
            pass
