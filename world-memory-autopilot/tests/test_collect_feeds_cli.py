"""CLI contract tests for direct scheduled RSS collection."""

from __future__ import annotations

from io import StringIO
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from world_memory import cli as cli_module


class CollectFeedsCliTests(unittest.TestCase):
    def test_collect_feeds_routes_exact_window_to_direct_fetcher(self) -> None:
        expected = {
            "status": "complete",
            "windowStart": "2026-08-25T00:00:00Z",
            "windowEnd": "2026-08-25T02:00:00Z",
            "fetchedAt": "2026-08-25T02:01:00Z",
            "retrievalMethod": "direct-http",
            "feedSuccessCount": 8,
            "feedFailureCount": 0,
            "itemCount": 0,
            "sourceOutcomes": [],
            "snapshotId": None,
            "cursor": 0,
            "returnedItemCount": 0,
            "items": [],
            "nextCursor": None,
        }
        stdin = StringIO(
            json.dumps(
                {
                    "windowStart": "2026-08-25T00:00:00Z",
                    "windowEnd": "2026-08-25T02:00:00Z",
                    "timeoutSeconds": 17,
                }
            )
        )
        stdout = StringIO()
        stderr = StringIO()

        with patch.object(
            cli_module,
            "collect_feed_window",
            return_value={
                key: value
                for key, value in expected.items()
                if key
                not in {
                    "snapshotId",
                    "cursor",
                    "returnedItemCount",
                    "nextCursor",
                }
            },
            create=True,
        ) as collect:
            exit_code = cli_module.main(
                ["collect-feeds"], stdin=stdin, stdout=stdout, stderr=stderr
            )

        self.assertEqual(exit_code, 0)
        self.assertEqual(stderr.getvalue(), "")
        self.assertEqual(json.loads(stdout.getvalue()), expected)
        call = collect.call_args
        self.assertIs(call.args[0], cli_module.direct_http_fetch)
        self.assertEqual(call.kwargs["timeout"], 17.0)
        self.assertEqual(
            call.kwargs["window_start"].isoformat(), "2026-08-25T00:00:00+00:00"
        )
        self.assertEqual(
            call.kwargs["window_end"].isoformat(), "2026-08-25T02:00:00+00:00"
        )

    def test_large_collection_is_read_back_as_bounded_lossless_pages(self) -> None:
        items = [
            {
                "itemId": f"item-{index:03d}",
                "sourceId": "financial_juice",
                "sourceName": "FinancialJuice",
                "title": f"Headline {index}",
                "url": f"https://example.com/{index}",
                "publishedAt": "2026-08-25T01:00:00Z",
                "summary": f"Summary {index} " + ("가" * 1_200),
            }
            for index in range(259)
        ]
        collected = {
            "status": "complete",
            "windowStart": "2026-08-25T00:00:00Z",
            "windowEnd": "2026-08-25T02:00:00Z",
            "fetchedAt": "2026-08-25T02:01:00Z",
            "retrievalMethod": "direct-http",
            "feedSuccessCount": 8,
            "feedFailureCount": 0,
            "itemCount": len(items),
            "sourceOutcomes": [],
            "items": items,
        }
        collect_input = {
            "windowStart": "2026-08-25T00:00:00Z",
            "windowEnd": "2026-08-25T02:00:00Z",
            "timeoutSeconds": 17,
        }

        with TemporaryDirectory() as temporary_directory, patch.object(
            cli_module, "collect_feed_window", return_value=collected, create=True
        ) as collect, patch.object(
            cli_module,
            "FEED_SNAPSHOT_DIRECTORY",
            Path(temporary_directory),
            create=True,
        ):
            output_pages: list[bytes] = []
            first = self._run_json_command(
                "collect-feeds", collect_input, output_pages=output_pages
            )
            combined = list(first["items"])
            snapshot_id = first["snapshotId"]
            cursor = first["nextCursor"]

            while cursor is not None:
                page = self._run_json_command(
                    "read-feed-page",
                    {"snapshotId": snapshot_id, "cursor": cursor},
                    output_pages=output_pages,
                )
                combined.extend(page["items"])
                cursor = page["nextCursor"]

        self.assertEqual(collect.call_count, 1)
        self.assertLess(first["returnedItemCount"], collected["itemCount"])
        self.assertEqual(combined, items)
        self.assertTrue(all(len(output) <= 32_768 for output in output_pages))

    def test_read_feed_page_rejects_cursor_not_returned_by_snapshot(self) -> None:
        items = [
            {
                "itemId": f"item-{index:03d}",
                "sourceId": "financial_juice",
                "sourceName": "FinancialJuice",
                "title": f"Headline {index}",
                "url": f"https://example.com/{index}",
                "publishedAt": "2026-08-25T01:00:00Z",
                "summary": "나" * 1_200,
            }
            for index in range(259)
        ]
        collected = {
            "status": "complete",
            "windowStart": "2026-08-25T00:00:00Z",
            "windowEnd": "2026-08-25T02:00:00Z",
            "fetchedAt": "2026-08-25T02:01:00Z",
            "retrievalMethod": "direct-http",
            "feedSuccessCount": 8,
            "feedFailureCount": 0,
            "itemCount": len(items),
            "sourceOutcomes": [],
            "items": items,
        }

        with TemporaryDirectory() as temporary_directory, patch.object(
            cli_module, "collect_feed_window", return_value=collected, create=True
        ), patch.object(
            cli_module,
            "FEED_SNAPSHOT_DIRECTORY",
            Path(temporary_directory),
            create=True,
        ):
            first = self._run_json_command(
                "collect-feeds",
                {
                    "windowStart": "2026-08-25T00:00:00Z",
                    "windowEnd": "2026-08-25T02:00:00Z",
                    "timeoutSeconds": 17,
                },
            )
            stdout = StringIO()
            stderr = StringIO()
            exit_code = cli_module.main(
                ["read-feed-page"],
                stdin=StringIO(
                    json.dumps({"snapshotId": first["snapshotId"], "cursor": 1})
                ),
                stdout=stdout,
                stderr=stderr,
            )

        self.assertEqual(exit_code, 2)
        self.assertEqual(stdout.getvalue(), "")
        self.assertEqual(stderr.getvalue(), "invalid-input\n")

    def _run_json_command(
        self,
        command: str,
        payload: dict[str, object],
        *,
        output_pages: list[bytes] | None = None,
    ) -> dict[str, object]:
        stdout = StringIO()
        stderr = StringIO()
        exit_code = cli_module.main(
            [command],
            stdin=StringIO(json.dumps(payload)),
            stdout=stdout,
            stderr=stderr,
        )
        self.assertEqual(exit_code, 0, stderr.getvalue())
        self.assertEqual(stderr.getvalue(), "")
        if output_pages is not None:
            output_pages.append(stdout.getvalue().encode("utf-8"))
        return json.loads(stdout.getvalue())


if __name__ == "__main__":
    unittest.main()
