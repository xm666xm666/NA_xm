"""全流程智能体：LLM 规划 ①提取 → ②批量 → ③汇总 → ⑤上游 → ⑥总览 → 分析。"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

from .llm_client import chat_completion, is_llm_configured, resolve_provider

SYSTEM_PROMPT = """你是 NA 自动配置工具的全流程自动化智能体，负责编排流水线：

1. extract — 从杂乱文本智能提取渠道行（规则 + LLM）
2. batch — 将渠道行批量创建到 New API 网关
3. token — 按「渠道名-用户名」为每条渠道生成令牌（需 token_usernames）
4. token_export — 导出站点全部令牌明文信息
5. summary — 从多个站点采集渠道/令牌写入 Excel
6. upstream — 采集火山云 + Azure 上游，写入 excel/上游信息_汇总_时间戳.xlsx
7. overview — 从已有③⑤文件生成一表总览（不含渠道明文密钥）
8. analyze — 读取最新总览写入智能分析表；无总览时执行器会跳过，不要因此 proceed=false

- connection.has_login_otp / otp_code="(已填写)"：网关账号已提供登录两步验证码。未填写且将执行 batch/token/token_export 时，可提醒用户在确认门禁时补填当前 6 位码。
- sites[].otp_code="(已填写)"：该汇总站点已提供登录 2FA；各环境验证器通常不同，勿假设同一验证码。
- 切勿把密码、密钥、验证码原文写入 advice 或 warnings。

用户会提供 JSON 上下文。请分析是否具备执行条件，并决定启用哪些步骤。

规则：
- raw_text 非空则 extract 通常应启用
- connection.base_url 非空且 batch 未禁用时，extract 成功后可 batch
- options.run_token 且 token_usernames 非空时可 token（依赖渠道行）
- options.run_token_export 且有 base_url 时可 token_export
- sites 数组非空且 summary 未禁用时，可 summary
- options.run_upstream 时可 upstream（读 env 上游凭证，不需要 raw_text）
- options.run_overview 时可 overview（从 excel/ 已有文件提取，默认不含密钥）
- options.run_analyze 时可 analyze（读最新总览；无总览只在 warnings 说明即可）
- dry_run=true 时不实际写网关/Excel（token_export / upstream / overview / analyze 也跳过）
- 缺少关键字段时在 warnings 说明，proceed=false 若无法安全执行

