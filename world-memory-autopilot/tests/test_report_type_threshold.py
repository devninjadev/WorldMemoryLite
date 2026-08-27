"""Regression tests for the scheduled integration threshold."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import unittest

from world_memory.windows import choose_report_type


_UTC = timezone.utc


class ReportTypeThresholdTests(unittest.TestCase):
    def test_scheduled_run_remains_briefing_before_345_minutes(self) -> None:
        latest = datetime(2026, 8, 25, 0, 0, tzinfo=_UTC)

        report_type = choose_report_type(latest + timedelta(minutes=344), latest)

        self.assertEqual(report_type, "briefing")

    def test_scheduled_run_integrates_at_345_minutes(self) -> None:
        latest = datetime(2026, 8, 25, 0, 0, tzinfo=_UTC)

        report_type = choose_report_type(latest + timedelta(minutes=345), latest)

        self.assertEqual(report_type, "world-memory")

    def test_manual_force_still_integrates_immediately(self) -> None:
        latest = datetime(2026, 8, 25, 0, 0, tzinfo=_UTC)

        report_type = choose_report_type(
            latest + timedelta(minutes=1), latest, force=True
        )

        self.assertEqual(report_type, "world-memory")


if __name__ == "__main__":
    unittest.main()
