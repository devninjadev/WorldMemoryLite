"""Ephemeral, byte-bounded paging for one collected feed window."""

from __future__ import annotations

import json
import os
from pathlib import Path
import re
import secrets
import tempfile
import time
from typing import Mapping, Sequence


DEFAULT_SNAPSHOT_DIRECTORY = (
    Path(tempfile.gettempdir()) / "world-memory-feed-snapshots-v1"
)
PAGE_ITEM_BUDGET_BYTES = 16_384
PAGE_ITEM_LIMIT = 20
SNAPSHOT_TTL_SECONDS = 24 * 60 * 60

_SNAPSHOT_ID = re.compile(r"[0-9a-f]{32}\Z")
_SNAPSHOT_KEYS = frozenset(
    {"version", "createdAtEpoch", "itemCount", "pageStarts", "pages"}
)


def create_feed_snapshot(
    collected: Mapping[str, object],
    *,
    directory: Path = DEFAULT_SNAPSHOT_DIRECTORY,
    now_epoch: float | None = None,
) -> dict[str, object]:
    """Return the first bounded page and retain later pages in temporary storage."""

    if not isinstance(collected, Mapping):
        raise ValueError("collected feed result must be a mapping")
    items = collected.get("items")
    item_count = collected.get("itemCount")
    if type(items) is not list or type(item_count) is not int:
        raise ValueError("collected feed result has invalid items")
    if item_count != len(items):
        raise ValueError("collected feed itemCount does not match items")
    if not isinstance(directory, Path):
        raise ValueError("snapshot directory must be a Path")

    pages = _partition_items(items)
    page_starts = _page_starts(pages)
    snapshot_id: str | None = None
    next_cursor: int | None = None
    now_value = time.time() if now_epoch is None else _epoch(now_epoch)

    if len(pages) > 1:
        directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        _remove_expired_snapshots(directory, now_value)
        snapshot_id = secrets.token_hex(16)
        snapshot = {
            "version": 1,
            "createdAtEpoch": now_value,
            "itemCount": item_count,
            "pageStarts": page_starts,
            "pages": pages,
        }
        _write_snapshot(directory, snapshot_id, snapshot)
        next_cursor = page_starts[1]

    first_page = pages[0]
    result = {key: value for key, value in collected.items() if key != "items"}
    result.update(
        {
            "snapshotId": snapshot_id,
            "cursor": 0,
            "returnedItemCount": len(first_page),
            "items": first_page,
            "nextCursor": next_cursor,
        }
    )
    return result


def read_feed_page(
    snapshot_id: object,
    cursor: object,
    *,
    directory: Path = DEFAULT_SNAPSHOT_DIRECTORY,
    now_epoch: float | None = None,
) -> dict[str, object]:
    """Read one exact continuation page without performing external I/O."""

    if type(snapshot_id) is not str or _SNAPSHOT_ID.fullmatch(snapshot_id) is None:
        raise ValueError("snapshotId is invalid")
    if isinstance(cursor, bool) or not isinstance(cursor, int) or cursor <= 0:
        raise ValueError("cursor must be a positive integer")
    if not isinstance(directory, Path):
        raise ValueError("snapshot directory must be a Path")

    snapshot = _load_snapshot(directory / f"{snapshot_id}.json")
    now_value = time.time() if now_epoch is None else _epoch(now_epoch)
    created_at = _epoch(snapshot["createdAtEpoch"])
    if now_value - created_at > SNAPSHOT_TTL_SECONDS:
        raise ValueError("feed snapshot expired")

    page_starts = snapshot["pageStarts"]
    pages = snapshot["pages"]
    if type(page_starts) is not list or type(pages) is not list:
        raise ValueError("feed snapshot has invalid pages")
    if cursor not in page_starts[1:]:
        raise ValueError("cursor was not issued by this snapshot")
    page_index = page_starts.index(cursor)
    page = pages[page_index]
    if type(page) is not list:
        raise ValueError("feed snapshot page is invalid")
    next_cursor = (
        page_starts[page_index + 1]
        if page_index + 1 < len(page_starts)
        else None
    )
    return {
        "snapshotId": snapshot_id,
        "cursor": cursor,
        "itemCount": snapshot["itemCount"],
        "returnedItemCount": len(page),
        "items": page,
        "nextCursor": next_cursor,
    }


def _partition_items(items: Sequence[object]) -> list[list[object]]:
    if not items:
        return [[]]
    pages: list[list[object]] = []
    current: list[object] = []
    current_bytes = 2
    for item in items:
        if type(item) is not dict:
            raise ValueError("feed item must be an object")
        item_bytes = len(_compact_json(item).encode("utf-8"))
        separator_bytes = 1 if current else 0
        if current and (
            len(current) >= PAGE_ITEM_LIMIT
            or current_bytes + separator_bytes + item_bytes > PAGE_ITEM_BUDGET_BYTES
        ):
            pages.append(current)
            current = []
            current_bytes = 2
            separator_bytes = 0
        current.append(item)
        current_bytes += separator_bytes + item_bytes
    pages.append(current)
    return pages


def _page_starts(pages: Sequence[Sequence[object]]) -> list[int]:
    starts: list[int] = []
    cursor = 0
    for page in pages:
        starts.append(cursor)
        cursor += len(page)
    return starts


def _write_snapshot(
    directory: Path, snapshot_id: str, snapshot: Mapping[str, object]
) -> None:
    final_path = directory / f"{snapshot_id}.json"
    temporary_path = directory / f".{snapshot_id}.tmp"
    descriptor = os.open(
        temporary_path,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL,
        0o600,
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(_compact_json(snapshot))
            handle.write("\n")
        os.replace(temporary_path, final_path)
    except BaseException:
        temporary_path.unlink(missing_ok=True)
        raise


def _load_snapshot(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if type(value) is not dict or frozenset(value) != _SNAPSHOT_KEYS:
        raise ValueError("feed snapshot has invalid shape")
    if value["version"] != 1:
        raise ValueError("feed snapshot version is unsupported")
    item_count = value["itemCount"]
    pages = value["pages"]
    page_starts = value["pageStarts"]
    if type(item_count) is not int or item_count < 0:
        raise ValueError("feed snapshot itemCount is invalid")
    if type(pages) is not list or not pages or type(page_starts) is not list:
        raise ValueError("feed snapshot pages are invalid")
    if _page_starts(pages) != page_starts:
        raise ValueError("feed snapshot cursors are invalid")
    if sum(len(page) for page in pages if type(page) is list) != item_count:
        raise ValueError("feed snapshot itemCount does not match pages")
    return value


def _remove_expired_snapshots(directory: Path, now_epoch: float) -> None:
    cutoff = now_epoch - SNAPSHOT_TTL_SECONDS
    for path in directory.glob("*.json"):
        try:
            if path.stat().st_mtime < cutoff:
                path.unlink()
        except OSError:
            continue


def _compact_json(value: object) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        allow_nan=False,
    )


def _epoch(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("epoch must be a number")
    numeric = float(value)
    if numeric < 0:
        raise ValueError("epoch must be nonnegative")
    return numeric
