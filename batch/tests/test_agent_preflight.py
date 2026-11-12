from __future__ import annotations

import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from batch.lib import agent_preflight


class FakeClient:
    existing_channels: list[dict] = []

    def __init__(self, base_url: str):
        self.base_url = base_url

    def get_status(self):
        return {"success": True}

    def list_groups(self):
        return ["default"]

    def list_all_channels(self):
        return list(self.existing_channels)

    def create_channel(self, payload):
        raise AssertionError("只读预检不得创建渠道")

    def update_option(self, key, value):
        raise AssertionError("只读预检不得创建分组")


def _patch_remote(monkeypatch, existing_channels=None):
    FakeClient.existing_channels = list(existing_channels or [])
    monkeypatch.setattr(agent_preflight, "NewAPIClient", FakeClient)
    monkeypatch.setattr(agent_preflight, "authenticate_client", lambda client, auth: None)
    monkeypatch.setattr(
        agent_preflight,
        "get_channel_types",
        lambda base_url: ([{"value": 45, "label": "字节火山方舟、豆包通用"}], "test"),
    )


def test_preflight_isolates_line_errors_and_redacts_secrets(monkeypatch):
    _patch_remote(monkeypatch, [{"id": 7, "name": "occupied", "models": "occupied-model"}])
    text = "\n".join(
        [
            "new-channel default 字节火山方舟、豆包通用 doubao-demo doubao-demo->ep-demo sk-top-secret",
            "occupied default 字节火山方舟、豆包通用 other-model other-model->ep-other sk-other-secret",
            "broken row",
        ]
    )
    result = agent_preflight.run_agent_preflight(
        base_url="https://na.example.com",
        batch_text=text,
        default_key="",
        auth={},
    )
    assert result["read_only"] is True
    assert result["create_count"] == 1
    assert result["skip_count"] == 1
    assert result["error_count"] == 1
    assert [item["source_line"] for item in result["items"]] == [1, 2, 3]
    created = result["items"][0]
    assert created["action"] == "create"
    assert created["base_url"] == agent_preflight.DEFAULT_VOLCANO_BASE_URL
    assert created["upstream_models"] == ["ep-demo"]
    assert "sk-top-secret" not in json.dumps(result, ensure_ascii=False)
    assert "sk-other-secret" not in json.dumps(result, ensure_ascii=False)
    assert "key" not in created


def test_preflight_simulates_automatic_group_creation(monkeypatch):
    _patch_remote(monkeypatch)
    result = agent_preflight.run_agent_preflight(
        base_url="https://na.example.com",
        batch_text="new-channel team-a 字节火山方舟、豆包通用 doubao-demo doubao-demo->ep-demo sk-secret",
        default_key="",
        auth={},
    )
    assert result["groups_to_create"] == ["team-a"]
    assert result["create_count"] == 1
    assert any("自动创建分组" in change for change in result["items"][0]["changes"])
