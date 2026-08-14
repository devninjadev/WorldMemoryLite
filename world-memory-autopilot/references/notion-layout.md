# Notion layout

The fresh Hub title is `World Memory · Notion Native`. Its body contains the exact marker:

`World Memory storage contract: notion-native-v2`

The marker confirms the intended installation surface. It is not execution state or a write receipt.

## Canonical registry

Embed this exact-shape address book in the scheduled prompt after bootstrap replaces the placeholders with connector-returned locators:

```json
{
  "schemaVersion": "notion-native-v2",
  "workspaceId": "<workspace-id>",
  "hub": {"pageId": "<hub-page-id>", "url": "https://www.notion.so/World-Memory-<hub-page-id-without-hyphens>"},
  "collections": {"dataSourceId": "<collections-data-source-id>"},
  "stories": {"dataSourceId": "<stories-data-source-id>"},
  "storyChanges": {"dataSourceId": "<story-changes-data-source-id>"},
  "reports": {"dataSourceId": "<reports-data-source-id>"},
  "views": {
    "reportsRecent": {"url": "https://app.notion.com/p/<reports-database-id-without-hyphens>?v=<reports-view-id-without-hyphens>"},
    "storiesCurrent": {"url": "https://app.notion.com/p/<stories-database-id-without-hyphens>?v=<stories-view-id-without-hyphens>"}
  },
  "marketSources": {
    "vixSpreadsheet": {
      "publicCsvUrl": "https://docs.google.com/spreadsheets/d/15xqjZq8di2UqrePpYR_p72j5FCj-WTEDC4rdjZSqc_w/export?format=csv&gid=0",
      "expectedSymbols": ["VIX9D", "VIX", "VIX3M", "VIX6M"]
    }
  }
}
```

The registry contains immutable addresses only. Never add observations, fetch state, provider results, cursors, run state, locks, model output, or mutable audit fields. `marketSources.vixSpreadsheet` is the package-owned exact public source address and ordered symbol contract; it is not a cache or provider receipt. The four data sources below are the complete storage surface. In Notion's current model, the database container ID and data_source_id are different identifiers, and a database URL contains the database container ID. Consequently, each runtime data source locator stores only dataSourceId; do not persist a database URL, database container ID, or any other field there. The Hub remains a page locator whose URL is bound to its pageId. Saved views are separate read locators: each exact locator has only `url`, the URL path contains one database container UUID, and its only query parameter is the `v` view UUID. Runtime never changes either view.

## Deterministic CLI

| Command | Exact input keys | Output purpose |
|---|---|---|
| validate-registry | schemaVersion,workspaceId,hub,collections,stories,storyChanges,reports,views,marketSources | validated normalized registry address book |
| schema | (none) | independent logical schema manifest |

## Structured CLI input shapes

| Value | Closed shape |
|---|---|
| validate-registry | the exact Canonical registry object above; every ID is a UUID string; hub has pageId,url; each data source has only dataSourceId; each view has only url with exactly one database UUID path locator and one v UUID query parameter |

Use connector-returned UUIDs, not the angle-bracket placeholders. UUID input may contain hyphens or omit them and is normalized to lower-case dashed form. The Hub URL must use HTTPS on `notion.so`, `notion.com`, or a subdomain and its final path segment must contain exactly the Hub `pageId`; a title prefix and omitted UUID hyphens are allowed. Each data source locator's exact closed shape is `{dataSourceId}`. Extra keys, including `url` and `databaseId`, are invalid there. Each view locator's exact closed shape is `{url}` and accepts only an HTTPS first-party Notion URL with no fragment or extra query parameters.

## Saved read views

| Registry key | Data source | Title | Configuration |
|---|---|---|---|
| reportsRecent | reports | Reports Recent | `SHOW "Name", "Report Type", "Window Start", "Window End", "Created At", "Collection", "Stories"; SORT BY "Window End" DESC, "Created At" DESC` |
| storiesCurrent | stories | Stories Current | `SHOW "Name", "Status", "Category", "Regions", "Importance", "Confidence", "Current View", "First Seen", "Last Evidence At", "Last Updated", "Related Stories", "Created At"; FILTER "Status" != "resolved"; SORT BY "Last Evidence At" DESC, "Last Updated" DESC` |

