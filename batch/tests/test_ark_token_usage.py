from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT / "batch") not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT / "batch"))

import lib.ark_token_usage as module  # noqa: E402


def test_usage_payload_builds_default_month_query():
    payload = module.usage_payload({
        "start_time": "2026-10-01",
        "end_time": "2026-10-07",
        "query_interval": "hour",
        "project_name": " AI-Drug ",
    })
    assert payload == {
        "StartTime": "2026-10-01",
        "EndTime": "2026-10-07",
        "QueryInterval": "Hour",
        "ProjectName": "AI-Drug",
    }


def test_usage_payload_accepts_model_filter():
    payload = module.usage_payload({
        "start": "2026-10-05",
        "end": "2026-10-01",
        "interval": "Day",
        "filter_type": "model_name",
        "filter_values": "a, b，c",
    })
    assert payload["StartTime"] == "2026-10-01"
    assert payload["EndTime"] == "2026-10-05"
    assert payload["Filters"] == [{"Key": "ModelName", "Values": ["a", "b", "c"]}]


def test_usage_totals_and_csv_export_are_stable():
    fields = ["Day", "InputTokens", "OutputTokens", "TotalTokens", "ReqCnt"]
    rows = [["2026-10-01", "10", "2", "12", "1"], ["2026-10-02", "20", "3", "23", "2"]]
    totals = module.usage_totals(fields, rows)
    assert totals == {
        "InputTokens": 30,
        "OutputTokens": 5,
        "TotalTokens": 35,
        "ReqCnt": 3,
    }
    assert module.csv_bytes(fields, rows).startswith(b"\xef\xbb\xbf")
