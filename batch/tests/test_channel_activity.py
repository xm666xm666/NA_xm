# -*- coding: utf-8 -*-
"""渠道近一月活跃分类。"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from lib.channel_activity import (  # noqa: E402
    ACTIVITY_ACTIVE,
    ACTIVITY_IDLE,
    ACTIVITY_NA,
    activity_allows_disable,
    build_activity_fill,
    parse_activity_label,
    parse_channel_model_names,
    verdict_from_details,
)


class ChannelActivityTests(unittest.TestCase):
    def test_parse_models_multiple(self):
        names = parse_channel_model_names(
            {"test_model": "gpt-4", "models": "gpt-4, glm-5.1, gpt-4"}
        )
        self.assertEqual(names, ["gpt-4", "glm-5.1"])

    def test_no_models_is_na(self):
        fill = build_activity_fill({"id": 1}, {}, fetch_ok=True)
        self.assertEqual(fill["activity_label"], ACTIVITY_NA)
        self.assertEqual(fill["activity_verdict"], "na")

    def test_fetch_fail_is_na_per_model(self):
        fill = build_activity_fill(
            {"id": 8, "models": "a,b"},
            {},
            fetch_ok=False,
        )
        self.assertIn("a: N/A", fill["activity_label"])
        self.assertIn("b: N/A", fill["activity_label"])
        self.assertFalse(activity_allows_disable(fill["activity_label"]))

    def test_missing_stat_is_idle(self):
        fill = build_activity_fill(
            {"id": 8, "models": "a,b"},
            {(8, "a"): {"total_requests": 3, "active_minutes": 2, "avg_rpm": 1, "avg_tpm": 10}},
            fetch_ok=True,
        )
        self.assertIn(f"a: {ACTIVITY_ACTIVE}", fill["activity_label"])
        self.assertIn(f"b: {ACTIVITY_IDLE}", fill["activity_label"])
        self.assertEqual(fill["activity_verdict"], "has_active")
        self.assertFalse(activity_allows_disable(fill["activity_label"]))

    def test_all_idle_allows_disable(self):
        fill = build_activity_fill({"id": 1, "models": "only"}, {}, fetch_ok=True)
        self.assertEqual(fill["activity_label"], f"only: {ACTIVITY_IDLE}")
        self.assertTrue(activity_allows_disable(fill["activity_label"]))

    def test_legacy_empty_allows_disable(self):
        self.assertTrue(activity_allows_disable(""))
        self.assertTrue(activity_allows_disable(None))

    def test_parse_label(self):
        parsed = parse_activity_label("m1: 近一月无活跃\nm2: 有活跃")
        self.assertEqual(verdict_from_details(parsed["details"]), "has_active")
        self.assertFalse(parsed["legacy"])
