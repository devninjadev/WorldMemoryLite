"""Declarative, capability-specific provider ordering for market observations.

The Workspace Agent owns every connector call.  This module only turns the
caller-supplied current connector access into an ordered, side-effect-free
plan, so an unavailable optional connector is absent rather than represented
as an attempted provider failure.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import date, datetime, timezone
import math
import re
from urllib.parse import parse_qsl, urlsplit


TOOL_ACCESS_KEYS = (
    "alpacaMarketData",
    "alpacaOptions",
    "alpacaCalendar",
    "wolframLanguage",
    "wolframAlpha",
)

_ROW_RULES = {
    "successRule": "one-complete-provider-observation",
    "partialRule": "preserve-usable-components-and-continue",
    "shortCircuitOnComplete": True,
}

_VALIDATOR_CAPABILITY = {
    "equity-current-price": "equity-current-price",
    "equity-latest-quote": None,
    "equity-daily-bars": "equity-daily-bars",
    "credit-risk-pair": "equity-pair-series",
    "market-breadth-pair": "equity-pair-series",
    "options-chain": None,
    "corporate-actions": None,
    "market-calendar": None,
    "btc-usd": None,
    "treasury-yield-curve": "treasury-yield-curve",
    "economic-time-series": "economic-time-series",
    "volatility-term-structure": "volatility-term-structure",
}

_CAPABILITY_FALLBACKS = {
    "equity-current-price": ("existing-equity",),
    "equity-latest-quote": ("existing-equity",),
    "equity-daily-bars": ("existing-equity",),
    "credit-risk-pair": ("existing-credit-risk",),
    "market-breadth-pair": ("existing-market-breadth",),
    "options-chain": (),
    "corporate-actions": ("existing-corporate-actions",),
    "market-calendar": ("existing-market-calendar",),
    "btc-usd": (),
    "treasury-yield-curve": ("treasury-csv", "treasury-xml"),
    "economic-time-series": ("fred-batch", "fred-page"),
    "volatility-term-structure": ("spreadsheet", "cboe"),
}

_ALPACA_MARKET_CAPABILITIES = frozenset(
    {
        "equity-current-price",
        "equity-latest-quote",
        "equity-daily-bars",
        "credit-risk-pair",
        "market-breadth-pair",
        "corporate-actions",
        "btc-usd",
    }
)
_ALPACA_OPTIONS_CAPABILITIES = frozenset({"options-chain"})
_ALPACA_CALENDAR_CAPABILITIES = frozenset({"market-calendar"})

SAFE_ERROR_CODES = frozenset(
    {
        "tool-unavailable",
        "permission-denied",
        "premium-feed-required",
        "provider-no-result",
        "provider-timeout",
        "provider-rate-limited",
        "provider-malformed",
        "entity-mismatch",
        "currency-mismatch",
        "unsupported-value-basis",
        "missing-required-field",
        "evidence-unbound",
        "future-dated",
        "stale",
        "insufficient-history",
        "pair-misaligned",
        "normalization-failed",
    }
)

SAFE_PROVIDER_RESULT_ERRORS = SAFE_ERROR_CODES | frozenset(
    {"market_provider_error", "market_provider_empty_values"}
)

_PROVIDERS = frozenset(
    {
        "alpaca",
        "wolfram-language",
        "wolfram-alpha",
        "existing-equity",
        "existing-credit-risk",
        "existing-market-breadth",
        "existing-corporate-actions",
        "existing-market-calendar",
        "treasury-csv",
        "treasury-xml",
        "fred-batch",
        "fred-page",
        "spreadsheet",
        "cboe",
    }
)

_PROVIDER_URL_HOSTS = {
    "alpaca": frozenset({"data.alpaca.markets"}),
    "existing-equity": frozenset(
        {"api.nasdaq.com", "query1.finance.yahoo.com", "www.ishares.com"}
    ),
    "existing-credit-risk": frozenset(
        {"api.nasdaq.com", "query1.finance.yahoo.com", "www.ishares.com"}
    ),
    "existing-market-breadth": frozenset(
        {"api.nasdaq.com", "query1.finance.yahoo.com", "www.spglobal.com"}
    ),
    "treasury-csv": frozenset({"home.treasury.gov"}),
    "treasury-xml": frozenset({"home.treasury.gov"}),
    "fred-batch": frozenset({"api.stlouisfed.org", "fred.stlouisfed.org"}),
    "fred-page": frozenset({"fred.stlouisfed.org"}),
    "spreadsheet": frozenset({"docs.google.com"}),
    "cboe": frozenset({"cdn.cboe.com", "www.cboe.com"}),
}

_SENSITIVE_URL_KEYS = frozenset(
    {
        "api_key",
        "apikey",
        "access_token",
        "token",
        "auth",
        "authorization",
        "secret",
        "credential",
        "password",
        "signature",
        "clientsecret",
        "bearer",
    }
)

_VALUE_BASES = {
    "equity-current-price": frozenset({"last-trade", "last"}),
    "equity-daily-bars": frozenset(
        {
            "unadjusted-close",
            "unadjusted-usd",
            "iex-trade-derived-bar",
            "sip-trade-derived-bar",
            "wolfram-daily-ohlcv",
        }
    ),
    "equity-pair-series": frozenset(
        {
            "unadjusted-close",
            "iex-trade-derived-bar",
            "sip-trade-derived-bar",
            "wolfram-daily-close",
        }
    ),
}
_EQUITY_PROVIDERS_BY_CAPABILITY = {
    "equity-current-price": frozenset(
        {"alpaca", "wolfram-language", "wolfram-alpha", "existing-equity"}
    ),
    "equity-daily-bars": frozenset(
        {"alpaca", "wolfram-language", "wolfram-alpha", "existing-equity"}
    ),
    "equity-pair-series": frozenset(
        {
            "alpaca",
            "wolfram-language",
            "wolfram-alpha",
            "existing-credit-risk",
            "existing-market-breadth",
        }
    ),
}
_MARKET_SCOPES = frozenset({"iex", "sip", "provider-market", "unknown"})
_SESSIONS = frozenset(
    {"regular", "pre-market", "after-hours", "closed", "unknown"}
)

_COMMON_CANDIDATE_FIELDS = frozenset(
    {
        "schemaVersion",
        "capability",
        "provider",
        "sourceLocator",
        "fetchedAt",
        "completeness",
        "evidenceBindings",
    }
)
_CAPABILITY_CANDIDATE_FIELDS = {
    "equity-current-price": frozenset(
        {
            "instrument",
            "price",
            "observedAt",
            "valueBasis",
            "marketScope",
            "session",
        }
    ),
    "equity-daily-bars": frozenset(
        {"instrument", "valueBasis", "marketScope", "session", "bars"}
    ),
    "equity-pair-series": frozenset(
        {"currency", "valueBasis", "marketScope", "session", "series"}
    ),
    "treasury-yield-curve": frozenset(
        {"country", "unit", "date", "valueBasis", "maturities"}
    ),
    "economic-time-series": frozenset(
        {"seriesId", "semanticIdentity", "frequency", "unit", "observations"}
    ),
    "volatility-term-structure": frozenset({"date", "unit", "components"}),
}
_CAPABILITY_REQUEST_FIELDS = {
    "equity-current-price": frozenset(
        {"capability", "cutoff", "instrument", "maximumAgeSeconds"}
    ),
    "equity-daily-bars": frozenset(
        {"capability", "cutoff", "instrument", "startDate", "endDate"}
    ),
    "equity-pair-series": frozenset(
        {
            "capability",
            "cutoff",
            "instruments",
            "startDate",
            "endDate",
            "minimumCommonDays",
        }
    ),
    "treasury-yield-curve": frozenset(
        {"capability", "cutoff", "country", "date"}
    ),
    "economic-time-series": frozenset(
        {
            "capability",
            "cutoff",
            "seriesId",
            "semanticIdentity",
            "frequency",
            "unit",
            "minimumHistory",
            "startDate",
            "endDate",
        }
    ),
    "volatility-term-structure": frozenset({"capability", "cutoff", "date"}),
}
_REQUEST_INSTRUMENT_FIELDS = frozenset(
    {"symbol", "currency", "region", "assetClass"}
)
_CANDIDATE_INSTRUMENT_FIELDS = frozenset(
    {"symbol", "currency", "region", "assetClass", "exchange"}
)
_TREASURY_MATURITIES = frozenset({"3M", "1Y", "2Y", "5Y", "10Y", "30Y"})
_TREASURY_COMPLETE_MATURITIES = ("2Y", "5Y", "10Y", "30Y")
_VIX_COMPONENTS = frozenset({"VIX9D", "VIX", "VIX3M", "VIX6M"})
_VIX_COMPONENT_ORDER = ("VIX9D", "VIX", "VIX3M", "VIX6M")
_SCHEDULED_ECONOMIC_SERIES_IDS = (
    "FRED:NFCIRISK",
    "FRED:WALCL",
    "FRED:WDTGAL",
    "FRED:RRPONTSYD",
    "FRED:DTWEXBGS",
)
_IMAGE_SUFFIXES = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg")
_REPAIR_ELIGIBLE_ERROR_CODES = frozenset(
    {
        "provider-malformed",
        "missing-required-field",
        "evidence-unbound",
        "normalization-failed",
    }
)
_QUERY_TOOL_PROVIDERS = {
    "Wolfram Language": "wolfram-language",
    "Wolfram Alpha": "wolfram-alpha",
}
_PATH_MISSING = object()
_USD_NOMINAL_EQUIVALENTS = frozenset({"USD", "USDT", "USDC"})

_INVOCATION_ARGUMENTS = {
    "equity-current-price": ("instrument.symbol", "maximumAgeSeconds", "cutoff"),
    "equity-latest-quote": ("instrument.symbol", "cutoff"),
    "equity-daily-bars": ("instrument.symbol", "startDate", "endDate", "cutoff"),
    "credit-risk-pair": ("instruments[].symbol", "startDate", "endDate", "cutoff"),
    "market-breadth-pair": ("instruments[].symbol", "startDate", "endDate", "cutoff"),
    "options-chain": ("instrument.symbol", "cutoff"),
    "corporate-actions": ("instrument.symbol", "startDate", "endDate"),
    "market-calendar": ("startDate", "endDate"),
    "btc-usd": ("instrument.symbol", "startDate", "endDate"),
    "treasury-yield-curve": ("country", "date"),
    "economic-time-series": ("seriesId", "startDate", "endDate"),
    "volatility-term-structure": ("date", "plan.vixSymbols"),
}

_ALPACA_ACTIONS = {
    "equity-current-price": "get_stock_latest_trade",
    "equity-latest-quote": "get_stock_latest_quote",
    "equity-daily-bars": "get_stock_bars",
    "credit-risk-pair": "get_stock_bars_for_each_symbol",
    "market-breadth-pair": "get_stock_bars_for_each_symbol",
    "options-chain": "get_option_chain",
    "corporate-actions": "get_corporate_actions",
    "market-calendar": "get_market_calendar",
    "btc-usd": "get_crypto_bars",
}

_PUBLIC_HTTP_INVOCATIONS = {
    "existing-equity": (
        "get_yahoo_chart",
        "https://query1.finance.yahoo.com/v8/finance/chart/{instrument.symbol}",
    ),
    "existing-credit-risk": (
        "get_yahoo_chart_for_each_symbol",
        "https://query1.finance.yahoo.com/v8/finance/chart/{instruments[].symbol}",
    ),
    "existing-market-breadth": (
        "get_yahoo_chart_for_each_symbol",
        "https://query1.finance.yahoo.com/v8/finance/chart/{instruments[].symbol}",
    ),
    "existing-corporate-actions": (
        "get_yahoo_chart_corporate_actions",
        "https://query1.finance.yahoo.com/v8/finance/chart/{instrument.symbol}",
    ),
    "existing-market-calendar": (
        "get_nasdaq_market_calendar",
        "https://api.nasdaq.com/api/calendar",
    ),
    "treasury-csv": (
        "get_treasury_daily_par_yield_csv",
        "https://home.treasury.gov/resource-center/data-chart-center/interest-rates/daily-treasury-rates.csv/{date.year}/all",
    ),
    "treasury-xml": (
        "get_treasury_daily_par_yield_xml",
        "https://home.treasury.gov/resource-center/data-chart-center/interest-rates/pages/xml",
    ),
    "fred-batch": (
        "get_fred_graph_csv_for_series",
        "https://fred.stlouisfed.org/graph/fredgraph.csv?id={seriesIdWithoutPrefix}",
    ),
    "fred-page": (
        "get_fred_series_page",
        "https://fred.stlouisfed.org/series/{seriesIdWithoutPrefix}",
    ),
    "spreadsheet": ("get_registered_vix_csv", "plan.vixPublicCsvUrl"),
    "cboe": (
        "get_cboe_history_csv_for_each_symbol",
        "https://cdn.cboe.com/api/global/us_indices/daily_prices/{plan.vixSymbols[]}_History.csv",
    ),
}


def normalize_market_tool_access(value: object) -> dict[str, bool]:
    """Require the exact, boolean-only connector-access contract."""
    if type(value) is not dict or set(value) != set(TOOL_ACCESS_KEYS):
        raise ValueError("market tool access keys do not match")
    if any(type(value[key]) is not bool for key in TOOL_ACCESS_KEYS):
        raise ValueError("market tool access must use booleans")
    return {key: value[key] for key in TOOL_ACCESS_KEYS}


def build_plugin_market_plan(
    *,
    tool_access: object,
    vix_public_csv_url: str,
    vix_symbols: tuple[str, ...],
) -> dict[str, object]:
    """Describe ordered, caller-owned market-provider attempts without I/O."""
    access = normalize_market_tool_access(tool_access)
    _validate_vix_source(vix_public_csv_url, vix_symbols)
    return {
        "planVersion": "1.0",
        "mode": "caller-supplied-observations",
        "externalIo": False,
        "failurePolicy": "preserve-independent-successes",
        "toolAccess": dict(access),
        "vixPublicCsvUrl": vix_public_csv_url,
        "vixSymbols": list(vix_symbols),
        "capabilities": {
            capability: _capability_row(capability, access, vix_public_csv_url)
            for capability in _CAPABILITY_FALLBACKS
        },
    }


def collect_planned_market_observations(
    *, plan: object, outcomes: object
) -> dict[str, object]:
    """Validate one invocation-local plan/outcome graph and compute effective values."""
    validated_plan = _validate_invocation_plan(plan)
    if type(outcomes) is not list or not outcomes:
        raise ValueError("market outcomes must be a nonempty list")
    seen_stable_keys: set[str] = set()
    economic_series_ids: set[str] = set()
    provider_rows: list[dict[str, object]] = []
    effective: dict[str, object] = {}
    gaps: list[str] = []
    for outcome in outcomes:
        if type(outcome) is not dict or set(outcome) != {
            "capability",
            "request",
            "stableKey",
            "attempts",
        }:
            raise ValueError("market outcome shape is invalid")
        capability = outcome["capability"]
        if (
            type(capability) is not str
            or capability not in validated_plan["capabilities"]
        ):
            raise ValueError("market outcome capability is invalid")
        row = validated_plan["capabilities"][capability]
        if not row["validatorSupported"]:
            raise ValueError("market outcome capability is not validator supported")
        request = outcome["request"]
        if _validate_request(request):
            raise ValueError("market outcome request is invalid")
        if request["capability"] != row["validatorCapability"]:
            raise ValueError("market outcome request capability is invalid")
        _validate_plan_capability_request(capability, request)
        if capability == "economic-time-series":
            economic_series_ids.add(request["seriesId"])
        stable_key = _expected_stable_key(capability, request)
        if outcome["stableKey"] != stable_key or stable_key in seen_stable_keys:
            raise ValueError("market outcome stable key is invalid")
        attempts = outcome["attempts"]
        expected_providers = row["providers"]
        if type(attempts) is not list or len(attempts) != len(expected_providers):
            raise ValueError("market attempt chain is incomplete")
        accepted: list[dict[str, object]] = []
        chain_complete = False
        for expected_provider, attempt in zip(expected_providers, attempts):
            normalized_row, observation = _validate_planned_attempt(
                capability=capability,
                expected_provider=expected_provider,
                request=request,
                stable_key=stable_key,
                attempt=attempt,
                chain_complete=chain_complete,
            )
            provider_rows.append(normalized_row)
            if normalized_row["status"] == "ok":
                chain_complete = True
                accepted.append(observation)
            elif normalized_row["status"] == "partial":
                accepted.append(observation)
                gaps.append(
                    f"{capability}/{expected_provider}: market_provider_partial"
                )
            elif normalized_row["status"] == "error":
                gaps.append(
                    f"{capability}/{expected_provider}: {normalized_row['error']}"
                )
        if accepted:
            if request["capability"] == "volatility-term-structure":
                effective[stable_key] = _effective_vix_observation(accepted)
            else:
                complete = [
                    observation
                    for observation in accepted
                    if observation["completeness"] == "complete"
                ]
                effective[stable_key] = deepcopy(
                    complete[-1] if complete else accepted[0]
                )
        seen_stable_keys.add(stable_key)
    if economic_series_ids and economic_series_ids != set(
        _SCHEDULED_ECONOMIC_SERIES_IDS
    ):
        raise ValueError("scheduled economic series set is incomplete")
    status = "unavailable" if not effective else ("partial" if gaps else "ok")
    return {
        "status": status,
        "providers": provider_rows,
        "values": effective,
        "gaps": gaps,
    }


def _validate_invocation_plan(value: object) -> dict[str, object]:
    if type(value) is not dict or set(value) != {
        "planVersion",
        "mode",
        "externalIo",
        "failurePolicy",
        "toolAccess",
        "vixPublicCsvUrl",
        "vixSymbols",
        "capabilities",
    }:
        raise ValueError("market plan shape is invalid")
    symbols = value["vixSymbols"]
    if type(symbols) is not list:
        raise ValueError("market plan symbols are invalid")
    expected = build_plugin_market_plan(
        tool_access=value["toolAccess"],
        vix_public_csv_url=value["vixPublicCsvUrl"],
        vix_symbols=tuple(symbols),
    )
    if value != expected:
        raise ValueError("market plan contradicts current access")
    return value


def _validate_plan_capability_request(
    capability: str, request: dict[str, object]
) -> None:
    if capability == "credit-risk-pair":
        symbols = [item["symbol"] for item in request["instruments"]]
        if symbols != ["HYG", "LQD"] or request["minimumCommonDays"] != 6:
            raise ValueError("credit-risk request is invalid")
    if capability == "market-breadth-pair":
        symbols = [item["symbol"] for item in request["instruments"]]
        if symbols != ["RSP", "SPY"] or request["minimumCommonDays"] != 21:
            raise ValueError("market-breadth request is invalid")


def _expected_stable_key(capability: str, request: dict[str, object]) -> str:
    if capability == "equity-current-price":
        return f"equity.current-price.{request['instrument']['symbol']}"
    if capability == "equity-daily-bars":
        return f"equity.daily-bars.{request['instrument']['symbol']}"
    if capability == "credit-risk-pair":
        return "credit-risk.HYG-LQD"
    if capability == "market-breadth-pair":
        return "market-breadth.RSP-SPY"
    if capability == "treasury-yield-curve":
        return "treasury.yield-curve.US"
    if capability == "economic-time-series":
        return f"economic.{request['seriesId']}"
    if capability == "volatility-term-structure":
        return "VIX.term-structure"
    raise ValueError("stable key capability is unsupported")


def _validate_planned_attempt(
    *,
    capability: str,
    expected_provider: str,
    request: dict[str, object],
    stable_key: str,
    attempt: object,
    chain_complete: bool,
) -> tuple[dict[str, object], dict[str, object] | None]:
    if type(attempt) is not dict or set(attempt) != {
        "provider",
        "status",
        "values",
        "error",
        "stage",
        "validationEnvelope",
    }:
        raise ValueError("market attempt shape is invalid")
    if attempt["provider"] != expected_provider:
        raise ValueError("market attempt provider order is invalid")
    status = attempt["status"]
    values = attempt["values"]
    error = attempt["error"]
    stage = attempt["stage"]
    validation_envelope = attempt["validationEnvelope"]
    if (
        type(status) is not str
        or type(values) is not dict
        or type(error) is not str
        or type(stage) is not str
    ):
        raise ValueError("market attempt fields are invalid")
    observation: dict[str, object] | None = None
    if chain_complete:
        if (
            status != "not-attempted"
            or values
            or error
            or stage
            or validation_envelope is not None
        ):
            raise ValueError("completed chain requires not-attempted fallbacks")
    elif status in {"ok", "partial"}:
        if set(values) != {stable_key} or stage:
            raise ValueError("accepted attempt requires one normalized observation")
        if status == "ok" and error:
            raise ValueError("complete attempt cannot have an error")
        if status == "partial" and error != "market_provider_partial":
            raise ValueError("partial attempt requires its safe gap")
        if type(validation_envelope) is not dict:
            raise ValueError("accepted attempt requires its validation envelope")
        if validation_envelope.get("request") != request:
            raise ValueError("validation envelope request is invalid")
        assessment = assess_market_observation(validation_envelope)
        if assessment.get("status") != "accepted":
            raise ValueError("validation envelope was not accepted")
        observation = assessment["observation"]
        if observation != values[stable_key]:
            raise ValueError("normalized observation contradicts validation envelope")
        observation = _validate_normalized_observation(
            request, observation, expected_provider
        )
        expected_completeness = "complete" if status == "ok" else "partial"
        if observation["completeness"] != expected_completeness:
            raise ValueError("attempt status contradicts observation completeness")
    elif status == "error":
        if (
            values
            or validation_envelope is not None
            or error not in SAFE_PROVIDER_RESULT_ERRORS
            or stage not in {"fetch", "parse"}
        ):
            raise ValueError("attempted failure is invalid")
    elif status == "not-attempted":
        raise ValueError("not-attempted is allowed only after complete")
    else:
        raise ValueError("market attempt status is invalid")
    normalized = {
        "capability": capability,
        "provider": expected_provider,
        "status": status,
        "values": deepcopy(values),
        "error": error,
        "stage": stage,
    }
    return normalized, observation


def _validate_normalized_observation(
    request: dict[str, object], value: object, provider: str
) -> dict[str, object]:
    if type(value) is not dict:
        raise ValueError("normalized observation must be an object")
    capability = request["capability"]
    expected_fields = (
        (_COMMON_CANDIDATE_FIELDS - {"evidenceBindings"})
        | _CAPABILITY_CANDIDATE_FIELDS[capability]
    )
    if set(value) != expected_fields:
        raise ValueError("normalized observation shape is invalid")
    candidate = deepcopy(value)
    if (
        candidate["schemaVersion"] != "1.0"
        or candidate["capability"] != capability
        or candidate["provider"] != provider
        or candidate["completeness"] not in {"complete", "partial"}
    ):
        raise ValueError("normalized observation identity is invalid")
    if not _valid_source_locator_without_evidence(
        candidate["sourceLocator"], provider, request
    ):
        raise ValueError("normalized source locator is invalid")
    fetched = _parse_aware_datetime(candidate["fetchedAt"])
    cutoff = _parse_aware_datetime(request["cutoff"])
    if fetched is None or cutoff is None or fetched > cutoff:
        raise ValueError("normalized fetchedAt is invalid")
    errors = _validate_capability(request, candidate)
    if errors:
        raise ValueError("normalized observation is invalid")
    candidate["fetchedAt"] = _utc_text(fetched)
    return candidate


def _valid_source_locator_without_evidence(
    value: object, provider: str, request: dict[str, object]
) -> bool:
    if type(value) is not dict:
        return False
    if set(value) == {"kind", "tool", "queryDescriptor"}:
        return (
            value.get("kind") == "provider-query"
            and value.get("tool") in _QUERY_TOOL_PROVIDERS
            and _QUERY_TOOL_PROVIDERS[value["tool"]] == provider
            and value.get("queryDescriptor") in _allowed_query_descriptors(request)
        )
    if set(value) != {"kind", "url"} or value.get("kind") != "url":
        return False
    return _safe_provider_url(value.get("url"), provider)


def _effective_vix_observation(
    observations: list[dict[str, object]]
) -> dict[str, object]:
    components: dict[str, object] = {}
    for observation in observations:
        for symbol, level in observation["components"].items():
            components.setdefault(
                symbol,
                {
                    "level": level,
                    "date": observation["date"],
                    "provider": observation["provider"],
                    "sourceLocator": deepcopy(observation["sourceLocator"]),
                    "fetchedAt": observation["fetchedAt"],
                },
            )
    return {
        "schemaVersion": "1.0",
        "capability": "volatility-term-structure",
        "completeness": (
            "complete" if set(components) == _VIX_COMPONENTS else "partial"
        ),
        "unit": "index-points",
        "components": components,
    }


def assess_market_observation(value: object) -> dict[str, object]:
    """Validate one evidence-bound observation without retaining raw evidence."""
    if type(value) is not dict or set(value) != {
        "request",
        "candidate",
        "evidence",
        "normalizationAttempt",
    }:
        return _rejected([_error("provider-malformed", "request")], 2)

    attempt = value["normalizationAttempt"]
    if type(attempt) is not int or attempt not in (1, 2):
        return _rejected([_error("normalization-failed", "normalizationAttempt")], 2)

    evidence, evidence_errors = _validate_evidence(value["evidence"])
    try:
        provider_no_result = _is_provider_no_result(evidence)
    except ValueError:
        return _rejected([_error("provider-malformed", "evidence")], attempt)
    if provider_no_result:
        return _rejected(
            [_error("provider-no-result", "evidence")], attempt, immediate=True
        )

    request = value["request"]
    candidate = value["candidate"]
    repair_context = _is_wolfram_alpha_text_candidate(candidate, evidence)
    errors = list(evidence_errors)
    errors.extend(_validate_request(request))
    errors.extend(_validate_candidate_envelope(request, candidate, evidence))
    if errors:
        return _rejected(errors, attempt, repair_context=repair_context)

    normalized = deepcopy(candidate)
    errors.extend(_validate_evidence_bindings(normalized, evidence))
    errors.extend(_validate_capability(request, normalized))
    if errors:
        return _rejected(errors, attempt, repair_context=repair_context)

    normalized["fetchedAt"] = _utc_text(_parse_aware_datetime(candidate["fetchedAt"]))
    normalized.pop("evidenceBindings", None)
    return {"status": "accepted", "observation": normalized}


def _validate_evidence(
    value: object,
) -> tuple[list[dict[str, object]], list[dict[str, str]]]:
    if type(value) is not list or not value:
        return [], [_error("provider-malformed", "evidence")]
    rows: list[dict[str, object]] = []
    seen: set[str] = set()
    for row in value:
        if type(row) is not dict or set(row) != {"evidenceId", "format", "content"}:
            return [], [_error("provider-malformed", "evidence")]
        evidence_id = row["evidenceId"]
        evidence_format = row["format"]
        content = row["content"]
        if (
            type(evidence_id) is not str
            or not evidence_id
            or evidence_id in seen
            or evidence_format not in ("structured", "text")
            or (evidence_format == "structured" and type(content) not in (dict, list))
            or (evidence_format == "text" and type(content) is not str)
        ):
            return [], [_error("provider-malformed", "evidence")]
        seen.add(evidence_id)
        rows.append(row)
    return rows, []


def _is_provider_no_result(evidence: list[dict[str, object]]) -> bool:
    if len(evidence) != 1 or evidence[0].get("format") != "text":
        return False
    text = str(evidence[0].get("content", "")).strip()
    if text.casefold() == "no results found":
        return True
    parsed = urlsplit(text)
    return (
        parsed.scheme in ("http", "https")
        and bool(parsed.hostname)
        and parsed.path.casefold().endswith(_IMAGE_SUFFIXES)
    )


def _validate_request(value: object) -> list[dict[str, str]]:
    if type(value) is not dict:
        return [_error("provider-malformed", "request")]
    capability = value.get("capability")
    expected_fields = _CAPABILITY_REQUEST_FIELDS.get(capability)
    if expected_fields is None or set(value) != expected_fields:
        return [_error("provider-malformed", "request")]
    errors: list[dict[str, str]] = []
    if _parse_aware_datetime(value["cutoff"]) is None:
        errors.append(_error("provider-malformed", "request.cutoff"))
    if capability in ("equity-current-price", "equity-daily-bars"):
        if not _valid_request_instrument(value["instrument"]):
            errors.append(_error("provider-malformed", "request.instrument"))
        if capability == "equity-current-price" and (
            type(value["maximumAgeSeconds"]) is not int
            or value["maximumAgeSeconds"] < 1
        ):
            errors.append(
                _error("provider-malformed", "request.maximumAgeSeconds")
            )
    elif capability == "equity-pair-series":
        instruments = value["instruments"]
        if (
            type(instruments) is not list
            or len(instruments) != 2
            or any(not _valid_request_instrument(item) for item in instruments)
        ):
            errors.append(_error("provider-malformed", "request.instruments"))
        if type(value["minimumCommonDays"]) is not int or value["minimumCommonDays"] < 1:
            errors.append(_error("provider-malformed", "request.minimumCommonDays"))
    elif capability == "treasury-yield-curve":
        if value["country"] != "US":
            errors.append(_error("entity-mismatch", "request.country"))
    elif capability == "economic-time-series":
        if (
            type(value["seriesId"]) is not str
            or not value["seriesId"]
            or type(value["semanticIdentity"]) is not str
            or not value["semanticIdentity"]
            or type(value["frequency"]) is not str
            or not value["frequency"]
            or type(value["unit"]) is not str
            or not value["unit"]
            or type(value["minimumHistory"]) is not int
            or value["minimumHistory"] < 1
        ):
            errors.append(_error("provider-malformed", "request"))
    for field in ("date", "startDate", "endDate"):
        if field in value and _parse_date(value[field]) is None:
            errors.append(_error("provider-malformed", f"request.{field}"))
    cutoff = _parse_aware_datetime(value.get("cutoff"))
    if cutoff is not None:
        cutoff_day = cutoff.date()
        if "date" in value:
            requested_day = _parse_date(value["date"])
            if requested_day is not None and requested_day > cutoff_day:
                errors.append(_error("future-dated", "request.date"))
        if "startDate" in value and "endDate" in value:
            start = _parse_date(value["startDate"])
            end = _parse_date(value["endDate"])
            if start is not None and end is not None:
                if start > end:
                    errors.append(_error("provider-malformed", "request.dateWindow"))
                if end > cutoff_day:
                    errors.append(_error("future-dated", "request.endDate"))
    return errors


def _validate_candidate_envelope(
    request: object,
    candidate: object,
    evidence: list[dict[str, object]],
) -> list[dict[str, str]]:
    if type(candidate) is not dict:
        return [_error("provider-malformed", "candidate")]
    capability = request.get("capability") if type(request) is dict else None
    capability_fields = _CAPABILITY_CANDIDATE_FIELDS.get(capability)
    if capability_fields is None:
        return [_error("provider-malformed", "candidate")]
    expected_fields = _COMMON_CANDIDATE_FIELDS | capability_fields
    missing = expected_fields - set(candidate)
    if missing:
        for field in sorted(missing):
            return [_error("missing-required-field", _safe_candidate_field(field))]
    if set(candidate) != expected_fields:
        return [_error("provider-malformed", "candidate")]
    errors: list[dict[str, str]] = []
    if candidate["schemaVersion"] != "1.0":
        errors.append(_error("provider-malformed", "schemaVersion"))
    if candidate["capability"] != capability:
        errors.append(_error("entity-mismatch", "capability"))
    if (
        type(candidate["provider"]) is not str
        or candidate["provider"] not in _PROVIDERS
    ):
        errors.append(_error("provider-malformed", "provider"))
    if candidate["completeness"] not in ("complete", "partial"):
        errors.append(_error("provider-malformed", "completeness"))
    if _parse_aware_datetime(candidate["fetchedAt"]) is None:
        errors.append(_error("provider-malformed", "fetchedAt"))
    elif type(request) is dict:
        fetched = _parse_aware_datetime(candidate["fetchedAt"])
        cutoff = _parse_aware_datetime(request.get("cutoff"))
        if fetched is not None and cutoff is not None and fetched > cutoff:
            errors.append(_error("future-dated", "fetchedAt"))
    if not _valid_source_locator(
        candidate["sourceLocator"], candidate["provider"], request, evidence
    ):
        errors.append(_error("provider-malformed", "sourceLocator"))
    errors.extend(_validate_bindings(candidate["evidenceBindings"], evidence))
    return errors


def _validate_bindings(
    value: object, evidence: list[dict[str, object]]
) -> list[dict[str, str]]:
    if type(value) is not list:
        return [_error("provider-malformed", "evidenceBindings")]
    evidence_ids = {row["evidenceId"] for row in evidence}
    seen_fields: set[str] = set()
    evidence_by_id = {row["evidenceId"]: row for row in evidence}
    for binding in value:
        if type(binding) is not dict:
            return [_error("provider-malformed", "evidenceBindings")]
        field = binding.get("field")
        evidence_id = binding.get("evidenceId")
        if type(field) is not str or not field or field in seen_fields:
            return [_error("provider-malformed", "evidenceBindings")]
        if type(evidence_id) is not str or evidence_id not in evidence_ids:
            return [_error("provider-malformed", "evidenceBindings")]
        evidence_row = evidence_by_id[evidence_id]
        if evidence_row["format"] == "structured":
            if set(binding) != {"field", "evidenceId", "evidencePath"}:
                return [_error("provider-malformed", "evidenceBindings")]
            if not _valid_field_path(binding["evidencePath"]):
                return [_error("provider-malformed", "evidenceBindings")]
        else:
            if set(binding) != {"field", "evidenceId", "textSpan", "excerpt"}:
                return [_error("provider-malformed", "evidenceBindings")]
            span = binding["textSpan"]
            excerpt = binding["excerpt"]
            if (
                type(span) is not dict
                or set(span) != {"start", "end"}
                or type(span["start"]) is not int
                or type(span["end"]) is not int
                or isinstance(span["start"], bool)
                or isinstance(span["end"], bool)
                or span["start"] < 0
                or span["end"] <= span["start"]
                or type(excerpt) is not str
                or not excerpt
                or len(excerpt) > 500
            ):
                return [_error("provider-malformed", "evidenceBindings")]
        seen_fields.add(field)
    return []


def _valid_source_locator(
    value: object,
    provider: object,
    request: object,
    evidence: list[dict[str, object]],
) -> bool:
    if type(value) is not dict:
        return False
    if set(value) == {"kind", "url"} and value.get("kind") == "url":
        url = value.get("url")
        if not _safe_provider_url(url, provider):
            return False
        return any(_evidence_contains_locator(row, url) for row in evidence)
    if (
        set(value) == {"kind", "tool", "queryDescriptor"}
        and value.get("kind") == "provider-query"
        and value.get("tool") in _QUERY_TOOL_PROVIDERS
        and provider == _QUERY_TOOL_PROVIDERS[value["tool"]]
        and type(value.get("queryDescriptor")) is str
    ):
        return value["queryDescriptor"] in _allowed_query_descriptors(request)
    return False


def _safe_provider_url(value: object, provider: object) -> bool:
    if type(value) is not str or type(provider) is not str:
        return False
    try:
        parsed = urlsplit(value)
        return (
            parsed.scheme in ("http", "https")
            and bool(parsed.hostname)
            and parsed.username is None
            and parsed.password is None
            and not parsed.fragment
            and not any(
                _sensitive_url_key(key)
                for key, _ in parse_qsl(parsed.query, keep_blank_values=True)
            )
            and provider in _PROVIDER_URL_HOSTS
            and parsed.hostname.casefold() in _PROVIDER_URL_HOSTS[provider]
        )
    except (TypeError, ValueError):
        return False


def _sensitive_url_key(value: str) -> bool:
    compact = re.sub(r"[^a-z0-9]", "", value.casefold())
    exact = {
        re.sub(r"[^a-z0-9]", "", key.casefold()) for key in _SENSITIVE_URL_KEYS
    }
    return compact == "key" or compact in exact or any(
        marker in compact
        for marker in ("credential", "signature", "securitytoken", "accesskey")
    )


def _allowed_query_descriptors(request: object) -> frozenset[str]:
    if type(request) is not dict:
        return frozenset()
    capability = request.get("capability")
    if capability == "equity-current-price":
        instrument = request.get("instrument")
        if type(instrument) is dict and type(instrument.get("symbol")) is str:
            return frozenset({f"{capability}:{instrument['symbol']}"})
    if capability == "equity-daily-bars":
        instrument = request.get("instrument")
        if type(instrument) is dict:
            return frozenset(
                {
                    f"{capability}:{instrument.get('symbol')}:{request.get('startDate')}:{request.get('endDate')}"
                }
            )
    if capability == "equity-pair-series":
        instruments = request.get("instruments")
        if type(instruments) is list and len(instruments) == 2:
            symbols = ",".join(
                str(item.get("symbol")) for item in instruments if type(item) is dict
            )
            return frozenset(
                {
                    f"{capability}:{symbols}:{request.get('startDate')}:{request.get('endDate')}"
                }
            )
    if capability == "treasury-yield-curve":
        return frozenset(
            {f"{capability}:{request.get('country')}:{request.get('date')}"}
        )
    if capability == "economic-time-series":
        return frozenset(
            {
                f"{capability}:{request.get('seriesId')}:{request.get('startDate')}:{request.get('endDate')}",
                f"{capability}:{request.get('semanticIdentity')}:{request.get('startDate')}:{request.get('endDate')}",
            }
        )
    if capability == "volatility-term-structure":
        return frozenset({f"{capability}:{request.get('date')}"})
    return frozenset()


def _validate_capability(
    request: dict[str, object], candidate: dict[str, object]
) -> list[dict[str, str]]:
    capability = request["capability"]
    validators = {
        "equity-current-price": _validate_current_price,
        "equity-daily-bars": _validate_daily_bars,
        "equity-pair-series": _validate_pair_series,
        "treasury-yield-curve": _validate_treasury_curve,
        "economic-time-series": _validate_economic_series,
        "volatility-term-structure": _validate_volatility_structure,
    }
    return validators[capability](request, candidate)


def _validate_current_price(
    request: dict[str, object], candidate: dict[str, object]
) -> list[dict[str, str]]:
    errors = _instrument_errors(request["instrument"], candidate["instrument"])
    if not _positive_finite(candidate["price"]):
        errors.append(_error("provider-malformed", "price"))
    if candidate["valueBasis"] not in _VALUE_BASES["equity-current-price"]:
        errors.append(_error("unsupported-value-basis", "valueBasis"))
    errors.extend(_market_provenance_errors(candidate))
    observed_at = candidate["observedAt"]
    if observed_at is None:
        if candidate["completeness"] != "partial":
            errors.append(_error("missing-required-field", "observedAt"))
        return errors
    parsed = _parse_aware_datetime(observed_at)
    if parsed is None:
        errors.append(_error("provider-malformed", "observedAt"))
        return errors
    candidate["observedAt"] = _utc_text(parsed)
    cutoff = _parse_aware_datetime(request["cutoff"])
    if cutoff is not None and parsed > cutoff:
        errors.append(_error("future-dated", "observedAt"))
    elif cutoff is not None and (
        cutoff - parsed
    ).total_seconds() > request["maximumAgeSeconds"]:
        errors.append(_error("stale", "observedAt"))
    return errors


def _validate_daily_bars(
    request: dict[str, object], candidate: dict[str, object]
) -> list[dict[str, str]]:
    errors = _instrument_errors(request["instrument"], candidate["instrument"])
    if candidate["valueBasis"] not in _VALUE_BASES["equity-daily-bars"]:
        errors.append(_error("unsupported-value-basis", "valueBasis"))
    errors.extend(_market_provenance_errors(candidate))
    bars = candidate["bars"]
    if type(bars) is not list or not bars:
        errors.append(_error("missing-required-field", "bars"))
        return errors
    previous: date | None = None
    cutoff_date = _cutoff_date(request)
    for index, row in enumerate(bars):
        row_field = f"bars.{index}"
        if type(row) is not dict or set(row) != {
            "date",
            "open",
            "high",
            "low",
            "close",
            "volume",
        }:
            errors.append(_error("provider-malformed", row_field))
            continue
        row_date = _parse_date(row["date"])
        if row_date is None:
            errors.append(_error("provider-malformed", f"{row_field}.date"))
        elif previous is not None and row_date <= previous:
            errors.append(_error("provider-malformed", "bars"))
        elif cutoff_date is not None and row_date > cutoff_date:
            errors.append(_error("future-dated", f"{row_field}.date"))
        elif row_date is not None and not _date_in_request_window(request, row_date):
            errors.append(_error("provider-malformed", f"{row_field}.date"))
        if row_date is not None:
            previous = row_date
        numeric = [row[name] for name in ("open", "high", "low", "close")]
        if not all(_positive_finite(number) for number in numeric):
            errors.append(_error("provider-malformed", row_field))
        elif not (
            row["low"] <= row["open"] <= row["high"]
            and row["low"] <= row["close"] <= row["high"]
        ):
            errors.append(_error("provider-malformed", row_field))
        volume = row["volume"]
        if type(volume) is not int or volume < 0:
            errors.append(_error("provider-malformed", f"{row_field}.volume"))
    return errors


def _validate_pair_series(
    request: dict[str, object], candidate: dict[str, object]
) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    if type(candidate["currency"]) is not str or not candidate["currency"]:
        errors.append(_error("provider-malformed", "currency"))
    if candidate["valueBasis"] not in _VALUE_BASES["equity-pair-series"]:
        errors.append(_error("unsupported-value-basis", "valueBasis"))
    errors.extend(_market_provenance_errors(candidate))
    series = candidate["series"]
    if type(series) is not list or len(series) != 2:
        errors.append(_error("pair-misaligned", "series"))
        return errors
    date_sets: list[set[date]] = []
    for index, item in enumerate(series):
        item_field = f"series.{index}"
        if type(item) is not dict or set(item) != {"instrument", "rows"}:
            errors.append(_error("provider-malformed", item_field))
            continue
        errors.extend(
            _instrument_errors(request["instruments"][index], item["instrument"])
        )
        if (
            type(item["instrument"]) is dict
            and item["instrument"].get("currency") != candidate["currency"]
        ):
            errors.append(_error("currency-mismatch", "currency"))
        rows = item["rows"]
        if type(rows) is not list or not rows:
            errors.append(_error("pair-misaligned", "series"))
            continue
        parsed_dates: list[date] = []
        previous: date | None = None
        for row_index, row in enumerate(rows):
            row_field = f"{item_field}.rows.{row_index}"
            if type(row) is not dict or set(row) != {"date", "value"}:
                errors.append(_error("provider-malformed", row_field))
                continue
            row_date = _parse_date(row["date"])
            if row_date is None or (previous is not None and row_date <= previous):
                errors.append(_error("pair-misaligned", "series"))
            else:
                parsed_dates.append(row_date)
                previous = row_date
                if row_date > _cutoff_date(request):
                    errors.append(_error("future-dated", f"{row_field}.date"))
                elif not _date_in_request_window(request, row_date):
                    errors.append(_error("provider-malformed", f"{row_field}.date"))
            if not _positive_finite(row["value"]):
                errors.append(_error("provider-malformed", f"{row_field}.value"))
        date_sets.append(set(parsed_dates))
    if len(date_sets) == 2:
        common_dates = date_sets[0] & date_sets[1]
        if (
            date_sets[0] != date_sets[1]
            or len(common_dates) < request["minimumCommonDays"]
        ):
            errors.append(_error("pair-misaligned", "series"))
    return errors


def _validate_treasury_curve(
    request: dict[str, object], candidate: dict[str, object]
) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    if candidate["country"] != "US" or candidate["country"] != request["country"]:
        errors.append(_error("entity-mismatch", "country"))
    if candidate["unit"] != "percent":
        errors.append(_error("provider-malformed", "unit"))
    if candidate["valueBasis"] != "us-treasury-yield-curve-rate":
        errors.append(_error("unsupported-value-basis", "valueBasis"))
    curve_date = _parse_date(candidate["date"])
    if curve_date is None:
        errors.append(_error("provider-malformed", "date"))
    else:
        if candidate["date"] != request["date"]:
            errors.append(_error("entity-mismatch", "date"))
        if curve_date > _cutoff_date(request):
            errors.append(_error("future-dated", "date"))
    maturities = candidate["maturities"]
    if type(maturities) is not dict or not maturities:
        errors.append(_error("missing-required-field", "maturities"))
        return errors
    if not set(maturities) <= _TREASURY_MATURITIES:
        errors.append(_error("provider-malformed", "maturities"))
    for maturity in _TREASURY_COMPLETE_MATURITIES:
        if candidate["completeness"] == "complete" and maturity not in maturities:
            errors.append(_error("missing-required-field", f"maturities.{maturity}"))
    if any(not _finite_number(number) for number in maturities.values()):
        errors.append(_error("provider-malformed", "maturities"))
    return errors


def _validate_economic_series(
    request: dict[str, object], candidate: dict[str, object]
) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    exact_id = candidate["seriesId"] == request["seriesId"]
    exact_semantics = candidate["semanticIdentity"] == request["semanticIdentity"]
    if not exact_id and not exact_semantics:
        errors.append(_error("entity-mismatch", "seriesIdentity"))
    if candidate["frequency"] != request["frequency"]:
        errors.append(_error("entity-mismatch", "frequency"))
    if candidate["unit"] != request["unit"]:
        errors.append(_error("entity-mismatch", "unit"))
    observations = candidate["observations"]
    if type(observations) is not list:
        errors.append(_error("provider-malformed", "observations"))
        return errors
    if len(observations) < request["minimumHistory"]:
        errors.append(_error("insufficient-history", "observations"))
    previous: date | None = None
    for index, row in enumerate(observations):
        row_field = f"observations.{index}"
        if type(row) is not dict or set(row) != {"date", "value"}:
            errors.append(_error("provider-malformed", row_field))
            continue
        row_date = _parse_date(row["date"])
        if row_date is None or (previous is not None and row_date <= previous):
            errors.append(_error("provider-malformed", "observations"))
        else:
            previous = row_date
            if row_date > _cutoff_date(request):
                errors.append(_error("future-dated", f"{row_field}.date"))
            elif not _date_in_request_window(request, row_date):
                errors.append(_error("provider-malformed", f"{row_field}.date"))
        if not _finite_number(row["value"]):
            errors.append(_error("provider-malformed", f"{row_field}.value"))
    return errors


def _market_provenance_errors(
    candidate: dict[str, object]
) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    market_scope = candidate["marketScope"]
    session = candidate["session"]
    if market_scope not in _MARKET_SCOPES:
        errors.append(_error("provider-malformed", "marketScope"))
    if session not in _SESSIONS:
        errors.append(_error("provider-malformed", "session"))
    provider = candidate["provider"]
    capability = candidate["capability"]
    if provider not in _EQUITY_PROVIDERS_BY_CAPABILITY[capability]:
        errors.append(_error("provider-malformed", "provider"))
    if provider == "alpaca" and market_scope not in {"iex", "sip"}:
        errors.append(_error("provider-malformed", "marketScope"))
    if provider in {"wolfram-language", "wolfram-alpha"} and market_scope not in {
        "provider-market",
        "unknown",
    }:
        errors.append(_error("provider-malformed", "marketScope"))
    value_basis = candidate.get("valueBasis")
    if capability == "equity-current-price":
        if provider == "alpaca" and value_basis != "last-trade":
            errors.append(_error("unsupported-value-basis", "valueBasis"))
        if provider in {"wolfram-language", "wolfram-alpha"} and value_basis != "last":
            errors.append(_error("unsupported-value-basis", "valueBasis"))
    if capability in {"equity-daily-bars", "equity-pair-series"}:
        if provider == "alpaca" and value_basis not in {
            "iex-trade-derived-bar",
            "sip-trade-derived-bar",
        }:
            errors.append(_error("unsupported-value-basis", "valueBasis"))
        if provider in {"wolfram-language", "wolfram-alpha"} and value_basis not in {
            "wolfram-daily-ohlcv",
            "wolfram-daily-close",
        }:
            errors.append(_error("unsupported-value-basis", "valueBasis"))
        if provider == "alpaca":
            expected_scope = (
                "iex" if value_basis == "iex-trade-derived-bar" else "sip"
            )
            if market_scope != expected_scope:
                errors.append(_error("provider-malformed", "marketScope"))
        if provider in {
            "existing-equity",
            "existing-credit-risk",
            "existing-market-breadth",
        }:
            if value_basis not in {"unadjusted-close", "unadjusted-usd"}:
                errors.append(_error("unsupported-value-basis", "valueBasis"))
            if market_scope not in {"provider-market", "unknown"}:
                errors.append(_error("provider-malformed", "marketScope"))
    if capability == "equity-current-price" and provider == "existing-equity":
        if value_basis != "last":
            errors.append(_error("unsupported-value-basis", "valueBasis"))
        if market_scope not in {"provider-market", "unknown"}:
            errors.append(_error("provider-malformed", "marketScope"))
    return errors


def _date_in_request_window(request: dict[str, object], value: date) -> bool:
    start = _parse_date(request.get("startDate"))
    end = _parse_date(request.get("endDate"))
    return start is not None and end is not None and start <= value <= end


def _validate_volatility_structure(
    request: dict[str, object], candidate: dict[str, object]
) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    if candidate["unit"] != "index-points":
        errors.append(_error("provider-malformed", "unit"))
    observed_date = _parse_date(candidate["date"])
    if observed_date is None:
        errors.append(_error("provider-malformed", "date"))
    else:
        if candidate["date"] != request["date"]:
            errors.append(_error("entity-mismatch", "date"))
        if observed_date > _cutoff_date(request):
            errors.append(_error("future-dated", "date"))
    components = candidate["components"]
    if type(components) is not dict or not components:
        errors.append(_error("missing-required-field", "components"))
        return errors
    if not set(components) <= _VIX_COMPONENTS:
        errors.append(_error("provider-malformed", "components"))
    if candidate["completeness"] == "complete":
        for symbol in _VIX_COMPONENT_ORDER:
            if symbol not in components:
                errors.append(_error("missing-required-field", f"components.{symbol}"))
    if any(not _positive_finite(number) for number in components.values()):
        errors.append(_error("provider-malformed", "components"))
    return errors


def _validate_evidence_bindings(
    candidate: dict[str, object], evidence: list[dict[str, object]]
) -> list[dict[str, str]]:
    bindings = candidate["evidenceBindings"]
    evidence_by_id = {row["evidenceId"]: row for row in evidence}
    required = dict(_required_evidence_leaves(candidate))
    bindings_by_field = {
        binding["field"]: binding for binding in bindings if type(binding) is dict
    }
    errors: list[dict[str, str]] = []
    for field, expected in required.items():
        binding = bindings_by_field.get(field)
        if binding is None:
            errors.append(_error("evidence-unbound", _safe_evidence_path(field)))
            continue
        evidence_row = evidence_by_id.get(binding["evidenceId"])
        if evidence_row is None:
            errors.append(_error("evidence-unbound", _safe_evidence_path(field)))
            continue
        if evidence_row["format"] == "structured":
            evidence_path = binding.get("evidencePath")
            if evidence_path != field:
                errors.append(_error("evidence-unbound", _safe_evidence_path(field)))
                continue
            actual = _value_at_field_path(evidence_row["content"], evidence_path)
            if actual is _PATH_MISSING or not _same_evidence_scalar(
                field, actual, expected
            ):
                errors.append(_error("evidence-unbound", _safe_evidence_path(field)))
        else:
            span = binding.get("textSpan")
            excerpt = binding.get("excerpt")
            content = evidence_row["content"]
            if (
                type(span) is not dict
                or type(excerpt) is not str
                or span.get("end", len(content) + 1) > len(content)
                or content[span.get("start", -1) : span.get("end", -1)] != excerpt
                or not _text_excerpt_proves(field, expected, excerpt)
            ):
                errors.append(_error("evidence-unbound", _safe_evidence_path(field)))
    for field in bindings_by_field:
        if field not in required:
            errors.append(_error("provider-malformed", "evidenceBindings"))
    return errors


def _required_evidence_leaves(candidate: dict[str, object]):
    yield "fetchedAt", candidate["fetchedAt"]
    for field in sorted(_CAPABILITY_CANDIDATE_FIELDS[candidate["capability"]]):
        yield from _scalar_leaves(candidate[field], field)


def _scalar_leaves(value: object, path: str):
    if value is None:
        return
    if type(value) in (str, int, float):
        yield path, value
    elif type(value) is dict:
        for key, child in value.items():
            yield from _scalar_leaves(child, f"{path}.{key}")
    elif type(value) is list:
        for index, child in enumerate(value):
            yield from _scalar_leaves(child, f"{path}.{index}")


def _valid_field_path(value: object) -> bool:
    return type(value) is str and re.fullmatch(
        r"[A-Za-z][A-Za-z0-9]*(?:\.(?:[A-Za-z0-9][A-Za-z0-9-]*|\d+))*",
        value,
    ) is not None


def _value_at_field_path(value: object, path: object) -> object:
    if not _valid_field_path(path):
        return _PATH_MISSING
    current = value
    for part in str(path).split("."):
        if type(current) is dict and part in current:
            current = current[part]
        elif type(current) is list and part.isdigit() and int(part) < len(current):
            current = current[int(part)]
        else:
            return _PATH_MISSING
    return current


def _same_evidence_scalar(field: str, actual: object, expected: object) -> bool:
    if type(expected) in (int, float):
        return (
            type(actual) in (int, float)
            and _finite_number(actual)
            and _finite_number(expected)
            and actual == expected
        )
    if (
        _is_currency_field(field)
        and type(actual) is str
        and type(expected) is str
        and {actual, expected} <= _USD_NOMINAL_EQUIVALENTS
    ):
        return True
    return type(actual) is type(expected) and actual == expected


def _text_excerpt_proves(field: str, expected: object, excerpt: str) -> bool:
    if not _text_contains_exact_scalar(excerpt, expected, field=field):
        return False
    parts = field.split(".")
    labels = (field, parts[-1])
    return any(
        re.search(
            rf"(?<![A-Za-z0-9_.-]){re.escape(label)}\s*[:=|]",
            excerpt,
        )
        is not None
        for label in labels
    )


def _text_contains_exact_scalar(
    text: str, expected: object, *, field: str = ""
) -> bool:
    if type(expected) in (int, float):
        rendered = str(expected)
        return re.search(
            rf"(?<![\w.]){re.escape(rendered)}(?![\w.])", text
        ) is not None
    if type(expected) is not str:
        return False
    accepted = (
        _USD_NOMINAL_EQUIVALENTS
        if _is_currency_field(field) and expected in _USD_NOMINAL_EQUIVALENTS
        else (expected,)
    )
    return any(
        re.search(
            rf"(?<![A-Za-z0-9]){re.escape(value)}(?![A-Za-z0-9])", text
        )
        is not None
        for value in accepted
    )


def _text_evidence_contains_candidate_scalars(
    candidate: object, evidence: list[dict[str, object]]
) -> bool:
    if type(candidate) is not dict:
        return False
    capability = candidate.get("capability")
    capability_fields = _CAPABILITY_CANDIDATE_FIELDS.get(capability)
    if capability_fields is None or set(candidate) != (
        _COMMON_CANDIDATE_FIELDS | capability_fields
    ):
        return False
    text = "\n".join(str(row["content"]) for row in evidence)
    return all(
        _text_contains_exact_scalar(text, expected, field=field)
        for field, expected in _required_evidence_leaves(candidate)
    )


def _is_currency_field(field: str) -> bool:
    return field == "currency" or field.endswith(".currency")


def _contains_scalar(value: object, expected: object) -> bool:
    if type(value) in (dict, list):
        children = value.values() if type(value) is dict else value
        return any(_contains_scalar(child, expected) for child in children)
    return type(value) is type(expected) and value == expected


def _evidence_contains_locator(row: dict[str, object], locator: str) -> bool:
    if row["format"] == "text":
        return locator in row["content"]
    return _contains_scalar(row["content"], locator)


def _valid_request_instrument(value: object) -> bool:
    return (
        type(value) is dict
        and set(value) == _REQUEST_INSTRUMENT_FIELDS
        and all(type(value[field]) is str and bool(value[field]) for field in value)
    )


def _instrument_errors(
    expected: object, actual: object
) -> list[dict[str, str]]:
    if (
        type(expected) is not dict
        or type(actual) is not dict
        or set(actual) != _CANDIDATE_INSTRUMENT_FIELDS
        or any(type(actual[field]) is not str or not actual[field] for field in actual)
    ):
        return [_error("provider-malformed", "instrument")]
    errors: list[dict[str, str]] = []
    if actual["currency"] != expected["currency"]:
        errors.append(_error("currency-mismatch", "instrument.currency"))
    for field in ("symbol", "region", "assetClass"):
        if actual[field] != expected[field]:
            errors.append(_error("entity-mismatch", f"instrument.{field}"))
    return errors


def _parse_aware_datetime(value: object) -> datetime | None:
    if type(value) is not str or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed.astimezone(timezone.utc)


def _utc_text(value: datetime | None) -> str:
    if value is None:
        raise ValueError("aware datetime required")
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _parse_date(value: object) -> date | None:
    if type(value) is not str:
        return None
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.isoformat() == value else None


def _cutoff_date(request: dict[str, object]) -> date:
    cutoff = _parse_aware_datetime(request["cutoff"])
    if cutoff is None:
        raise ValueError("validated cutoff required")
    return cutoff.date()


def _finite_number(value: object) -> bool:
    if type(value) not in (int, float):
        return False
    try:
        return math.isfinite(value)
    except OverflowError:
        return False


def _positive_finite(value: object) -> bool:
    return _finite_number(value) and value > 0


def _safe_candidate_field(field: str) -> str:
    safe_fields = _COMMON_CANDIDATE_FIELDS | frozenset().union(
        *_CAPABILITY_CANDIDATE_FIELDS.values()
    )
    return field if field in safe_fields else "candidate"


def _safe_evidence_path(path: str) -> str:
    allowed = {"fetchedAt"}
    prefixes = tuple(f"{field}." for field in frozenset().union(
        *_CAPABILITY_CANDIDATE_FIELDS.values()
    ))
    roots = frozenset().union(*_CAPABILITY_CANDIDATE_FIELDS.values())
    return path if path in allowed or path in roots or path.startswith(prefixes) else "candidate"


def _error(code: str, field: str) -> dict[str, str]:
    if code not in SAFE_ERROR_CODES:
        raise ValueError("unsafe error code")
    return {"code": code, "field": field}


def _rejected(
    errors: list[dict[str, str]],
    attempt: int,
    *,
    immediate: bool = False,
    repair_context: bool = False,
) -> dict[str, object]:
    unique: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for error in errors:
        item = (error["code"], error["field"])
        if item not in seen:
            seen.add(item)
            unique.append({"code": item[0], "field": item[1]})
    return {
        "status": "rejected",
        "errors": unique,
        "repairAllowed": (
            not immediate
            and repair_context
            and attempt < 2
            and bool(unique)
            and all(error["code"] in _REPAIR_ELIGIBLE_ERROR_CODES for error in unique)
        ),
        "fallbackRequired": True,
    }


def _is_wolfram_alpha_text_candidate(
    candidate: object, evidence: list[dict[str, object]]
) -> bool:
    return (
        type(candidate) is dict
        and candidate.get("provider") == "wolfram-alpha"
        and type(candidate.get("sourceLocator")) is dict
        and candidate["sourceLocator"].get("kind") == "provider-query"
        and candidate["sourceLocator"].get("tool") == "Wolfram Alpha"
        and len(evidence) == 1
        and evidence[0].get("format") == "text"
        and _text_evidence_contains_candidate_scalars(candidate, evidence)
    )


def _capability_row(
    capability: str, access: dict[str, bool], vix_public_csv_url: str
) -> dict[str, object]:
    providers: list[str] = []
    if access["alpacaMarketData"] and capability in _ALPACA_MARKET_CAPABILITIES:
        providers.append("alpaca")
    if access["alpacaOptions"] and capability in _ALPACA_OPTIONS_CAPABILITIES:
        providers.append("alpaca")
    if access["alpacaCalendar"] and capability in _ALPACA_CALENDAR_CAPABILITIES:
        providers.append("alpaca")
    if access["wolframLanguage"]:
        providers.append("wolfram-language")
    if access["wolframAlpha"]:
        providers.append("wolfram-alpha")
    providers.extend(_CAPABILITY_FALLBACKS[capability])
    validator_capability = _VALIDATOR_CAPABILITY[capability]
    row = {
        "providers": providers,
        "attempts": [
            _provider_attempt(capability, provider, vix_public_csv_url)
            for provider in providers
        ],
        "validatorSupported": validator_capability is not None,
        "validatorCapability": validator_capability,
        "scheduleEligible": validator_capability is not None,
        **_ROW_RULES,
    }
    if capability == "economic-time-series":
        row["scheduledSeriesIds"] = list(_SCHEDULED_ECONOMIC_SERIES_IDS)
    return row


def _provider_attempt(
    capability: str, provider: str, vix_public_csv_url: str
) -> dict[str, object]:
    access_key: str | None = None
    kind = "public-http"
    tool = "HTTP"
    action: str
    method: str | None = "GET"
    endpoint_template: str | None
    evidence_format = "structured"
    source_locator_persistence = "url"
    if provider == "alpaca":
        if capability == "options-chain":
            access_key = "alpacaOptions"
        elif capability == "market-calendar":
            access_key = "alpacaCalendar"
        else:
            access_key = "alpacaMarketData"
        kind = "connector-tool"
        tool = "Alpaca"
        action = _ALPACA_ACTIONS[capability]
        method = None
        endpoint_template = None
    elif provider == "wolfram-language":
        access_key = "wolframLanguage"
        kind = "connector-tool"
        tool = "Wolfram Language"
        action = "evaluate"
        method = None
        endpoint_template = None
        source_locator_persistence = "provider-query"
    elif provider == "wolfram-alpha":
        access_key = "wolframAlpha"
        kind = "connector-tool"
        tool = "Wolfram Alpha"
        action = "query"
        method = None
        endpoint_template = None
        evidence_format = "text"
        source_locator_persistence = "provider-query"
    else:
        action, endpoint_template = _PUBLIC_HTTP_INVOCATIONS[provider]
        if provider == "spreadsheet":
            endpoint_template = vix_public_csv_url
    return {
        "provider": provider,
        "requiredToolAccess": access_key,
        "invocation": {
            "kind": kind,
            "tool": tool,
            "action": action,
            "method": method,
            "endpointTemplate": endpoint_template,
            "requestArguments": list(_INVOCATION_ARGUMENTS[capability]),
            "evidenceFormat": evidence_format,
            "rawQueryPersistence": "forbidden",
            "sourceLocatorPersistence": source_locator_persistence,
        },
    }


def _validate_vix_source(
    vix_public_csv_url: str, vix_symbols: tuple[str, ...]
) -> None:
    if type(vix_public_csv_url) is not str or not vix_public_csv_url:
        raise ValueError("vix public CSV URL must be a nonempty string")
    if type(vix_symbols) is not tuple or not vix_symbols:
        raise ValueError("vix symbols must be a nonempty tuple")
    if any(type(symbol) is not str or not symbol for symbol in vix_symbols):
        raise ValueError("vix symbols must be nonempty strings")
