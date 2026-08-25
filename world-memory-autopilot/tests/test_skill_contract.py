"""Behavioral contract tests for the installed notion-native skill."""

from __future__ import annotations

import copy
from datetime import datetime, timedelta
import json
from pathlib import Path
import re
import unittest

from world_memory.bootstrap import build_bootstrap_plan, render_scheduled_prompt
from world_memory.feed import FEEDS, FeedOutcome
from world_memory.market import MarketSnapshot, ProviderResult, combine_market_results
from world_memory.notion_layout import DATABASE_SCHEMAS, HUB_MARKER
from world_memory.notion_payloads import story_change_page
from world_memory.registry import Registry
from world_memory.windows import (
    Window,
    choose_report_type,
    compute_window,
    resolve_same_window,
)
from world_memory.workflow import WriteOutcome, build_user_result, resolve_write_response

from tests.test_cli import (
    MARKET_TOOL_ACCESS,
    REGISTRY,
    STORY_ID,
    TOOL_ACCESS,
    VALID_SPY_PAYLOAD,
    VIX_PUBLIC_CSV_URL,
    VIX_SYMBOLS,
    WORKSPACE_ID,
    registry_discovery_input,
    run_cli,
    schema_projections,
    view_projections,
)
from tests.test_llm_plan import VALID as _CLUSTERED_PLAN
from tests.test_notion_payloads import DECISION, NOW, REGISTRY as REGISTRY_OBJECT
from tests.test_plugin_market import _bind_structured_payload


PACKAGE = Path(__file__).resolve().parents[1]
WORKTREE = PACKAGE.parent
SKILL_PATH = PACKAGE / "SKILL.md"
REFERENCE_PATHS = {
    "notion-layout": PACKAGE / "references" / "notion-layout.md",
    "collection-and-analysis": PACKAGE / "references" / "collection-and-analysis.md",
    "deployment": PACKAGE / "references" / "deployment.md",
    "market-data": PACKAGE / "references" / "market-data.md",
}
CLUSTERED_PLAN = copy.deepcopy(_CLUSTERED_PLAN)
CLUSTERED_PLAN["storyDecisions"][0]["storyLocator"] = STORY_ID
CLUSTERED_PLAN["evidenceClusters"][0]["storyLocators"] = [STORY_ID]


def _valid_collect_market_data_input() -> dict[str, object]:
    plan_result = run_cli(
        "market-data-plan",
        "-",
        stdin=json.dumps({"registry": REGISTRY, "toolAccess": MARKET_TOOL_ACCESS}),
    )
    observation_result = run_cli(
        "validate-market-observation",
        "-",
        stdin=json.dumps(VALID_SPY_PAYLOAD),
    )
    if plan_result.returncode or observation_result.returncode:
        raise AssertionError("market fixture precondition failed")
    plan = json.loads(plan_result.stdout)
    observation = json.loads(observation_result.stdout)["observation"]
    stable_key = "equity.current-price.SPY"
    attempts = []
    for provider in plan["capabilities"]["equity-current-price"]["providers"]:
        if provider == "alpaca":
            attempts.append(
                {
                    "provider": provider,
                    "status": "error",
                    "values": {},
                    "error": "provider-no-result",
                    "stage": "fetch",
                    "validationEnvelope": None,
                }
            )
        elif provider == "wolfram-language":
            attempts.append(
                {
                    "provider": provider,
                    "status": "ok",
                    "values": {stable_key: observation},
                    "error": "",
                    "stage": "",
                    "validationEnvelope": VALID_SPY_PAYLOAD,
                }
            )
        else:
            attempts.append(
                {
                    "provider": provider,
                    "status": "not-attempted",
                    "values": {},
                    "error": "",
                    "stage": "",
                    "validationEnvelope": None,
                }
            )
    return {
        "plan": plan,
        "outcomes": [
            {
                "capability": "equity-current-price",
                "request": VALID_SPY_PAYLOAD["request"],
                "stableKey": stable_key,
                "attempts": attempts,
            }
        ],
    }


def _read(path: Path) -> str:
    if not path.is_file():
        raise AssertionError(f"required installed file is missing: {path.name}")
    return path.read_text(encoding="utf-8")


def _frontmatter(text: str) -> tuple[dict[str, str], bytes]:
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].strip() != "---":
        raise AssertionError("SKILL.md must begin with YAML frontmatter")
    try:
        closing = next(index for index, line in enumerate(lines[1:], 1) if line.strip() == "---")
    except StopIteration as exc:
        raise AssertionError("SKILL.md frontmatter is not closed") from exc
    raw = "".join(lines[: closing + 1]).encode("utf-8")
    parsed: dict[str, str] = {}
    for line in lines[1:closing]:
        key, separator, value = line.partition(":")
        if not separator or not key.strip() or key.strip() in parsed:
            raise AssertionError("frontmatter must contain unique scalar keys")
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        parsed[key.strip()] = value
    return parsed, raw


def _table_after(text: str, heading: str) -> list[list[str]]:
    marker = heading + "\n"
    if marker not in text:
        raise AssertionError(f"missing table heading: {heading}")
    tail = text.split(marker, 1)[1].lstrip("\n")
    lines = tail.splitlines()
    table: list[list[str]] = []
    started = False
    for line in lines:
        if line.startswith("|"):
            started = True
            cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
            table.append(cells)
        elif started:
            break
    if len(table) < 3:
        raise AssertionError(f"table under {heading} is incomplete")
    return table


def _parse_schema_table(text: str, key: str) -> dict[str, dict[str, object]]:
    table = _table_after(text, f"### Schema: {key}")
    expected_header = ["Property", "Type", "Required", "Values or target", "Cardinality"]
    if table[0] != expected_header:
        raise AssertionError(f"schema header for {key} is invalid")
    parsed: dict[str, dict[str, object]] = {}
    for cells in table[2:]:
        if len(cells) != 5:
            raise AssertionError(f"schema row for {key} has the wrong width")
        name, property_type, required, values, cardinality = cells
        descriptor: dict[str, object] = {
            "type": property_type,
            "required": {"yes": True, "no": False}[required],
            "cardinality": cardinality,
        }
        if values.startswith("options="):
            descriptor["options"] = values.removeprefix("options=").split(",")
        elif values.startswith("target="):
            pieces = values.split(";")
            descriptor["target"] = pieces[0].removeprefix("target=")
            if len(pieces) == 2:
                descriptor["self"] = pieces[1] == "self=true"
        elif values != "—":
            raise AssertionError(f"unknown schema values cell: {values}")
        parsed[name] = descriptor
    return parsed


def _documented_schema(descriptor: dict[str, object], property_name: str) -> dict[str, object]:
    expected = copy.deepcopy(descriptor)
    if expected["type"] == "multi_select":
        cardinality = "many"
    elif expected["type"] == "relation" and property_name != "Primary Story":
        cardinality = "many"
    else:
        cardinality = "one"
    expected["cardinality"] = cardinality
    return expected


def _contract_rows(text: str) -> dict[str, str]:
    if "## Contract map\n" not in text:
        return {}
    table = _table_after(text, "## Contract map")
    if table[0] != ["Contract", "Operational rule"]:
        raise AssertionError("contract map header is invalid")
    return {row[0]: row[1] for row in table[2:]}


def _json_block_after(text: str, heading: str) -> object:
    match = re.search(
        rf"{re.escape(heading)}\n\n```json\n(?P<body>.*?)\n```",
        text,
        flags=re.DOTALL,
    )
    if match is None:
        raise AssertionError(f"missing JSON block after {heading}")
    return json.loads(match.group("body"))


def _documented_cli_rows() -> dict[str, tuple[str, str, str]]:
    rows: dict[str, tuple[str, str, str]] = {}
    for owner, path in REFERENCE_PATHS.items():
        table = _table_after(_read(path), "## Deterministic CLI")
        if table[0] != ["Command", "Exact input keys", "Output purpose"]:
            raise AssertionError(f"CLI table header is invalid: {path.name}")
        for command, input_keys, purpose in table[2:]:
            if command in rows:
                raise AssertionError(f"CLI command has multiple owners: {command}")
            rows[command] = (owner, input_keys, purpose)
    return rows


