"""Regression tests for scheduled World Memory RSS collection."""

from __future__ import annotations

import csv
from datetime import datetime, timezone
from io import StringIO
import unittest
from unittest.mock import patch

from world_memory import feed as feed_module


_UTC = timezone.utc
_EXPECTED_FEEDS = (
    ("financial_juice", "FinancialJuice", "https://rss.app/feeds/5VaycMAa8SwPhOAP.csv", 0),
    ("walter_bloomberg", "Walter Bloomberg", "https://rss.app/feeds/YcRRdWN5eSO3o2LP.csv", 0),
    ("wall_st_engine", "Wall St Engine", "https://rss.app/feeds/Hf52VRUllNu7gABF.csv", 0),
    ("first_squawk", "First Squawk", "https://rss.app/feeds/d68ow40E3dkwaEvN.csv", -540),
    ("unusual_whales", "unusual_whales", "https://rss.app/feeds/nikLNBATmLDuprRz.csv", -540),
    ("reuters", "Reuters", "https://rss.app/feeds/_fSiPEQ8FZXQdj4js.csv", 0),
    ("dow_jones", "Dow Jones Personal", "https://rss.app/feeds/_m6HwVpkVbkV6H1V6.csv", 0),
    ("bloomberg", "Bloomberg Personal", "https://rss.app/feeds/_t07deORnyZW90CjC.csv", 0),
)
_HEADERS = (
    "ID",
    "Feed URL",
    "Feed Link",
    "Feed Title",
    "Feed Description",
    "Feed Icon",
    "Title",
    "Link",
    "Description",
    "Image",
    "Plain Description",
    "Author",
    "Date",
)


def _csv(*rows: dict[str, str]) -> bytes:
    output = StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=_HEADERS, lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow({header: row.get(header, "") for header in _HEADERS})
    return output.getvalue().encode("utf-8")


