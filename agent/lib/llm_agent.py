"""LLM 智能体：补充或主导渠道字段提取。"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

from .group_deriver import derive_group_from_name
from .llm_client import (
    chat_completion,
    is_llm_configured,
    provider_allows_empty_key,
    resolve_provider,
)
from .rule_extractor import ExtractedFields
from .type_registry import all_type_labels, resolve_type_hint

SYSTEM_PROMPT = """你是 New API 渠道配置助手。用户会粘贴杂乱的项目信息，你需要提取并结构化以下字段：

- name: 渠道/项目名称（完整标识，如 demo-alpha-test-glm-x）
- group: 分组名，通常从 name 去掉模型后缀得到（如 demo-alpha-test）
- type_label: 渠道类型，必须从已知列表中选择完整名称
- model: 对外模型名，通常与 name 相同
- upstream_model: 上游真实模型 ID（如火山方舟的 ep-xxxxxxxx、路径型 /models/GLM-5.2-FP8，或 Azure 的 gpt-4o / text-embedding-ada-002）
- api_key: API 密钥（UUID 或 sk- 开头）
- base_url: 上游地址；若类型有默认值则填默认
- api_version: 仅 Azure OpenAI 需要

忽略噪声信息：RPM/TPM 限额、版本标注 GLM-5.2｜260617、测试别名等。

若上游模型以 ep- 开头，则类型默认为「字节火山方舟、豆包通用」，Base URL 默认为 https://ark.cn-beijing.volces.com，用户无需再提供火山/豆包描述或 Base URL。

已知渠道类型：{type_labels}

类型默认 Base URL：
- 字节火山方舟、豆包通用 -> https://ark.cn-beijing.volces.com

