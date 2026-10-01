# News discovery for investment insight

Use publisher-web-search-v5. World Memory is an evolving investment research notebook: retain important events, useful reporting, interpretations and testable hypotheses with their sources and uncertainty. Use ordinary editorial trust: when a reputable outlet reports an ordinary development as fact, accept it as a fact with its source link. Relevance to investment judgment comes before article admission labels. Keep numeric validation, Notion schema and confirmed-write ordering unchanged.

## Ordinary editorial trust

Use common-sense knowledge of the outlet's reputation, editorial accountability and identifiable reporting. Established general/financial news outlets, reputable local/sector publications and their clearly attributed wire republications are normally sufficient. This is a semantic judgment, not a new outlet-scoring system or an allowlist. One such source is enough to state an ordinary reported event as fact and cite it. Do not routinely label it unconfirmed, demand an official document or seek an independent second witness. Source links usually suffice; do not prefix every sentence with "reportedly" or "according to".

Preserve distinctions the article itself makes: negotiations are negotiations, a proposal is not an enacted measure, an anonymous-source exclusive retains its stated uncertainty, and opinion/forecasts remain analysis. Investigate further when an actual contradiction, unclear meaning or consequential ambiguity warrants it. Unfamiliar reposts, anonymous social claims and unattributed aggregations are leads to an identifiable source, not automatically facts. These exceptions must not become a universal verification gate.

## Supplementary XML discovery feeds

After required workspace/window checks and only for a new collection, fetch each
of these enabled feeds once as supplementary news candidates:

| Feed key | URL | Timestamp correction |
| --- | --- | --- |
| financialjuice | https://www.financialjuice.com/feed.ashx?xy=rss | none |
| first_squawk | https://rss.app/feeds/d68ow40E3dkwaEvN.xml | subtract 540 minutes |
| reuters | https://rss.app/feeds/_fSiPEQ8FZXQdj4js.xml | none |
| dow_jones | https://rss.app/feeds/_m6HwVpkVbkV6H1V6.xml | none |
| bloomberg | https://rss.app/feeds/_t07deORnyZW90CjC.xml | none |

From the skill root, invoke once per key, replacing `<feed-key>`:

```sh
python3 scripts/financialjuice_feed.py --feed <feed-key> --snapshot-dir /tmp/world-memory-<run-id>/feeds
```

The helper isolates each RSS.app feed in its own subdirectory. Preserve independent
successes if another feed fails. unusual_whales
(`https://rss.app/feeds/nikLNBATmLDuprRz.xml`) is disabled: the 2026-09-28 curl probe
returned HTTP 502 rather than RSS. Do not probe it in scheduled runs until explicitly
revalidated. The four enabled RSS.app feeds each returned 50 parseable items in that
probe; this establishes current access, not long-term reliability or full-window coverage.
Dow Jones had 24 items without pubDate. Keep these as undated candidates, verify
publication time from reporting before assigning them to a window, and never
substitute retrieval time for publication time. Coverage spans exclude undated items.

Use one unique invocation-local directory and reuse it throughout that run.
The helper uses curl once, saves the response before parsing, and reuses cached
success or failure on later calls. Never change directories to retry. HTTP 200
alone is not success: require valid RSS items. On 403/429, timeout, missing curl,
invalid XML or empty content, continue web discovery; do not immediately retry,
change clients or bypass access restrictions. If runtime access is unavailable,
skip the helper and continue research. Feed availability never gates a Report.
These listed XML sources are the scheduled RSS exceptions; do not invoke the
legacy RSS.app collector, CSV builders or its zero-success/no-write rules.

Read all returned candidate headlines, then group related updates into events.
Retain title, article URL, GUID, publication time and retrieval time separately;
use the helper’s normalized UTC dates. First Squawk’s observed GMT-labeled times
are nine hours ahead, matching the existing source-specific correction; the helper
subtracts 540 minutes exactly once. Do not apply that correction to other feeds.
If corrected dates become implausible, treat the timestamp as uncertain and verify it. Deduplicate
by GUID/link and by event meaning. An empty description is normal for a headline
feed. Do not use its numeric headlines as replacements for market-data.md.

Treat these as discovery leads: follow material headlines to the feed’s
linked article or accessible reputable reporting before expanding the claim.
Preserve any attribution or uncertainty; no automatic second-source requirement.
An unresolved useful lead may remain attributed with a concrete next check.

The observed FinancialJuice feed returned 100 items spanning about 5.5 hours, not a guaranteed
six-hour archive or documented fixed capacity. Compare oldest/newest timestamps
with the Report window; search uncovered periods and topics. Never equate 100
items with 100 independent events or stop discovery because the feed succeeded.
Keep raw responses and transport details invocation-local, outside Notion.
A feed failure that searches compensate for is not automatically a Report gap;
disclose an actual remaining coverage limitation that matters to the analysis.

## Find the important events first

