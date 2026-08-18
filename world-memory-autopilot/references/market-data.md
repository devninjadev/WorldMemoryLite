# Market data

Treat every provider as an independent observation. Market data enriches the news evidence; no single provider is an authority gate for the Report.

## Deterministic CLI

| Command | Exact input keys | Output purpose |
|---|---|---|
| market-data-plan | registry,toolAccess | capability-specific provider collection plan |
| validate-market-observation | request,candidate,evidence,normalizationAttempt | validated evidence-bound market observation |
| collect-market-data | plan,outcomes | validated planned-provider snapshot |

## Structured CLI input shapes

| Value | Closed shape |
|---|---|
| market-data-plan | exact keys registry,toolAccess; registry is the validated notion-native-v2 object and toolAccess is the current response |
| market-data-plan.toolAccess | exact boolean keys alpacaMarketData,alpacaOptions,alpacaCalendar,wolframLanguage,wolframAlpha; each value reflects current tool access rather than remembered availability |
| market-data-plan.attempts[] | exact keys provider,requiredToolAccess,invocation; invocation has exact keys kind,tool,action,method,endpointTemplate,requestArguments,evidenceFormat,rawQueryPersistence,sourceLocatorPersistence and is directly executable without inferring an operation from provider |
| validate-market-observation | exact keys request,candidate,evidence,normalizationAttempt; normalizationAttempt is 1 or 2 |
| request | one of the six exact capability shapes below; cutoff is aware; current price also has maximumAgeSeconds; date windows satisfy startDate<=endDate<=cutoff; instruments use exact keys symbol,currency,region,assetClass |
| candidate common | exact keys schemaVersion,capability,provider,sourceLocator,fetchedAt,completeness,evidenceBindings plus only the capability fields below; provider is a closed plan provider; schemaVersion is 1.0; completeness is complete or partial |
| sourceLocator | either exact keys kind,url with kind=url and evidence-bound provider-host URL without credentials, key/token/credential/signature/access-key/security-token query keys including signed vendor prefixes, or fragment; or exact keys kind,tool,queryDescriptor with kind=provider-query and matching Wolfram provider |
| evidenceBindings[] | structured evidence uses exact keys field,evidenceId,evidencePath with the same exact scalar field path; text evidence uses exact keys field,evidenceId,textSpan,excerpt with an exact field-level source span |
| evidence[] | exact keys evidenceId,format,content; format is structured or text; content is the corresponding tool result bound only to that evidenceId |
| collect-market-data | exact keys plan,outcomes; plan is the unchanged current market-data-plan response and outcomes is a nonempty list of complete planned chains |
| collect-market-data.outcomes[] | exact keys capability,request,stableKey,attempts; capability is validatorSupported and in plan and may repeat only for a distinct request and stableKey; request maps to validatorCapability; attempts cover every planned provider once in order; any economic outcomes cover exactly the five scheduledSeriesIds |
| collect-market-data.attempts[] | exact keys provider,status,values,error,stage,validationEnvelope; complete forces every later row to not-attempted; partial or error permits the next attempt; ok or partial contains exactly one normalized observation at stableKey and the original accepted validation envelope; error or not-attempted uses validationEnvelope null |
| values.<stableKey> | atomic capabilities use one complete fallback observation instead of mixing a partial; VIX uses missing-only components with provider,sourceLocator,date,fetchedAt provenance per component; never a scalar or flattened pseudo-curve |

`market-data-plan` accepts exactly `{registry,toolAccess}`. It validates the complete `notion-native-v2` registry and the five current boolean access flags, performs no connector I/O, and returns an ordered provider chain per capability. Do not infer connector installation from old runs or documentation: the Workspace Agent supplies the current tool-access response on every run, and an unavailable optional connector is absent from the plan rather than reported as an attempted failure.

The scheduled prompt renders the exact Task 1 wrapper as valid JSON inside `market_data_plan_request_template`: `registry` is the actual validated embedded registry object and `toolAccess` has exactly the five declared keys with `null` values. Parse that block, replace each `null` only with its corresponding current observed boolean, and call `market-data-plan` with the same object. Do not reconstruct the registry, add a key, or change any other value. Each capability row carries executable `attempts`, `validatorSupported`, `validatorCapability`, `scheduleEligible`, `successRule:one-complete-provider-observation`, `partialRule:preserve-usable-components-and-continue`, and `shortCircuitOnComplete:true`. Every attempt identifies its provider, required current tool-access key or `null`, and a closed invocation descriptor. Connector attempts name the exact tool action and request fields; public attempts name HTTP `GET`, an exact official/public endpoint template, and request fields. The descriptor also declares structured versus text evidence and whether accepted provenance is a public URL or a deterministic provider-query descriptor. No provider-label inference is permitted. The raw tool query is invocation-local and forbidden from persistence; the validated deterministic `sourceLocator.queryDescriptor` is the only query representation that may accompany an accepted Wolfram observation. Call only listed providers and preserve their exact order. Independent capability chains may run concurrently. Provider attempts inside one capability chain are sequential and conditional; never start fallback N+1 before fallback N has failed validation or returned an accepted partial result with still-missing fields.

