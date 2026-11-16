"""New API 上游用户管理的受控适配层。"""

from __future__ import annotations

import unicodedata
from typing import Any


MANAGE_ACTIONS = {"enable", "disable", "delete", "promote", "demote"}
SEARCH_PAGE_SIZE = 100
CREATE_FIELDS = {"username", "display_name", "password", "remark"}
UPDATE_FIELDS = CREATE_FIELDS | {"group", "quota"}
PUBLIC_USER_FIELDS = {
    "id",
    "username",
    "display_name",
    "role",
    "status",
    "email",
    "github_id",
    "discord_id",
    "oidc_id",
    "wechat_id",
    "telegram_id",
    "linux_do_id",
    "quota",
    "used_quota",
    "request_count",
    "group",
    "aff_count",
    "aff_quota",
    "aff_history_quota",
    "inviter_id",
    "DeletedAt",
    "deleted_at",
    "remark",
}
COMMON_WEAK_PASSWORDS = {
    "000000",
    "111111",
    "123456",
    "12345678",
    "123456789",
    "1234567890",
    "1q2w3e4r",
    "1qaz2wsx",
    "abc123",
    "admin",
    "admin123",
    "admin1234",
    "admin1234!",
    "admin@123",
    "letmein",
    "password",
    "password1",
    "password1!",
    "password123",
    "password@123",
    "qwerty",
    "qwerty123",
    "qwerty123!",
    "root",
    "root123",
    "test1234",
    "welcome",
}


def _positive_int(value: Any, label: str, *, maximum: int | None = None) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{label}必须是正整数")
    try:
        parsed = int(str(value).strip())
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label}必须是正整数") from exc
    if parsed <= 0 or str(value).strip() not in {str(parsed), f"+{parsed}"}:
        raise ValueError(f"{label}必须是正整数")
    if maximum is not None and parsed > maximum:
        raise ValueError(f"{label}不能超过 {maximum}")
    return parsed


def normalize_list_query(page: Any, page_size: Any, keyword: Any, group: Any) -> dict[str, Any]:
    normalized_keyword = str(keyword or "").strip()
    normalized_group = str(group or "").strip()
    if len(normalized_keyword) > 100:
        raise ValueError("搜索关键字不能超过 100 个字符")
    if len(normalized_group) > 64:
        raise ValueError("分组名称不能超过 64 个字符")
    return {
        "page": _positive_int(page or 1, "页码"),
        "page_size": _positive_int(page_size or 20, "每页数量", maximum=100),
        "keyword": normalized_keyword,
        "group": normalized_group,
    }


def validate_password_strength(password: Any) -> str:
    if not isinstance(password, str):
        return "密码必须是字符串"
    length = len(password)
    if length < 8:
        return "密码长度至少为8个字符"
    if length > 20:
        return "密码长度不能超过20个字符"
    if len(password.encode("utf-8")) > 72:
        return "密码 UTF-8 编码不能超过72字节"
    if password.strip().lower() in COMMON_WEAK_PASSWORDS:
        return "密码过于常见，请更换更强的密码"
    categories = [False, False, False, False]
    for char in password:
        if char.isupper():
            categories[0] = True
        elif char.islower():
            categories[1] = True
        elif char.isdigit():
            categories[2] = True
        elif unicodedata.category(char).startswith(("P", "S")):
            categories[3] = True
    if sum(categories) < 3:
        return "密码必须包含大写字母、小写字母、数字、特殊符号中的至少三类"
    return ""


def _clean_record(payload: Any, allowed: set[str]) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("请提交有效的用户参数")
    unknown = sorted(set(payload) - allowed)
    if unknown:
        raise ValueError(f"包含不支持的用户字段：{', '.join(unknown)}")
    return dict(payload)


def _text_field(record: dict[str, Any], field: str, label: str, maximum: int, *, required: bool = False) -> str:
    value = record.get(field, "")
    if not isinstance(value, str):
        raise ValueError(f"{label}必须是字符串")
    value = value.strip() if field in {"username", "group"} else value
    if required and not value:
        raise ValueError(f"请填写{label}")
    if len(value) > maximum:
        raise ValueError(f"{label}不能超过 {maximum} 个字符")
    record[field] = value
    return value


def validate_create_record(payload: Any) -> dict[str, Any]:
    record = _clean_record(payload, CREATE_FIELDS)
    username = _text_field(record, "username", "用户名", 20, required=True)
    _text_field(record, "display_name", "显示名称", 20)
    _text_field(record, "remark", "备注", 255)
    password_error = validate_password_strength(record.get("password"))
    if password_error:
        raise ValueError(password_error)
    if not record["display_name"]:
        record["display_name"] = username
    record["role"] = 1
    return record


