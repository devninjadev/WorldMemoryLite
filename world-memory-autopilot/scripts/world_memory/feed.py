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
    max_workers: int = 5,
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
        return FeedOutcome(
            source_id=feed.id,
            source_name=feed.name,
            status="ok",
            items=_parse_csv(feed, response),
            error="",
            retryable=False,
        )
    except (TypeError, UnicodeError, ValueError, csv.Error) as exc:
        return _error_outcome(feed, exc, category="feed_parse", retryable=False)


def _parse_csv(feed: FeedSpec, response: bytes) -> tuple[FeedItem, ...]:
    if not isinstance(response, bytes):
        raise TypeError("feed response must be UTF-8 bytes")
    text = response.decode("utf-8", errors="strict")
    if text.startswith("\ufeff"):
        raise ValueError("RSS.app CSV must be UTF-8 without a BOM")

    reader = csv.DictReader(StringIO(text))
    if tuple(reader.fieldnames or ()) != _CSV_HEADERS:
        raise ValueError("RSS.app CSV header does not match the required schema")

    items: list[FeedItem] = []
    for row in reader:
        title = _collapsed(row.get("Title"))
        date_text = _collapsed(row.get("Date"))
        if not title or not date_text:
            raise ValueError("RSS.app CSV rows require nonempty Title and Date")
        source_url = _collapsed(row.get("Link")) or feed.url
        canonical_url = _canonical_url(source_url)
        published_at = _normalize_timestamp(date_text, feed.published_at_offset_minutes)
        summary_source = row.get("Plain Description")
        if not _collapsed(summary_source):
            summary_source = row.get("Description")
        summary = normalize_feed_summary(summary_source)
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
    return tuple(items)


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
