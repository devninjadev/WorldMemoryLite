"""CLI contract tests for direct scheduled RSS collection."""

from __future__ import annotations

from io import StringIO
import json
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
            "feedSuccessCount": 5,
            "feedFailureCount": 0,
            "itemCount": 0,
            "sourceOutcomes": [],
            "items": [],
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
            cli_module, "collect_feed_window", return_value=expected, create=True
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


if __name__ == "__main__":
    unittest.main()
