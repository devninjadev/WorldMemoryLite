"""Contract tests for the immutable notion-native installation registry."""

from __future__ import annotations

import copy
from dataclasses import FrozenInstanceError
import unittest

from world_memory.registry import (
    DEFAULT_VIX_SPREADSHEET_SOURCE,
    DataSourceLocator,
    MarketSources,
    PageLocator,
    Registry,
    VixSpreadsheetSource,
    ViewLocator,
    notion_page_id_from_url,
    validate_registry,
)


WORKSPACE_ID = "11111111-1111-4111-8111-111111111111"
HUB_ID = "22222222-2222-4222-8222-222222222222"
COLLECTIONS_ID = "33333333-3333-4333-8333-333333333333"
STORIES_ID = "44444444-4444-4444-8444-444444444444"
STORY_CHANGES_ID = "55555555-5555-4555-8555-555555555555"
REPORTS_ID = "66666666-6666-4666-8666-666666666666"
REPORTS_VIEW_ID = "77777777-7777-4777-8777-777777777777"
STORIES_VIEW_ID = "88888888-8888-4888-8888-888888888888"
DATABASE_IDS = {
    "collections": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
    "stories": "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
    "storyChanges": "cccccccc-cccc-4ccc-8ccc-cccccccccccc",
    "reports": "dddddddd-dddd-4ddd-8ddd-dddddddddddd",
}
VIX_PUBLIC_CSV_URL = (
    "https://docs.google.com/spreadsheets/d/"
    "15xqjZq8di2UqrePpYR_p72j5FCj-WTEDC4rdjZSqc_w/export?format=csv&gid=0"
)
VIX_SYMBOLS = ("VIX9D", "VIX", "VIX3M", "VIX6M")


def notion_url(identifier: str) -> str:
    return "https://www.notion.so/World-Memory-" + identifier.replace("-", "")


def notion_view_url(database_id: str, view_id: str) -> str:
    return (
        "https://app.notion.com/p/"
        + database_id.replace("-", "")
        + "?v="
        + view_id.replace("-", "")
    )


FIXTURE = {
    "schemaVersion": "notion-native-v2",
    "workspaceId": WORKSPACE_ID,
    "hub": {"pageId": HUB_ID, "url": notion_url(HUB_ID)},
    "collections": {"dataSourceId": COLLECTIONS_ID},
    "stories": {"dataSourceId": STORIES_ID},
    "storyChanges": {"dataSourceId": STORY_CHANGES_ID},
    "reports": {"dataSourceId": REPORTS_ID},
    "views": {
        "reportsRecent": {
            "url": notion_view_url(DATABASE_IDS["reports"], REPORTS_VIEW_ID)
        },
        "storiesCurrent": {
            "url": notion_view_url(DATABASE_IDS["stories"], STORIES_VIEW_ID)
        },
    },
    "marketSources": {
        "vixSpreadsheet": {
            "publicCsvUrl": VIX_PUBLIC_CSV_URL,
            "expectedSymbols": list(VIX_SYMBOLS),
        }
    },
}


