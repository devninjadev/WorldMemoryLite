"""Pure provider routing; no observations, credentials, or connector I/O."""

from __future__ import annotations

TOOL_ACCESS_KEYS = (
    "alpacaMarketData",
    "alpacaOptions",
    "alpacaCalendar",
    "wolframLanguage",
    "wolframAlpha",
)


TRADINGVIEW_ACCESS_KEYS = ("tradingViewQuotes", "tradingViewHistory")


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
    "volatility-term-structure": ("cboe", "spreadsheet"),
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


_SCHEDULED_ECONOMIC_SERIES_IDS = (
    "FRED:NFCIRISK",
    "FRED:WALCL",
    "FRED:WDTGAL",
    "FRED:RRPONTSYD",
    "FRED:DTWEXBGS",
)


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
    "google-finance": (
        "open_quote_and_parse_quote_for_each_symbol",
        "https://www.google.com/finance/quote/{plan.vixSymbols[]}:INDEXCBOE",
    ),
    "spreadsheet": ("get_registered_vix_csv", "plan.vixPublicCsvUrl"),
    "cboe": (
        "get_cboe_history_csv_for_each_symbol",
        "https://cdn.cboe.com/api/global/us_indices/daily_prices/{plan.vixSymbols[]}_History.csv",
    ),
}


def normalize_market_tool_access(value: object) -> dict[str, bool]:
    """Require the exact, boolean-only connector-access contract."""
    if type(value) is not dict or set(value) not in (
        set(TOOL_ACCESS_KEYS),
        set(TOOL_ACCESS_KEYS + TRADINGVIEW_ACCESS_KEYS),
    ):
        raise ValueError("market tool access keys do not match")
    if any(type(value[key]) is not bool for key in value):
        raise ValueError("market tool access must use booleans")
    return dict(value)


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


def _capability_row(
    capability: str, access: dict[str, bool], vix_public_csv_url: str
) -> dict[str, object]:
    providers: list[str] = []
    tv_key = (
        "tradingViewQuotes"
        if capability == "equity-current-price"
        else "tradingViewHistory"
    )
    if capability in {
        "equity-current-price",
        "equity-daily-bars",
        "credit-risk-pair",
        "market-breadth-pair",
        "economic-time-series",
        "treasury-yield-curve",
    } and access.get(tv_key, False):
        providers.append("tradingview")
    if capability == "volatility-term-structure":
        providers.append("google-finance")
    if access["alpacaMarketData"] and capability in _ALPACA_MARKET_CAPABILITIES:
        providers.append("alpaca")
    if access["alpacaOptions"] and capability in _ALPACA_OPTIONS_CAPABILITIES:
        providers.append("alpaca")
    if access["alpacaCalendar"] and capability in _ALPACA_CALENDAR_CAPABILITIES:
        providers.append("alpaca")
    if access["wolframLanguage"]:
        providers.append("wolfram-language")
    if access["wolframAlpha"] and capability not in {
        "economic-time-series",
        "treasury-yield-curve",
    }:
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
    if provider == "tradingview":
        access_key = (
            "tradingViewQuotes"
            if capability == "equity-current-price"
            else "tradingViewHistory"
        )
        kind, tool = "connector-tool", "TradingView MCP"
        action = (
            "get_symbol_data_batch"
            if capability == "equity-current-price"
            else "get_ohlcv"
        )
        method, endpoint_template = None, None
        source_locator_persistence = "provider-query"
    elif provider == "alpaca":
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
        if capability in {"economic-time-series", "treasury-yield-curve"}:
            action = "import_official_fred_csv"
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
        if provider == "google-finance":
            tool = "web.open + world_memory.google_finance.parse_quote"
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


def _validate_vix_source(vix_public_csv_url: str, vix_symbols: tuple[str, ...]) -> None:
    if type(vix_public_csv_url) is not str or not vix_public_csv_url:
        raise ValueError("vix public CSV URL must be a nonempty string")
    if type(vix_symbols) is not tuple or not vix_symbols:
        raise ValueError("vix symbols must be a nonempty tuple")
    if any(type(symbol) is not str or not symbol for symbol in vix_symbols):
        raise ValueError("vix symbols must be nonempty strings")
