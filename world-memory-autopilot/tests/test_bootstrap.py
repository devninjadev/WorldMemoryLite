"""Contract tests for the finite fresh setup plan and scheduled prompt."""

from __future__ import annotations

import copy
import json
import unittest

from world_memory.bootstrap import build_bootstrap_plan, render_scheduled_prompt
from world_memory.feed import FEEDS
from world_memory.notion_layout import DATABASE_SCHEMAS, HUB_MARKER
from world_memory.registry import Registry

from tests.test_cli import (
    REGISTRY,
    VIX_PUBLIC_CSV_URL,
    VIX_SYMBOLS,
    WORKSPACE_ID,
)


class BootstrapPlanTests(unittest.TestCase):
    def test_bootstrap_plan_creates_new_hub_without_search_or_migration(self) -> None:
        plan = build_bootstrap_plan(WORKSPACE_ID)

        self.assertEqual(plan["mode"], "fresh-install")
        self.assertEqual(plan["hub"]["title"], "World Memory · Notion Native")
        self.assertEqual(plan["hub"]["marker"], HUB_MARKER)
        self.assertEqual(len(plan["databases"]), 4)
        serialized = json.dumps(plan, ensure_ascii=False).lower()
        for forbidden in (
            "search",
            "migration",
            "delete",
            "move",
            "repair",
            "retry",
            "credential",
            "oldtitle",
            "oldid",
            "live response",
        ):
            self.assertNotIn(forbidden, serialized)

    def test_plan_has_one_finite_ordered_fresh_install_action_sequence(self) -> None:
        plan = build_bootstrap_plan(WORKSPACE_ID)
        actions = plan["actions"]

        self.assertEqual(
            [action["action"] for action in actions],
            [
                "fetch-self-and-check-workspace",
                "create-hub",
                "create-database-with-initial-data-source",
                "create-database-with-initial-data-source",
                "create-database-with-initial-data-source",
                "create-database-with-initial-data-source",
                "resolve-initial-data-source-locators",
                "add-declared-relations",
                "configure-saved-views",
                "verify-read-only-vix-spreadsheet-source",
                "read-back",
                "emit-registry",
            ],
        )
        self.assertEqual(
            [action["step"] for action in actions], list(range(1, len(actions) + 1))
        )
        self.assertEqual(actions[0]["expectedWorkspaceId"], WORKSPACE_ID)
        self.assertEqual(
            actions[1],
            {
                "step": 2,
                "action": "create-hub",
                "title": "World Memory · Notion Native",
                "marker": HUB_MARKER,
            },
        )
        self.assertEqual(
            [
                action["databaseKey"]
                for action in actions
                if action["action"]
                == "create-database-with-initial-data-source"
            ],
            ["collections", "stories", "storyChanges", "reports"],
        )
        for action in actions[2:6]:
            database = next(
                item
                for item in plan["databases"]
                if item["key"] == action["databaseKey"]
            )
            self.assertEqual(
                action,
                {
                    "step": action["step"],
                    "action": "create-database-with-initial-data-source",
                    "databaseKey": database["key"],
                    "parent": "new-hub",
                    "databaseTitle": database["title"],
                    "initialDataSource": {
                        "title": database["title"],
                        "properties": database["properties"],
                    },
                },
            )
        self.assertLess(
            [item["action"] for item in actions].index(
                "resolve-initial-data-source-locators"
            ),
            [item["action"] for item in actions].index("add-declared-relations"),
        )
        self.assertEqual(
            actions[6],
            {
                "step": 7,
                "action": "resolve-initial-data-source-locators",
                "databaseKeys": [
                    "collections",
                    "stories",
                    "storyChanges",
                    "reports",
                ],
                "fields": ["dataSourceId"],
            },
        )
        self.assertEqual(
            actions[-4],
            {
                "step": 9,
                "action": "configure-saved-views",
                "tool": "notion_create_view",
                "databaseLocatorSource": "matching create response only",
                "queryableUrl": "databaseUrl with returned viewId as sole v parameter",
                "views": [
                    {
                        "key": "reportsRecent",
                        "dataSourceKey": "reports",
                        "title": "Reports Recent",
                        "configuration": (
                            'SHOW "Name", "Report Type", "Window Start", '
                            '"Window End", "Created At", "Collection", "Stories"; '
                            'SORT BY "Window End" DESC, "Created At" DESC'
                        ),
                    },
                    {
                        "key": "storiesCurrent",
                        "dataSourceKey": "stories",
                        "title": "Stories Current",
                        "configuration": (
                            'SHOW "Name", "Status", "Category", "Regions", '
                            '"Importance", "Confidence", "Current View", '
                            '"First Seen", "Last Evidence At", "Last Updated", '
                            '"Related Stories", "Created At"; '
                            'FILTER "Status" != "resolved"; '
                            'SORT BY "Last Evidence At" DESC, "Last Updated" DESC'
                        ),
                    },
                ],
            },
        )
        self.assertEqual(
            actions[-3],
            {
                "step": 10,
                "action": "verify-read-only-vix-spreadsheet-source",
                "method": "GET",
                "publicCsvUrl": VIX_PUBLIC_CSV_URL,
                "expectedSymbols": VIX_SYMBOLS,
                "mutationAllowed": False,
            },
        )
        self.assertEqual(
            actions[-2],
            {
                "step": 11,
                "action": "read-back",
                "hubLocatorFields": ["pageId", "url"],
                "dataSourceLocatorFields": ["dataSourceId"],
                "schemaProjectionFields": ["propertyNames", "propertyTypes"],
                "viewLocatorFields": ["databaseUrl", "viewId", "queryableUrl"],
                "viewBindingFields": ["dataSourceId", "configuration"],
            },
        )
        self.assertEqual(
            actions[-1],
            {
                "step": 12,
                "action": "emit-registry",
                "schemaVersion": "notion-native-v2",
                "locatorKeys": [
                    "hub",
                    "collections",
                    "stories",
                    "storyChanges",
                    "reports",
                    "views",
                    "marketSources",
                ],
            },
        )
        self.assertEqual(
            plan["views"],
            actions[-4]["views"],
        )
        self.assertEqual(plan["marketSources"], REGISTRY["marketSources"])

    def test_data_sources_are_logical_nonrelation_schema_then_declared_relations(self) -> None:
        plan = build_bootstrap_plan(WORKSPACE_ID)
        expected_relations = []

        for database in plan["databases"]:
            key = database["key"]
            expected_properties = {
                name: descriptor
                for name, descriptor in DATABASE_SCHEMAS[key]["properties"].items()
                if descriptor["type"] != "relation"
            }
            self.assertEqual(database["title"], DATABASE_SCHEMAS[key]["title"])
            self.assertEqual(database["properties"], expected_properties)
            self.assertNotIn(
                "relation",
                {
                    descriptor["type"]
                    for descriptor in database["properties"].values()
                },
            )

            for property_name, descriptor in DATABASE_SCHEMAS[key][
                "properties"
            ].items():
                if descriptor["type"] == "relation":
                    expected_relations.append(
                        {
                            "sourceDatabase": key,
                            "property": property_name,
                            "targetDatabase": descriptor["target"],
                            "required": descriptor["required"],
                            "self": descriptor.get("self", False),
                        }
                    )

        self.assertEqual(plan["relations"], expected_relations)
        relation_action = next(
            action
            for action in plan["actions"]
            if action["action"] == "add-declared-relations"
        )
        self.assertEqual(relation_action["relations"], expected_relations)

    def test_plan_is_independent_and_normalizes_only_the_workspace_uuid(self) -> None:
        plan = build_bootstrap_plan(WORKSPACE_ID.replace("-", "").upper())
        self.assertEqual(plan["workspaceId"], WORKSPACE_ID)
        plan["databases"][0]["properties"]["Name"]["type"] = "mutated"
        self.assertEqual(
            build_bootstrap_plan(WORKSPACE_ID)["databases"][0]["properties"][
                "Name"
            ]["type"],
            "title",
        )

        with self.assertRaisesRegex(ValueError, "workspace_id"):
            build_bootstrap_plan("not-a-workspace-uuid")

    def test_bootstrap_plan_sets_the_six_hour_schedule_creation_cadence(self) -> None:
        plan = build_bootstrap_plan(WORKSPACE_ID)

        self.assertEqual(plan["schedule"], {"creationCadenceMinutes": 360})




if __name__ == "__main__":
    unittest.main()
