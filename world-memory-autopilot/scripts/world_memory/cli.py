"""Single-object JSON commands for Notion-native World Memory.

Commands validate, normalize, combine, or describe caller-supplied
observations. The sole public-network exception is ``collect-feeds``, which
performs bounded GETs to the eight fixed RSS.app CSV URLs. No command has a
connector, model, or persistent-state client.
"""

from __future__ import annotations

import argparse
import csv
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from io import StringIO
import json
from pathlib import Path
import sys
from typing import Callable, Sequence, TextIO
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from .bootstrap import build_bootstrap_plan, render_scheduled_prompt
from .discovery import resolve_registry_discovery
from .feed import (
    FEEDS,
    FeedItem,
    FeedOutcome,
    FeedSpec,
    collect_feed_window,
    direct_http_fetch,
    normalize_feed_summary,
)
from .feed_pages import (
    DEFAULT_SNAPSHOT_DIRECTORY,
    create_feed_snapshot,
    read_feed_page,
)
from .llm_plan import validate_llm_plan
from .market import MarketSnapshot
from .notion_layout import DATABASE_SCHEMAS, bootstrap_manifest
from .plugin_market import (
    assess_market_observation,
    build_plugin_market_plan,
    collect_planned_market_observations,
)
from .registry import Registry, normalize_uuid, validate_registry
from .windows import (
    ReportDecision,
    choose_report_type,
    compute_window,
    resolve_same_window,
)
from .views import (
    REPORTS_RECENT_CONFIGURATION,
    STORIES_CURRENT_CONFIGURATION,
    normalize_story_view,
    resolve_report_view,
)


