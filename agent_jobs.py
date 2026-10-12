"""智能体异步任务：进程内状态机、事件队列、协作式取消、后台线程执行。

服务重启后任务不保留。
"""

from __future__ import annotations

import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any, Callable

from pipeline_runner import STEP_LABELS, execute_pipeline, normalize_step_order

TERMINAL = frozenset({"succeeded", "failed", "cancelled"})
ACTIVE = frozenset({"queued", "planning", "running", "waiting_confirm"})


@dataclass
class JobEvent:
    type: str  # step | status | log | error | done
    ts: float
    data: dict[str, Any] = field(default_factory=dict)


@dataclass
class AgentJob:
    id: str
    status: str = "queued"
    goal: str = ""
    raw_text: str = ""
    connection: dict[str, Any] = field(default_factory=dict)
    sites: list[dict[str, Any]] = field(default_factory=list)
    options: dict[str, Any] = field(default_factory=dict)
    llm_config: dict[str, Any] = field(default_factory=dict)
    channel_lines: str = ""
    plan: dict[str, Any] = field(default_factory=dict)
    steps: list[dict[str, Any]] = field(default_factory=list)
    checkpoint: str = ""
    cancel_requested: bool = False
    confirmed: bool = False
    message: str = ""
    result: dict[str, Any] = field(default_factory=dict)
    events: list[JobEvent] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    _cond: threading.Condition = field(default_factory=threading.Condition, repr=False)
    _worker_lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "status": self.status,
            "goal": self.goal,
            "raw_text": self.raw_text,
            "connection": {
                **self.connection,
                "password": "***" if self.connection.get("password") else "",
                "access_token": "***" if self.connection.get("access_token") else "",
                "otp_code": "***" if self.connection.get("otp_code") else "",
                "totp_secret": "***" if self.connection.get("totp_secret") else "",
            },
            "sites_count": len(self.sites),
            "options": self.options,
            "channel_lines": self.channel_lines,
            "plan": self.plan,
            "steps": self.steps,
            "checkpoint": self.checkpoint,
            "cancel_requested": self.cancel_requested,
            "confirmed": self.confirmed,
            "message": self.message,
            "result": self.result,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "event_count": len(self.events),
        }


class AgentJobStore:
    def __init__(self) -> None:
        self._jobs: dict[str, AgentJob] = {}
        self._lock = threading.RLock()

    def create(
        self,
        *,
        goal: str,
        raw_text: str,
        connection: dict[str, Any],
        sites: list[dict[str, Any]],
        options: dict[str, Any],
        llm_config: dict[str, Any],
        channel_lines: str = "",
    ) -> AgentJob:
        job = AgentJob(
            id=uuid.uuid4().hex[:12],
            goal=goal,
            raw_text=raw_text,
            connection=dict(connection),
            sites=list(sites),
            options=dict(options),
            llm_config=dict(llm_config),
            channel_lines=str(channel_lines or ""),
            confirmed=not bool(options.get("require_confirm", True)),
        )
        with self._lock:
            self._jobs[job.id] = job
        self.append_event(job, "log", {"message": "任务已创建"})
        return job

    def get(self, job_id: str) -> AgentJob | None:
        with self._lock:
            return self._jobs.get(job_id)

    def snapshot_jobs(self) -> list[dict[str, Any]]:
        with self._lock:
            return [job.to_dict() for job in self._jobs.values()]

    def append_event(self, job: AgentJob, etype: str, data: dict[str, Any] | None = None) -> None:
        ev = JobEvent(type=etype, ts=time.time(), data=data or {})
        with job._cond:
            job.events.append(ev)
            job.updated_at = time.time()
            job._cond.notify_all()

    def set_status(self, job: AgentJob, status: str, **extra: Any) -> None:
        with job._cond:
            job.status = status
            job.updated_at = time.time()
            for k, v in extra.items():
                if hasattr(job, k):
                    setattr(job, k, v)
            job._cond.notify_all()
        payload = {"status": status, **extra}
        self.append_event(job, "status", payload)

    def wait_events(self, job: AgentJob, after: int, timeout: float = 12.0) -> list[JobEvent]:
        with job._cond:
            if after < len(job.events):
                return list(job.events[after:])
            job._cond.wait(timeout=timeout)
            if after < len(job.events):
                return list(job.events[after:])
            return []


STORE = AgentJobStore()
_running_threads: dict[str, threading.Thread] = {}
_threads_lock = threading.Lock()


def request_cancel(job_id: str) -> AgentJob | None:
    job = STORE.get(job_id)
    if not job:
        return None
    job.cancel_requested = True
    STORE.append_event(job, "log", {"message": "已请求取消（将在步骤边界生效）"})
    if job.status == "waiting_confirm":
        STORE.set_status(job, "cancelled", message="已取消", checkpoint=job.checkpoint or "batch")
        STORE.append_event(job, "done", {"status": "cancelled"})
    return job


