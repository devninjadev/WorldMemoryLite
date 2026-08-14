"""Behavior tests for deterministic Notion view-mode result normalization."""

from __future__ import annotations

import copy
from datetime import datetime
import json
import unittest

from world_memory.views import normalize_story_view, resolve_report_view


REPORT_A = "11111111-1111-4111-8111-111111111111"
REPORT_B = "22222222-2222-4222-8222-222222222222"
REPORT_C = "33333333-3333-4333-8333-333333333333"
COLLECTION_A = "44444444-4444-4444-8444-444444444444"
STORY_A = "55555555-5555-4555-8555-555555555555"
STORY_B = "66666666-6666-4666-8666-666666666666"


def notion_url(identifier: str) -> str:
    return "https://app.notion.com/p/" + identifier.replace("-", "")


def report_row(
    identifier: str,
    start: str,
    end: str,
    report_type: str,
    created_at: str,
) -> dict[str, object]:
    return {
        "url": notion_url(identifier),
        "Name": f"Report {identifier[:4]}",
        "Report Type": report_type,
        "date:Window Start:start": start,
        "date:Window Start:is_datetime": 1,
        "date:Window End:start": end,
        "date:Window End:is_datetime": 1,
        "Created At": created_at,
        "Collection": json.dumps([notion_url(COLLECTION_A)]),
    }


def story_row(identifier: str = STORY_A) -> dict[str, object]:
    return {
        "url": notion_url(identifier),
        "Name": "Rates reprice risk assets",
        "Status": "active",
        "Category": "rates",
        "Regions": json.dumps(["US", "GLOBAL"]),
        "Importance": "high",
        "Confidence": "medium",
        "Current View": "Rates remain the transmission channel.",
        "date:First Seen:start": "2026-08-14T00:00:00Z",
        "date:First Seen:is_datetime": 1,
        "date:Last Evidence At:start": "2026-08-14T06:00:00Z",
        "date:Last Evidence At:is_datetime": 1,
        "date:Last Updated:start": "2026-08-14T06:00:00Z",
        "date:Last Updated:is_datetime": 1,
        "Created At": "2026-08-14T00:01:00Z",
    }


