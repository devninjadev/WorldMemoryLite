"""Contract tests for readable Notion-native create and update requests."""

from __future__ import annotations

import copy
from datetime import datetime
import unittest

from world_memory.feed import FeedItem, FeedOutcome, normalize_feed_summary
from world_memory.market import MarketSnapshot, ProviderResult
from world_memory.notion_payloads import (
    collection_pages,
    collection_page,
    report_page,
    story_change_page,
    story_page,
    story_update,
)
from world_memory.registry import Registry
from world_memory.windows import Window


WORKSPACE_ID = "11111111-1111-4111-8111-111111111111"
HUB_ID = "22222222-2222-4222-8222-222222222222"
COLLECTIONS_ID = "33333333-3333-4333-8333-333333333333"
STORIES_ID = "44444444-4444-4444-8444-444444444444"
STORY_CHANGES_ID = "55555555-5555-4555-8555-555555555555"
REPORTS_ID = "66666666-6666-4666-8666-666666666666"
COLLECTION_ID = "77777777-7777-4777-8777-777777777777"
STORY_ID = "88888888-8888-4888-8888-888888888888"
RELATED_STORY_ID = "99999999-9999-4999-8999-999999999999"
REPORT_ID = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
REPORTS_VIEW_ID = "abababab-abab-4bab-8bab-abababababab"
STORIES_VIEW_ID = "bcbcbcbc-bcbc-4bcb-8bcb-bcbcbcbcbcbc"
REPORTS_DATABASE_ID = "cdcdcdcd-cdcd-4dcd-8dcd-cdcdcdcdcdcd"
STORIES_DATABASE_ID = "dededede-dede-4ede-8ede-dededededede"
VIX_PUBLIC_CSV_URL = (
    "https://docs.google.com/spreadsheets/d/"
    "15xqjZq8di2UqrePpYR_p72j5FCj-WTEDC4rdjZSqc_w/export?format=csv&gid=0"
)


def notion_url(identifier: str) -> str:
    return "https://www.notion.so/World-Memory-" + identifier.replace("-", "")


REGISTRY = Registry.from_mapping(
    {
        "schemaVersion": "notion-native-v2",
        "workspaceId": WORKSPACE_ID,
        "hub": {"pageId": HUB_ID, "url": notion_url(HUB_ID)},
        "collections": {"dataSourceId": COLLECTIONS_ID},
        "stories": {"dataSourceId": STORIES_ID},
        "storyChanges": {"dataSourceId": STORY_CHANGES_ID},
        "reports": {"dataSourceId": REPORTS_ID},
        "views": {
            "reportsRecent": {
                "url": f"https://app.notion.com/p/{REPORTS_DATABASE_ID.replace('-', '')}?v={REPORTS_VIEW_ID.replace('-', '')}"
            },
            "storiesCurrent": {
                "url": f"https://app.notion.com/p/{STORIES_DATABASE_ID.replace('-', '')}?v={STORIES_VIEW_ID.replace('-', '')}"
            },
        },
        "marketSources": {
            "vixSpreadsheet": {
                "publicCsvUrl": VIX_PUBLIC_CSV_URL,
                "expectedSymbols": ["VIX9D", "VIX", "VIX3M", "VIX6M"],
            }
        },
    }
)


