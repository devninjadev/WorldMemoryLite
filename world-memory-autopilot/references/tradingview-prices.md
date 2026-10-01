# TradingView-first market observations (VIX excluded)

Discover the current connected MCP serving `https://mcp.tradingview.com/mcp`.
The known plugin name is Tradingview Official MCP Server; route by the current
exposed tool schema, never a personal connector ID or a hard-coded host prefix.
A skill cannot install, connect or authorize the service. Unavailable access
means use existing fallbacks. Check availability in the actual Workspace Agent,
not another Codex/chat session. See the official [MCP documentation](https://www.tradingview.com/mcp/docs).

`market-data-plan.toolAccess` accepts the legacy five flags unchanged, or those
five plus both boolean flags `tradingViewQuotes,tradingViewHistory`. Legacy
inputs leave TradingView disabled. Current scheduled prompts supply seven flags
from current access: quotes requires symbol resolution and quote tools; history
requires OHLCV tools; known exact FRED IDs remain eligible even when fuzzy search omits them. A runtime quote failure does not
disable history. Do not infer usable quotes from tool visibility alone.

All scheduled capabilities except volatility-term-structure prepend `tradingview` when their required quote/history route is available. VIX term structure is explicitly
excluded: preserve Google Finance -> Wolfram Language -> Wolfram Alpha -> Cboe
-> registered spreadsheet exactly. Never replace spot-tenor indices with VIX
futures or a different TradingView curve. Treasury and FRED then use the tested Wolfram Language CSV import and official HTTP fallbacks; see [wolfram-fallback.md](wolfram-fallback.md).
For equities after TradingView, retain Alpaca (including its existing Paper Trading read-only
fallback), Wolfram Language, Wolfram Alpha and existing public fallbacks.

1. Resolve the instrument using `search_symbols` or the equivalent exposed
   tool. Select the exchange/security/currency requested, not the first fuzzy
   result or another company's similar symbol. Reuse the resolved symbol in this
   invocation. Multiple listings on one company page remain separate securities.
2. Current price: discover supported quote columns, then use
   `get_symbol_data_batch` (up to the tool's limit) or the exposed equivalent.
   Validate actual values, symbol, currency, session, price observation time and
   update mode/delay. Quote retrieval time is not price time. Missing exact time
   cannot yield complete current-price validation. Stale/empty/missing/429/
   permission/timeout results fall through without repeated retries.
3. History: `get_ohlcv`, interval 1D, a bounded count covering the requested
   window. Inspect symbol, notice, timestamps, adjustment and session. Do not
   fabricate missing dates, replace volume with notional turnover, or call the
   latest daily close a current trade. The currently supported history basis is
   split-adjusted-close, regular session, provider-market. If returned semantics
   differ, reject this path instead of silently relabelling it. Disclose feed
   delay and unfinished last bars; use completed dates for pair comparisons.
4. For HYG/LQD and RSP/SPY collect both from one provider with the same basis,
   currency and session; intersect observed dates and meet minimumCommonDays.
   If incomplete, fall back for the entire pair, not one leg. Preserve raw
   successful observations as evidence, without mixing them into another pair.

Use the existing six validator shapes. Provider is `tradingview`; accepted
provenance has `{kind:provider-query,tool:"TradingView MCP",queryDescriptor}`
with the same capability/symbol/date descriptor formats as market-data.md.
Current price requires valueBasis=last; history/pairs require
valueBasis=split-adjusted-close. Preserve exchange identity in each instrument.
Structured evidence must actually support each field; a normalized projection
must be deterministically traceable to raw provider results and verified symbol
metadata. Do not invent a timestamp, currency, session or market-feed assurance
just to pass validation. Keep only validated observation provenance in reports;
raw tool results and temporary candidates remain invocation-local.

On a route-wide 429 or permission failure, remember that route's safe error
category for the remainder of this invocation and skip repeating calls to it;
record remaining planned attempts as error with that category and stage=fetch
so fallback and gaps remain truthful. This does not block independent history
or quote routes. No durable circuit-breaker state or retry loop is required.
An individual missing symbol does not disable all other symbols.

## Macro series and Treasury

Use exact FRED:NFCIRISK, FRED:WALCL, FRED:WDTGAL, FRED:RRPONTSYD and FRED:DTWEXBGS with OHLCV interval 1D, summary=false and a bounded count covering the request. A 1D request preserves sparse original weekly observations; 1W moves timestamps to the start of the week and aggregates daily releases. Never use weekly bars as original release dates. Fuzzy search currently omits these series or returns unrelated securities. An exact ID confirmed by the official TradingView symbol page and an identity-matching successful response is sufficient. Do not substitute an unrelated fuzzy match. The economic-data tool accepts ECONOMICS symbols, not FRED IDs; use its catalog only for genuinely equivalent indicators.

The verified raw TradingView monetary series are USD, whereas FRED WALCL/WDTGAL are millions of USD and RRPONTSYD is billions of USD. Do not infer scale from magnitude. Recheck metadata if the route/feed changes. `world_memory.tradingview_macro.normalize_series(raw, symbol)` converts the verified profiles to canonical units, checks exact identity, numeric OHLC equality, UTC observation dates and ordering, and rejects weekly/aggregated bars. It never fills missing dates. This helper is a pure Python API, not a network client. Filter the resulting observations to the requested window and apply the existing economic validator with matching unit/frequency, minimum history and cutoff. Preserve the raw response and unit-profile derivation as temporary evidence.

For the existing constant-maturity Treasury curve use FRED:DGS2, FRED:DGS5, FRED:DGS10 and FRED:DGS30 through the same 1D route. `normalize_curve(raw_by_maturity, observation_date)` requires all four legs on the requested observed date. Choose the newest common actual date no later than cutoff before creating the validation request; do not relabel Thursday data as Friday. TVC:US02Y/US05Y/US10Y/US30Y are separate market-yield observations and must not silently replace the official constant-maturity curve basis. The validator still requires same-date percent values and the original curve basis.

All scheduled non-VIX observations now start with TradingView, but a missing symbol, insufficient history, stale data, unit uncertainty or permission/rate-limit failure still requires fallback. Tool visibility alone is not successful collection. Success ends that capability chain; do not call Wolfram in parallel as redundant confirmation.
