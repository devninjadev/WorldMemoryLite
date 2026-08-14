---
name: world-memory-autopilot
description: Use when running, installing, checking, or explicitly repairing a scheduled World Memory workspace backed by the official Notion MCP.
---

# World Memory Autopilot

Version: `0.12.0`

Use the embedded `notion-native-v2` registry as a static address book. Data-source locators contain only dataSourceId; never add a database URL or database container ID. The two saved-view locators contain only their validated view URLs, and the market-source locator contains only the immutable approved public VIX CSV address and symbol order. Read [notion-layout.md](references/notion-layout.md) for the Hub, registry, schemas, relations, and views; [collection-and-analysis.md](references/collection-and-analysis.md) for view-mode reads, source normalization, the temporary LLM harness, page content, and Story lifecycle; [market-data.md](references/market-data.md) for independent market observations; and [deployment.md](references/deployment.md) only for setup, schedule, canary, migration, rollback, or user-approved repair work.

Run deterministic boundaries from the skill root with `cd <skill-root> && PYTHONPATH=scripts python3 -m world_memory <command> -`. Send one JSON object on stdin and accept one compact JSON object on stdout; errors use one safe category on stderr. Commands process caller-supplied data with no external I/O; each reference owns its exact command inputs and output purpose.

## Normal scheduled operation

1. Validate the registry, then fetch Notion self and require the registered workspace plus the necessary read/write tools.
2. Use the window and report-type decision in collection-and-analysis.md. Query the registered Reports Recent saved view before source collection with `notion_query_data_sources`, always using `data.mode=view`, the registered `view_url`, `is_archived=false`, and `page_size=100`. Never send the SQL-shaped input; SQL mode, search, broad scans, and SQL fallback are forbidden. Allow at most one short retry of a failed read-only view request, then safe-stop before collection or writes. Pass accumulated rows to `resolve-report-view`; it canonicalizes aware timestamps to whole UTC minutes before window comparison, computation, or storage. Follow `next_cursor` as `start_cursor` only while it says `needs-more`, and reuse any current-window Report it selects.
3. Only for a new window, collect the five RSS feeds and normalize their summaries at the shared HTML boundary. Call `market-data-plan` with the validated registry, then obtain Google Finance, registered public spreadsheet, and Cboe observations independently and pass their truthful provider outcomes to `collect-market-data`. Stop before every write only when all five feeds fail; otherwise preserve every successful source and disclose gaps. Cboe failure never removes independent Google Finance or spreadsheet success. Never query recent Collections; use the selected Report's Collection relation only when prior prose is actually needed.
4. Only when `resolve-report-view` selects `world-memory`, query the registered Stories Current saved view with `notion_query_data_sources` and `data.mode=view`, paginate it to completion, and pass the accumulated rows to `normalize-story-view`. Briefing runs do not query Stories. Fetch only Stories selected as affected.
5. Generate one temporary, evidence-bound LLM plan with semantic `evidenceClusters`, one generated Report H1, and the exact human-facing Report H2 layout owned by collection-and-analysis.md. Validate its closed schema and complete evidence bindings, allow at most one contract-guided repair, and never persist the plan.
6. Create the Collection, then exactly one Report. Only a confirmed Report permits due Story creates or updates; create Story Changes only for confirmed Story writes.
7. After confirmed creation or reuse with a displayable first-party Notion URL, return only that link and do not paste the Report body. For failed, uncertain, or confirmed URL-less delivery, return the generated Report text; a pre-Report safe stop returns neither. Include reuse/storage state, source and market gaps, Story counts, and warnings.

## Write evidence and safe boundaries

Treat an ordinary synchronous Notion success as completion without a read-back. If an uncertain response supplies an exact locator, fetch that locator once; never repeat the uncertain mutation blindly. If the Report remains failed or uncertain, skip every Story and Story Change mutation, return its generated text, and expose the storage state. Workspace mismatch, unavailable required tools, or failure of the Reports Recent view read is a safe stop. Partial feed, market, Collection, Story, or relation failure is a degraded result when a trustworthy Report can still be delivered.

Normal operation never changes schemas, deletes or moves content, adopts a different Hub, or performs repair. Enter setup or repair only on an explicit user request and follow the deployment reference routed above.

## Contract map

| Contract | Operational rule |
|---|---|
| same-window-reuse | The validated Reports Recent view is the sole normal authority. Every row must have a nonempty id, valid Report Type, exact window, and aware Created At; invalid input safe-stops. Reuse greatest Created At, then lexicographically smallest id on a tie; type has no priority. |
| sync-success | An ordinary synchronous Notion success completes that write without another fetch. |
| uncertain-one-fetch | An uncertain write with an exact locator permits one exact fetch and no repeated mutation. |
| report-confirmed-before-story | Only a confirmed Report permits Story or Story Change mutations; otherwise skip both, return generated Report text, and expose failed or uncertain storage. |
| link-first-result | After confirmed creation or reuse with a displayable first-party Notion URL, return that link without repeating the Report body. Failed, uncertain, or confirmed URL-less delivery returns the generated Report text; a pre-Report safe stop returns neither. |