class SkillEntrypointTests(unittest.TestCase):
    def test_frontmatter_is_small_trigger_only_and_versioned(self) -> None:
        skill = _read(SKILL_PATH)
        frontmatter, raw = _frontmatter(skill)

        self.assertEqual(
            frontmatter,
            {
                "name": "world-memory-autopilot",
                "description": frontmatter.get("description", ""),
            },
        )
        self.assertTrue(frontmatter["description"].startswith("Use when "))
        self.assertLess(len(raw), 1024)
        self.assertEqual(skill.count("Version: `0.14.3`"), 1)

    def test_entrypoint_routes_each_detailed_concern_once(self) -> None:
        skill = _read(SKILL_PATH)
        for name, path in REFERENCE_PATHS.items():
            self.assertTrue(path.is_file(), name)
            self.assertEqual(skill.count(f"references/{name}.md"), 1, name)
        self.assertNotIn("| Property | Type |", skill)

    def test_entrypoint_preserves_independent_market_success(self) -> None:
        skill = _read(SKILL_PATH)
        self.assertIn(
            "Cboe failure never removes independent Google Finance or spreadsheet success",
            skill,
        )

    def test_installed_contracts_have_one_detailed_owner(self) -> None:
        documents = {"SKILL.md": _read(SKILL_PATH)}
        documents.update({path.name: _read(path) for path in REFERENCE_PATHS.values()})
        expected_owners = {
            "same-window-reuse": "SKILL.md",
            "sync-success": "SKILL.md",
            "uncertain-one-fetch": "SKILL.md",
            "report-confirmed-before-story": "SKILL.md",
            "link-first-result": "SKILL.md",
            "partial-feed": "collection-and-analysis.md",
            "all-feed-safe-stop": "collection-and-analysis.md",
            "story-due-confirmed-change": "collection-and-analysis.md",
            "setup-separation": "deployment.md",
            "cboe-independence": "market-data.md",
            "binance-proxy-unchanged": "market-data.md",
        }
        observed: dict[str, str] = {}
        for document, text in documents.items():
            for key in _contract_rows(text):
                self.assertNotIn(key, observed, f"duplicate detailed contract: {key}")
                observed[key] = document
        self.assertEqual(observed, expected_owners)

    def test_schedule_prompt_executes_the_same_normal_order_contract(self) -> None:
        prompt = render_scheduled_prompt(Registry.from_mapping(REGISTRY))

        ordered = (
            "Validate the embedded registry",
            "Query Reports Recent before source collection",
            "resolve-report-view",
            "Run collect-feeds exactly once",
            "query Stories Current only when world-memory is due",
            "one temporary LLM plan",
            "Collection -> exactly one Report -> due-only Stories -> Story Changes only for confirmed Story writes",
            "Return a concise user result",
        )
        positions = [prompt.index(fragment) for fragment in ordered]
        self.assertEqual(positions, sorted(positions))

    def test_entrypoint_exposes_one_object_offline_cli_transport(self) -> None:
        skill = _read(SKILL_PATH)
        self.assertEqual(
            skill.count(
                "cd <skill-root> && PYTHONPATH=scripts python3 -m world_memory <command> -"
            ),
            1,
        )
        for rule in (
            "one JSON object on stdin",
            "one compact JSON object on stdout",
            "safe category on stderr",
            "no external I/O",
        ):
            self.assertIn(rule, skill)

    def test_entrypoint_routes_due_and_window_details_to_one_reference(self) -> None:
        skill = _read(SKILL_PATH)
        self.assertIn(
            "Use the window and report-type decision in collection-and-analysis.md",
            skill,
        )


