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
from datetime import UTC, datetime, timedelta
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
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, create_engine, func, select
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

# 去掉容易混淆的字符，恢复码可在手机上准确抄录；12 位约有 60 bit 熵。
RECOVERY_CODE_ALPHABET = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"
RECOVERY_CODE_LENGTH = 12
RECOVERY_CODE_MAX_FAILURES = 5
RECOVERY_CODE_LOCK_MINUTES = 15

FEATURE_WORKSPACE = "workspace"
FEATURE_BATCH = "batch"
FEATURE_PLATFORM = "platform"
FEATURE_DATA_SUMMARY = "data_summary"
FEATURE_UPSTREAM = "upstream"
FEATURE_UPSTREAM_BILL = "upstream_bill"
FEATURE_OVERVIEW = "overview"
FEATURE_AGENT = "agent"
FEATURE_EXTRACTION = "extraction"
FEATURE_USER_ADMIN = "user_admin"
DEFAULT_USER_FEATURES = frozenset({FEATURE_EXTRACTION})

# 可由超管逐账户授予的功能；角色标签不再隐式授予这些权限。
FEATURE_OPTIONS = (
    (FEATURE_WORKSPACE, "工作台", "查看工作台、任务进度和产物"),
    (FEATURE_EXTRACTION, "智能提取", "使用渠道与令牌提取"),
    (FEATURE_BATCH, "批量配置", "连接站点并管理渠道、令牌和分组"),
    (FEATURE_PLATFORM, "平台信息", "跨 test / uat / prod 查看和编辑 ai-cloud 模型与令牌"),
    (FEATURE_DATA_SUMMARY, "数据汇总", "采集站点数据并导出汇总"),
    (FEATURE_UPSTREAM, "上游信息", "采集火山云与 Azure 上游资源"),
    (FEATURE_UPSTREAM_BILL, "上游账单", "采集和导出云厂商账单"),
    (FEATURE_OVERVIEW, "一表总览", "查看总览、卫生策略和智能分析"),
    (FEATURE_AGENT, "智能体", "创建并执行智能体任务"),
)
FEATURE_KEYS = frozenset(feature for feature, _label, _description in FEATURE_OPTIONS)
FEATURE_ORDER = tuple(feature for feature, _label, _description in FEATURE_OPTIONS)
FEATURE_LABELS = {feature: label for feature, label, _description in FEATURE_OPTIONS}

# 产物不共享一个笼统的“下载”权限：同一个通用接口会服务于数据汇总、
# 上游信息、账单和一表总览。按类型归属，才能既让管理员正常使用其已获
# 授权的历史文件，又不会借下载接口读取超管专属文件。
ARTIFACT_KIND_FEATURES = {
    "summary": FEATURE_DATA_SUMMARY,
    "balance": FEATURE_DATA_SUMMARY,
    "upstream": FEATURE_UPSTREAM,
    "overview": FEATURE_OVERVIEW,
    "analysis": FEATURE_OVERVIEW,
    "bill": FEATURE_UPSTREAM_BILL,
    "bill_azure": FEATURE_UPSTREAM_BILL,
    "bill_combined": FEATURE_UPSTREAM_BILL,
    "logs": FEATURE_BATCH,
}

_BATCH_API_PATHS = frozenset(
    {
        "/api/batch-config",
        "/api/env-sites",
        "/api/channel-types",
        "/api/test-connection",
        "/api/batch-create",
        "/api/channel-test",
        "/api/batch-update-channels",
        "/api/channel-remark-sync",
        "/api/channel-models",
        "/api/token-batch-create",
        "/api/token-batch-update",
        "/api/token-export",
        "/api/groups-list",
        "/api/groups-members",
        "/api/groups-switch",
        "/api/groups-create",
        "/api/groups-delete",
        "/api/batch-delete-channels",
        "/api/batch-channel-status",
        "/api/token-batch-delete",
        "/api/token-batch-status",
    }
)


