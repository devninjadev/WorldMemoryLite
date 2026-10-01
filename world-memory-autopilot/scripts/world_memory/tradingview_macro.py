"""Pure normalization of verified TradingView FRED 1D observations.

These profiles describe the current raw-dollar TradingView feed, not arbitrary
FRED CSV inputs. Caller checks current provider metadata before using them.
"""

from datetime import datetime, timezone, date
from math import isfinite

SERIES = {
    "FRED:NFCIRISK": (1, "index", "weekly"),
    "FRED:WALCL": (1_000_000, "millions-of-usd", "weekly"),
    "FRED:WDTGAL": (1_000_000, "millions-of-usd", "weekly"),
    "FRED:RRPONTSYD": (1_000_000_000, "billions-of-usd", "daily"),
    "FRED:DTWEXBGS": (1, "index-jan2006=100", "daily"),
    **{f"FRED:DGS{n}": (1, "percent", "daily") for n in (2, 5, 10, 30)},
}
MATURITIES = {f"{n}Y": f"FRED:DGS{n}" for n in (2, 5, 10, 30)}


def normalize_series(raw, symbol):
    """Return observed dates/closes in original FRED units; never resample."""
    if (
        type(raw) is not dict
        or symbol not in SERIES
        or raw.get("success") is not True
        or raw.get("symbol") != symbol
        or raw.get("interval") != "1D"
    ):
        raise ValueError("invalid-series-response")
    bars = raw.get("bars")
    if type(bars) is not list or not bars:
        raise ValueError("missing-observations")
    divisor, unit, frequency = SERIES[symbol]
    observations = []
    previous = None
    for bar in bars:
        if type(bar) is not dict or type(bar.get("t")) is not int:
            raise ValueError("invalid-observation")
        # FRED 1D bars carry original dates at UTC midnight. Aggregated bars
        # move dates and can combine several releases; reject them above.
        stamp = bar["t"]
        if stamp % 86400 or (previous is not None and stamp <= previous):
            raise ValueError("invalid-observation-date")
        try:
            day = datetime.fromtimestamp(stamp, timezone.utc).date().isoformat()
        except (OverflowError, OSError, ValueError) as exc:
            raise ValueError("invalid-observation-date") from exc
        values = [bar.get(k) for k in ("o", "h", "l", "c")]
        if any(type(v) not in (int, float) or not isfinite(v) for v in values):
            raise ValueError("invalid-observation-value")
        if len(set(values)) != 1:
            raise ValueError("aggregated-observation")
        observations.append({"date": day, "value": bar["c"] / divisor})
        previous = stamp
    return {
        "seriesId": symbol,
        "unit": unit,
        "frequency": frequency,
        "observations": observations,
    }


def normalize_curve(raw_by_maturity, observation_date):
    """Require the same explicit observed date on all four DGS legs."""
    if type(raw_by_maturity) is not dict or set(raw_by_maturity) != set(MATURITIES):
        raise ValueError("incomplete-curve")
    if (
        type(observation_date) is not str
        or date.fromisoformat(observation_date).isoformat() != observation_date
    ):
        raise ValueError("invalid-curve-date")
    values = {}
    for maturity, symbol in MATURITIES.items():
        rows = normalize_series(raw_by_maturity[maturity], symbol)["observations"]
        matches = [row["value"] for row in rows if row["date"] == observation_date]
        if len(matches) != 1:
            raise ValueError("missing-curve-date")
        values[maturity] = matches[0]
    return {
        "country": "US",
        "date": observation_date,
        "unit": "percent",
        "valueBasis": "us-treasury-yield-curve-rate",
        "maturities": values,
    }