def apply_auth_refresh(
    job: AgentJob,
    *,
    otp_code: str = "",
    connection: dict[str, Any] | None = None,
    sites: list[dict[str, Any]] | None = None,
) -> None:
    """门禁确认 / 重试时刷新登录 2FA，不把验证码写入事件日志。"""
    conn = dict(job.connection or {})
    patch = dict(connection or {})
    code = str(otp_code or patch.get("otp_code") or patch.get("verification_code") or "").strip()
    if code:
        conn["otp_code"] = code
    totp_secret = str(patch.get("totp_secret") or patch.get("otp_secret") or "").strip()
    if totp_secret:
        conn["totp_secret"] = totp_secret
    for key in ("username", "password", "access_token", "default_key", "base_url"):
        if key in patch and patch[key] is not None:
            conn[key] = patch[key]
    if "user_id" in patch and patch["user_id"] not in (None, ""):
        conn["user_id"] = patch["user_id"]
    job.connection = conn
    if isinstance(sites, list) and sites:
        job.sites = list(sites)
    job.updated_at = time.time()


def patch_plan(job_id: str, body: dict[str, Any]) -> AgentJob | None:
    job = STORE.get(job_id)
    if not job:
        return None
    if job.status in ("running", "planning"):
        raise RuntimeError("任务执行中，无法修改计划")
    if job.status in TERMINAL and job.status == "succeeded":
        raise RuntimeError("任务已成功结束，无法修改计划")

    if "steps" in body:
        steps = normalize_step_order([str(s) for s in (body.get("steps") or [])])
        plan = dict(job.plan or {})
        plan["steps"] = steps
        if "proceed" in body:
            plan["proceed"] = bool(body.get("proceed"))
        if "advice" in body and body.get("advice") is not None:
            plan["advice"] = str(body.get("advice"))
        job.plan = plan
    elif "proceed" in body:
        plan = dict(job.plan or {})
        plan["proceed"] = bool(body.get("proceed"))
        job.plan = plan

    if "channel_lines" in body and body.get("channel_lines") is not None:
        job.channel_lines = str(body.get("channel_lines"))

    if "options" in body and isinstance(body.get("options"), dict):
        job.options = {**job.options, **body["options"]}

    if "connection" in body or "otp_code" in body or "sites" in body:
        apply_auth_refresh(
            job,
            otp_code=str(body.get("otp_code") or ""),
            connection=body.get("connection") if isinstance(body.get("connection"), dict) else None,
            sites=body.get("sites") if isinstance(body.get("sites"), list) else None,
        )

    STORE.append_event(job, "log", {"message": "计划已更新", "plan": job.plan})
    job.updated_at = time.time()
    return job


def confirm_job(
    job_id: str,
    channel_lines: str | None = None,
    *,
    otp_code: str = "",
    connection: dict[str, Any] | None = None,
    sites: list[dict[str, Any]] | None = None,
) -> AgentJob | None:
    job = STORE.get(job_id)
    if not job:
        return None
    if channel_lines is not None:
        job.channel_lines = channel_lines
    apply_auth_refresh(job, otp_code=otp_code, connection=connection, sites=sites)
    job.confirmed = True
    job.cancel_requested = False
    if not job.checkpoint:
        job.checkpoint = "batch"
    STORE.append_event(
        job,
        "log",
        {"message": "渠道行已确认", "channel_lines_len": len(job.channel_lines or "")},
    )
    job.updated_at = time.time()
    return job


def prepare_retry(job_id: str) -> AgentJob | None:
    job = STORE.get(job_id)
    if not job:
        return None
    if job.status not in ("failed", "cancelled"):
        raise RuntimeError("仅失败或已取消的任务可 retry")

    failed_id = ""
    for s in job.steps:
        if s.get("status") == "err":
            failed_id = str(s.get("id") or "")
            break
    if not failed_id:
        failed_id = job.checkpoint or "extract"

    # 保留失败步之前的成功结果
    keep: list[dict[str, Any]] = []
    for s in job.steps:
        if s.get("id") == failed_id:
            break
        if s.get("status") in ("ok", "warn", "skipped"):
            keep.append(s)
    job.steps = keep
    job.checkpoint = failed_id
    job.cancel_requested = False
    job.message = f"准备从「{STEP_LABELS.get(failed_id, failed_id)}」重试"
    if failed_id == "batch":
        job.confirmed = True
    STORE.set_status(job, "queued", message=job.message)
    STORE.append_event(job, "log", {"message": job.message, "checkpoint": failed_id})
    return job


