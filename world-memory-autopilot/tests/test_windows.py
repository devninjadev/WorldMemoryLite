"""Contract tests for UTC report windows and same-window reuse."""

from __future__ import annotations

from datetime import datetime, timezone
import unittest

from world_memory.windows import (
    ReportDecision,
    Window,
    choose_report_type,
    compute_window,
    resolve_same_window,
)


def dt(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


WINDOW = Window(dt("2026-08-14T00:00:00Z"), dt("2026-08-14T03:00:00Z"))


def report(
    report_type: str,
    created_at: str,
    *,
    locator: str = "report-a",
    window_start: str = "2026-08-14T00:00:00Z",
    window_end: str = "2026-08-14T03:00:00Z",
) -> dict[str, object]:
    return {
        "id": locator,
        "Report Type": report_type,
        "Window Start": window_start,
        "Window End": window_end,
        "Created At": created_at,
    }


class WindowTests(unittest.TestCase):
    def test_first_run_uses_three_hour_lookback(self) -> None:
        window = compute_window(dt("2026-08-14T03:00:00Z"))
        self.assertEqual(window.start, dt("2026-08-14T00:00:00Z"))
        self.assertEqual(window.end, dt("2026-08-14T03:00:00Z"))

    def test_window_boundaries_are_canonical_whole_utc_minutes(self) -> None:
        window = compute_window(
            dt("2026-08-14T03:00:28.987654Z"),
            last_window_end=dt("2026-08-14T01:30:59.123456Z"),
        )
        self.assertEqual(window.start, dt("2026-08-14T01:30:00Z"))
        self.assertEqual(window.end, dt("2026-08-14T03:00:00Z"))

        first = compute_window(dt("2026-08-14T03:00:59.999999Z"), cadence_minutes=60)
        self.assertEqual(first.start, dt("2026-08-14T02:00:00Z"))
        self.assertEqual(first.end, dt("2026-08-14T03:00:00Z"))

    def test_rejects_naive_datetimes_and_invalid_cadence(self) -> None:
        naive = datetime(2026, 8, 14, 3, 0, 0)
        with self.assertRaisesRegex(ValueError, "timezone-aware"):
            compute_window(naive)
        with self.assertRaisesRegex(ValueError, "cadence_minutes"):
            compute_window(dt("2026-08-14T03:00:00Z"), cadence_minutes=True)
        with self.assertRaisesRegex(ValueError, "cadence_minutes"):
            compute_window(dt("2026-08-14T03:00:00Z"), cadence_minutes=0)
        with self.assertRaisesRegex(ValueError, "timezone-aware"):
            choose_report_type(naive, None)

    def test_rejects_a_future_last_window_end(self) -> None:
        now = dt("2026-08-14T03:00:00Z")
        with self.assertRaisesRegex(ValueError, "last_window_end"):
            compute_window(now, last_window_end=dt("2026-08-14T03:01:00Z"))

        same_minute = compute_window(
            now, last_window_end=dt("2026-08-14T03:00:59.999999Z")
        )
        self.assertEqual(same_minute.start, now)
        self.assertEqual(same_minute.end, now)

    def test_canonicalizes_offsets_to_utc(self) -> None:
        window = compute_window(
            datetime(2026, 8, 14, 12, 0, tzinfo=timezone.utc), cadence_minutes=60
        )
        self.assertEqual(window.start.tzinfo, timezone.utc)
        self.assertEqual(window.end.tzinfo, timezone.utc)

    def test_due_boundary_is_exactly_345_minutes(self) -> None:
        latest = dt("2026-08-14T00:00:00Z")
        self.assertEqual(
            choose_report_type(dt("2026-08-14T05:44:59Z"), latest), "briefing"
        )
        self.assertEqual(
            choose_report_type(dt("2026-08-14T05:45:00Z"), latest), "world-memory"
        )
        self.assertEqual(
            choose_report_type(
                dt("2026-08-14T05:45:10Z"),
                dt("2026-08-14T00:00:59.999999Z"),
            ),
            "world-memory",
        )

    def test_missing_latest_world_memory_is_due(self) -> None:
        self.assertEqual(
            choose_report_type(dt("2026-08-14T01:00:00Z"), None), "world-memory"
        )

    def test_force_selects_world_memory(self) -> None:
        self.assertEqual(
            choose_report_type(
                dt("2026-08-14T01:00:00Z"),
                dt("2026-08-14T00:00:00Z"),
                force=True,
            ),
            "world-memory",
        )


class SameWindowResolutionTests(unittest.TestCase):
    def test_zero_reports_requests_creation(self) -> None:
        decision = resolve_same_window([], WINDOW)
        self.assertEqual(
            decision,
            ReportDecision("create", None, None, ()),
        )

    def test_one_report_is_reused_regardless_of_type(self) -> None:
        existing = report("briefing", "2026-08-14T03:01:00Z")
        decision = resolve_same_window([existing], WINDOW)
        self.assertEqual(decision.disposition, "reuse")
        self.assertEqual(decision.report_type, "briefing")
        self.assertIs(decision.reused, existing)
        self.assertEqual(decision.reused["Report Type"], "briefing")
        self.assertEqual(decision.warnings, ())

    def test_multiple_reports_reuse_newest_and_warn(self) -> None:
        older = report("briefing", "2026-08-14T03:01:00Z", locator="report-a")
        newer = report("world-memory", "2026-08-14T03:02:00Z", locator="report-b")
        decision = resolve_same_window([older, newer], WINDOW)
        self.assertIs(decision.reused, newer)
        self.assertEqual(decision.report_type, "world-memory")
        self.assertEqual(
            decision.warnings,
            ("duplicate reports observed for the same window; reused newest",),
        )

    def test_tied_created_at_uses_stable_locator_tie_break(self) -> None:
        later_locator = report(
            "briefing", "2026-08-14T03:01:00Z", locator="report-z"
        )
        earlier_locator = report(
            "world-memory", "2026-08-14T03:01:00Z", locator="report-a"
        )
        decision = resolve_same_window([later_locator, earlier_locator], WINDOW)
        self.assertIs(decision.reused, earlier_locator)

    def test_rejects_a_malformed_row_instead_of_silently_ignoring_it(self) -> None:
        malformed = report("briefing", "2026-08-14T03:01:00Z")
        del malformed["Created At"]
        with self.assertRaisesRegex(ValueError, "Created At"):
            resolve_same_window([malformed], WINDOW)

    def test_rejects_a_row_outside_the_complete_scoped_window(self) -> None:
        wrong_window = report(
            "briefing",
            "2026-08-14T03:01:00Z",
            window_end="2026-08-14T03:01:00Z",
        )
        with self.assertRaisesRegex(ValueError, "Window End"):
            resolve_same_window([wrong_window], WINDOW)

    def test_rejects_invalid_report_type_and_locator(self) -> None:
        invalid_type = report("daily", "2026-08-14T03:01:00Z")
        with self.assertRaisesRegex(ValueError, "Report Type"):
            resolve_same_window([invalid_type], WINDOW)

        missing_locator = report("briefing", "2026-08-14T03:01:00Z")
        del missing_locator["id"]
        with self.assertRaisesRegex(ValueError, "locator"):
            resolve_same_window([missing_locator], WINDOW)

    def test_rejects_query_failures_instead_of_treating_them_as_empty(self) -> None:
        with self.assertRaisesRegex(ValueError, "reports"):
            resolve_same_window(None, WINDOW)
        with self.assertRaisesRegex(ValueError, "reports"):
            resolve_same_window({"error": "Notion unavailable"}, WINDOW)


if __name__ == "__main__":
    unittest.main()