class ReportViewTests(unittest.TestCase):
    def test_resolves_new_window_and_six_hour_due_from_unsorted_rows(self) -> None:
        rows = [
            report_row(
                REPORT_A,
                "2026-08-14T00:00:00Z",
                "2026-08-14T03:00:00Z",
                "world-memory",
                "2026-08-14T03:01:00Z",
            ),
            report_row(
                REPORT_B,
                "2026-08-14T03:00:00Z",
                "2026-08-14T06:00:00Z",
                "briefing",
                "2026-08-14T06:01:00Z",
            ),
        ]

        result = resolve_report_view(
            now=datetime.fromisoformat("2026-08-14T09:00:00+00:00"),
            cadence_minutes=180,
            force=False,
            rows=reversed(rows),
            has_more=False,
        )

        self.assertEqual(result["disposition"], "create")
        self.assertEqual(result["window"], {
            "start": "2026-08-14T06:00:00Z",
            "end": "2026-08-14T09:00:00Z",
        })
        self.assertEqual(result["reportType"], "world-memory")
        self.assertEqual(result["lastWindowEnd"], "2026-08-14T06:00:00Z")
        self.assertEqual(result["latestWorldMemoryEnd"], "2026-08-14T03:00:00Z")

    def test_reuses_newest_same_window_and_warns_on_duplicate(self) -> None:
        older = report_row(
            REPORT_A,
            "2026-08-14T06:00:00Z",
            "2026-08-14T09:00:00Z",
            "briefing",
            "2026-08-14T09:01:00Z",
        )
        newer = report_row(
            REPORT_B,
            "2026-08-14T06:00:00Z",
            "2026-08-14T09:00:00Z",
            "world-memory",
            "2026-08-14T09:02:00Z",
        )
        previous = report_row(
            REPORT_C,
            "2026-08-14T03:00:00Z",
            "2026-08-14T06:00:00Z",
            "world-memory",
            "2026-08-14T06:01:00Z",
        )

        result = resolve_report_view(
            now=datetime.fromisoformat("2026-08-14T09:00:00+00:00"),
            cadence_minutes=180,
            force=False,
            rows=[older, previous, newer],
            has_more=True,
        )

        self.assertEqual(result["disposition"], "reuse")
        self.assertEqual(result["reused"]["id"], REPORT_B)
        self.assertEqual(result["reportType"], "world-memory")
        self.assertEqual(len(result["warnings"]), 1)

    def test_reuses_minute_precision_notion_row_for_second_bearing_now(self) -> None:
        existing = report_row(
            REPORT_A,
            "2026-08-14T11:35:00.000Z",
            "2026-08-14T12:35:00.000Z",
            "world-memory",
            "2026-08-14T12:36:00Z",
        )

        result = resolve_report_view(
            now=datetime.fromisoformat("2026-08-14T12:35:28.987654+00:00"),
            cadence_minutes=60,
            force=True,
            rows=[existing],
            has_more=False,
        )

        self.assertEqual(result["disposition"], "reuse")
        self.assertEqual(result["window"], {
            "start": "2026-08-14T11:35:00Z",
            "end": "2026-08-14T12:35:00Z",
        })
        self.assertEqual(result["reused"]["id"], REPORT_A)

    def test_canonicalizes_second_bearing_notion_window_dates(self) -> None:
        existing = report_row(
            REPORT_A,
            "2026-08-14T11:35:59.999999Z",
            "2026-08-14T12:35:28.123456Z",
            "briefing",
            "2026-08-14T12:36:00Z",
        )

        try:
            result = resolve_report_view(
                now=datetime.fromisoformat("2026-08-14T12:35:58.987654+00:00"),
                cadence_minutes=60,
                force=False,
                rows=[existing],
                has_more=False,
            )
        except ValueError as exc:
            self.fail(f"Report view window dates were not minute-canonicalized: {exc}")

        self.assertEqual(result["disposition"], "reuse")
        self.assertEqual(result["window"], {
            "start": "2026-08-14T11:35:00Z",
            "end": "2026-08-14T12:35:00Z",
        })

    def test_requests_continuation_only_when_world_memory_boundary_is_unknown(self) -> None:
        row = report_row(
            REPORT_A,
            "2026-08-14T03:00:00Z",
            "2026-08-14T06:00:00Z",
            "briefing",
            "2026-08-14T06:01:00Z",
        )

        pending = resolve_report_view(
            now=datetime.fromisoformat("2026-08-14T09:00:00+00:00"),
            cadence_minutes=180,
            force=False,
            rows=[row],
            has_more=True,
        )
        exhausted = resolve_report_view(
            now=datetime.fromisoformat("2026-08-14T09:00:00+00:00"),
            cadence_minutes=180,
            force=False,
            rows=[row],
            has_more=False,
        )

        self.assertEqual(pending["disposition"], "needs-more")
        self.assertEqual(exhausted["disposition"], "create")
        self.assertEqual(exhausted["reportType"], "world-memory")

    def test_rejects_future_overlap_duplicate_locator_and_unknown_fields(self) -> None:
        base = report_row(
            REPORT_A,
            "2026-08-14T06:00:00Z",
            "2026-08-14T09:00:00Z",
            "briefing",
            "2026-08-14T09:01:00Z",
        )
        cases: list[list[dict[str, object]]] = []

        future = copy.deepcopy(base)
        future["date:Window End:start"] = "2026-08-14T12:00:00Z"
        cases.append([future])

        overlap = copy.deepcopy(base)
        overlap["date:Window Start:start"] = "2026-08-14T05:00:00Z"
        cases.append([
            overlap,
            report_row(
                REPORT_B,
                "2026-08-14T03:00:00Z",
                "2026-08-14T06:00:00Z",
                "briefing",
                "2026-08-14T06:01:00Z",
            ),
        ])

        cases.append([base, copy.deepcopy(base)])
        unknown = copy.deepcopy(base)
        unknown["SQL"] = "SELECT *"
        cases.append([unknown])

        for rows in cases:
            with self.subTest(rows=rows), self.assertRaises(ValueError):
                resolve_report_view(
                    now=datetime.fromisoformat("2026-08-14T09:00:00+00:00"),
                    cadence_minutes=180,
                    force=False,
                    rows=rows,
                    has_more=False,
                )


class StoryViewTests(unittest.TestCase):
    def test_normalizes_complete_current_story_projection(self) -> None:
        row = story_row()
        row["Related Stories"] = json.dumps([notion_url(STORY_B)])

        result = normalize_story_view([row], has_more=False)

        self.assertEqual(result["disposition"], "complete")
        self.assertEqual(result["stories"][0]["id"], STORY_A)
        self.assertEqual(result["stories"][0]["Related Stories"], [STORY_B])

    def test_requires_all_pages_before_returning_known_story_set(self) -> None:
        result = normalize_story_view([story_row()], has_more=True)

        self.assertEqual(result["disposition"], "needs-more")
        self.assertEqual(result["stories"], [])

    def test_rejects_resolved_duplicate_malformed_or_unknown_rows(self) -> None:
        resolved = story_row()
        resolved["Status"] = "resolved"
        malformed = story_row()
        malformed["Regions"] = "US"
        unknown = story_row()
        unknown["temporaryControl"] = {}

        for rows in (
            [resolved],
            [story_row(), story_row()],
            [malformed],
            [unknown],
        ):
            with self.subTest(rows=rows), self.assertRaises(ValueError):
                normalize_story_view(rows, has_more=False)


if __name__ == "__main__":
    unittest.main()
