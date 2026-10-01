# Additive company, industry and event extension

Version `entities-v1`; authorized upgrade policy `additive-entities-v1`.
This release adds the following bounded upgrade to an existing registered
`notion-native-v2` installation. It does not replace the four original data
sources, reinterpret their records, or perform historical backfill. The
Workspace Agent owns MCP calls; helpers plan and validate caller-supplied data.

## Entry and compatibility

On an existing registered installation, fetch Notion self and current tool
access, then fetch the exact registered Hub once. Read its human-readable
`World Memory entity extension` section. It contains only the extension
version and the role-to-data-source addresses, not execution state or a ledger.
The core Hub marker remains unchanged. A scheduled prompt may also carry these
addresses in optional `registry.entitySources`; legacy registries remain valid.
Reconcile that address book with the exact Hub section. Conflicting addresses
are an extension conflict; never select a title match or overwrite a binding.
If the Hub section is absent, inspect its child database metadata once before
creating anything: an unregistered existing entity database is an ambiguity,
not proof that creation is safe. Stop the extension for manual resolution.

The fixed entities-v1 upgrade is authorized when the user installs/runs this release
with `entityUpgradePolicy: additive-entities-v1`, or explicitly requests this
upgrade. A legacy schedule with an explicit no-schema-change instruction must
be updated with that policy before automatic upgrading; do not reinterpret it
as consent. The user can disable the extension with `entityUpgradePolicy:
disabled`. Keep ordinary news/report operation when extension tools alone are
unavailable; wrong workspace or missing required core access still stops.

When the Hub says `entities-v1` and all three registered addresses are present,
use them without scanning schemas or records on every run. On first authorized
upgrade, missing version/bindings, or a concrete property/target error, fetch
only schemas for registered data sources. Do not fetch their rows. A newer or
unknown extension version is incompatible: report it and disable extension
writes instead of downgrading it.

## Pure upgrade planner

`entity-extension-plan` accepts exactly:

- `registry`: validated base registry, optionally with `entitySources` mapping
  any already registered subset of `industries`, `companies`, `events` to
  `{dataSourceId}`. All are connector-returned UUIDs, distinct from core sources.
- `workspaceId`, `hubPageId`: from the current exact identity reads.
- `policy`: `additive-entities-v1`.
- `sources`: every registered core/entity role, each with exact keys
  `dataSourceId,properties`. Property descriptors contain `type`, `options`
  for selects (all observed option names), and actual target data-source UUID
  in `target` for relations. They are projections from fresh schema reads,
  never guesses from page contents or titles.

The result is `extensionVersion,status,actions,conflicts`. `status` is `ready`,
`upgrade-needed`, or `conflict`. Actions are connector-neutral descriptions
with only `create-database` or `add-properties`; translate them through the
current official MCP tool schema. There are no delete, rename, move, replace,
type-conversion, view-edit, or data-backfill actions. Existing options and user
properties are preserved. A conflict emits no mutation actions.

Execute base database creations sequentially in industries/companies/events
order. After each confirmed creation, read back that exact returned database
and data-source locator, then append only its role/address to the exact Hub
section before proceeding. Preserve unrelated Hub prose and core bindings.
Reuse each confirmed ID; do not recreate a partial installation. If address
registration fails or is uncertain, stop the extension and report the exact
returned locator; do not blindly create again in this or the next run. An
uncertain mutation permits at most one exact-locator read, not a repeated write.

Within one upgrade, allow at most three base creations and one missing-property patch per registered role; never repeat an unchanged failed/uncertain action. A readback that still lacks the requested addition ends this upgrade as incomplete. Recompute the plan with the new bindings and schema observations, then add
missing properties and relations using actual IDs. Read back changed schemas
once, and require a final `ready` result before marking the Hub `entities-v1`.
Do not write the completion marker after partial failure. No transaction or
search-consistency guarantee is assumed. No locks, durable cursor, per-record
existence proof, or second audit ledger is needed.

Retain successful additions after a partial failure, disable incomplete entity
writes, disclose the gap, and continue core reporting when it remains usable.
Rollback disables entity operations and preserves all pages/properties. Do not
feed a registry with entitySources to an older strict helper: use its unchanged
base registry without the optional key. Never delete the new DBs automatically.

