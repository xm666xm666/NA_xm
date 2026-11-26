from unittest.mock import MagicMock

from batch.lib.platform_info import list_channels


def test_list_channels_includes_test_model_and_idle_models():
    client = MagicMock()
    client.list_all_channels.return_value = [
        {"id": 7, "models": "model-a, model-b", "test_model": "model-test"},
    ]
    client.fetch_channel_activity_stats.return_value = [
        {"channel_id": 7, "model_name": "model-test", "active_minutes": 10, "total_requests": 20},
        {"channel_id": 7, "model_name": "model-a", "active_minutes": 5, "total_requests": 8},
    ]

    rows = list_channels(client)

    requested = client.fetch_channel_activity_stats.call_args.args[0]
    assert requested == [
        {"channel_id": 7, "model_name": "model-test"},
        {"channel_id": 7, "model_name": "model-a"},
        {"channel_id": 7, "model_name": "model-b"},
    ]
    assert [item["model_name"] for item in rows[0]["activity_stats"]] == ["model-test", "model-a", "model-b"]
    idle = rows[0]["activity_stats"][-1]
    assert idle["total_requests"] == 0
    assert idle["total_tokens"] == 0