Normal operation reads these saved views through `notion_query_data_sources` only with the explicit view-shaped input `data.mode=view`. The older dedicated view tool is deprecated. Never send the SQL-shaped input; SQL mode, semantic search, and runtime view mutation are not authority surfaces.

## Data sources

| Registry key | Data source title |
|---|---|
| collections | World Memory Collections |
| stories | World Memory Stories |
| storyChanges | World Memory Story Changes |
| reports | World Memory Reports |

## Schemas

`Required` describes the logical contract. `Cardinality` is the number of values accepted per page property. Long prose belongs in page Markdown, not in extra properties.

### Schema: collections

| Property | Type | Required | Values or target | Cardinality |
|---|---|---|---|---|
| Name | title | yes | — | one |
| Window Start | date | yes | — | one |
| Window End | date | yes | — | one |
| Feed Success Count | number | yes | — | one |
| Feed Failure Count | number | yes | — | one |
| Item Count | number | yes | — | one |
| Market Data Status | select | yes | options=complete,partial,unavailable,not-requested | one |
| Data Gaps | rich_text | no | — | one |
| Created At | created_time | no | — | one |

### Schema: stories

| Property | Type | Required | Values or target | Cardinality |
|---|---|---|---|---|
| Name | title | yes | — | one |
| Status | select | yes | options=emerging,active,cooling,resolved | one |
| Category | select | yes | options=macro,rates,fx,equity,credit,commodity,policy,geopolitics,technology,other | one |
| Regions | multi_select | yes | options=US,KR,CN,JP,EU,GLOBAL | many |
| Importance | select | yes | options=high,medium,low | one |
| Confidence | select | yes | options=high,medium,low | one |
| Current View | rich_text | yes | — | one |
| First Seen | date | yes | — | one |
| Last Evidence At | date | yes | — | one |
| Last Updated | date | yes | — | one |
| Related Stories | relation | no | target=stories;self=true | many |
| Created At | created_time | no | — | one |

### Schema: storyChanges

| Property | Type | Required | Values or target | Cardinality |
|---|---|---|---|---|
| Name | title | yes | — | one |
| Observed At | date | yes | — | one |
| Change Type | select | yes | options=created,strengthened,weakened,reframed,relationship-changed,cooled,resolved | one |
| Direction | select | yes | options=strengthens,weakens,reframes,connects,closes,neutral | one |
| Strength | select | yes | options=high,medium,low | one |
| Confidence | select | yes | options=high,medium,low | one |
| Primary Story | relation | yes | target=stories | one |
| Related Story | relation | no | target=stories | many |
| Related Report | relation | no | target=reports | many |
| Related Collection | relation | no | target=collections | many |
| Created At | created_time | no | — | one |

### Schema: reports

| Property | Type | Required | Values or target | Cardinality |
|---|---|---|---|---|
| Name | title | yes | — | one |
| Report Type | select | yes | options=briefing,world-memory | one |
| Window Start | date | yes | — | one |
| Window End | date | yes | — | one |
| Stance | select | yes | options=risk-on,neutral,defensive,mixed | one |
| Confidence | select | yes | options=high,medium,low | one |
| Data Quality | select | yes | options=complete,partial,limited | one |
| Data Gaps | rich_text | no | — | one |
| Collection | relation | no | target=collections | many |
| Stories | relation | no | target=stories | many |
| Created At | created_time | no | — | one |

## Property transport

Use ordinary Notion property values. At the MCP boundary, dates use `date:<Property>:start` plus `date:<Property>:is_datetime`. Relations contain confirmed page IDs. Collection, Story, Story Change, and Report bodies are readable Markdown.