| Normal scheduled capability | Task 1 plan row | Task 2 validator request | Ordered attempt contract |
|---|---|---|---|
| current equity price | equity-current-price | equity-current-price | Alpaca; Wolfram Language; Wolfram Alpha; existing equity fallback |
| equity daily bars | equity-daily-bars | equity-daily-bars | Alpaca; Wolfram Language; Wolfram Alpha; existing equity fallback |
| HYG/LQD credit-risk pair | credit-risk-pair | equity-pair-series | Alpaca; Wolfram Language; Wolfram Alpha; existing credit-risk fallback |
| RSP/SPY breadth pair | market-breadth-pair | equity-pair-series | Alpaca; Wolfram Language; Wolfram Alpha; existing breadth fallback |
| US Treasury yield curve | treasury-yield-curve | treasury-yield-curve | Wolfram Language; Wolfram Alpha; Treasury CSV; Treasury XML |
| FRED economic time series | economic-time-series, once each for FRED:NFCIRISK,FRED:WALCL,FRED:WDTGAL,FRED:RRPONTSYD,FRED:DTWEXBGS | economic-time-series | Wolfram Language; Wolfram Alpha; FRED batch; FRED page |
| VIX term structure | volatility-term-structure | volatility-term-structure | Wolfram Language; Wolfram Alpha; registered public spreadsheet; Cboe |

The validator supports exactly six capability values: `equity-current-price`, `equity-daily-bars`, `equity-pair-series`, `treasury-yield-curve`, `economic-time-series`, and `volatility-term-structure`. Normal scheduled operation does not request Task 1 rows `equity-latest-quote`, `options-chain`, `corporate-actions`, `market-calendar`, or `btc-usd`. If a separate direct task requests one, do not send that unsupported name to this validator and do not claim validated success. A latest-quote request may degrade to `equity-current-price` only when the observed value is genuinely a current price; its accepted candidate remains `partial` and must be described as current price, never as a quote.

## Exact validator capability shapes

| Capability | Exact request-specific keys after capability,cutoff | Exact candidate-specific keys after the common fields |
|---|---|---|
| equity-current-price | instrument,maximumAgeSeconds | instrument,price,observedAt,valueBasis,marketScope,session |
| equity-daily-bars | instrument,startDate,endDate | instrument,valueBasis,marketScope,session,bars |
| equity-pair-series | instruments,startDate,endDate,minimumCommonDays | currency,valueBasis,marketScope,session,series |
| treasury-yield-curve | country,date | country,unit,date,valueBasis,maturities |
| economic-time-series | seriesId,semanticIdentity,frequency,unit,minimumHistory,startDate,endDate | seriesId,semanticIdentity,frequency,unit,observations |
| volatility-term-structure | date | date,unit,components |

## Nested validator shapes

