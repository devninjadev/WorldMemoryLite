# World Memory Autopilot 0.12.0

`world-memory-autopilot-v0.12.0.zip` installs a SQL-free, Notion-native World Memory skill for ChatGPT Workspace Agents and the official Notion MCP.

> **Independent release line:** `WorldMemoryLite` is separate from the legacy `WorldMemorySkillChatGPT` repository. Publishing here does not update existing installations automatically. Existing users must explicitly opt in, pause the old schedule, install this package, and complete the documented v0.11.x migration before resuming operation.

## Install

1. Install `world-memory-autopilot-v0.12.0.zip` as the workspace skill.
2. Connect the official Notion MCP. Allow setup and schema-create permissions only during bootstrap, then reduce access to normal read/write after the live canary; destructive permissions remain disabled.
3. Run the explicit fresh bootstrap. It creates a new `World Memory · Notion Native` Hub and four database containers, each with an initial data source: `World Memory Collections`, `World Memory Stories`, `World Memory Story Changes`, and `World Memory Reports`.
4. Configure the saved Notion views `Reports Recent` and `Stories Current`, then complete the finite schema-and-view read-back. Run the read-only public CSV canary and require the ordered VIX symbols `VIX9D`, `VIX`, `VIX3M`, and `VIX6M`; the setup must never mutate that spreadsheet.
5. Embed the validated `notion-native-v2` registry, including the exact public VIX CSV source contract, in a regenerated scheduled prompt.
6. Create the schedule. The creation default is a one-hour interval; the operating recommendation is about three hours. Confirm the active setting rather than assuming it changed.

The registry is an immutable installation address book for the workspace, Hub, four data sources, two saved views, and the approved public market source. Hub addresses retain `pageId` plus its page URL; data source addresses retain only `dataSourceId`, not database container IDs or URLs; view addresses retain only their exact URL. `marketSources.vixSpreadsheet` retains only the exact public CSV URL and ordered symbols, never observations or fetch state. Do not put credentials or mutable run state in it.

## Normal operation

Each window first reads `Reports Recent` through the official Notion MCP query tool's explicit view mode and reuses an existing Report when present. The scheduled prompt never sends SQL-shaped input, never invokes the SQL backend, and has no SQL fallback. A new run collects the fixed news feeds and independent market observations, writes a readable Collection, creates exactly one Report, and reads `Stories Current` only for six-hour Story integration when due. It does not query recent Collections. Stories retain the current market thesis; Story Changes explain confirmed material creates or updates.

Runtime timestamps and Report window dates are deterministically converted to whole UTC minutes before comparison, computation, and storage. This matches the Notion date surface, so a second-bearing invocation reuses the minute-aligned Report returned by `Reports Recent` instead of creating a narrow duplicate window.

A partial source failure does not erase successful news or market observations. In particular, Cboe failure does not discard Google Finance or spreadsheet results. Feed descriptions become readable plain text through one HTML boundary before analysis. If all five news feeds fail, the run stops before writing. Storage or source gaps remain visible in the result.

Each Report uses one generated thesis H1 followed by `Key Takeaway`, `시장 현황`, `중장기 맥락`, `주요 지표들`, `지켜봐야 할 것들`, `관심을 가져볼 만한 이슈들`, and `출처·데이터 안내`. Semantic evidence clusters cover every supplied item exactly once; high-importance evidence can be visible in the Report without forcing a Story write. Confirmed new or reused Reports return their Notion link without duplicating the body, while failed, uncertain, or URL-less delivery returns the generated Markdown fallback.

Normal runs trust ordinary synchronous Notion success, avoid routine verification calls, and keep setup, saved-view changes, schema changes, deletion, movement, and repair outside scheduled operation. The payload adapter preserves each logical leading H1 by sending a harmless empty block before it.

## Upgrade from v0.11.x

v0.11.x migrations must pause the existing schedule, explicitly regenerate the `notion-native-v2` registry and prompt under setup permission, validate `Reports Recent` and `Stories Current` with a saved-view canary plus the public CSV source in read-only mode, then resume. The four Notion schemas do not change; existing Reports and Stories remain readable, and type-agnostic same-window reuse continues across the boundary. The scheduled skill never guesses view URLs, mutates a view or spreadsheet, or upgrades itself.

## Existing installations and rollback

Old `0.10.x` artifacts are rollback-only archives. Their Hubs and records are not auto-migrated, adopted, merged, or deleted by 0.12.0. Install the new release into a clean Hub, pause the old schedule, verify the new schedule, and keep the old Hub as an independent reference. Rollback means stopping the new schedule and deciding separately whether to reactivate an older one; it does not require deletion.

Live acceptance requires a new test Hub and actual Workspace Agent receipts. Local tests validate the package contract but do not claim that live canary has run.
