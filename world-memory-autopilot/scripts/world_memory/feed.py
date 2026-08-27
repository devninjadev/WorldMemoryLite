"""Bounded, direct-HTTP-friendly collection of RSS.app CSV feeds.

This module deliberately keeps source results invocation-local.  It does not
write cursors, keys, digests, or any other durable collection state.
"""

from __future__ import annotations

import csv
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from html import unescape
from html.parser import HTMLParser
from io import StringIO
import re
from typing import Callable, Iterable
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse
from urllib.request import Request, urlopen


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
_TRACKING_PARAMETERS = {"fbclid", "gclid"}
_UTC = timezone.utc
_USER_AGENT = "WorldMemoryAutopilot/0.14.4 (feed contract verifier)"
_BLOCKED_SUMMARY_TAGS = frozenset({"script", "style", "iframe", "object"})
_VOID_BLOCKED_SUMMARY_TAGS = frozenset({"embed"})
_BLOCKED_MARKUP_IN_RAW_TEXT = re.compile(
    r"<\s*(/?)\s*(script|style|iframe|object|embed)\b[^>]*>",
    re.IGNORECASE,
)
_SUMMARY_BOUNDARY_TAGS = frozenset(
    {
        "address",
        "article",
        "aside",
        "blockquote",
        "br",
        "dd",
        "details",
        "div",
        "dl",
        "dt",
        "figcaption",
        "figure",
        "footer",
        "form",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "header",
        "hr",
        "li",
        "main",
        "nav",
        "ol",
        "p",
        "pre",
        "section",
        "summary",
        "table",
        "tbody",
        "td",
        "tfoot",
        "th",
        "thead",
        "tr",
        "ul",
    }
)


@dataclass(frozen=True)
class FeedSpec:
    """The immutable direct-HTTP configuration for one RSS.app source."""

    id: str
    name: str
    url: str
    published_at_offset_minutes: int = 0


FEEDS: tuple[FeedSpec, ...] = (
    FeedSpec("financial_juice", "FinancialJuice", "https://rss.app/feeds/5VaycMAa8SwPhOAP.csv"),
    FeedSpec("walter_bloomberg", "Walter Bloomberg", "https://rss.app/feeds/YcRRdWN5eSO3o2LP.csv"),
    FeedSpec("wall_st_engine", "Wall St Engine", "https://rss.app/feeds/Hf52VRUllNu7gABF.csv"),
    FeedSpec("first_squawk", "First Squawk", "https://rss.app/feeds/d68ow40E3dkwaEvN.csv", -540),
    FeedSpec("unusual_whales", "unusual_whales", "https://rss.app/feeds/nikLNBATmLDuprRz.csv", -540),
    FeedSpec("reuters", "Reuters", "https://rss.app/feeds/_fSiPEQ8FZXQdj4js.csv"),
    FeedSpec("dow_jones", "Dow Jones Personal", "https://rss.app/feeds/_m6HwVpkVbkV6H1V6.csv"),
    FeedSpec("bloomberg", "Bloomberg Personal", "https://rss.app/feeds/_t07deORnyZW90CjC.csv"),
)


@dataclass(frozen=True)
class FeedItem:
    """A normalized source item, suitable only for the current invocation."""

    item_id: str
    source_id: str
    source_name: str
    title: str
    url: str
    published_at: str
    summary: str


@dataclass(frozen=True)
class FeedOutcome:
    """One source's result, preserving successes beside independent failures."""

    source_id: str
    source_name: str
    status: str
    items: tuple[FeedItem, ...]
    error: str
    retryable: bool
    rejected_item_count: int = 0


Fetcher = Callable[[str, float], bytes]


