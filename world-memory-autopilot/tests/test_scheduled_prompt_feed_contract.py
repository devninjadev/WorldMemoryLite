"""Regression test for the scheduled feed acquisition contract."""

from __future__ import annotations

import unittest

from world_memory.bootstrap import render_scheduled_prompt
from world_memory.registry import Registry


_REGISTRY = {
    "schemaVersion": "notion-native-v2",
    "workspaceId": "11111111-1111-4111-8111-111111111111",
    "hub": {
        "pageId": "22222222-2222-4222-8222-222222222222",
        "url": "https://app.notion.com/p/22222222222242228222222222222222",
    },
    "collections": {"dataSourceId": "33333333-3333-4333-8333-333333333333"},
    "stories": {"dataSourceId": "44444444-4444-4444-8444-444444444444"},
    "storyChanges": {"dataSourceId": "55555555-5555-4555-8555-555555555555"},
    "reports": {"dataSourceId": "66666666-6666-4666-8666-666666666666"},
    "views": {
        "reportsRecent": {
            "url": "https://app.notion.com/p/77777777777747778777777777777777?v=88888888888848888888888888888888"
        },
        "storiesCurrent": {
            "url": "https://app.notion.com/p/99999999999949998999999999999999?v=aaaaaaaaaaaa4aaa8aaaaaaaaaaaaaaa"
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
    def test_binds_direct_collection_and_keeps_web_research_as_enrichment(self) -> None:
        prompt = render_scheduled_prompt(Registry.from_mapping(_REGISTRY))

        self.assertIn("Run collect-feeds exactly once", prompt)
        self.assertIn('"timeoutSeconds":20', prompt)
        self.assertIn("Use its returned filtered items unchanged", prompt)
        self.assertIn(
            "Never use generic web fetch, web search, browser, or connector tools as RSS feed transport",
            prompt,
        )
        self.assertIn(
            "General web research remains allowed after collect-feeds",
            prompt,
        )
        self.assertIn("does not change feed success or failure", prompt)
        self.assertIn("If feedSuccessCount is zero", prompt)
        self.assertIn("latestPublishedAt", prompt)


if __name__ == "__main__":
    unittest.main()
