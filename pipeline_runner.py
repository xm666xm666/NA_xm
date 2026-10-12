"""NA 自动配置 — 流水线执行器（提取 / 渠道 / 令牌 / 导出 / 汇总 / 上游 / 总览 / 分析）。

支持同步一键跑完，以及按步执行 / 检查点 / 门禁 / 取消回调（供异步任务使用）。
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable

STEP_ORDER = (
    "extract",
    "batch",
    "token",
    "token_export",
    "summary",
    "upstream",
    "overview",
    "analyze",
)
STEP_LABELS = {
    "plan": "LLM 规划",
    "extract": "智能提取",
    "batch": "批量创建渠道",
    "token": "批量创建令牌",
    "token_export": "导出令牌",
    "summary": "数据汇总",
    "upstream": "上游采集",
    "overview": "一表总览",
    "analyze": "智能分析",
}


@dataclass
class StepResult:
    id: str
    label: str
    status: str  # ok | warn | err | skipped
    message: str = ""
    data: dict[str, Any] = field(default_factory=dict)


@dataclass
class PipelineResult:
    success: bool
    message: str
    steps: list[StepResult] = field(default_factory=list)
    channel_lines: str = ""
    token_lines: str = ""
    token_export_text: str = ""
    plan: dict[str, Any] = field(default_factory=dict)
    dry_run: bool = False
    outcome: str = "succeeded"  # succeeded | failed | cancelled | waiting_confirm

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "message": self.message,
            "channel_lines": self.channel_lines,
            "token_lines": self.token_lines,
            "token_export_text": self.token_export_text,
            "dry_run": self.dry_run,
            "plan": self.plan,
            "steps": [asdict(s) for s in self.steps],
            "outcome": self.outcome,
        }


def _step(id_: str, label: str, status: str, message: str = "", **data: Any) -> StepResult:
    return StepResult(id=id_, label=label, status=status, message=message, data=dict(data))


def _build_auth(connection: dict[str, Any]) -> dict[str, Any]:
    access_token = str(connection.get("access_token") or "").strip()
    if access_token:
        user_id = int(connection.get("user_id") or 0)
        if not user_id:
            raise ValueError("使用 Access Token 时需填写用户 ID")
        auth: dict[str, Any] = {"access_token": access_token, "user_id": user_id}
    else:
        auth = {
            "username": str(connection.get("username") or "").strip(),
            "password": connection.get("password") or "",
            "otp_code": str(connection.get("otp_code") or connection.get("verification_code") or "").strip(),
            "totp_secret": str(connection.get("totp_secret") or connection.get("otp_secret") or "").strip(),
        }
    if connection.get("verify_ssl") is not None:
        auth["verify_ssl"] = connection.get("verify_ssl")
    if connection.get("totp_secret") and "totp_secret" not in auth:
        auth["totp_secret"] = str(connection.get("totp_secret") or "").strip()
    return auth


def user_wanted_steps(options: dict[str, Any]) -> list[str]:
    wanted: list[str] = []
    if options.get("run_extract", True):
        wanted.append("extract")
    if options.get("run_batch", True):
        wanted.append("batch")
    if options.get("run_token", False):
        wanted.append("token")
    if options.get("run_token_export", False):
        wanted.append("token_export")
    if options.get("run_summary", True):
        wanted.append("summary")
    if options.get("run_upstream", False):
        wanted.append("upstream")
    if options.get("run_overview", False):
        wanted.append("overview")
    if options.get("run_analyze", False):
        wanted.append("analyze")
    return wanted


def intersect_plan_steps(llm_steps: list[str], options: dict[str, Any]) -> tuple[list[str], list[str]]:
    """最终 steps = 用户勾选优先，再与 LLM 计划求并（勾选必跑）。"""
    wanted = set(user_wanted_steps(options))
    valid = set(STEP_ORDER)
    llm_clean = [s for s in llm_steps if s in valid]
    merged = set(llm_clean) | wanted
    # 仅保留用户勾选的（LLM 多出来的仍裁掉）
    final = [s for s in STEP_ORDER if s in merged and s in wanted]
    warnings: list[str] = []
    trimmed = [s for s in llm_clean if s not in final]
    if trimmed:
        warnings.append(f"已按用户勾选裁掉步骤: {', '.join(trimmed)}")
    return final, warnings


def normalize_step_order(steps: list[str]) -> list[str]:
    valid = set(STEP_ORDER)
    chosen = {s for s in steps if s in valid}
    return [s for s in STEP_ORDER if s in chosen]


def _redact_plan_context(
    *,
    raw_text: str,
    goal: str,
    connection: dict[str, Any],
    sites: list[dict[str, Any]],
    options: dict[str, Any],
) -> dict[str, Any]:
    """规划上下文脱敏：密码 / Token / 二次验证码不送给 LLM。"""

    def scrub_conn(raw: dict[str, Any]) -> dict[str, Any]:
        conn = dict(raw or {})
        if conn.get("password"):
            conn["password"] = "***"
        if conn.get("access_token"):
            conn["access_token"] = "***"
        otp = str(conn.get("otp_code") or conn.get("verification_code") or "").strip()
        totp = str(conn.get("totp_secret") or conn.get("otp_secret") or "").strip()
        conn.pop("verification_code", None)
        conn.pop("totp_secret", None)
        conn.pop("otp_secret", None)
        conn["otp_code"] = "(已填写)" if otp or totp else ""
        conn["has_login_otp"] = bool(otp or totp)
        return conn

    sites_out: list[dict[str, Any]] = []
    for item in sites or []:
        row = dict(item or {})
        if row.get("password"):
            row["password"] = "***"
        if row.get("access_token"):
            row["access_token"] = "***"
        otp = str(row.get("otp_code") or row.get("verification_code") or "").strip()
        totp = str(row.get("totp_secret") or row.get("otp_secret") or "").strip()
        row.pop("verification_code", None)
        row.pop("totp_secret", None)
        row.pop("otp_secret", None)
        row["otp_code"] = "(已填写)" if otp or totp else ""
        sites_out.append(row)
    return {
        "raw_text": raw_text,
        "goal": goal,
        "connection": scrub_conn(connection),
        "sites": sites_out,
        "options": options,
    }


def build_plan(
    *,
    raw_text: str,
    goal: str,
    connection: dict[str, Any],
    sites: list[dict[str, Any]],
    options: dict[str, Any],
    llm_config: dict[str, Any],
    plan_pipeline_fn: Callable[..., Any],
) -> Any:
    context = _redact_plan_context(
        raw_text=raw_text,
        goal=goal,
        connection=connection,
        sites=sites,
        options=options,
    )
    plan = plan_pipeline_fn(
        context,
        api_base=str(llm_config.get("api_base") or ""),
        api_key=str(llm_config.get("api_key") or ""),
        model=str(llm_config.get("model") or "gpt-4o-mini"),
        provider=str(llm_config.get("provider") or ""),
        timeout=int(llm_config.get("timeout") or 60),
        use_llm=bool(options.get("use_llm_plan", True)),
    )
    final, extra = intersect_plan_steps(list(plan.steps or []), options)
    plan.steps = final
    plan.warnings = list(plan.warnings or []) + extra
    if not plan.steps:
        plan.proceed = False
        if not plan.advice:
            plan.advice = "没有可执行步骤（请检查勾选与输入）"
    return plan


def run_step(
    step_id: str,
    *,
    raw_text: str,
    connection: dict[str, Any],
    sites: list[dict[str, Any]],
    options: dict[str, Any],
    llm_config: dict[str, Any],
    channel_lines: str,
    extract_channels: Callable[..., Any],
    batch: dict[str, Any],
    project_dir: Path,
) -> tuple[StepResult, str]:
    """执行单步，返回 (StepResult, 更新后的 channel_lines)。"""
    dry_run = bool(options.get("dry_run"))
    label = STEP_LABELS.get(step_id, step_id)

    if step_id == "extract":
        text = str(raw_text or "").strip()
        if not text:
            return _step("extract", label, "err", "缺少原始文本"), channel_lines
        try:
            result = extract_channels(text, use_llm=True, llm_config=llm_config)
            lines = result.channel_lines or result.channel_line or ""
            if result.success and lines:
                return (
                    _step(
                        "extract",
                        label,
                        "ok",
                        result.message or f"提取 {result.count} 条",
                        count=result.count,
                        mode=result.mode,
                        llm=asdict(result.llm) if hasattr(result, "llm") else {},
                    ),
                    lines,
                )
            return _step("extract", label, "err", result.message or "提取失败"), channel_lines
        except Exception as exc:  # noqa: BLE001
            return _step("extract", label, "err", str(exc)), channel_lines

    if step_id == "batch":
        if dry_run:
            return _step("batch", label, "skipped", "试运行：未写入网关"), channel_lines
        if not str(channel_lines or "").strip():
            return _step("batch", label, "err", "无渠道行可创建"), channel_lines
        base_url = batch["normalize_na_base_url"](str(connection.get("base_url") or "").strip())
        if not base_url:
            return _step("batch", label, "err", "缺少 New API 地址"), channel_lines
        try:
            auth = _build_auth(connection)
            default_key = str(connection.get("default_key") or "").strip()
            batch_result = batch["run_batch_create"](
                base_url=base_url,
                batch_text=channel_lines,
                default_key=default_key,
                auth=auth,
            )
            ok = batch_result.failed_count == 0
            return (
                _step(
                    "batch",
                    label,
                    "ok" if ok else "warn",
                    f"成功 {batch_result.success_count}，跳过 {batch_result.skipped_count}，失败 {batch_result.failed_count}",
                    total=batch_result.total,
                    success_count=batch_result.success_count,
                    skipped_count=batch_result.skipped_count,
                    failed_count=batch_result.failed_count,
                    items=batch_result.items[:20],
                ),
                channel_lines,
            )
        except Exception as exc:  # noqa: BLE001
            return _step("batch", label, "err", str(exc)), channel_lines

    if step_id == "token":
        usernames = str(options.get("token_usernames") or "").strip()
        if dry_run:
            try:
                token_text = batch["build_token_batch_text"](channel_lines, usernames)
                count = len([ln for ln in token_text.splitlines() if ln.strip()])
                return (
                    _step(
                        "token",
                        label,
                        "skipped",
                        f"试运行：将生成 {count} 条令牌（未写入）",
                        token_lines=token_text,
                        preview_count=count,
                    ),
                    channel_lines,
                )
            except Exception as exc:  # noqa: BLE001
                return _step("token", label, "err", str(exc)), channel_lines
        if not usernames:
            return _step("token", label, "err", "创建令牌需填写用户名"), channel_lines
        if not str(channel_lines or "").strip():
            return _step("token", label, "err", "无渠道行，无法按「渠道名-用户名」生成令牌"), channel_lines
        base_url = batch["normalize_na_base_url"](str(connection.get("base_url") or "").strip())
        if not base_url:
            return _step("token", label, "err", "缺少 New API 地址"), channel_lines
        try:
            token_text = batch["build_token_batch_text"](channel_lines, usernames)
            auth = _build_auth(connection)
            token_result = batch["run_token_batch_create"](
                base_url=base_url,
                batch_text=token_text,
                auth=auth,
            )
            ok = token_result.failed_count == 0
            return (
                _step(
                    "token",
                    label,
                    "ok" if ok else "warn",
                    f"令牌成功 {token_result.success_count}，跳过 {token_result.skipped_count}，失败 {token_result.failed_count}",
                    token_lines=token_text,
                    total=token_result.total,
                    success_count=token_result.success_count,
                    skipped_count=token_result.skipped_count,
                    failed_count=token_result.failed_count,
                    items=token_result.items[:20],
                ),
                channel_lines,
            )
        except Exception as exc:  # noqa: BLE001
            return _step("token", label, "err", str(exc)), channel_lines

    if step_id == "token_export":
        if dry_run:
            return _step("token_export", label, "skipped", "试运行：未导出令牌"), channel_lines
        base_url = batch["normalize_na_base_url"](str(connection.get("base_url") or "").strip())
        if not base_url:
            return _step("token_export", label, "err", "缺少 New API 地址"), channel_lines
        try:
            auth = _build_auth(connection)
            export_result = batch["export_all_tokens_text"](base_url=base_url, auth=auth, pasted_keys="")
            return (
                _step(
                    "token_export",
                    label,
                    "ok",
                    f"已导出 {export_result.total} 条令牌，明文秘钥 {export_result.key_resolved} 条",
                    export_text=export_result.text,
                    total=export_result.total,
                    key_resolved=export_result.key_resolved,
                    key_missing=export_result.key_missing,
                ),
                channel_lines,
            )
        except Exception as exc:  # noqa: BLE001
            return _step("token_export", label, "err", str(exc)), channel_lines

    if step_id == "summary":
        if dry_run:
            return _step("summary", label, "skipped", "试运行：未采集"), channel_lines
        parsed_sites = batch["parse_summary_sites"](sites)
        if not parsed_sites:
            return _step("summary", label, "skipped", "未配置有效站点"), channel_lines
        try:
            excel_path = batch["default_excel_path"](project_dir)
            stats, saved_path = batch["run_data_summary_collect"](
                sites=parsed_sites,
                excel_path=excel_path,
            )
            ok = stats.sites_ok > 0
            rel = str(saved_path.relative_to(project_dir)).replace("\\", "/")
            return (
                _step(
                    "summary",
                    label,
                    "ok" if ok else "warn",
                    f"采集完成：成功 {stats.sites_ok} 站"
                    + (f"，失败 {stats.sites_failed} 站" if stats.sites_failed else ""),
                    file=rel,
                    sites_ok=stats.sites_ok,
                    sites_failed=stats.sites_failed,
                    channels_added=stats.channels_added,
                    tokens_added=stats.tokens_added,
                    duplicate_channels=stats.duplicate_channels,
                    duplicate_tokens=stats.duplicate_tokens,
                    errors=stats.errors,
                ),
                channel_lines,
            )
        except Exception as exc:  # noqa: BLE001
            return _step("summary", label, "err", str(exc)), channel_lines

    if step_id in ("upstream", "overview", "analyze"):
        return _run_downstream_step(step_id, label, options, batch, project_dir), channel_lines

    return _step(step_id, label, "err", f"未知步骤: {step_id}"), channel_lines


def _run_downstream_step(
    step_id: str,
    label: str,
    options: dict[str, Any],
    batch: dict[str, Any],
    project_dir: Path,
) -> StepResult:
    """⑤ 上游 / ⑥ 总览 / 智能分析。缺文件或凭证时跳过，不把整条流水线打成失败。"""
    dry_run = bool(options.get("dry_run"))
    dry_msgs = {
        "upstream": "试运行：未采集上游",
        "overview": "试运行：未生成一表总览",
        "analyze": "试运行：未执行智能分析",
    }
    if dry_run:
        return _step(step_id, label, "skipped", dry_msgs[step_id])

    fn_name = {
        "upstream": "agent_collect_upstream",
        "overview": "agent_build_overview",
        "analyze": "agent_run_analysis",
    }[step_id]
    fn = batch.get(fn_name)
    if not callable(fn):
        return _step(step_id, label, "err", f"智能体未接线{label}")
    try:
        result = fn(project_dir) or {}
    except Exception as exc:  # noqa: BLE001
        return _step(step_id, label, "err", str(exc))
    extra = {
        key: value
        for key, value in result.items()
        if key not in ("ok", "skipped", "message")
    }
    if result.get("skipped"):
        return _step(step_id, label, "skipped", result.get("message") or "已跳过", **extra)
    if result.get("ok"):
        return _step(step_id, label, "ok", result.get("message") or f"{label}完成", **extra)
    if result.get("file"):
        return _step(step_id, label, "warn", result.get("message") or f"{label}部分完成", **extra)
    return _step(step_id, label, "err", result.get("message") or f"{label}失败", **extra)


def remaining_steps(plan_steps: list[str], start_from: str | None) -> list[str]:
    ordered = normalize_step_order(plan_steps)
    if not start_from or start_from in ("", "plan"):
        return ordered
    if start_from not in ordered:
        # 从该步起：若 start_from 合法但被裁掉，返回空后续中包含其后的
        if start_from in STEP_ORDER:
            idx = STEP_ORDER.index(start_from)
            return [s for s in ordered if STEP_ORDER.index(s) >= idx]
        return ordered
    idx = ordered.index(start_from)
    return ordered[idx:]


def execute_pipeline(
    *,
    raw_text: str,
    goal: str,
    connection: dict[str, Any],
    sites: list[dict[str, Any]],
    options: dict[str, Any],
    llm_config: dict[str, Any],
    extract_channels: Callable[..., Any],
    plan_pipeline_fn: Callable[..., Any],
    batch: dict[str, Any],
    project_dir: Path,
    channel_lines: str = "",
    plan_dict: dict[str, Any] | None = None,
    existing_steps: list[StepResult] | None = None,
    start_from: str | None = None,
    confirmed: bool = False,
    should_cancel: Callable[[], bool] | None = None,
    on_event: Callable[[str, dict[str, Any]], None] | None = None,
) -> PipelineResult:
    """按检查点执行流水线。

    outcome: succeeded | failed | cancelled | waiting_confirm
    """
    dry_run = bool(options.get("dry_run"))
    require_confirm = bool(options.get("require_confirm", True))
    steps: list[StepResult] = list(existing_steps or [])
    lines = str(channel_lines or "")
    cancel_fn = should_cancel or (lambda: False)

    def emit(etype: str, data: dict[str, Any]) -> None:
        if on_event:
            on_event(etype, data)

    # 规划
    need_plan = plan_dict is None or not plan_dict.get("steps") or start_from in (None, "", "plan")
    if need_plan and (not plan_dict or start_from in (None, "", "plan")):
        if cancel_fn():
            return PipelineResult(
                success=False,
                message="已取消",
                steps=steps,
                channel_lines=lines,
                plan=plan_dict or {},
                dry_run=dry_run,
                outcome="cancelled",
            )
        emit("status", {"status": "planning"})
        plan = build_plan(
            raw_text=raw_text,
            goal=goal,
            connection=connection,
            sites=sites,
            options=options,
            llm_config=llm_config,
            plan_pipeline_fn=plan_pipeline_fn,
        )
        plan_dict = asdict(plan)
        if not plan.proceed:
            sr = _step(
                "plan",
                STEP_LABELS["plan"],
                "err",
                plan.advice or "未通过规划校验",
                warnings=plan.warnings,
                steps=plan.steps,
                confidence=plan.confidence,
                llm_invoked=plan.invoked,
            )
            steps = [s for s in steps if s.id != "plan"] + [sr]
            emit("step", asdict(sr))
            return PipelineResult(
                success=False,
                message=plan.advice or "智能体判断当前无法安全执行",
                steps=steps,
                channel_lines=lines,
                plan=plan_dict,
                dry_run=dry_run,
                outcome="failed",
            )
        sr = _step(
            "plan",
            STEP_LABELS["plan"],
            "ok",
            plan.advice or f"将执行: {' → '.join(plan.steps)}",
            steps=plan.steps,
            warnings=plan.warnings,
            confidence=plan.confidence,
            llm_invoked=plan.invoked,
        )
        steps = [s for s in steps if s.id != "plan"] + [sr]
        emit("step", asdict(sr))
        emit("status", {"status": "running", "plan": plan_dict})
    else:
        plan_dict = plan_dict or {}

    plan_steps = list(plan_dict.get("steps") or [])
    todo = remaining_steps(plan_steps, start_from if start_from not in (None, "", "plan") else None)

    overall_ok = True
    token_lines = ""
    token_export_text = ""
    for step_id in todo:
        if cancel_fn():
            emit("status", {"status": "cancelled", "checkpoint": step_id})
            return PipelineResult(
                success=False,
                message="已取消",
                steps=steps,
                channel_lines=lines,
                token_lines=token_lines,
                token_export_text=token_export_text,
                plan=plan_dict,
                dry_run=dry_run,
                outcome="cancelled",
            )

        # 人工门禁：即将执行 batch，且需要确认
        if (
            step_id == "batch"
            and require_confirm
            and not confirmed
            and not dry_run
            and "batch" in plan_steps
        ):
            emit(
                "status",
                {
                    "status": "waiting_confirm",
                    "checkpoint": "batch",
                    "channel_lines": lines,
                },
            )
            return PipelineResult(
                success=True,
                message="提取完成，请确认渠道行后继续批量创建",
                steps=steps,
                channel_lines=lines,
                token_lines=token_lines,
                token_export_text=token_export_text,
                plan=plan_dict,
                dry_run=dry_run,
                outcome="waiting_confirm",
            )

        emit("status", {"status": "running", "running_step": step_id})
        sr, lines = run_step(
            step_id,
            raw_text=raw_text,
            connection=connection,
            sites=sites,
            options=options,
            llm_config=llm_config,
            channel_lines=lines,
            extract_channels=extract_channels,
            batch=batch,
            project_dir=project_dir,
        )
        if sr.data.get("token_lines"):
            token_lines = str(sr.data.get("token_lines") or "")
        if sr.data.get("export_text"):
            token_export_text = str(sr.data.get("export_text") or "")
        # 替换同 id 旧结果（retry）
        steps = [s for s in steps if s.id != step_id] + [sr]
        emit("step", asdict(sr))

        if sr.status == "err":
            overall_ok = False
            # extract 失败短路
            if step_id == "extract":
                emit("status", {"status": "failed", "checkpoint": step_id})
                return PipelineResult(
                    success=False,
                    message=sr.message or "提取失败",
                    steps=steps,
                    channel_lines=lines,
                    token_lines=token_lines,
                    token_export_text=token_export_text,
                    plan=plan_dict,
                    dry_run=dry_run,
                    outcome="failed",
                )
            # 后续步骤失败：停止
            emit("status", {"status": "failed", "checkpoint": step_id})
            return PipelineResult(
                success=False,
                message=sr.message or f"{STEP_LABELS.get(step_id, step_id)}失败",
                steps=steps,
                channel_lines=lines,
                token_lines=token_lines,
                token_export_text=token_export_text,
                plan=plan_dict,
                dry_run=dry_run,
                outcome="failed",
            )
        if sr.status == "warn":
            overall_ok = False

    msg_parts = [s.message for s in steps if s.status in ("ok", "warn") and s.id != "plan"]
    advice = str((plan_dict or {}).get("advice") or "")
    message = advice or ("；".join(msg_parts) if msg_parts else "流水线执行完成")
    outcome = "succeeded" if overall_ok else "failed"
    return PipelineResult(
        success=overall_ok,
        message=message,
        steps=steps,
        channel_lines=lines,
        token_lines=token_lines,
        token_export_text=token_export_text,
        plan=plan_dict or {},
        dry_run=dry_run,
        outcome=outcome,
    )


def run_pipeline(
    *,
    raw_text: str,
    goal: str,
    connection: dict[str, Any],
    sites: list[dict[str, Any]],
    options: dict[str, Any],
    llm_config: dict[str, Any],
    extract_channels: Callable[..., Any],
    plan_pipeline_fn: Callable[..., Any],
    batch: dict[str, Any],
    project_dir: Path,
    channel_lines: str = "",
) -> PipelineResult:
    """同步兼容入口（默认不停门禁，由调用方 options.require_confirm 控制）。"""
    return execute_pipeline(
        raw_text=raw_text,
        goal=goal,
        connection=connection,
        sites=sites,
        options=options,
        llm_config=llm_config,
        extract_channels=extract_channels,
        plan_pipeline_fn=plan_pipeline_fn,
        batch=batch,
        project_dir=project_dir,
        channel_lines=channel_lines,
        confirmed=not bool(options.get("require_confirm", False)),
        start_from=None,
    )