class LayoutAndSourceDocumentationTests(unittest.TestCase):
    def test_readme_marks_connectors_optional_and_live_acceptance_unverified(self) -> None:
        readme = _read(WORKTREE / "README.md")
        for required in (
            "Alpaca and Wolfram are optional connectors",
            "existing official and public fallbacks remain available",
            "does not prove live Alpaca, Wolfram, Workspace, or Notion acceptance",
            "keeps only the newly built versioned World Memory ZIP in that output directory",
        ):
            with self.subTest(required=required):
                self.assertIn(required, readme)

    def test_structured_cli_inputs_have_closed_nested_shapes(self) -> None:
        collection = _table_after(
            _read(REFERENCE_PATHS["collection-and-analysis"]),
            "## Structured CLI input shapes",
        )
        self.assertEqual(collection[0], ["Value", "Closed shape"])
        self.assertEqual(
            {row[0]: row[1] for row in collection[2:]},
            {
                "window scalars": "now:aware ISO timestamp canonicalized by the helper to a whole UTC minute; cadenceMinutes:positive integer; lastWindowEnd/latestWorldMemoryEnd:aware ISO timestamp or null and likewise minute-canonicalized; force:boolean",
                "window.sameWindowReports[]": "exact keys id,Report Type,Window Start,Window End,Created At; id:nonempty string; Report Type:briefing or world-memory; Window Start/End:aware ISO strings equal to the requested window; Created At:aware ISO string",
                "resolve-report-view": "exact keys now,cadenceMinutes,force,rows,hasMore; now:aware ISO timestamp canonicalized by the helper to a whole UTC minute; cadenceMinutes:positive integer; force/hasMore:boolean",
                "Reports view rows[]": "required keys url,Name,Report Type,date:Window Start:start,date:Window End:start,Created At; window dates are canonicalized to whole UTC minutes; optional known Report properties and date is_datetime markers only; Collection/Stories are JSON-array strings when present and may be omitted when empty",
                "normalize-story-view": "exact keys rows,hasMore; hasMore:boolean",
                "Stories view rows[]": "required keys url,Name,Status,Category,Regions,Importance,Confidence,Current View,date:First Seen:start,date:Last Evidence At:start,date:Last Updated:start,Created At; Regions is a JSON-array string; optional Related Stories is a JSON-array string; date is_datetime markers may be present",
                "collect-feeds": "windowStart/windowEnd:aware ISO timestamps with start before end; timeoutSeconds:positive number; the command captures fetchedAt and requires windowEnd not to be in its future",
                "normalize-feed": "feedId:one configured ID; csv:string with the exact RSS.app header listed below",
                "validate-llm-plan candidate": "exact keys report,storyDecisions,evidenceClusters",
                "candidate.report": "exact keys type,stance,confidence,dataQuality,dataGaps,markdown; dataGaps:list of strings; markdown:string with the ordered Report headings",
                "candidate.storyDecisions[]": "exact keys action,storyLocator,name,status,category,regions,changeType,direction,importance,confidence,currentView,storyMarkdown,changeMarkdown,relatedStoryLocators,evidenceItemIds; locator fields use canonical lower-case dashed Story UUIDs",
                "candidate.evidenceClusters[]": "exact keys clusterId,importance,evidenceItemIds,reportSections,storyLocators; importance:high, medium, or low; every member is a nonempty string and locator/evidence members use supplied bindings",
                "validation bindings": "knownStoryIds:list of canonical lower-case dashed Story UUIDs; evidenceItemIds:list of nonempty strings; expectedReportType:briefing or world-memory",
            },
        )

        market = _table_after(
            _read(REFERENCE_PATHS["market-data"]),
            "## Structured CLI input shapes",
        )
        self.assertEqual(market[0], ["Value", "Closed shape"])
        self.assertEqual(
            {row[0]: row[1] for row in market[2:]},
            {
                "market-data-plan": "exact keys registry,toolAccess; registry is the validated notion-native-v2 object and toolAccess is the current response",
                "market-data-plan.toolAccess": "exact boolean keys alpacaMarketData,alpacaOptions,alpacaCalendar,wolframLanguage,wolframAlpha; each value reflects current tool access rather than remembered availability",
                "market-data-plan.attempts[]": "exact keys provider,requiredToolAccess,invocation; invocation has exact keys kind,tool,action,method,endpointTemplate,requestArguments,evidenceFormat,rawQueryPersistence,sourceLocatorPersistence and is directly executable without inferring an operation from provider",
                "validate-market-observation": "exact keys request,candidate,evidence,normalizationAttempt; normalizationAttempt is 1 or 2",
                "request": "one of the six exact capability shapes below; cutoff is aware; current price also has maximumAgeSeconds; date windows satisfy startDate<=endDate<=cutoff; instruments use exact keys symbol,currency,region,assetClass",
                "candidate common": "exact keys schemaVersion,capability,provider,sourceLocator,fetchedAt,completeness,evidenceBindings plus only the capability fields below; provider is a closed plan provider; schemaVersion is 1.0; completeness is complete or partial",
                "sourceLocator": "either exact keys kind,url with kind=url and evidence-bound provider-host URL without credentials, key/token/credential/signature/access-key/security-token query keys including signed vendor prefixes, or fragment; or exact keys kind,tool,queryDescriptor with kind=provider-query and matching Wolfram provider",
                "evidenceBindings[]": "structured evidence uses exact keys field,evidenceId,evidencePath with the same exact scalar field path; text evidence uses exact keys field,evidenceId,textSpan,excerpt with an exact field-level source span",
                "evidence[]": "exact keys evidenceId,format,content; format is structured or text; content is the corresponding tool result bound only to that evidenceId",
                "collect-market-data": "exact keys plan,outcomes; plan is the unchanged current market-data-plan response and outcomes is a nonempty list of complete planned chains",
                "collect-market-data.outcomes[]": "exact keys capability,request,stableKey,attempts; capability is validatorSupported and in plan and may repeat only for a distinct request and stableKey; request maps to validatorCapability; attempts cover every planned provider once in order; any economic outcomes cover exactly the five scheduledSeriesIds",
                "collect-market-data.attempts[]": "exact keys provider,status,values,error,stage,validationEnvelope; complete forces every later row to not-attempted; partial or error permits the next attempt; ok or partial contains exactly one normalized observation at stableKey and the original accepted validation envelope; error or not-attempted uses validationEnvelope null",
                "values.<stableKey>": "atomic capabilities use one complete fallback observation instead of mixing a partial; VIX uses missing-only components with provider,sourceLocator,date,fetchedAt provenance per component; never a scalar or flattened pseudo-curve",
            },
        )

    def test_generated_schedule_builds_a_real_current_access_plan_request(self) -> None:
        """Catch a rendered JSON template that cannot cross the Task 1 boundary."""

        prompt = render_scheduled_prompt(Registry.from_mapping(REGISTRY))
        marker = "<market_data_plan_request_template>\n"
        self.assertIn(marker, prompt)
        self.assertNotIn("{registry:<", prompt)
        self.assertIn(
            "replace each null in toolAccess with the corresponding current observed boolean. Do not change any other key or value",
            prompt,
        )
        template = json.loads(
            prompt.split(marker, 1)[1].split(
                "\n</market_data_plan_request_template>", 1
            )[0]
        )
        self.assertEqual(set(template), {"registry", "toolAccess"})
        self.assertEqual(template["registry"], REGISTRY)
        self.assertEqual(
            template["toolAccess"],
            {
                "alpacaMarketData": None,
                "alpacaOptions": None,
                "alpacaCalendar": None,
                "wolframLanguage": None,
                "wolframAlpha": None,
            },
        )
        observed_access = {
            "alpacaMarketData": True,
            "alpacaOptions": False,
            "alpacaCalendar": True,
            "wolframLanguage": True,
            "wolframAlpha": False,
        }
        for key, value in observed_access.items():
            template["toolAccess"][key] = value

        completed = run_cli("market-data-plan", "-", stdin=json.dumps(template))

        self.assertEqual(completed.returncode, 0, completed.stderr)
        plan = json.loads(completed.stdout)
        self.assertEqual(
            plan["capabilities"]["credit-risk-pair"]["providers"][:3],
            ["alpaca", "wolfram-language", "existing-credit-risk"],
        )
        self.assertTrue(
            plan["capabilities"]["credit-risk-pair"]["shortCircuitOnComplete"]
        )

    def test_documented_nested_validator_shapes_are_closed(self) -> None:
        """Catch nested documentation that cannot define a Task 2 candidate."""

        table = _table_after(
            _read(REFERENCE_PATHS["market-data"]),
            "## Nested validator shapes",
        )
        self.assertEqual(table[0], ["Value", "Exact closed shape and constraint"])
        self.assertEqual(
            {row[0]: row[1] for row in table[2:]},
            {
                "common candidate": "schemaVersion=1.0; capability equals request; provider is in the closed plan enum; sourceLocator as below; fetchedAt aware and not after cutoff; completeness complete or partial; evidenceBindings list; plus exactly one capability field set",
                "URL sourceLocator": "exact keys kind,url; kind=url; provider-host HTTP(S) URL without userinfo, secret query key, or fragment; exact URL occurs in supplied evidence",
                "provider-query sourceLocator": "exact keys kind,tool,queryDescriptor; kind=provider-query; tool Wolfram Language maps to provider wolfram-language or Wolfram Alpha maps to wolfram-alpha; descriptor exactly matches one deterministic format below",
                "evidence[]": "nonempty list of exact keys evidenceId,format,content; evidenceId nonempty and unique; structured content is object or list; text content is string",
                "evidenceBindings[]": "every non-null capability scalar plus fetchedAt has exactly one binding; structured rows use field,evidenceId,evidencePath with identical field/path and exact typed value; text rows use field,evidenceId,textSpan,excerpt whose exact source slice contains that field value and any maturity,component,or OHLC label; only currency fields treat USD,USDT,USDC as nominal 1:1 equivalents",
                "request instrument": "exact keys symbol,currency,region,assetClass; every value nonempty string",
                "candidate instrument": "exact keys symbol,currency,region,assetClass,exchange; requested symbol,currency,region,assetClass match exactly and USD remains the canonical output currency when source evidence says USDT or USDC; every value nonempty string",
                "current price": "positive finite price; closed provider-specific valueBasis,marketScope,session; observedAt aware, not after cutoff, and within maximumAgeSeconds, or null only when completeness=partial",
                "daily bars": "closed provider-specific valueBasis,marketScope,session; nonempty date-ascending rows inside startDate/endDate; positive finite OHLC; low <= open and close <= high; integer volume >= 0",
                "bar row": "exact keys date,open,high,low,close,volume",
                "pair series": "exactly two ordered members matching requested instruments; closed common currency,valueBasis,marketScope,session; both date sets are identical after caller intersection and contain at least minimumCommonDays",
                "pair member": "exact keys instrument,rows; rows nonempty and date-ascending",
                "pair row": "exact keys date,value; value positive finite; date inside startDate/endDate and not after cutoff",
                "Treasury maturities": "nonempty subset of 3M,1Y,2Y,5Y,10Y,30Y with finite values; complete requires 2Y,5Y,10Y,30Y; country US; unit percent; valueBasis us-treasury-yield-curve-rate; date equals request and is not future",
                "economic observations": "list length at least minimumHistory; exact seriesId or exact semanticIdentity; frequency and unit equal request; rows date-ascending inside startDate/endDate and not future",
                "economic observation": "exact keys date,value; value finite",
                "VIX components": "nonempty subset of VIX9D,VIX,VIX3M,VIX6M with positive finite values; complete requires all four; unit index-points; date equals request and is not future",
            },
        )

    def test_documented_representative_validator_fixtures_execute(self) -> None:
        """Catch representative documented candidates rejected by the real validator."""

        market = _read(REFERENCE_PATHS["market-data"])
        cases = (
            ("### Current price validator fixture", "equity-current-price"),
            ("### Daily bars validator fixture", "equity-daily-bars"),
            ("### Treasury validator fixture", "treasury-yield-curve"),
            ("### Economic series validator fixture", "economic-time-series"),
        )
        for heading, capability in cases:
            with self.subTest(capability=capability):
                fixture = _json_block_after(market, heading)
                self.assertEqual(fixture["request"]["capability"], capability)
                completed = run_cli(
                    "validate-market-observation", "-", stdin=json.dumps(fixture)
                )
                self.assertEqual(completed.returncode, 0, completed.stderr)
                response = json.loads(completed.stdout)
                self.assertEqual(response["status"], "accepted")
                self.assertEqual(response["observation"]["capability"], capability)

    def test_documented_partial_observation_survives_real_validator_and_collector(self) -> None:
        """Catch partial-to-error or normalized-observation-to-scalar projection."""

        fixture = _json_block_after(
            _read(REFERENCE_PATHS["market-data"]),
            "### Partial validator fixture",
        )
        validated = run_cli(
            "validate-market-observation", "-", stdin=json.dumps(fixture)
        )
        self.assertEqual(validated.returncode, 0, validated.stderr)
        response = json.loads(validated.stdout)
        self.assertEqual(response["status"], "accepted")
        observation = response["observation"]
        self.assertEqual(observation["completeness"], "partial")

        plan = json.loads(
            run_cli(
                "market-data-plan",
                "-",
                stdin=json.dumps(
                    {"registry": REGISTRY, "toolAccess": MARKET_TOOL_ACCESS}
                ),
            ).stdout
        )
        stable_key = "VIX.term-structure"
        attempts = []
        for index, provider in enumerate(
            plan["capabilities"]["volatility-term-structure"]["providers"]
        ):
            if index == 0:
                attempts.append(
                    {
                        "provider": provider,
                        "status": "partial",
                        "values": {stable_key: observation},
                        "error": "market_provider_partial",
                        "stage": "",
                        "validationEnvelope": fixture,
                    }
                )
            else:
                attempts.append(
                    {
                        "provider": provider,
                        "status": "error",
                        "values": {},
                        "error": "provider-no-result",
                        "stage": "fetch",
                        "validationEnvelope": None,
                    }
                )
        collected = run_cli(
            "collect-market-data",
            "-",
            stdin=json.dumps(
                {
                    "plan": plan,
                    "outcomes": [
                        {
                            "capability": "volatility-term-structure",
                            "request": fixture["request"],
                            "stableKey": stable_key,
                            "attempts": attempts,
                        }
                    ],
                }
            ),
        )

        self.assertEqual(collected.returncode, 0, collected.stderr)
        snapshot = json.loads(collected.stdout)
        self.assertEqual(snapshot["status"], "partial")
        self.assertEqual(
            snapshot["values"]["VIX.term-structure"]["components"]["VIX"]["level"],
            observation["components"]["VIX"],
        )
        self.assertEqual(
            snapshot["gaps"][0],
            "volatility-term-structure/wolfram-language: market_provider_partial",
        )

    def test_documented_pair_requests_cross_the_real_validator_without_fill(self) -> None:
        """Catch wrong pair identities, minima, descriptors, or fabricated dates."""

        requests = _json_block_after(
            _read(REFERENCE_PATHS["market-data"]),
            "### Scheduled pair request fixtures",
        )
        cases = (
            ("credit-risk-pair", ("HYG", "LQD"), 6),
            ("market-breadth-pair", ("RSP", "SPY"), 21),
        )
        observed_trading_dates = (
            "2026-07-17",
            "2026-07-20",
            "2026-07-21",
            "2026-07-22",
            "2026-07-23",
            "2026-07-24",
            "2026-07-27",
            "2026-07-28",
            "2026-07-29",
            "2026-07-30",
            "2026-07-31",
            "2026-08-03",
            "2026-08-04",
            "2026-08-05",
            "2026-08-06",
            "2026-08-07",
            "2026-08-10",
            "2026-08-11",
            "2026-08-12",
            "2026-08-13",
            "2026-08-14",
        )
        for task1_name, symbols, minimum in cases:
            with self.subTest(task1_name=task1_name):
                request = requests[task1_name]
                self.assertEqual(request["capability"], "equity-pair-series")
                self.assertEqual(
                    tuple(item["symbol"] for item in request["instruments"]),
                    symbols,
                )
                self.assertEqual(request["minimumCommonDays"], minimum)
                dates = observed_trading_dates[-minimum:]
                series = []
                evidence_series = []
                bindings = []
                for index, instrument in enumerate(request["instruments"]):
                    rows = [
                        {"date": date, "value": 80.0 + index * 20 + row_index}
                        for row_index, date in enumerate(dates)
                    ]
                    series.append(
                        {
                            "instrument": {**instrument, "exchange": "NYSE Arca"},
                            "rows": rows,
                        }
                    )
                    evidence_series.append({"rows": rows})
                    bindings.append(
                        {"field": f"series.{index}.rows", "evidenceId": "ev-pair"}
                    )
                descriptor = (
                    f"equity-pair-series:{','.join(symbols)}:"
                    f"{request['startDate']}:{request['endDate']}"
                )
                payload = {
                    "request": request,
                    "candidate": {
                        "schemaVersion": "1.0",
                        "capability": "equity-pair-series",
                        "provider": "wolfram-language",
                        "sourceLocator": {
                            "kind": "provider-query",
                            "tool": "Wolfram Language",
                            "queryDescriptor": descriptor,
                        },
                        "fetchedAt": "2026-08-16T11:45:00Z",
                        "completeness": "complete",
                        "evidenceBindings": bindings,
                        "currency": "USD",
                        "valueBasis": "wolfram-daily-close",
                        "marketScope": "provider-market",
                        "session": "regular",
                        "series": series,
                    },
                    "evidence": [
                        {
                            "evidenceId": "ev-pair",
                            "format": "structured",
                            "content": {"series": evidence_series},
                        }
                    ],
                    "normalizationAttempt": 1,
                }
                _bind_structured_payload(payload, "ev-pair")
                completed = run_cli(
                    "validate-market-observation", "-", stdin=json.dumps(payload)
                )
                self.assertEqual(completed.returncode, 0, completed.stderr)
                self.assertEqual(json.loads(completed.stdout)["status"], "accepted")

    def test_market_reference_documents_executable_validation_boundaries(self) -> None:
        """Catch docs that leave provider selection or evidence repair ambiguous."""

        market = _read(REFERENCE_PATHS["market-data"])
        collection = _read(REFERENCE_PATHS["collection-and-analysis"])
        skill = _read(SKILL_PATH)

        for required in (
            "IEX versus SIP",
            "Wolfram `Last` degradation",
            "Treasury value-basis",
            "entity validation",
            "evidence binding",
            "query descriptor",
            "No Results Found",
            "graph-only",
            "at most one validation-guided repair",
            "fetch only missing fields or components",
            "do not mix providers, currencies, or value bases",
            "temporary plugin inputs",
        ):
            with self.subTest(required=required):
                self.assertTrue(
                    required in market or required in collection or required in skill,
                    required,
                )

        deployment = _table_after(
            _read(REFERENCE_PATHS["deployment"]),
            "## Structured CLI input shapes",
        )
        self.assertEqual(deployment[0], ["Value", "Closed shape"])
        self.assertEqual(
            {row[0]: row[1] for row in deployment[2:]},
            {
                "bootstrap-plan.workspaceId": "UUID string",
                "resolve-registry-discovery": "exact keys workspaceId,candidates; candidates is the bounded result of one exact-title Notion search plus exact candidate fetches",
                "candidates[]": "exact keys pageId,url,title,marker,workspaceRoot,installation; installation is null for a non-v2 candidate or has exact keys databases,views for a v2 candidate",
                "installation.databases": "exact keys collections,stories,storyChanges,reports; each has title,databaseUrl,parentPageId,dataSourceId,properties",
                "installation.views": "exact keys reportsRecent,storiesCurrent; each has name,databaseUrl,viewId,dataSourceId,displayProperties,sorts",
                "render-scheduled-prompt": "the exact Canonical registry object in notion-layout.md",
                "verify-live.registry/workspaceId": "the exact Canonical registry plus the same workspace UUID",
                "verify-live.toolAccess": "exact boolean keys fetchSelf,queryDataSources,fetchPages,createPages,updatePages; all true",
                "verify-live.schemaProjections": "exact keys collections,stories,storyChanges,reports; each value has exact keys dataSourceId,properties",
                "schemaProjections.<key>.properties": "exact property-name to property-type string mapping from notion-layout.md",
                "verify-live.viewProjections": "exact keys reportsRecent,storiesCurrent; each value has exact keys url,dataSourceId,configuration and must match registry plus the saved-view contract",
            },
        )

        notion_layout = _table_after(
            _read(REFERENCE_PATHS["notion-layout"]),
            "## Structured CLI input shapes",
        )
        self.assertEqual(notion_layout[0], ["Value", "Closed shape"])
        self.assertEqual(
            {row[0]: row[1] for row in notion_layout[2:]},
            {
                "validate-registry": "the exact Canonical registry object above; every ID is a UUID string; hub has pageId,url; each data source has only dataSourceId; each view has only url with exactly one database UUID path locator and one v UUID query parameter",
            },
        )

    def test_public_cli_failure_and_one_repair_contract_are_not_contradictory(self) -> None:
        collection = _read(REFERENCE_PATHS["collection-and-analysis"])
        skill = _read(SKILL_PATH)
        self.assertIn(
            "returns only the value-free `invalid-input` stderr category",
            collection,
        )
        self.assertIn(
            "one contract-guided regeneration against the exact shapes and enums above",
            collection,
        )
        self.assertNotIn("return validation errors", collection)
        self.assertIn("contract-guided repair", skill)

        invalid = {
            "candidate": CLUSTERED_PLAN,
            "knownStoryIds": ["story-001"],
            "evidenceItemIds": [],
            "expectedReportType": "world-memory",
        }
        completed = run_cli(
            "validate-llm-plan", "-", stdin=json.dumps(invalid)
        )
        self.assertEqual(completed.returncode, 2)
        self.assertEqual(completed.stdout, "")
        self.assertEqual(completed.stderr, "invalid-input\n")

    def test_layout_names_exactly_the_four_runtime_data_sources(self) -> None:
        table = _table_after(_read(REFERENCE_PATHS["notion-layout"]), "## Data sources")
        self.assertEqual(table[0], ["Registry key", "Data source title"])
        documented = {row[0]: row[1] for row in table[2:]}
        self.assertEqual(
            documented,
            {key: schema["title"] for key, schema in DATABASE_SCHEMAS.items()},
        )

    def test_layout_document_matches_every_runtime_schema_descriptor(self) -> None:
        text = _read(REFERENCE_PATHS["notion-layout"])
        self.assertIn(HUB_MARKER, text)
        for key, schema in DATABASE_SCHEMAS.items():
            documented = _parse_schema_table(text, key)
            expected = {
                name: _documented_schema(descriptor, name)
                for name, descriptor in schema["properties"].items()
            }
            self.assertEqual(documented, expected, key)

    def test_layout_registry_is_an_address_book_with_exact_shape(self) -> None:
        text = _read(REFERENCE_PATHS["notion-layout"])
        block = re.search(
            r"## Canonical registry\n.*?```json\n(?P<body>.*?)\n```",
            text,
            flags=re.DOTALL,
        )
        self.assertIsNotNone(block)
        registry = json.loads(block.group("body"))
        self.assertEqual(
            tuple(registry),
            ("schemaVersion", "workspaceId", "hub", "collections", "stories", "storyChanges", "reports", "views", "marketSources"),
        )
        self.assertEqual(registry["schemaVersion"], "notion-native-v2")
        self.assertEqual(set(registry["hub"]), {"pageId", "url"})
        self.assertEqual(
            registry["hub"]["url"],
            "https://www.notion.so/World-Memory-<hub-page-id-without-hyphens>",
        )
        for key in ("collections", "stories", "storyChanges", "reports"):
            self.assertEqual(set(registry[key]), {"dataSourceId"})
        self.assertEqual(set(registry["views"]), {"reportsRecent", "storiesCurrent"})
        for locator in registry["views"].values():
            self.assertEqual(set(locator), {"url"})
        self.assertEqual(
            registry["marketSources"],
            {
                "vixSpreadsheet": {
                    "publicCsvUrl": VIX_PUBLIC_CSV_URL,
                    "expectedSymbols": VIX_SYMBOLS,
                }
            },
        )

        canonical_section = text.split("## Data sources", 1)[0]
        self.assertNotIn("databaseId", block.group("body"))
        self.assertNotRegex(
            canonical_section,
            r'"(?:collections|stories|storyChanges|reports)"\s*:\s*\{[^}]*"url"',
        )

    def test_runtime_locator_contract_matches_notion_database_container_model(self) -> None:
        layout = _read(REFERENCE_PATHS["notion-layout"])
        deployment = _read(REFERENCE_PATHS["deployment"])
        skill = _read(SKILL_PATH)
        readme = _read(WORKTREE / "README.md")

        for required in (
            "database container ID and data_source_id are different identifiers",
            "database URL contains the database container ID",
            "data source locator stores only dataSourceId",
        ):
            with self.subTest(required=required):
                self.assertIn(required, layout)
        self.assertIn(
            "four database containers, each with one initial data source",
            deployment,
        )
        self.assertIn(
            "Resolve only each initial data source's dataSourceId",
            deployment,
        )
        self.assertIn("Data-source locators contain only dataSourceId", skill)
        self.assertIn(
            "four database containers, each with an initial data source",
            readme,
        )

    def test_documented_feed_table_matches_runtime_order_and_offsets(self) -> None:
        table = _table_after(
            _read(REFERENCE_PATHS["collection-and-analysis"]),
            "## Configured feeds",
        )
        self.assertEqual(table[0], ["ID", "Name", "URL", "Offset minutes"])
        rows = tuple((row[0], row[1], row[2], int(row[3])) for row in table[2:])
        self.assertEqual(
            rows,
            tuple((feed.id, feed.name, feed.url, feed.published_at_offset_minutes) for feed in FEEDS),
        )

    def test_each_runtime_command_has_one_reference_owner_and_exact_input_keys(self) -> None:
        rows = _documented_cli_rows()
        help_result = run_cli("--help")
        self.assertEqual(help_result.returncode, 0, help_result.stderr)
        command_group = re.search(r"\{([^}]+)\}", help_result.stdout)
        self.assertIsNotNone(command_group)
        self.assertEqual(set(rows), set(command_group.group(1).split(",")))
        self.assertEqual(
            rows,
            {
                "validate-registry": (
                    "notion-layout",
                    "schemaVersion,workspaceId,hub,collections,stories,storyChanges,reports,views,marketSources",
                    "validated normalized registry address book",
                ),
                "schema": (
                    "notion-layout",
                    "(none)",
                    "independent logical schema manifest",
                ),
                "window": (
                    "collection-and-analysis",
                    "now,cadenceMinutes,lastWindowEnd,sameWindowReports,latestWorldMemoryEnd,force",
                    "UTC window, same-window disposition, and report type",
                ),
                "resolve-report-view": (
                    "collection-and-analysis",
                    "now,cadenceMinutes,force,rows,hasMore",
                    "view-backed UTC window, reuse disposition, and report type",
                ),
                "normalize-story-view": (
                    "collection-and-analysis",
                    "rows,hasMore",
                    "validated complete current Story projections",
                ),
                "collect-feeds": (
                    "collection-and-analysis",
                    "windowStart,windowEnd,timeoutSeconds",
                    "fixed-source direct HTTP collection, normalized half-open window filtering, deduplication, and per-source diagnostics",
                ),
                "normalize-feed": (
                    "collection-and-analysis",
                    "feedId,csv",
                    "normalized configured-feed outcome",
                ),
                "validate-llm-plan": (
                    "collection-and-analysis",
                    "candidate,knownStoryIds,evidenceItemIds,expectedReportType",
                    "validated temporary plan",
                ),
                "market-data-plan": (
                    "market-data",
                    "registry,toolAccess",
                    "capability-specific provider collection plan",
                ),
                "validate-market-observation": (
                    "market-data",
                    "request,candidate,evidence,normalizationAttempt",
                    "validated evidence-bound market observation",
                ),
                "collect-market-data": (
                    "market-data",
                    "plan,outcomes",
                    "validated planned-provider snapshot",
                ),
                "bootstrap-plan": (
                    "deployment",
                    "workspaceId",
                    "finite fresh-install action plan",
                ),
                "resolve-registry-discovery": (
                    "deployment",
                    "workspaceId,candidates",
                    "bounded read-only registry recovery result",
                ),
                "render-scheduled-prompt": (
                    "deployment",
                    "schemaVersion,workspaceId,hub,collections,stories,storyChanges,reports,views,marketSources",
                    "self-contained scheduled prompt",
                ),
                "verify-live": (
                    "deployment",
                    "registry,workspaceId,toolAccess,schemaProjections,viewProjections",
                    "validation of supplied canary evidence",
                ),
            },
        )

    def test_every_documented_command_executes_as_one_compact_json_subprocess(self) -> None:
        csv_payload = (PACKAGE / "tests" / "fixtures" / "rss-app-sample.csv").read_text(
            encoding="utf-8"
        )
        fixtures: dict[str, dict[str, object]] = {
            "validate-registry": REGISTRY,
            "schema": {},
            "bootstrap-plan": {"workspaceId": WORKSPACE_ID},
            "resolve-registry-discovery": registry_discovery_input(),
            "window": {
                "now": "2026-08-14T03:00:00Z",
                "cadenceMinutes": 180,
                "lastWindowEnd": None,
                "sameWindowReports": [],
                "latestWorldMemoryEnd": None,
                "force": False,
            },
            "resolve-report-view": {
                "now": "2026-08-14T03:00:00Z",
                "cadenceMinutes": 180,
                "force": False,
                "rows": [],
                "hasMore": False,
            },
            "normalize-story-view": {"rows": [], "hasMore": False},
            "validate-llm-plan": {
                "candidate": CLUSTERED_PLAN,
                "knownStoryIds": [STORY_ID],
                "evidenceItemIds": ["item-1"],
                "expectedReportType": "world-memory",
            },
            "render-scheduled-prompt": REGISTRY,
            "normalize-feed": {"feedId": "first_squawk", "csv": csv_payload},
            "market-data-plan": {
                "registry": REGISTRY,
                "toolAccess": MARKET_TOOL_ACCESS,
            },
            "validate-market-observation": VALID_SPY_PAYLOAD,
            "collect-market-data": _valid_collect_market_data_input(),
            "verify-live": {
                "registry": REGISTRY,
                "workspaceId": WORKSPACE_ID,
                "toolAccess": TOOL_ACCESS,
                "schemaProjections": schema_projections(),
                "viewProjections": view_projections(),
            },
        }
        documented = _documented_cli_rows()
        self.assertEqual(set(documented) - {"collect-feeds"}, set(fixtures))
        for command, request in fixtures.items():
            with self.subTest(command=command):
                completed = run_cli(command, "-", stdin=json.dumps(request))
                self.assertEqual(completed.returncode, 0, completed.stderr)
                self.assertEqual(completed.stderr, "")
                self.assertEqual(completed.stdout.count("\n"), 1)
                output = json.loads(completed.stdout)
                self.assertIs(type(output), dict)
                self.assertEqual(
                    completed.stdout,
                    json.dumps(output, ensure_ascii=False, separators=(",", ":"))
                    + "\n",
                )

    def test_twelve_data_mapping_commands_execute_the_current_v2_contract(self) -> None:
        csv_payload = (PACKAGE / "tests" / "fixtures" / "rss-app-sample.csv").read_text(
            encoding="utf-8"
        )
        fixtures = {
            "validate-registry": REGISTRY,
            "resolve-registry-discovery": registry_discovery_input(),
            "window": {
                "now": "2026-08-14T03:00:00Z",
                "cadenceMinutes": 180,
                "lastWindowEnd": None,
                "sameWindowReports": [],
                "latestWorldMemoryEnd": None,
                "force": False,
            },
            "resolve-report-view": {
                "now": "2026-08-14T03:00:00Z",
                "cadenceMinutes": 180,
                "force": False,
                "rows": [],
                "hasMore": False,
            },
            "normalize-story-view": {"rows": [], "hasMore": False},
            "validate-llm-plan": {
                "candidate": CLUSTERED_PLAN,
                "knownStoryIds": [STORY_ID],
                "evidenceItemIds": ["item-1"],
                "expectedReportType": "world-memory",
            },
            "render-scheduled-prompt": REGISTRY,
            "normalize-feed": {"feedId": "first_squawk", "csv": csv_payload},
            "market-data-plan": {
                "registry": REGISTRY,
                "toolAccess": MARKET_TOOL_ACCESS,
            },
            "validate-market-observation": VALID_SPY_PAYLOAD,
            "collect-market-data": _valid_collect_market_data_input(),
            "verify-live": {
                "registry": REGISTRY,
                "workspaceId": WORKSPACE_ID,
                "toolAccess": TOOL_ACCESS,
                "schemaProjections": schema_projections(),
                "viewProjections": view_projections(),
            },
        }
        self.assertEqual(len(fixtures), 12)
        for command, request in fixtures.items():
            with self.subTest(command=command):
                completed = run_cli(command, "-", stdin=json.dumps(request))
                self.assertEqual(completed.returncode, 0, completed.stderr)
                output = json.loads(completed.stdout)
                self.assertIs(type(output), dict)

    def test_installed_v2_contract_routes_source_html_headings_clusters_and_link_first(self) -> None:
        layout = _read(REFERENCE_PATHS["notion-layout"])
        market = _read(REFERENCE_PATHS["market-data"])
        collection = _read(REFERENCE_PATHS["collection-and-analysis"])
        prompt = render_scheduled_prompt(Registry.from_mapping(REGISTRY))
        for text in (layout, market):
            self.assertIn(VIX_PUBLIC_CSV_URL, text)
            for symbol in VIX_SYMBOLS:
                self.assertIn(symbol, text)
        embedded = json.loads(
            prompt.split("<world_memory_registry>\n", 1)[1].split(
                "\n</world_memory_registry>", 1
            )[0]
        )
        self.assertEqual(
            embedded["marketSources"]["vixSpreadsheet"],
            {
                "publicCsvUrl": VIX_PUBLIC_CSV_URL,
                "expectedSymbols": VIX_SYMBOLS,
            },
        )
        for blocked in ("script", "style", "iframe", "embed", "object"):
            self.assertIn(f"`{blocked}`", collection)
            self.assertIn(blocked, prompt)
        for heading in (
            "## Key Takeaway",
            "## 시장 현황",
            "## 중장기 맥락",
            "## 주요 지표들",
            "## 지켜봐야 할 것들",
            "## 관심을 가져볼 만한 이슈들",
            "## 출처·데이터 안내",
        ):
            self.assertIn(f"`{heading}`", collection)
            self.assertIn(heading, prompt)
        for field in (
            "clusterId",
            "importance",
            "evidenceItemIds",
            "reportSections",
            "storyLocators",
        ):
            self.assertIn(field, collection)
            self.assertIn(field, prompt)
        for truth_rule in (
            "ok, partial, error, or not-attempted",
            "stage=fetch or stage=parse",
            "not-attempted creates no gap",
        ):
            self.assertIn(truth_rule, prompt)
        for section_id in (
            "key-takeaway",
            "market-status",
            "medium-term-context",
            "key-indicators",
            "watch-items",
            "issues-of-interest",
            "sources-and-data",
        ):
            self.assertIn(section_id, prompt)
        self.assertIn("return only that link", prompt)

    def test_reference_and_prompt_share_report_depth_without_an_llm_judge(self) -> None:
        collection = _read(REFERENCE_PATHS["collection-and-analysis"])
        prompt = render_scheduled_prompt(Registry.from_mapping(REGISTRY))
        required = (
            "Key Takeaway uses 3-5 unordered bullets",
            "briefing uses at least 2 prose paragraphs in each narrative section",
            "world-memory uses at least 3 prose paragraphs in each narrative section",
            "Do not call a separate LLM quality reviewer",
        )

        for text in (collection, prompt):
            for rule in required:
                with self.subTest(surface="reference" if text is collection else "prompt", rule=rule):
                    self.assertIn(rule, text)

    def test_deployment_documents_read_only_canaries_and_v011x_pause_regenerate_resume(self) -> None:
        deployment = _read(REFERENCE_PATHS["deployment"])
        readme = _read(WORKTREE / "README.md")
        for text in (deployment, readme):
            for required in (
                "v0.11.x",
                "pause",
                "notion-native-v2",
                "regenerate",
                "Reports Recent",
                "Stories Current",
                "public CSV",
                "read-only",
                "resume",
            ):
                self.assertIn(required, text)
        plan = build_bootstrap_plan(WORKSPACE_ID)
        canary = plan["actions"][9]
        self.assertEqual(canary["action"], "verify-read-only-vix-spreadsheet-source")
        self.assertEqual(canary["method"], "GET")
        self.assertFalse(canary["mutationAllowed"])
        self.assertEqual(canary["publicCsvUrl"], VIX_PUBLIC_CSV_URL)
        self.assertEqual(canary["expectedSymbols"], VIX_SYMBOLS)

    def test_installable_prose_does_not_restore_persistent_control_machinery(self) -> None:
        prose = "\n".join(
            _read(path) for path in (SKILL_PATH, *REFERENCE_PATHS.values())
        ).lower()
        for forbidden in (
            "transaction protocol",
            "run ledger",
            "persistent control json",
            "second audit store",
            "hash authority",
            "commit protocol",
        ):
            self.assertNotIn(forbidden, prose)

    def test_story_payload_routing_uses_real_public_helpers_not_fictional_commands(self) -> None:
        text = _read(REFERENCE_PATHS["collection-and-analysis"])
        for helper in (
            "collection_page",
            "report_page",
            "story_page",
            "story_update",
            "story_change_page",
        ):
            self.assertIn(f"`{helper}`", text)
        self.assertNotIn("story-create", _documented_cli_rows())
        self.assertNotIn("story-update", _documented_cli_rows())