_COMMANDS = (
    "validate-registry",
    "resolve-registry-discovery",
    "schema",
    "bootstrap-plan",
    "window",
    "resolve-report-view",
    "normalize-story-view",
    "validate-llm-plan",
    "render-scheduled-prompt",
    "collect-feeds",
    "read-feed-page",
    "normalize-feed",
    "market-data-plan",
    "validate-market-observation",
    "collect-market-data",
    "verify-live",
)
_CSV_HEADERS = (
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
_TRACKING_PARAMETERS = frozenset({"fbclid", "gclid"})
_UTC = timezone.utc
FEED_SNAPSHOT_DIRECTORY = DEFAULT_SNAPSHOT_DIRECTORY
_TOOL_ACCESS_KEYS_IN_ORDER = (
    "fetchSelf",
    "queryDataSources",
    "fetchPages",
    "createPages",
    "updatePages",
)
_TOOL_ACCESS_KEYS = frozenset(_TOOL_ACCESS_KEYS_IN_ORDER)
_DATA_SOURCE_KEYS = ("collections", "stories", "storyChanges", "reports")
_VIEW_BINDINGS = {
    "reportsRecent": (
        "reports",
        REPORTS_RECENT_CONFIGURATION,
    ),
    "storiesCurrent": (
        "stories",
        STORIES_CURRENT_CONFIGURATION,
    ),
}


class _CliUsageError(Exception):
    """Internal marker for a value-free command-line usage failure."""


class _SafeArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        del message
        raise _CliUsageError


def _parser() -> argparse.ArgumentParser:
    parser = _SafeArgumentParser(prog="world-memory")
    subparsers = parser.add_subparsers(dest="command", required=True)
    help_text = {
        "validate-registry": "normalize the embedded native registry",
        "resolve-registry-discovery": "validate one-shot Notion recovery observations",
        "schema": "return an independent logical schema manifest",
        "bootstrap-plan": "describe a finite fresh setup",
        "window": "resolve a supplied report-window observation",
        "resolve-report-view": "resolve supplied saved Reports view rows",
        "normalize-story-view": "normalize supplied saved Stories view rows",
        "validate-llm-plan": "validate one supplied temporary plan",
        "render-scheduled-prompt": "render the self-contained schedule prompt",
        "collect-feeds": "directly collect the fixed RSS.app feeds for one window",
        "read-feed-page": "read one continuation page from a collected feed snapshot",
        "normalize-feed": "normalize one supplied RSS.app CSV payload",
        "market-data-plan": "describe independent market observations",
        "validate-market-observation": "validate one supplied market observation",
        "collect-market-data": "combine supplied provider observations",
        "verify-live": "validate supplied canary evidence only",
    }
    for name in _COMMANDS:
        command = subparsers.add_parser(name, help=help_text[name])
        command.add_argument("input", nargs="?", default="-")
    return parser


def _read_json_object(path: str, stdin: TextIO) -> dict[str, object]:
    if path == "-":
        text = stdin.read()
    else:
        text = Path(path).read_text(encoding="utf-8")
    value = json.loads(
        text,
        object_pairs_hook=_unique_json_object,
        parse_constant=_reject_json_constant,
    )
    if type(value) is not dict:
        raise ValueError("input must be a JSON object")
    return value


def _unique_json_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON object key")
        result[key] = value
    return result


def _reject_json_constant(value: str) -> object:
    del value
    raise ValueError("nonfinite JSON number")


def _write_json_object(value: object, stdout: TextIO) -> None:
    if type(value) is not dict:
        raise ValueError("output must be a JSON object")
    stdout.write(
        json.dumps(
            value,
            ensure_ascii=False,
            separators=(",", ":"),
            allow_nan=False,
        )
    )
    stdout.write("\n")


def main(
    argv: Sequence[str] | None = None,
    *,
    stdin: TextIO = sys.stdin,
    stdout: TextIO = sys.stdout,
    stderr: TextIO = sys.stderr,
) -> int:
    """Run one deterministic command and emit one safe result or error category."""

    try:
        args = _parser().parse_args(argv)
        value = _read_json_object(args.input, stdin)
        _write_json_object(_dispatch(args.command, value), stdout)
        return 0
    except _CliUsageError:
        stderr.write("cli-usage-error\n")
    except (OSError, UnicodeError):
        stderr.write("input-read-error\n")
    except (
        csv.Error,
        json.JSONDecodeError,
        OverflowError,
        RecursionError,
        TypeError,
        ValueError,
    ):
        stderr.write("invalid-input\n")
    return 2


def _dispatch(command: str, value: dict[str, object]) -> dict[str, object]:
    handlers: dict[str, Callable[[dict[str, object]], dict[str, object]]] = {
        "validate-registry": validate_registry,
        "resolve-registry-discovery": resolve_registry_discovery,
        "schema": _schema,
        "bootstrap-plan": _bootstrap_plan,
        "window": _window,
        "resolve-report-view": _resolve_report_view,
        "normalize-story-view": _normalize_story_view,
        "validate-llm-plan": _validate_llm_plan,
        "render-scheduled-prompt": _render_scheduled_prompt,
        "collect-feeds": _collect_feeds,
        "read-feed-page": _read_feed_page,
        "normalize-feed": _normalize_feed,
        "market-data-plan": _market_data_plan,
        "validate-market-observation": assess_market_observation,
        "collect-market-data": _collect_market_data,
        "verify-live": _verify_live,
    }
    handler = handlers.get(command)
    if handler is None:
        raise _CliUsageError
    return handler(value)


def _schema(value: dict[str, object]) -> dict[str, object]:
    _require_exact_keys(value, frozenset(), "schema input")
    return bootstrap_manifest()


def _bootstrap_plan(value: dict[str, object]) -> dict[str, object]:
    _require_exact_keys(value, frozenset({"workspaceId"}), "bootstrap-plan input")
    return build_bootstrap_plan(value["workspaceId"])


def _window(value: dict[str, object]) -> dict[str, object]:
    _require_exact_keys(
        value,
        frozenset(
            {
                "now",
                "cadenceMinutes",
                "lastWindowEnd",
                "sameWindowReports",
                "latestWorldMemoryEnd",
                "force",
            }
        ),
        "window input",
    )
    now = _timestamp(value["now"], "now")
    last_window_end = _optional_timestamp(value["lastWindowEnd"], "lastWindowEnd")
    latest_world_memory_end = _optional_timestamp(
        value["latestWorldMemoryEnd"], "latestWorldMemoryEnd"
    )
    force = value["force"]
    if type(force) is not bool:
        raise ValueError("force must be a boolean")
    reports = value["sameWindowReports"]
    if type(reports) is not list:
        raise ValueError("sameWindowReports must be a list")

    window = compute_window(
        now,
        cadence_minutes=value["cadenceMinutes"],
        last_window_end=last_window_end,
    )
    decision = resolve_same_window(reports, window)
    report_type = (
        decision.report_type
        if decision.disposition == "reuse"
        else choose_report_type(now, latest_world_memory_end, force=force)
    )
    return {
        "window": {"start": _utc_iso(window.start), "end": _utc_iso(window.end)},
        "sameWindow": _report_decision_mapping(decision),
        "reportType": report_type,
    }


def _resolve_report_view(value: dict[str, object]) -> dict[str, object]:
    _require_exact_keys(
        value,
        frozenset({"now", "cadenceMinutes", "force", "rows", "hasMore"}),
        "resolve-report-view input",
    )
    if type(value["rows"]) is not list:
        raise ValueError("rows must be a list")
    if type(value["force"]) is not bool or type(value["hasMore"]) is not bool:
        raise ValueError("force and hasMore must be booleans")
    return resolve_report_view(
        now=_timestamp(value["now"], "now"),
        cadence_minutes=value["cadenceMinutes"],
        force=value["force"],
        rows=value["rows"],
        has_more=value["hasMore"],
    )


def _normalize_story_view(value: dict[str, object]) -> dict[str, object]:
    _require_exact_keys(
        value,
        frozenset({"rows", "hasMore"}),
        "normalize-story-view input",
    )
    if type(value["rows"]) is not list:
        raise ValueError("rows must be a list")
    if type(value["hasMore"]) is not bool:
        raise ValueError("hasMore must be a boolean")
    return normalize_story_view(value["rows"], has_more=value["hasMore"])


def _validate_llm_plan(value: dict[str, object]) -> dict[str, object]:
    _require_exact_keys(
        value,
        frozenset(
            {
                "candidate",
                "knownStoryIds",
                "evidenceItemIds",
                "expectedReportType",
            }
        ),
        "validate-llm-plan input",
    )
    story_ids = _string_list(value["knownStoryIds"], "knownStoryIds")
    evidence_ids = _string_list(value["evidenceItemIds"], "evidenceItemIds")
    expected_report_type = _string(value["expectedReportType"], "expectedReportType")
    normalized_story_ids = {
        normalize_uuid(story_id, "knownStoryIds") for story_id in story_ids
    }
    return validate_llm_plan(
        value["candidate"],
        known_story_locators=normalized_story_ids,
        evidence_item_ids=set(evidence_ids),
        expected_report_type=expected_report_type,
    )


def _render_scheduled_prompt(value: dict[str, object]) -> dict[str, object]:
    registry = Registry.from_mapping(value)
    return {"prompt": render_scheduled_prompt(registry)}


def _collect_feeds(value: dict[str, object]) -> dict[str, object]:
    _require_exact_keys(
        value,
        frozenset({"windowStart", "windowEnd", "timeoutSeconds"}),
        "collect-feeds input",
    )
    timeout = value["timeoutSeconds"]
    if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or timeout <= 0:
        raise ValueError("timeoutSeconds must be a positive number")
    collected = collect_feed_window(
        direct_http_fetch,
        window_start=_timestamp(value["windowStart"], "windowStart"),
        window_end=_timestamp(value["windowEnd"], "windowEnd"),
        fetched_at=datetime.now(_UTC),
        timeout=float(timeout),
    )
    return create_feed_snapshot(collected, directory=FEED_SNAPSHOT_DIRECTORY)


def _read_feed_page(value: dict[str, object]) -> dict[str, object]:
    _require_exact_keys(
        value,
        frozenset({"snapshotId", "cursor"}),
        "read-feed-page input",
    )
    return read_feed_page(
        value["snapshotId"],
        value["cursor"],
        directory=FEED_SNAPSHOT_DIRECTORY,
    )


def _normalize_feed(value: dict[str, object]) -> dict[str, object]:
    _require_exact_keys(value, frozenset({"feedId", "csv"}), "normalize-feed input")
    feed_id = _string(value["feedId"], "feedId")
    csv_payload = value["csv"]
    if type(csv_payload) is not str:
        raise ValueError("csv must be a string")
    feed = next((item for item in FEEDS if item.id == feed_id), None)
    if feed is None:
        raise ValueError("feedId must identify a configured feed")
    outcome = FeedOutcome(
        source_id=feed.id,
        source_name=feed.name,
        status="ok",
        items=_parse_supplied_csv(feed, csv_payload),
        error="",
        retryable=False,
    )
    return _feed_outcome_mapping(outcome)


def _market_data_plan(value: dict[str, object]) -> dict[str, object]:
    _require_exact_keys(
        value,
        frozenset({"registry", "toolAccess"}),
        "market-data-plan input",
    )
    registry = Registry.from_mapping(value["registry"])
    vix_source = registry.market_sources.vix_spreadsheet
    return build_plugin_market_plan(
        tool_access=value["toolAccess"],
        vix_public_csv_url=vix_source.public_csv_url,
        vix_symbols=vix_source.expected_symbols,
    )


def _collect_market_data(value: dict[str, object]) -> dict[str, object]:
    _require_exact_keys(
        value, frozenset({"plan", "outcomes"}), "collect-market-data input"
    )
    return collect_planned_market_observations(
        plan=value["plan"], outcomes=value["outcomes"]
    )


def _verify_live(value: dict[str, object]) -> dict[str, object]:
    _require_exact_keys(
        value,
        frozenset(
            {
                "registry",
                "workspaceId",
                "toolAccess",
                "schemaProjections",
                "viewProjections",
            }
        ),
        "verify-live input",
    )
    registry = Registry.from_mapping(value["registry"])
    workspace_id = normalize_uuid(value["workspaceId"], "workspaceId")
    if workspace_id != registry.workspace_id:
        raise ValueError("workspace identity does not match registry")

    tool_access = value["toolAccess"]
    if type(tool_access) is not dict:
        raise ValueError("toolAccess must be an object")
    _require_exact_keys(tool_access, _TOOL_ACCESS_KEYS, "toolAccess")
    if any(type(item) is not bool or not item for item in tool_access.values()):
        raise ValueError("required tool access is unavailable")

    projections = value["schemaProjections"]
    if type(projections) is not dict:
        raise ValueError("schemaProjections must be an object")
    _require_exact_keys(
        projections, frozenset(_DATA_SOURCE_KEYS), "schemaProjections"
    )
    normalized_projections: dict[str, object] = {}
    registry_mapping = registry.to_mapping()
    for key in _DATA_SOURCE_KEYS:
        projection = projections[key]
        if type(projection) is not dict:
            raise ValueError("schema projection must be an object")
        _require_exact_keys(
            projection,
            frozenset({"dataSourceId", "properties"}),
            "schema projection",
        )
        data_source_id = normalize_uuid(
            projection["dataSourceId"], "dataSourceId"
        )
        registry_locator = registry_mapping[key]
        if type(registry_locator) is not dict:
            raise ValueError("registry locator is invalid")
        if data_source_id != registry_locator["dataSourceId"]:
            raise ValueError("schema projection locator does not match registry")
        properties = projection["properties"]
        if type(properties) is not dict or any(
            type(name) is not str or type(property_type) is not str
            for name, property_type in properties.items()
        ):
            raise ValueError("schema property projection is invalid")
        expected = {
            name: descriptor["type"]
            for name, descriptor in DATABASE_SCHEMAS[key]["properties"].items()
        }
        if properties != expected:
            raise ValueError("schema name/type projection does not match")
        normalized_projections[key] = {
            "dataSourceId": data_source_id,
            "properties": expected,
        }

    view_projections = value["viewProjections"]
    if type(view_projections) is not dict:
        raise ValueError("viewProjections must be an object")
    _require_exact_keys(
        view_projections, frozenset(_VIEW_BINDINGS), "viewProjections"
    )
    normalized_views: dict[str, object] = {}
    registry_views = registry_mapping["views"]
    if type(registry_views) is not dict:
        raise ValueError("registry views are invalid")
    for key, (data_source_key, expected_configuration) in _VIEW_BINDINGS.items():
        projection = view_projections[key]
        if type(projection) is not dict:
            raise ValueError("view projection must be an object")
        _require_exact_keys(
            projection,
            frozenset({"url", "dataSourceId", "configuration"}),
            "view projection",
        )
        registry_view = registry_views[key]
        registry_data_source = registry_mapping[data_source_key]
        if type(registry_view) is not dict or type(registry_data_source) is not dict:
            raise ValueError("registry view binding is invalid")
        if projection["url"] != registry_view["url"]:
            raise ValueError("view projection URL does not match registry")
        data_source_id = normalize_uuid(
            projection["dataSourceId"], "view dataSourceId"
        )
        if data_source_id != registry_data_source["dataSourceId"]:
            raise ValueError("view projection data source does not match registry")
        if projection["configuration"] != expected_configuration:
            raise ValueError("view projection configuration does not match")
        normalized_views[key] = {
            "url": registry_view["url"],
            "dataSourceId": data_source_id,
            "configuration": expected_configuration,
        }

    return {
        "status": "supplied-evidence-valid",
        "liveExecutionPerformed": False,
        "workspaceId": workspace_id,
        "toolAccess": {key: tool_access[key] for key in _TOOL_ACCESS_KEYS_IN_ORDER},
        "registry": registry_mapping,
        "schemaProjections": normalized_projections,
        "viewProjections": normalized_views,
    }


def _parse_supplied_csv(feed: FeedSpec, text: str) -> tuple[FeedItem, ...]:
    """Pure adapter for one configured feed; no fetcher is created or invoked."""

    if text.startswith("\ufeff"):
        raise ValueError("RSS.app CSV must not contain a BOM")
    reader = csv.DictReader(StringIO(text))
    if tuple(reader.fieldnames or ()) != _CSV_HEADERS:
        raise ValueError("RSS.app CSV header does not match")

    items: list[FeedItem] = []
    for row in reader:
        title = _collapsed(row.get("Title"))
        date_text = _collapsed(row.get("Date"))
        if not date_text:
            raise ValueError("RSS.app CSV row requires a date")
        source_url = _collapsed(row.get("Link")) or feed.url
        canonical_url = _canonical_article_url(source_url)
        published_at = _feed_timestamp(
            date_text, feed.published_at_offset_minutes
        )
        summary_source = row.get("Plain Description")
        if not _collapsed(summary_source):
            summary_source = row.get("Description")
        summary = normalize_feed_summary(summary_source)
        if not title:
            title = summary
        if not title:
            raise ValueError("RSS.app CSV row requires title or description text")
        items.append(
            FeedItem(
                item_id="\x1f".join((feed.id, canonical_url, title, published_at)),
                source_id=feed.id,
                source_name=feed.name,
                title=title,
                url=source_url,
                published_at=published_at,
                summary=summary,
            )
        )
    return tuple(items)


def _feed_timestamp(value: str, offset_minutes: int) -> str:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        try:
            parsed = parsedate_to_datetime(value)
        except (TypeError, ValueError) as exc:
            raise ValueError("RSS.app Date must be a timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("RSS.app Date must include a timezone")
    return (
        parsed.astimezone(_UTC) + timedelta(minutes=offset_minutes)
    ).isoformat().replace("+00:00", "Z")


def _canonical_article_url(value: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
        raise ValueError("URL must use HTTP(S) and include a host")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("URL must not contain user information")
    try:
        port = parsed.port
    except ValueError as exc:
        raise ValueError("URL port is invalid") from exc
    hostname = parsed.hostname.lower()
    if port is not None and not (
        (parsed.scheme.lower() == "http" and port == 80)
        or (parsed.scheme.lower() == "https" and port == 443)
    ):
        hostname = f"{hostname}:{port}"
    query = urlencode(
        [
            (key, item)
            for key, item in parse_qsl(parsed.query, keep_blank_values=True)
            if not key.lower().startswith("utm_")
            and key.lower() not in _TRACKING_PARAMETERS
        ],
        doseq=True,
    )
    return urlunparse((parsed.scheme.lower(), hostname, parsed.path, "", query, ""))


def _feed_outcome_mapping(outcome: FeedOutcome) -> dict[str, object]:
    return {
        "sourceId": outcome.source_id,
        "sourceName": outcome.source_name,
        "status": outcome.status,
        "items": [
            {
                "itemId": item.item_id,
                "sourceId": item.source_id,
                "sourceName": item.source_name,
                "title": item.title,
                "url": item.url,
                "publishedAt": item.published_at,
                "summary": item.summary,
            }
            for item in outcome.items
        ],
        "error": outcome.error,
        "retryable": outcome.retryable,
    }


def _market_snapshot_mapping(snapshot: MarketSnapshot) -> dict[str, object]:
    return {
        "status": snapshot.status,
        "providers": [
            {
                "provider": result.provider,
                "status": result.status,
                "values": result.values,
                "error": result.error,
                "stage": result.stage,
            }
            for result in snapshot.providers
        ],
        "values": snapshot.values,
        "gaps": list(snapshot.gaps),
    }


def _report_decision_mapping(decision: ReportDecision) -> dict[str, object]:
    return {
        "disposition": decision.disposition,
        "reportType": decision.report_type,
        "reused": decision.reused,
        "warnings": list(decision.warnings),
    }


def _require_exact_keys(
    value: object, expected: frozenset[str], label: str
) -> dict[str, object]:
    if type(value) is not dict or set(value) != expected:
        raise ValueError(f"{label} keys do not match")
    return value


def _timestamp(value: object, field_name: str) -> datetime:
    if type(value) is not str:
        raise ValueError(f"{field_name} must be a timestamp string")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{field_name} must be an ISO timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{field_name} must include a timezone")
    return parsed


def _optional_timestamp(value: object, field_name: str) -> datetime | None:
    return None if value is None else _timestamp(value, field_name)


def _utc_iso(value: datetime) -> str:
    return value.astimezone(_UTC).isoformat().replace("+00:00", "Z")


def _string(value: object, field_name: str) -> str:
    if type(value) is not str or not value.strip():
        raise ValueError(f"{field_name} must be a nonempty string")
    return value


def _string_list(value: object, field_name: str) -> tuple[str, ...]:
    if type(value) is not list or any(
        type(item) is not str or not item for item in value
    ):
        raise ValueError(f"{field_name} must be a list of nonempty strings")
    return tuple(value)


def _collapsed(value: object) -> str:
    return " ".join(value.split()) if type(value) is str else ""
