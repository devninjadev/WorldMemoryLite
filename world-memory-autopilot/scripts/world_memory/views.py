"""Pure normalization for official Notion MCP saved-view query results."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime, timezone
import json

from .notion_layout import DATABASE_SCHEMAS
from .registry import normalize_uuid, notion_page_id_from_url
from .windows import (
    Window,
    canonical_utc_minute,
    choose_report_type,
    compute_window,
    resolve_same_window,
)


_UTC = timezone.utc
REPORTS_RECENT_CONFIGURATION = (
    'SHOW "Name", "Report Type", "Window Start", "Window End", "Created At", '
    '"Collection", "Stories"; '
    'SORT BY "Window End" DESC, "Created At" DESC'
)
STORIES_CURRENT_CONFIGURATION = (
    'SHOW "Name", "Status", "Category", "Regions", "Importance", "Confidence", '
    '"Current View", "First Seen", "Last Evidence At", "Last Updated", '
    '"Related Stories", "Created At"; '
    'FILTER "Status" != "resolved"; '
    'SORT BY "Last Evidence At" DESC, "Last Updated" DESC'
)
_REPORT_REQUIRED = frozenset(
    {
        "url",
        "Name",
        "Report Type",
        "date:Window Start:start",
        "date:Window End:start",
        "Created At",
    }
)
_REPORT_ALLOWED = _REPORT_REQUIRED | frozenset(
    {
        "Stance",
        "Confidence",
        "Data Quality",
        "Data Gaps",
        "Collection",
        "Stories",
        "date:Window Start:is_datetime",
        "date:Window End:is_datetime",
    }
)
_STORY_REQUIRED = frozenset(
    {
        "url",
        "Name",
        "Status",
        "Category",
        "Regions",
        "Importance",
        "Confidence",
        "Current View",
        "date:First Seen:start",
        "date:Last Evidence At:start",
        "date:Last Updated:start",
        "Created At",
    }
)
_STORY_ALLOWED = _STORY_REQUIRED | frozenset(
    {
        "Related Stories",
        "date:First Seen:is_datetime",
        "date:Last Evidence At:is_datetime",
        "date:Last Updated:is_datetime",
    }
)
_REPORT_TYPES = frozenset(
    DATABASE_SCHEMAS["reports"]["properties"]["Report Type"]["options"]
)
_STORY_STATUSES = frozenset(
    DATABASE_SCHEMAS["stories"]["properties"]["Status"]["options"]
)
_STORY_CATEGORIES = frozenset(
    DATABASE_SCHEMAS["stories"]["properties"]["Category"]["options"]
)
_STORY_REGIONS = frozenset(
    DATABASE_SCHEMAS["stories"]["properties"]["Regions"]["options"]
)
_LEVELS = frozenset(("high", "medium", "low"))


def resolve_report_view(
    *,
    now: datetime,
    cadence_minutes: int,
    force: bool,
    rows: Iterable[object],
    has_more: bool,
) -> dict[str, object]:
    """Derive idempotency, the next window, and due state from saved-view rows."""

    now_utc = canonical_utc_minute(now, "now")
    if type(force) is not bool or type(has_more) is not bool:
        raise ValueError("force and has_more must be booleans")
    normalized = _report_rows(rows)
    if any(row["_end"] > now_utc for row in normalized):
        raise ValueError("Report view contains a future window")

    current = [row for row in normalized if row["_end"] == now_utc]
    earlier = [row for row in normalized if row["_end"] < now_utc]
    last_window_end = max((row["_end"] for row in earlier), default=None)
    window = compute_window(now_utc, cadence_minutes, last_window_end)

    if current:
        if has_more and not earlier:
            return _needs_more(window, last_window_end)
        if any(row["_start"] != window.start for row in current):
            raise ValueError("same-end Report rows do not match the current window")
        decision = resolve_same_window(
            [_public_report_row(row) for row in current], window
        )
        return {
            "disposition": "reuse",
            "window": _window_mapping(window),
            "reportType": decision.report_type,
            "reused": decision.reused,
            "warnings": list(decision.warnings),
            "lastWindowEnd": _optional_iso(last_window_end),
            "latestWorldMemoryEnd": None,
        }

    latest_world_memory_end = max(
        (
            row["_end"]
            for row in normalized
            if row["Report Type"] == "world-memory" and row["_end"] <= window.start
        ),
        default=None,
    )
    if not force and latest_world_memory_end is None and has_more:
        return _needs_more(window, last_window_end)
    report_type = choose_report_type(
        now_utc, latest_world_memory_end, force=force
    )
    return {
        "disposition": "create",
        "window": _window_mapping(window),
        "reportType": report_type,
        "reused": None,
        "warnings": [],
        "lastWindowEnd": _optional_iso(last_window_end),
        "latestWorldMemoryEnd": _optional_iso(latest_world_memory_end),
    }


def normalize_story_view(
    rows: Iterable[object], *, has_more: bool
) -> dict[str, object]:
    """Validate the complete current-Story view projection for the LLM boundary."""

    if type(has_more) is not bool:
        raise ValueError("has_more must be a boolean")
    raw_rows = _materialize(rows, "Story rows")
    normalized: list[dict[str, object]] = []
    seen: set[str] = set()
    for raw in raw_rows:
        if (
            type(raw) is not dict
            or not _STORY_REQUIRED.issubset(raw)
            or not set(raw).issubset(_STORY_ALLOWED)
        ):
            raise ValueError("Story view row keys do not match")
        locator, url = _page_locator(raw["url"])
        if locator in seen:
            raise ValueError("Story view contains a duplicate locator")
        seen.add(locator)
        name = _nonempty_string(raw["Name"], "Name")
        status = _enum(raw["Status"], _STORY_STATUSES, "Status")
        if status == "resolved":
            raise ValueError("Stories Current view contains a resolved Story")
        category = _enum(raw["Category"], _STORY_CATEGORIES, "Category")
        regions = _enum_list(raw["Regions"], _STORY_REGIONS, "Regions")
        importance = _enum(raw["Importance"], _LEVELS, "Importance")
        confidence = _enum(raw["Confidence"], _LEVELS, "Confidence")
        current_view = _nonempty_string(raw["Current View"], "Current View")
        first_seen = _timestamp(raw["date:First Seen:start"], "First Seen")
        _validate_datetime_marker(raw, "date:First Seen:is_datetime")
        last_evidence = _timestamp(
            raw["date:Last Evidence At:start"], "Last Evidence At"
        )
        _validate_datetime_marker(raw, "date:Last Evidence At:is_datetime")
        last_updated = _timestamp(
            raw["date:Last Updated:start"], "Last Updated"
        )
        _validate_datetime_marker(raw, "date:Last Updated:is_datetime")
        created_at = _timestamp(raw["Created At"], "Created At")
        if first_seen > last_evidence or last_evidence > last_updated:
            raise ValueError("Story dates are not monotonic")
        related = _relation_ids(raw.get("Related Stories", []), "Related Stories")
        normalized.append(
            {
                "id": locator,
                "url": url,
                "Name": name,
                "Status": status,
                "Category": category,
                "Regions": regions,
                "Importance": importance,
                "Confidence": confidence,
                "Current View": current_view,
                "First Seen": _utc_iso(first_seen),
                "Last Evidence At": _utc_iso(last_evidence),
                "Last Updated": _utc_iso(last_updated),
                "Related Stories": related,
                "Created At": _utc_iso(created_at),
                "_sort": (last_evidence, last_updated, locator),
            }
        )
    if has_more:
        return {"disposition": "needs-more", "stories": []}
    normalized.sort(
        key=lambda row: (
            -row["_sort"][0].timestamp(),
            -row["_sort"][1].timestamp(),
            row["_sort"][2],
        )
    )
    for row in normalized:
        del row["_sort"]
    return {"disposition": "complete", "stories": normalized}


def _report_rows(rows: Iterable[object]) -> list[dict[str, object]]:
    normalized: list[dict[str, object]] = []
    seen: set[str] = set()
    for raw in _materialize(rows, "Report rows"):
        if type(raw) is not dict:
            raise ValueError("Report view row must be an object")
        if not _REPORT_REQUIRED.issubset(raw) or not set(raw).issubset(_REPORT_ALLOWED):
            raise ValueError("Report view row keys do not match")
        locator, url = _page_locator(raw["url"])
        if locator in seen:
            raise ValueError("Report view contains a duplicate locator")
        seen.add(locator)
        report_type = _enum(raw["Report Type"], _REPORT_TYPES, "Report Type")
        start = canonical_utc_minute(
            _timestamp(raw["date:Window Start:start"], "Window Start"),
            "Window Start",
        )
        _validate_datetime_marker(raw, "date:Window Start:is_datetime")
        end = canonical_utc_minute(
            _timestamp(raw["date:Window End:start"], "Window End"),
            "Window End",
        )
        _validate_datetime_marker(raw, "date:Window End:is_datetime")
        if start > end:
            raise ValueError("Report Window Start is after Window End")
        normalized.append(
            {
                "id": locator,
                "url": url,
                "Name": _nonempty_string(raw["Name"], "Name"),
                "Report Type": report_type,
                "Window Start": _utc_iso(start),
                "Window End": _utc_iso(end),
                "Created At": _utc_iso(_timestamp(raw["Created At"], "Created At")),
                "Collection": _relation_ids(raw.get("Collection", []), "Collection"),
                "Stories": _relation_ids(raw.get("Stories", []), "Stories"),
                "_start": start,
                "_end": end,
            }
        )
    normalized.sort(
        key=lambda row: (
            -row["_end"].timestamp(),
            -_timestamp(row["Created At"], "Created At").timestamp(),
            row["id"],
        )
    )
    return normalized


def _public_report_row(row: dict[str, object]) -> dict[str, object]:
    return {
        key: value
        for key, value in row.items()
        if key not in {"_start", "_end", "url", "Name", "Collection", "Stories"}
    } | {
        "url": row["url"],
        "Name": row["Name"],
        "Collection": row["Collection"],
        "Stories": row["Stories"],
    }


def _needs_more(window: Window, last_window_end: datetime | None) -> dict[str, object]:
    return {
        "disposition": "needs-more",
        "window": _window_mapping(window),
        "reportType": None,
        "reused": None,
        "warnings": [],
        "lastWindowEnd": _optional_iso(last_window_end),
        "latestWorldMemoryEnd": None,
    }


def _materialize(rows: Iterable[object], field_name: str) -> list[object]:
    if isinstance(rows, (str, bytes, dict)):
        raise ValueError(f"{field_name} must be an iterable of rows")
    try:
        return list(rows)
    except TypeError as exc:
        raise ValueError(f"{field_name} must be an iterable of rows") from exc


def _page_locator(value: object) -> tuple[str, str]:
    if type(value) is not str:
        raise ValueError("row url must be a string")
    return notion_page_id_from_url(value), value


def _relation_ids(value: object, field_name: str) -> list[str]:
    value = _array_value(value, field_name)
    result: list[str] = []
    for item in value:
        if type(item) is not str:
            raise ValueError(f"{field_name} members must be strings")
        try:
            identifier = normalize_uuid(item, field_name)
        except ValueError:
            identifier = notion_page_id_from_url(item)
        if identifier in result:
            raise ValueError(f"{field_name} contains a duplicate")
        result.append(identifier)
    return result


def _enum(value: object, allowed: frozenset[str], field_name: str) -> str:
    if type(value) is not str or value not in allowed:
        raise ValueError(f"{field_name} is invalid")
    return value


def _enum_list(value: object, allowed: frozenset[str], field_name: str) -> list[str]:
    value = _array_value(value, field_name)
    if not value:
        raise ValueError(f"{field_name} must be a nonempty list")
    result: list[str] = []
    for item in value:
        result.append(_enum(item, allowed, field_name))
    if len(set(result)) != len(result):
        raise ValueError(f"{field_name} contains a duplicate")
    return result


def _array_value(value: object, field_name: str) -> list[object]:
    """Accept the official view transport's JSON-array strings or direct lists."""
    if type(value) is str:
        try:
            value = json.loads(value)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{field_name} must contain a JSON array") from exc
    if type(value) is not list:
        raise ValueError(f"{field_name} must be a list")
    return value


def _validate_datetime_marker(row: dict[str, object], key: str) -> None:
    if key in row and (type(row[key]) is not int or row[key] != 1):
        raise ValueError(f"{key} must be 1")


def _nonempty_string(value: object, field_name: str) -> str:
    if type(value) is not str or not value.strip():
        raise ValueError(f"{field_name} must be a nonempty string")
    return value


def _timestamp(value: object, field_name: str) -> datetime:
    if type(value) is not str:
        raise ValueError(f"{field_name} must be a timestamp string")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{field_name} must be an ISO timestamp") from exc
    return _aware_utc(parsed, field_name)


def _aware_utc(value: object, field_name: str) -> datetime:
    if (
        not isinstance(value, datetime)
        or value.tzinfo is None
        or value.utcoffset() is None
    ):
        raise ValueError(f"{field_name} must be timezone-aware")
    return value.astimezone(_UTC)


def _window_mapping(window: Window) -> dict[str, str]:
    return {"start": _utc_iso(window.start), "end": _utc_iso(window.end)}


def _optional_iso(value: datetime | None) -> str | None:
    return None if value is None else _utc_iso(value)


def _utc_iso(value: datetime) -> str:
    return value.astimezone(_UTC).isoformat().replace("+00:00", "Z")