Start with the available feed candidates and a broad scan of the current market agenda and the previous Report/active Story context already available. Look for developments likely to change policy, capital flows, earnings, supply chains or risk appetite, including major political meetings, central-bank decisions, trade negotiations, conflicts and corporate events. These are prompts for semantic judgment, not an exhaustive keyword checklist or a new classifier. Search for current developments and upcoming catalysts even when the original announcement predates the report window. Start with one or two broad, publisher-unrestricted queries covering market developments and policy/world events, without naming a desired answer. For example, adapt "<current date> global markets major news policy diplomacy trade" to the run; do not hard-code a country, leader or summit.

Use Bloomberg, FT, WSJ, Barron's, Benzinga and MarketWatch as discovery sources, not a whitelist or a quota of acceptable evidence. Cover each lightly with a focused query; spend further searches on material events and missing topics rather than mechanical broad/focused query pairs for every publisher. Reuters, AP, credible local/sector outlets and official agendas/releases are ordinary follow-up sources. Validate the actual publisher/domain but do not discard a useful off-list result. Scheduled collection uses the supplementary XML helper above, never the legacy RSS.app CSV helpers.

Search across these news areas before selecting the Report's central thesis.
US and KR have priority; include material developments elsewhere with a clear
transmission path. The broad opening queries are a starting point, not a search
budget. Search a missing area directly; do not assume a general market wrap
covered it.

| Area | Concrete discovery targets |
|---|---|
| Companies | Earnings, beat/miss, guidance changes, major contracts/orders, M&A, buybacks, financing, executive changes, product launches and regulatory actions |
| Politics and policy | Government decisions, fiscal measures, elections, legislation, trade talks, tariffs, sanctions and major diplomatic meetings |
| Security | Conflicts, ceasefires, military actions, shipping/security disruptions and their material changes, not just oil-price reactions |
| Industries | Capacity and production, supply chains, capex execution, energy/power, semiconductors/AI infrastructure, demand, pricing and competitive shifts |
| Macro and central banks | New releases, policy decisions, speeches and upcoming catalysts as news; keep numerical market collection under market-data.md |

Discover broadly, then normally retain roughly 3–8 meaningful distinct news
events when evidence supports them. This is a selection guide for Collection
news briefs, not a limit on searches, scanned headlines, sources or Story writes;
retain more when warranted and fewer when genuinely sparse. Market observations
do not count toward this news guide. Preserve useful company/industry events
even when they do not change the overall market stance.

Normally retain no more than about two distinct events for one subject; merge
repeated headlines and price reactions to the same event. Do not let one leader,
war, oil story or mega-cap crowd out other material developments. Override the
soft concentration guide when evidence warrants it, not to avoid researching
other areas. Prioritize earnings and guidance surprises; balance company,
institution, policy and industry developments without inventing category quotas.

Before drafting, compare selected events with the candidate pool and the areas
above. Follow up an unsearched or thin area, and repair failed searches using
accessible sources instead of interpreting failure as no news. Keep these
selection judgments internal; do not add a review checklist to the Report.

Publisher homepages, topic pages and live-news indexes are discovery surfaces. Do not store a landing page as if it were a dated article, but follow its material headlines to article links or accessible coverage before discarding it. A blocked original can be followed by searching its headline or event across publishers.

Search date operators are hints, not proof of article recency: inspect actual publication/update dates. If a query produces only old results or no useful hits, simplify it, drop restrictive domain/date operators, or inspect a current headline index. Do not repeat the same unsuccessful query per publisher or conclude that nothing happened. Keep discovery broad enough to find continuing events; use dates afterward to describe what is new versus continuing.

Before writing, ask within the existing analysis pass: does the selected material account for the dominant events and near-term catalysts visible in the current search results and existing context? If a major known event is absent, do a targeted search or carry it forward with its last known status and next check. Do not let a six-hour cutoff, paywall, missing exact timestamp or one reporting origin erase it. This is a relevance check, not a second LLM reviewer or an obligation to build an exhaustive news inventory.

## Follow a lead through accessible reporting

For a material Bloomberg/FT or other paywalled lead, search the event, entities, distinctive claims and important numbers without restricting the query to that publisher. Read accessible reporting, an authorized republication, a summary explicitly attributing the original, or an official source. Original full text is optional. Do not repeatedly open known denials, bypass access controls or reconstruct the blocked article from snippets.

Record who originally reported the claim and which source was actually consulted. An accessible article saying "according to Bloomberg" is usable evidence of that reported development. A clear publisher-attributed search excerpt can also support the claim it actually states. Do not claim to have read an inaccessible original or invent omitted details. A bare or ambiguous headline is a lead for follow-up, not a license to invent the event particulars.

Syndication/requotation is a useful access route. Several copies of one report have one reporting origin; they do not become several independent witnesses. That bookkeeping rule does not disqualify the report, lower quality automatically, require another origin, or create a Data Gap. Write naturally, for example "Bloomberg 보도에 따르면 …; 접근 가능한 ○○ 보도에서 해당 내용을 확인했다." Use more direct corroboration when available and worthwhile, but never require two independent sources for every event or exclusive.

