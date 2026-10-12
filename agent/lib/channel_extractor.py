"""渠道信息提取编排器。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .block_parser import split_into_blocks
from .formatter import format_channel_line, format_fields_summary
from .group_deriver import derive_group_from_name
from .llm_agent import enrich_with_llm
from .llm_client import is_llm_configured, provider_allows_empty_key, resolve_provider
from .rule_extractor import ExtractedFields, extract_blocks_by_rules
from .type_registry import get_type_by_label


@dataclass
class ChannelItem:
    index: int
    success: bool
    channel_line: str = ""
    fields: ExtractedFields = field(default_factory=ExtractedFields)
    summary: dict[str, str] = field(default_factory=dict)
    message: str = ""


@dataclass
class LlmUsageSummary:
    enabled: bool = False
    configured: bool = False
    invoked: bool = False
    success: bool = False
    provider: str = ""
    model: str = ""
    items_invoked: int = 0
    items_succeeded: int = 0
    items_failed: int = 0
    filled_fields: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


@dataclass
class ExtractResult:
    success: bool
    channel_line: str = ""
    channel_lines: str = ""
    count: int = 0
    items: list[ChannelItem] = field(default_factory=list)
    fields: ExtractedFields = field(default_factory=ExtractedFields)
    summary: dict[str, str] = field(default_factory=dict)
    message: str = ""
    mode: str = "rules"
    llm: LlmUsageSummary = field(default_factory=LlmUsageSummary)


def validate_llm_config(llm_config: dict[str, Any] | None) -> str | None:
    cfg = llm_config or {}
    api_base = str(cfg.get("api_base") or "").strip()
    if not api_base:
        return "启用 LLM 增强需要配置 API 地址（llm_api_base）"
    provider = resolve_provider(api_base, str(cfg.get("provider") or ""))
    api_key = str(cfg.get("api_key") or "").strip()
    if not api_key and not provider_allows_empty_key(provider):
        return f"启用 LLM 增强需要配置 API Key（厂商 {provider}）"
    return None


def _finalize_fields(fields: ExtractedFields) -> ExtractedFields:
    type_info = get_type_by_label(fields.type_label)
    if type_info and type_info.base_url and not fields.base_url:
        fields.base_url = type_info.base_url
        fields.sources.setdefault("base_url", "type_default")

    if fields.name:
        derived = derive_group_from_name(fields.name)
        if derived:
            fields.group = derived
            fields.sources["group"] = "derived"

    if fields.name:
        from .group_deriver import derive_model_from_name

        core = derive_model_from_name(fields.name)
        if not fields.model:
            fields.model = core or fields.name
            fields.sources.setdefault(
                "model",
                "same_as_name" if fields.model == fields.name else "name_ascii_core",
            )
        elif core and fields.model == fields.name and core != fields.name:
            # 名称含中文备注时，模型列用 ASCII 核心
            fields.model = core
            fields.sources["model"] = "name_ascii_core"

    return fields


def _process_block(
    index: int,
    block_text: str,
    fields: ExtractedFields,
    *,
    use_llm: bool,
    llm_config: dict[str, Any],
    require_key: bool = True,
) -> ChannelItem:
    llm_config = llm_config or {}
    if use_llm and is_llm_configured(llm_config):
        enrich_result = enrich_with_llm(
            block_text,
            fields,
            api_base=str(llm_config.get("api_base", "")),
            api_key=str(llm_config.get("api_key", "")),
            model=str(llm_config.get("model", "gpt-4o-mini")),
            timeout=int(llm_config.get("timeout", 60)),
            provider=str(llm_config.get("provider") or ""),
            required=True,
            override=True,
        )
        fields = enrich_result.fields
        if not enrich_result.success:
            return ChannelItem(
                index=index,
                success=False,
                fields=fields,
                summary=format_fields_summary(fields),
                message=f"#{index} LLM 调用失败: {enrich_result.error or '未知错误'}",
            )

    fields = _finalize_fields(fields)
    missing = fields.missing_fields(require_key=require_key)
    if missing:
        return ChannelItem(
            index=index,
            success=False,
            fields=fields,
            summary=format_fields_summary(fields),
            message=f"#{index} 未能完整提取，缺少: {', '.join(missing)}",
        )

    try:
        line = format_channel_line(fields, require_key=require_key)
    except ValueError as exc:
        return ChannelItem(
            index=index,
            success=False,
            fields=fields,
            summary=format_fields_summary(fields),
            message=f"#{index} {exc}",
        )

    return ChannelItem(
        index=index,
        success=True,
        channel_line=line,
        fields=fields,
        summary=format_fields_summary(fields),
        message=f"#{index} 提取成功",
    )


def _build_llm_summary(items: list[ChannelItem], *, enabled: bool, configured: bool) -> LlmUsageSummary:
    summary = LlmUsageSummary(enabled=enabled, configured=configured)
    filled: set[str] = set()
    errors: list[str] = []

    for item in items:
        fields = item.fields
        if fields.llm_provider and not summary.provider:
            summary.provider = fields.llm_provider
        if fields.llm_model and not summary.model:
            summary.model = fields.llm_model
        if fields.llm_invoked:
            summary.invoked = True
            summary.items_invoked += 1
            if fields.llm_success:
                summary.items_succeeded += 1
                filled.update(fields.llm_filled)
            else:
                summary.items_failed += 1
        if fields.llm_error:
            errors.append(fields.llm_error)

    summary.filled_fields = sorted(filled)
    summary.errors = errors
    summary.success = summary.items_invoked > 0 and summary.items_failed == 0
    return summary


def _resolve_mode(*, use_llm: bool, llm_summary: LlmUsageSummary) -> str:
    if use_llm and llm_summary.invoked and llm_summary.items_succeeded > 0:
        return "llm"
    if llm_summary.invoked and llm_summary.items_succeeded > 0:
        return "rules+llm"
    if use_llm and llm_summary.items_failed > 0:
        return "llm_failed"
    return "rules"


def extract_channels(
    raw_text: str,
    *,
    use_llm: bool = False,
    llm_config: dict[str, Any] | None = None,
    require_key: bool = True,
) -> ExtractResult:
    text = (raw_text or "").strip()
    if not text:
        return ExtractResult(success=False, message="请输入项目信息")

    blocks = split_into_blocks(text)
    if not blocks:
        return ExtractResult(success=False, message="未检测到有效输入")

    llm_config = llm_config or {}
    configured = is_llm_configured(llm_config)
    if use_llm:
        llm_error = validate_llm_config(llm_config)
        if llm_error:
            return ExtractResult(
                success=False,
                message=llm_error,
                mode="llm_failed",
                llm=LlmUsageSummary(enabled=True, configured=False, errors=[llm_error]),
            )

    items: list[ChannelItem] = []

    for index, block_lines in enumerate(blocks, start=1):
        block_text = "\n".join(block_lines)
        fields_list = extract_blocks_by_rules(block_text)
        fields = fields_list[0] if fields_list else ExtractedFields()
        item = _process_block(
            index,
            block_text,
            fields,
            use_llm=use_llm,
            llm_config=llm_config,
            require_key=require_key,
        )
        items.append(item)

    llm_summary = _build_llm_summary(items, enabled=use_llm, configured=configured)
    success_count = sum(1 for item in items if item.success)
    all_success = success_count == len(items)
    channel_lines = "\n".join(item.channel_line for item in items if item.channel_line)

    first_ok = next((item for item in items if item.success), items[0] if items else None)
    first_fields = first_ok.fields if first_ok else ExtractedFields()
    mode = _resolve_mode(use_llm=use_llm, llm_summary=llm_summary)

    if use_llm and llm_summary.items_failed > 0 and not all_success:
        message = f"LLM 增强失败：{llm_summary.items_failed}/{len(items)} 条未成功调用 AI"
    elif len(items) == 1:
        message = first_ok.message if first_ok else "提取失败"
        if first_ok and first_ok.success:
            if use_llm and llm_summary.invoked:
                message = (
                    f"提取成功（AI 辅助：{llm_summary.provider or 'llm'}/"
                    f"{llm_summary.model or 'model'}，填充 {len(llm_summary.filled_fields)} 项）"
                )
            else:
                message = "提取成功，已生成批量配置程序渠道格式"
    elif all_success:
        if use_llm and llm_summary.invoked:
            message = (
                f"提取成功，共 {len(items)} 条渠道（AI 辅助：{llm_summary.provider or 'llm'}/"
                f"{llm_summary.model or 'model'}）"
            )
        else:
            message = f"提取成功，共 {len(items)} 条渠道"
    else:
        message = f"部分成功：{success_count}/{len(items)} 条"

    keyless_ok = [
        item
        for item in items
        if item.success and not str(item.fields.api_key or "").strip()
    ]
    if (not require_key) and all_success and keyless_ok:
        if len(items) == 1:
            message = "更新提取成功（不要求密钥）。请点「填入更新原配置」，不要用于批量创建。"
        else:
            message = (
                f"更新提取成功（无密钥，共 {len(items)} 条）。"
                "请点「填入更新原配置」，不要用于批量创建。"
            )

    return ExtractResult(
        success=all_success,
        channel_line=first_ok.channel_line if first_ok else "",
        channel_lines=channel_lines,
        count=len(items),
        items=items,
        fields=first_fields,
        summary=first_ok.summary if first_ok else {},
        message=message,
        mode=mode,
        llm=llm_summary,
    )


def extract_channel(
    raw_text: str,
    *,
    use_llm: bool = False,
    llm_config: dict[str, Any] | None = None,
    require_key: bool = True,
) -> ExtractResult:
    """兼容旧接口，内部走批量提取。"""
    return extract_channels(
        raw_text, use_llm=use_llm, llm_config=llm_config, require_key=require_key
    )