| Value | Exact closed shape and constraint |
|---|---|
| common candidate | schemaVersion=1.0; capability equals request; provider is in the closed plan enum; sourceLocator as below; fetchedAt aware and not after cutoff; completeness complete or partial; evidenceBindings list; plus exactly one capability field set |
| URL sourceLocator | exact keys kind,url; kind=url; provider-host HTTP(S) URL without userinfo, secret query key, or fragment; exact URL occurs in supplied evidence |
| provider-query sourceLocator | exact keys kind,tool,queryDescriptor; kind=provider-query; tool Wolfram Language maps to provider wolfram-language or Wolfram Alpha maps to wolfram-alpha; descriptor exactly matches one deterministic format below |
| evidence[] | nonempty list of exact keys evidenceId,format,content; evidenceId nonempty and unique; structured content is object or list; text content is string |
| evidenceBindings[] | every non-null capability scalar plus fetchedAt has exactly one binding; structured rows use field,evidenceId,evidencePath with identical field/path and exact typed value; text rows use field,evidenceId,textSpan,excerpt whose exact source slice contains that field value and any maturity,component,or OHLC label; only currency fields treat USD,USDT,USDC as nominal 1:1 equivalents |
| request instrument | exact keys symbol,currency,region,assetClass; every value nonempty string |
| candidate instrument | exact keys symbol,currency,region,assetClass,exchange; requested symbol,currency,region,assetClass match exactly and USD remains the canonical output currency when source evidence says USDT or USDC; every value nonempty string |
| current price | positive finite price; closed provider-specific valueBasis,marketScope,session; observedAt aware, not after cutoff, and within maximumAgeSeconds, or null only when completeness=partial |
| daily bars | closed provider-specific valueBasis,marketScope,session; nonempty date-ascending rows inside startDate/endDate; positive finite OHLC; low <= open and close <= high; integer volume >= 0 |
| bar row | exact keys date,open,high,low,close,volume |
| pair series | exactly two ordered members matching requested instruments; closed common currency,valueBasis,marketScope,session; both date sets are identical after caller intersection and contain at least minimumCommonDays |
| pair member | exact keys instrument,rows; rows nonempty and date-ascending |
| pair row | exact keys date,value; value positive finite; date inside startDate/endDate and not after cutoff |
| Treasury maturities | nonempty subset of 3M,1Y,2Y,5Y,10Y,30Y with finite values; complete requires 2Y,5Y,10Y,30Y; country US; unit percent; valueBasis us-treasury-yield-curve-rate; date equals request and is not future |
| economic observations | list length at least minimumHistory; exact seriesId or exact semanticIdentity; frequency and unit equal request; rows date-ascending inside startDate/endDate and not future |
| economic observation | exact keys date,value; value finite |
| VIX components | nonempty subset of VIX9D,VIX,VIX3M,VIX6M with positive finite values; complete requires all four; unit index-points; date equals request and is not future |

## Deterministic query descriptors

| Capability | Exact queryDescriptor format |
|---|---|
| equity-current-price | `equity-current-price:<symbol>` |
| equity-daily-bars | `equity-daily-bars:<symbol>:<startDate>:<endDate>` |
| equity-pair-series | `equity-pair-series:<symbol1>,<symbol2>:<startDate>:<endDate>` |
| treasury-yield-curve | `treasury-yield-curve:<country>:<date>` |
| economic-time-series | `economic-time-series:<seriesId>:<startDate>:<endDate>` or `economic-time-series:<semanticIdentity>:<startDate>:<endDate>` |
| volatility-term-structure | `volatility-term-structure:<date>` |

Every `instrument` request object has exactly `symbol,currency,region,assetClass`. Each candidate instrument adds exactly `exchange`. A provider-query source locator has exact keys `kind,tool,queryDescriptor`, uses `kind:"provider-query"`, names `Wolfram Language` or `Wolfram Alpha`, and binds to the corresponding provider. A URL source locator has exact keys `kind,url`, uses `kind:"url"`, contains no credentials, sensitive query keys, or fragment, matches the provider host, and appears in supplied evidence. Structured bindings have exact `field,evidenceId,evidencePath`; text bindings have exact `field,evidenceId,textSpan,excerpt`; every evidence row has exact `evidenceId,format,content`.

`normalizationAttempt` starts at `1`. Only a validator rejection with `repairAllowed:true` authorizes one repair of the same Wolfram text evidence, sent with `normalizationAttempt:2`. There is no attempt 3, and structured evidence is never LLM-repaired.

### Scheduled pair request fixtures

```json
{
  "credit-risk-pair": {
    "capability": "equity-pair-series",
    "cutoff": "2026-08-16T12:00:00Z",
    "instruments": [
      {"symbol": "HYG", "currency": "USD", "region": "US", "assetClass": "ETF"},
      {"symbol": "LQD", "currency": "USD", "region": "US", "assetClass": "ETF"}
    ],
    "startDate": "2026-08-02",
    "endDate": "2026-08-16",
    "minimumCommonDays": 6
  },
  "market-breadth-pair": {
    "capability": "equity-pair-series",
    "cutoff": "2026-08-16T12:00:00Z",
    "instruments": [
      {"symbol": "RSP", "currency": "USD", "region": "US", "assetClass": "ETF"},
      {"symbol": "SPY", "currency": "USD", "region": "US", "assetClass": "ETF"}
    ],
    "startDate": "2026-07-02",
    "endDate": "2026-08-16",
    "minimumCommonDays": 21
  }
}
```