Spend verification effort where it changes the investment interpretation: whether a meeting is proposed or scheduled, whether a measure is a proposal or enacted policy, the time horizon, the affected companies and the magnitude. A reasonable default is one or two focused follow-ups per material event; unresolved high-impact ambiguity can justify another. Stop when the important distinction is clear. Do not use official-document availability as a universal prerequisite.

## Facts, reporting, analysis and hypotheses

All four belong in this memory. Distinguish them through ordinary prose:

- Observed data or an announced action: describe the observation and as-of date.
- A named publisher's report or exclusive: attribute it, including reported plans or negotiations.
- A source's interpretation: say whose analysis it is and why it matters.
- Our investment hypothesis: explain the possible transmission path, affected assets/industries, counterevidence and next check.

Ordinary factual reporting from a reputable outlet belongs with facts; it does not need an uncertainty label merely because it comes from journalism. Any of these may support a Key Takeaway or an evolving Story when material. An unconfirmed report may change market expectations; it need not be confined to a throwaway watch list. Preserve uncertainty in the claim itself rather than banning it from analysis. Do not turn a rumor, allegation or scenario into an established event, or confuse price reaction with proof of the report. Conflicting accounts may be useful investment context: state the disagreement and its consequences instead of deleting the entire topic.

## Time and continuity

The report window is a collection/update window, not an expiry date for events. Preserve publication time when available, otherwise use its displayed date or say timing is unclear; retrieval time is not publication time. Distinguish a new announcement, a new development, newly found reporting and continuing context in plain language. Exact minute-level timestamps are not required for useful inclusion.

Compare with the previous Report and relevant Collection when accessible; use already available Story context without expanding briefing runs into whole-DB Story scans. If optional previous prose is unavailable, use visible context and avoid claiming a definitive change from the missing baseline. Do not stop an otherwise useful report solely for that gap. Required workspace/Reports-view access checks still apply. Do not create a duplicate Story when its identity cannot be resolved.

A summit announced earlier remains relevant while its date, agenda, likely outcomes or market expectations matter. Include its current status, possible transmission and next observable milestone without presenting old news as new. An old article can supply background to a current thesis. A fresh headline with unchanged substance alone does not justify a duplicate Story change.

A useful new Report may be based on a material event, a changed expectation, meaningful market movement, a new connection among existing evidence or an upcoming catalyst. It does not require a newly published independently confirmed article. Avoid empty repetition: when adequate coverage yields no useful update or context to convey, reuse an applicable current-window report or use the existing no-change completion convention. If collection actually fails, say so rather than claiming no change.

## Store useful content, not eligibility verdicts

Use the existing Collection schema and concise prose: source/title/link, the supported development or interpretation, original reporting origin when different, consulted source, known date, and why it matters. Link related coverage under one event rather than presenting syndicated copies as distinct events. Retain a material unresolved lead with a concrete next check when useful. Omit RSS feed success/failure fields and do not use RSS payload builders. If Collection storage fails, preserve this source trail in Report sources.

Keep any search coverage note short. There is no per-publisher minimum, fixed independent-source count, or "eligible core evidence" score. Zero retained Bloomberg/FT articles, a paywall, a syndicated story or normal indexing delay are not by themselves Data Gaps. Do not expose internal English admission labels or query counts in the investment narrative.

Data Gaps should identify missing information that could change the conclusion, unresolved material contradictions, insufficient requested market history or actual collection/storage failures. Confidence reflects the thesis and evidence available, not the number of independently authored articles. Data Quality reflects whether the observations needed for this report were obtained, not source prestige, paywall status or a complete set of six publishers. Distinguish missing bill text that leaves an important provision uncertain from merely missing a bill number after the substantive claim was reported clearly.

Normal weekends/holidays and expected macro publication lags are as-of context, not automatic report failures. Use completed sessions for a weekend overview. Never label an old quote real-time or weaken the current-price validator; only an analysis that truly needs a fresh current price should treat its absence as a relevant gap.

The Report should spend its space on what changed, why it matters, possible beneficiaries/losers, transmission, alternative explanations and next checks. Sources explain where these ideas came from. Do not turn the report into a compliance log. No new property, verification enum, persistent state or extra LLM pass is required.


## Final editing within the same plan

Before submitting the one plan, review each proposed Data Gap for the specific
missing fact and how it could affect the conclusion. Normal market closure,
expected release lag, a paywall or single reporting origin alone belongs in
brief source/as-of context. Remove internal admission labels and query counts
from reader-facing prose. Retain qualifications that matter, including a
missing denominator or a disputed claim. This is a semantic editing obligation
in the existing drafting/one-repair allowance, not a keyword-based validator or
an extra model pass. Apply the same standard to manual and scheduled runs.
