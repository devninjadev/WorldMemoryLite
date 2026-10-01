"""One optional RSS discovery request per invocation; never retry a saved outcome."""
import argparse
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
import json
from pathlib import Path
import subprocess
import xml.etree.ElementTree as ET
from urllib.parse import urlsplit

from world_memory.feed import normalize_feed_summary

URL = "https://www.financialjuice.com/feed.ashx?xy=rss"


FEEDS = {
    "financialjuice": (URL, 0),
    "first_squawk": ("https://rss.app/feeds/d68ow40E3dkwaEvN.xml", -540),
    "reuters": ("https://rss.app/feeds/_fSiPEQ8FZXQdj4js.xml", 0),
    "dow_jones": ("https://rss.app/feeds/_m6HwVpkVbkV6H1V6.xml", 0),
    "bloomberg": ("https://rss.app/feeds/_t07deORnyZW90CjC.xml", 0),
}


def parse_rss(body, feed="financialjuice"):
    _, offset = FEEDS[feed]
    if b"<!DOCTYPE" in body.upper() or b"<!ENTITY" in body.upper():
        raise ValueError("unsafe-xml")
    root = ET.fromstring(body)
    if root.tag != "rss":
        raise ValueError("not-rss")
    items, seen, rejected = [], set(), 0
    for row in root.findall("./channel/item"):
        title = normalize_feed_summary(row.findtext("title") or "")
        link = (row.findtext("link") or "").strip()
        guid = (row.findtext("guid") or "").strip()
        try:
            raw_date = row.findtext("pubDate") or ""
            date = None if not raw_date and feed != "financialjuice" else parsedate_to_datetime(raw_date)
            if not title or not guid or (date is not None and date.tzinfo is None):
                raise ValueError("missing-fields")
            if urlsplit(link).scheme not in {"http", "https"} or not urlsplit(link).netloc:
                raise ValueError("invalid-link")
        except (ValueError, TypeError, AttributeError):
            rejected += 1
            continue
        if guid in seen:
            continue
        seen.add(guid)
        items.append({"id": feed + ":" + guid, "guid": guid,
                      "title": title, "url": link,
                      "publishedAt": (date.astimezone(timezone.utc) + timedelta(minutes=offset)).isoformat() if date else None,
                      "description": normalize_feed_summary(row.findtext("description") or "")})
    items.sort(key=lambda item: item["publishedAt"] or "", reverse=True)
    dated = [item for item in items if item["publishedAt"]]
    return {"undatedCount": len(items) - len(dated), "status": "ok" if items else "unavailable", "items": items,
            "count": len(items), "rejectedCount": rejected,
            "oldestPublishedAt": dated[-1]["publishedAt"] if dated else None,
            "newestPublishedAt": dated[0]["publishedAt"] if dated else None}


def collect(snapshot_dir, feed="financialjuice"):
    url, _ = FEEDS[feed]
    directory = Path(snapshot_dir)
    if feed != "financialjuice":
        directory = directory / feed
    directory.mkdir(parents=True, exist_ok=True)
    result_path = directory / "result.json"
    if result_path.exists():
        return json.loads(result_path.read_text())
    # Exclusive marker also prevents a second request after a crash or overlap.
    try:
        with (directory / "attempted").open("x") as marker:
            marker.write(datetime.now(timezone.utc).isoformat())
    except FileExistsError:
        return {"status": "unavailable", "reason": "already-attempted", "items": []}
    result = {"status": "unavailable", "source": url, "items": [],
              "retrievedAt": datetime.now(timezone.utc).isoformat()}
    body_path = directory / "response.xml"
    try:
        response = subprocess.run(
            ["curl", "--silent", "--show-error", "--max-time", "25",
             "--max-filesize", "2097152", "--output", str(body_path),
             "--write-out", "%{http_code}", url],
            capture_output=True, text=True, timeout=30, check=False)
        status = response.stdout.strip()
        result["httpStatus"] = status
        if response.returncode != 0 or status != "200":
            result["reason"] = "rate-limited" if status == "429" else "transport-failed"
        else:
            result.update(parse_rss(body_path.read_bytes(), feed))
            if result["status"] != "ok":
                result["reason"] = "empty-feed"
    except (OSError, subprocess.TimeoutExpired):
        result["reason"] = "transport-unavailable"
    except (ValueError, ET.ParseError):
        result["reason"] = "invalid-rss"
    result_path.write_text(json.dumps(result, ensure_ascii=False))
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot-dir", required=True)
    parser.add_argument("--feed", choices=FEEDS, default="financialjuice")
    args = parser.parse_args()
    print(json.dumps(collect(args.snapshot_dir, args.feed), ensure_ascii=False))
