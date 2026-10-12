# -*- coding: utf-8 -*-
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from lib.env_clusters import cluster_label, ordered_site_keys, public_host


class EnvClusterTests(unittest.TestCase):
    def test_legacy_keys_map_to_two_clusters(self):
        self.assertEqual(cluster_label("test"), "非生产")
        self.assertEqual(cluster_label("uat"), "非生产")
        self.assertEqual(cluster_label("prod"), "生产")

    def test_custom_keys_keep_cluster_sense(self):
        self.assertEqual(cluster_label("nonprod"), "非生产")
        self.assertEqual(cluster_label("production"), "生产")
        self.assertEqual(cluster_label("北京生产"), "生产")

    def test_ordered_keys_legacy_first_then_extras(self):
        keys = ordered_site_keys(
            {
                "_comment": "x",
                "upstream": {"volc": {}},
                "prod": {"base_url": "https://p.example"},
                "lab": {"base_url": "https://lab.example"},
                "test": {"base_url": "https://t.example"},
            }
        )
        self.assertEqual(keys, ["test", "prod", "lab"])

    def test_public_host_strips_path(self):
        self.assertEqual(public_host("https://na.example.com/console"), "na.example.com")
        self.assertEqual(public_host(""), "")


if __name__ == "__main__":
    unittest.main()
