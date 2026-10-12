"""渠道一键测试：按模型调用 NewAPI GET /api/channel/test/:id。"""

from __future__ import annotations

from typing import Any

from .api_client import NewAPIClient, authenticate_client
from .channel_models import extract_channel_models


def parse_model_names(raw: Any) -> list[str]:
    if isinstance(raw, (list, tuple, set)):
        texts = [str(item).strip() for item in raw]
    else:
        text = str(raw or "").replace("，", ",")
        texts = [part.strip() for part in text.split(",")]
    seen: set[str] = set()
    names: list[str] = []
    for name in texts:
        if name and name not in seen:
            seen.add(name)
            names.append(name)
    return names


def format_test_failure_message(failed: list[dict[str, Any]]) -> str:
    if not failed:
        return ""
    parts: list[str] = []
    for item in failed:
        model = str(item.get("model") or "").strip() or "(默认模型)"
        message = str(item.get("message") or "测试失败").strip() or "测试失败"
        parts.append(f"模型 {model}: {message}")
    return "；".join(parts)


def test_channel_models(
    client: NewAPIClient,
    channel_id: int,
    models: list[str],
    *,
    name: str = "",
) -> dict[str, Any]:
    results: list[dict[str, Any]] = []
    failed: list[dict[str, Any]] = []
    to_test = list(models) if models else [""]
    for model in to_test:
        try:
            raw = client.test_channel(channel_id, model=model)
        except Exception as exc:  # noqa: BLE001
            raw = {"success": False, "message": str(exc), "time": 0.0, "model": model}
        entry = {
            "model": str(model or raw.get("model") or "").strip(),
            "success": bool(raw.get("success")),
            "message": str(raw.get("message") or ""),
            "time": float(raw.get("time") or 0),
        }
        results.append(entry)
        if not entry["success"]:
            failed.append(entry)

    ok = not failed
    label = f"渠道「{name}」" if name else f"渠道 #{channel_id}"
    if ok:
        times = [item["time"] for item in results if item.get("time")]
        last = times[-1] if times else 0.0
        message = f"{label}测试成功" + (f"，耗时 {last:.2f} 秒" if last else "")
    else:
        message = f"{label}测试失败：" + format_test_failure_message(failed)
    return {
        "channel_id": int(channel_id),
        "name": name,
        "success": ok,
        "message": message,
        "results": results,
        "failed": failed,
        "failed_models": [
            str(item.get("model") or "").strip() or "(默认模型)" for item in failed
        ],
    }


def run_channel_test(
    *,
    base_url: str,
    auth: dict[str, Any],
    channel_id: int,
    models: list[str] | str | None = None,
    name: str = "",
) -> dict[str, Any]:
    cid = int(channel_id or 0)
    if cid <= 0:
        raise ValueError("缺少渠道 ID，请先完成创建后再测试")
    client = NewAPIClient(base_url)
    authenticate_client(client, auth)
    model_list = parse_model_names(models)
    channel_name = str(name or "").strip()
    if not model_list:
        channels = client.list_all_channels()
        found = next((item for item in channels if int(item.get("id") or 0) == cid), None)
        if found:
            model_list = extract_channel_models(found)
            if not channel_name:
                channel_name = str(found.get("name") or "").strip()
    return test_channel_models(client, cid, model_list, name=channel_name)