仅返回 JSON，不要 markdown：
{{"name":"","group":"","type_label":"","model":"","upstream_model":"","api_key":"","base_url":"","api_version":"","reasoning":""}}"""


@dataclass
class LlmEnrichResult:
    fields: ExtractedFields
    invoked: bool = False
    success: bool = False
    provider: str = ""
    model: str = ""
    filled_fields: list[str] = field(default_factory=list)
    error: str = ""


def _parse_json_response(text: str) -> dict[str, Any]:
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


def _merge_llm_into_fields(
    fields: ExtractedFields,
    data: dict[str, Any],
    *,
    override: bool = False,
) -> list[str]:
    mapping = {
        "name": "name",
        "group": "group",
        "type_label": "type_label",
        "model": "model",
        "upstream_model": "upstream_model",
        "api_key": "api_key",
        "base_url": "base_url",
        "api_version": "api_version",
    }
    filled: list[str] = []
    for src, dst in mapping.items():
        value = str(data.get(src) or "").strip()
        if not value:
            continue
        current = getattr(fields, dst, "").strip()
        if override or not current:
            if current and current != value:
                fields.sources[dst] = "llm:override"
            else:
                fields.sources[dst] = "llm"
            setattr(fields, dst, value)
            filled.append(dst)

    type_hint = resolve_type_hint(fields.type_label)
    if type_hint:
        fields.type_label = type_hint.label
        if type_hint.base_url and (override or not fields.base_url):
            if fields.base_url and fields.base_url != type_hint.base_url:
                fields.sources["base_url"] = "llm:type_default:override"
            else:
                fields.sources["base_url"] = "llm:type_default"
            fields.base_url = type_hint.base_url
            if "base_url" not in filled:
                filled.append("base_url")

    if fields.name and (override or not fields.group):
        derived = derive_group_from_name(fields.name)
        if derived and (override or not fields.group):
            fields.group = derived
            fields.sources["group"] = "llm:derived"
            if "group" not in filled:
                filled.append("group")

    if fields.name and (override or not fields.model):
        if override or not fields.model:
            fields.model = fields.name
            fields.sources["model"] = "llm:same_as_name"
            if "model" not in filled:
                filled.append("model")

    reasoning = str(data.get("reasoning") or "").strip()
    if reasoning:
        fields.sources["reasoning"] = reasoning

    filled_count = sum(
        1
        for key in ("name", "type_label", "upstream_model", "api_key")
        if getattr(fields, key, "").strip()
    )
    fields.confidence = max(fields.confidence, filled_count / 4.0)
    return filled


def _apply_llm_meta(
    fields: ExtractedFields,
    *,
    invoked: bool,
    success: bool,
    provider: str,
    model: str,
    filled_fields: list[str],
    error: str = "",
) -> ExtractedFields:
    fields.llm_invoked = invoked
    fields.llm_success = success
    fields.llm_provider = provider
    fields.llm_model = model
    fields.llm_filled = list(filled_fields)
    fields.llm_error = error
    if provider:
        fields.sources["llm_provider"] = provider
    if model:
        fields.sources["llm_model"] = model
    if invoked:
        fields.sources["llm_invoked"] = "true"
    return fields


def enrich_with_llm(
    raw_text: str,
    fields: ExtractedFields,
    *,
    api_base: str,
    api_key: str,
    model: str,
    timeout: int = 60,
    provider: str = "",
    required: bool = False,
    override: bool = False,
) -> LlmEnrichResult:
    llm_config = {
        "api_base": api_base,
        "api_key": api_key,
        "provider": provider,
    }
    provider = resolve_provider(api_base, provider)

    if not is_llm_configured(llm_config):
        message = "未配置 LLM：请填写 API 地址" + (
            "" if provider_allows_empty_key(provider) else " 与 API Key"
        )
        fields.warnings.append(message)
        merged = _apply_llm_meta(
            fields,
            invoked=False,
            success=False,
            provider=provider,
            model=model,
            filled_fields=[],
            error=message,
        )
        if required:
            merged.warnings.append(message)
        return LlmEnrichResult(fields=merged, error=message)

    user_prompt = (
        "请从以下杂乱信息中提取渠道配置字段。"
        + ("优先以你的判断为准，可覆盖规则引擎已有结果。" if override else "仅补充规则引擎未识别的字段。")
        + "\n\n"
        f"--- 用户输入 ---\n{raw_text.strip()}\n\n"
        f"--- 规则引擎已识别（可能不完整或有误）---\n"
        f"{json.dumps({k: getattr(fields, k) for k in ('name','group','type_label','model','upstream_model','api_key','base_url')}, ensure_ascii=False)}"
    )

    try:
        content = chat_completion(
            api_base=api_base,
            api_key=api_key,
            model=model,
            provider=provider,
            timeout=timeout,
            messages=[
                {
                    "role": "system",
                    "content": SYSTEM_PROMPT.format(type_labels="、".join(all_type_labels())),
                },
                {"role": "user", "content": user_prompt},
            ],
        )
        data = _parse_json_response(content)
        filled = _merge_llm_into_fields(fields, data, override=override)
        merged = _apply_llm_meta(
            fields,
            invoked=True,
            success=True,
            provider=provider,
            model=model,
            filled_fields=filled,
        )
        if required and not filled:
            merged.warnings.append("LLM 已调用但未返回可用字段，请检查模型或输入内容")
        return LlmEnrichResult(
            fields=merged,
            invoked=True,
            success=True,
            provider=provider,
            model=model,
            filled_fields=filled,
        )
    except Exception as exc:  # noqa: BLE001
        message = f"LLM 调用失败 ({provider}): {exc}"
        fields.warnings.append(message)
        merged = _apply_llm_meta(
            fields,
            invoked=True,
            success=False,
            provider=provider,
            model=model,
            filled_fields=[],
            error=message,
        )
        if required:
            merged.warnings.append(message)
        return LlmEnrichResult(
            fields=merged,
            invoked=True,
            success=False,
            provider=provider,
            model=model,
            error=message,
        )
