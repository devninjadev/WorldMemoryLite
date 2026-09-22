"""Regression test for the scheduled feed acquisition contract."""

from __future__ import annotations

import unittest

from world_memory.bootstrap import render_scheduled_prompt
from world_memory.registry import Registry


_REGISTRY = {
    "schemaVersion": "notion-native-v2",
    "workspaceId": "3666f452-b2ec-4373-b789-21de47f74fec",
    "hub": {
        "pageId": "3bc2f5b1-4f3b-8176-9245-c8356b8b3072",
        "url": "https://app.notion.com/p/3bc2f5b14f3b81769245c8356b8b3072",
    },
    "collections": {"dataSourceId": "7ade603e-4679-4ec4-a649-9eee37aaf5f3"},
    "stories": {"dataSourceId": "70d9d79e-0731-4c0a-85c3-8fdddf8b747b"},
    "storyChanges": {"dataSourceId": "a77292d7-72a6-486f-9c17-049d0e5e66f8"},
    "reports": {"dataSourceId": "77f9c6e9-3636-4696-b2b1-e71efe2cfdd0"},
    "views": {
        "reportsRecent": {
            "url": "https://app.notion.com/p/02f42d94e35f4472b370f659ee364083?v=3bc2f5b14f3b81c483ec000c8732c5e5"
        },
        "storiesCurrent": {
            "url": "https://app.notion.com/p/a96636ccb58b43c1aec1b687149cd769?v=3bc2f5b14f3b8102af15000c67d7b019"
        },
    },
    "marketSources": {
        "vixSpreadsheet": {
            "publicCsvUrl": "https://docs.google.com/spreadsheets/d/15xqjZq8di2UqrePpYR_p72j5FCj-WTEDC4rdjZSqc_w/export?format=csv&gid=0",
            "expectedSymbols": ["VIX9D", "VIX", "VIX3M", "VIX6M"],
        }
    },
}


class ScheduledPromptFeedContractTests(unittest.TestCase):
    def test_search_mode_replaces_rss_without_losing_storage_guards(self):
        prompt = render_scheduled_prompt(Registry.from_mapping(_REGISTRY))
        for domain in ('bloomberg.com', 'ft.com', 'wsj.com', 'barrons.com', 'benzinga.com', 'marketwatch.com'):
            self.assertIn(domain, prompt)
        for guard in ('publisher-web-search-v2', 'novelty-baseline-unavailable', 'late-discovered', 'coarse-window', 'omit RSS Feed Success Count', 'Only a confirmed Report'):
            self.assertIn(guard, prompt)
        self.assertNotIn('Run collect-feeds exactly once', prompt)
        self.assertNotIn('If feedSuccessCount is zero', prompt)
        self.assertNotIn('https://rss.app/feeds/', prompt)

    def test_search_feed_admits_attributed_claims_without_original_access(self):
        prompt = render_scheduled_prompt(Registry.from_mapping(_REGISTRY))
        for boundary in ('Original-article access is optional', 'search-summary-only', 'never newly-published', 'Semantic novelty', 'Lead-only candidates cannot alone justify a Report', 'not independent', 'omit unsupported numbers', 'Do not reject'):
            self.assertIn(boundary, prompt)
        self.assertNotIn('Only new/material-update/late-discovered items with sufficient article-level evidence', prompt)

    def test_keeps_six_hour_reservation_with_345_minute_integration_due(self) -> None:
        prompt = render_scheduled_prompt(Registry.from_mapping(_REGISTRY))

        self.assertIn("Schedule creation defaults to six hours", prompt)
        self.assertIn("345 minutes", prompt)
        self.assertIn(
            "less than 345 minutes since its Window End means briefing",
            prompt,
        )
        self.assertIn(
            "exactly 345 minutes or more means world-memory",
            prompt,
        )


if __name__ == "__main__":
    unittest.main()