def dt(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


WINDOW = Window(dt("2026-08-14T00:00:00Z"), dt("2026-08-14T03:00:00Z"))
ITEM = FeedItem(
    item_id="item-1",
    source_id="reuters",
    source_name="Reuters Business",
    title="[Markets] *jump*",
    url="https://example.com/article?sector=macro",
    published_at="2026-08-14T01:15:00Z",
    summary="Stocks rose while rates fell.",
)
OUTCOMES = (
    FeedOutcome("reuters", "Reuters Business", "ok", (ITEM,), "", False),
    FeedOutcome(
        "wire-failure",
        "Wire Failure",
        "error",
        (),
        "feed_fetch_timeouterror",
        True,
    ),
)
MARKET = MarketSnapshot(
    "partial",
    (
        ProviderResult("google-finance", "ok", {"SPY": 651.2}, ""),
        ProviderResult("cboe", "error", {}, "market_provider_error", "fetch"),
    ),
    {"SPY": 651.2},
    ("cboe: market_provider_error",),
)
PLAN = {
    "report": {
        "type": "world-memory",
        "stance": "neutral",
        "confidence": "medium",
        "dataQuality": "partial",
        "dataGaps": ["Cboe unavailable"],
        "markdown": (
            "# 🌍 변동성은 낮지만 경계는 남아 있다\n\n"
            "## Key Takeaway\n\n금리와 주가의 엇갈린 신호를 점검한다.\n\n"
            "## 시장 현황\n\n주식과 금리를 함께 본다.\n\n"
            "## 중장기 맥락\n\n정책 경로를 추적한다.\n\n"
            "## 주요 지표들\n\n변동성 지표를 확인한다.\n\n"
            "## 지켜봐야 할 것들\n\n다음 발표를 본다.\n\n"
            "## 관심을 가져볼 만한 이슈들\n\n전파 경로를 살핀다.\n\n"
            "## 출처·데이터 안내\n\n확인된 출처만 사용한다."
        ),
    },
    "storyDecisions": [],
    "evidenceClusters": [
        {
            "clusterId": "cluster-1",
            "importance": "high",
            "evidenceItemIds": ["item-1"],
            "reportSections": ["key-takeaway", "market-status"],
            "storyLocators": [],
        }
    ],
}
NOW = dt("2026-08-14T03:30:00Z")
DECISION = {
    "action": "create",
    "storyLocator": "",
    "name": "US rates reprice risk assets",
    "status": "active",
    "category": "rates",
    "regions": ["US", "GLOBAL"],
    "changeType": "reframed",
    "direction": "reframes",
    "importance": "high",
    "confidence": "medium",
    "currentView": "Rates remain the dominant transmission channel.",
    "storyMarkdown": (
        "# 현재 판단\n\n금리가 위험자산의 재평가를 주도한다.\n\n"
        "## 전파 경로\n\n국채 금리에서 주식 밸류에이션으로 이어진다."
    ),
    "changeMarkdown": (
        "# 무엇이 바뀌었나\n\n전파 경로의 중심이 실적에서 금리로 이동했다.\n\n"
        "## 왜 바뀌었나\n\n새 근거가 금리 민감도를 높였다."
    ),
    "relatedStoryLocators": [RELATED_STORY_ID],
    "evidenceItemIds": ["item-1"],
}


class CollectionPayloadTests(unittest.TestCase):
    def test_large_collection_is_split_into_sequential_page_requests(self) -> None:
        items = tuple(
            FeedItem(
                item_id=f"item-{index}",
                source_id="reuters",
                source_name="Reuters Business",
                title=f"Headline {index}",
                url=f"https://example.com/article-{index}",
                published_at="2026-08-14T01:15:00Z",
                summary=f"Summary {index}",
            )
            for index in range(101)
        )
        outcomes = (FeedOutcome("reuters", "Reuters Business", "ok", items, "", False),)

        requests = collection_pages(REGISTRY, WINDOW, outcomes, MARKET)

        self.assertEqual(len(requests), 3)
        self.assertEqual(
            [request["pages"][0]["properties"]["Item Count"] for request in requests],
            [50, 50, 1],
        )
        self.assertEqual(
            [request["pages"][0]["properties"]["Name"] for request in requests],
            [
                "Collection · 2026-08-14 09:00–12:00 KST · 1/3",
                "Collection · 2026-08-14 09:00–12:00 KST · 2/3",
                "Collection · 2026-08-14 09:00–12:00 KST · 3/3",
            ],
        )
        combined = "\n".join(request["pages"][0]["content"] for request in requests)
        for index in range(101):
            self.assertEqual(combined.count(f"### Headline {index}\n"), 1)

    def test_collection_is_plain_markdown_grouped_by_source(self) -> None:
        payload = collection_page(REGISTRY, WINDOW, OUTCOMES, MARKET)
        page = payload["pages"][0]

        self.assertEqual(payload["parent"], {"data_source_id": COLLECTIONS_ID})
        self.assertTrue(page["content"].startswith("<empty-block/>\n# 수집 개요"))
        self.assertIn("## Reuters Business", page["content"])
        self.assertIn("### \\[Markets\\] \\*jump\\*", page["content"])
        self.assertIn(
            "- URL: [기사 원문](https://example.com/article?sector=macro)",
            page["content"],
        )
        self.assertIn("## Wire Failure", page["content"])
        self.assertIn("수집 실패", page["content"])
        self.assertIn("## 시장 데이터", page["content"])
        self.assertIn("SPY: 651.2", page["content"])
        self.assertIn("cboe: 수집 실패", page["content"])
        self.assertNotIn("```json", page["content"])
        self.assertNotIn("Payload Digest", repr(page))
        self.assertNotIn("# Collection ·", page["content"])

    def test_collection_renders_not_attempted_market_provider_without_false_failure(self) -> None:
        market = MarketSnapshot(
            "partial",
            (
                ProviderResult("google-finance", "not-attempted", {}, ""),
                ProviderResult("spreadsheet", "ok", {"VIX": 14.58}, ""),
                ProviderResult(
                    "cboe", "error", {}, "market_provider_error", "fetch"
                ),
            ),
            {"VIX": 14.58},
            ("cboe: market_provider_error",),
        )

        content = collection_page(REGISTRY, WINDOW, OUTCOMES, market)["pages"][0][
            "content"
        ]

        self.assertIn("google-finance: 시도하지 않음", content)
        self.assertNotIn("google-finance: 수집 실패", content)
        self.assertIn("VIX: 14.58", content)
        self.assertIn("cboe: 수집 실패", content)

    def test_collection_rejects_noncanonical_provider_stages(self) -> None:
        malformed = (
            MarketSnapshot(
                "ok",
                (
                    ProviderResult(
                        "google-finance", "ok", {"SPY": 651.2}, "", "fetch"
                    ),
                ),
                {"SPY": 651.2},
                (),
            ),
            MarketSnapshot(
                "unavailable",
                (
                    ProviderResult(
                        "cboe", "error", {}, "market_provider_error", ""
                    ),
                ),
                {},
                ("cboe: market_provider_error",),
            ),
            MarketSnapshot(
                "unavailable",
                (
                    ProviderResult(
                        "cboe", "error", {}, "market_provider_error", "transform"
                    ),
                ),
                {},
                ("cboe: market_provider_error",),
            ),
        )

        for market in malformed:
            with self.subTest(provider=market.providers[0]):
                with self.assertRaisesRegex(ValueError, "market"):
                    collection_page(REGISTRY, WINDOW, OUTCOMES, market)

    def test_collection_never_receives_text_released_by_a_mismatched_blocked_close(self) -> None:
        summary = normalize_feed_summary(
            "<iframe>secret</object>LEAKED INSTRUCTION</iframe>"
        )
        item = FeedItem(
            item_id="mismatched-close",
            source_id="reuters",
            source_name="Reuters Business",
            title="Safe title",
            url="https://example.com/safe",
            published_at="2026-08-14T01:15:00Z",
            summary=summary,
        )
        outcomes = (
            FeedOutcome("reuters", "Reuters Business", "ok", (item,), "", False),
        )

        content = collection_page(REGISTRY, WINDOW, outcomes, MARKET)["pages"][0][
            "content"
        ]

        self.assertNotIn("LEAKED INSTRUCTION", content)

    def test_collection_never_receives_text_from_crossed_blocked_subtrees(self) -> None:
        summary = normalize_feed_summary(
            "<p>Visible before</p><script> hidden one <style>hidden two</script>"
            " BLOCKED TEXT LEAK </style><p>Visible after</p>"
        )
        item = FeedItem(
            item_id="crossed-blocked-subtrees",
            source_id="reuters",
            source_name="Reuters Business",
            title="Safe title",
            url="https://example.com/safe",
            published_at="2026-08-14T01:15:00Z",
            summary=summary,
        )
        outcomes = (FeedOutcome("reuters", "Reuters Business", "ok", (item,), "", False),)

        content = collection_page(REGISTRY, WINDOW, outcomes, MARKET)["pages"][0]["content"]

        self.assertIn("Visible before Visible after", content)
        self.assertNotIn("BLOCKED TEXT LEAK", content)
        self.assertNotIn("secret", content)

    def test_collection_properties_are_exact_and_dates_use_flattened_connector_keys(self) -> None:
        properties = collection_page(REGISTRY, WINDOW, OUTCOMES, MARKET)["pages"][0][
            "properties"
        ]

        self.assertEqual(
            properties,
            {
                "Name": "Collection · 2026-08-14 09:00–12:00 KST",
                "date:Window Start:start": "2026-08-14T00:00:00Z",
                "date:Window Start:is_datetime": 1,
                "date:Window End:start": "2026-08-14T03:00:00Z",
                "date:Window End:is_datetime": 1,
                "Feed Success Count": 1,
                "Feed Failure Count": 1,
                "Item Count": 1,
                "Market Data Status": "partial",
                "Data Gaps": (
                    "Wire Failure: feed_fetch_timeouterror; "
                    "cboe: market_provider_error"
                ),
            },
        )
        self.assertNotIn("Window Start", properties)
        self.assertNotIn("Window End", properties)

    def test_collection_window_dates_are_whole_utc_minutes(self) -> None:
        window = Window(
            dt("2026-08-14T00:00:59.999999Z"),
            dt("2026-08-14T03:00:28.123456Z"),
        )

        properties = collection_page(REGISTRY, window, OUTCOMES, MARKET)["pages"][0][
            "properties"
        ]

        self.assertEqual(
            properties["date:Window Start:start"], "2026-08-14T00:00:00Z"
        )
        self.assertEqual(
            properties["date:Window End:start"], "2026-08-14T03:00:00Z"
        )

    def test_collection_escapes_the_current_official_inline_control_set(self) -> None:
        injected = FeedItem(
            item_id="injected",
            source_id="reuters",
            source_name="Reuters Business",
            title=(
                "\\ *bold* ~~strike~~ `code` $x$ [label] "
                "<mention-page> {color=\"red\"} |pipe| ^caret^ snake_case"
            ),
            url="https://example.com/safe?sector=macro",
            published_at="2026-08-14T01:15:00Z",
            summary=(
                "<file src=\"https://example.com/x\">payload</file> "
                "{color=\"red\"} $y$ ~~down~~ |cell| ^up^"
            ),
        )
        outcomes = (
            FeedOutcome(
                "reuters", "Reuters Business", "ok", (injected,), "", False
            ),
        )

        content = collection_page(REGISTRY, WINDOW, outcomes, MARKET)["pages"][0][
            "content"
        ]

        for escaped in (
            r"\\",
            r"\*bold\*",
            r"\~\~strike\~\~",
            r"\`code\`",
            r"\$x\$",
            r"\[label\]",
            r"\<mention-page\>",
            r'\{color="red"\}',
            r"\|pipe\|",
            r"\^caret\^",
            r'\<file src="https://example.com/x"\>',
        ):
            with self.subTest(escaped=escaped):
                self.assertIn(escaped, content)
        self.assertIn("snake_case", content)
        self.assertNotIn(r"snake\_case", content)

    def test_collection_rejects_unsafe_rendered_article_urls(self) -> None:
        for url in (
            "https://example.com/x\n\n# INJECTED",
            "https://example.com/x\r# INJECTED",
            "javascript:alert(1)",
            "https://user:password@example.com/x",
            "https://example.com/not a valid destination",
            'https://example.com/x{color="red"}',
            "https://example.com/x</callout>",
            "https://example.com/x)[evil](https://evil.example",
            "https://example.com/x\\escaped",
            "https://example.com/x`code`",
            "https://example.com/x|table",
            "https://example.com/x^equation",
            "https://example.com/(raw-parentheses)",
            'https://example.com/x"title',
            "https://example.com/%ZZ",
        ):
            with self.subTest(url=url):
                item = copy.copy(ITEM)
                object.__setattr__(item, "url", url)
                outcomes = (
                    FeedOutcome(
                        "reuters", "Reuters Business", "ok", (item,), "", False
                    ),
                )
                with self.assertRaisesRegex(ValueError, "URL"):
                    collection_page(REGISTRY, WINDOW, outcomes, MARKET)

    def test_collection_preserves_safe_url_bytes_inside_an_explicit_link(self) -> None:
        safe_url = (
            "https://example.com/~desk/$ticker/report%20one"
            "?sector=macro&literal=%7Bsafe%7D#point"
        )
        item = copy.copy(ITEM)
        object.__setattr__(item, "url", safe_url)
        outcomes = (
            FeedOutcome("reuters", "Reuters Business", "ok", (item,), "", False),
        )

        content = collection_page(REGISTRY, WINDOW, outcomes, MARKET)["pages"][0][
            "content"
        ]

        self.assertIn(f"- URL: [기사 원문]({safe_url})", content)
        self.assertEqual(content.count(safe_url), 1)
        self.assertNotIn(f"- URL: {safe_url}", content)

    def test_collection_renders_each_retained_occurrence_exactly_once(self) -> None:
        repeated = (
            FeedOutcome(
                "reuters", "Reuters Business", "ok", (ITEM, ITEM), "", False
            ),
        )

        page = collection_page(REGISTRY, WINDOW, repeated, MARKET)["pages"][0]

        self.assertEqual(page["properties"]["Item Count"], 1)
        self.assertEqual(page["content"].count("### \\[Markets\\] \\*jump\\*"), 1)


class ReportPayloadTests(unittest.TestCase):
    def test_report_uses_official_create_wrapper_and_readable_markdown(self) -> None:
        payload = report_page(
            REGISTRY,
            WINDOW,
            PLAN,
            relations={"Collection": [COLLECTION_ID], "Stories": [STORY_ID]},
        )

        self.assertEqual(payload["parent"], {"data_source_id": REPORTS_ID})
        self.assertEqual(len(payload["pages"]), 1)
        self.assertEqual(
            payload["pages"][0]["content"],
            "<empty-block/>\n" + PLAN["report"]["markdown"],
        )
        self.assertNotIn("# World Memory ·", payload["pages"][0]["content"])

    def test_report_properties_are_exact_and_dates_use_flattened_connector_keys(self) -> None:
        properties = report_page(
            REGISTRY,
            WINDOW,
            PLAN,
            relations={"Collection": [COLLECTION_ID], "Stories": [STORY_ID]},
        )["pages"][0]["properties"]

        self.assertEqual(
            properties,
            {
                "Name": "World Memory · 2026-08-14 09:00–12:00 KST",
                "Report Type": "world-memory",
                "date:Window Start:start": "2026-08-14T00:00:00Z",
                "date:Window Start:is_datetime": 1,
                "date:Window End:start": "2026-08-14T03:00:00Z",
                "date:Window End:is_datetime": 1,
                "Stance": "neutral",
                "Confidence": "medium",
                "Data Quality": "partial",
                "Data Gaps": "Cboe unavailable",
                "Collection": [COLLECTION_ID],
                "Stories": [STORY_ID],
            },
        )

    def test_report_window_dates_are_whole_utc_minutes(self) -> None:
        window = Window(
            dt("2026-08-14T00:00:59.999999Z"),
            dt("2026-08-14T03:00:28.123456Z"),
        )

        properties = report_page(
            REGISTRY,
            window,
            PLAN,
            relations={"Collection": [COLLECTION_ID], "Stories": [STORY_ID]},
        )["pages"][0]["properties"]

        self.assertEqual(
            properties["date:Window Start:start"], "2026-08-14T00:00:00Z"
        )
        self.assertEqual(
            properties["date:Window End:start"], "2026-08-14T03:00:00Z"
        )


class StoryPayloadTests(unittest.TestCase):
    def test_story_create_uses_exact_properties_and_flattened_dates(self) -> None:
        payload = story_page(REGISTRY, DECISION, NOW)
        page = payload["pages"][0]

        self.assertEqual(payload["parent"], {"data_source_id": STORIES_ID})
        self.assertEqual(page["content"], "<empty-block/>\n" + DECISION["storyMarkdown"])
        self.assertEqual(
            page["properties"],
            {
                "Name": "US rates reprice risk assets",
                "Status": "active",
                "Category": "rates",
                "Regions": ["US", "GLOBAL"],
                "Importance": "high",
                "Confidence": "medium",
                "Current View": "Rates remain the dominant transmission channel.",
                "date:First Seen:start": "2026-08-14T03:30:00Z",
                "date:First Seen:is_datetime": 1,
                "date:Last Evidence At:start": "2026-08-14T03:30:00Z",
                "date:Last Evidence At:is_datetime": 1,
                "date:Last Updated:start": "2026-08-14T03:30:00Z",
                "date:Last Updated:is_datetime": 1,
                "Related Stories": [RELATED_STORY_ID],
            },
        )
        for logical_date in ("First Seen", "Last Evidence At", "Last Updated"):
            self.assertNotIn(logical_date, page["properties"])

    def test_story_update_declares_ordered_property_then_content_commands(self) -> None:
        decision = copy.deepcopy(DECISION)
        decision["action"] = "update"
        decision["storyLocator"] = STORY_ID

        payload = story_update(STORY_ID, decision, NOW)

        self.assertEqual(
            payload,
            {
                "steps": [
                    {
                        "page_id": STORY_ID,
                        "command": "update_properties",
                        "properties": {
                            "Name": "US rates reprice risk assets",
                            "Status": "active",
                            "Category": "rates",
                            "Regions": ["US", "GLOBAL"],
                            "Importance": "high",
                            "Confidence": "medium",
                            "Current View": "Rates remain the dominant transmission channel.",
                            "date:Last Evidence At:start": "2026-08-14T03:30:00Z",
                            "date:Last Evidence At:is_datetime": 1,
                            "date:Last Updated:start": "2026-08-14T03:30:00Z",
                            "date:Last Updated:is_datetime": 1,
                            "Related Stories": [RELATED_STORY_ID],
                        },
                    },
                    {
                        "page_id": STORY_ID,
                        "command": "replace_content",
                        "new_str": "<empty-block/>\n" + DECISION["storyMarkdown"],
                    },
                ]
            },
        )
        self.assertNotIn("date:First Seen:start", payload["steps"][0]["properties"])

    def test_story_update_clears_relations_absent_from_the_current_projection(self) -> None:
        decision = copy.deepcopy(DECISION)
        decision["action"] = "update"
        decision["storyLocator"] = STORY_ID
        decision["relatedStoryLocators"] = []

        properties = story_update(STORY_ID, decision, NOW)["steps"][0]["properties"]

        self.assertEqual(properties["Related Stories"], [])

    def test_story_update_binds_and_normalizes_the_validated_story_locator(self) -> None:
        decision = copy.deepcopy(DECISION)
        decision["action"] = "update"
        decision["storyLocator"] = STORY_ID

        payload = story_update(STORY_ID.replace("-", "").upper(), decision, NOW)

        self.assertEqual(payload["steps"][0]["page_id"], STORY_ID)
        self.assertEqual(payload["steps"][1]["page_id"], STORY_ID)

        with self.assertRaisesRegex(ValueError, "storyLocator"):
            story_update(
                "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
                decision,
                NOW,
            )

    def test_story_change_uses_only_confirmed_relations_and_human_markdown(self) -> None:
        payload = story_change_page(
            REGISTRY,
            DECISION,
            NOW,
            {"primaryStory": STORY_ID, "report": REPORT_ID},
        )
        page = payload["pages"][0]
        properties = page["properties"]

        self.assertEqual(payload["parent"], {"data_source_id": STORY_CHANGES_ID})
        self.assertEqual(properties["Change Type"], "reframed")
        self.assertEqual(properties["Primary Story"], [STORY_ID])
        self.assertEqual(properties["Related Report"], [REPORT_ID])
        self.assertNotIn("Related Story", properties)
        self.assertNotIn("Related Collection", properties)
        self.assertEqual(properties["date:Observed At:start"], "2026-08-14T03:30:00Z")
        self.assertEqual(properties["date:Observed At:is_datetime"], 1)
        self.assertNotIn("Observed At", properties)
        self.assertEqual(page["content"], "<empty-block/>\n" + DECISION["changeMarkdown"])
        self.assertIn("# 무엇이 바뀌었나", page["content"])
        self.assertNotIn("# US rates reprice risk assets", page["content"])

    def test_story_change_maps_each_explicit_confirmed_relation(self) -> None:
        properties = story_change_page(
            REGISTRY,
            DECISION,
            NOW,
            {
                "primaryStory": STORY_ID,
                "relatedStory": RELATED_STORY_ID,
                "report": REPORT_ID,
                "collection": COLLECTION_ID,
            },
        )["pages"][0]["properties"]

        self.assertEqual(properties["Related Story"], [RELATED_STORY_ID])
        self.assertEqual(properties["Related Report"], [REPORT_ID])
        self.assertEqual(properties["Related Collection"], [COLLECTION_ID])

    def test_story_change_properties_are_exact(self) -> None:
        properties = story_change_page(
            REGISTRY,
            DECISION,
            NOW,
            {
                "primaryStory": STORY_ID,
                "relatedStory": RELATED_STORY_ID,
                "report": REPORT_ID,
                "collection": COLLECTION_ID,
            },
        )["pages"][0]["properties"]

        self.assertEqual(
            properties,
            {
                "Name": "US rates reprice risk assets · reframed · 2026-08-14",
                "date:Observed At:start": "2026-08-14T03:30:00Z",
                "date:Observed At:is_datetime": 1,
                "Change Type": "reframed",
                "Direction": "reframes",
                "Strength": "high",
                "Confidence": "medium",
                "Primary Story": [STORY_ID],
                "Related Story": [RELATED_STORY_ID],
                "Related Report": [REPORT_ID],
                "Related Collection": [COLLECTION_ID],
            },
        )

    def test_story_change_requires_a_confirmed_primary_story_id(self) -> None:
        for relations in ({}, {"report": REPORT_ID}, {"primaryStory": ""}):
            with self.subTest(relations=relations):
                with self.assertRaisesRegex(ValueError, "primaryStory"):
                    story_change_page(REGISTRY, DECISION, NOW, relations)

        with self.assertRaisesRegex(ValueError, "relation"):
            story_change_page(
                REGISTRY,
                DECISION,
                NOW,
                {"primaryStory": STORY_ID, "unconfirmedStory": RELATED_STORY_ID},
            )

    def test_story_change_primary_is_one_normalized_page_uuid(self) -> None:
        normalized = story_change_page(
            REGISTRY,
            DECISION,
            NOW,
            {"primaryStory": STORY_ID.replace("-", "").upper()},
        )["pages"][0]["properties"]
        self.assertEqual(normalized["Primary Story"], [STORY_ID])

        for primary in (
            "not-a-page-id",
            f" {STORY_ID} ",
            [STORY_ID, RELATED_STORY_ID],
            [STORY_ID, STORY_ID],
        ):
            with self.subTest(primary=primary):
                with self.assertRaisesRegex(ValueError, "primaryStory"):
                    story_change_page(
                        REGISTRY,
                        DECISION,
                        NOW,
                        {"primaryStory": primary},
                    )

    def test_update_story_change_primary_matches_the_validated_story_locator(self) -> None:
        decision = copy.deepcopy(DECISION)
        decision["action"] = "update"
        decision["storyLocator"] = STORY_ID

        payload = story_change_page(
            REGISTRY,
            decision,
            NOW,
            {"primaryStory": STORY_ID},
        )
        self.assertEqual(
            payload["pages"][0]["properties"]["Primary Story"], [STORY_ID]
        )

        with self.assertRaisesRegex(ValueError, "primaryStory.*storyLocator"):
            story_change_page(
                REGISTRY,
                decision,
                NOW,
                {"primaryStory": RELATED_STORY_ID},
            )

    def test_all_relation_fields_require_and_normalize_page_uuids(self) -> None:
        report_properties = report_page(
            REGISTRY,
            WINDOW,
            PLAN,
            relations={"Collection": [COLLECTION_ID.replace("-", "").upper()]},
        )["pages"][0]["properties"]
        self.assertEqual(report_properties["Collection"], [COLLECTION_ID])

        bad_decision = copy.deepcopy(DECISION)
        bad_decision["relatedStoryLocators"] = ["not-a-page-id"]
        with self.assertRaisesRegex(ValueError, "relatedStoryLocators"):
            story_page(REGISTRY, bad_decision, NOW)

        with self.assertRaisesRegex(ValueError, "relations.Collection"):
            report_page(
                REGISTRY,
                WINDOW,
                PLAN,
                relations={"Collection": ["not-a-page-id"]},
            )

    def test_scheduled_story_builders_reject_unknown_change_types_and_merge_split(self) -> None:
        unknown = copy.deepcopy(DECISION)
        unknown["changeType"] = "rewritten"
        with self.assertRaisesRegex(ValueError, "changeType"):
            story_change_page(
                REGISTRY, unknown, NOW, {"primaryStory": STORY_ID}
            )

        for action in ("merge", "split"):
            with self.subTest(action=action):
                forbidden = copy.deepcopy(DECISION)
                forbidden["action"] = action
                with self.assertRaisesRegex(ValueError, "action"):
                    story_page(REGISTRY, forbidden, NOW)
                with self.assertRaisesRegex(ValueError, "action"):
                    story_change_page(
                        REGISTRY, forbidden, NOW, {"primaryStory": STORY_ID}
                    )

    def test_direct_story_builders_reject_values_outside_task1_enums(self) -> None:
        cases = (
            ("status", "invented-status"),
            ("category", "invented-category"),
            ("regions", ["MARS"]),
        )
        for field, value in cases:
            with self.subTest(field=field):
                decision = copy.deepcopy(DECISION)
                decision[field] = value
                with self.assertRaisesRegex(ValueError, field):
                    story_page(REGISTRY, decision, NOW)


if __name__ == "__main__":
    unittest.main()