def validate_update_record(user_id: Any, payload: Any) -> dict[str, Any]:
    parsed_id = _positive_int(user_id, "用户 ID")
    record = _clean_record(payload, UPDATE_FIELDS)
    missing = sorted({"username", "display_name", "remark", "group", "quota"} - set(record))
    if missing:
        raise ValueError(f"编辑用户缺少字段：{', '.join(missing)}")
    _text_field(record, "username", "用户名", 20, required=True)
    _text_field(record, "display_name", "显示名称", 20)
    _text_field(record, "remark", "备注", 255)
    _text_field(record, "group", "分组", 64, required=True)
    password = record.get("password", "")
    if password:
        password_error = validate_password_strength(password)
        if password_error:
            raise ValueError(password_error)
    elif not isinstance(password, str):
        raise ValueError("密码必须是字符串")
    quota = record.get("quota")
    if isinstance(quota, bool):
        raise ValueError("额度必须是整数")
    try:
        record["quota"] = int(str(quota).strip())
    except (TypeError, ValueError) as exc:
        raise ValueError("额度必须是整数") from exc
    if str(quota).strip() not in {str(record["quota"]), f"+{record['quota']}"}:
        raise ValueError("额度必须是整数")
    record["id"] = parsed_id
    return record


def validate_manage_action(user_id: Any, action: Any) -> tuple[int, str]:
    parsed_id = _positive_int(user_id, "用户 ID")
    normalized_action = str(action or "").strip().lower()
    if normalized_action not in MANAGE_ACTIONS:
        raise ValueError("不支持的用户管理操作")
    return parsed_id, normalized_action


def public_user(record: Any) -> dict[str, Any]:
    if not isinstance(record, dict):
        return {}
    return {field: record[field] for field in PUBLIC_USER_FIELDS if field in record}


def public_action_result(data: Any) -> Any:
    """管理动作只回传白名单字段，避免旧版上游回显密码等敏感数据。"""
    if isinstance(data, dict):
        return public_user(data)
    if isinstance(data, list):
        return [public_user(item) for item in data if isinstance(item, dict)]
    return None


def _request(client: Any, method: str, path: str, *, params: dict[str, Any] | None = None, payload: dict[str, Any] | None = None, fallback: str) -> Any:
    kwargs: dict[str, Any] = {
        "params": params,
        "headers": {**client._headers(), "Accept": "application/json"},
        "timeout": client.timeout,
    }
    if payload is not None:
        kwargs["json"] = payload
    response = client.session.request(method, f"{client.base_url.rstrip('/')}{path}", **kwargs)
    try:
        body = response.json()
    except (TypeError, ValueError):
        body = None
    if isinstance(body, dict) and body.get("success") is False:
        raise RuntimeError(str(body.get("message") or fallback))
    response.raise_for_status()
    if not isinstance(body, dict) or not body.get("success"):
        message = body.get("message") if isinstance(body, dict) else ""
        raise RuntimeError(str(message or fallback))
    return body.get("data")


def _user_page(client: Any, path: str, params: dict[str, Any]) -> tuple[list[Any], int]:
    data = _request(client, "GET", path, params=params, fallback="获取用户列表失败")
    if isinstance(data, list):
        items = data
        total = len(items)
    elif isinstance(data, dict):
        items = data.get("items") or []
        total = data.get("total", len(items))
    else:
        raise RuntimeError("用户列表格式异常")
    if not isinstance(items, list):
        raise RuntimeError("用户列表格式异常")
    try:
        total = max(0, int(total))
    except (TypeError, ValueError) as exc:
        raise RuntimeError("用户总数格式异常") from exc
    return items, total


def _matches_username_or_id(record: Any, keyword: str) -> bool:
    if not isinstance(record, dict):
        return False
    username = str(record.get("username") or "")
    if keyword.casefold() in username.casefold():
        return True
    if keyword.isascii() and keyword.isdigit():
        raw_id = record.get("id")
        if raw_id is None or isinstance(raw_id, bool):
            return False
        try:
            return int(str(raw_id)) == int(keyword)
        except (TypeError, ValueError):
            return False
    return False


def _search_usernames(client: Any, keyword: str, group: str) -> list[Any]:
    """上游宽匹配可能命中邮箱或显示名称，这里收敛为用户名或 ID 并保留准确总数。"""
    matches: list[Any] = []
    upstream_page = 1
    scanned = 0
    while True:
        items, total = _user_page(
            client,
            "/api/user/search",
            {
                "p": 0 if upstream_page == 1 else upstream_page,
                "page_size": SEARCH_PAGE_SIZE,
                "keyword": keyword,
                "group": group,
            },
        )
        matches.extend(item for item in items if _matches_username_or_id(item, keyword))
        scanned += len(items)
        if not items or scanned >= total or len(items) < SEARCH_PAGE_SIZE:
            return matches
        upstream_page += 1