def _steps_from_result(result_steps: list[Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for s in result_steps:
        if hasattr(s, "id"):
            out.append(asdict(s))
        elif isinstance(s, dict):
            out.append(s)
    return out


def run_job_worker(
    job_id: str,
    load_deps: Callable[[], tuple[Any, Any, Any, Any]],
    start_from: str | None = None,
) -> None:
    job = STORE.get(job_id)
    if not job:
        return
    if not job._worker_lock.acquire(blocking=False):
        STORE.append_event(job, "log", {"message": "已有执行线程在运行，忽略重复 start"})
        return
    try:
        extract_fn, plan_fn, batch, project_dir = load_deps()

        from pipeline_runner import StepResult

        existing: list[StepResult] = []
        for s in job.steps:
            existing.append(
                StepResult(
                    id=str(s.get("id") or ""),
                    label=str(s.get("label") or ""),
                    status=str(s.get("status") or "ok"),
                    message=str(s.get("message") or ""),
                    data=dict(s.get("data") or {}),
                )
            )

        def on_event(etype: str, data: dict[str, Any]) -> None:
            if etype == "status":
                st = str(data.get("status") or "")
                if st == "planning":
                    job.status = "planning"
                elif st == "running":
                    job.status = "running"
                    if data.get("running_step"):
                        job.checkpoint = str(data["running_step"])
                    if data.get("plan"):
                        job.plan = dict(data["plan"])
                elif st == "waiting_confirm":
                    job.status = "waiting_confirm"
                    job.checkpoint = str(data.get("checkpoint") or "batch")
                    if "channel_lines" in data:
                        job.channel_lines = str(data.get("channel_lines") or "")
                    job.message = "等待确认渠道行"
                elif st in TERMINAL:
                    job.status = st
                    if data.get("checkpoint"):
                        job.checkpoint = str(data["checkpoint"])
                job.updated_at = time.time()
            STORE.append_event(job, etype, data)

        STORE.append_event(
            job,
            "log",
            {"message": f"开始执行（from={start_from or 'plan'}）"},
        )

        result = execute_pipeline(
            raw_text=job.raw_text,
            goal=job.goal,
            connection=job.connection,
            sites=job.sites,
            options=job.options,
            llm_config=job.llm_config,
            extract_channels=extract_fn,
            plan_pipeline_fn=plan_fn,
            batch=batch,
            project_dir=project_dir,
            channel_lines=job.channel_lines,
            plan_dict=job.plan if job.plan.get("steps") and start_from not in (None, "", "plan") else None,
            existing_steps=existing if start_from not in (None, "", "plan") else None,
            start_from=start_from,
            confirmed=job.confirmed,
            should_cancel=lambda: job.cancel_requested,
            on_event=on_event,
        )

        job.channel_lines = result.channel_lines
        job.plan = result.plan
        job.steps = _steps_from_result(result.steps)
        job.message = result.message
        job.result = result.to_dict()
        # 透出令牌相关产物供 UI
        if result.token_lines:
            job.result["token_lines"] = result.token_lines
        if result.token_export_text:
            job.result["token_export_text"] = result.token_export_text
        job.updated_at = time.time()

        if result.outcome == "waiting_confirm":
            job.status = "waiting_confirm"
            job.checkpoint = "batch"
            STORE.append_event(
                job,
                "status",
                {
                    "status": "waiting_confirm",
                    "checkpoint": "batch",
                    "channel_lines": job.channel_lines,
                },
            )
            return

        if result.outcome == "cancelled" or job.cancel_requested:
            job.status = "cancelled"
            STORE.append_event(job, "done", {"status": "cancelled", "message": job.message})
            return

        if result.outcome == "succeeded" and result.success:
            job.status = "succeeded"
            job.checkpoint = ""
            STORE.append_event(job, "done", {"status": "succeeded", "message": job.message})
            return

        # failed / partial
        job.status = "failed"
        # checkpoint = 第一个 err 步
        for s in job.steps:
            if s.get("status") == "err":
                job.checkpoint = str(s.get("id") or "")
                break
        STORE.append_event(job, "error", {"message": job.message, "checkpoint": job.checkpoint})
        STORE.append_event(job, "done", {"status": "failed", "message": job.message})
    except Exception as exc:  # noqa: BLE001
        job.status = "failed"
        job.message = str(exc)
        STORE.append_event(job, "error", {"message": str(exc)})
        STORE.append_event(job, "done", {"status": "failed", "message": str(exc)})
    finally:
        job._worker_lock.release()
        with job._cond:
            job._cond.notify_all()
        with _threads_lock:
            _running_threads.pop(job_id, None)


def start_job_thread(
    job_id: str,
    load_deps: Callable[[], tuple[Any, Any, Any, Any]],
    start_from: str | None = None,
) -> threading.Thread | None:
    job = STORE.get(job_id)
    if not job:
        return None
    with _threads_lock:
        existing = _running_threads.get(job_id)
        if existing and existing.is_alive():
            return existing
        t = threading.Thread(
            target=run_job_worker,
            args=(job_id, load_deps, start_from),
            name=f"agent-job-{job_id}",
            daemon=True,
        )
        _running_threads[job_id] = t
        t.start()
        return t