class _FeedSummaryParser(HTMLParser):
    """Extract visible text without retaining executable or embedded subtrees."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=False)
        self.parts: list[str] = []
        self.blocked_tags: list[str] = []
        self.pending_blocked_closers: list[str] = []

    def handle_starttag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        del attrs
        tag = tag.lower()
        if self.blocked_tags:
            if tag in _BLOCKED_SUMMARY_TAGS:
                self._enter_blocked(tag)
            return
        if tag in _BLOCKED_SUMMARY_TAGS:
            self.parts.append(" ")
            self._enter_blocked(tag)
            return
        if tag in _VOID_BLOCKED_SUMMARY_TAGS:
            self.parts.append(" ")
            return
        if tag in _SUMMARY_BOUNDARY_TAGS:
            self.parts.append(" ")

    def handle_startendtag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        del attrs
        tag = tag.lower()
        if not self.blocked_tags and (
            tag in _BLOCKED_SUMMARY_TAGS
            or tag in _VOID_BLOCKED_SUMMARY_TAGS
            or tag in _SUMMARY_BOUNDARY_TAGS
        ):
            self.parts.append(" ")

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if self.blocked_tags:
            self._leave_blocked(tag)
            return
        if tag in _SUMMARY_BOUNDARY_TAGS:
            self.parts.append(" ")

    def handle_data(self, data: str) -> None:
        if self.blocked_tags:
            # HTMLParser treats script/style bodies as raw text. Track only
            # structural blocked-tag markers inside that body so crossed
            # closers cannot release attacker-controlled text early.
            for match in _BLOCKED_MARKUP_IN_RAW_TEXT.finditer(data):
                closing, tag = match.groups()
                tag = tag.lower()
                if tag in _VOID_BLOCKED_SUMMARY_TAGS:
                    continue
                if closing:
                    self._leave_blocked(tag)
                else:
                    self._enter_blocked(tag)
            return
        self.parts.append(data)

    def handle_entityref(self, name: str) -> None:
        if not self.blocked_tags:
            self.parts.append(f"&{name};")

    def handle_charref(self, name: str) -> None:
        if not self.blocked_tags:
            self.parts.append(f"&#{name};")

    def _enter_blocked(self, tag: str) -> None:
        self.blocked_tags.append(tag)

    def _leave_blocked(self, tag: str) -> None:
        if tag == self.blocked_tags[-1]:
            self.blocked_tags.pop()
            while (
                self.blocked_tags
                and self.blocked_tags[-1] in self.pending_blocked_closers
            ):
                pending = self.blocked_tags.pop()
                self.pending_blocked_closers.remove(pending)
            if not self.blocked_tags:
                self.pending_blocked_closers.clear()
                self.parts.append(" ")
            return
        if tag in self.blocked_tags and tag not in self.pending_blocked_closers:
            self.pending_blocked_closers.append(tag)


def normalize_feed_summary(value: object) -> str:
    """Return collapsed visible text from one untrusted RSS summary value."""

    if type(value) is not str:
        return ""
    parser = _FeedSummaryParser()
    parser.feed(value)
    parser.close()
    return " ".join(unescape("".join(parser.parts)).split())


def collect_feeds(
    fetcher: Fetcher,
    *,
    now: datetime,
    timeout: float = 20.0,
    max_workers: int = 8,
) -> tuple[FeedOutcome, ...]:
    """Fetch all configured CSV feeds concurrently and return configured order."""
    _require_aware_datetime(now, "now")
    if not callable(fetcher):
        raise ValueError("fetcher must be callable")
    if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or timeout <= 0:
        raise ValueError("timeout must be a positive number")
    if isinstance(max_workers, bool) or not isinstance(max_workers, int) or max_workers <= 0:
        raise ValueError("max_workers must be a positive integer")

    outcomes: dict[str, FeedOutcome] = {}
    with ThreadPoolExecutor(max_workers=min(max_workers, len(FEEDS))) as executor:
        pending = {
            executor.submit(_collect_one, feed, fetcher, float(timeout)): feed
            for feed in FEEDS
        }
        for future in as_completed(pending):
            feed = pending[future]
            try:
                outcomes[feed.id] = future.result()
            except Exception as exc:  # Defensive worker boundary; collection remains partial.
                outcomes[feed.id] = _error_outcome(
                    feed, exc, category="feed_worker", retryable=True
                )
    return tuple(outcomes[feed.id] for feed in FEEDS)


def direct_http_fetch(url: str, timeout: float) -> bytes:
    """Fetch one configured RSS.app CSV over a cache-bypassing public GET."""

    if url not in {feed.url for feed in FEEDS}:
        raise ValueError("url must identify a configured feed")
    if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or timeout <= 0:
        raise ValueError("timeout must be a positive number")
    request = Request(
        url,
        headers={
            "User-Agent": _USER_AGENT,
            "Accept": "text/csv,text/plain;q=0.9,*/*;q=0.1",
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
        },
        method="GET",
    )
    with urlopen(request, timeout=float(timeout)) as response:
        status = getattr(response, "status", None) or response.getcode()
        if not isinstance(status, int) or status < 200 or status >= 300:
            raise OSError("feed response was not successful")
        return response.read()


def collect_feed_window(
    fetcher: Fetcher,
    *,
    window_start: datetime,
    window_end: datetime,
    fetched_at: datetime,
    timeout: float = 20.0,
    max_workers: int = 8,
) -> dict[str, object]:
    """Collect, normalize, window-filter, and diagnose all configured feeds."""

    window_start = _require_aware_datetime(window_start, "window_start").astimezone(_UTC)
    window_end = _require_aware_datetime(window_end, "window_end").astimezone(_UTC)
    fetched_at = _require_aware_datetime(fetched_at, "fetched_at").astimezone(_UTC)
    if window_start >= window_end:
        raise ValueError("window_start must be before window_end")
    if window_end > fetched_at:
        raise ValueError("window_end must not be after fetched_at")

    outcomes = collect_feeds(
        fetcher,
        now=fetched_at,
        timeout=timeout,
        max_workers=max_workers,
    )
    filtered_outcomes: list[FeedOutcome] = []
    latest_by_source: dict[str, str | None] = {}
    parsed_counts: dict[str, int] = {}
    window_counts: dict[str, int] = {}
    for outcome in outcomes:
        parsed_counts[outcome.source_id] = len(outcome.items)
        published = tuple(_item_timestamp(item) for item in outcome.items)
        latest_by_source[outcome.source_id] = (
            _utc_iso(max(published)) if published else None
        )
        window_items = tuple(
            item
            for item, published_at in zip(outcome.items, published)
            if window_start <= published_at < window_end
        )
        window_counts[outcome.source_id] = len(window_items)
        filtered_outcomes.append(
            FeedOutcome(
                source_id=outcome.source_id,
                source_name=outcome.source_name,
                status=outcome.status,
                items=window_items,
                error=outcome.error,
                retryable=outcome.retryable,
                rejected_item_count=outcome.rejected_item_count,
            )
        )

    retained = deduplicate_items(filtered_outcomes)
    retained_counts = {feed.id: 0 for feed in FEEDS}
    for item in retained:
        retained_counts[item.source_id] += 1
    success_count = sum(outcome.status == "ok" for outcome in outcomes)
    failure_count = len(outcomes) - success_count
    status = "failed" if success_count == 0 else "partial" if failure_count else "complete"

    return {
        "status": status,
        "windowStart": _utc_iso(window_start),
        "windowEnd": _utc_iso(window_end),
        "fetchedAt": _utc_iso(fetched_at),
        "retrievalMethod": "direct-http",
        "feedSuccessCount": success_count,
        "feedFailureCount": failure_count,
        "itemCount": len(retained),
        "sourceOutcomes": [
            {
                "sourceId": outcome.source_id,
                "sourceName": outcome.source_name,
                "status": outcome.status,
                "parsedItemCount": parsed_counts[outcome.source_id],
                "rejectedItemCount": outcome.rejected_item_count,
                "windowItemCount": window_counts[outcome.source_id],
                "retainedItemCount": retained_counts[outcome.source_id],
                "latestPublishedAt": latest_by_source[outcome.source_id],
                "error": outcome.error,
                "retryable": outcome.retryable,
            }
            for outcome in outcomes
        ],
        "items": [_feed_item_mapping(item) for item in retained],
    }


def deduplicate_items(outcomes: Iterable[FeedOutcome]) -> tuple[FeedItem, ...]:
    """Keep the first configured occurrence of each canonical article URL."""
    seen: set[str] = set()
    retained: list[FeedItem] = []
    for outcome in outcomes:
        if not isinstance(outcome, FeedOutcome) or outcome.status != "ok":
            continue
        for item in outcome.items:
            canonical_url = _canonical_url(item.url)
            if canonical_url in seen:
                continue
            seen.add(canonical_url)
            retained.append(item)
    return tuple(retained)


def _item_timestamp(item: FeedItem) -> datetime:
    try:
        parsed = datetime.fromisoformat(item.published_at.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("normalized feed timestamp is invalid") from exc
    return _require_aware_datetime(parsed, "published_at").astimezone(_UTC)


def _feed_item_mapping(item: FeedItem) -> dict[str, object]:
    return {
        "itemId": item.item_id,
        "sourceId": item.source_id,
        "sourceName": item.source_name,
        "title": item.title,
        "url": item.url,
        "publishedAt": item.published_at,
        "summary": item.summary,
    }


def _utc_iso(value: datetime) -> str:
    return value.astimezone(_UTC).isoformat().replace("+00:00", "Z")


def _collect_one(feed: FeedSpec, fetcher: Fetcher, timeout: float) -> FeedOutcome:
    try:
        response = fetcher(feed.url, timeout)
    except Exception as exc:
        return _error_outcome(
            feed,
            exc,
            category="feed_fetch",
            retryable=isinstance(exc, (OSError, TimeoutError)),
        )

    try:
        items, rejected_item_count = _parse_csv(feed, response)
        return FeedOutcome(
            source_id=feed.id,
            source_name=feed.name,
            status="ok",
            items=items,
            error="",
            retryable=False,
            rejected_item_count=rejected_item_count,
        )
    except (TypeError, UnicodeError, ValueError, csv.Error) as exc:
        return _error_outcome(feed, exc, category="feed_parse", retryable=False)


def _parse_csv(feed: FeedSpec, response: bytes) -> tuple[tuple[FeedItem, ...], int]:
    if not isinstance(response, bytes):
        raise TypeError("feed response must be UTF-8 bytes")
    text = response.decode("utf-8", errors="strict")
    if text.startswith("\ufeff"):
        raise ValueError("RSS.app CSV must be UTF-8 without a BOM")

    reader = csv.DictReader(StringIO(text))
    if tuple(reader.fieldnames or ()) != _CSV_HEADERS:
        raise ValueError("RSS.app CSV header does not match the required schema")

    items: list[FeedItem] = []
    rejected_item_count = 0
    for row in reader:
        try:
            title = _collapsed(row.get("Title"))
            date_text = _collapsed(row.get("Date"))
            if not date_text:
                raise ValueError("RSS.app CSV rows require a nonempty Date")
            source_url = _collapsed(row.get("Link")) or feed.url
            canonical_url = _canonical_url(source_url)
            published_at = _normalize_timestamp(
                date_text, feed.published_at_offset_minutes
            )
            summary_source = row.get("Plain Description")
            if not _collapsed(summary_source):
                summary_source = row.get("Description")
            summary = normalize_feed_summary(summary_source)
            if not title:
                title = summary
            if not title:
                raise ValueError("RSS.app CSV rows require Title or Description text")
            item_id = "\x1f".join((feed.id, canonical_url, title, published_at))
            items.append(
                FeedItem(
                    item_id=item_id,
                    source_id=feed.id,
                    source_name=feed.name,
                    title=title,
                    url=source_url,
                    published_at=published_at,
                    summary=summary,
                )
            )
        except (TypeError, UnicodeError, ValueError):
            rejected_item_count += 1
    if rejected_item_count and not items:
        raise ValueError("RSS.app CSV contains rows but none are valid")
    return tuple(items), rejected_item_count


def _normalize_timestamp(value: str, offset_minutes: int) -> str:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        try:
            parsed = parsedate_to_datetime(value)
        except (TypeError, ValueError) as exc:
            raise ValueError("RSS.app Date must be an ISO 8601 or RFC 2822 timestamp") from exc
    parsed = _require_aware_datetime(parsed, "RSS.app Date")
    normalized = parsed.astimezone(_UTC) + timedelta(minutes=offset_minutes)
    return normalized.isoformat().replace("+00:00", "Z")


def _canonical_url(value: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
        raise ValueError("URL must use HTTP(S) and include a host")
    hostname = parsed.hostname.lower()
    try:
        port = parsed.port
    except ValueError as exc:
        raise ValueError("URL has an invalid port") from exc
    if port is not None and not ((parsed.scheme.lower() == "http" and port == 80) or (parsed.scheme.lower() == "https" and port == 443)):
        hostname = f"{hostname}:{port}"
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("URL must not contain user credentials")
    query = urlencode(
        [
            (key, item)
            for key, item in parse_qsl(parsed.query, keep_blank_values=True)
            if not key.lower().startswith("utm_") and key.lower() not in _TRACKING_PARAMETERS
        ],
        doseq=True,
    )
    return urlunparse((parsed.scheme.lower(), hostname, parsed.path, "", query, ""))


def _collapsed(value: object) -> str:
    return " ".join(value.split()) if isinstance(value, str) else ""


def _error_outcome(
    feed: FeedSpec, exc: Exception, *, category: str, retryable: bool
) -> FeedOutcome:
    return FeedOutcome(feed.id, feed.name, "error", (), _safe_error(category, exc), retryable)


def _safe_error(category: str, exc: Exception) -> str:
    """Return a stable diagnostic code without serializing untrusted exception text."""
    return f"{category}_{exc.__class__.__name__.lower()}"[:240]


def _require_aware_datetime(value: object, field_name: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be a timezone-aware datetime")
    return value