def list_users(client: Any, query: dict[str, Any]) -> dict[str, Any]:
    page = query["page"]
    page_size = query["page_size"]
    keyword = query["keyword"]
    group = query["group"]
    if keyword:
        matches = _search_usernames(client, keyword, group)
        start = (page - 1) * page_size
        items = matches[start:start + page_size]
        total = len(matches)
    else:
        params: dict[str, Any] = {
            "p": 0 if page == 1 else page,
            "page_size": page_size,
        }
        path = "/api/user/"
        if group:
            path = "/api/user/search"
            params.update({"keyword": "", "group": group})
        items, total = _user_page(client, path, params)
    return {
        "items": [public_user(item) for item in items if isinstance(item, dict)],
        "page": page,
        "page_size": page_size,
        "total": total,
    }


def get_user(client: Any, user_id: Any) -> dict[str, Any]:
    parsed_id = _positive_int(user_id, "用户 ID")
    data = _request(client, "GET", f"/api/user/{parsed_id}", fallback="获取用户详情失败")
    if not isinstance(data, dict):
        raise RuntimeError("用户详情格式异常")
    record = public_user(data)
    record["password"] = ""
    return record


def create_user(client: Any, record: dict[str, Any]) -> Any:
    data = _request(client, "POST", "/api/user/", payload=record, fallback="创建用户失败")
    return public_action_result(data)


def update_user(client: Any, record: dict[str, Any]) -> Any:
    data = _request(client, "PUT", "/api/user/", payload=record, fallback="更新用户失败")
    return public_action_result(data)


def manage_user(client: Any, user_id: int, action: str) -> Any:
    data = _request(
        client,
        "POST",
        "/api/user/manage",
        payload={"id": user_id, "action": action},
        fallback="用户管理操作失败",
    )
    return public_action_result(data)


def reset_user_security(client: Any, user_id: Any, kind: str) -> Any:
    parsed_id = _positive_int(user_id, "用户 ID")
    paths = {"passkey": "reset_passkey", "2fa": "2fa"}
    if kind not in paths:
        raise ValueError("不支持的安全重置操作")
    labels = {"passkey": "重置 Passkey 失败", "2fa": "重置 2FA 失败"}
    data = _request(
        client,
        "DELETE",
        f"/api/user/{parsed_id}/{paths[kind]}",
        fallback=labels[kind],
    )
    return public_action_result(data)


def _group_names(data: Any) -> list[str]:
    if isinstance(data, dict):
        data = data.get("items") or data.get("groups") or list(data)
    if not isinstance(data, list):
        return []
    names = []
    for item in data:
        name = item.get("name") if isinstance(item, dict) else item
        if isinstance(name, str) and name.strip() and name.strip() not in names:
            names.append(name.strip())
    return names


def get_user_options(client: Any) -> dict[str, Any]:
    """读取筛选项和额度展示配置；辅助配置失败时不阻塞用户列表。"""
    groups: list[str] = []
    warnings: list[str] = []
    try:
        groups = _group_names(_request(client, "GET", "/api/group/", fallback="获取分组失败"))
    except Exception as exc:  # noqa: BLE001
        try:
            groups = _group_names(client.list_user_groups())
        except Exception:  # noqa: BLE001
            warnings.append(str(exc) or "分组读取失败")

    status: dict[str, Any] = {}
    try:
        raw_status = _request(client, "GET", "/api/status", fallback="获取额度配置失败")
        if isinstance(raw_status, dict):
            status = raw_status
    except Exception as exc:  # noqa: BLE001
        warnings.append(str(exc) or "额度配置读取失败")
    try:
        quota_per_unit = float(status.get("quota_per_unit") or 500000)
    except (TypeError, ValueError):
        quota_per_unit = 500000.0
    if quota_per_unit <= 0:
        quota_per_unit = 500000.0
    return {
        "groups": groups,
        "quota_per_unit": quota_per_unit,
        "quota_display_type": str(status.get("quota_display_type") or "USD"),
        "usd_exchange_rate": status.get("usd_exchange_rate") or 1,
        "custom_currency_symbol": str(status.get("custom_currency_symbol") or "¤"),
        "custom_currency_exchange_rate": status.get("custom_currency_exchange_rate") or 1,
        "warnings": warnings,
    }