These fixed dates illustrate the rule for a `2026-08-16T12:00:00Z` invocation. At runtime, `cutoff` is the aware invocation timestamp, `endDate` is its UTC calendar date, HYG/LQD `startDate` is 14 calendar days before that date, and RSP/SPY `startDate` is 45 calendar days before it. The identities are always exactly USD, US, ETF in the displayed order.

Alpaca equity observations must label IEX versus SIP explicitly in their source/session metadata; a value from the default IEX feed must never be described as consolidated SIP. Keep the requested symbol, asset class, region, currency, exchange when supplied, and session basis intact through entity validation. `LatestTrade`, `LatestQuote`, current price, adjusted bar, and unadjusted bar are different value bases.

The accepted equity provenance combinations are closed:

| Provider | Accepted valueBasis and marketScope |
|---|---|
| Alpaca | `last-trade` with `iex` or `sip`; `iex-trade-derived-bar` with `iex`; `sip-trade-derived-bar` with `sip` |
| Wolfram Language or Wolfram Alpha | current price `last` with `provider-market` or `unknown`; history `wolfram-daily-ohlcv` or `wolfram-daily-close` with `provider-market` or `unknown` |
| Existing equity fallback | current price `last` with `provider-market` or `unknown`; daily history `unadjusted-close` or `unadjusted-usd` with `provider-market` or `unknown` |
| Existing credit-risk or breadth fallback | pair history `unadjusted-close` with `provider-market` or `unknown` |

No other provider, basis, or scope combination is accepted. In particular, Yahoo cannot claim SIP basis and Alpaca IEX-derived bars cannot claim SIP scope.

Wolfram Language is the structured route. Prefer an explicit dated series or entity property over a bare aggregate. Treat Wolfram `Last` degradation as a lower-information observation: it may supply a current scalar only when the response still binds the requested entity, date/time, unit, value basis, and numeric value. It cannot silently stand in for a requested history, pair, or curve. Wolfram Alpha is the evidence-text route and needs a precise query descriptor tied to the request. A descriptor is allowed only when it is one of the deterministic request-specific descriptors accepted by `validate-market-observation`; never accept a caller-invented semantic alias.

The spreadsheet request is derived only from `marketSources.vixSpreadsheet` and carries this exact final public fallback contract:

- public CSV: `https://docs.google.com/spreadsheets/d/15xqjZq8di2UqrePpYR_p72j5FCj-WTEDC4rdjZSqc_w/export?format=csv&gid=0`
- ordered symbols: `VIX9D`, `VIX`, `VIX3M`, `VIX6M`

The helper reports `externalIo:false`; the Workspace Agent, not Python, performs the read. Never mutate the spreadsheet, search Drive by title, substitute a private locator, or persist fetched values in the registry.

## Candidate validation and repair

Build the candidate from one provider attempt and submit it with the exact request, evidence rows, and `normalizationAttempt` to `validate-market-observation`. Structured tool output stays structured. Bind every non-null identity, date, unit, value-basis, market-scope, session, timestamp, label, and numeric leaf to its exact structured path. Only evidence-bearing Wolfram Alpha text may be normalized by the LLM; each field then binds to an exact verified character span and excerpt in the same source text. That excerpt must contain the exact candidate value and its exact full field label or leaf label followed by `:`, `=`, or `|`; a nearby unrelated mention cannot prove the field. The sole scalar-equivalence exception is a field named `currency` or ending in `.currency`: source `USD`, `USDT`, and `USDC` are accepted as a nominal 1:1 set, and the normalized candidate retains the requested canonical `USD`. This does not authorize an unlisted stablecoin, `USDJPY`, `USDTX`, `USDCX`, a ticker rewrite, or substring matching in any other field. No live peg check or FX adjustment is performed. The deterministic layer verifies supplied bindings but never falls back to semantic keyword matching. The validator performs closed-shape checks, entity validation, provider-host/query-descriptor validation, evidence-path/span validation, aware cutoff/future/staleness checks, and capability-specific completeness checks. It returns only a normalized observation on `accepted`; it never retains raw evidence.

Do not invoke the LLM when a provider returns `No Results Found`, a graph-only image or URL, or text without every required non-null candidate scalar, including entity identity, date, unit, value basis, and numeric values. These outcomes fall through immediately and cannot set `repairAllowed:true`. A rejected response exposes only bounded safe errors such as `provider-no-result`, `entity-mismatch`, `unsupported-value-basis`, `evidence-unbound`, `stale`, or `pair-misaligned`; never store or repeat raw provider errors. If and only if `repairAllowed:true`, permit at most one validation-guided repair of the same Wolfram Alpha text evidence with `normalizationAttempt:2`. Do not refetch, broaden the query, change the entity, or repair structured provider output. Any second rejection or `repairAllowed:false` requires the next planned fallback.