class RuntimeBehaviorAgreementTests(unittest.TestCase):
    def test_duplicate_selection_contract_matches_runtime_total_order(self) -> None:
        skill_contract = _contract_rows(_read(SKILL_PATH))["same-window-reuse"]
        self.assertEqual(
            skill_contract,
            "The validated Reports Recent view is the sole normal authority. Every row must have a nonempty id, valid Report Type, exact window, and aware Created At; invalid input safe-stops. Reuse greatest Created At, then lexicographically smallest id on a tie; type has no priority.",
        )
        window = Window(
            datetime.fromisoformat("2026-08-14T00:00:00+00:00"),
            datetime.fromisoformat("2026-08-14T03:00:00+00:00"),
        )
        older = {
            "id": "report-z",
            "Report Type": "briefing",
            "Window Start": "2026-08-14T00:00:00Z",
            "Window End": "2026-08-14T03:00:00Z",
            "Created At": "2026-08-14T03:01:00Z",
        }
        tied_high = {
            **older,
            "id": "report-b",
            "Report Type": "briefing",
            "Created At": "2026-08-14T03:02:00Z",
        }
        tied_low = {
            **older,
            "id": "report-a",
            "Report Type": "world-memory",
            "Created At": "2026-08-14T03:02:00Z",
        }
        decision = resolve_same_window([older, tied_high, tied_low], window)
        self.assertIs(decision.reused, tied_low)
        cli_request = {
            "now": "2026-08-14T03:00:00Z",
            "cadenceMinutes": 180,
            "lastWindowEnd": None,
            "sameWindowReports": [older, tied_high, tied_low],
            "latestWorldMemoryEnd": None,
            "force": False,
        }
        completed = run_cli("window", "-", stdin=json.dumps(cli_request))
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(json.loads(completed.stdout)["sameWindow"]["reused"], tied_low)

    def test_unconfirmed_report_contract_blocks_story_and_change_writes(self) -> None:
        rows = _contract_rows(_read(SKILL_PATH))
        self.assertIn("report-confirmed-before-story", rows)
        self.assertEqual(
            rows["report-confirmed-before-story"],
            "Only a confirmed Report permits Story or Story Change mutations; otherwise skip both, return generated Report text, and expose failed or uncertain storage.",
        )
        prompt = render_scheduled_prompt(Registry.from_mapping(REGISTRY))
        self.assertIn(
            "Only a confirmed Report permits Story or Story Change writes",
            prompt,
        )
        self.assertIn(
            "If Report confirmation fails or remains uncertain, skip both phases",
            prompt,
        )

    def test_installed_link_first_contract_matches_the_runtime_result_matrix(self) -> None:
        report_id = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
        report_url = (
            "https://app.notion.com/p/World-Memory-" + report_id.replace("-", "")
        )
        report_markdown = "# Generated Report\n\nBody must have one delivery owner."
        all_ok = tuple(
            FeedOutcome(feed.id, feed.name, "ok", (), "", False) for feed in FEEDS
        )
        partial = all_ok[:-1] + (
            FeedOutcome(
                FEEDS[-1].id,
                FEEDS[-1].name,
                "error",
                (),
                "feed_fetch_error",
                True,
            ),
        )
        all_failed = tuple(
            FeedOutcome(
                feed.id, feed.name, "error", (), "feed_fetch_error", True
            )
            for feed in FEEDS
        )
        market = MarketSnapshot("unavailable", (), {}, ())
        cases = (
            (
                "confirmed-new-url",
                report_markdown,
                WriteOutcome("report", "confirmed", report_url, ""),
                all_ok,
                ("", report_url),
            ),
            (
                "reused-url",
                report_markdown,
                WriteOutcome("reused", "confirmed", report_url, ""),
                (),
                ("", report_url),
            ),
            (
                "degraded-confirmed-url",
                report_markdown,
                WriteOutcome("report", "confirmed", report_url, ""),
                partial,
                ("", report_url),
            ),
            (
                "confirmed-uuid-only",
                report_markdown,
                WriteOutcome("report", "confirmed", report_id, ""),
                all_ok,
                (report_markdown, ""),
            ),
            (
                "failed",
                report_markdown,
                WriteOutcome("report", "failed", "", "report write failed"),
                partial,
                (report_markdown, ""),
            ),
            (
                "uncertain",
                report_markdown,
                WriteOutcome(
                    "report", "verify-once", report_url, "report write is uncertain"
                ),
                partial,
                (report_markdown, ""),
            ),
            (
                "safe-stop",
                "",
                WriteOutcome("safe-stop", "failed", "", "all feeds failed"),
                all_failed,
                ("", ""),
            ),
        )

        for name, markdown, outcome, feeds, expected_pair in cases:
            with self.subTest(runtime_case=name):
                result = build_user_result(
                    report_markdown=markdown,
                    report_outcome=outcome,
                    feed_outcomes=feeds,
                    market=market,
                )
                self.assertEqual(
                    (result["reportMarkdown"], result["reportUrl"]),
                    expected_pair,
                )

        expected_contract = (
            "After confirmed creation or reuse with a displayable first-party "
            "Notion URL, return that link without repeating the Report body. "
            "Failed, uncertain, or confirmed URL-less delivery returns the "
            "generated Report text; a pre-Report safe stop returns neither."
        )
        with self.subTest(installed_surface="SKILL contract map"):
            self.assertEqual(
                _contract_rows(_read(SKILL_PATH)).get("link-first-result"),
                expected_contract,
            )

        prompt = render_scheduled_prompt(Registry.from_mapping(REGISTRY))
        for rule in (
            "For a confirmed new or reused Report with a displayable first-party Notion URL, return only that link and do not paste the Report body",
            "For a failed, uncertain, or confirmed URL-less Report, return the generated Report text instead; a pre-Report safe stop returns neither",
        ):
            with self.subTest(installed_surface="scheduled prompt", rule=rule):
                self.assertIn(rule, prompt)

    def test_reference_prompt_and_compute_window_agree_on_previous_end_and_first_lookback(self) -> None:
        reference = _read(REFERENCE_PATHS["collection-and-analysis"])
        table = _table_after(reference, "### Current window decision")
        self.assertEqual(table[0], ["Condition", "Window Start", "Window End"])
        self.assertEqual(
            table[2:],
            [
                [
                    "lastWindowEnd present",
                    "canonical whole UTC minute of lastWindowEnd",
                    "canonical whole UTC minute of now",
                ],
                [
                    "lastWindowEnd absent",
                    "canonical whole UTC minute of now minus actual cadenceMinutes",
                    "canonical whole UTC minute of now",
                ],
            ],
        )
        now = datetime.fromisoformat("2026-08-14T03:00:28.987654+00:00")
        previous = datetime.fromisoformat("2026-08-14T01:00:59.123456+00:00")
        canonical_now = datetime.fromisoformat("2026-08-14T03:00:00+00:00")
        canonical_previous = datetime.fromisoformat("2026-08-14T01:00:00+00:00")
        first = compute_window(now, cadence_minutes=60)
        continued = compute_window(now, cadence_minutes=60, last_window_end=previous)
        self.assertEqual(first.start, canonical_now - timedelta(minutes=60))
        self.assertEqual(first.end, canonical_now)
        self.assertEqual(continued.start, canonical_previous)
        self.assertEqual(continued.end, canonical_now)
        prompt = render_scheduled_prompt(Registry.from_mapping(REGISTRY))
        self.assertIn(
            "canonicalizes aware UTC now and Report window boundaries to whole UTC minutes before comparison, computation, or storage",
            prompt,
        )

    def test_reference_prompt_and_report_type_runtime_agree_at_345_minute_boundary(self) -> None:
        reference = _read(REFERENCE_PATHS["collection-and-analysis"])
        table = _table_after(reference, "### Report type decision")
        self.assertEqual(
            table[0],
            ["Invocation", "Latest world-memory Window End", "Force", "Report type"],
        )
        self.assertEqual(
            table[2:],
            [
                ["scheduled", "absent", "false", "world-memory"],
                ["scheduled", "age < 345 minutes", "false", "briefing"],
                ["scheduled", "age >= 345 minutes", "false", "world-memory"],
                ["explicit direct/manual", "present or absent", "true", "world-memory"],
            ],
        )
        now = datetime.fromisoformat("2026-08-14T06:00:00+00:00")
        cases = (
            (None, False, "world-memory"),
            (now - timedelta(minutes=344), False, "briefing"),
            (now - timedelta(minutes=345), False, "world-memory"),
            (now - timedelta(minutes=1), True, "world-memory"),
        )
        for latest, force, expected in cases:
            with self.subTest(latest=latest, force=force):
                self.assertEqual(choose_report_type(now, latest, force=force), expected)
        prompt = render_scheduled_prompt(Registry.from_mapping(REGISTRY))
        for rule in (
            "No latest world-memory Report means world-memory",
            "less than 345 minutes since its Window End means briefing",
            "exactly 345 minutes or more means world-memory",
            "Scheduled operation always passes force=false and must not choose force itself",
            "Only an explicit direct/manual user request may pass force=true",
        ):
            self.assertIn(rule, prompt)

    def test_same_window_report_is_reused_before_sources(self) -> None:
        window = Window(
            datetime.fromisoformat("2026-08-14T00:00:00+00:00"),
            datetime.fromisoformat("2026-08-14T03:00:00+00:00"),
        )
        row = {
            "id": "report-existing",
            "Report Type": "briefing",
            "Window Start": "2026-08-14T00:00:00Z",
            "Window End": "2026-08-14T03:00:00Z",
            "Created At": "2026-08-14T03:01:00Z",
        }
        self.assertIs(resolve_same_window([row], window).reused, row)

    def test_partial_feed_and_cboe_failure_preserve_independent_success(self) -> None:
        feeds = tuple(
            FeedOutcome(feed.id, feed.name, "ok", (), "", False)
            for feed in FEEDS[:-1]
        ) + (FeedOutcome(FEEDS[-1].id, FEEDS[-1].name, "error", (), "feed_fetch_error", True),)
        market = combine_market_results(
            (
                ProviderResult("google-finance", "ok", {"SPY": 651.2}, ""),
                ProviderResult("spreadsheet", "ok", {"USD/KRW": 1387.5}, ""),
                ProviderResult("cboe", "error", {}, "parser detail", "parse"),
            )
        )
        result = build_user_result(
            report_markdown="# 한눈에 보기\n\n본문",
            report_outcome=WriteOutcome(
                "report",
                "confirmed",
                "https://app.notion.com/p/World-Memory-aaaaaaaaaaaa4aaa8aaaaaaaaaaaaaaa",
                "",
            ),
            feed_outcomes=feeds,
            market=market,
        )
        self.assertEqual(result["status"], "degraded")
        self.assertEqual(result["feedSuccessCount"], 7)
        self.assertEqual(market.values, {"SPY": 651.2, "USD/KRW": 1387.5})

    def test_all_feed_failure_is_prewrite_safe_stop(self) -> None:
        feeds = tuple(
            FeedOutcome(feed.id, feed.name, "error", (), "feed_fetch_error", True)
            for feed in FEEDS
        )
        result = build_user_result(
            report_markdown="",
            report_outcome=WriteOutcome("safe-stop", "failed", "", "all feeds failed"),
            feed_outcomes=feeds,
            market=MarketSnapshot("unavailable", (), {}, ()),
        )
        self.assertEqual(result["status"], "safe-stop")
        self.assertEqual(result["storyChangeCreatedCount"], 0)

    def test_sync_success_and_uncertain_locator_have_no_retry_state(self) -> None:
        page_id = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
        page_url = "https://app.notion.com/p/World-Memory-" + page_id.replace("-", "")
        confirmed = resolve_write_response("report", {"id": page_id, "url": page_url})
        uncertain = resolve_write_response("report", {"status": "timeout", "page_id": page_id})
        self.assertEqual(confirmed.status, "confirmed")
        self.assertEqual(confirmed.warning, "")
        self.assertEqual(uncertain.status, "verify-once")
        self.assertIn("do not retry", uncertain.warning)

    def test_story_integration_is_due_at_345_minutes_and_changes_require_a_confirmed_story(self) -> None:
        now = datetime.fromisoformat("2026-08-14T05:45:00+00:00")
        latest = datetime.fromisoformat("2026-08-14T00:00:00+00:00")
        self.assertEqual(choose_report_type(now, latest), "world-memory")
        with self.assertRaisesRegex(ValueError, "primaryStory"):
            story_change_page(REGISTRY_OBJECT, DECISION, NOW, {})

    def test_bootstrap_is_finite_setup_and_scheduled_prompt_cannot_repair_schema(self) -> None:
        plan = build_bootstrap_plan(WORKSPACE_ID)
        prompt = render_scheduled_prompt(Registry.from_mapping(REGISTRY))
        self.assertEqual(plan["mode"], "fresh-install")
        self.assertEqual(len(plan["actions"]), 12)
        self.assertIn(
            "Scheduled runs must not perform schema, delete, move, migration, or repair operations.",
            prompt,
        )


if __name__ == "__main__":
    unittest.main()
