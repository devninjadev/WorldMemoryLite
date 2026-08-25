"""Contract tests for write outcomes and graceful user-visible degradation."""

from __future__ import annotations

import unittest

from world_memory.feed import FEEDS, FeedOutcome
from world_memory.market import MarketSnapshot, ProviderResult
from world_memory.workflow import WriteOutcome, build_user_result, resolve_write_response


COLLECTION_ID = "77777777-7777-4777-8777-777777777777"
REPORT_ID = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
COLLECTION_URL = (
    "https://www.notion.so/World-Memory-" + COLLECTION_ID.replace("-", "")
)
REPORT_URL = "https://www.notion.so/World-Memory-" + REPORT_ID.replace("-", "")
REPORT_APP_URL = "https://app.notion.com/p/World-Memory-" + REPORT_ID.replace("-", "")
REPORT_WWW_COM_URL = (
    "https://www.notion.com/World-Memory-" + REPORT_ID.replace("-", "")
)
REPORT_MARKDOWN = "# 한눈에 보기\n\n금리와 주가의 엇갈린 신호를 점검한다."
ALL_OK_OUTCOMES = tuple(
    FeedOutcome(feed.id, feed.name, "ok", (), "", False) for feed in FEEDS
)
OUTCOMES = ALL_OK_OUTCOMES[:-1] + (
    FeedOutcome(
        FEEDS[-1].id,
        FEEDS[-1].name,
        "error",
        (),
        "feed_fetch_timeouterror",
        True,
    ),
)
ALL_FAILED_OUTCOMES = tuple(
    FeedOutcome(feed.id, feed.name, "error", (), "feed_fetch_error", True)
    for feed in FEEDS
)
MARKET_OK = MarketSnapshot(
    "ok",
    (ProviderResult("google-finance", "ok", {"SPY": 651.2}, ""),),
    {"SPY": 651.2},
    (),
)
MARKET_PARTIAL = MarketSnapshot(
    "partial",
    (
        ProviderResult("google-finance", "ok", {"SPY": 651.2}, ""),
        ProviderResult("cboe", "error", {}, "market_provider_error", "fetch"),
    ),
    {"SPY": 651.2},
    ("cboe: market_provider_error",),
)