class RegistryTests(unittest.TestCase):
    def test_accepts_exact_native_registry(self) -> None:
        registry = Registry.from_mapping(FIXTURE)
        self.assertEqual(registry.schema_version, "notion-native-v2")
        self.assertIsInstance(registry.hub, PageLocator)
        self.assertIsInstance(registry.reports, DataSourceLocator)
        self.assertIsInstance(registry.reports_recent, ViewLocator)
        self.assertIsInstance(registry.market_sources, MarketSources)
        self.assertIsInstance(
            registry.market_sources.vix_spreadsheet, VixSpreadsheetSource
        )
        self.assertEqual(
            registry.market_sources.vix_spreadsheet,
            VixSpreadsheetSource(VIX_PUBLIC_CSV_URL, VIX_SYMBOLS),
        )
        self.assertEqual(
            registry.market_sources.vix_spreadsheet,
            DEFAULT_VIX_SPREADSHEET_SOURCE,
        )
        self.assertEqual(registry.reports_recent.view_id, REPORTS_VIEW_ID)
        self.assertEqual(
            registry.reports_recent.database_id, DATABASE_IDS["reports"]
        )
        self.assertEqual(registry.reports.data_source_id, REPORTS_ID)
        self.assertEqual(registry.to_mapping(), FIXTURE)
        self.assertEqual(validate_registry(FIXTURE), FIXTURE)

        with self.assertRaises(FrozenInstanceError):
            registry.market_sources.vix_spreadsheet.public_csv_url = "changed"

    def test_rejects_v1_or_missing_market_source_registry(self) -> None:
        legacy = copy.deepcopy(FIXTURE)
        legacy["schemaVersion"] = "notion-native-v1"
        with self.assertRaisesRegex(ValueError, "notion-native-v2"):
            Registry.from_mapping(legacy)

        missing = copy.deepcopy(FIXTURE)
        del missing["marketSources"]
        with self.assertRaisesRegex(ValueError, "registry keys"):
            Registry.from_mapping(missing)

    def test_rejects_substituted_or_noncanonical_vix_spreadsheet_urls(self) -> None:
        invalid_urls = (
            VIX_PUBLIC_CSV_URL.replace("docs.google.com", "sheets.google.com"),
            VIX_PUBLIC_CSV_URL.replace(
                "https://", "https://user:password@", 1
            ),
            VIX_PUBLIC_CSV_URL + "#sheet",
            VIX_PUBLIC_CSV_URL.replace("docs.google.com", "docs.google.com:443"),
            VIX_PUBLIC_CSV_URL + "&gid=1",
            VIX_PUBLIC_CSV_URL + "&source=world-memory",
            VIX_PUBLIC_CSV_URL.replace("format=csv", "format=xlsx"),
            VIX_PUBLIC_CSV_URL.replace("gid=0", "gid=not-a-number"),
            VIX_PUBLIC_CSV_URL.replace(
                "15xqjZq8di2UqrePpYR_p72j5FCj-WTEDC4rdjZSqc_w",
                "substituted-sheet-id",
            ),
            VIX_PUBLIC_CSV_URL.replace("/export?", "/edit?"),
        )
        for url in invalid_urls:
            with self.subTest(url=url):
                broken = copy.deepcopy(FIXTURE)
                broken["marketSources"]["vixSpreadsheet"]["publicCsvUrl"] = url
                with self.assertRaises(ValueError):
                    Registry.from_mapping(broken)

    def test_rejects_missing_reordered_or_extra_vix_symbols(self) -> None:
        invalid_symbols = (
            ["VIX9D", "VIX", "VIX3M"],
            ["VIX", "VIX9D", "VIX3M", "VIX6M"],
            ["VIX9D", "VIX", "VIX3M", "VIX6M", "VVIX"],
        )
        for symbols in invalid_symbols:
            with self.subTest(symbols=symbols):
                broken = copy.deepcopy(FIXTURE)
                broken["marketSources"]["vixSpreadsheet"][
                    "expectedSymbols"
                ] = symbols
                with self.assertRaisesRegex(ValueError, "expectedSymbols"):
                    Registry.from_mapping(broken)

    def test_accepts_data_source_ids_distinct_from_database_container_urls(self) -> None:
        registry = Registry.from_mapping(FIXTURE)
        locators = {
            "collections": registry.collections,
            "stories": registry.stories,
            "storyChanges": registry.story_changes,
            "reports": registry.reports,
        }

        for key, locator in locators.items():
            database_url = notion_url(DATABASE_IDS[key])
            self.assertEqual(
                notion_page_id_from_url(database_url), DATABASE_IDS[key]
            )
            self.assertNotEqual(locator.data_source_id, DATABASE_IDS[key])
            self.assertFalse(hasattr(locator, "url"))

    def test_rejects_legacy_or_extra_registry_fields(self) -> None:
        with self.assertRaisesRegex(ValueError, "registry keys"):
            Registry.from_mapping({**FIXTURE, "installation": {}})

    def test_rejects_non_notion_urls_and_mismatched_hub_page_ids(self) -> None:
        broken = copy.deepcopy(FIXTURE)
        broken["hub"]["url"] = "https://example.com/notion-page"
        with self.assertRaisesRegex(ValueError, "Notion URL"):
            Registry.from_mapping(broken)

        broken = copy.deepcopy(FIXTURE)
        broken["hub"]["url"] = notion_url(STORIES_ID)
        with self.assertRaisesRegex(ValueError, "does not match"):
            Registry.from_mapping(broken)

    def test_normalizes_uuids_and_rejects_boolean_strings(self) -> None:
        value = copy.deepcopy(FIXTURE)
        value["workspaceId"] = WORKSPACE_ID.replace("-", "").upper()
        value["reports"]["dataSourceId"] = REPORTS_ID.replace("-", "").upper()
        normalized = Registry.from_mapping(value).to_mapping()
        self.assertEqual(normalized, FIXTURE)

        value = copy.deepcopy(FIXTURE)
        value["workspaceId"] = True
        with self.assertRaisesRegex(ValueError, "workspaceId"):
            Registry.from_mapping(value)

    def test_rejects_wrong_locator_shape(self) -> None:
        value = copy.deepcopy(FIXTURE)
        value["hub"]["dataSourceId"] = HUB_ID
        del value["hub"]["pageId"]
        with self.assertRaisesRegex(ValueError, "locator keys"):
            Registry.from_mapping(value)

        for extra_key, extra_value in (
            ("url", notion_url(DATABASE_IDS["reports"])),
            ("databaseId", DATABASE_IDS["reports"]),
        ):
            with self.subTest(extra_key=extra_key):
                value = copy.deepcopy(FIXTURE)
                value["reports"][extra_key] = extra_value
                with self.assertRaisesRegex(ValueError, "locator keys"):
                    Registry.from_mapping(value)

    def test_rejects_missing_or_ambiguous_view_locators(self) -> None:
        missing = copy.deepcopy(FIXTURE)
        del missing["views"]
        with self.assertRaisesRegex(ValueError, "registry keys"):
            Registry.from_mapping(missing)

        cases = (
            "https://example.com/p/"
            + DATABASE_IDS["reports"].replace("-", "")
            + "?v="
            + REPORTS_VIEW_ID,
            notion_view_url(DATABASE_IDS["reports"], REPORTS_VIEW_ID) + "&pvs=4",
            "https://app.notion.com/p/"
            + DATABASE_IDS["reports"].replace("-", "")
            + "?v=not-a-uuid",
            notion_view_url(DATABASE_IDS["reports"], REPORTS_VIEW_ID) + "#fragment",
        )
        for url in cases:
            with self.subTest(url=url):
                broken = copy.deepcopy(FIXTURE)
                broken["views"]["reportsRecent"]["url"] = url
                with self.assertRaises(ValueError):
                    Registry.from_mapping(broken)

        broken = copy.deepcopy(FIXTURE)
        broken["views"]["reportsRecent"]["viewId"] = REPORTS_VIEW_ID
        with self.assertRaisesRegex(ValueError, "view"):
            Registry.from_mapping(broken)

    def test_accepts_current_first_party_notion_com_page_domains(self) -> None:
        value = copy.deepcopy(FIXTURE)
        value["hub"]["url"] = (
            "https://app.notion.com/p/World-Memory-" + HUB_ID.replace("-", "")
        )

        registry = Registry.from_mapping(value)

        self.assertEqual(registry.hub.url, value["hub"]["url"])

    def test_rejects_credentials_on_current_first_party_notion_urls(self) -> None:
        value = copy.deepcopy(FIXTURE)
        value["hub"]["url"] = (
            "https://user:password@app.notion.com/p/World-Memory-"
            + HUB_ID.replace("-", "")
        )

        with self.assertRaisesRegex(ValueError, "credentials"):
            Registry.from_mapping(value)

    def test_rejects_a_page_url_with_the_same_uuid_repeated(self) -> None:
        value = copy.deepcopy(FIXTURE)
        compact_id = HUB_ID.replace("-", "")
        value["hub"]["url"] = (
            f"https://app.notion.com/p/World-Memory-{compact_id}-{compact_id}"
        )

        with self.assertRaisesRegex(ValueError, "one page UUID"):
            Registry.from_mapping(value)


if __name__ == "__main__":
    unittest.main()