def artifact_feature(kind: str | None) -> str | None:
    """返回某类 Excel 产物所需能力；未知类型必须由调用方拒绝。"""
    return ARTIFACT_KIND_FEATURES.get(str(kind or "").strip().lower())

class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "web_users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(512))
    role: Mapped[str] = mapped_column(String(24), default=ROLE_USER, index=True)
    features_json: Mapped[str] = mapped_column(Text, default='["extraction"]', server_default='["extraction"]', nullable=False)
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


class PermissionRequest(Base):
    __tablename__ = "web_permission_requests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("web_users.id", ondelete="CASCADE"), index=True)
    requested_features_json: Mapped[str] = mapped_column(Text, nullable=False)
    approved_features_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="pending", index=True, nullable=False)
    reviewer_note: Mapped[str] = mapped_column(String(1000), default="", nullable=False)
    reviewed_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("web_users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


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


class PasswordRecoveryCode(Base):
    """每个网站账户的一份恢复验证码；明文绝不落库。"""

    __tablename__ = "web_password_recovery_codes"
    __table_args__ = (UniqueConstraint("user_id", name="uq_web_password_recovery_codes_user_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("web_users.id", ondelete="CASCADE"), index=True)
    code_hash: Mapped[str] = mapped_column(String(512), nullable=False)
    failed_attempt_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False)
    rotated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC), nullable=False
    )


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
            role=ROLE_USER if role != ROLE_SUPERADMIN else ROLE_SUPERADMIN,
            features_json=json.dumps(sorted(DEFAULT_USER_FEATURES)),
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

    @staticmethod
    def _normalize_recovery_code(raw: str) -> str:
        return "".join(char for char in str(raw or "").upper() if char.isalnum())

    @staticmethod
    def _display_recovery_code(raw: str) -> str:
        return "-".join(raw[index : index + 4] for index in range(0, len(raw), 4))

    @staticmethod
    def _normalize_utc(value: datetime | None) -> datetime | None:
        if value and value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value

    def issue_password_recovery_code(self, user: User) -> str:
        """轮换恢复验证码，调用方只能在当前响应中展示一次明文。"""
        raw = "".join(secrets.choice(RECOVERY_CODE_ALPHABET) for _ in range(RECOVERY_CODE_LENGTH))
        db = self.session()
        record = db.scalar(select(PasswordRecoveryCode).where(PasswordRecoveryCode.user_id == user.id))
        if record:
            record.code_hash = self.passwords.hash(raw)
            record.failed_attempt_count = 0
            record.locked_until = None
        else:
            db.add(PasswordRecoveryCode(user_id=user.id, code_hash=self.passwords.hash(raw)))
        db.commit()
        return self._display_recovery_code(raw)

    def reset_password_with_recovery_code(
        self,
        *,
        identity: str,
        recovery_code: str,
        new_password: str,
    ) -> tuple[User | None, str, str]:
        """以账户与恢复码重置密码，并在成功后轮换恢复码。

        返回 ``(user, error, next_recovery_code)``。错误始终使用泛化消息，
        避免通过此接口枚举邮箱或用户名。
        """
        key = str(identity or "").strip().lower()
        normalized_code = self._normalize_recovery_code(recovery_code)
        generic_error = "账号或恢复验证码不正确"
        if not key or len(normalized_code) != RECOVERY_CODE_LENGTH:
            return None, generic_error, ""

        db = self.session()
        user = db.scalar(
            select(User).where(
                (User.username == key) | (User.email == key),
                User.is_active.is_(True),
                User.is_deleted.is_(False),
            )
        )
        if not user:
            return None, generic_error, ""
        record = db.scalar(select(PasswordRecoveryCode).where(PasswordRecoveryCode.user_id == user.id))
        if not record:
            return None, generic_error, ""

        now = _utcnow()
        locked_until = self._normalize_utc(record.locked_until)
        if locked_until and locked_until > now:
            return None, "恢复验证码已临时锁定，请 15 分钟后再试", ""

        try:
            valid = self.passwords.verify(record.code_hash, normalized_code)
            if valid and self.passwords.check_needs_rehash(record.code_hash):
                record.code_hash = self.passwords.hash(normalized_code)
        except (VerifyMismatchError, InvalidHashError):
            valid = False

        if not valid:
            record.failed_attempt_count += 1
            if record.failed_attempt_count >= RECOVERY_CODE_MAX_FAILURES:
                record.locked_until = now + timedelta(minutes=RECOVERY_CODE_LOCK_MINUTES)
                record.failed_attempt_count = 0
            db.commit()
            return None, generic_error, ""

        user.password_hash = self.passwords.hash(new_password)
        user.must_change_password = False
        record.failed_attempt_count = 0
        record.locked_until = None
        db.commit()
        next_code = self.issue_password_recovery_code(user)
        return user, "", next_code

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
        )
        self._configure_server_sessions(production, root_dir)
        auto_create_schema = os.getenv("WEB_AUTO_CREATE_SCHEMA", "true" if not production else "false").lower() == "true"
        if auto_create_schema and not production:
            self._upgrade_local_schema(root_dir, database_url)
        self.store = IdentityStore(database_url, auto_create_schema=auto_create_schema)
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

    @staticmethod
    def _upgrade_local_schema(root_dir: Path, database_url: str) -> None:
        config_path = root_dir / "alembic.ini"
        if not config_path.is_file():
            return
        from alembic import command
        from alembic.config import Config

        config = Config(str(config_path))
        config.set_main_option("script_location", str(root_dir / "migrations"))
        config.set_main_option("prepend_sys_path", str(root_dir).replace("%", "%%"))
        config.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))
        command.upgrade(config, "head")

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
        if not principal:
            return False
        if principal.role == ROLE_SUPERADMIN:
            return feature in FEATURE_KEYS or feature == FEATURE_USER_ADMIN
        return feature in self.user_features(principal)

    @staticmethod
    def user_features(user: User) -> set[str]:
        if user.role == ROLE_SUPERADMIN:
            return set(FEATURE_KEYS) | {FEATURE_USER_ADMIN}
        try:
            values = json.loads(user.features_json or "[]")
        except (TypeError, ValueError):
            return set()
        if not isinstance(values, list):
            return set()
        return {str(value) for value in values if str(value) in FEATURE_KEYS}

    @staticmethod
    def role_for_features(features: set[str]) -> str:
        return ROLE_ADMIN if features - DEFAULT_USER_FEATURES else ROLE_USER

    def api_feature(self, path: str) -> str | None:
        """将每一个业务 API 收敛到唯一能力；未知 API 一律不自动放行。

        过去的兜底会把任意新 `/api/*` 归入批量配置，普通用户可能在新接口
        上意外获得权限。这里故意采用显式映射，新增接口必须同时声明权限。
        """
        if path in {"/api/artifacts", "/api/artifacts/download"}:
            # 兼容历史的未带 kind 的超管下载链接；非超管必须显式带所属类型。
            return artifact_feature(request.args.get("kind")) or FEATURE_OVERVIEW
        if path.startswith("/api/workspace/"):
            return FEATURE_WORKSPACE
        if path.startswith("/api/policy/") or path.startswith("/api/hygiene/"):
            return FEATURE_OVERVIEW
        if path.startswith("/api/upstream/bill") or path.startswith("/api/upstream/azure/bill"):
            return FEATURE_UPSTREAM_BILL
        if path.startswith("/api/overview/"):
            return FEATURE_OVERVIEW
        if path.startswith("/api/agent/") or path == "/api/agent/run":
            return FEATURE_AGENT
        if path in {"/api/extract", "/api/extract-token", "/api/llm-presets"}:
            return FEATURE_EXTRACTION
        if path.startswith("/api/data-summary/") or path.startswith("/api/channel-balance"):
            return FEATURE_DATA_SUMMARY
        if path.startswith("/api/platform/"):
            return FEATURE_PLATFORM
        if path.startswith("/api/upstream/"):
            return FEATURE_UPSTREAM
        if path in _BATCH_API_PATHS or path == "/api/logs-export" or path.startswith("/api/logs-export/"):
            return FEATURE_BATCH
        return None

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
        if not feature or not self.has_feature(feature, user):
            self.store.audit("access.denied", resource=path, outcome="denied", detail={"feature": feature or "unmapped"})
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
            recovery_code = ""
            if request.method == "POST":
                if not self._verify_form_csrf():
                    error = "页面校验已失效，请刷新后重试"
                elif request.form.get("password", "") != request.form.get("password_confirm", ""):
                    error = "两次输入的密码不一致"
                else:
                    try:
                        user = self.store.create_user(
                            username=request.form.get("username", ""),
                            email=request.form.get("email", ""),
                            password=request.form.get("password", ""),
                            # 网站账户不再经 SMTP 发送验证链接；邮箱只作登录标识与唯一性字段。
                            email_verified=True,
                        )
                        recovery_code = self.store.issue_password_recovery_code(user)
                        success = "注册成功。请立即保存下方恢复验证码；它只会显示这一次。"
                        self.store.audit("auth.register", resource=f"user:{user.id}")
                    except ValueError as exc:
                        error = str(exc)
            return render_template(
                "register.html",
                csrf_token=self.csrf_token(),
                error=error,
                success=success,
                recovery_code=recovery_code,
            )

        @bp.get("/verify-email/<token>")
        def verify_email(token: str):
            # 兼容历史邮件链接：不再消费令牌或发送新的邮件。
            return render_template(
                "message.html",
                title="邮箱验证已下线",
                message="网站账户现使用恢复验证码找回密码，请使用已有账户直接登录。",
                level="success",
            )

        @bp.get("/forgot-password")
        @bp.post("/forgot-password")
        def forgot_password():
            error = ""
            notice = ""
            recovery_code = ""
            if request.method == "POST":
                if not self._verify_form_csrf():
                    error = "页面校验已失效，请刷新后重试"
                elif request.form.get("password", "") != request.form.get("password_confirm", ""):
                    error = "两次输入的新密码不一致"
                elif len(request.form.get("password", "")) < 12:
                    error = "新密码至少需要 12 位"
                else:
                    user, error, recovery_code = self.store.reset_password_with_recovery_code(
                        identity=request.form.get("identity", ""),
                        recovery_code=request.form.get("recovery_code", ""),
                        new_password=request.form.get("password", ""),
                    )
                    if user:
                        self.store.audit("auth.password_reset", resource=f"user:{user.id}")
                        notice = "密码已更新。请保存新的恢复验证码；旧验证码已立即失效。"
                    else:
                        self.store.audit("auth.password_reset", outcome="denied")
            return render_template(
                "forgot_password.html",
                csrf_token=self.csrf_token(),
                error=error,
                notice=notice,
                recovery_code=recovery_code,
            )

        @bp.get("/reset-password/<token>")
        @bp.post("/reset-password/<token>")
        def reset_password(token: str):
            # 历史邮件链接不再是凭据，统一进入验证码重置页。
            return redirect(url_for("identity.forgot_password"))

        @bp.post("/logout")
        def logout():
            # 工作台通过 X-CSRF-Token 发起退出；普通页面表单仍可使用 csrf_token 字段。
            if not self._verify_logout_csrf():
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
            pending_requests = 0
            if user.role == ROLE_SUPERADMIN:
                pending_requests = int(
                    self.store.session().scalar(
                        select(func.count(PermissionRequest.id)).where(PermissionRequest.status == "pending")
                    )
                    or 0
                )
            return jsonify(
                {
                    "authenticated": True,
                    "user": self.public_user(user),
                    "features": sorted(self.user_features(user)),
                    "pending_permission_requests": pending_requests,
                    "csrf_token": self.csrf_token(),
                }
            )

        @bp.get("/permissions/request")
        @bp.post("/permissions/request")
        def permission_request():
            blocked = self.page_guard()
            if blocked:
                return blocked
            user = self.current_user()
            if user.role == ROLE_SUPERADMIN:
                return redirect(url_for("identity.admin_users", _anchor="permission-requests"))
            db = self.store.session()
            error = ""
            success = ""
            if request.method == "POST":
                if not self._verify_form_csrf():
                    error = "页面校验已失效，请刷新后重试"
                else:
                    selected = {str(value) for value in request.form.getlist("feature")}
                    if not selected or not selected <= FEATURE_KEYS:
                        error = "请选择至少一项有效功能"
                    else:
                        selected -= self.user_features(user)
                        pending = db.scalar(
                            select(PermissionRequest).where(
                                PermissionRequest.user_id == user.id,
                                PermissionRequest.status == "pending",
                            )
                        )
                        if pending:
                            error = "你已有待处理申请，请等待超管处理后再提交"
                        elif not selected:
                            error = "所选功能已全部开通"
                        else:
                            item = PermissionRequest(
                                user_id=user.id,
                                requested_features_json=json.dumps(sorted(selected), ensure_ascii=False),
                            )
                            db.add(item)
                            db.commit()
                            self.store.audit(
                                "permission.requested",
                                resource=f"permission_request:{item.id}",
                                detail={"features": sorted(selected)},
                            )
                            success = "申请已通知超管 admin，请等待处理。"
            history = db.scalars(
                select(PermissionRequest)
                .where(PermissionRequest.user_id == user.id)
                .order_by(PermissionRequest.created_at.desc())
            ).all()
            history_features = {}
            for item in history:
                try:
                    raw_keys = item.approved_features_json if item.status == "approved" else item.requested_features_json
                    values = json.loads(raw_keys or "[]")
                except (TypeError, ValueError):
                    values = []
                keys = {str(value) for value in values} if isinstance(values, list) else set()
                history_features[item.id] = [FEATURE_LABELS[key] for key in FEATURE_ORDER if key in keys]
            current_features = self.user_features(user)
            available_options = [option for option in FEATURE_OPTIONS if option[0] not in current_features]
            return render_template(
                "permission_request.html",
                user=user,
                feature_options=available_options,
                requests=history,
                history_features=history_features,
                csrf_token=self.csrf_token(),
                error=error,
                success=success,
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
            recovery_code = ""
            if request.method == "POST":
                if not self._verify_form_csrf():
                    error = "页面校验已失效，请刷新后重试"
                elif not self.store.verify_password(user, request.form.get("current_password", "")):
                    error = "当前密码不正确"
                elif request.form.get("action") == "rotate_recovery_code":
                    recovery_code = self.store.issue_password_recovery_code(user)
                    success = "已生成新的恢复验证码，旧验证码已立即失效。请保存下方内容。"
                    self.store.audit("auth.recovery_code_rotated", resource=f"user:{user.id}")
                elif request.form.get("new_password", "") != request.form.get("new_password_confirm", ""):
                    error = "两次输入的新密码不一致"
                elif len(request.form.get("new_password", "")) < 12:
                    error = "新密码至少需要 12 位"
                else:
                    user.password_hash = self.store.passwords.hash(request.form["new_password"])
                    user.must_change_password = False
                    self.store.session().commit()
                    recovery_code = self.store.issue_password_recovery_code(user)
                    self.store.audit("auth.password_changed", resource=f"user:{user.id}")
                    success = "密码已更新。请保存下方新的恢复验证码；旧验证码已立即失效。"
            return render_template(
                "account.html",
                user=user,
                csrf_token=self.csrf_token(),
                error=error,
                success=success,
                recovery_code=recovery_code,
            )

        @bp.get("/admin/users")
        def admin_users():
            blocked = self.page_guard(FEATURE_USER_ADMIN)
            if blocked:
                return blocked
            users = self.store.session().scalars(select(User).where(User.is_deleted.is_(False)).order_by(User.created_at.desc())).all()
            permission_map = {user.id: self.user_features(user) for user in users}
            pending_requests = self.store.session().scalars(
                select(PermissionRequest)
                .where(PermissionRequest.status == "pending")
                .order_by(PermissionRequest.created_at.asc())
            ).all()
            request_users = {
                request_item.id: self.store.session().get(User, request_item.user_id)
                for request_item in pending_requests
            }
            request_feature_map = {}
            for item in pending_requests:
                try:
                    values = json.loads(item.requested_features_json or "[]")
                except (TypeError, ValueError):
                    values = []
                keys = {str(value) for value in values} if isinstance(values, list) else set()
                request_feature_map[item.id] = [option for option in FEATURE_OPTIONS if option[0] in keys]
            return render_template(
                "admin_users.html",
                users=users,
                feature_options=FEATURE_OPTIONS,
                permission_map=permission_map,
                pending_requests=pending_requests,
                request_users=request_users,
                request_feature_map=request_feature_map,
                feature_labels={key: label for key, label, _description in FEATURE_OPTIONS},
                csrf_token=self.csrf_token(),
                current_user=self.current_user(),
            )

        @bp.post("/admin/users/<int:user_id>/permissions")
        def admin_user_permissions(user_id: int):
            return self._admin_user_action(user_id, "permissions")

        @bp.post("/admin/permission-requests/<int:request_id>/approve")
        def admin_permission_request_approve(request_id: int):
            return self._admin_permission_request_action(request_id, "approve")

        @bp.post("/admin/permission-requests/<int:request_id>/reject")
        def admin_permission_request_reject(request_id: int):
            return self._admin_permission_request_action(request_id, "reject")

        @bp.post("/admin/users/<int:user_id>/status")
        def admin_user_status(user_id: int):
            return self._admin_user_action(user_id, "status")

        @bp.post("/admin/users/<int:user_id>/delete")
        def admin_user_delete(user_id: int):
            return self._admin_user_action(user_id, "delete")

        @bp.post("/admin/users/create")
        def admin_user_create():
            return self._admin_create_user()

        @bp.post("/admin/users/<int:user_id>/password")
        def admin_user_password(user_id: int):
            return self._admin_reset_password(user_id)

        return bp

    def _verify_form_csrf(self) -> bool:
        expected = str(session.get("csrf_token") or "")
        supplied = str(request.form.get("csrf_token") or "")
        return bool(expected and supplied and secrets.compare_digest(expected, supplied))

    def _verify_logout_csrf(self) -> bool:
        """验证退出请求的同源令牌，兼容工作台 Fetch 与传统表单提交。"""
        expected = str(session.get("csrf_token") or "")
        supplied = str(request.form.get("csrf_token") or request.headers.get("X-CSRF-Token", ""))
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
        if target.role == ROLE_SUPERADMIN:
            abort(400, "超管账户不能通过普通用户管理操作修改")
        if action == "permissions":
            selected = {str(value) for value in request.form.getlist("feature")}
            if not selected <= FEATURE_KEYS:
                abort(400, "功能权限无效")
            target.features_json = json.dumps(sorted(selected), ensure_ascii=False)
            target.role = self.role_for_features(selected)
            detail = {"features": sorted(selected)}
            event = "user.permissions_changed"
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
        return redirect(url_for("identity.admin_users", _anchor="users"))

    def _admin_create_user(self) -> Response:
        blocked = self.page_guard(FEATURE_USER_ADMIN)
        if blocked:
            return blocked
        if not self._verify_form_csrf():
            abort(400)
        role = str(request.form.get("role") or ROLE_USER)
        if role not in (ROLE_USER, ROLE_ADMIN):
            abort(400, "角色无效")
        password = str(request.form.get("password") or "")
        password_confirm = str(request.form.get("password_confirm") or "")
        if password != password_confirm:
            abort(400, "两次输入的密码不一致")
        try:
            user = self.store.create_user(
                username=request.form.get("username", ""),
                email=request.form.get("email", ""),
                password=password,
                role=role,
                email_verified=True,
                must_change_password=True,
            )
        except ValueError as exc:
            abort(400, str(exc))
        db = self.store.session()
        if role == ROLE_ADMIN:
            user.features_json = json.dumps(sorted(FEATURE_KEYS), ensure_ascii=False)
            user.role = ROLE_ADMIN
        else:
            user.features_json = json.dumps(sorted(DEFAULT_USER_FEATURES), ensure_ascii=False)
            user.role = ROLE_USER
        db.commit()
        self.store.audit("user.created_by_admin", resource=f"user:{user.id}", detail={"username": user.username, "role": user.role})
        return redirect(url_for("identity.admin_users", _anchor="users"))

    def _admin_reset_password(self, user_id: int) -> Response:
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
            abort(400, "默认超管 admin 的密码请在账户设置中修改")
        if target.role == ROLE_SUPERADMIN:
            abort(400, "超管账户不能通过普通用户管理操作修改")
        new_password = str(request.form.get("new_password") or "")
        new_password_confirm = str(request.form.get("new_password_confirm") or "")
        if new_password != new_password_confirm:
            abort(400, "两次输入的新密码不一致")
        if len(new_password) < 12:
            abort(400, "新密码至少需要 12 位")
        target.password_hash = self.store.passwords.hash(new_password)
        target.must_change_password = True
        target.failed_login_count = 0
        target.locked_until = None
        db.commit()
        self.store.audit("user.password_changed_by_admin", resource=f"user:{target.id}", detail={"must_change_password": True})
        return redirect(url_for("identity.admin_users", _anchor="users"))

    def _admin_permission_request_action(self, request_id: int, action: str) -> Response:
        blocked = self.page_guard(FEATURE_USER_ADMIN)
        if blocked:
            return blocked
        if not self._verify_form_csrf():
            abort(400)
        db = self.store.session()
        item = db.get(PermissionRequest, request_id)
        if not item or item.status != "pending":
            abort(404)
        requester = db.get(User, item.user_id)
        if not requester or requester.role == ROLE_SUPERADMIN:
            abort(404)
        if requester.is_deleted and action == "approve":
            abort(404)
        try:
            values = json.loads(item.requested_features_json or "[]")
        except (TypeError, ValueError):
            values = []
        requested = {str(value) for value in values} if isinstance(values, list) else set()
        requested &= FEATURE_KEYS
        if action == "approve":
            selected = {str(value) for value in request.form.getlist("feature")}
            if not selected or not selected <= requested:
                abort(400, "请选择至少一项有效的申请权限")
            grants = self.user_features(requester) | selected
            requester.features_json = json.dumps(sorted(grants), ensure_ascii=False)
            requester.role = self.role_for_features(grants)
            item.approved_features_json = json.dumps(sorted(selected), ensure_ascii=False)
            item.status = "approved"
            event = "permission.approved"
            detail = {"features": sorted(selected), "role": requester.role}
        elif action == "reject":
            item.status = "rejected"
            event = "permission.rejected"
            detail = {"features": sorted(requested)}
        else:
            abort(400)
        item.reviewer_note = str(request.form.get("reviewer_note") or "").strip()[:1000]
        item.reviewed_by_user_id = self.current_user().id
        item.reviewed_at = _utcnow()
        db.commit()
        self.store.audit(event, resource=f"permission_request:{item.id}", detail=detail)
        return redirect(url_for("identity.admin_users", _anchor="permission-requests"))

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