### Current price validator fixture

```json
{
  "request": {
    "capability": "equity-current-price",
    "cutoff": "2026-08-16T12:00:00Z",
    "maximumAgeSeconds": 3600,
    "instrument": {"symbol": "SPY", "currency": "USD", "region": "US", "assetClass": "ETF"}
  },
  "candidate": {
    "schemaVersion": "1.0",
    "capability": "equity-current-price",
    "provider": "wolfram-language",
    "sourceLocator": {"kind": "provider-query", "tool": "Wolfram Language", "queryDescriptor": "equity-current-price:SPY"},
    "fetchedAt": "2026-08-16T11:45:00Z",
    "completeness": "complete",
    "evidenceBindings": [
      {"field": "fetchedAt", "evidenceId": "ev-price", "evidencePath": "fetchedAt"},
      {"field": "instrument.symbol", "evidenceId": "ev-price", "evidencePath": "instrument.symbol"},
      {"field": "instrument.currency", "evidenceId": "ev-price", "evidencePath": "instrument.currency"},
      {"field": "instrument.region", "evidenceId": "ev-price", "evidencePath": "instrument.region"},
      {"field": "instrument.assetClass", "evidenceId": "ev-price", "evidencePath": "instrument.assetClass"},
      {"field": "instrument.exchange", "evidenceId": "ev-price", "evidencePath": "instrument.exchange"},
      {"field": "price", "evidenceId": "ev-price", "evidencePath": "price"},
      {"field": "observedAt", "evidenceId": "ev-price", "evidencePath": "observedAt"},
      {"field": "valueBasis", "evidenceId": "ev-price", "evidencePath": "valueBasis"},
      {"field": "marketScope", "evidenceId": "ev-price", "evidencePath": "marketScope"},
      {"field": "session", "evidenceId": "ev-price", "evidencePath": "session"}
    ],
    "instrument": {"symbol": "SPY", "currency": "USD", "region": "US", "assetClass": "ETF", "exchange": "NYSE Arca"},
    "price": 645.25,
    "observedAt": "2026-08-16T11:30:00Z",
    "valueBasis": "last",
    "marketScope": "provider-market",
    "session": "regular"
  },
  "evidence": [{"evidenceId": "ev-price", "format": "structured", "content": {"fetchedAt": "2026-08-16T11:45:00Z", "instrument": {"symbol": "SPY", "currency": "USD", "region": "US", "assetClass": "ETF", "exchange": "NYSE Arca"}, "price": 645.25, "observedAt": "2026-08-16T11:30:00Z", "valueBasis": "last", "marketScope": "provider-market", "session": "regular"}}],
  "normalizationAttempt": 1
}
```

### Daily bars validator fixture

```json
{
  "request": {
    "capability": "equity-daily-bars",
    "cutoff": "2026-08-16T12:00:00Z",
    "instrument": {"symbol": "SPY", "currency": "USD", "region": "US", "assetClass": "ETF"},
    "startDate": "2026-08-14",
    "endDate": "2026-08-15"
  },
  "candidate": {
    "schemaVersion": "1.0",
    "capability": "equity-daily-bars",
    "provider": "alpaca",
    "sourceLocator": {"kind": "url", "url": "https://data.alpaca.markets/v2/stocks/SPY/bars"},
    "fetchedAt": "2026-08-16T11:45:00Z",
    "completeness": "complete",
    "evidenceBindings": [
      {"field": "fetchedAt", "evidenceId": "ev-bars", "evidencePath": "fetchedAt"},
      {"field": "instrument.symbol", "evidenceId": "ev-bars", "evidencePath": "instrument.symbol"},
      {"field": "instrument.currency", "evidenceId": "ev-bars", "evidencePath": "instrument.currency"},
      {"field": "instrument.region", "evidenceId": "ev-bars", "evidencePath": "instrument.region"},
      {"field": "instrument.assetClass", "evidenceId": "ev-bars", "evidencePath": "instrument.assetClass"},
      {"field": "instrument.exchange", "evidenceId": "ev-bars", "evidencePath": "instrument.exchange"},
      {"field": "valueBasis", "evidenceId": "ev-bars", "evidencePath": "valueBasis"},
      {"field": "marketScope", "evidenceId": "ev-bars", "evidencePath": "marketScope"},
      {"field": "session", "evidenceId": "ev-bars", "evidencePath": "session"},
      {"field": "bars.0.date", "evidenceId": "ev-bars", "evidencePath": "bars.0.date"},
      {"field": "bars.0.open", "evidenceId": "ev-bars", "evidencePath": "bars.0.open"},
      {"field": "bars.0.high", "evidenceId": "ev-bars", "evidencePath": "bars.0.high"},
      {"field": "bars.0.low", "evidenceId": "ev-bars", "evidencePath": "bars.0.low"},
      {"field": "bars.0.close", "evidenceId": "ev-bars", "evidencePath": "bars.0.close"},
      {"field": "bars.0.volume", "evidenceId": "ev-bars", "evidencePath": "bars.0.volume"}
    ],
    "instrument": {"symbol": "SPY", "currency": "USD", "region": "US", "assetClass": "ETF", "exchange": "NYSE Arca"},
    "valueBasis": "iex-trade-derived-bar",
    "marketScope": "iex",
    "session": "regular",
    "bars": [{"date": "2026-08-15", "open": 644.0, "high": 648.0, "low": 642.0, "close": 645.0, "volume": 68000000}]
  },
  "evidence": [{"evidenceId": "ev-bars", "format": "structured", "content": {"sourceUrl": "https://data.alpaca.markets/v2/stocks/SPY/bars", "fetchedAt": "2026-08-16T11:45:00Z", "instrument": {"symbol": "SPY", "currency": "USD", "region": "US", "assetClass": "ETF", "exchange": "NYSE Arca"}, "valueBasis": "iex-trade-derived-bar", "marketScope": "iex", "session": "regular", "bars": [{"date": "2026-08-15", "open": 644.0, "high": 648.0, "low": 642.0, "close": 645.0, "volume": 68000000}]}}],
  "normalizationAttempt": 1
}
```

