# Deployment

Use this reference only for explicit setup, deployment, canary, rollback, or user-approved repair. Normal scheduled operation follows `SKILL.md` and cannot enter this mode by itself.

## Deterministic CLI

| Command | Exact input keys | Output purpose |
|---|---|---|
| bootstrap-plan | workspaceId | finite fresh-install action plan |
| resolve-registry-discovery | workspaceId,candidates | bounded read-only registry recovery result |
| render-scheduled-prompt | schemaVersion,workspaceId,hub,collections,stories,storyChanges,reports,views,marketSources | self-contained scheduled prompt |
| verify-live | registry,workspaceId,toolAccess,schemaProjections,viewProjections | validation of supplied canary evidence |

## Structured CLI input shapes

| Value | Closed shape |
|---|---|
| bootstrap-plan.workspaceId | UUID string |
| resolve-registry-discovery | exact keys workspaceId,candidates; candidates is the bounded result of one exact-title Notion search plus exact candidate fetches |
| candidates[] | exact keys pageId,url,title,marker,workspaceRoot,installation; installation is null for a non-v2 candidate or has exact keys databases,views for a v2 candidate |
| installation.databases | exact keys collections,stories,storyChanges,reports; each has title,databaseUrl,parentPageId,dataSourceId,properties |
| installation.views | exact keys reportsRecent,storiesCurrent; each has name,databaseUrl,viewId,dataSourceId,displayProperties,sorts |
| render-scheduled-prompt | the exact Canonical registry object in notion-layout.md |
| verify-live.registry/workspaceId | the exact Canonical registry plus the same workspace UUID |
| verify-live.toolAccess | exact boolean keys fetchSelf,queryDataSources,fetchPages,createPages,updatePages; all true |
| verify-live.schemaProjections | exact keys collections,stories,storyChanges,reports; each value has exact keys dataSourceId,properties |
| schemaProjections.<key>.properties | exact property-name to property-type string mapping from notion-layout.md |
| verify-live.viewProjections | exact keys reportsRecent,storiesCurrent; each value has exact keys url,dataSourceId,configuration and must match registry plus the saved-view contract |

`verify-live` validates only evidence already supplied by the caller; it does not contact Notion. Each `schemaProjections` data-source ID must match the registry, and its property mapping must include every schema property exactly once. Each `viewProjections` row must bind the registry URL to the expected data source and exact saved configuration.

## Contract map

| Contract | Operational rule |
|---|---|
| setup-separation | Fresh setup and repair are explicit user-approved modes; scheduled operation cannot create or change schema, delete, move, adopt, or repair storage. |

## Official capability check

Before changing platform-dependent behavior, confirm the current official surfaces:

