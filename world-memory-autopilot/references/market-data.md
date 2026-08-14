# Market data

Treat every provider as an independent observation. Market data enriches the news evidence; no single provider is an authority gate for the Report.

## Deterministic CLI

| Command | Exact input keys | Output purpose |
|---|---|---|
| market-data-plan | registry | independent provider collection plan |
| collect-market-data | providers | combined supplied-provider snapshot |

## Structured CLI input shapes

| Value | Closed shape |
|---|---|
| collect-market-data.providers[] | exact keys provider,status,values,error,stage; provider:nonempty string; status:ok, error, or not-attempted; ok has nonempty values plus empty error/stage; error has empty values, safe error, and stage fetch or parse; not-attempted has empty values/error/stage |
| values.<observation> | canonical exact keys value,instrument,sessionBasis,observedAt,currency,unit,source,freshness; value:number; observedAt:aware ISO timestamp; currency:string or null; all other fields:nonempty strings |

`market-data-plan` accepts exactly `{registry}`, validates the complete `notion-native-v2` registry, and returns three independent caller-owned requests in this order: Google Finance, spreadsheet, Cboe. The spreadsheet request is derived only from `marketSources.vixSpreadsheet` and carries this exact read-only source contract:

- public CSV: `https://docs.google.com/spreadsheets/d/15xqjZq8di2UqrePpYR_p72j5FCj-WTEDC4rdjZSqc_w/export?format=csv&gid=0`
- ordered symbols: `VIX9D`, `VIX`, `VIX3M`, `VIX6M`

The helper reports `externalIo:false`; the Workspace Agent, not Python, performs the read. Never mutate the spreadsheet, search Drive by title, substitute a private locator, or persist fetched values in the registry.

Supply one provider object for every requested provider, including a truthful `not-attempted` row when the caller intentionally did not perform it. Key `values` by a stable observation name such as `SPY.current-regular-price`; a value may be a simple scalar for compatibility or the canonical observation record above. An `ok` result needs at least one usable value and empty `error`/`stage`. An attempted failure uses `values:{}`, a safe error category, and `stage:"fetch"` or `stage:"parse"`. `not-attempted` uses empty `values`, `error`, and `stage`; it remains visible but creates no data gap. The CLI closes and validates the provider envelope, sanitizes attempted failure detail, and passes successful observation leaves through unchanged; it performs no provider fetch or semantic market normalization.

## Contract map

| Contract | Operational rule |
|---|---|
| cboe-independence | Cboe failure never removes an independently successful Google Finance or spreadsheet observation. |

## Providers

| Provider | Role | Independent failure behavior |
|---|---|---|
| Google Finance | quoted market observations | Preserve values when spreadsheet or Cboe fails. |
| spreadsheet | exact registered public VIX CSV observations | Preserve values when Cboe parsing fails. |
| Cboe | exchange-specific volatility and derivatives observations | Mark only Cboe fields unavailable when retrieval or parsing fails. |

Collect providers concurrently when possible and normalize each into provider, status, values, safe error, and attempted failure stage. Restore configured input order after concurrency. Merge successful values in declared order; on a key disagreement, keep the first successful observation while retaining the provider outcome for interpretation.

## Observation contract

For every value retain the instrument, named session basis, observed timestamp, currency, unit, source, and freshness. Do not silently compare regular-session close, current regular price, premarket, delayed spreadsheet value, percentage, index points, currency, and basis points as if they were equivalent.

Classify market availability as:

- `complete`: all requested independent observations are usable
- `partial`: at least one value is usable and at least one provider or requested field is missing
- `unavailable`: no provider supplies a usable value
- `not-requested`: the run deliberately did not request market observations

When providers disagree beyond a meaningful tolerance, show the discrepancy and lower confidence for the affected interpretation. Do not discard both observations merely because they disagree.

If all market providers are unavailable but at least one news feed succeeded, a limited Report may continue with an explicit data gap. Never manufacture a market value, substitute an unnamed session, or let Cboe availability decide whether spreadsheet evidence is kept.