### Treasury validator fixture

```json
{
  "request": {"capability": "treasury-yield-curve", "cutoff": "2026-08-16T12:00:00Z", "country": "US", "date": "2026-08-15"},
  "candidate": {
    "schemaVersion": "1.0",
    "capability": "treasury-yield-curve",
    "provider": "wolfram-language",
    "sourceLocator": {"kind": "provider-query", "tool": "Wolfram Language", "queryDescriptor": "treasury-yield-curve:US:2026-08-15"},
    "fetchedAt": "2026-08-16T11:45:00Z",
    "completeness": "complete",
    "evidenceBindings": [
      {"field": "fetchedAt", "evidenceId": "ev-curve", "evidencePath": "fetchedAt"},
      {"field": "country", "evidenceId": "ev-curve", "evidencePath": "country"},
      {"field": "unit", "evidenceId": "ev-curve", "evidencePath": "unit"},
      {"field": "date", "evidenceId": "ev-curve", "evidencePath": "date"},
      {"field": "valueBasis", "evidenceId": "ev-curve", "evidencePath": "valueBasis"},
      {"field": "maturities.2Y", "evidenceId": "ev-curve", "evidencePath": "maturities.2Y"},
      {"field": "maturities.5Y", "evidenceId": "ev-curve", "evidencePath": "maturities.5Y"},
      {"field": "maturities.10Y", "evidenceId": "ev-curve", "evidencePath": "maturities.10Y"},
      {"field": "maturities.30Y", "evidenceId": "ev-curve", "evidencePath": "maturities.30Y"}
    ],
    "country": "US",
    "unit": "percent",
    "date": "2026-08-15",
    "valueBasis": "us-treasury-yield-curve-rate",
    "maturities": {"2Y": 3.61, "5Y": 3.74, "10Y": 4.02, "30Y": 4.61}
  },
  "evidence": [{"evidenceId": "ev-curve", "format": "structured", "content": {"fetchedAt": "2026-08-16T11:45:00Z", "country": "US", "unit": "percent", "date": "2026-08-15", "valueBasis": "us-treasury-yield-curve-rate", "maturities": {"2Y": 3.61, "5Y": 3.74, "10Y": 4.02, "30Y": 4.61}}}],
  "normalizationAttempt": 1
}
```

### Economic series validator fixture

