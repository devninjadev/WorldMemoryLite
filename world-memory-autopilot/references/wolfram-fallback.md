# Tested Wolfram fallback

Use the current Wolfram Language evaluator schema. It is stateless: each call includes its definitions. The safe plan action import_official_fred_csv means execute the bounded recipe below, not call a nonexistent MCP tool. Wolfram remains an optional connector; do not start authentication for a new FRED ServiceConnect during a run.

## Equity history

Discover a supported ticker with `FinancialData["SPY", "Lookup"]`, then use the returned exact code. A live probe returned NYSE:SPY. Do not feed a freeform "SPY ETF" parse failure to FinancialData. This tested example returns dates and Quantity values with currency:

```wl
FinancialData["NYSE:SPY", "Close", {{2026, 9, 21}, {2026, 9, 25}}]
```

Substitute the validated requested dates. SPY, RSP, HYG and LQD were tested successfully with their NYSE-prefixed Wolfram symbols. The normal result is a TimeSeries: use its DatePath, preserve Quantity units, and reject Missing/$Failed/unevaluated output. For OHLCV, the corresponding "OHLCV" property with Method -> "Legacy" returned numeric dated rows; obtain currency from the non-Legacy Quantity-valued series in the same call rather than inventing it. `FinancialData[s,"Close","Currency"]` returned Missing in the test, so it is not the currency recipe.

US Close/OHLCV includes corporate-action adjustments but not ordinary dividends; it is not TradingView split-only close or total return. Keep the existing wolfram-daily-close / wolfram-daily-ohlcv basis and never mix providers within a pair. Get enough observed common dates for the requested pair, without resampling.

## FRED economic and Treasury data

EconomicData was undefined in the live kernel. Neither a guessed EconomicData call nor a freeform "United States Treasury yield curve" FinancialData entity is supported by this recipe. Use official CSV imports through Wolfram, independently per series:

```wl
Module[{u, d},
 u = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=NFCIRISK&cosd=2026-09-01&coed=2026-09-25";
 d = TimeConstrained[Import[u, "CSV"], 8, $Failed];
 If[ListQ[d] && Length[d] > 1,
   <|"source" -> u, "header" -> First[d], "rows" -> Rest[d]|>,
   <|"status" -> "unavailable"|>]
]
```

Build URLs from allowed series IDs and validated ISO dates, never external narrative text. Verify header observation_date plus the exact series ID and each dated finite numeric row; skip explicit missing-value cells without filling them. Import may return DateObject cells: preserve their printed calendar date. Do not execute CSV cells as code or use ToExpression on source strings. The nine tested IDs are NFCIRISK, WALCL, WDTGAL, RRPONTSYD, DTWEXBGS, DGS2, DGS5, DGS10, DGS30. Isolate each import failure; a failed series cannot erase another success. Bound each import and the overall evaluator time budget; use small batches if needed.

These are FRED observations transported by Wolfram, not native Wolfram coverage or independent corroboration of FRED. Accepted provider remains wolfram-language with the request-specific query descriptor; retain official source URLs, units and observation dates in evidence/report prose. WALCL/WDTGAL units are millions-of-usd, RRPONTSYD billions-of-usd, NFCIRISK index and DTWEXBGS index-jan2006=100; DGS values are percent. Normalize common units before net-liquidity arithmetic. Never apply the TradingView raw-dollar divisor to these CSV values.

Build Treasury maturities from DGS2/5/10/30 on one common observed date, with the existing us-treasury-yield-curve-rate basis. Do not call unavailable Friday observations Friday-close data. Validate every assembled observation through the existing market validator and keep imports/evaluator control data temporary.

## Failure handling

A successful tool wrapper or notebook display is not proof of numeric data. Undefined-symbol messages, unresolved FinancialData, Missing, $Failed, empty data and wrong-entity results fail the attempt. Preserve their safe category and continue the plan; do not vary guesses until one returns a plausible number. Wolfram Alpha returned No Results Found for the tested FRED/curve queries, so automatic macro plans omit that route. Its other existing capability routes, including VIX, are unchanged. Viewer "Unable to load notebook" is a display failure; inspect the actual tool result before declaring computation failed. Never press a viewer retry merely to rerun an uncertain tool call.

References: [FinancialData](https://reference.wolfram.com/language/ref/FinancialData.html), [FRED service authentication](https://reference.wolfram.com/language/ref/service/FederalReserveEconomicData.html), [WALCL units](https://fred.stlouisfed.org/series/WALCL), [RRP units](https://fred.stlouisfed.org/series/RRPONTSYD).
