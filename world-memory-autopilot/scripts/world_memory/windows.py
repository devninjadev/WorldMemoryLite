"""Pure UTC decisions for World Memory report windows."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone


UTC = timezone.utc
INTEGRATION_INTERVAL = timedelta(minutes=345)


@dataclass(frozen=True)
class Window:
    """An inclusive-start, inclusive-end UTC collection interval."""

    start: datetime
    end: datetime

    def __post_init__(self) -> None:
        start = canonical_utc_minute(self.start, "start")
        end = canonical_utc_minute(self.end, "end")
        if start > end:
            raise ValueError("start must not be after end")
        object.__setattr__(self, "start", start)
        object.__setattr__(self, "end", end)


@dataclass(frozen=True)
class ReportDecision:
    """Whether a report window requires creation or can reuse an existing row."""

    disposition: str
    report_type: str | None
    reused: dict[str, object] | None
    warnings: tuple[str, ...]


def compute_window(
    now: datetime,
    cadence_minutes: int = 180,
    last_window_end: datetime | None = None,
) -> Window:
    """Return the whole-minute UTC interval ending at ``now``."""
    now_utc = canonical_utc_minute(now, "now")
    if isinstance(cadence_minutes, bool) or not isinstance(cadence_minutes, int):
        raise ValueError("cadence_minutes must be a positive integer")
    if cadence_minutes <= 0:
        raise ValueError("cadence_minutes must be a positive integer")

    if last_window_end is None:
        start = now_utc - timedelta(minutes=cadence_minutes)
    else:
        start = canonical_utc_minute(last_window_end, "last_window_end")
        if start > now_utc:
            raise ValueError("last_window_end must not be after now")
    return Window(start=start, end=now_utc)


def choose_report_type(
    now: datetime,
    latest_world_memory_end: datetime | None,
    force: bool = False,
) -> str:
    """Choose the 345-minute World Memory integration or a regular briefing."""
    now_utc = canonical_utc_minute(now, "now")
    if not isinstance(force, bool):
        raise ValueError("force must be a boolean")
    if force or latest_world_memory_end is None:
        return "world-memory"

    latest_utc = canonical_utc_minute(
        latest_world_memory_end, "latest_world_memory_end"
    )
    if latest_utc > now_utc:
        raise ValueError("latest_world_memory_end must not be after now")
    if now_utc - latest_utc >= INTEGRATION_INTERVAL:
        return "world-memory"
    return "briefing"


def resolve_same_window(reports: object, window: Window) -> ReportDecision:
    """Reuse exactly one validated report from a complete same-window query."""
    if not isinstance(window, Window):
        raise ValueError("window must be a Window")
    if not isinstance(reports, (list, tuple)):
        raise ValueError("reports must be a complete list or tuple query result")
    if not reports:
        return ReportDecision("create", None, None, ())

    validated: list[tuple[datetime, str, dict[str, object]]] = []
    for row in reports:
        if not isinstance(row, dict):
            raise ValueError("report row must be a mapping")
        report_type = row.get("Report Type")
        if report_type not in {"briefing", "world-memory"}:
            raise ValueError("Report Type must be briefing or world-memory")
        if "Window Start" not in row:
            raise ValueError("report row is missing Window Start")
        if "Window End" not in row:
            raise ValueError("report row is missing Window End")
        if _parse_utc(row["Window Start"], "Window Start") != window.start:
            raise ValueError("Window Start does not match the requested window")
        if _parse_utc(row["Window End"], "Window End") != window.end:
            raise ValueError("Window End does not match the requested window")
        if "Created At" not in row:
            raise ValueError("report row is missing Created At")
        created_at = _parse_utc(row["Created At"], "Created At")
        locator = _require_locator(row)
        validated.append((created_at, locator, row))

    newest_created_at = max(created_at for created_at, _, _ in validated)
    newest = min(
        (entry for entry in validated if entry[0] == newest_created_at),
        key=lambda entry: entry[1],
    )
    reused = newest[2]
    warnings: tuple[str, ...] = ()
    if len(validated) > 1:
        warnings = ("duplicate reports observed for the same window; reused newest",)
    return ReportDecision("reuse", reused["Report Type"], reused, warnings)


def _require_utc(value: object, field_name: str) -> datetime:
    """Require an aware datetime and canonicalize it to UTC without precision loss."""
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be a timezone-aware datetime")
    return value.astimezone(UTC)


def canonical_utc_minute(value: object, field_name: str = "value") -> datetime:
    """Convert an aware timestamp to UTC and discard sub-minute precision."""
    return _require_utc(value, field_name).replace(second=0, microsecond=0)


def _parse_utc(value: object, field_name: str) -> datetime:
    """Parse a Notion-style timestamp and canonicalize it to UTC."""
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError(f"{field_name} must be an ISO 8601 timestamp") from exc
    return _require_utc(value, field_name)


def _require_locator(row: dict[str, object]) -> str:
    """Require the Notion page ID used as this pure module's stable locator."""
    locator = row.get("id")
    if isinstance(locator, bool) or not isinstance(locator, str) or not locator:
        raise ValueError("report row must include a nonempty id locator")
    return locator


def _utc_iso(value: datetime) -> str:
    """Serialize a canonical UTC datetime with a trailing ``Z`` for external payloads."""
    return _require_utc(value, "value").isoformat().replace("+00:00", "Z")
