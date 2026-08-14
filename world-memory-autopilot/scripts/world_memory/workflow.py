"""Pure write-response and user-result decisions for Notion-native runs.

This module neither calls Notion nor retries a mutation.  It classifies an
already returned connector value and builds a concise, user-visible result.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from .feed import FEEDS, FeedOutcome
from .market import MarketSnapshot, validate_market_snapshot
from .registry import normalize_uuid, notion_page_id_from_url


_WRITE_STATUSES = frozenset({"confirmed", "verify-once", "failed"})
_UNCERTAIN_RESPONSE_STATUSES = frozenset({"timeout", "uncertain", "unknown"})
_FAILED_RESPONSE_STATUSES = frozenset({"error", "failed", "failure"})
_CONFIRMED_RESPONSE_STATUSES = frozenset({"ok", "success", "confirmed"})
_MARKET_USER_STATUS = {
    "ok": "complete",
    "partial": "partial",
    "unavailable": "unavailable",
}


@dataclass(frozen=True)
class WriteOutcome:
    """One deterministic decision about an already returned write response."""

    kind: str
    status: str
    locator: str
    warning: str

    def __post_init__(self) -> None:
        if type(self.kind) is not str or not self.kind.strip():
            raise ValueError("kind must be a nonempty string")
        if self.status not in _WRITE_STATUSES:
            raise ValueError("status must be confirmed, verify-once, or failed")
        if type(self.locator) is not str:
            raise ValueError("locator must be a string")
        if type(self.warning) is not str:
            raise ValueError("warning must be a string")


def resolve_write_response(kind: str, response: object) -> WriteOutcome:
    """Classify one connector response without readback or duplicate writing."""

    normalized_kind = _nonempty_string(kind, "kind")
    if not isinstance(response, Mapping):
        return _failed(normalized_kind)

    if response.get("object") == "async_task":
        return _resolve_async_response(normalized_kind, response)

    if "status" in response and type(response.get("status")) is not str:
        return _failed(normalized_kind)
    response_status = response.get("status")
    if response_status in _FAILED_RESPONSE_STATUSES:
        return _failed(normalized_kind)
    if response_status in _UNCERTAIN_RESPONSE_STATUSES:
        locator = _uncertain_locator(response)
        if locator:
            return WriteOutcome(
                normalized_kind,
                "verify-once",
                locator,
                (
                    f"{normalized_kind} write is uncertain; fetch the exact "
                    "locator once and do not retry"
                ),
            )
        return _failed(normalized_kind)
    if response_status is not None and response_status not in _CONFIRMED_RESPONSE_STATUSES:
        return _failed(normalized_kind)

    return _resolve_sync_response(normalized_kind, response)


def _resolve_async_response(
    kind: str, response: Mapping[object, object]
) -> WriteOutcome:
    status = response.get("status")
    if type(status) is not str:
        return _failed(kind)
    if status != "succeeded":
        return _failed(kind)
    result = response.get("result")
    if not isinstance(result, Mapping):
        return _failed(kind)
    return _resolve_sync_response(kind, result)


def _resolve_sync_response(
    kind: str, response: Mapping[object, object]
) -> WriteOutcome:
    if "status" in response:
        status = response.get("status")
        if type(status) is not str or status not in _CONFIRMED_RESPONSE_STATUSES:
            return _failed(kind)
    response_object = response.get("object")
    if response_object is not None and response_object != "page":
        return _failed(kind)

    if "pages" in response:
        pages = response.get("pages")
        if not isinstance(pages, (list, tuple)) or not pages:
            return _failed(kind)
        locator = _confirmed_page_locator(pages[0])
        if locator:
            return WriteOutcome(kind, "confirmed", locator, "")
        return _failed(kind)

    direct_locator = _confirmed_page_locator(response)
    if direct_locator:
        return WriteOutcome(kind, "confirmed", direct_locator, "")
    return _failed(kind)


def build_user_result(
    *,
    report_markdown: str,
    report_outcome: WriteOutcome,
    feed_outcomes: Iterable[FeedOutcome],
    market: MarketSnapshot,
    collection_outcome: WriteOutcome | None = None,
    story_created: int = 0,
    story_updated: int = 0,
    changes_created: int = 0,
    warnings: Iterable[str] = (),
) -> dict[str, object]:
    """Build the user-visible completion/degradation summary for one run."""

    if type(report_markdown) is not str:
        raise ValueError("report_markdown must be a string")
    if not isinstance(report_outcome, WriteOutcome):
        raise ValueError("report_outcome must be a WriteOutcome")
    if collection_outcome is not None and not isinstance(
        collection_outcome, WriteOutcome
    ):
        raise ValueError("collection_outcome must be a WriteOutcome or None")
    outcomes = _feed_outcomes(feed_outcomes)
    market = _market_snapshot(market)
    _validate_outcome_roles(
        report_outcome=report_outcome,
        collection_outcome=collection_outcome,
        report_markdown=report_markdown,
    )
    _validate_feed_state(report_outcome.kind, outcomes)
    counts = (
        _count(story_created, "story_created"),
        _count(story_updated, "story_updated"),
        _count(changes_created, "changes_created"),
    )
    _validate_prewrite_counts(report_outcome, counts)

    success_count = sum(outcome.status == "ok" for outcome in outcomes)
    failure_count = len(outcomes) - success_count
    visible_warnings = _warnings(
        warnings,
        report_outcome,
        collection_outcome,
        outcomes,
        market,
    )
    status = _user_status(
        report_outcome=report_outcome,
        collection_outcome=collection_outcome,
        outcomes=outcomes,
        market=market,
        warnings=visible_warnings,
    )
    report_url = _notion_url(report_outcome.locator)
    link_first_delivery = (
        report_outcome.status == "confirmed"
        and report_outcome.kind in {"report", "reused"}
        and bool(report_url)
    )

    return {
        "status": status,
        "reportMarkdown": "" if link_first_delivery else report_markdown,
        "reportUrl": report_url if link_first_delivery else "",
        "collectionStatus": (
            collection_outcome.status
            if collection_outcome is not None
            else "not-requested"
        ),
        "feedSuccessCount": success_count,
        "feedFailureCount": failure_count,
        "marketStatus": _MARKET_USER_STATUS[market.status],
        "storyCreatedCount": counts[0],
        "storyUpdatedCount": counts[1],
        "storyChangeCreatedCount": counts[2],
        "warnings": list(visible_warnings),
    }


def _failed(kind: str) -> WriteOutcome:
    return WriteOutcome(kind, "failed", "", f"{kind} write was not confirmed")


def _confirmed_page_locator(value: object) -> str:
    if not isinstance(value, Mapping):
        return ""
    identifier = _canonical_page_id(value.get("id"))
    if not identifier:
        return ""
    if "url" not in value:
        return identifier
    url = _valid_notion_url(value.get("url"))
    if not url:
        return ""
    try:
        url_identifier = notion_page_id_from_url(url)
    except ValueError:
        return ""
    return url if url_identifier == identifier else ""


def _uncertain_locator(value: Mapping[object, object]) -> str:
    url = _valid_notion_url(value.get("url"))
    page_id = _canonical_page_id(value.get("page_id"))
    if url and page_id:
        try:
            if notion_page_id_from_url(url) != page_id:
                return ""
        except ValueError:
            return ""
    return url or page_id


def _user_status(
    *,
    report_outcome: WriteOutcome,
    collection_outcome: WriteOutcome | None,
    outcomes: tuple[FeedOutcome, ...],
    market: MarketSnapshot,
    warnings: tuple[str, ...],
) -> str:
    if report_outcome.kind == "reused" and report_outcome.status == "confirmed":
        return "reused"
    if report_outcome.kind == "safe-stop":
        return "safe-stop"
    if report_outcome.status != "confirmed":
        return "storage-failed"
    if (
        any(outcome.status != "ok" for outcome in outcomes)
        or market.status != "ok"
        or (
            collection_outcome is not None
            and collection_outcome.status != "confirmed"
        )
        or warnings
    ):
        return "degraded"
    return "completed"


def _warnings(
    explicit: Iterable[str],
    report_outcome: WriteOutcome,
    collection_outcome: WriteOutcome | None,
    outcomes: tuple[FeedOutcome, ...],
    market: MarketSnapshot,
) -> tuple[str, ...]:
    values = list(_string_iterable(explicit, "warnings"))
    if report_outcome.warning:
        values.append(report_outcome.warning)
    if collection_outcome is not None and collection_outcome.warning:
        values.append(collection_outcome.warning)
    values.extend(
        f"{outcome.source_name}: {outcome.error}"
        for outcome in outcomes
        if outcome.status != "ok"
    )
    values.extend(market.gaps)
    return tuple(dict.fromkeys(value for value in values if value))


def _feed_outcomes(value: Iterable[FeedOutcome]) -> tuple[FeedOutcome, ...]:
    if isinstance(value, (str, bytes)):
        raise ValueError("feed_outcomes must contain FeedOutcome values")
    try:
        outcomes = tuple(value)
    except TypeError as exc:
        raise ValueError("feed_outcomes must be iterable") from exc
    if not all(isinstance(outcome, FeedOutcome) for outcome in outcomes):
        raise ValueError("feed_outcomes must contain FeedOutcome values")
    if any(outcome.status not in {"ok", "error"} for outcome in outcomes):
        raise ValueError("FeedOutcome status must be ok or error")
    return outcomes


def _market_snapshot(value: object) -> MarketSnapshot:
    return validate_market_snapshot(value)


def _validate_outcome_roles(
    *,
    report_outcome: WriteOutcome,
    collection_outcome: WriteOutcome | None,
    report_markdown: str,
) -> None:
    if report_outcome.kind not in {"report", "reused", "safe-stop"}:
        raise ValueError("report_outcome kind is not valid for the report role")
    if collection_outcome is not None and collection_outcome.kind != "collection":
        raise ValueError("collection_outcome kind must be collection")

    if report_outcome.kind == "reused":
        if report_outcome.status != "confirmed":
            raise ValueError("reused report outcome status must be confirmed")
        if collection_outcome is not None:
            raise ValueError("reused report outcome cannot include a collection outcome")
    elif report_outcome.kind == "safe-stop":
        if report_outcome.status != "failed" or report_outcome.locator:
            raise ValueError("safe-stop outcome must be an unlocated failed outcome")
        if report_markdown:
            raise ValueError("safe-stop is pre-write and cannot include report markdown")
        if collection_outcome is not None:
            raise ValueError("safe-stop cannot include a collection outcome")

    _validate_outcome_locator(report_outcome, "report_outcome")
    if collection_outcome is not None:
        _validate_outcome_locator(collection_outcome, "collection_outcome")


def _validate_outcome_locator(outcome: WriteOutcome, field_name: str) -> None:
    located = bool(_canonical_page_id(outcome.locator) or _valid_notion_url(outcome.locator))
    if outcome.status in {"confirmed", "verify-once"} and not located:
        raise ValueError(f"{field_name} requires a valid Notion page locator")
    if outcome.status == "failed" and outcome.locator:
        raise ValueError(f"{field_name} failed status cannot contain a locator")


def _validate_feed_state(
    report_kind: str, outcomes: tuple[FeedOutcome, ...]
) -> None:
    if report_kind == "reused":
        if outcomes:
            raise ValueError("reused outcome must not contain fresh feed outcomes")
        return

    configured_ids = tuple(feed.id for feed in FEEDS)
    if tuple(outcome.source_id for outcome in outcomes) != configured_ids:
        raise ValueError("fresh result requires the configured five feeds in order")
    success_count = sum(outcome.status == "ok" for outcome in outcomes)
    if report_kind == "safe-stop":
        if success_count:
            raise ValueError("safe-stop requires all configured feeds to fail")
    elif success_count == 0:
        raise ValueError("fresh report requires at least one successful feed")


def _validate_prewrite_counts(
    report_outcome: WriteOutcome, counts: tuple[int, int, int]
) -> None:
    if report_outcome.kind in {"safe-stop", "reused"} and any(counts):
        raise ValueError(
            f"{report_outcome.kind} Story counts must all be zero"
        )
    if report_outcome.status != "confirmed" and any(counts):
        raise ValueError("unconfirmed Report Story counts must all be zero")


def _count(value: object, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{field_name} must be a nonnegative integer")
    return value


def _string_iterable(value: Iterable[str], field_name: str) -> tuple[str, ...]:
    if isinstance(value, (str, bytes)):
        raise ValueError(f"{field_name} must be an iterable of strings")
    try:
        values = tuple(value)
    except TypeError as exc:
        raise ValueError(f"{field_name} must be an iterable of strings") from exc
    if any(type(item) is not str for item in values):
        raise ValueError(f"{field_name} must be an iterable of strings")
    return values


def _notion_url(value: object) -> str:
    return _valid_notion_url(value)


def _valid_notion_url(value: object) -> str:
    if type(value) is not str or not value or value != value.strip():
        return ""
    try:
        notion_page_id_from_url(value)
    except ValueError:
        return ""
    return value


def _canonical_page_id(value: object) -> str:
    if type(value) is not str:
        return ""
    try:
        normalized = normalize_uuid(value, "page id")
    except ValueError:
        return ""
    return normalized if value == normalized else ""


def _string_value(value: object) -> str:
    return value.strip() if type(value) is str and value.strip() else ""


def _nonempty_string(value: object, field_name: str) -> str:
    normalized = _string_value(value)
    if not normalized:
        raise ValueError(f"{field_name} must be a nonempty string")
    return normalized