## Storage model

Use `extensions.ENTITY_SCHEMAS` and `EXTENSION_PROPERTIES` as the manifest:

| Role | Properties |
|---|---|
| industries | Name (title), Aliases (text), Definition (text) |
| companies | Name (title), Aliases (text), Tickers (text), Listing Status (select), Industries (relation) |
| events | Name (title), Occurred At (date, optional), Claim (text), Companies, Industries, Collection, Report, Stories (relations) |
| existing stories | add Companies, Industries, Events relations |
| existing storyChanges | add Events relation |

Company identity is its page ID, not a ticker. Store multiple verified
exchange-qualified tickers as newline-separated rich text; aliases include
local-language/English names and non-ticker abbreviations. Do not create
multi-select options per company, industry, event or ticker. Listing Status
has the finite values listed/private/delisted/unconfirmed; absence of a ticker
alone does not prove a private listing status. Parent and subsidiary are
separate companies. An ADR and an ordinary share may reference one issuer but
are different price instruments. Never average their prices or substitute one
listing without checking the requested exchange, security and currency.

An event records an evidence-supported occurrence/claim with source links,
publication time and occurrence time distinguished, corroboration/conflict,
and what changed. A Story remains an evolving interpretation; Story Changes
record the reason/before/after and link supporting Events. Industry pages keep
short scope definitions so similarly named but different concepts stay distinct.

## Semantic work and targeted retrieval

For every new report window with ready, enabled extension, including briefing,
the same temporary LLM plan must include `entityPlan` and `entityReview`. Pass
`entityContext: {policy,readiness,reason}` to validate-llm-plan. Policy is the
observed additive-entities-v1 or disabled setting. Readiness is ready, disabled,
unavailable or incomplete from the exact Hub/tool observations. Disabled policy
requires disabled readiness and vice versa. Non-ready states require a specific
reason; unavailable/incomplete reasons must also appear exactly in report.dataGaps.
The helper derives required review for ready/enabled runs. Context is mandatory;
the old entityReviewRequired flag is rejected. Never change readiness merely to
accept an incomplete plan. No new schema scan is needed for registered ready Hubs.

`entityPlan` keeps these role lists (up to 50 proposals per role):

```text
{
  industries: [{key, name, aliases: [string], definition, evidenceItemIds: [id]}],
  companies: [{key, name, aliases: [string], tickers: [EXCHANGE:TICKER],
               listingStatus, evidenceItemIds: [id],
               memory: {currentView, change, nextCheck}}],
  events: [{key, name, occurredAt: ISO-date-or-aware-time-or-null, claim,
            companyKeys: [key], industryKeys: [key], evidenceItemIds: [id]}]
}
```

Company memory fields are nonempty, evidence-grounded prose. `change` describes
the material update or explicitly explains unchanged significance. Do not
invent a change to justify writing. Legacy optional plans can omit memory;
active required review cannot. Each proposal requires known evidence; event
company/industry keys resolve within this plan. Missing occurrence time is null.
Keys are invocation-local, never persistent IDs.

`entityReview` has exactly one decision per existing evidence cluster:

```text
[{clusterId, disposition: planned|not-applicable|deferred,
  companyKeys: [key], industryKeys: [key], eventKeys: [key], reason}]
```

Review the material subjects, not every incidental name. `planned` binds at
least one proposal for creation or reuse; do not decide persistent identity
before targeted lookup. Referenced proposals must share evidence with that
cluster, and every proposal must be referenced. `not-applicable` means no useful
entity/event action, with a specific semantic reason. `deferred` means useful
work cannot be planned safely, with a specific reason kept in the internal review.
Both non-planned decisions have empty key lists. All role lists may be empty
only with reviewed reasons; macro-only news need not invent companies. A useful
macro event may have no company. Code checks coverage, enums and bindings; the
model checks whether reasons and omissions are justified. No keyword classifier,
extra LLM review call, durable coverage ledger or persisted control JSON.

Produce the evidence clusters and their review decisions before treating the
Report draft as ready. For each material subject, return planned, not-applicable
or deferred with a specific reason. No-change is a completed decision; missing
review is unfinished work. A deferred decision describes a real evidence/access
obstacle, never an excuse for not performing the review.