class WriteResponseTests(unittest.TestCase):
    def test_sync_success_needs_no_readback(self) -> None:
        outcome = resolve_write_response(
            "report", {"pages": [{"id": REPORT_ID, "url": REPORT_URL}]}
        )

        self.assertEqual(outcome, WriteOutcome("report", "confirmed", REPORT_URL, ""))

    def test_update_page_success_accepts_the_returned_page_locator(self) -> None:
        outcome = resolve_write_response(
            "story", {"id": REPORT_ID, "url": REPORT_URL}
        )

        self.assertEqual(outcome.status, "confirmed")
        self.assertEqual(outcome.locator, REPORT_URL)
        self.assertEqual(outcome.warning, "")

    def test_uncertain_response_with_locator_requests_one_exact_fetch_only(self) -> None:
        outcome = resolve_write_response(
            "collection", {"status": "timeout", "page_id": COLLECTION_ID}
        )

        self.assertEqual(outcome.status, "verify-once")
        self.assertEqual(outcome.locator, COLLECTION_ID)
        self.assertIn("fetch", outcome.warning)
        self.assertIn("do not retry", outcome.warning)
        self.assertNotEqual(outcome.status, "retry")

    def test_uncertain_or_malformed_response_without_locator_fails_closed(self) -> None:
        for response in (
            None,
            {},
            {"status": "timeout"},
            {"pages": []},
            {"error": "connector response omitted a page"},
        ):
            with self.subTest(response=response):
                outcome = resolve_write_response("report", response)
                self.assertEqual(outcome.status, "failed")
                self.assertEqual(outcome.locator, "")
                self.assertTrue(outcome.warning)

    def test_retry_is_not_a_valid_write_outcome_state(self) -> None:
        with self.assertRaisesRegex(ValueError, "status"):
            WriteOutcome("report", "retry", "", "")

    def test_async_nonterminal_and_failed_responses_never_confirm_task_ids(self) -> None:
        for status in ("queued", "running", "retrying", "failed"):
            with self.subTest(status=status):
                outcome = resolve_write_response(
                    "report",
                    {
                        "object": "async_task",
                        "id": "task_abc123",
                        "status": status,
                        "poll_after_seconds": 2,
                    },
                )

                self.assertEqual(outcome.status, "failed")
                self.assertEqual(outcome.locator, "")
                self.assertNotIn("task_abc123", repr(outcome))

    def test_async_succeeded_classifies_only_the_nested_operation_result(self) -> None:
        outcome = resolve_write_response(
            "report",
            {
                "object": "async_task",
                "id": "task_abc123",
                "status": "succeeded",
                "result": {"pages": [{"id": REPORT_ID, "url": REPORT_APP_URL}]},
            },
        )

        self.assertEqual(outcome, WriteOutcome("report", "confirmed", REPORT_APP_URL, ""))
        self.assertNotIn("task_abc123", repr(outcome))

    def test_async_succeeded_with_no_valid_nested_page_fails(self) -> None:
        for result in (
            None,
            {},
            {"id": "task_nested"},
            {"url": "https://evil.example/not-notion"},
        ):
            with self.subTest(result=result):
                outcome = resolve_write_response(
                    "report",
                    {
                        "object": "async_task",
                        "id": "task_abc123",
                        "status": "succeeded",
                        "result": result,
                    },
                )
                self.assertEqual(outcome.status, "failed")
                self.assertEqual(outcome.locator, "")

    def test_malformed_status_types_fail_without_raising(self) -> None:
        for status in ([], {}, 1, True, object()):
            with self.subTest(status_type=type(status).__name__):
                outcome = resolve_write_response(
                    "report", {"status": status, "id": REPORT_ID, "url": REPORT_URL}
                )
                self.assertEqual(outcome.status, "failed")
                self.assertEqual(outcome.locator, "")

    def test_sync_confirmation_rejects_task_ids_evil_urls_and_mismatched_pages(self) -> None:
        other_id = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
        other_url = "https://app.notion.com/p/World-Memory-" + other_id.replace("-", "")
        for response in (
            {"url": "https://evil.example/not-notion"},
            {"id": "task_abc123", "url": REPORT_URL},
            {"id": REPORT_ID, "url": "https://evil.example/not-notion"},
            {"id": REPORT_ID, "url": other_url},
            {"id": REPORT_ID, "url": f" {REPORT_URL} "},
            {
                "pages": [{"id": "task_nested"}],
                "id": REPORT_ID,
                "url": REPORT_URL,
            },
            {"status": "unexpected", "id": REPORT_ID, "url": REPORT_URL},
        ):
            with self.subTest(response=response):
                outcome = resolve_write_response("report", response)
                self.assertEqual(outcome.status, "failed")
                self.assertEqual(outcome.locator, "")

    def test_sync_confirmation_accepts_canonical_page_ids_and_current_domains(self) -> None:
        app_outcome = resolve_write_response(
            "report", {"pages": [{"id": REPORT_ID, "url": REPORT_APP_URL}]}
        )
        com_outcome = resolve_write_response(
            "report", {"id": REPORT_ID, "url": REPORT_WWW_COM_URL}
        )
        id_outcome = resolve_write_response("report", {"id": REPORT_ID})

        self.assertEqual(app_outcome.locator, REPORT_APP_URL)
        self.assertEqual(com_outcome.locator, REPORT_WWW_COM_URL)
        self.assertEqual(id_outcome.locator, REPORT_ID)
        self.assertEqual(
            (app_outcome.status, com_outcome.status, id_outcome.status),
            ("confirmed", "confirmed", "confirmed"),
        )


