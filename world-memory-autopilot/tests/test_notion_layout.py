"""Contract tests for the four-database Notion-native bootstrap layout."""

from __future__ import annotations

import json
import unittest

from world_memory.notion_layout import (
    DATABASE_SCHEMAS,
    DATABASE_TITLES,
    HUB_MARKER,
    HUB_TITLE,
    SCHEMA_VERSION,
    bootstrap_manifest,
)


class NotionLayoutTests(unittest.TestCase):
    def test_manifest_has_only_four_native_databases(self) -> None:
        manifest = bootstrap_manifest()
        self.assertEqual(manifest["hubTitle"], "World Memory · Notion Native")
        self.assertEqual(
            manifest["marker"], "World Memory storage contract: notion-native-v2"
        )
        self.assertEqual(
            tuple(manifest["databases"]),
            ("collections", "stories", "storyChanges", "reports"),
        )
        serialized = json.dumps(manifest, sort_keys=True)
        for forbidden in ("Runs", "Installations", "Feed Batches", "wmc1"):
            self.assertNotIn(forbidden, serialized)

    def test_constants_describe_the_native_installation(self) -> None:
        self.assertEqual(SCHEMA_VERSION, "notion-native-v2")
        self.assertEqual(HUB_TITLE, "World Memory · Notion Native")
        self.assertEqual(HUB_MARKER, "World Memory storage contract: notion-native-v2")
        self.assertEqual(
            DATABASE_TITLES,
            {
                "collections": "World Memory Collections",
                "stories": "World Memory Stories",
                "storyChanges": "World Memory Story Changes",
                "reports": "World Memory Reports",
            },
        )

    def test_collections_schema_has_exact_properties_and_enums(self) -> None:
        properties = DATABASE_SCHEMAS["collections"]["properties"]
        self.assertEqual(
            properties,
            {
                "Name": {"type": "title", "required": True},
                "Window Start": {"type": "date", "required": True},
                "Window End": {"type": "date", "required": True},
                "Feed Success Count": {"type": "number", "required": True},
                "Feed Failure Count": {"type": "number", "required": True},
                "Item Count": {"type": "number", "required": True},
                "Market Data Status": {
                    "type": "select",
                    "required": True,
                    "options": ["complete", "partial", "unavailable", "not-requested"],
                },
                "Data Gaps": {"type": "rich_text", "required": False},
                "Created At": {"type": "created_time", "required": False},
            },
        )

    def test_stories_schema_has_exact_properties_and_self_relation(self) -> None:
        properties = DATABASE_SCHEMAS["stories"]["properties"]
        self.assertEqual(
            properties["Status"],
            {"type": "select", "required": True, "options": ["emerging", "active", "cooling", "resolved"]},
        )
        self.assertEqual(
            properties["Category"],
            {
                "type": "select",
                "required": True,
                "options": ["macro", "rates", "fx", "equity", "credit", "commodity", "policy", "geopolitics", "technology", "other"],
            },
        )
        self.assertEqual(
            properties["Regions"],
            {"type": "multi_select", "required": True, "options": ["US", "KR", "CN", "JP", "EU", "GLOBAL"]},
        )
        for name in ("Importance", "Confidence"):
            self.assertEqual(
                properties[name],
                {"type": "select", "required": True, "options": ["high", "medium", "low"]},
            )
        self.assertEqual(properties["Current View"], {"type": "rich_text", "required": True})
        for name in ("First Seen", "Last Evidence At", "Last Updated"):
            self.assertEqual(properties[name], {"type": "date", "required": True})
        self.assertEqual(
            properties["Related Stories"],
            {"type": "relation", "required": False, "target": "stories", "self": True},
        )
        self.assertEqual(properties["Created At"], {"type": "created_time", "required": False})
        self.assertEqual(
            tuple(properties),
            ("Name", "Status", "Category", "Regions", "Importance", "Confidence", "Current View", "First Seen", "Last Evidence At", "Last Updated", "Related Stories", "Created At"),
        )

    def test_story_changes_schema_has_exact_properties_enums_and_relations(self) -> None:
        properties = DATABASE_SCHEMAS["storyChanges"]["properties"]
        self.assertEqual(properties["Name"], {"type": "title", "required": True})
        self.assertEqual(properties["Observed At"], {"type": "date", "required": True})
        self.assertEqual(
            properties["Change Type"],
            {
                "type": "select",
                "required": True,
                "options": ["created", "strengthened", "weakened", "reframed", "relationship-changed", "cooled", "resolved"],
            },
        )
        self.assertEqual(
            properties["Direction"],
            {"type": "select", "required": True, "options": ["strengthens", "weakens", "reframes", "connects", "closes", "neutral"]},
        )
        for name in ("Strength", "Confidence"):
            self.assertEqual(
                properties[name],
                {"type": "select", "required": True, "options": ["high", "medium", "low"]},
            )
        self.assertEqual(properties["Primary Story"], {"type": "relation", "required": True, "target": "stories"})
        self.assertEqual(properties["Related Story"], {"type": "relation", "required": False, "target": "stories"})
        self.assertEqual(properties["Related Report"], {"type": "relation", "required": False, "target": "reports"})
        self.assertEqual(properties["Related Collection"], {"type": "relation", "required": False, "target": "collections"})
        self.assertEqual(properties["Created At"], {"type": "created_time", "required": False})

    def test_reports_schema_has_exact_properties_enums_and_relations(self) -> None:
        properties = DATABASE_SCHEMAS["reports"]["properties"]
        self.assertEqual(properties["Name"], {"type": "title", "required": True})
        self.assertEqual(
            properties["Report Type"],
            {"type": "select", "required": True, "options": ["briefing", "world-memory"]},
        )
        self.assertEqual(properties["Window Start"], {"type": "date", "required": True})
        self.assertEqual(properties["Window End"], {"type": "date", "required": True})
        self.assertEqual(
            properties["Stance"],
            {"type": "select", "required": True, "options": ["risk-on", "neutral", "defensive", "mixed"]},
        )
        self.assertEqual(
            properties["Confidence"],
            {"type": "select", "required": True, "options": ["high", "medium", "low"]},
        )
        self.assertEqual(
            properties["Data Quality"],
            {"type": "select", "required": True, "options": ["complete", "partial", "limited"]},
        )
        self.assertEqual(properties["Data Gaps"], {"type": "rich_text", "required": False})
        self.assertEqual(properties["Collection"], {"type": "relation", "required": False, "target": "collections"})
        self.assertEqual(properties["Stories"], {"type": "relation", "required": False, "target": "stories"})
        self.assertEqual(properties["Created At"], {"type": "created_time", "required": False})

    def test_manifest_is_a_deep_copy_and_dates_remain_logical_schema(self) -> None:
        first = bootstrap_manifest()
        first["databases"]["reports"]["properties"]["Window Start"]["type"] = "mutated"
        second = bootstrap_manifest()
        self.assertEqual(second["databases"]["reports"]["properties"]["Window Start"], {"type": "date", "required": True})
        self.assertNotIn("date:Window Start:start", json.dumps(second, sort_keys=True))


if __name__ == "__main__":
    unittest.main()