Use `prepare-report` with exact keys registry,window,validation,relations.
Window has start/end aware ISO strings from resolve-report-view; relations use
the existing report_page relation shape. Validation has the exact validate-llm-plan
input including entityContext. If review fields/cluster decisions are missing,
the helper returns status=needs-review and clustersToReview, with no write request.
Complete that work using the collected evidence and call prepare-report again.
This is completion of the original drafting pass, not a fresh news collection or
another report window. Only status=ready contains the Report request. The Python
report_page builder requires that same validation input and validates review too.
Never bypass it with hand-written create_pages properties/content.

The shared one-repair limit applies to invalid generated content, not permission
to omit review. A report-only fallback must retain valid entityPlan/entityReview
and the same entityContext even if Story decisions are dropped. There is no
entityReviewFailure escape, false-readiness shortcut, or legacy omitted-input
path. If the run cannot finish review, it has no prepared Report and must say
work is unfinished; do not manufacture a no-change decision. Keep routine review
results internal rather than adding a checklist or reasons to the Report.

Before an entity write, reuse an already confirmed page ID or resolve only the
entities touched by this window. Read current search access once and choose the
available Notion search/AI-search tool. Use short name/alias/exchange-ticker
queries scoped to the registered entity data source. Fetch plausible matches
and verify their parent and identity. Inspect notices about ignored filters.
Do not interpret a capped or filtered-out result as proof of absence. Use one
specific alternative query when ambiguity warrants it, then leave linkage
unresolved rather than scanning the DB or merging uncertain companies. New
entities may be created after a reasonable bounded search; rare low-impact
duplicates are preferable to exhaustive pre/post-create scans. LLM reasoning
resolves narrative identity; deterministic code does not merge by string match.

Keep invocation-local key-to-page-ID mappings. Create or update only relevant
industries/companies and genuinely new events after a confirmed Report; then
link confirmed Events to confirmed Stories/Story Changes. Reuse the Collection
and Report IDs already obtained by the core workflow. Resolve source links from
known evidence IDs, not invented URLs. Write readable evidence/corroboration
Markdown; never persist entityPlan/entityReview or temporary keys.

### Company memory and navigation

For a new company or material new evidence about an existing one, keep readable
sections for 현재 관점, 중요한 변화, 관련 근거, 다음 확인점 in its page body. Use the
validated memory prose; distinguish reported fact, interpretation and hypothesis.
Retain useful earlier evidence/history and unrelated user prose. Append a dated
material development or narrowly revise the current view, rather than replacing
the whole page. Include verified source links and confirmed relevant Event and
Story page links so the company page is an entry point into its accumulated
research. No new database property is required. Repeated coverage without new
significance reuses existing notes; do not append duplicate updates.

Use the existing company page obtained during identity resolution. If its body
cannot be read, skip that body update and disclose the gap instead of replacing
unknown content. When an Event or Story becomes confirmed after the company
write, add its readable link narrowly to that company note. Planned, reused,
updated, unresolved and failed work must be distinguished in completion.

### Complete confirmed links

After confirmed Story writes, link those Story IDs back to the confirmed Report,
preserving its existing Stories relation. Existing confirmed Story IDs may be
included at Report creation; newly created IDs are added afterward. Related
confirmed Events must link to confirmed Stories and their Changes. Pass `events`
as a list of confirmed Event page UUIDs to `story_change_page` when already
available; otherwise patch the confirmed Change after Event creation.

`notion_payloads.append_relations(page_id, existing_relations,
confirmed_relations)` builds one `update_properties` request for Stories,
Companies, Industries or Events. Inputs map property names to lists of confirmed
page UUIDs. Normalize fetched page URLs before calling. Supply the complete
current relation for every property being changed, even when empty; never assume
a failed/truncated read means empty. Reuse already available projections and
known freshly created properties. If a needed projection is missing, fetch only
that exact page. The helper preserves prior order, deduplicates and returns None
for a no-op. It does not fetch, execute or prove successful storage.

Execute only nonempty patches through current official MCP. A failed/uncertain
relation is a disclosed link gap, not a reason to erase successful Reports,
Stories, Changes or Events. Ordinary synchronous success suffices; no routine
readback or blind retry. Do not backfill unrelated past reports or links.

