"""Deterministically extract quote headers, never related assets or AI prose."""
import re
from datetime import datetime, timedelta, timezone
from urllib.parse import unquote, urlsplit

SYMBOLS = ('VIX9D', 'VIX', 'VIX3M', 'VIX6M')

def parse_quote(text, url, cutoff):
    now = datetime.fromisoformat(cutoff.replace('Z', '+00:00'))
    if now.tzinfo is None:
        raise ValueError('aware cutoff required')
    parsed = urlsplit(url)
    path = unquote(parsed.path)
    match = re.fullmatch(r'/finance/(?:beta/)?quote/(VIX9D|VIX|VIX3M|VIX6M):INDEXCBOE', path)
    if parsed.scheme != 'https' or parsed.netloc != 'www.google.com' or not match or parsed.query or parsed.fragment:
        raise ValueError('unsupported quote URL')
    symbol = match[1]
    clean = re.sub(r'(?m)^L\d+: ?', '', text)
    anchor = re.search(r'(?m)^' + symbol + r':INDEXCBOE\s*$', clean)
    if not anchor:
        raise ValueError('missing quote identity')
    tail = clean[anchor.end():]
    if 'area_chart' not in tail:
        raise ValueError('unrecognized quote header boundary')
    header = re.split(r'area_chart|Related assets|People also search for|Overview|News stories|[A-Z0-9]+:INDEXCBOE', tail, maxsplit=1)[0]
    price = re.search(r'(?m)^\s*(\d+(?:\.\d+)?)\s*$', header)
    stamp = re.search(r'([A-Z][a-z]{2}) (\d{1,2})(?:, (\d{4}))?, (\d{1,2}):(\d{2})(?::(\d{2}))?\s*([AP]M) GMT([+-]\d{1,2})(?::(\d{2}))?', header)
    if not price or not stamp or float(price[1]) <= 0:
        raise ValueError('missing quote value or timestamp')
    month, day, year, hour, minute, second, ampm, offset, om = stamp.groups()
    off = int(offset) * 60 + (int(om or 0) * (1 if int(offset) >= 0 else -1))
    tz = timezone(timedelta(minutes=off))
    hour = int(hour) % 12 + (12 if ampm == 'PM' else 0)
    years = [int(year)] if year else [now.year-1, now.year, now.year+1]
    dates = []
    for y in years:
        try:
            dates.append(datetime(y, datetime.strptime(month, '%b').month, int(day), hour, int(minute), int(second or 0), tzinfo=tz))
        except ValueError:
            continue
    dates = [d for d in dates if timedelta(0) <= now-d <= timedelta(days=7)]
    if len(dates) != 1:
        raise ValueError('future, stale or ambiguous quote date')
    observed = dates[0]
    return {'symbol':symbol, 'value':float(price[1]), 'date':observed.date().isoformat(), 'observedAt':observed.isoformat(), 'unit':'index-points', 'sourceUrl':url, 'displayedTimestamp':stamp[0], 'yearInferred':year is None}