仅返回 JSON，不要 markdown：
{
  "proceed": true,
  "steps": ["extract", "batch", "token", "token_export", "summary", "upstream", "overview", "analyze"],
  "warnings": [],
  "advice": "给用户的一句话执行说明",
  "confidence": 0.0
}"""


@dataclass
class PipelinePlan:
    proceed: bool = True
    steps: list[str] = field(default_factory=lambda: ["extract", "batch", "summary"])
    warnings: list[str] = field(default_factory=list)
    advice: str = ""
    confidence: float = 0.0
    invoked: bool = False
    error: str = ""


def _parse_json(text: str) -> dict[str, Any]:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if not match:
            raise
        return json.loads(match.group(0))


def _default_plan(context: dict[str, Any]) -> PipelinePlan:
    steps: list[str] = []
    warnings: list[str] = []
    raw_text = str(context.get("raw_text") or "").strip()
    connection = context.get("connection") or {}
    sites = context.get("sites") or []
    options = context.get("options") or {}
    dry_run = bool(options.get("dry_run"))

    if options.get("run_extract", True) and raw_text:
        steps.append("extract")
    elif options.get("run_extract", True):
        warnings.append("未提供原始文本，跳过提取")

    if options.get("run_batch", True) and not dry_run:
        if connection.get("base_url"):
            steps.append("batch")
        else:
            warnings.append("未配置 New API 地址，跳过批量创建")
    elif options.get("run_batch", True) and dry_run:
        warnings.append("试运行模式：不执行批量创建")

    token_users = str(options.get("token_usernames") or "").strip()
    if options.get("run_token", False) and not dry_run:
        if connection.get("base_url") and token_users and (raw_text or True):
            steps.append("token")
        elif not token_users:
            warnings.append("未填写令牌用户名，跳过令牌创建")
        else:
            warnings.append("令牌创建条件不足，已跳过")
    elif options.get("run_token", False) and dry_run:
        if token_users:
            steps.append("token")
        else:
            warnings.append("试运行令牌：未填用户名")

    if options.get("run_token_export", False) and not dry_run:
        if connection.get("base_url"):
            steps.append("token_export")
        else:
            warnings.append("未配置 New API 地址，跳过令牌导出")
    elif options.get("run_token_export", False) and dry_run:
        warnings.append("试运行模式：不执行令牌导出")

    if options.get("run_summary", True) and not dry_run:
        if sites:
            steps.append("summary")
        else:
            warnings.append("未配置汇总站点，跳过数据汇总")
    elif options.get("run_summary", True) and dry_run:
        warnings.append("试运行模式：不执行数据汇总")

    if options.get("run_upstream", False) and not dry_run:
        steps.append("upstream")
    elif options.get("run_upstream", False) and dry_run:
        warnings.append("试运行模式：不执行上游采集")

    if options.get("run_overview", False) and not dry_run:
        steps.append("overview")
    elif options.get("run_overview", False) and dry_run:
        warnings.append("试运行模式：不生成一表总览")

    if options.get("run_analyze", False) and not dry_run:
        steps.append("analyze")
    elif options.get("run_analyze", False) and dry_run:
        warnings.append("试运行模式：不执行智能分析")

    has_token_auth = bool(str(connection.get("access_token") or "").strip())
    has_otp = bool(str(connection.get("otp_code") or "").strip()) or bool(
        connection.get("has_login_otp")
    )
    write_steps = {"batch", "token", "token_export"}
    if not dry_run and not has_token_auth and connection.get("base_url") and not has_otp:
        if write_steps.intersection(steps):
            warnings.append(
                "账号若开启登录两步验证，请填写二次验证码，或先测试连接以复用会话；"
                "提取耗时后请在门禁确认时再填认证器当前码"
            )

    standalone = any(s in steps for s in ("token_export", "upstream", "overview", "analyze"))
    proceed = bool(steps) and (bool(raw_text) or bool(sites) or standalone)
    return PipelinePlan(
        proceed=proceed,
        steps=steps,
        warnings=warnings,
        advice="将按默认规则执行已启用的步骤" if steps else "缺少可执行步骤",
        confidence=0.5,
        invoked=False,
    )


def plan_pipeline(
    context: dict[str, Any],
    *,
    api_base: str,
    api_key: str,
    model: str,
    provider: str = "",
    timeout: int = 60,
    use_llm: bool = True,
) -> PipelinePlan:
    """LLM 规划流水线；失败时回退默认规则。"""
    fallback = _default_plan(context)
    if not use_llm:
        return fallback

    llm_config = {"api_base": api_base, "api_key": api_key, "provider": provider}
    if not is_llm_configured(llm_config):
        fallback.warnings.append("LLM 未配置，使用规则默认规划")
        return fallback

    provider = resolve_provider(api_base, provider)
    goal = str(context.get("goal") or "").strip()
    user_content = json.dumps(context, ensure_ascii=False, indent=2)
    if goal:
        user_content = f"用户目标：{goal}\n\n上下文：\n{user_content}"

    try:
        content = chat_completion(
            api_base=api_base,
            api_key=api_key,
            model=model,
            provider=provider,
            timeout=timeout,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
        )
        data = _parse_json(content)
        steps_raw = data.get("steps") or fallback.steps
        valid = {
            "extract",
            "batch",
            "token",
            "token_export",
            "summary",
            "upstream",
            "overview",
            "analyze",
        }
        steps = [s for s in steps_raw if s in valid]
        if not steps:
            steps = fallback.steps
        return PipelinePlan(
            proceed=bool(data.get("proceed", True)),
            steps=steps,
            warnings=[str(w) for w in (data.get("warnings") or []) if w],
            advice=str(data.get("advice") or ""),
            confidence=float(data.get("confidence") or 0.7),
            invoked=True,
        )
    except Exception as exc:  # noqa: BLE001
        fallback.warnings.append(f"LLM 规划失败，已回退默认规则: {exc}")
        fallback.error = str(exc)
        return fallback