class UserResultTests(unittest.TestCase):
    def test_report_delivery_matrix_is_link_first_with_safe_fallbacks(self) -> None:
        cases = (
            (
                "confirmed-new-url",
                {
                    "report_markdown": REPORT_MARKDOWN,
                    "report_outcome": WriteOutcome(
                        "report", "confirmed", REPORT_URL, ""
                    ),
                    "feed_outcomes": ALL_OK_OUTCOMES,
                    "market": MARKET_OK,
                },
                ("", REPORT_URL),
            ),
            (
                "reused-url",
                {
                    "report_markdown": REPORT_MARKDOWN,
                    "report_outcome": WriteOutcome(
                        "reused", "confirmed", REPORT_URL, ""
                    ),
                    "feed_outcomes": (),
                    "market": MARKET_OK,
                },
                ("", REPORT_URL),
            ),
            (
                "degraded-confirmed-url",
                {
                    "report_markdown": REPORT_MARKDOWN,
                    "report_outcome": WriteOutcome(
                        "report", "confirmed", REPORT_URL, ""
                    ),
                    "collection_outcome": WriteOutcome(
                        "collection",
                        "failed",
                        "",
                        "collection write was not confirmed",
                    ),
                    "feed_outcomes": OUTCOMES,
                    "market": MARKET_PARTIAL,
                },
                ("", REPORT_URL),
            ),
            (
                "confirmed-uuid-only",
                {
                    "report_markdown": REPORT_MARKDOWN,
                    "report_outcome": WriteOutcome(
                        "report", "confirmed", REPORT_ID, ""
                    ),
                    "feed_outcomes": ALL_OK_OUTCOMES,
                    "market": MARKET_OK,
                },
                (REPORT_MARKDOWN, ""),
            ),
            (
                "failed",
                {
                    "report_markdown": REPORT_MARKDOWN,
                    "report_outcome": WriteOutcome(
                        "report", "failed", "", "report write was not confirmed"
                    ),
                    "feed_outcomes": OUTCOMES,
                    "market": MARKET_PARTIAL,
                },
                (REPORT_MARKDOWN, ""),
            ),
            (
                "uncertain-with-untrusted-url",
                {
                    "report_markdown": REPORT_MARKDOWN,
                    "report_outcome": WriteOutcome(
                        "report",
                        "verify-once",
                        REPORT_URL,
                        "report write is uncertain; fetch once",
                    ),
                    "feed_outcomes": OUTCOMES,
                    "market": MARKET_PARTIAL,
                },
                (REPORT_MARKDOWN, ""),
            ),
            (
                "safe-stop",
                {
                    "report_markdown": "",
                    "report_outcome": WriteOutcome(
                        "safe-stop", "failed", "", "all configured feeds failed"
                    ),
                    "feed_outcomes": ALL_FAILED_OUTCOMES,
                    "market": MARKET_PARTIAL,
                },
                ("", ""),
            ),
        )
        expected_keys = {
            "status",
            "reportMarkdown",
            "reportUrl",
            "collectionStatus",
            "feedSuccessCount",
            "feedFailureCount",
            "marketStatus",
            "storyCreatedCount",
            "storyUpdatedCount",
            "storyChangeCreatedCount",
            "warnings",
        }

        for name, kwargs, expected_pair in cases:
            with self.subTest(name=name):
                result = build_user_result(**kwargs)
                self.assertEqual(set(result), expected_keys)
                self.assertEqual(
                    (result["reportMarkdown"], result["reportUrl"]),
                    expected_pair,
                )

    def test_completed_result_includes_visible_counts_and_report_url(self) -> None:
        result = build_user_result(
            report_markdown=REPORT_MARKDOWN,
            report_outcome=WriteOutcome("report", "confirmed", REPORT_URL, ""),
            collection_outcome=WriteOutcome(
                "collection", "confirmed", COLLECTION_URL, ""
            ),
            feed_outcomes=ALL_OK_OUTCOMES,
            market=MARKET_OK,
            story_created=1,
            story_updated=2,
            changes_created=3,
        )

        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["reportMarkdown"], "")
        self.assertEqual(result["reportUrl"], REPORT_URL)
        self.assertEqual(result["collectionStatus"], "confirmed")
        self.assertEqual(result["feedSuccessCount"], 8)
        self.assertEqual(result["feedFailureCount"], 0)
        self.assertEqual(result["marketStatus"], "complete")
        self.assertEqual(result["storyCreatedCount"], 1)
        self.assertEqual(result["storyUpdatedCount"], 2)
        self.assertEqual(result["storyChangeCreatedCount"], 3)
        self.assertEqual(result["warnings"], [])

    def test_collection_failure_does_not_erase_a_confirmed_report(self) -> None:
        result = build_user_result(
            report_markdown=REPORT_MARKDOWN,
            report_outcome=WriteOutcome("report", "confirmed", REPORT_URL, ""),
            collection_outcome=WriteOutcome(
                "collection", "failed", "", "collection write was not confirmed"
            ),
            feed_outcomes=OUTCOMES,
            market=MARKET_PARTIAL,
        )

        self.assertEqual(result["status"], "degraded")
        self.assertEqual(result["reportMarkdown"], "")
        self.assertEqual(result["reportUrl"], REPORT_URL)
        self.assertEqual(result["collectionStatus"], "failed")
        self.assertEqual(result["feedSuccessCount"], 7)
        self.assertEqual(result["feedFailureCount"], 1)
        self.assertEqual(result["marketStatus"], "partial")
        self.assertIn("collection write was not confirmed", result["warnings"])

    def test_not_attempted_market_provider_preserves_partial_result_without_false_gap(self) -> None:
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

        result = build_user_result(
            report_markdown=REPORT_MARKDOWN,
            report_outcome=WriteOutcome("report", "confirmed", REPORT_URL, ""),
            feed_outcomes=ALL_OK_OUTCOMES,
            market=market,
        )

        self.assertEqual(result["status"], "degraded")
        self.assertEqual(result["marketStatus"], "partial")
        self.assertNotIn("google-finance", "\n".join(result["warnings"]))
        self.assertIn("cboe: market_provider_error", result["warnings"])

    def test_report_failure_still_returns_generated_markdown(self) -> None:
        result = build_user_result(
            report_markdown=REPORT_MARKDOWN,
            report_outcome=WriteOutcome(
                "report", "failed", "", "report write was not confirmed"
            ),
            feed_outcomes=OUTCOMES,
            market=MARKET_PARTIAL,
        )

        self.assertEqual(result["status"], "storage-failed")
        self.assertEqual(result["reportMarkdown"], REPORT_MARKDOWN)
        self.assertEqual(result["reportUrl"], "")
        self.assertIn("report write was not confirmed", result["warnings"])

    def test_reused_report_is_distinct_from_a_new_write(self) -> None:
        result = build_user_result(
            report_markdown=REPORT_MARKDOWN,
            report_outcome=WriteOutcome("reused", "confirmed", REPORT_URL, ""),
            feed_outcomes=(),
            market=MARKET_OK,
            warnings=("same-window Report reused",),
        )

        self.assertEqual(result["status"], "reused")
        self.assertEqual(result["reportMarkdown"], "")
        self.assertEqual(result["reportUrl"], REPORT_URL)
        self.assertEqual(result["warnings"], ["same-window Report reused"])

    def test_all_feed_failures_are_a_safe_stop(self) -> None:
        result = build_user_result(
            report_markdown="",
            report_outcome=WriteOutcome(
                "safe-stop", "failed", "", "all configured feeds failed"
            ),
            feed_outcomes=ALL_FAILED_OUTCOMES,
            market=MARKET_PARTIAL,
        )

        self.assertEqual(result["status"], "safe-stop")
        self.assertEqual(result["feedSuccessCount"], 0)
        self.assertEqual(result["feedFailureCount"], 8)
        self.assertIn("all configured feeds failed", result["warnings"])

    def test_non_url_report_locator_is_not_presented_as_a_report_url(self) -> None:
        result = build_user_result(
            report_markdown=REPORT_MARKDOWN,
            report_outcome=WriteOutcome("report", "confirmed", REPORT_ID, ""),
            feed_outcomes=ALL_OK_OUTCOMES,
            market=MARKET_OK,
        )

        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["reportMarkdown"], REPORT_MARKDOWN)
        self.assertEqual(result["reportUrl"], "")

    def test_rejects_outcome_kinds_in_the_wrong_roles(self) -> None:
        cases = (
            {
                "report_outcome": WriteOutcome(
                    "collection", "confirmed", REPORT_URL, ""
                ),
                "collection_outcome": None,
            },
            {
                "report_outcome": WriteOutcome(
                    "report", "confirmed", REPORT_URL, ""
                ),
                "collection_outcome": WriteOutcome(
                    "report", "confirmed", COLLECTION_URL, ""
                ),
            },
            {
                "report_outcome": WriteOutcome("reused", "failed", "", "failed"),
                "collection_outcome": None,
            },
            {
                "report_outcome": WriteOutcome(
                    "safe-stop", "confirmed", REPORT_URL, ""
                ),
                "collection_outcome": None,
            },
        )
        for case in cases:
            with self.subTest(case=case):
                with self.assertRaisesRegex(ValueError, "outcome|kind|status"):
                    build_user_result(
                        report_markdown=REPORT_MARKDOWN,
                        report_outcome=case["report_outcome"],
                        collection_outcome=case["collection_outcome"],
                        feed_outcomes=ALL_OK_OUTCOMES,
                        market=MARKET_OK,
                    )

    def test_fresh_report_requires_all_configured_feeds_and_one_success(self) -> None:
        confirmed = WriteOutcome("report", "confirmed", REPORT_URL, "")
        for outcomes in ((), ALL_OK_OUTCOMES[:-1], tuple(reversed(ALL_OK_OUTCOMES))):
            with self.subTest(source_ids=tuple(item.source_id for item in outcomes)):
                with self.assertRaisesRegex(ValueError, "all configured feeds"):
                    build_user_result(
                        report_markdown=REPORT_MARKDOWN,
                        report_outcome=confirmed,
                        feed_outcomes=outcomes,
                        market=MARKET_OK,
                    )

        with self.assertRaisesRegex(ValueError, "at least one successful feed"):
            build_user_result(
                report_markdown="# already written",
                report_outcome=confirmed,
                feed_outcomes=ALL_FAILED_OUTCOMES,
                market=MARKET_OK,
            )

    def test_safe_stop_is_prewrite_only_and_requires_all_feed_failures(self) -> None:
        safe_stop = WriteOutcome(
            "safe-stop", "failed", "", "all configured feeds failed"
        )
        with self.assertRaisesRegex(ValueError, "safe-stop"):
            build_user_result(
                report_markdown=REPORT_MARKDOWN,
                report_outcome=safe_stop,
                feed_outcomes=ALL_FAILED_OUTCOMES,
                market=MARKET_OK,
            )
        with self.assertRaisesRegex(ValueError, "safe-stop"):
            build_user_result(
                report_markdown="",
                report_outcome=safe_stop,
                feed_outcomes=OUTCOMES,
                market=MARKET_OK,
            )

    def test_prewrite_paths_reject_every_contradictory_story_count(self) -> None:
        cases = (
            (
                "safe-stop",
                {
                    "report_markdown": "",
                    "report_outcome": WriteOutcome(
                        "safe-stop", "failed", "", "all configured feeds failed"
                    ),
                    "feed_outcomes": ALL_FAILED_OUTCOMES,
                },
            ),
            (
                "reused",
                {
                    "report_markdown": REPORT_MARKDOWN,
                    "report_outcome": WriteOutcome(
                        "reused", "confirmed", REPORT_URL, ""
                    ),
                    "feed_outcomes": (),
                },
            ),
        )
        for kind, base in cases:
            for count_field in (
                "story_created",
                "story_updated",
                "changes_created",
            ):
                with self.subTest(kind=kind, count_field=count_field):
                    with self.assertRaisesRegex(
                        ValueError, f"{kind}.*Story counts.*zero"
                    ):
                        build_user_result(
                            **base,
                            market=MARKET_OK,
                            **{count_field: 1},
                        )

    def test_unconfirmed_report_rejects_every_contradictory_story_count(self) -> None:
        for status in ("failed", "verify-once"):
            for count_field in (
                "story_created",
                "story_updated",
                "changes_created",
            ):
                with self.subTest(status=status, count_field=count_field):
                    with self.assertRaisesRegex(
                        ValueError, "unconfirmed Report.*Story counts.*zero"
                    ):
                        build_user_result(
                            report_markdown=REPORT_MARKDOWN,
                            report_outcome=WriteOutcome(
                                "report",
                                status,
                                REPORT_ID if status == "verify-once" else "",
                                "report write was not confirmed",
                            ),
                            feed_outcomes=ALL_OK_OUTCOMES,
                            market=MARKET_OK,
                            **{count_field: 1},
                        )

    def test_rejects_impossible_market_snapshot_states(self) -> None:
        impossible = (
            MarketSnapshot("ok", (), {}, ()),
            MarketSnapshot(
                "partial",
                (ProviderResult("google-finance", "ok", {"SPY": 651.2}, ""),),
                {"SPY": 651.2},
                (),
            ),
            MarketSnapshot("unavailable", (), {"SPY": 651.2}, ()),
            MarketSnapshot(
                "ok",
                (ProviderResult("google-finance", "ok", {"SPY": 651.2}, ""),),
                {"QQQ": 580.0},
                (),
            ),
            MarketSnapshot(
                "partial",
                (
                    ProviderResult("google-finance", "ok", {"SPY": 651.2}, ""),
                    ProviderResult("cboe", "error", {}, "market_provider_error"),
                ),
                {"SPY": 651.2},
                ("wrong gap",),
            ),
            MarketSnapshot(
                "unavailable",
                (ProviderResult("cboe", "error", {}, "market_provider_error"),),
                {},
                (),
            ),
        )
        for market in impossible:
            with self.subTest(status=market.status):
                with self.assertRaisesRegex(ValueError, "market"):
                    build_user_result(
                        report_markdown=REPORT_MARKDOWN,
                        report_outcome=WriteOutcome(
                            "report", "confirmed", REPORT_URL, ""
                        ),
                        feed_outcomes=ALL_OK_OUTCOMES,
                        market=market,
                    )

    def test_user_result_rejects_noncanonical_provider_stages(self) -> None:
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
                    build_user_result(
                        report_markdown=REPORT_MARKDOWN,
                        report_outcome=WriteOutcome(
                            "report", "confirmed", REPORT_URL, ""
                        ),
                        feed_outcomes=ALL_OK_OUTCOMES,
                        market=market,
                    )

    def test_current_app_notion_report_url_is_visible(self) -> None:
        result = build_user_result(
            report_markdown=REPORT_MARKDOWN,
            report_outcome=WriteOutcome(
                "report", "confirmed", REPORT_APP_URL, ""
            ),
            feed_outcomes=ALL_OK_OUTCOMES,
            market=MARKET_OK,
        )

        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["reportMarkdown"], "")
        self.assertEqual(result["reportUrl"], REPORT_APP_URL)


if __name__ == "__main__":
    unittest.main()
