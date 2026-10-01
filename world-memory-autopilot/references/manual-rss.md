# Manual RSS compatibility

Use only for an explicit RSS collection/diagnosis request. Normal scheduled
operation uses publisher-web-search.md. These helpers remain for old callers.

The exact RSS.app CSV header order is `ID,Feed URL,Feed Link,Feed Title,Feed Description,Feed Icon,Title,Link,Description,Image,Plain Description,Author,Date`. Prefer `Plain Description` when it is nonempty; otherwise use `Description`. Both routes pass through the same standard-library HTML normalization boundary before evidence or Markdown use. When RSS.app omits `Title` but supplies normalized description text, use that text as the item title; reject a row only when both are empty or its date is absent. The boundary preserves readable text and block/`br` whitespace, resolves entities, removes comments, and discards complete `script`, `style`, `iframe`, `embed`, and `object` subtrees. It never fetches embedded URLs or treats external text as instructions.

## Configured feeds

Call `collect-feeds` exactly once for the resolved Report window. It performs read-only direct HTTP GETs with bounded concurrency and timeout, a stable user agent, and `Cache-Control: no-cache` plus `Pragma: no-cache`. It permits only these fixed RSS.app CSV sources and returns outcomes in this order:

| ID | Name | URL | Offset minutes |
|---|---|---|---|
| financial_juice | FinancialJuice | https://rss.app/feeds/5VaycMAa8SwPhOAP.csv | 0 |
| walter_bloomberg | Walter Bloomberg | https://rss.app/feeds/YcRRdWN5eSO3o2LP.csv | 0 |
| wall_st_engine | Wall St Engine | https://rss.app/feeds/Hf52VRUllNu7gABF.csv | 0 |
| first_squawk | First Squawk | https://rss.app/feeds/d68ow40E3dkwaEvN.csv | -540 |
| unusual_whales | unusual_whales | https://rss.app/feeds/nikLNBATmLDuprRz.csv | -540 |
| reuters | Reuters | https://rss.app/feeds/_fSiPEQ8FZXQdj4js.csv | 0 |
| dow_jones | Dow Jones Personal | https://rss.app/feeds/_m6HwVpkVbkV6H1V6.csv | 0 |
| bloomberg | Bloomberg Personal | https://rss.app/feeds/_t07deORnyZW90CjC.csv | 0 |

The top-level result reports `status` (`complete`, `partial`, or `failed`), UTC `windowStart`, `windowEnd`, and `fetchedAt`, `retrievalMethod=direct-http`, `feedSuccessCount`, `feedFailureCount`, total `itemCount`, ordered `sourceOutcomes`, `snapshotId`, `cursor`, `returnedItemCount`, the first deduplicated `items` page, and `nextCursor`. When `nextCursor` is non-null, call `read-feed-page` with exact top-level keys `snapshotId,cursor`, using the returned snapshot ID and cursor without alteration. Append every page's `items` in order and continue with only that page's returned `nextCursor` until null. Never call `collect-feeds` again for the same window. Require the accumulated count to equal the first result's `itemCount`; mismatch, missing snapshot, expired snapshot, or invalid cursor safe-stops before every write. The local snapshot expires after 24 hours and is never persisted to Notion or supplied as evidence; only its unchanged items are evidence.

Each source outcome reports `status`, `parsedItemCount`, `rejectedItemCount`, `windowItemCount`, `retainedItemCount`, `latestPublishedAt`, a safe error category, and retryability. A malformed row is quarantined while valid rows from that feed remain usable; a feed whose nonempty payload contains no valid rows remains a parse failure. This distinguishes a valid empty window from stale data, rejected malformed rows, and transport or parse failure. Apply each source offset before the standard half-open `[windowStart, windowEnd)` test. Deduplicate canonical article URLs only within the current invocation, keep the first configured occurrence, and never scan old Collections to prove global uniqueness.

Use `collect-feeds` output items unchanged as RSS evidence. Never use generic web fetch, web search, browser, or connector tools as RSS transport, substitute collection, or a failed-feed fallback. After `collect-feeds`, general web research is allowed when additional information is needed to verify or enrich a material selected headline. Store that as separate evidence with its own source; it never changes RSS success/failure state, counts, diagnostics, or provenance.


For supplied CSV, normalize-feed is strict: a malformed row rejects the input.
Network collection isolates malformed rows and preserves usable rows with the
rejected-item count. Both paths share feed.parse_feed_csv. Feed transport errors
are observations, not proof of source failure; diagnosis is in deployment.md.

## CLI inputs

| Command | Input | Contract |
|---|---|---|
| collect-feeds | windowStart,windowEnd,timeoutSeconds | fixed-source direct HTTP collection, normalized half-open window filtering, deduplication, and per-source diagnostics |
| read-feed-page | snapshotId,cursor | one ordered continuation page from the invocation-local feed snapshot; no network I/O |
| normalize-feed | feedId,csv | normalized configured-feed outcome |
| collect-feeds | windowStart/windowEnd:aware ISO timestamps with start before end; timeoutSeconds:positive number; the command captures fetchedAt and requires windowEnd not to be in its future |
| read-feed-page | snapshotId:exact opaque ID returned by collect-feeds; cursor:positive integer exactly equal to its latest non-null nextCursor |
| normalize-feed | feedId:one configured ID; csv:string with the exact RSS.app header listed above |

## Manual collection storage

### Failure handling

| Contract | Operational rule |
|---|---|
| partial-feed | One to seven failed feeds preserve every successful item and become explicit Data Gaps. |
| all-feed-safe-stop | Eight failed feeds stop before Collection, Report, Story, or Story Change writes. |
| story-due-confirmed-change | Story integration runs only when 345 elapsed minutes are due, and each Story Change follows a confirmed Story create or update. |

### Collection

Create one Collection before the Report when at least one feed succeeds. Its properties record the UTC window, feed success/failure counts, retained item count, market status, and short gaps. Its Markdown uses this order:

- `# 수집 개요`
- one `## <source name>` section per configured source, with title, published time, article link, and evidence-grounded summary
- `## 시장 데이터`, with every independent provider outcome and its gaps