```json
{
  "request": {
    "capability": "economic-time-series",
    "cutoff": "2026-08-16T12:00:00Z",
    "seriesId": "FRED:CPIAUCSL",
    "semanticIdentity": "US consumer price index all urban consumers",
    "frequency": "monthly",
    "unit": "index-1982-1984=100",
    "minimumHistory": 2,
    "startDate": "2026-06-01",
    "endDate": "2026-07-01"
  },
  "candidate": {
    "schemaVersion": "1.0",
    "capability": "economic-time-series",
    "provider": "wolfram-language",
    "sourceLocator": {"kind": "provider-query", "tool": "Wolfram Language", "queryDescriptor": "economic-time-series:FRED:CPIAUCSL:2026-06-01:2026-07-01"},
    "fetchedAt": "2026-08-16T11:45:00Z",
    "completeness": "complete",
    "evidenceBindings": [
      {"field": "fetchedAt", "evidenceId": "ev-economic", "evidencePath": "fetchedAt"},
      {"field": "seriesId", "evidenceId": "ev-economic", "evidencePath": "seriesId"},
      {"field": "semanticIdentity", "evidenceId": "ev-economic", "evidencePath": "semanticIdentity"},
      {"field": "frequency", "evidenceId": "ev-economic", "evidencePath": "frequency"},
      {"field": "unit", "evidenceId": "ev-economic", "evidencePath": "unit"},
      {"field": "observations.0.date", "evidenceId": "ev-economic", "evidencePath": "observations.0.date"},
      {"field": "observations.0.value", "evidenceId": "ev-economic", "evidencePath": "observations.0.value"},
      {"field": "observations.1.date", "evidenceId": "ev-economic", "evidencePath": "observations.1.date"},
      {"field": "observations.1.value", "evidenceId": "ev-economic", "evidencePath": "observations.1.value"}
    ],
    "seriesId": "FRED:CPIAUCSL",
    "semanticIdentity": "US consumer price index all urban consumers",
    "frequency": "monthly",
    "unit": "index-1982-1984=100",
    "observations": [{"date": "2026-06-01", "value": 323.0}, {"date": "2026-07-01", "value": 323.8}]
  },
  "evidence": [{"evidenceId": "ev-economic", "format": "structured", "content": {"fetchedAt": "2026-08-16T11:45:00Z", "seriesId": "FRED:CPIAUCSL", "semanticIdentity": "US consumer price index all urban consumers", "frequency": "monthly", "unit": "index-1982-1984=100", "observations": [{"date": "2026-06-01", "value": 323.0}, {"date": "2026-07-01", "value": 323.8}]}}],
  "normalizationAttempt": 1
}
```

### Partial validator fixture

```json
{
  "request": {
    "capability": "volatility-term-structure",
    "cutoff": "2026-08-16T12:00:00Z",
    "date": "2026-08-15"
  },
  "candidate": {
    "schemaVersion": "1.0",
    "capability": "volatility-term-structure",
    "provider": "wolfram-language",
    "sourceLocator": {
      "kind": "provider-query",
      "tool": "Wolfram Language",
      "queryDescriptor": "volatility-term-structure:2026-08-15"
    },
    "fetchedAt": "2026-08-16T11:45:00Z",
    "completeness": "partial",
    "evidenceBindings": [
      {"field": "fetchedAt", "evidenceId": "ev-vix", "evidencePath": "fetchedAt"},
      {"field": "date", "evidenceId": "ev-vix", "evidencePath": "date"},
      {"field": "unit", "evidenceId": "ev-vix", "evidencePath": "unit"},
      {"field": "components.VIX9D", "evidenceId": "ev-vix", "evidencePath": "components.VIX9D"},
      {"field": "components.VIX", "evidenceId": "ev-vix", "evidencePath": "components.VIX"}
    ],
    "date": "2026-08-15",
    "unit": "index-points",
    "components": {"VIX9D": 15.2, "VIX": 16.4}
  },
  "evidence": [
    {
      "evidenceId": "ev-vix",
      "format": "structured",
      "content": {"fetchedAt": "2026-08-16T11:45:00Z", "date": "2026-08-15", "unit": "index-points", "components": {"VIX9D": 15.2, "VIX": 16.4}}
    }
  ],
  "normalizationAttempt": 1
}
```

An accepted `complete` result short-circuits the capability. Do not call later providers; represent each skipped planned request truthfully as `not-attempted`. An accepted `partial` result is not a failure: preserve its usable observations and fetch only missing fields or components from the next provider. Never overwrite a usable component while filling another one.

HYG/LQD and RSP/SPY are pair observations. Within a pair, do not mix providers, currencies, or value bases. Intersect raw provider-observed dates only, discard every non-common date before comparison, and then require the configured minimum common history: 6 dates for HYG/LQD and 21 for RSP/SPY. Never synthesize a date, forward-fill a missing leg, carry forward a stale value, or infer a point from a graph. A partial provider may contribute only if it preserves that same pair basis. Otherwise continue to the next provider for the whole missing pair rather than stitching two incomparable legs.

