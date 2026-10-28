"""New API HTTP 客户端。"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import random
import threading
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import requests
import urllib3
from urllib3.exceptions import InsecureRequestWarning

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from .rate_budget import assert_can_proceed, note_rate_limited, note_used, remaining
from .token_api_fields import (
    apply_model_limits,
    extract_model_limit,
    legacy_token_quota_payload,
)
from .totp import resolve_otp_code

_log = logging.getLogger("na.api_client")
_INSECURE_SSL_WARNINGS_DISABLED = False
_TOKEN_CRYPTO_HEADER = "X-Token-Crypto-Key"


def coerce_verify_ssl(value: Any, default: bool = True) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"0", "false", "no", "off"}:
        return False
    if text in {"1", "true", "yes", "on"}:
        return True
    return default


def disable_insecure_ssl_warnings() -> None:
    global _INSECURE_SSL_WARNINGS_DISABLED
    if not _INSECURE_SSL_WARNINGS_DISABLED:
        urllib3.disable_warnings(InsecureRequestWarning)
        _INSECURE_SSL_WARNINGS_DISABLED = True


def _optional_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _parse_log_list_payload(
    data: dict[str, Any],
    *,
    page: int,
    page_size: int,
) -> dict[str, Any]:
    """兼容 data 为分页对象或日志数组两种返回。total 缺失时为 None，避免被当成 0 提前停拉。"""
    raw = data.get("data")
    items: list[Any] = []
    total = data.get("total")
    returned_page = page
    returned_size = page_size

    if isinstance(raw, list):
        items = raw
    elif isinstance(raw, dict):
        maybe_items = raw.get("items")
        if maybe_items is None:
            maybe_items = raw.get("Items")
        items = maybe_items if isinstance(maybe_items, list) else []
        if raw.get("total") is not None:
            total = raw.get("total")
        if raw.get("page") is not None:
            returned_page = raw.get("page")
        if raw.get("page_size") is not None:
            returned_size = raw.get("page_size")
        elif raw.get("PageSize") is not None:
            returned_size = raw.get("PageSize")

    return {
        "page": _optional_int(returned_page) or page,
        "page_size": _optional_int(returned_size) or page_size,
        "total": _optional_int(total),
        "items": items,
    }


class SecureVerificationError(RuntimeError):
    """上游要求重新做 /api/verify（403 VERIFICATION_*）。"""


def login_payload_needs_2fa(payload: Any) -> str:
    """判断登录响应是否还要走两步验证。

    返回 ``verify``（已绑定，需验证码）、``setup``（尚未绑定）或空串。
    兼容旧字段 ``require_2fa`` 与 v1.0.1 的 ``mfa_action``。
    """
    if not isinstance(payload, dict):
        return ""
    action = str(payload.get("mfa_action") or "").strip().lower()
    if action in {"verify", "setup"}:
        return action
    if payload.get("require_2fa"):
        return "verify"
    return ""


# 进程内 + 磁盘会话缓存，避免连续操作反复登录触发 429
_SESSION_CACHE: dict[str, dict[str, Any]] = {}
_SESSION_CACHE_LOCK = threading.Lock()
_SESSION_CACHE_TTL_SEC = 2 * 60 * 60.0  # 2h：覆盖多轮「继续补全」
_SESSION_DISK_DIR = Path(__file__).resolve().parents[2] / ".cache" / "na_sessions"


def _auth_cache_key(base_url: str, username: str, password: str = "", *, access_token: str = "") -> str:
    if access_token:
        digest = hashlib.sha256(f"token\0{access_token}".encode("utf-8")).hexdigest()[:24]
    else:
        digest = hashlib.sha256(f"{username}\0{password}".encode("utf-8")).hexdigest()[:24]
    return f"{base_url.rstrip('/')}|{digest}"


def _disk_path(key: str) -> Path:
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()[:40]
    return _SESSION_DISK_DIR / f"{digest}.json"


def _store_session_cache(key: str, client: "NewAPIClient") -> None:
    entry = {
        "expires_at": time.time() + _SESSION_CACHE_TTL_SEC,
        "cookies": requests.utils.dict_from_cookiejar(client.session.cookies),
        "user_id": client.user_id,
        "role": client.role,
        "authorization": client.session.headers.get("Authorization"),
        "base_url": client.base_url,
    }
    with _SESSION_CACHE_LOCK:
        _SESSION_CACHE[key] = entry
    try:
        _SESSION_DISK_DIR.mkdir(parents=True, exist_ok=True)
        _disk_path(key).write_text(json.dumps(entry, ensure_ascii=False), encoding="utf-8")
    except Exception as exc:  # noqa: BLE001
        _log.debug("会话落盘失败: %s", exc)


def _load_disk_session(key: str) -> dict[str, Any] | None:
    path = _disk_path(key)
    if not path.exists():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None
    if not isinstance(raw, dict):
        return None
    if float(raw.get("expires_at") or 0) < time.time():
        try:
            path.unlink(missing_ok=True)
        except Exception:  # noqa: BLE001
            pass
        return None
    return raw


def _apply_session_cache(client: "NewAPIClient", key: str) -> bool:
    with _SESSION_CACHE_LOCK:
        entry = _SESSION_CACHE.get(key)
        if entry and float(entry.get("expires_at") or 0) < time.time():
            _SESSION_CACHE.pop(key, None)
            entry = None
        if not entry:
            entry = _load_disk_session(key)
            if entry:
                _SESSION_CACHE[key] = entry
    if not entry:
        return False
    cookies = dict(entry.get("cookies") or {})
    user_id = entry.get("user_id")
    role = entry.get("role")
    authorization = entry.get("authorization")
    if user_id is None:
        return False
    client.session.cookies.clear()
    client.session.headers.pop("Authorization", None)
    client.session.cookies.update(cookies)
    if authorization:
        client.session.headers["Authorization"] = authorization
    client.user_id = int(user_id)
    client.role = int(role or 0)
    if authorization:
        client.auth_mode = "token"
    else:
        client.auth_mode = "password"
    client.session_cache_hit = True
    client.session_cache_expires_at = float(entry.get("expires_at") or 0)
    _log.info("复用会话缓存 | base=%s | user_id=%s", client.base_url, client.user_id)
    return True


def _invalidate_session_cache(key: str) -> None:
    with _SESSION_CACHE_LOCK:
        _SESSION_CACHE.pop(key, None)
    try:
        _disk_path(key).unlink(missing_ok=True)
    except Exception:  # noqa: BLE001
        pass


def session_cache_alive(
    base_url: str,
    *,
    username: str = "",
    password: str = "",
    access_token: str = "",
) -> bool:
    """磁盘/内存会话是否仍有效（不打网关，供工作台展示「已认证」）。"""
    base = str(base_url or "").rstrip("/")
    if not base:
        return False
    key = _auth_cache_key(base, str(username or ""), str(password or ""), access_token=str(access_token or ""))
    now = time.time()
    with _SESSION_CACHE_LOCK:
        entry = _SESSION_CACHE.get(key)
        if entry and float(entry.get("expires_at") or 0) >= now and entry.get("user_id") is not None:
            return True
    disk = _load_disk_session(key)
    return bool(disk and disk.get("user_id") is not None)


class NewAPIClient:
    def __init__(
        self,
        base_url: str,
        user_id: int | None = None,
        timeout: int = 30,
        *,
        verify_ssl: bool = True,
    ):
        self.base_url = base_url.rstrip("/")
        self.user_id = user_id
        self.role: int | None = None
        self.timeout = timeout
        self.auth_mode: str = ""  # "password" | "token"
        self.session_cache_hit = False
        self.session_cache_expires_at = 0.0
        self._token_crypto_lock = threading.Lock()
        self._token_crypto_private_key = None
        self._token_crypto_key_header = ""
        self._token_crypto_enabled = False
        self._token_input_quota_supported: bool | None = None
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        self.set_verify_ssl(verify_ssl)

    def set_verify_ssl(self, verify: bool) -> None:
        """内网网关证书域名不匹配时可关闭校验。"""
        ok = bool(verify)
        self.session.verify = ok
        if not ok:
            disable_insecure_ssl_warnings()
            _log.warning("已跳过 SSL 证书校验 | base=%s", self.base_url)

    def _headers(self) -> dict[str, str]:
        headers: dict[str, str] = {}
        if self.user_id is not None:
            headers["New-Api-User"] = str(self.user_id)
        return headers

    def _token_crypto_public_key_header(self) -> str:
        """生成进程内 RSA-2048 会话公钥，格式为 Base64(SPKI DER)。"""
        if self._token_crypto_key_header:
            return self._token_crypto_key_header
        with self._token_crypto_lock:
            if not self._token_crypto_key_header:
                private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
                spki_der = private_key.public_key().public_bytes(
                    Encoding.DER,
                    PublicFormat.SubjectPublicKeyInfo,
                )
                self._token_crypto_private_key = private_key
                self._token_crypto_key_header = base64.b64encode(spki_der).decode("ascii")
        return self._token_crypto_key_header

    @staticmethod
    def _token_crypto_required(response: requests.Response) -> bool:
        """只在上游明确要求令牌加密协议时降级，避免吞掉其他 400 参数错误。"""
        try:
            payload = response.json()
        except (ValueError, TypeError):
            return False
        if not isinstance(payload, dict):
            return False
        message = str(payload.get("message") or "")
        return _TOKEN_CRYPTO_HEADER in message and any(
            marker in message
            for marker in ("missing", "invalid", "缺失", "非法", "无效")
        )

    def _request_token_api(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
    ) -> requests.Response:
        headers = self._headers()
        request_kwargs: dict[str, Any] = {
            "params": params,
            "headers": headers,
            "timeout": self.timeout,
        }
        if json_body is not None:
            request_kwargs["json"] = json_body

        response = self._perform_token_request(method, f"{self.base_url}{path}", request_kwargs)
        response.raise_for_status()
        return response

    def _perform_token_request(
        self,
        method: str,
        url: str,
        request_kwargs: dict[str, Any],
    ) -> requests.Response:
        headers = dict(request_kwargs.get("headers") or {})
        if self._token_crypto_enabled:
            headers[_TOKEN_CRYPTO_HEADER] = self._token_crypto_public_key_header()
            request_kwargs["headers"] = headers

        response = self.session.request(method, url, **request_kwargs)
        if not self._token_crypto_enabled and response.status_code == 400 and self._token_crypto_required(response):
            headers = {**headers, _TOKEN_CRYPTO_HEADER: self._token_crypto_public_key_header()}
            request_kwargs["headers"] = headers
            response = self.session.request(method, url, **request_kwargs)
            self._token_crypto_enabled = True
        return response

    def _decrypt_token_keys(self, value: Any) -> Any:
        """解密新版 New API 返回的 token.key 字段。"""
        if isinstance(value, list):
            return [self._decrypt_token_keys(item) for item in value]
        if not isinstance(value, dict):
            return value
        result = dict(value)
        result = {name: self._decrypt_token_keys(child) for name, child in result.items()}
        encrypted_key = result.get("key")
        if isinstance(encrypted_key, str) and encrypted_key and self._token_crypto_private_key is not None:
            try:
                ciphertext = base64.b64decode(encrypted_key, validate=True)
                plaintext = self._token_crypto_private_key.decrypt(
                    ciphertext,
                    padding.OAEP(
                        mgf=padding.MGF1(algorithm=hashes.SHA256()),
                        algorithm=hashes.SHA256(),
                        label=None,
                    ),
                )
                result["key"] = plaintext.decode("utf-8")
            except (ValueError, TypeError, UnicodeDecodeError) as exc:
                raise RuntimeError("解密 New API 令牌密钥失败") from exc
        return result

    def supports_token_input_quota(self) -> bool:
        """探测 v1.0.3 及以上版本的独立 Token 额度协议。"""
        if self._token_input_quota_supported is None:
            try:
                response = self.session.get(
                    f"{self.base_url}/api/token/model_quota_capabilities",
                    headers=self._headers(),
                    timeout=self.timeout,
                )
                payload = response.json() if response.status_code == 200 else {}
                self._token_input_quota_supported = bool(payload.get("success"))
            except Exception:
                self._token_input_quota_supported = False
        return self._token_input_quota_supported

    def prepare_token_payload_for_gateway(self, payload: dict[str, Any]) -> dict[str, Any]:
        """编辑器/批量请求按上游版本自动选择新额度或老金额额度协议。"""
        body = dict(payload)
        if self.supports_token_input_quota():
            return body
        return legacy_token_quota_payload(body)

    def login(
        self,
        username: str,
        password: str,
        *,
        otp_code: str = "",
        max_retries: int = 2,
    ) -> dict[str, Any]:
        self.session.headers.pop("Authorization", None)
        self.session.cookies.clear()
        last_error: BaseException | None = None
        _log.info("开始登录 | base=%s | user=%s | max_retries=%s", self.base_url, username, max_retries)
        for attempt in range(max(1, int(max_retries))):
            try:
                resp = self.session.post(
                    f"{self.base_url}/api/user/login",
                    json={"username": username, "password": password},
                    headers=self._headers(),
                    timeout=self.timeout,
                )
                if resp.status_code == 429:
                    # CriticalRateLimit 窗口约 20 分钟；短退避后快速失败，避免前端假死空耗配额
                    note_rate_limited(self.base_url)
                    last_error = requests.HTTPError(
                        f"429 Too Many Requests for url: {resp.url}",
                        response=resp,
                    )
                    if attempt + 1 >= max(1, int(max_retries)):
                        break
                    wait = 1.0 + random.uniform(0.2, 0.6)
                    _log.warning(
                        "登录限流 429 | attempt=%s/%s | wait=%.1fs | base=%s",
                        attempt + 1,
                        max_retries,
                        wait,
                        self.base_url,
                    )
                    time.sleep(wait)
                    continue
                resp.raise_for_status()
                data = resp.json()
                if not data.get("success"):
                    msg = data.get("message") or "登录失败"
                    _log.error("登录失败 | base=%s | user=%s | message=%s", self.base_url, username, msg)
                    raise RuntimeError(msg)

                note_used(self.base_url, 1)
                payload = data.get("data") or {}
                self._ingest_response_cookies(resp)
                mfa = login_payload_needs_2fa(payload)
                if mfa == "setup":
                    _log.error("登录需要先绑定两步验证 | user=%s", username)
                    raise RuntimeError(
                        "该账号尚未绑定登录两步验证，请先在 NA 控制台完成 MFA 绑定后再采集。"
                    )
                if mfa == "verify":
                    code = resolve_otp_code(otp_code)
                    if not code:
                        _log.error("登录需要两步验证 | user=%s", username)
                        raise RuntimeError(
                            "账号启用了登录两步验证，请填写认证器当前 6 位验证码、8 位备用码，"
                            "或在 env/sites.json 预置 totp_secret（认证器原始密钥）。"
                        )
                    return self.verify_login_2fa(code)

                if payload.get("id") is None:
                    raise RuntimeError("登录响应异常：未返回用户信息，也未提示两步验证")
                self.user_id = int(payload["id"])
                self.role = int(payload.get("role") or 0)
                self.auth_mode = "password"
                _log.info(
                    "登录成功 | base=%s | user=%s | user_id=%s | role=%s",
                    self.base_url,
                    username,
                    self.user_id,
                    self.role,
                )
                return payload
            except requests.HTTPError as exc:
                response = getattr(exc, "response", None)
                if response is not None and response.status_code == 429:
                    note_rate_limited(self.base_url)
                    last_error = exc
                    if attempt + 1 >= max(1, int(max_retries)):
                        break
                    wait = 1.0 + random.uniform(0.2, 0.6)
                    _log.warning(
                        "登录 HTTP 429 | attempt=%s/%s | wait=%.1fs | base=%s",
                        attempt + 1,
                        max_retries,
                        wait,
                        self.base_url,
                    )
                    time.sleep(wait)
                    continue
                _log.error("登录 HTTP 错误 | base=%s | err=%s", self.base_url, exc)
                raise
        if last_error:
            _log.error("登录最终失败（429 限流）| base=%s | user=%s", self.base_url, username)
            raise RuntimeError(
                "登录过于频繁被限流（429）。请等待约 15～20 分钟后再试；或改用 Access Token。详情: "
                f"{last_error}"
            ) from last_error
        raise RuntimeError("登录失败")

    def set_access_token(self, access_token: str, user_id: int, *, clear_cookies: bool = False) -> None:
        token = access_token.strip()
        if token.lower().startswith("bearer "):
            token = token[7:].strip()
        # 默认保留 cookie：/api/verify 写入的 secure_verified_at 依赖 session
        if clear_cookies:
            self.session.cookies.clear()
        self.session.headers["Authorization"] = token
        self.user_id = user_id
        self.auth_mode = "token"

    def verify_login_2fa(self, code: str) -> dict[str, Any]:
        """完成登录两步验证：POST /api/user/login/2fa（依赖 login 留下的 pending session）。"""
        clean = str(code or "").strip()
        if not clean:
            raise RuntimeError("请输入登录两步验证码")
        resp = self.session.post(
            f"{self.base_url}/api/user/login/2fa",
            json={"code": clean},
            headers=self._headers(),
            timeout=self.timeout,
        )
        if resp.status_code == 429:
            note_rate_limited(self.base_url)
            raise RuntimeError(
                "登录两步验证触发限流（429）。请等待约 15～20 分钟后再试，或改用 Access Token。"
            )
        resp.raise_for_status()
        data = resp.json()
        if not data.get("success"):
            raise RuntimeError(data.get("message") or "登录两步验证失败")
        note_used(self.base_url, 1)
        self._ingest_response_cookies(resp)
        payload = data.get("data") or {}
        if payload.get("id") is not None:
            self.user_id = int(payload["id"])
        if payload.get("role") is not None:
            self.role = int(payload["role"])
        self.auth_mode = "password"
        _log.info("登录两步验证成功 | base=%s | user_id=%s", self.base_url, self.user_id)
        return payload

    def _drop_named_cookies(self, *names: str) -> None:
        """删除 jar 中指定名称的 cookie（所有 domain/path）。"""
        wanted = {n.lower() for n in names}
        for c in list(self.session.cookies):
            if str(c.name).lower() not in wanted:
                continue
            try:
                self.session.cookies.clear(c.domain, c.path, c.name)
            except Exception:  # noqa: BLE001
                try:
                    self.session.cookies.clear(None, c.path, c.name)
                except Exception:  # noqa: BLE001
                    pass

    def _ingest_response_cookies(self, resp: requests.Response) -> None:
        """用响应 Set-Cookie 覆盖同名 cookie，避免继续使用过期的 secure_verified_at。"""
        raw_headers = getattr(getattr(resp, "raw", None), "headers", None)
        set_cookies: list[str] = []
        if raw_headers is not None and hasattr(raw_headers, "getlist"):
            try:
                set_cookies = list(raw_headers.getlist("Set-Cookie") or [])
            except Exception:  # noqa: BLE001
                set_cookies = []
        if not set_cookies:
            single = resp.headers.get("Set-Cookie")
            if single:
                set_cookies = [single]

        if not set_cookies and not resp.cookies:
            _log.warning(
                "响应无 Set-Cookie，保留现有 jar | base=%s | jar=%s",
                self.base_url,
                list(self.session.cookies.keys()),
            )
            return

        # 有新 cookie 时先丢掉旧 session，再写入，避免过期 verified 残留
        self._drop_named_cookies("session", "sessions")
        try:
            self.session.cookies.update(resp.cookies)
        except Exception as exc:  # noqa: BLE001
            _log.debug("update resp.cookies 失败: %s", exc)

        host = urlparse(self.base_url).hostname or ""
        for header in set_cookies:
            first = header.split(";", 1)[0].strip()
            if "=" not in first:
                continue
            name, value = first.split("=", 1)
            name = name.strip()
            value = value.strip()
            if not name:
                continue
            try:
                self.session.cookies.set(name, value, domain=host or None, path="/")
            except Exception:  # noqa: BLE001
                try:
                    self.session.cookies.set(name, value)
                except Exception as exc:  # noqa: BLE001
                    _log.debug("写入 cookie %s 失败: %s", name, exc)

        _log.info(
            "已刷新响应 cookie | base=%s | set_cookie_count=%s | jar=%s",
            self.base_url,
            len(set_cookies) or len(resp.cookies),
            list(self.session.cookies.keys()),
        )

    def verify_secure(self, code: str, *, method: str = "2fa") -> dict[str, Any]:
        """通用安全验证：POST /api/verify，在 session 写入 secure_verified_at（约 5 分钟有效）。

        与官方前端一致：verify 成功后直接调业务接口，不再依赖 /api/verify/status
        （status 回读可能带回旧/空 Set-Cookie，反而把刚写入的验证状态冲掉）。
        """
        clean = resolve_otp_code(code)
        if not clean:
            raise RuntimeError("请输入二次验证码，或在 env/sites.json 预置 totp_secret")
        resp = self.session.post(
            f"{self.base_url}/api/verify",
            json={"method": method or "2fa", "code": clean},
            headers=self._headers(),
            timeout=self.timeout,
        )
        if resp.status_code == 429:
            note_rate_limited(self.base_url)
            raise RuntimeError(
                "二次验证触发限流（429）。请等待约 15～20 分钟后再「继续补全密钥」。"
            )
        resp.raise_for_status()
        data = resp.json()
        if not data.get("success"):
            raise RuntimeError(data.get("message") or "二次验证失败")
        note_used(self.base_url, 1)
        self._ingest_response_cookies(resp)
        _log.info("安全验证成功 | base=%s | method=%s", self.base_url, method)
        return data.get("data") or {}

    def get_verify_status(self) -> dict[str, Any]:
        """查询安全验证状态（不走 CriticalRateLimit）。拉密钥主路径请勿在 verify 后调用。"""
        resp = self.session.get(
            f"{self.base_url}/api/verify/status",
            headers={
                **self._headers(),
                "Cache-Control": "no-store, no-cache, must-revalidate",
                "Pragma": "no-cache",
            },
            timeout=self.timeout,
            params={"_ts": int(time.time() * 1000)},
        )
        resp.raise_for_status()
        # status 若带回 Set-Cookie，可能清掉 verified；故意不 ingest
        data = resp.json()
        if not data.get("success"):
            raise RuntimeError(data.get("message") or "查询验证状态失败")
        return data.get("data") or {}

    def ensure_secure_verified(
        self,
        code: str,
        *,
        method: str = "2fa",
        force: bool = False,
    ) -> dict[str, Any]:
        """确保 session 已通过安全验证。

        ``force=True``（拉密钥场景）：用户刚提交了验证码时必须重新 ``/api/verify``。
        """
        clean = resolve_otp_code(code)
        if not clean:
            raise RuntimeError("请输入二次验证码，或在 env/sites.json 预置 totp_secret")
        if not force:
            try:
                status = self.get_verify_status()
                if bool(status.get("verified")):
                    _log.info(
                        "安全验证仍有效，跳过 /api/verify | base=%s | expires_at=%s",
                        self.base_url,
                        status.get("expires_at"),
                    )
                    return status
            except Exception as exc:  # noqa: BLE001
                _log.debug("查询验证状态失败，将重新验证: %s", exc)
        else:
            _log.info("强制二次验证（用户已提交验证码）| base=%s", self.base_url)
        return self.verify_secure(clean, method=method)

    def prefer_cookie_session(self) -> None:
        """密码登录场景下去掉 Authorization，强制走 cookie 会话（与官方前端一致）。"""
        if self.auth_mode == "password" and self.session.headers.get("Authorization"):
            _log.info("密码登录态：去掉 Authorization，安全验证写入同一 cookie session")
            self.session.headers.pop("Authorization", None)


    def is_root(self) -> bool:
        return int(self.role or 0) >= 100

    def get_status(self) -> dict[str, Any]:
        resp = self.session.get(
            f"{self.base_url}/api/status",
            headers=self._headers(),
            timeout=self.timeout,
        )
        resp.raise_for_status()
        return resp.json()

    def create_channel(self, payload: dict[str, Any]) -> dict[str, Any]:
        resp = self.session.post(
            f"{self.base_url}/api/channel/",
            json=payload,
            headers=self._headers(),
            timeout=self.timeout,
        )
        resp.raise_for_status()
        data = resp.json()
        if not data.get("success"):
            raise RuntimeError(data.get("message") or "创建渠道失败")
        return data

    def test_channel(
        self,
        channel_id: int,
        model: str = "",
        endpoint_type: str = "",
        *,
        timeout: int | None = None,
    ) -> dict[str, Any]:
        """GET /api/channel/test/:id，与网关「测试」按钮相同。time 为秒。"""
        cid = int(channel_id)
        if cid <= 0:
            raise RuntimeError("测试渠道缺少 ID")
        params: dict[str, str] = {}
        if str(model or "").strip():
            params["model"] = str(model).strip()
        if str(endpoint_type or "").strip():
            params["endpoint_type"] = str(endpoint_type).strip()
        wait = timeout if timeout is not None else max(int(self.timeout or 30), 120)
        _log.info("测试渠道 | id=%s | model=%s", cid, params.get("model") or "(默认)")
        resp = self.session.get(
            f"{self.base_url}/api/channel/test/{cid}",
            params=params or None,
            headers=self._headers(),
            timeout=wait,
        )
        resp.raise_for_status()
        data = resp.json() if resp.content else {}
        if not isinstance(data, dict):
            raise RuntimeError("测试渠道返回异常")
        return {
            "success": bool(data.get("success")),
            "message": str(data.get("message") or ""),
            "time": float(data.get("time") or 0),
            "model": str(model or "").strip(),
        }

    def update_channel(self, channel: dict[str, Any]) -> dict[str, Any]:
        """PUT /api/channel/ 更新已有渠道。未传 key 时上游 GORM 会跳过空字段，保留原密钥。"""
        payload = dict(channel or {})
        if payload.get("id") is None:
            raise RuntimeError("更新渠道缺少 ID")
        payload["id"] = int(payload["id"])
        if not str(payload.get("key") or "").strip():
            payload.pop("key", None)
        _log.info("更新渠道 | id=%s | name=%s", payload.get("id"), payload.get("name"))
        resp = self.session.put(
            f"{self.base_url}/api/channel/",
            json=payload,
            headers=self._headers(),
            timeout=self.timeout,
        )
        resp.raise_for_status()
        data = resp.json()
        if not data.get("success"):
            raise RuntimeError(data.get("message") or "更新渠道失败")
        return data

    def update_channel_status(self, channel_id: int, status: int) -> dict[str, Any]:
        """更新渠道状态：1=启用，2=手动禁用。"""
        _log.info("更新渠道状态 | id=%s | status=%s", channel_id, status)
        resp = self.session.put(
            f"{self.base_url}/api/channel/",
            json={"id": int(channel_id), "status": int(status)},
            headers=self._headers(),
            timeout=self.timeout,
        )
        resp.raise_for_status()
        data = resp.json()
        if not data.get("success"):
            raise RuntimeError(data.get("message") or "更新渠道状态失败")
        return data

    def update_token_status(self, token_id: int, status: int) -> dict[str, Any]:
        """更新令牌状态：1=启用，2=禁用。PUT /api/token/?status_only=true。"""
        _log.info("更新令牌状态 | id=%s | status=%s", token_id, status)
        resp = self.session.put(
            f"{self.base_url}/api/token/",
            params={"status_only": "true"},
            json={"id": int(token_id), "status": int(status)},
            headers=self._headers(),
            timeout=self.timeout,
        )
        resp.raise_for_status()
        data = resp.json()
        if not data.get("success"):
            raise RuntimeError(data.get("message") or "更新令牌状态失败")
        return data

    def list_options_map(self) -> dict[str, str]:
        """获取系统选项（需 Root 权限）。"""
        resp = self.session.get(
            f"{self.base_url}/api/option/",
            headers=self._headers(),
            timeout=self.timeout,
        )
        resp.raise_for_status()
        data = resp.json()
        if not data.get("success"):
            raise RuntimeError(data.get("message") or "获取系统选项失败")

        options: dict[str, str] = {}
        for item in data.get("data") or []:
            if not isinstance(item, dict):
                continue
            key = item.get("key")
            if key:
                options[str(key)] = str(item.get("value") or "")
        return options

    def update_option(self, key: str, value: str) -> None:
        """更新系统选项（需 Root 权限）。"""
        resp = self.session.put(
            f"{self.base_url}/api/option/",
            json={"key": key, "value": value},
            headers=self._headers(),
            timeout=self.timeout,
        )
        resp.raise_for_status()
        data = resp.json()
        if not data.get("success"):
            raise RuntimeError(data.get("message") or f"更新选项 {key} 失败")

    def list_groups(self) -> list[str]:
        resp = self.session.get(
            f"{self.base_url}/api/group/",
            headers=self._headers(),
            timeout=self.timeout,
        )
        resp.raise_for_status()
        data = resp.json()
        if not data.get("success"):
            return []
        groups = data.get("data") or []
        if isinstance(groups, dict):
            return list(groups.keys())
        if isinstance(groups, list):
            names: list[str] = []
            for item in groups:
                if isinstance(item, str):
                    names.append(item)
                elif isinstance(item, dict):
                    name = item.get("name") or item.get("group")
                    if name:
                        names.append(str(name))
            return names
        return []

    def list_all_channels(self, page_size: int = 100) -> list[dict[str, Any]]:
        """分页拉取全部渠道（默认不含秘钥字段），拉取后按 ID 升序排列。

        新版 New API 服务端对列表查询 Omit(\"key\")；明文密钥需
        POST /api/channel/{id}/key（Root + 安全验证），见 fetch_channel_key。
        """
        page = 1
        items: list[dict[str, Any]] = []
        total = None
        page_size = min(max(1, int(page_size)), 100)

        while True:
            resp = self.session.get(
                f"{self.base_url}/api/channel/",
                params={
                    "p": page,
                    "page_size": page_size,
                    "status": "all",
                    "id_sort": "false",
                },
                headers=self._headers(),
                timeout=self.timeout,
            )
            resp.raise_for_status()
            payload = resp.json()
            if not payload.get("success"):
                raise RuntimeError(payload.get("message") or "获取渠道列表失败")

            data = payload.get("data") or {}
            if isinstance(data, list):
                batch = data
                total = len(batch)
            else:
                batch = data.get("items") or []
                total = data.get("total", len(items) + len(batch))
            if not isinstance(batch, list):
                break

            items.extend(batch)
            try:
                total_int = int(total)
            except (TypeError, ValueError):
                total_int = len(items)
            if len(items) >= total_int or not batch:
                break
            page += 1

        items.sort(key=lambda row: int(row.get("id") or 0))
        return items

    def fetch_channel_activity_stats(
        self,
        items: list[dict[str, Any]],
        *,
        batch_size: int = 500,
    ) -> list[dict[str, Any]]:
        """POST /api/channel/activity_stats，按渠道+模型拉近一月活跃。单批最多 500。"""
        pairs = [item for item in (items or []) if isinstance(item, dict)]
        if not pairs:
            return []
        cap = min(max(1, int(batch_size)), 500)
        collected: list[dict[str, Any]] = []
        for start in range(0, len(pairs), cap):
            chunk = pairs[start : start + cap]
            resp = self.session.post(
                f"{self.base_url}/api/channel/activity_stats",
                json={"items": chunk},
                headers=self._headers(),
                timeout=max(self.timeout, 60),
            )
            resp.raise_for_status()
            payload = resp.json() if resp.content else {}
            if not payload.get("success"):
                raise RuntimeError(payload.get("message") or "获取渠道近一月活跃失败")
            data = payload.get("data") or {}
            batch = data.get("items") if isinstance(data, dict) else None
            if not isinstance(batch, list):
                batch = payload.get("items") if isinstance(payload.get("items"), list) else []
            collected.extend(item for item in batch if isinstance(item, dict))
        return collected

    def list_user_groups(self) -> list[str]:
        """获取当前用户可用令牌分组。"""
        resp = self.session.get(
            f"{self.base_url}/api/user/self/groups",
            headers=self._headers(),
            timeout=self.timeout,
        )
        resp.raise_for_status()
        data = resp.json()
        if not data.get("success"):
            return []
        groups = data.get("data") or {}
        if isinstance(groups, dict):
            return list(groups.keys())
        if isinstance(groups, list):
            return [str(item) for item in groups]
        return []

    def list_all_tokens(self, page_size: int = 100) -> list[dict[str, Any]]:
        """分页拉取当前用户全部令牌，拉取后按 ID 降序排列（最新在上）。"""
        page = 1
        items: list[dict[str, Any]] = []
        total = None
        page_size = min(max(1, int(page_size)), 100)

        while True:
            resp = self._request_token_api(
                "GET",
                "/api/token/",
                params={"p": page, "size": page_size},
            )
            resp.raise_for_status()
            payload = resp.json()
            if not payload.get("success"):
                raise RuntimeError(payload.get("message") or "获取令牌列表失败")

            data = payload.get("data") or {}
            if isinstance(data, list):
                batch = data
                total = len(batch)
            else:
                batch = data.get("items") or []
                total = data.get("total", len(items) + len(batch))
            if not isinstance(batch, list):
                break

            items.extend(self._decrypt_token_keys(batch))
            try:
                total_int = int(total)
            except (TypeError, ValueError):
                total_int = len(items)
            if len(items) >= total_int or not batch:
                break
            page += 1

        items.sort(key=lambda row: int(row.get("id") or 0), reverse=True)
        return items

    def get_token(self, token_id: int) -> dict[str, Any]:
        resp = self._request_token_api(
            "GET",
            f"/api/token/{token_id}",
        )
        resp.raise_for_status()
        data = resp.json()
        if not data.get("success"):
            raise RuntimeError(data.get("message") or "获取令牌详情失败")
        token = self._decrypt_token_keys(data.get("data") or {})
        if not isinstance(token, dict):
            raise RuntimeError("令牌详情格式异常")
        return token

    def create_token(self, payload: dict[str, Any]) -> dict[str, Any]:
        body = dict(payload)
        model_limit = extract_model_limit(body)
        if model_limit:
            apply_model_limits(body, model_limit)
        body.pop("token_model_rate_limits", None)

        resp = self.session.post(
            f"{self.base_url}/api/token/",
            json=body,
            headers=self._headers(),
            timeout=self.timeout,
        )
        resp.raise_for_status()
        data = resp.json()
        if not data.get("success"):
            raise RuntimeError(data.get("message") or "创建令牌失败")
        return data

    def update_token(
        self,
        payload: dict[str, Any],
        *,
        preserve_token_model_rate_limits: bool = False,
    ) -> dict[str, Any]:
        body = dict(payload)
        model_limit = extract_model_limit(body)
        if model_limit:
            apply_model_limits(body, model_limit)
        if not preserve_token_model_rate_limits:
            # 旧网关对模型级限流字段兼容性不一致，默认沿用原有行为。
            body.pop("token_model_rate_limits", None)

        resp = self._request_token_api(
            "PUT",
            "/api/token/",
            json_body=body,
        )
        resp.raise_for_status()
        data = resp.json()
        if not data.get("success"):
            raise RuntimeError(data.get("message") or "更新令牌失败")
        if isinstance(data.get("data"), (dict, list)):
            data["data"] = self._decrypt_token_keys(data["data"])
        return data

    def search_tokens(self, keyword: str) -> list[dict[str, Any]]:
        resp = self._request_token_api(
            "GET",
            "/api/token/search",
            params={"keyword": keyword, "token": ""},
        )
        resp.raise_for_status()
        data = resp.json()
        if not data.get("success"):
            return []
        items = self._decrypt_token_keys(data.get("data") or [])
        return items if isinstance(items, list) else []

    def fetch_token_key(self, token_id: int) -> str:
        """按需获取单个令牌明文 key（不带 sk- 前缀）。

        新版 New API 列表接口会脱敏，需调用 POST /api/token/{id}/key。
        """
        resp = self.session.post(
            f"{self.base_url}/api/token/{token_id}/key",
            headers=self._headers(),
            timeout=self.timeout,
        )
        resp.raise_for_status()
        data = resp.json()
        if not data.get("success"):
            raise RuntimeError(data.get("message") or "获取令牌秘钥失败")
        payload = data.get("data") or {}
        key = str(payload.get("key") or "").strip()
        if not key:
            raise RuntimeError("令牌秘钥响应为空")
        return key

    def fetch_channel_key(
        self,
        channel_id: int,
        *,
        max_retries: int = 1,
        retry_wait_sec: float = 2.0,
    ) -> str:
        """获取渠道上游明文 API Key：POST /api/channel/{id}/key。

        须先调用 ``verify_secure``（session 约 5 分钟有效），且账号为 Root。
        上游对该接口使用 CriticalRateLimit（与登录/验证共用同一 IP 桶）。
        默认快速失败（不长退避），由上层在 429 时停止并提示稍后「继续补全」。
        """
        last_error: BaseException | None = None
        for attempt in range(max(1, int(max_retries))):
            resp = self.session.post(
                f"{self.base_url}/api/channel/{int(channel_id)}/key",
                json={},
                headers=self._headers(),
                timeout=self.timeout,
            )
            if resp.status_code == 429:
                note_rate_limited(self.base_url)
                last_error = requests.HTTPError(
                    f"429 Too Many Requests for url: {resp.url}",
                    response=resp,
                )
                if attempt + 1 >= max(1, int(max_retries)):
                    break
                wait = float(retry_wait_sec) * (1.0 + 0.15 * attempt) + random.uniform(0.2, 0.6)
                _log.warning(
                    "渠道密钥限流 429 | id=%s | attempt=%s/%s | wait=%.1fs",
                    channel_id,
                    attempt + 1,
                    max_retries,
                    wait,
                )
                time.sleep(wait)
                continue
            if resp.status_code == 403:
                try:
                    err = resp.json()
                except Exception:  # noqa: BLE001
                    err = {}
                code = str(err.get("code") or "")
                msg = str(err.get("message") or "需要安全验证")
                if code in {
                    "VERIFICATION_REQUIRED",
                    "VERIFICATION_EXPIRED",
                    "VERIFICATION_INVALID",
                    "EXPIRED",
                    "INVALID",
                }:
                    raise SecureVerificationError(f"{msg} [{code}]")
                raise RuntimeError(msg or "获取渠道密钥被拒绝（需 Root + 二次验证）")
            resp.raise_for_status()
            data = resp.json()
            if not data.get("success"):
                raise RuntimeError(data.get("message") or "获取渠道密钥失败")
            payload = data.get("data") or {}
            if isinstance(payload, str):
                key = payload.strip()
            else:
                key = str(payload.get("key") or "").strip()
            if not key:
                raise RuntimeError("渠道密钥响应为空")
            note_used(self.base_url, 1)
            return key
        raise RuntimeError(
            f"渠道#{channel_id} 密钥拉取触发上游限流（429），请稍后再「继续补全密钥」。"
            + (f" 详情: {last_error}" if last_error else "")
        )

    def fetch_token_keys_batch(self, token_ids: list[int]) -> dict[int, str]:
        """批量获取令牌明文 key（不带 sk- 前缀）。POST /api/token/batch/keys"""
        ids = [int(item) for item in token_ids if item is not None]
        if not ids:
            return {}

        resp = self.session.post(
            f"{self.base_url}/api/token/batch/keys",
            json={"ids": ids},
            headers=self._headers(),
            timeout=self.timeout,
        )
        resp.raise_for_status()
        data = resp.json()
        if not data.get("success"):
            raise RuntimeError(data.get("message") or "批量获取令牌秘钥失败")

        payload = data.get("data") or {}
        raw_keys = payload.get("keys") or {}
        resolved: dict[int, str] = {}
        if isinstance(raw_keys, dict):
            for token_id, key in raw_keys.items():
                text = str(key or "").strip()
                if text:
                    resolved[int(token_id)] = text
        return resolved

    def delete_channels_batch(self, channel_ids: list[int]) -> int:
        ids = [int(item) for item in channel_ids if item is not None]
        if not ids:
            return 0
        resp = self.session.post(
            f"{self.base_url}/api/channel/batch",
            json={"ids": ids},
            headers=self._headers(),
            timeout=self.timeout,
        )
        resp.raise_for_status()
        data = resp.json()
        if not data.get("success"):
            raise RuntimeError(data.get("message") or "批量删除渠道失败")
        return int(data.get("data") or len(ids))

    def delete_tokens_batch(self, token_ids: list[int]) -> int:
        ids = [int(item) for item in token_ids if item is not None]
        if not ids:
            return 0
        resp = self.session.post(
            f"{self.base_url}/api/token/batch",
            json={"ids": ids},
            headers=self._headers(),
            timeout=self.timeout,
        )
        resp.raise_for_status()
        data = resp.json()
        if not data.get("success"):
            raise RuntimeError(data.get("message") or "批量删除令牌失败")
        return int(data.get("data") or len(ids))

    def get_self_user(self) -> dict[str, Any]:
        resp = self.session.get(
            f"{self.base_url}/api/user/self",
            headers=self._headers(),
            timeout=self.timeout,
        )
        resp.raise_for_status()
        data = resp.json()
        if not data.get("success"):
            raise RuntimeError(data.get("message") or "获取用户信息失败")
        payload = data.get("data") or {}
        if payload.get("role") is not None:
            self.role = int(payload["role"])
        if payload.get("id") is not None:
            self.user_id = int(payload["id"])
        return payload

    def is_admin(self) -> bool:
        return int(self.role or 0) >= 10

    def list_logs(
        self,
        *,
        page: int = 1,
        page_size: int = 100,
        admin: bool | None = None,
        log_type: int = 0,
        start_timestamp: int | None = None,
        end_timestamp: int | None = None,
        username: str = "",
        token_name: str = "",
        model_name: str = "",
        channel: int | None = None,
        group: str = "",
    ) -> dict[str, Any]:
        use_admin = self.is_admin() if admin is None else bool(admin)
        endpoint = "/api/log/" if use_admin else "/api/log/self/"
        size = min(max(1, int(page_size)), 100)
        params: dict[str, Any] = {
            "p": max(1, int(page)),
            "page_size": size,
            "ps": size,
            "type": int(log_type or 0),
        }
        if start_timestamp:
            params["start_timestamp"] = int(start_timestamp)
        if end_timestamp:
            params["end_timestamp"] = int(end_timestamp)
        if token_name:
            params["token_name"] = token_name
        if model_name:
            params["model_name"] = model_name
        if group:
            params["group"] = group
        if use_admin:
            if username:
                params["username"] = username
            if channel not in (None, ""):
                params["channel"] = int(channel)

        # COUNT + 深分页可能超过默认 30s
        resp = self.session.get(
            f"{self.base_url}{endpoint}",
            params=params,
            headers=self._headers(),
            timeout=max(int(self.timeout or 30), 120),
        )
        resp.raise_for_status()
        data = resp.json()
        if not data.get("success"):
            raise RuntimeError(data.get("message") or "获取使用日志失败")
        return _parse_log_list_payload(data, page=page, page_size=size)


def authenticate_client(client: NewAPIClient, auth: dict[str, Any]) -> None:
    """按 Access Token 或用户名密码登录。

    密码登录优先复用进程内/磁盘会话缓存，避免连续采集反复 ``/api/user/login``
    触发 CriticalRateLimit（与 ``/api/verify``、拉密钥共用配额）。

    含密钥时请传 ``otp_code``：有缓存则直接复用会话再 ``ensure_secure_verified``；
    无缓存时登录（含登录 2FA）并写入缓存供后续「继续补全」复用。

    Access Token 可跳过 login 配额；拉密钥仍须保留 cookie session（verify 写入）。
    """
    if "verify_ssl" in auth:
        client.set_verify_ssl(coerce_verify_ssl(auth.get("verify_ssl"), True))
    access_token = str(auth.get("access_token") or "").strip()
    if access_token:
        user_id = int(auth.get("user_id") or 0)
        if not user_id:
            raise RuntimeError("使用 Access Token 时需填写用户 ID")
        cache_key = _auth_cache_key(client.base_url, "", access_token=access_token)
        skip_cache = bool(auth.get("skip_session_cache"))
        if not skip_cache and _apply_session_cache(client, cache_key):
            # 缓存可能带 Authorization + cookies；再确保 token 一致
            client.set_access_token(access_token, user_id, clear_cookies=False)
            try:
                client.get_self_user()
                return
            except Exception:  # noqa: BLE001
                _invalidate_session_cache(cache_key)
        client.set_access_token(access_token, user_id, clear_cookies=True)
        client.get_self_user()
        if client.role is None:
            # get_self_user 应已填充；兜底
            pass
        if not skip_cache:
            _store_session_cache(cache_key, client)
            client.session_cache_hit = False
            client.session_cache_expires_at = time.time() + _SESSION_CACHE_TTL_SEC
        return

    username = str(auth.get("username") or "").strip()
    password = auth.get("password") or ""
    if not username:
        raise RuntimeError("请填写用户名密码，或使用 Access Token 登录")

    otp_code = resolve_otp_code(
        auth.get("otp_code"),
        auth.get("verification_code"),
        totp_secret=auth.get("totp_secret") or auth.get("otp_secret"),
    )
    # 仅显式跳过时才绕过缓存；有 OTP 也应优先复用会话，避免每次补密钥都登录
    skip_cache = bool(auth.get("skip_session_cache"))

    cache_key = _auth_cache_key(client.base_url, username, str(password))
    if not skip_cache and _apply_session_cache(client, cache_key):
        try:
            client.get_self_user()
            return
        except Exception:  # noqa: BLE001
            _invalidate_session_cache(cache_key)

    # 无可用会话时才登录；配额不足则直接提示等待，避免空耗
    if remaining(client.base_url) < 1:
        assert_can_proceed(client.base_url, need=1)

    user = client.login(username, password, otp_code=otp_code)
    if user.get("id") is not None:
        client.user_id = int(user["id"])
    if user.get("role") is not None:
        client.role = int(user["role"])
    if not client.user_id:
        raise RuntimeError("登录成功但未返回用户 ID")
    if not skip_cache:
        _store_session_cache(cache_key, client)
        client.session_cache_hit = False
        client.session_cache_expires_at = time.time() + _SESSION_CACHE_TTL_SEC


def refresh_auth_session_cache(client: NewAPIClient, auth: dict[str, Any]) -> None:
    """登录/二次验证后刷新磁盘会话，便于下一轮跳过 login 与重复 verify。"""
    access_token = str(auth.get("access_token") or "").strip()
    if access_token:
        key = _auth_cache_key(client.base_url, "", access_token=access_token)
    else:
        username = str(auth.get("username") or "").strip()
        if not username:
            return
        key = _auth_cache_key(client.base_url, username, str(auth.get("password") or ""))
    _store_session_cache(key, client)