class FeedWindowCollectionTests(unittest.TestCase):
    def test_configures_eight_article_and_relay_feeds_in_order(self) -> None:
        self.assertEqual(
            tuple((feed.id, feed.name, feed.url, feed.published_at_offset_minutes) for feed in feed_module.FEEDS),
            _EXPECTED_FEEDS,
        )

    def test_direct_fetch_uses_fixed_url_and_cache_bypass_headers(self) -> None:
        class Response:
            status = 200

            def __enter__(self) -> "Response":
                return self

            def __exit__(self, *args: object) -> None:
                del args

            def getcode(self) -> int:
                return self.status

            def read(self) -> bytes:
                return b"payload"

        with patch.object(feed_module, "urlopen", return_value=Response()) as open_url:
            payload = feed_module.direct_http_fetch(feed_module.FEEDS[0].url, 13)

        self.assertEqual(payload, b"payload")
        request = open_url.call_args.args[0]
        self.assertEqual(request.get_method(), "GET")
        self.assertEqual(request.get_header("Cache-control"), "no-cache")
        self.assertEqual(request.get_header("Pragma"), "no-cache")
        self.assertIn("WorldMemoryAutopilot/0.14.4", request.get_header("User-agent"))
        self.assertEqual(open_url.call_args.kwargs["timeout"], 13.0)
        with self.assertRaisesRegex(ValueError, "configured feed"):
            feed_module.direct_http_fetch("https://example.com/not-configured.csv", 13)

    def test_filters_normalized_half_open_window_and_reports_diagnostics(self) -> None:
        payloads = {feed.url: _csv() for feed in feed_module.FEEDS}
        payloads[feed_module.FEEDS[0].url] = _csv(
            {
                "ID": "start",
                "Title": "At start",
                "Link": "https://example.com/start?utm_source=rss",
                "Plain Description": "Visible <b>summary</b>",
                "Date": "2026-08-25T00:00:00Z",
            },
            {
                "ID": "end",
                "Title": "At end",
                "Link": "https://example.com/end",
                "Date": "2026-08-25T02:00:00Z",
            },
        )
        payloads[feed_module.FEEDS[3].url] = _csv(
            {
                "ID": "offset",
                "Title": "KST wall clock",
                "Link": "https://example.com/offset",
                "Date": "2026-08-25T09:30:00Z",
            }
        )

        result = feed_module.collect_feed_window(
            lambda url, timeout: payloads[url],
            window_start=datetime(2026, 8, 25, 0, 0, tzinfo=_UTC),
            window_end=datetime(2026, 8, 25, 2, 0, tzinfo=_UTC),
            fetched_at=datetime(2026, 8, 25, 2, 1, tzinfo=_UTC),
        )

        self.assertEqual(result["status"], "complete")
        self.assertEqual(result["retrievalMethod"], "direct-http")
        self.assertEqual(result["feedSuccessCount"], 8)
        self.assertEqual(result["feedFailureCount"], 0)
        self.assertEqual(result["itemCount"], 2)
        self.assertEqual(
            [item["publishedAt"] for item in result["items"]],
            ["2026-08-25T00:00:00Z", "2026-08-25T00:30:00Z"],
        )
        financial = result["sourceOutcomes"][0]
        self.assertEqual(financial["status"], "ok")
        self.assertEqual(financial["parsedItemCount"], 2)
        self.assertEqual(financial["windowItemCount"], 1)
        self.assertEqual(financial["retainedItemCount"], 1)
        self.assertEqual(financial["latestPublishedAt"], "2026-08-25T02:00:00Z")
        first_squawk = result["sourceOutcomes"][3]
        self.assertEqual(first_squawk["latestPublishedAt"], "2026-08-25T00:30:00Z")
        self.assertEqual(first_squawk["windowItemCount"], 1)

    def test_uses_normalized_description_when_provider_omits_title(self) -> None:
        payloads = {feed.url: _csv() for feed in feed_module.FEEDS}
        payloads[feed_module.FEEDS[1].url] = _csv(
            {
                "ID": "description-only",
                "Title": "",
                "Link": "https://example.com/description-only",
                "Description": "<p>Fallback <b>headline</b></p>",
                "Date": "2026-08-25T00:30:00Z",
            }
        )

        result = feed_module.collect_feed_window(
            lambda url, timeout: payloads[url],
            window_start=datetime(2026, 8, 25, 0, 0, tzinfo=_UTC),
            window_end=datetime(2026, 8, 25, 2, 0, tzinfo=_UTC),
            fetched_at=datetime(2026, 8, 25, 2, 1, tzinfo=_UTC),
        )

        self.assertEqual(result["status"], "complete")
        self.assertEqual(result["sourceOutcomes"][1]["parsedItemCount"], 1)
        self.assertEqual(result["items"][0]["title"], "Fallback headline")
        self.assertEqual(result["items"][0]["summary"], "Fallback headline")

    def test_quarantines_malformed_rows_without_discarding_valid_feed_items(self) -> None:
        payloads = {feed.url: _csv() for feed in feed_module.FEEDS}
        payloads[feed_module.FEEDS[6].url] = _csv(
            {
                "ID": "valid",
                "Title": "Valid Dow Jones item",
                "Link": "https://example.com/valid",
                "Date": "2026-08-25T01:00:00Z",
            },
            {
                "ID": "missing-date",
                "Title": "Undated Dow Jones item",
                "Link": "https://example.com/missing-date",
                "Date": "",
            },
        )

        result = feed_module.collect_feed_window(
            lambda url, timeout: payloads[url],
            window_start=datetime(2026, 8, 25, 0, 0, tzinfo=_UTC),
            window_end=datetime(2026, 8, 25, 2, 0, tzinfo=_UTC),
            fetched_at=datetime(2026, 8, 25, 2, 1, tzinfo=_UTC),
        )

        dow_jones = result["sourceOutcomes"][6]
        self.assertEqual(dow_jones["status"], "ok")
        self.assertEqual(dow_jones["parsedItemCount"], 1)
        self.assertEqual(dow_jones["rejectedItemCount"], 1)
        self.assertEqual(dow_jones["retainedItemCount"], 1)
        self.assertEqual(result["itemCount"], 1)

    def test_preserves_successes_when_one_feed_fails(self) -> None:
        failing_url = feed_module.FEEDS[1].url

        def fetch(url: str, timeout: float) -> bytes:
            del timeout
            if url == failing_url:
                raise TimeoutError("simulated timeout")
            return _csv()

        result = feed_module.collect_feed_window(
            fetch,
            window_start=datetime(2026, 8, 25, 0, 0, tzinfo=_UTC),
            window_end=datetime(2026, 8, 25, 2, 0, tzinfo=_UTC),
            fetched_at=datetime(2026, 8, 25, 2, 1, tzinfo=_UTC),
        )

        self.assertEqual(result["status"], "partial")
        self.assertEqual(result["feedSuccessCount"], 7)
        self.assertEqual(result["feedFailureCount"], 1)
        failure = result["sourceOutcomes"][1]
        self.assertEqual(failure["status"], "error")
        self.assertEqual(failure["parsedItemCount"], 0)
        self.assertEqual(failure["windowItemCount"], 0)
        self.assertIsNone(failure["latestPublishedAt"])
        self.assertEqual(failure["error"], "feed_fetch_timeouterror")
        self.assertTrue(failure["retryable"])

    def test_marks_all_feed_failure_without_items(self) -> None:
        def fetch(url: str, timeout: float) -> bytes:
            del url, timeout
            raise OSError("simulated outage")

        result = feed_module.collect_feed_window(
            fetch,
            window_start=datetime(2026, 8, 25, 0, 0, tzinfo=_UTC),
            window_end=datetime(2026, 8, 25, 2, 0, tzinfo=_UTC),
            fetched_at=datetime(2026, 8, 25, 2, 1, tzinfo=_UTC),
        )

        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["feedSuccessCount"], 0)
        self.assertEqual(result["feedFailureCount"], 8)
        self.assertEqual(result["itemCount"], 0)
        self.assertEqual(result["items"], [])


if __name__ == "__main__":
    unittest.main()