Treasury value-basis labels are semantic, not cosmetic. The validator accepts the US Treasury par yield curve rate basis for the requested date; a constant-maturity series, bond price, yield-to-maturity, real yield, or forward rate is not an interchangeable substitute. For FRED, bind both the exact series ID or exclusive semantic identity and its frequency/unit/history. Treasury and FRED fallbacks remain official/public fallback observations; Wolfram does not become their storage authority.

Pass `collect-market-data` the unchanged invocation-local plan plus one outcome for each requested supported capability instance. Each outcome repeats the exact validator request, its deterministic stable key, and one attempt row for every plan provider in exact order. The economic plan row declares five `scheduledSeriesIds`; submit exactly one distinct outcome for each, and never let a one-series subset claim overall scheduled success. When `validate-market-observation` accepts `completeness:"complete"`, map it to `status:"ok"`, put the accepted normalized observation object unchanged at that stable key, include the unchanged original `request,candidate,evidence,normalizationAttempt` object as `validationEnvelope`, and use empty `error` and `stage`; every later provider must be truthful `not-attempted` with `validationEnvelope:null`. When it accepts `completeness:"partial"`, map it to `status:"partial"`, use `error:"market_provider_partial"`, keep `stage` empty, include that same original validation envelope, and continue to the next provider. The collector calls the validator again and requires the returned observation to equal `values.<stableKey>` exactly before discarding the temporary envelope. An attempted failure uses `values:{}`, `validationEnvelope:null`, a bounded safe error such as `tool-unavailable`, `permission-denied`, `premium-feed-required`, `provider-no-result`, `provider-timeout`, or `provider-rate-limited`, and `stage:"fetch"` or `stage:"parse"`. Arbitrary scalars, raw/control objects outside the temporary envelope, credential-shaped keys, missing attempts, duplicate stable keys/providers, reordered attempts, flattened Treasury maturities, and planless provider rows are rejected.

Treasury, equity pairs, and economic series are atomic: a later complete fallback replaces the earlier partial observation in effective `values` as a whole, while all provider rows remain visible. They are never stitched field by field. VIX is the only missing-component merge: retain each earlier accepted component, fill only absent symbols, and record each effective component's provider, source locator, observation date, and fetchedAt. Thus an earlier Wolfram VIX level cannot be overwritten by a later fallback while VIX3M is filled.

The raw connector query, temporary plugin inputs, raw evidence, LLM-normalized candidates, validator errors/responses, tool-access payload, capability plan, and collection outcomes are invocation-local control data. Never put them in Notion, the registry, a local runtime ledger, or Report Markdown. An accepted observation may retain its validated public URL or deterministic `sourceLocator.queryDescriptor` as provenance; this descriptor is not the raw tool query. Persist only the ordinary human-readable Collection/Report/Story records already defined by the product schema, using accepted market observations as bounded evidence.

## Contract map

| Contract | Operational rule |
|---|---|
| cboe-independence | Cboe failure never removes an independently successful Google Finance or spreadsheet observation. |
| binance-proxy-unchanged | This package contains no Binance adapter or persisted Binance proxy contract. `btc-usd` remains validatorSupported=false and scheduleEligible=false, so this release neither changes nor invents the separate legacy 24/7 perpetual-proxy acceptance boundary. |

## Capability-chain execution

Run only independent capability chains concurrently. Inside one chain, call providers sequentially in the returned plan order, validate the attempt, and decide complete short-circuit versus partial continuation before starting the next provider. Restore planned capability and provider order when assembling rows. A complete short-circuit makes every later planned provider `not-attempted`; a partial result remains a `partial` row and an explicit gap. Apply the atomic-replacement and VIX-only missing-component policies above instead of generic nested-dictionary merging.

## Observation contract

For every value retain the accepted normalized observation's complete Task 2 shape unchanged. Do not silently compare regular-session close, current regular price, latest quote, premarket, delayed spreadsheet value, percentage, index points, currency, and basis points as if they were equivalent.

Classify market availability as:

- `complete`: all requested independent observations are usable
- `partial`: at least one value is usable and at least one provider or requested field is missing
- `unavailable`: no provider supplies a usable value
- `not-requested`: the run deliberately did not request market observations

When providers disagree beyond a meaningful tolerance, show the discrepancy and lower confidence for the affected interpretation. Do not discard both observations merely because they disagree.

If all market providers are unavailable but at least one news feed succeeded, a limited Report may continue with an explicit data gap. Never manufacture a market value, substitute an unnamed session, or let Cboe availability decide whether spreadsheet evidence is kept.
