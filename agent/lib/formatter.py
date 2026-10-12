"""格式化为 old 程序渠道管理行。"""

from __future__ import annotations

from .rule_extractor import ExtractedFields
from .type_registry import get_type_by_label


def format_channel_line(fields: ExtractedFields, *, require_key: bool = True) -> str:
    """输出 old 程序可粘贴的单行渠道数据。

    ``require_key=False`` 用于更新原配置：不写秘钥列，网关保留原密钥。
    """
    name = fields.name.strip()
    group = fields.group.strip()
    type_label = fields.type_label.strip()
    model = fields.model.strip() or name
    upstream = fields.upstream_model.strip()
    base_url = fields.base_url.strip()
    api_key = fields.api_key.strip()
    api_version = fields.api_version.strip()

    needed = [name, group, type_label, model, upstream, base_url]
    if require_key:
        needed.append(api_key)
    if not all(needed):
        missing = fields.missing_fields(require_key=require_key)
        raise ValueError(f"字段不完整，缺少: {', '.join(missing)}")

    redirect = f"{model}->{upstream}"
    type_info = get_type_by_label(type_label)
    parts = [name, group, type_label, model, redirect, base_url]
    if type_info and type_info.api_version_required:
        if not api_version:
            raise ValueError(f"类型「{type_label}」必须填写 API 版本")
        parts.append(api_version)
    if require_key:
        parts.append(api_key)
    return " ".join(parts)


def format_fields_summary(fields: ExtractedFields) -> dict[str, str]:
    return {
        "名称": fields.name,
        "分组": fields.group,
        "类型": fields.type_label,
        "模型": fields.model,
        "模型上游": fields.upstream_model,
        "Base URL": fields.base_url,
        "API版本": fields.api_version,
        "API Key": fields.api_key,
    }