When updating an existing company, merge verified aliases/tickers with its
current values; do not replace them with the subset in this window. Existing
relations are preserved when appending a new link.

For a new company or a relevant missing/additional industry link, use collected
evidence and available company notes to identify what the company sells for
revenue, or concretely plans to commercialize. Profitability is not required;
vague ambitions, purchasing, internal use, investment exposure and news
co-occurrence alone do not establish industry membership. For example, buying
optical connectivity does not make an AI model provider an optical supplier.
Define the intended business scope, then compare existing candidates' names,
aliases and definitions through the bounded lookup above. Reuse a semantically
matching industry; if none fits and evidence supports the business, create a
briefly defined industry and link it. Creation is a normal choice, not a last
resort; do not force a nearby but mismatched category. Include needed industries
in the same entityPlan before Report preparation; resolve/create and link them
after the Report is confirmed. Distinguish concrete planned entry from current
sales in the existing company note. Event/Story industry links may represent
effects or demand without implying company membership.

Apply this judgment only when considering a new link. Do not routinely
re-investigate companies, revalidate existing links, or backfill classifications.
Leave unsupported new links unset; do not require extra research, similarity
scores, review objects or validation gates. Existing mislinks are handled by
separately requested manual cleanup, not recurring automatic purges.

Existing page bodies are appended/edited narrowly. Do not reread every ordinary
successful write. Failed optional entity writes do not roll back a Report or
erase successful evidence. Report created/reused/unresolved counts and gaps.

Never backfill all historical entries during ordinary operation. Add links to
an old Story only when new evidence actually touches it. Entity search and this
upgrade are the explicit bounded exceptions to the base workflow's search and
schema-write restrictions; core Report reuse still uses its saved view.

Legacy prompts may spell the same policy `entity_upgrade_policy`; an explicit disabled/no-schema policy is never overridden merely because the skill was upgraded.


## Required completion check

For every newly confirmed Report, call `complete-entity-review` after entity,
company-memory and relation work, including when nothing needed writing. Input:

```text
{
  validation: {candidate, knownStoryIds, evidenceItemIds, expectedReportType,
               entityContext},
  outcomes: [{role, key, status, pageId, reason}],
  linkGaps: [string]
}
```

`validation` is the same input accepted by validate-llm-plan. This check reuses
it without another LLM call. Role is industries/companies/events. Supply exactly
one outcome per proposal; status is created, updated, unchanged, deferred or
failed. Created/updated/unchanged require a confirmed page UUID; other statuses
allow a known page UUID or null. Every outcome requires a specific reason.
Unchanged means a fetched existing page already serves the reviewed evidence;
it does not mean the lookup, review or necessary update was skipped. Created or
updated means all necessary body work succeeded, including company memory.
If a page was created but its required memory update failed, report failed with
that known page ID and retain the successful page; never blindly recreate it.
Record unresolved or failed Report/Story/Event relations in linkGaps. Use only
actual connector results; the helper cannot independently prove external I/O.

The helper checks the plan again, rejects unknown/duplicate outcomes, and counts
missing outcomes as degraded. Deferred review, failed/deferred outcomes and
link gaps also degrade completion. Empty role lists after complete justified
review yield no-change. Explicitly disabled extension yields disabled. Missing
review is rejected before Report creation; it cannot become report-only success.

Use this result inside the current execution only. If outcomes are missing,
complete the remaining planned work or obtain the actual result already returned;
then call complete-entity-review again. Never stop at recording a missing-outcome
warning while safely executable work remains. Failed/deferred outcomes must
represent concrete tool/evidence obstacles and obey existing no-blind-retry rules.

Do not write review decisions, reasons, per-entity counts or outcome summaries to
the Report, a separate page or a ledger. Preserve the normal investment report
format. Disclose actual material source/storage failures concisely under the
existing reporting rules; those are distinct from routine internal review.
Same-window reuse returns the existing Report without new review or backfill.

Python build_user_result accepts the same completion input as entity_completion.
For a newly confirmed Report, omission produces degraded with an explicit review
warning. Disabled is an intentional state, not failed review. Completion summaries
do not override market, Collection, Story or other independently observed failures.