- [OpenAI Workspace Agents](https://help.openai.com/en/articles/20001143-chatgpt-workspace-agents-for-enterprise-and-business)
- [Notion MCP setup](https://developers.notion.com/guides/mcp/get-started-with-mcp)
- [Notion MCP supported tools](https://developers.notion.com/guides/mcp/mcp-supported-tools)
- [Notion databases and data sources](https://developers.notion.com/guides/data-apis/working-with-databases)
- [Notion 2025-09-03 upgrade FAQ](https://developers.notion.com/guides/get-started/upgrade-faqs-2025-09-03)
- [Notion enhanced Markdown](https://developers.notion.com/guides/data-apis/enhanced-markdown)
- [Notion MCP security](https://developers.notion.com/guides/mcp/mcp-security-best-practices)

Fetch Notion self and confirm workspace identity plus current tool access. Do not infer unavailable or undocumented guarantees.

## Fresh bootstrap

For each installation, create a new private Hub titled `World Memory · Notion Native`; do not search for or adopt pages by title. Put the `notion-native-v2` marker in the Hub, then:

1. Create four database containers, each with one initial data source: Collections, Stories, Story Changes, and Reports. Give each initial data source the non-relation properties in [notion-layout.md](notion-layout.md).
2. Resolve only each initial data source's dataSourceId. A database URL identifies its enclosing database container, not the initial data source; do not put that URL or a database ID in the registry.
3. Add the seven declared relations after all targets exist.
4. Use `notion_create_view` with the matching database create response's database URL or ID and initial `dataSourceId`; these database locators are setup-local and never enter the registry. Configure the two saved views with the exact `SHOW`, `FILTER`, and `SORT BY` strings in [notion-layout.md](notion-layout.md). The `SHOW` directives make the one view response contain every property required by the deterministic helper.
5. Perform the public CSV canary as an explicit read-only HTTPS GET to the exact registered VIX URL. Require the ordered symbols `VIX9D`, `VIX`, `VIX3M`, and `VIX6M`; do not activate a schedule if the static address is invalid or the canary cannot establish the expected source contract. Never mutate the spreadsheet.
6. Read back the Hub locator, each data source's sole registry field `dataSourceId`, every property name/type, and each saved view's returned view ID, data-source binding, display properties, filters, and sorts. Form the queryable HTTPS view URL from the matching database URL plus that view ID as the sole `v` parameter, validate it, and persist only that URL in the registry.
7. Emit and validate the complete `notion-native-v2` registry, including its immutable `marketSources`, then regenerate and embed the scheduled prompt.

Keep setup finite. Do not save provisional addresses, credentials, OAuth tokens, cookies, or connector responses in the package or prompt.

## Schedule

Schedule creation defaults to a six-hour interval (`creationCadenceMinutes=360`). Never claim that an existing active schedule changed until its live setting is verified. Each actual cadence defines its own report window; Story integration remains due every six hours.

The scheduled prompt normally embeds the validated registry and the normal operation boundaries. If both that registry and a complete valid ChatGPT-memory registry are absent, the caller may search Notion exactly once for the exact Hub title, fetch the exact-title candidates, and pass bounded observations to `resolve-registry-discovery`. The helper selects only one workspace-root candidate with the exact v2 marker and exact four-database plus two-view structure; `text` from the connector is normalized only as the transport alias of logical `rich_text`. It returns a recovered registry or one bounded not-found, ambiguous, or structure-mismatch error. It does not contact Notion, write, repair, or persist anything. After this pre-operation recovery boundary, search and broad scans are forbidden again.

Connector Action Constraints permit `notion_query_data_sources` only for the registered saved-view workflow, and the prompt must always send the view-shaped `data.mode=view` input. Do not use the SQL-shaped input, SQL fallback, runtime view mutation, schema changes, deletion, movement, or broad repair.

## Repair and migration

Enter repair or migration only after an explicit request identifies the target and desired change. Read the target first, show a bounded plan and rollback path, obtain approval for schema or destructive work, and verify the changed invariant afterward. Never adopt a title match automatically. A fresh installation never reads or modifies an older Hub.

To migrate any v0.11.x installation, pause its schedule first. Under explicit setup permission, retain the four unchanged database schemas, read back the exact `Reports Recent` and `Stories Current` bindings/configurations, explicitly regenerate the complete `notion-native-v2` registry and scheduled prompt, and run both the saved-view and public CSV canaries in read-only mode; then resume only after both canaries pass. Existing Reports and Stories remain readable, and same-window reuse remains type-agnostic across the boundary. Normal scheduled operation cannot perform this migration, infer view URLs from titles, or mutate its embedded registry.

## Live canary

Use a new test Hub. Verify workspace binding, four schema projections, both saved-view projections, the read-only public CSV source and exact ordered VIX symbols, a SQL-free Reports view read, first Collection and Report, same-window reuse, a partial-source run, and a due Stories view plus Story/Story Change run. Inspect that pages are natural Markdown, use the approved Report layout, and preserve a logical leading H1 through the `<empty-block/>` transport adapter. Measure connector calls, ordinary read-backs, and elapsed time; report the observed values rather than promising unmeasured targets. Do not use an existing operating Hub as the canary.

## Rollback

Stop the new schedule, retain the new Hub for diagnosis, and let the user decide whether to reactivate an older schedule. Do not delete either Hub or combine their data automatically.
