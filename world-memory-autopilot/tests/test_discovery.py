"""Behavioral tests for one-shot read-only registry recovery."""

from __future__ import annotations

import copy
import unittest

from world_memory.discovery import resolve_registry_discovery
from world_memory.notion_layout import DATABASE_SCHEMAS, HUB_MARKER, HUB_TITLE
from world_memory.views import (
    REPORTS_RECENT_CONFIGURATION,
    STORIES_CURRENT_CONFIGURATION,
)

from tests.test_cli import REGISTRY, WORKSPACE_ID


LIVE_HUB_ID = "10000000-0000-4000-8000-000000000001"
LIVE_DATABASE_IDS = {
    "collections": "20000000-0000-4000-8000-000000000001",
    "stories": "20000000-0000-4000-8000-000000000002",
    "storyChanges": "20000000-0000-4000-8000-000000000003",
    "reports": "20000000-0000-4000-8000-000000000004",
}
LIVE_DATA_SOURCE_IDS = {
    "collections": "30000000-0000-4000-8000-000000000001",
    "stories": "30000000-0000-4000-8000-000000000002",
    "storyChanges": "30000000-0000-4000-8000-000000000003",
    "reports": "30000000-0000-4000-8000-000000000004",
}
LIVE_VIEW_IDS = {
    "reportsRecent": "40000000-0000-4000-8000-000000000001",
    "storiesCurrent": "40000000-0000-4000-8000-000000000002",
}


def _database_url(identifier: str) -> str:
    return "https://app.notion.com/p/" + identifier.replace("-", "")


def _configuration_parts(configuration: str) -> tuple[list[str], list[str]]:
    show = configuration.split("SHOW ", 1)[1].split(";", 1)[0]
    display_properties = [item.strip().strip('"') for item in show.split(",")]
    sort_text = configuration.split("SORT BY ", 1)[1]
    sorts = [item.strip() for item in sort_text.split(",")]
    return display_properties, sorts


def live_discovery_input() -> dict[str, object]:
    databases: dict[str, object] = {}
    for key, schema in DATABASE_SCHEMAS.items():
        properties = {
            name: ("text" if descriptor["type"] == "rich_text" else descriptor["type"])
            for name, descriptor in schema["properties"].items()
        }
        databases[key] = {
            "title": schema["title"],
            "databaseUrl": _database_url(LIVE_DATABASE_IDS[key]),
            "parentPageId": LIVE_HUB_ID,
            "dataSourceId": LIVE_DATA_SOURCE_IDS[key],
            "properties": properties,
        }

    reports_display, reports_sorts = _configuration_parts(
        REPORTS_RECENT_CONFIGURATION
    )
    stories_display, stories_sorts = _configuration_parts(
        STORIES_CURRENT_CONFIGURATION
    )
    installation = {
        "databases": databases,
        "views": {
            "reportsRecent": {
                "name": "Reports Recent",
                "databaseUrl": _database_url(LIVE_DATABASE_IDS["reports"]),
                "viewId": LIVE_VIEW_IDS["reportsRecent"],
                "dataSourceId": LIVE_DATA_SOURCE_IDS["reports"],
                "displayProperties": reports_display,
                "sorts": reports_sorts,
            },
            "storiesCurrent": {
                "name": "Stories Current",
                "databaseUrl": _database_url(LIVE_DATABASE_IDS["stories"]),
                "viewId": LIVE_VIEW_IDS["storiesCurrent"],
                "dataSourceId": LIVE_DATA_SOURCE_IDS["stories"],
                "displayProperties": stories_display,
                "sorts": stories_sorts,
            },
        },
    }
    legacy_ids = (
        "50000000-0000-4000-8000-000000000001",
        "50000000-0000-4000-8000-000000000002",
        "50000000-0000-4000-8000-000000000003",
    )
    return {
        "workspaceId": WORKSPACE_ID,
        "candidates": [
            {
                "pageId": identifier,
                "url": _database_url(identifier),
                "title": HUB_TITLE,
                "marker": "World Memory storage contract: notion-native-v1",
                "workspaceRoot": True,
                "installation": None,
            }
            for identifier in legacy_ids
        ]
        + [
            {
                "pageId": LIVE_HUB_ID,
                "url": (
                    "https://app.notion.com/p/example/World-Memory-Notion-Native-"
                    + LIVE_HUB_ID.replace("-", "")
                ),
                "title": HUB_TITLE,
                "marker": HUB_MARKER,
                "workspaceRoot": True,
                "installation": installation,
            }
        ],
    }


class RegistryDiscoveryTests(unittest.TestCase):
    def test_live_shape_selects_the_unique_v2_hub_among_four_title_matches(self) -> None:
        result = resolve_registry_discovery(live_discovery_input())

        self.assertEqual(result["status"], "recovered")
        self.assertEqual(result["error"], "")
        registry = result["registry"]
        self.assertEqual(registry["workspaceId"], WORKSPACE_ID)
        self.assertEqual(registry["hub"]["pageId"], LIVE_HUB_ID)
        for key in ("collections", "stories", "storyChanges", "reports"):
            self.assertEqual(
                registry[key], {"dataSourceId": LIVE_DATA_SOURCE_IDS[key]}
            )
        self.assertEqual(
            registry["views"]["reportsRecent"]["url"],
            _database_url(LIVE_DATABASE_IDS["reports"])
            + "?v="
            + LIVE_VIEW_IDS["reportsRecent"].replace("-", ""),
        )
        self.assertEqual(
            registry["views"]["storiesCurrent"]["url"],
            _database_url(LIVE_DATABASE_IDS["stories"])
            + "?v="
            + LIVE_VIEW_IDS["storiesCurrent"].replace("-", ""),
        )
        self.assertEqual(registry["marketSources"], REGISTRY["marketSources"])

    def test_no_exact_v2_root_candidate_returns_bounded_not_found(self) -> None:
        request = live_discovery_input()
        request["candidates"] = request["candidates"][:-1]

        self.assertEqual(
            resolve_registry_discovery(request),
            {
                "status": "not-found",
                "error": "world-memory-location-not-found",
                "registry": None,
            },
        )

    def test_two_exact_v2_root_candidates_return_bounded_ambiguity(self) -> None:
        request = live_discovery_input()
        duplicate = copy.deepcopy(request["candidates"][-1])
        duplicate["pageId"] = "22222222-2222-4222-8222-222222222222"
        duplicate["url"] = _database_url(duplicate["pageId"])
        request["candidates"].append(duplicate)

        self.assertEqual(
            resolve_registry_discovery(request),
            {
                "status": "ambiguous",
                "error": "world-memory-location-ambiguous",
                "registry": None,
            },
        )

    def test_schema_mismatch_returns_bounded_structure_error(self) -> None:
        request = live_discovery_input()
        candidate = request["candidates"][-1]
        candidate["installation"]["databases"]["reports"]["properties"].pop(
            "Window End"
        )

        self.assertEqual(
            resolve_registry_discovery(request),
            {
                "status": "structure-mismatch",
                "error": "world-memory-structure-mismatch",
                "registry": None,
            },
        )

    def test_wrong_view_binding_returns_bounded_structure_error(self) -> None:
        request = live_discovery_input()
        candidate = request["candidates"][-1]
        candidate["installation"]["views"]["storiesCurrent"][
            "dataSourceId"
        ] = LIVE_DATA_SOURCE_IDS["reports"]

        self.assertEqual(
            resolve_registry_discovery(request),
            {
                "status": "structure-mismatch",
                "error": "world-memory-structure-mismatch",
                "registry": None,
            },
        )


if __name__ == "__main__":
    unittest.main()
