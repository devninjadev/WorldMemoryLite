"""Contract tests for bounded RSS.app CSV collection and invocation-local dedupe."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import time
import unittest

from world_memory.feed import FEEDS, FeedItem, FeedOutcome, collect_feeds, deduplicate_items


NOW = datetime(2026, 8, 14, 15, 0, tzinfo=timezone.utc)
FIXTURE = (Path(__file__).parent / "fixtures" / "rss-app-sample.csv").read_bytes()


def fetcher_with_out_of_order_completion(url: str, timeout: float) -> bytes:
    del timeout
    source_index = next(index for index, feed in enumerate(FEEDS) if feed.url == url)
    time.sleep((len(FEEDS) - source_index) * 0.01)
    return FIXTURE.replace(b"sample-1", f"sample-{source_index}".encode("ascii"))


def fetcher_failing(source_id: str):
    def fetcher(url: str, timeout: float) -> bytes:
        del timeout
        feed = next(feed for feed in FEEDS if feed.url == url)
        if feed.id == source_id:
            raise TimeoutError("upstream timeout")
        return FIXTURE

    return fetcher


def outcome(source_id: str, url: str) -> FeedOutcome:
    return FeedOutcome(
        source_id=source_id,
        source_name=source_id,
        status="ok",
        items=(
            FeedItem(
                item_id=source_id,
                source_id=source_id,
                source_name=source_id,
                title="same headline",
                url=url,
                published_at="2026-08-14T12:00:00Z",
                summary="summary",
            ),
        ),
        error="",
        retryable=False,
    )


class FeedCollectionTests(unittest.TestCase):
    def test_configured_rss_app_sources_have_exact_order_and_offsets(self) -> None:
        self.assertEqual(
            tuple((feed.id, feed.name, feed.url, feed.published_at_offset_minutes) for feed in FEEDS),
            (
                ("financial_juice", "FinancialJuice", "https://rss.app/feeds/5VaycMAa8SwPhOAP.csv", 0),
                ("walter_bloomberg", "Walter Bloomberg", "https://rss.app/feeds/YcRRdWN5eSO3o2LP.csv", 0),
                ("wall_st_engine", "Wall St Engine", "https://rss.app/feeds/Hf52VRUllNu7gABF.csv", 0),
                ("first_squawk", "First Squawk", "https://rss.app/feeds/d68ow40E3dkwaEvN.csv", -540),
                ("unusual_whales", "unusual_whales", "https://rss.app/feeds/nikLNBATmLDuprRz.csv", -540),
            ),
        )

    def test_collects_all_sources_in_parallel_but_returns_configured_order(self) -> None:
        outcomes = collect_feeds(fetcher_with_out_of_order_completion, now=NOW)
        self.assertEqual(tuple(item.source_id for item in outcomes), tuple(feed.id for feed in FEEDS))
        self.assertEqual(sum(outcome.status == "ok" for outcome in outcomes), 5)

    def test_one_feed_failure_preserves_other_items(self) -> None:
        outcomes = collect_feeds(fetcher_failing(FEEDS[2].id), now=NOW)
        self.assertEqual(outcomes[2].status, "error")
        self.assertTrue(outcomes[2].retryable)
        self.assertTrue(outcomes[0].items)
        self.assertTrue(outcomes[4].items)

    def test_fetch_failure_uses_a_sanitized_stable_error_code(self) -> None:
        secret = "https://api-key:super-secret@example.com/authorization?token=leak"

        def failing_fetcher(_url: str, _timeout: float) -> bytes:
            raise RuntimeError(secret)

        outcomes = collect_feeds(failing_fetcher, now=NOW)
        self.assertEqual(outcomes[0].error, "feed_fetch_runtimeerror")
        self.assertNotIn(secret, outcomes[0].error)
        self.assertLessEqual(len(outcomes[0].error), 240)

    def test_string_fetch_response_is_rejected_at_the_public_bytes_boundary(self) -> None:
        outcomes = collect_feeds(lambda _url, _timeout: FIXTURE.decode("utf-8"), now=NOW)
        self.assertEqual(outcomes[0].status, "error")
        self.assertEqual(outcomes[0].error, "feed_parse_typeerror")

    def test_invalid_utf8_bytes_are_rejected(self) -> None:
        outcomes = collect_feeds(lambda _url, _timeout: b"\xff", now=NOW)
        self.assertEqual(outcomes[0].status, "error")
        self.assertEqual(outcomes[0].error, "feed_parse_unicodedecodeerror")

    def test_utf8_bom_is_rejected(self) -> None:
        outcomes = collect_feeds(lambda _url, _timeout: b"\xef\xbb\xbf" + FIXTURE, now=NOW)
        self.assertEqual(outcomes[0].status, "error")
        self.assertEqual(outcomes[0].error, "feed_parse_valueerror")

    def test_rss_item_normalizes_summary_url_and_timestamp_offset(self) -> None:
        first_squawk_fixture = FIXTURE.replace(
            b"https://Example.com/article?utm_source=rss&id=7", b""
        ).replace(b"Plain fixture summary", b"")
        outcomes = collect_feeds(
            lambda _url, _timeout: first_squawk_fixture,
            now=NOW,
            max_workers=1,
        )
        item = outcomes[3].items[0]
        self.assertEqual(item.title, "Market headline")
        self.assertEqual(item.url, FEEDS[3].url)
        self.assertEqual(item.summary, "Description fallback")
        self.assertEqual(item.published_at, "2026-08-14T03:00:00Z")

    def test_plain_description_html_becomes_readable_text_without_blocked_content(self) -> None:
        markup = (
            b"<article><p>Fed &amp; <strong>markets</strong><br>moved</p>"
            b"<!-- comment --><script>ignore https://hidden.example/script</script>"
            b"<style>.secret{display:none}</style>"
            b"<iframe src='https://hidden.example/frame'>frame text</iframe>"
            b"<embed src='https://hidden.example/embed'>"
            b"<object data='https://hidden.example/object'>object text</object>"
            b"<div>Bonds&nbsp;steady</div></article>"
        )
        fixture = FIXTURE.replace(b"Plain fixture summary", markup)

        result = collect_feeds(
            lambda _url, _timeout: fixture,
            now=NOW,
            max_workers=1,
        )[0].items[0].summary

        self.assertEqual(result, "Fed & markets moved Bonds steady")
        for forbidden in (
            "script",
            "style",
            "iframe",
            "embed",
            "object",
            "hidden.example",
            "frame text",
            "object text",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, result)

    def test_description_fallback_html_uses_the_same_text_normalization(self) -> None:
        fixture = FIXTURE.replace(
            b"Description fallback",
            b"<div>Fallback <em>signal</em><br>held &lt;steady&gt;</div>"
            b"<script>hidden instruction</script>",
        ).replace(b"Plain fixture summary", b"")

        result = collect_feeds(
            lambda _url, _timeout: fixture,
            now=NOW,
            max_workers=1,
        )[0].items[0].summary

        self.assertEqual(result, "Fallback signal held <steady>")
        self.assertNotIn("hidden instruction", result)

    def test_blocked_elements_keep_surrounding_words_separate(self) -> None:
        fixture = FIXTURE.replace(
            b"Plain fixture summary",
            b"Market<script>hidden</script>moved"
            b"<embed src='https://hidden.example/embed'>today",
        )

        result = collect_feeds(
            lambda _url, _timeout: fixture,
            now=NOW,
            max_workers=1,
        )[0].items[0].summary

        self.assertEqual(result, "Market moved today")

    def test_mismatched_blocked_closer_cannot_release_hidden_text(self) -> None:
        fixture = FIXTURE.replace(
            b"Plain fixture summary",
            b"<iframe>secret</object>LEAKED INSTRUCTION</iframe>Visible",
        )

        result = collect_feeds(
            lambda _url, _timeout: fixture,
            now=NOW,
            max_workers=1,
        )[0].items[0].summary

        self.assertEqual(result, "Visible")
        self.assertNotIn("LEAKED INSTRUCTION", result)

    def test_crossed_raw_text_tags_cannot_release_hidden_text(self) -> None:
        fixture = FIXTURE.replace(
            b"Plain fixture summary",
            b"<p>Visible before</p><script> hidden one <style>hidden two</script>"
            b" BLOCKED TEXT LEAK </style><p>Visible after</p>",
        )

        result = collect_feeds(
            lambda _url, _timeout: fixture,
            now=NOW,
            max_workers=1,
        )[0].items[0].summary

        self.assertEqual(result, "Visible before Visible after")
        self.assertNotIn("BLOCKED TEXT LEAK", result)

    def test_crossed_embedded_tags_recover_only_after_every_closer(self) -> None:
        fixture = FIXTURE.replace(
            b"Plain fixture summary",
            b"<p>Visible before</p><iframe>hidden<object>hidden</iframe>"
            b"hidden</object><p>Visible after</p>",
        )

        result = collect_feeds(
            lambda _url, _timeout: fixture,
            now=NOW,
            max_workers=1,
        )[0].items[0].summary

        self.assertEqual(result, "Visible before Visible after")
        self.assertNotIn("hidden", result)

    def test_details_and_summary_elements_keep_adjacent_text_separate(self) -> None:
        fixture = FIXTURE.replace(
            b"Plain fixture summary",
            b"<details><summary>One</summary></details>"
            b"<details><summary>Two</summary></details>",
        )

        result = collect_feeds(
            lambda _url, _timeout: fixture,
            now=NOW,
            max_workers=1,
        )[0].items[0].summary

        self.assertEqual(result, "One Two")

    def test_bad_csv_header_is_a_bounded_nonretryable_error(self) -> None:
        outcomes = collect_feeds(
            lambda _url, _timeout: b"Title,Date\nheadline,2026-08-14T12:00:00Z\n",
            now=NOW,
        )
        self.assertEqual(outcomes[0].status, "error")
        self.assertFalse(outcomes[0].retryable)
        self.assertLessEqual(len(outcomes[0].error), 240)
        self.assertTrue(outcomes[1].error)

    def test_dedupe_strips_tracking_parameters_and_keeps_first_configured_item(self) -> None:
        items = deduplicate_items((
            outcome("a", "https://Example.com:443/x?utm_source=rss&id=7#section"),
            outcome("b", "https://example.com/x?id=7"),
        ))
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].source_id, "a")

    def test_dedupe_keeps_article_path_case_and_business_query_parameters(self) -> None:
        items = deduplicate_items((
            outcome("a", "https://example.com/Article?id=7&gclid=ad"),
            outcome("b", "https://example.com/article?id=7"),
            outcome("c", "https://example.com/Article?id=8"),
        ))
        self.assertEqual(tuple(item.source_id for item in items), ("a", "b", "c"))


if __name__ == "__main__":
    unittest.main()
