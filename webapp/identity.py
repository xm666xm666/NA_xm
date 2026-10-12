"""本网站的本地身份认证、三角色权限与超管用户管理。

New API / 云厂商凭据与本网站账号相互独立。本模块只保存网站用户、
一次性令牌和审计信息；敏感明文不写入审计日志。
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import secrets
import smtplib
from datetime import UTC, datetime, timedelta
from email.message import EmailMessage
from functools import wraps
from pathlib import Path
from typing import Any, Callable, ParamSpec, TypeVar

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError
from flask import (
    Blueprint,
    Flask,
    Response,
    abort,
    current_app,
    g,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, create_engine, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, relationship, scoped_session, sessionmaker

from .local_bootstrap import load_project_env

_LOG = logging.getLogger(__name__)
_P = ParamSpec("_P")
_R = TypeVar("_R")

ROLE_SUPERADMIN = "superadmin"
ROLE_ADMIN = "admin"
ROLE_USER = "user"
ROLES = (ROLE_SUPERADMIN, ROLE_ADMIN, ROLE_USER)

FEATURE_WORKSPACE = "workspace"
FEATURE_BATCH = "batch"
FEATURE_DATA_SUMMARY = "data_summary"
FEATURE_UPSTREAM = "upstream"
FEATURE_UPSTREAM_BILL = "upstream_bill"
FEATURE_OVERVIEW = "overview"
FEATURE_AGENT = "agent"
FEATURE_EXTRACTION = "extraction"
FEATURE_USER_ADMIN = "user_admin"

ROLE_FEATURES = {
    ROLE_SUPERADMIN: {
        FEATURE_WORKSPACE,
        FEATURE_BATCH,
        FEATURE_DATA_SUMMARY,
        FEATURE_UPSTREAM,
        FEATURE_UPSTREAM_BILL,
        FEATURE_OVERVIEW,
        FEATURE_AGENT,
        FEATURE_EXTRACTION,
        FEATURE_USER_ADMIN,
    },
    ROLE_ADMIN: {
        FEATURE_WORKSPACE,
        FEATURE_BATCH,
        FEATURE_DATA_SUMMARY,
        FEATURE_UPSTREAM,
        FEATURE_EXTRACTION,
    },
    ROLE_USER: {
        FEATURE_BATCH,
        FEATURE_UPSTREAM,
        FEATURE_EXTRACTION,
    },
}


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "web_users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(512))
    role: Mapped[str] = mapped_column(String(24), default=ROLE_USER, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    email_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    must_change_password: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_bootstrap_superadmin: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    failed_login_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC), nullable=False
    )
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    tokens: Mapped[list["AccountToken"]] = relationship(back_populates="user", cascade="all, delete-orphan")


class AccountToken(Base):
    __tablename__ = "web_account_tokens"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("web_users.id", ondelete="CASCADE"), index=True)
    purpose: Mapped[str] = mapped_column(String(32), index=True)
    token_digest: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False)
    request_ip: Mapped[str] = mapped_column(String(128), default="", nullable=False)

    user: Mapped[User] = relationship(back_populates="tokens")


class AuditLog(Base):
    __tablename__ = "web_audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    actor_user_id: Mapped[int | None] = mapped_column(ForeignKey("web_users.id"), nullable=True, index=True)
    actor_username: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    actor_role: Mapped[str] = mapped_column(String(24), default="", nullable=False)
    action: Mapped[str] = mapped_column(String(96), index=True)
    resource: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    outcome: Mapped[str] = mapped_column(String(24), default="success", nullable=False)
    request_id: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    ip_address: Mapped[str] = mapped_column(String(128), default="", nullable=False)
    detail_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC), index=True, nullable=False)


class BackgroundJob(Base):
    __tablename__ = "web_background_jobs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner_user_id: Mapped[int | None] = mapped_column(ForeignKey("web_users.id"), nullable=True, index=True)
    kind: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(24), default="queued", index=True)
    payload_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    result_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class StoredArtifact(Base):
    __tablename__ = "web_artifacts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner_user_id: Mapped[int | None] = mapped_column(ForeignKey("web_users.id"), nullable=True, index=True)
    storage_key: Mapped[str] = mapped_column(String(512), unique=True, nullable=False)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str] = mapped_column(String(128), default="application/octet-stream", nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    sensitivity: Mapped[str] = mapped_column(String(24), default="internal", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False)


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _client_ip() -> str:
    forwarded = (request.headers.get("X-Forwarded-For") or "").split(",")[0].strip()
    return forwarded or (request.remote_addr or "-")


def _safe_next(value: str | None) -> str:
    text = str(value or "").strip()
    return text if text.startswith("/") and not text.startswith("//") else "/"


def _digest_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


class IdentityStore:
    """身份数据访问与不可绕过的业务规则。"""

    def __init__(self, database_url: str, *, auto_create_schema: bool) -> None:
        connect_args: dict[str, Any] = {}
        if database_url.startswith("sqlite"):
            connect_args["check_same_thread"] = False
        self.engine: Engine = create_engine(database_url, future=True, pool_pre_ping=True, connect_args=connect_args)
        self.sessions = scoped_session(sessionmaker(bind=self.engine, autoflush=False, expire_on_commit=False, future=True))
        self.passwords = PasswordHasher(time_cost=2, memory_cost=65536, parallelism=2)
        if auto_create_schema:
            Base.metadata.create_all(self.engine)

    def session(self) -> Session:
        return self.sessions()

    def close(self, _exc: BaseException | None = None) -> None:
        self.sessions.remove()

    def verify_password(self, user: User, password: str) -> bool:
        try:
            valid = self.passwords.verify(user.password_hash, password)
            if valid and self.passwords.check_needs_rehash(user.password_hash):
                user.password_hash = self.passwords.hash(password)
            return bool(valid)
        except (VerifyMismatchError, InvalidHashError):
            return False

    def create_user(
        self,
        *,
        username: str,
        email: str,
        password: str,
        role: str = ROLE_USER,
        email_verified: bool = False,
        must_change_password: bool = False,
        is_bootstrap_superadmin: bool = False,
    ) -> User:
        username = username.strip().lower()
        email = email.strip().lower()
        if not 3 <= len(username) <= 64 or not username.replace("_", "").replace("-", "").isalnum():
            raise ValueError("用户名需为 3-64 位字母、数字、下划线或连字符")
        if "@" not in email or len(email) > 255:
            raise ValueError("请输入有效邮箱")
        if role not in ROLES:
            raise ValueError("角色无效")
        if username == "admin" and not is_bootstrap_superadmin:
            raise ValueError("admin 为系统保留的默认超管账号")
        if len(password) < 12:
            raise ValueError("密码至少需要 12 位")
        db = self.session()
        if db.scalar(select(User).where((User.username == username) | (User.email == email))):
            raise ValueError("用户名或邮箱已注册")
        user = User(
            username=username,
            email=email,
            password_hash=self.passwords.hash(password),
            role=role,
            email_verified=email_verified,
            must_change_password=must_change_password,
            is_bootstrap_superadmin=is_bootstrap_superadmin,
        )
        db.add(user)
        db.commit()
        return user

    def bootstrap_superadmin(self, password: str | None) -> User | None:
        db = self.session()
        existing = db.scalar(select(User).where(User.username == "admin"))
        if existing:
            return existing
        if not password:
            return None
        return self.create_user(
            username="admin",
            email=os.getenv("BOOTSTRAP_ADMIN_EMAIL", "admin@localhost.invalid"),
            password=password,
            role=ROLE_SUPERADMIN,
            email_verified=True,
            must_change_password=True,
            is_bootstrap_superadmin=True,
        )

    def authenticate(self, identity: str, password: str) -> tuple[User | None, str]:
        db = self.session()
        key = identity.strip().lower()
        user = db.scalar(select(User).where((User.username == key) | (User.email == key)))
        generic = "账号或密码错误"
        if not user or user.is_deleted or not user.is_active:
            return None, generic
        now = _utcnow()
        locked_until = user.locked_until
        if locked_until and locked_until.tzinfo is None:
            locked_until = locked_until.replace(tzinfo=UTC)
        if locked_until and locked_until > now:
            return None, "账号已临时锁定，请稍后再试"
        if not self.verify_password(user, password):
            user.failed_login_count += 1
            if user.failed_login_count >= 5:
                user.locked_until = now + timedelta(minutes=15)
                user.failed_login_count = 0
            db.commit()
            return None, generic
        if current_app.config["REQUIRE_EMAIL_VERIFICATION"] and not user.email_verified:
            return None, "请先完成邮箱验证"
        user.failed_login_count = 0
        user.locked_until = None
        user.last_login_at = now
        db.commit()
        return user, ""

    def create_token(self, user: User, purpose: str, minutes: int) -> str:
        raw = secrets.token_urlsafe(32)
        db = self.session()
        db.query(AccountToken).filter(
            AccountToken.user_id == user.id,
            AccountToken.purpose == purpose,
            AccountToken.used_at.is_(None),
        ).update({AccountToken.used_at: _utcnow()}, synchronize_session=False)
        db.add(
            AccountToken(
                user_id=user.id,
                purpose=purpose,
                token_digest=_digest_token(raw),
                expires_at=_utcnow() + timedelta(minutes=minutes),
                request_ip=_client_ip(),
            )
        )
        db.commit()
        return raw

    def consume_token(self, raw: str, purpose: str) -> User | None:
        db = self.session()
        token = db.scalar(
            select(AccountToken).where(
                AccountToken.token_digest == _digest_token(raw),
                AccountToken.purpose == purpose,
                AccountToken.used_at.is_(None),
            )
        )
        if not token:
            return None
        expiry = token.expires_at.replace(tzinfo=UTC) if token.expires_at.tzinfo is None else token.expires_at
        if expiry <= _utcnow():
            token.used_at = _utcnow()
            db.commit()
            return None
        token.used_at = _utcnow()
        db.commit()
        return db.get(User, token.user_id)

    def audit(self, action: str, *, resource: str = "", outcome: str = "success", detail: dict[str, Any] | None = None) -> None:
        db = self.session()
        actor = getattr(g, "current_user", None)
        db.add(
            AuditLog(
                actor_user_id=getattr(actor, "id", None),
                actor_username=getattr(actor, "username", ""),
                actor_role=getattr(actor, "role", ""),
                action=action,
                resource=resource[:255],
                outcome=outcome,
                request_id=str(getattr(g, "request_id", ""))[:64],
                ip_address=_client_ip()[:128],
                detail_json=json.dumps(detail or {}, ensure_ascii=False, sort_keys=True)[:4000],
            )
        )
        db.commit()


class IdentityManager:
    def __init__(self, app: Flask, root_dir: Path) -> None:
        load_project_env(root_dir)
        self.app = app
        default_db = f"sqlite:///{(root_dir / '.cache' / 'website.db').as_posix()}"
        database_url = os.getenv("DATABASE_URL", default_db)
        production = os.getenv("APP_ENV", "development").lower() == "production"
        if production and not database_url.startswith("postgresql"):
            raise RuntimeError("生产环境必须配置 PostgreSQL DATABASE_URL")
        secret = os.getenv("APP_SECRET_KEY")
        if production and not secret:
            raise RuntimeError("生产环境必须配置 APP_SECRET_KEY")
        app.config.update(
            SECRET_KEY=secret or secrets.token_urlsafe(48),
            SESSION_COOKIE_NAME="na_web_session",
            SESSION_COOKIE_HTTPONLY=True,
            SESSION_COOKIE_SAMESITE="Lax",
            SESSION_COOKIE_SECURE=production,
            PERMANENT_SESSION_LIFETIME=timedelta(hours=8),
            REQUIRE_EMAIL_VERIFICATION=os.getenv("REQUIRE_EMAIL_VERIFICATION", "true" if production else "false").lower() == "true",
            WEB_PUBLIC_URL=os.getenv("WEB_PUBLIC_URL", "").rstrip("/"),
        )
        self._configure_server_sessions(production, root_dir)
        self.store = IdentityStore(database_url, auto_create_schema=os.getenv("WEB_AUTO_CREATE_SCHEMA", "true" if not production else "false").lower() == "true")
        self.store.bootstrap_superadmin(os.getenv("BOOTSTRAP_ADMIN_PASSWORD"))
        app.extensions["identity"] = self
        app.teardown_appcontext(self.store.close)
        app.before_request(self._load_current_user)
        app.before_request(self._guard_api)
        app.register_blueprint(self._build_blueprint())

    def _configure_server_sessions(self, production: bool, root_dir: Path) -> None:
        redis_url = os.getenv("REDIS_URL", "")
        if production and not redis_url:
            raise RuntimeError("生产环境必须配置 Redis REDIS_URL 作为服务端会话存储")
        try:
            from flask_session import Session
            if redis_url:
                import redis

                app_redis = redis.from_url(redis_url, health_check_interval=30)
                self.app.config.update(SESSION_TYPE="redis", SESSION_REDIS=app_redis)
            else:
                from cachelib import FileSystemCache

                cache_dir = root_dir / ".cache" / "flask_session"
                cache_dir.mkdir(parents=True, exist_ok=True)
                self.app.config.update(SESSION_TYPE="cachelib", SESSION_CACHELIB=FileSystemCache(str(cache_dir)))
            Session(self.app)
        except ImportError as exc:
            if production:
                raise RuntimeError("缺少 flask-session/redis 依赖，无法启用生产会话") from exc
            _LOG.warning("Flask-Session 未安装，开发环境退回 Flask 签名会话")

    def _load_current_user(self) -> None:
        g.request_id = request.headers.get("X-Request-ID") or secrets.token_hex(8)
        g.current_user = None
        user_id = session.get("user_id")
        if not user_id:
            return
        user = self.store.session().get(User, int(user_id))
        if not user or user.is_deleted or not user.is_active:
            session.clear()
            return
        g.current_user = user
        session.setdefault("csrf_token", secrets.token_urlsafe(32))

    def current_user(self) -> User | None:
        return getattr(g, "current_user", None)

    def has_feature(self, feature: str, user: User | None = None) -> bool:
        principal = user or self.current_user()
        return bool(principal and principal.role in ROLE_FEATURES and feature in ROLE_FEATURES[principal.role])

    def api_feature(self, path: str) -> str:
        if path.startswith("/api/workspace/") or path.startswith("/api/policy/") or path.startswith("/api/hygiene/"):
            return FEATURE_WORKSPACE
        if path.startswith("/api/upstream/bill") or path.startswith("/api/upstream/azure/bill"):
            return FEATURE_UPSTREAM_BILL
        if path.startswith("/api/overview/") or path.startswith("/api/artifacts"):
            return FEATURE_OVERVIEW
        if path.startswith("/api/agent/") or path == "/api/agent/run":
            return FEATURE_AGENT
        if path in {"/api/extract", "/api/extract-token", "/api/llm-presets"}:
            return FEATURE_EXTRACTION
        if path.startswith("/api/data-summary/") or path.startswith("/api/channel-balance"):
            return FEATURE_DATA_SUMMARY
        if path.startswith("/api/upstream/"):
            return FEATURE_UPSTREAM
        return FEATURE_BATCH

    def _guard_api(self) -> Response | None:
        path = request.path or ""
        if not path.startswith("/api/"):
            return None
        user = self.current_user()
        if not user:
            return jsonify({"success": False, "message": "请先登录", "code": "AUTH_REQUIRED"}), 401
        if user.must_change_password:
            return jsonify({"success": False, "message": "请先修改初始密码", "code": "PASSWORD_CHANGE_REQUIRED"}), 403
        if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
            expected = str(session.get("csrf_token") or "")
            supplied = request.headers.get("X-CSRF-Token", "")
            if not expected or not secrets.compare_digest(expected, supplied):
                return jsonify({"success": False, "message": "请求校验失败，请刷新页面后重试", "code": "CSRF_FAILED"}), 400
        feature = self.api_feature(path)
        if not self.has_feature(feature, user):
            self.store.audit("access.denied", resource=path, outcome="denied", detail={"feature": feature})
            return jsonify({"success": False, "message": "当前角色无权使用此功能", "code": "FORBIDDEN"}), 403
        return None

    def page_guard(self, feature: str | None = None) -> Response | None:
        user = self.current_user()
        if not user:
            return redirect(url_for("identity.login", next=request.full_path if request.query_string else request.path))
        if user.must_change_password and request.endpoint != "identity.account":
            return redirect(url_for("identity.account"))
        if feature and not self.has_feature(feature, user):
            abort(403)
        return None

    def csrf_token(self) -> str:
        token = str(session.get("csrf_token") or "")
        if not token:
            token = secrets.token_urlsafe(32)
            session["csrf_token"] = token
        return token

    def _send_mail(self, recipient: str, subject: str, text: str) -> None:
        host = os.getenv("SMTP_HOST", "").strip()
        if not host:
            _LOG.warning("SMTP 未配置，未发送账户邮件：subject=%s recipient=%s", subject, recipient)
            return
        message = EmailMessage()
        message["Subject"] = subject
        message["From"] = os.getenv("SMTP_FROM", "no-reply@localhost")
        message["To"] = recipient
        message.set_content(text)
        port = int(os.getenv("SMTP_PORT", "587"))
        with smtplib.SMTP(host, port, timeout=20) as smtp:
            if os.getenv("SMTP_STARTTLS", "true").lower() == "true":
                smtp.starttls()
            username = os.getenv("SMTP_USERNAME", "")
            password = os.getenv("SMTP_PASSWORD", "")
            if username:
                smtp.login(username, password)
            smtp.send_message(message)

    def _absolute_url(self, endpoint: str, **values: Any) -> str:
        relative = url_for(endpoint, _external=False, **values)
        base = str(self.app.config.get("WEB_PUBLIC_URL") or "")
        return f"{base}{relative}" if base else request.url_root.rstrip("/") + relative

    def _build_blueprint(self) -> Blueprint:
        bp = Blueprint("identity", __name__)

        @bp.get("/login")
        @bp.post("/login")
        def login():
            if self.current_user():
                return redirect(_safe_next(request.values.get("next")))
            next_url = _safe_next(request.values.get("next"))
            error = ""
            if request.method == "POST":
                if not self._verify_form_csrf():
                    error = "页面校验已失效，请刷新后重试"
                else:
                    user, error = self.store.authenticate(request.form.get("identity", ""), request.form.get("password", ""))
                    if user:
                        session.clear()
                        session["user_id"] = user.id
                        session["csrf_token"] = secrets.token_urlsafe(32)
                        session.permanent = True
                        self.store.audit("auth.login", resource=f"user:{user.id}")
                        return redirect(next_url)
                    self.store.audit("auth.login", outcome="denied", detail={"identity": request.form.get("identity", "")[:64]})
            return render_template("login.html", csrf_token=self.csrf_token(), error=error, next_url=next_url)

        @bp.get("/register")
        @bp.post("/register")
        def register():
            if self.current_user():
                return redirect("/")
            error = ""
            success = ""
            if request.method == "POST":
                if not self._verify_form_csrf():
                    error = "页面校验已失效，请刷新后重试"
                elif request.form.get("password", "") != request.form.get("password_confirm", ""):
                    error = "两次输入的密码不一致"
                else:
                    try:
                        verified = not self.app.config["REQUIRE_EMAIL_VERIFICATION"]
                        user = self.store.create_user(
                            username=request.form.get("username", ""),
                            email=request.form.get("email", ""),
                            password=request.form.get("password", ""),
                            email_verified=verified,
                        )
                        if verified:
                            success = "注册成功，请登录。"
                        else:
                            token = self.store.create_token(user, "verify_email", 30)
                            self._send_mail(user.email, "验证 NA 自动配置网站账号", f"请在 30 分钟内访问：{self._absolute_url('identity.verify_email', token=token)}")
                            success = "注册成功，验证邮件已发送。"
                        self.store.audit("auth.register", resource=f"user:{user.id}")
                    except ValueError as exc:
                        error = str(exc)
            return render_template("register.html", csrf_token=self.csrf_token(), error=error, success=success)

        @bp.get("/verify-email/<token>")
        def verify_email(token: str):
            user = self.store.consume_token(token, "verify_email")
            if not user:
                return render_template("message.html", title="验证链接无效", message="该验证链接已失效或已使用，请重新注册或联系超管。", level="error"), 400
            user.email_verified = True
            self.store.session().commit()
            self.store.audit("auth.verify_email", resource=f"user:{user.id}")
            return render_template("message.html", title="邮箱已验证", message="账号已启用，现在可以登录。", level="success")

        @bp.get("/forgot-password")
        @bp.post("/forgot-password")
        def forgot_password():
            notice = ""
            if request.method == "POST":
                if not self._verify_form_csrf():
                    notice = "页面校验已失效，请刷新后重试"
                else:
                    email = request.form.get("email", "").strip().lower()
                    user = self.store.session().scalar(select(User).where(User.email == email, User.is_active.is_(True), User.is_deleted.is_(False)))
                    if user:
                        token = self.store.create_token(user, "password_reset", 30)
                        self._send_mail(user.email, "重置 NA 自动配置网站密码", f"请在 30 分钟内访问：{self._absolute_url('identity.reset_password', token=token)}")
                        self.store.audit("auth.password_reset_requested", resource=f"user:{user.id}")
                    notice = "若该邮箱已注册，重置链接已发送。请检查收件箱和垃圾邮件。"
            return render_template("forgot_password.html", csrf_token=self.csrf_token(), notice=notice)

        @bp.get("/reset-password/<token>")
        @bp.post("/reset-password/<token>")
        def reset_password(token: str):
            error = ""
            if request.method == "POST":
                if not self._verify_form_csrf():
                    error = "页面校验已失效，请刷新后重试"
                elif request.form.get("password", "") != request.form.get("password_confirm", ""):
                    error = "两次输入的密码不一致"
                elif len(request.form.get("password", "")) < 12:
                    error = "密码至少需要 12 位"
                else:
                    user = self.store.consume_token(token, "password_reset")
                    if not user:
                        error = "重置链接已失效或已使用"
                    else:
                        user.password_hash = self.store.passwords.hash(request.form["password"])
                        user.must_change_password = False
                        self.store.session().commit()
                        self.store.audit("auth.password_reset", resource=f"user:{user.id}")
                        return render_template("message.html", title="密码已更新", message="请使用新密码登录。", level="success")
            return render_template("reset_password.html", csrf_token=self.csrf_token(), error=error)

        @bp.post("/logout")
        def logout():
            if not self._verify_form_csrf():
                abort(400)
            user = self.current_user()
            if user:
                self.store.audit("auth.logout", resource=f"user:{user.id}")
            session.clear()
            return redirect(url_for("identity.login"))

        @bp.get("/auth/me")
        def me():
            user = self.current_user()
            if not user:
                return jsonify({"authenticated": False}), 401
            return jsonify(
                {
                    "authenticated": True,
                    "user": self.public_user(user),
                    "features": sorted(ROLE_FEATURES.get(user.role, set())),
                    "csrf_token": self.csrf_token(),
                }
            )

        @bp.get("/account")
        @bp.post("/account")
        def account():
            blocked = self.page_guard()
            if blocked:
                return blocked
            user = self.current_user()
            error = ""
            success = ""
            if request.method == "POST":
                if not self._verify_form_csrf():
                    error = "页面校验已失效，请刷新后重试"
                elif not self.store.verify_password(user, request.form.get("current_password", "")):
                    error = "当前密码不正确"
                elif request.form.get("new_password", "") != request.form.get("new_password_confirm", ""):
                    error = "两次输入的新密码不一致"
                elif len(request.form.get("new_password", "")) < 12:
                    error = "新密码至少需要 12 位"
                else:
                    user.password_hash = self.store.passwords.hash(request.form["new_password"])
                    user.must_change_password = False
                    self.store.session().commit()
                    self.store.audit("auth.password_changed", resource=f"user:{user.id}")
                    success = "密码已更新"
            return render_template("account.html", user=user, csrf_token=self.csrf_token(), error=error, success=success)

        @bp.get("/admin/users")
        def admin_users():
            blocked = self.page_guard(FEATURE_USER_ADMIN)
            if blocked:
                return blocked
            users = self.store.session().scalars(select(User).where(User.is_deleted.is_(False)).order_by(User.created_at.desc())).all()
            return render_template("admin_users.html", users=users, roles=ROLES, csrf_token=self.csrf_token(), current_user=self.current_user())

        @bp.post("/admin/users/<int:user_id>/role")
        def admin_user_role(user_id: int):
            return self._admin_user_action(user_id, "role")

        @bp.post("/admin/users/<int:user_id>/status")
        def admin_user_status(user_id: int):
            return self._admin_user_action(user_id, "status")

        @bp.post("/admin/users/<int:user_id>/delete")
        def admin_user_delete(user_id: int):
            return self._admin_user_action(user_id, "delete")

        return bp

    def _verify_form_csrf(self) -> bool:
        expected = str(session.get("csrf_token") or "")
        supplied = str(request.form.get("csrf_token") or "")
        return bool(expected and supplied and secrets.compare_digest(expected, supplied))

    def _admin_user_action(self, user_id: int, action: str) -> Response:
        blocked = self.page_guard(FEATURE_USER_ADMIN)
        if blocked:
            return blocked
        if not self._verify_form_csrf():
            abort(400)
        db = self.store.session()
        target = db.get(User, user_id)
        actor = self.current_user()
        if not target or target.is_deleted:
            abort(404)
        if target.id == actor.id:
            abort(400, "不能修改当前登录账号")
        if target.is_bootstrap_superadmin:
            abort(400, "默认超管 admin 不能被降权、停用或删除")
        if action == "role":
            role = str(request.form.get("role") or "")
            if role not in ROLES:
                abort(400, "角色无效")
            target.role = role
            detail = {"role": role}
            event = "user.role_changed"
        elif action == "status":
            target.is_active = str(request.form.get("is_active") or "") == "true"
            detail = {"is_active": target.is_active}
            event = "user.status_changed"
        elif action == "delete":
            target.is_active = False
            target.is_deleted = True
            detail = {"soft_deleted": True}
            event = "user.deleted"
        else:
            abort(400)
        db.commit()
        self.store.audit(event, resource=f"user:{target.id}", detail=detail)
        return redirect(url_for("identity.admin_users"))

    @staticmethod
    def public_user(user: User) -> dict[str, Any]:
        return {"id": user.id, "username": user.username, "email": user.email, "role": user.role, "must_change_password": user.must_change_password}


def init_identity(app: Flask, root_dir: Path) -> IdentityManager:
    """绑定身份层。该函数只可在 Flask 应用创建后调用一次。"""
    return IdentityManager(app, root_dir)


def identity_required(feature: str) -> Callable[[Callable[_P, _R]], Callable[_P, _R]]:
    """为后续新增的独立路由提供显式权限装饰器。"""

    def decorator(func: Callable[_P, _R]) -> Callable[_P, _R]:
        @wraps(func)
        def wrapped(*args: _P.args, **kwargs: _P.kwargs):
            manager: IdentityManager = current_app.extensions["identity"]
            if not manager.current_user():
                abort(401)
            if not manager.has_feature(feature):
                abort(403)
            return func(*args, **kwargs)

        return wrapped

    return decorator
