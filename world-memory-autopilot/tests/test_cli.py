"""Behavioral tests for the offline deterministic World Memory CLI."""

from __future__ import annotations

import ast
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from world_memory.notion_layout import DATABASE_SCHEMAS, bootstrap_manifest
from world_memory.views import (
    REPORTS_RECENT_CONFIGURATION,
    STORIES_CURRENT_CONFIGURATION,
)


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PACKAGE_ROOT / "scripts"

WORKSPACE_ID = "11111111-1111-4111-8111-111111111111"
HUB_ID = "22222222-2222-4222-8222-222222222222"
COLLECTIONS_ID = "33333333-3333-4333-8333-333333333333"
STORIES_ID = "44444444-4444-4444-8444-444444444444"
STORY_CHANGES_ID = "55555555-5555-4555-8555-555555555555"
REPORTS_ID = "66666666-6666-4666-8666-666666666666"
STORY_ID = "77777777-7777-4777-8777-777777777777"
REPORTS_VIEW_ID = "88888888-8888-4888-8888-888888888888"
STORIES_VIEW_ID = "99999999-9999-4999-8999-999999999999"
DATABASE_IDS = {
    "collections": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
    "stories": "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
    "storyChanges": "cccccccc-cccc-4ccc-8ccc-cccccccccccc",
    "reports": "dddddddd-dddd-4ddd-8ddd-dddddddddddd",
}
VIX_PUBLIC_CSV_URL = (
    "https://docs.google.com/spreadsheets/d/"
    "15xqjZq8di2UqrePpYR_p72j5FCj-WTEDC4rdjZSqc_w/export?format=csv&gid=0"
)
VIX_SYMBOLS = ["VIX9D", "VIX", "VIX3M", "VIX6M"]


def notion_url(identifier: str) -> str:
    return "https://www.notion.so/World-Memory-" + identifier.replace("-", "")


def notion_view_url(database_id: str, view_id: str) -> str:
    return (
        "https://app.notion.com/p/"
        + database_id.replace("-", "")
        + "?v="
        + view_id.replace("-", "")
    )


REGISTRY = {
    "schemaVersion": "notion-native-v2",
    "workspaceId": WORKSPACE_ID,
    "hub": {"pageId": HUB_ID, "url": notion_url(HUB_ID)},
    "collections": {"dataSourceId": COLLECTIONS_ID},
    "stories": {"dataSourceId": STORIES_ID},
    "storyChanges": {"dataSourceId": STORY_CHANGES_ID},
    "reports": {"dataSourceId": REPORTS_ID},
    "views": {
        "reportsRecent": {
            "url": notion_view_url(DATABASE_IDS["reports"], REPORTS_VIEW_ID)
        },
        "storiesCurrent": {
            "url": notion_view_url(DATABASE_IDS["stories"], STORIES_VIEW_ID)
        },
    },
    "marketSources": {
        "vixSpreadsheet": {
            "publicCsvUrl": VIX_PUBLIC_CSV_URL,
            "expectedSymbols": VIX_SYMBOLS,
        }
    },
}

REPORT_MARKDOWN = """# 🌍 변동성은 낮지만 경계는 남아 있다

요약.

## Key Takeaway

핵심 결론.

## 시장 현황

시장 현황.

## 중장기 맥락

중장기 맥락.

## 주요 지표들

지표.

## 지켜봐야 할 것들

확인점.

## 관심을 가져볼 만한 이슈들

이슈.

## 출처·데이터 안내

없음."""

VALID_PLAN = {
    "report": {
        "type": "world-memory",
        "stance": "neutral",
        "confidence": "medium",
        "dataQuality": "complete",
        "dataGaps": [],
        "markdown": REPORT_MARKDOWN,
    },
    "storyDecisions": [],
    "evidenceClusters": [
        {
            "clusterId": "cluster-1",
            "importance": "high",
            "evidenceItemIds": ["item-1"],
            "reportSections": ["key-takeaway", "market-status"],
            "storyLocators": [],
        }
    ],
}

TOOL_ACCESS = {
    "fetchSelf": True,
    "queryDataSources": True,
    "fetchPages": True,
    "createPages": True,
    "updatePages": True,
}


def schema_projections() -> dict[str, object]:
    result: dict[str, object] = {}
    for key in ("collections", "stories", "storyChanges", "reports"):
        result[key] = {
            "dataSourceId": REGISTRY[key]["dataSourceId"],
            "properties": {
                name: descriptor["type"]
                for name, descriptor in DATABASE_SCHEMAS[key]["properties"].items()
            },
        }
    return result


def view_projections() -> dict[str, object]:
    return {
        "reportsRecent": {
            "url": REGISTRY["views"]["reportsRecent"]["url"],
            "dataSourceId": REPORTS_ID,
            "configuration": REPORTS_RECENT_CONFIGURATION,
        },
        "storiesCurrent": {
            "url": REGISTRY["views"]["storiesCurrent"]["url"],
            "dataSourceId": STORIES_ID,
            "configuration": STORIES_CURRENT_CONFIGURATION,
        },
    }


def run_cli(*args: str, stdin: str = "") -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(SCRIPTS)
    return subprocess.run(
        [sys.executable, "-m", "world_memory", *args],
        cwd=PACKAGE_ROOT,
        env=env,
        input=stdin,
        text=True,
        capture_output=True,
        check=False,
    )


class CliSmokeTests(unittest.TestCase):
    def test_validate_registry_round_trips_native_shape(self) -> None:
        result = run_cli("validate-registry", stdin=json.dumps(REGISTRY))

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            json.loads(result.stdout)["schemaVersion"], "notion-native-v2"
        )
        self.assertEqual(result.stderr, "")

    def test_realistic_database_urls_are_distinct_and_absent_from_registry(self) -> None:
        for key, database_id in DATABASE_IDS.items():
            with self.subTest(key=key):
                self.assertNotEqual(database_id, REGISTRY[key]["dataSourceId"])
                self.assertNotIn("url", REGISTRY[key])
                self.assertNotIn(database_id, json.dumps(REGISTRY))

    def test_legacy_commands_are_absent(self) -> None:
        help_result = run_cli("--help")

        self.assertEqual(help_result.returncode, 0, help_result.stderr)
        for legacy in (
            "run-key",
            "verify-precommit-snapshot",
            "advance-installation-cache",
            "digest",
        ):
            self.assertNotIn(legacy, help_result.stdout)


class CliMappingTests(unittest.TestCase):
    def assert_success_object(
        self, result: subprocess.CompletedProcess[str]
    ) -> dict[str, object]:
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "")
        self.assertTrue(result.stdout.endswith("\n"))
        self.assertEqual(result.stdout.count("\n"), 1)
        value = json.loads(result.stdout)
        self.assertIs(type(value), dict)
        self.assertEqual(
            result.stdout,
            json.dumps(value, ensure_ascii=False, separators=(",", ":")) + "\n",
        )
        return value

    def test_help_lists_exact_native_command_surface(self) -> None:
        result = run_cli("--help")
        self.assertEqual(result.returncode, 0, result.stderr)
        for command in (
            "validate-registry",
            "schema",
            "bootstrap-plan",
            "window",
            "resolve-report-view",
            "normalize-story-view",
            "validate-llm-plan",
            "render-scheduled-prompt",
            "normalize-feed",
            "market-data-plan",
            "collect-market-data",
            "verify-live",
        ):
            self.assertIn(command, result.stdout)

    def test_schema_maps_an_empty_object_to_an_independent_manifest(self) -> None:
        result = self.assert_success_object(run_cli("schema", "-", stdin="{}"))
        self.assertEqual(result, bootstrap_manifest())
        result["databases"]["reports"]["title"] = "mutated"
        self.assertEqual(
            bootstrap_manifest()["databases"]["reports"]["title"],
            "World Memory Reports",
        )

    def test_named_utf8_file_is_the_same_single_object_transport(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            input_path = Path(directory) / "registry.json"
            input_path.write_text(json.dumps(REGISTRY), encoding="utf-8")
            result = self.assert_success_object(
                run_cli("validate-registry", str(input_path))
            )
        self.assertEqual(result, REGISTRY)

    def test_bootstrap_plan_maps_only_a_workspace_uuid(self) -> None:
        result = self.assert_success_object(
            run_cli(
                "bootstrap-plan",
                stdin=json.dumps({"workspaceId": WORKSPACE_ID}),
            )
        )
        self.assertEqual(result["mode"], "fresh-install")
        self.assertEqual(result["workspaceId"], WORKSPACE_ID)
        self.assertEqual(len(result["databases"]), 4)

    def test_window_maps_supplied_observations_to_utc_decisions(self) -> None:
        request = {
            "now": "2026-08-14T12:00:00+09:00",
            "cadenceMinutes": 180,
            "lastWindowEnd": None,
            "sameWindowReports": [],
            "latestWorldMemoryEnd": "2026-08-13T21:00:00Z",
            "force": False,
        }
        result = self.assert_success_object(
            run_cli("window", stdin=json.dumps(request))
        )
        self.assertEqual(
            result,
            {
                "window": {
                    "start": "2026-08-14T00:00:00Z",
                    "end": "2026-08-14T03:00:00Z",
                },
                "sameWindow": {
                    "disposition": "create",
                    "reportType": None,
                    "reused": None,
                    "warnings": [],
                },
                "reportType": "world-memory",
            },
        )

    def test_window_reuses_one_same_window_report_without_retyping_it(self) -> None:
        existing = {
            "id": REPORTS_ID,
            "Report Type": "briefing",
            "Window Start": "2026-08-14T00:00:00Z",
            "Window End": "2026-08-14T03:00:00Z",
            "Created At": "2026-08-14T03:01:00Z",
        }
        request = {
            "now": "2026-08-14T03:00:00Z",
            "cadenceMinutes": 180,
            "lastWindowEnd": None,
            "sameWindowReports": [existing],
            "latestWorldMemoryEnd": None,
            "force": False,
        }
        result = self.assert_success_object(
            run_cli("window", stdin=json.dumps(request))
        )
        self.assertEqual(result["sameWindow"]["disposition"], "reuse")
        self.assertEqual(result["sameWindow"]["reused"], existing)
        self.assertEqual(result["reportType"], "briefing")

    def test_resolve_report_view_maps_raw_view_rows_to_a_new_window(self) -> None:
        request = {
            "now": "2026-08-14T09:00:00Z",
            "cadenceMinutes": 180,
            "force": False,
            "hasMore": False,
            "rows": [
                {
                    "url": notion_url(REPORTS_ID),
                    "Name": "World Memory",
                    "Report Type": "world-memory",
                    "date:Window Start:start": "2026-08-14T03:00:00Z",
                    "date:Window End:start": "2026-08-14T06:00:00Z",
                    "Created At": "2026-08-14T06:01:00Z",
                    "Collection": [notion_url(COLLECTIONS_ID)],
                    "Stories": [],
                }
            ],
        }

        result = self.assert_success_object(
            run_cli("resolve-report-view", stdin=json.dumps(request))
        )

        self.assertEqual(result["disposition"], "create")
        self.assertEqual(result["window"], {
            "start": "2026-08-14T06:00:00Z",
            "end": "2026-08-14T09:00:00Z",
        })
        self.assertEqual(result["reportType"], "briefing")
        self.assertEqual(result["latestWorldMemoryEnd"], "2026-08-14T06:00:00Z")

    def test_resolve_report_view_reuses_minute_row_for_second_bearing_now(self) -> None:
        request = {
            "now": "2026-08-14T12:35:28.987654Z",
            "cadenceMinutes": 60,
            "force": True,
            "hasMore": False,
            "rows": [
                {
                    "url": notion_url(REPORTS_ID),
                    "Name": "World Memory",
                    "Report Type": "world-memory",
                    "date:Window Start:start": "2026-08-14T11:35:00.000Z",
                    "date:Window End:start": "2026-08-14T12:35:00.000Z",
                    "Created At": "2026-08-14T12:36:00Z",
                }
            ],
        }

        result = self.assert_success_object(
            run_cli("resolve-report-view", stdin=json.dumps(request))
        )

        self.assertEqual(result["disposition"], "reuse")
        self.assertEqual(result["window"]["end"], "2026-08-14T12:35:00Z")

    def test_normalize_story_view_maps_raw_current_rows(self) -> None:
        request = {
            "hasMore": False,
            "rows": [
                {
                    "url": notion_url(STORY_ID),
                    "Name": "Rates reprice risk assets",
                    "Status": "active",
                    "Category": "rates",
                    "Regions": ["US", "GLOBAL"],
                    "Importance": "high",
                    "Confidence": "medium",
                    "Current View": "Rates remain the transmission channel.",
                    "date:First Seen:start": "2026-08-14T00:00:00Z",
                    "date:Last Evidence At:start": "2026-08-14T06:00:00Z",
                    "date:Last Updated:start": "2026-08-14T06:00:00Z",
                    "Related Stories": [],
                    "Created At": "2026-08-14T00:01:00Z",
                }
            ],
        }

        result = self.assert_success_object(
            run_cli("normalize-story-view", stdin=json.dumps(request))
        )

        self.assertEqual(result["disposition"], "complete")
        self.assertEqual(result["stories"][0]["id"], STORY_ID)

    def test_validate_llm_plan_maps_candidate_and_known_bindings_to_the_plan(self) -> None:
        request = {
            "candidate": VALID_PLAN,
            "knownStoryIds": [STORY_ID],
            "evidenceItemIds": ["item-1"],
            "expectedReportType": "world-memory",
        }
        result = self.assert_success_object(
            run_cli("validate-llm-plan", stdin=json.dumps(request))
        )
        self.assertEqual(result, VALID_PLAN)

    def test_render_scheduled_prompt_maps_a_registry_to_one_prompt_field(self) -> None:
        result = self.assert_success_object(
            run_cli("render-scheduled-prompt", stdin=json.dumps(REGISTRY))
        )
        self.assertEqual(set(result), {"prompt"})
        self.assertIn("<world_memory_registry>", result["prompt"])
        self.assertIn('"schemaVersion":"notion-native-v2"', result["prompt"])
        for key, database_id in DATABASE_IDS.items():
            with self.subTest(key=key):
                self.assertNotIn(database_id, result["prompt"])

    def test_normalize_feed_maps_one_supplied_csv_with_configured_offset(self) -> None:
        csv_payload = (
            PACKAGE_ROOT / "tests" / "fixtures" / "rss-app-sample.csv"
        ).read_text(encoding="utf-8")
        result = self.assert_success_object(
            run_cli(
                "normalize-feed",
                stdin=json.dumps(
                    {"feedId": "first_squawk", "csv": csv_payload}
                ),
            )
        )
        self.assertEqual(
            result,
            {
                "sourceId": "first_squawk",
                "sourceName": "First Squawk",
                "status": "ok",
                "items": [
                    {
                        "itemId": (
                            "first_squawk\x1fhttps://example.com/article?id=7"
                            "\x1fMarket headline\x1f2026-08-14T03:00:00Z"
                        ),
                        "sourceId": "first_squawk",
                        "sourceName": "First Squawk",
                        "title": "Market headline",
                        "url": "https://Example.com/article?utm_source=rss&id=7",
                        "publishedAt": "2026-08-14T03:00:00Z",
                        "summary": "Plain fixture summary",
                    }
                ],
                "error": "",
                "retryable": False,
            },
        )

    def test_normalize_feed_converts_html_through_the_shared_summary_boundary(self) -> None:
        csv_payload = (
            PACKAGE_ROOT / "tests" / "fixtures" / "rss-app-sample.csv"
        ).read_text(encoding="utf-8")
        csv_payload = csv_payload.replace(
            "Plain fixture summary",
            (
                "<section>Fed &amp; <strong>markets</strong><br>moved</section>"
                "<!-- comment --><iframe src='https://hidden.example/frame'>"
                "hidden text</iframe>"
            ),
        )

        result = self.assert_success_object(
            run_cli(
                "normalize-feed",
                stdin=json.dumps(
                    {"feedId": "first_squawk", "csv": csv_payload}
                ),
            )
        )

        self.assertEqual(result["items"][0]["summary"], "Fed & markets moved")
        self.assertNotIn("hidden.example", result["items"][0]["summary"])

    def test_market_data_plan_is_declarative_and_provider_independent(self) -> None:
        result = self.assert_success_object(
            run_cli(
                "market-data-plan", stdin=json.dumps({"registry": REGISTRY})
            )
        )
        self.assertEqual(
            result,
            {
                "mode": "caller-supplied-observations",
                "providers": [
                    {"id": "google-finance", "independent": True},
                    {
                        "id": "spreadsheet",
                        "independent": True,
                        "publicCsvUrl": VIX_PUBLIC_CSV_URL,
                        "expectedSymbols": VIX_SYMBOLS,
                    },
                    {"id": "cboe", "independent": True},
                ],
                "combination": {
                    "providerOrder": "input-order",
                    "valueConflict": "first-successful-provider-wins",
                    "failurePolicy": "preserve-independent-successes",
                },
                "externalIo": False,
            },
        )

    def test_collect_market_data_combines_only_supplied_provider_results(self) -> None:
        request = {
            "providers": [
                {
                    "provider": "google-finance",
                    "status": "ok",
                    "values": {"SPY": 651.2},
                    "error": "",
                    "stage": "",
                },
                {
                    "provider": "cboe",
                    "status": "error",
                    "values": {},
                    "error": "credential-shaped-untrusted-parser-detail",
                    "stage": "parse",
                },
            ]
        }
        result = self.assert_success_object(
            run_cli("collect-market-data", stdin=json.dumps(request))
        )
        self.assertEqual(
            result,
            {
                "status": "partial",
                "providers": [
                    {
                        "provider": "google-finance",
                        "status": "ok",
                        "values": {"SPY": 651.2},
                        "error": "",
                        "stage": "",
                    },
                    {
                        "provider": "cboe",
                        "status": "error",
                        "values": {},
                        "error": "market_provider_error",
                        "stage": "parse",
                    },
                ],
                "values": {"SPY": 651.2},
                "gaps": ["cboe: market_provider_error"],
            },
        )

    def test_collect_market_data_rejects_malformed_provider_truth(self) -> None:
        malformed = {
            "providers": [
                {
                    "provider": "cboe",
                    "status": "not-attempted",
                    "values": {},
                    "error": "",
                    "stage": "parse",
                }
            ]
        }

        result = run_cli("collect-market-data", stdin=json.dumps(malformed))

        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")
        self.assertEqual(result.stderr, "invalid-input\n")

    def test_verify_live_validates_only_supplied_canary_evidence(self) -> None:
        projections = schema_projections()
        request = {
            "registry": REGISTRY,
            "workspaceId": WORKSPACE_ID,
            "toolAccess": TOOL_ACCESS,
            "schemaProjections": projections,
            "viewProjections": view_projections(),
        }
        result = self.assert_success_object(
            run_cli("verify-live", stdin=json.dumps(request))
        )
        self.assertEqual(
            result,
            {
                "status": "supplied-evidence-valid",
                "liveExecutionPerformed": False,
                "workspaceId": WORKSPACE_ID,
                "toolAccess": TOOL_ACCESS,
                "registry": REGISTRY,
                "schemaProjections": projections,
                "viewProjections": view_projections(),
            },
        )


class CliSafetyTests(unittest.TestCase):
    def assert_safe_error(
        self,
        result: subprocess.CompletedProcess[str],
        category: str,
        *secret_values: str,
    ) -> None:
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")
        self.assertEqual(result.stderr, category + "\n")
        for secret in secret_values:
            self.assertNotIn(secret, result.stderr)

    def test_malformed_json_nonobjects_duplicate_keys_and_nonfinite_numbers_fail(self) -> None:
        for payload in (
            "not-json",
            "[]",
            '{"workspaceId":"one","workspaceId":"two"}',
            '{"value":NaN}',
        ):
            with self.subTest(payload=payload):
                self.assert_safe_error(
                    run_cli("validate-registry", stdin=payload), "invalid-input"
                )

    def test_deep_json_recursion_is_a_value_free_invalid_input(self) -> None:
        payload = '{"x":' + "[" * 10_000 + "0" + "]" * 10_000 + "}"

        result = run_cli("schema", stdin=payload)

        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, "")
        self.assertEqual(result.stderr, "invalid-input\n")
        for forbidden in (
            "Traceback",
            "RecursionError",
            str(PACKAGE_ROOT),
            str(SCRIPTS),
            "/",
        ):
            self.assertNotIn(forbidden, result.stderr)

    def test_oversized_cadence_is_a_value_free_invalid_input(self) -> None:
        request = {
            "now": "2026-08-14T03:00:00Z",
            "cadenceMinutes": 10**100,
            "lastWindowEnd": None,
            "sameWindowReports": [],
            "latestWorldMemoryEnd": None,
            "force": False,
        }

        result = run_cli("window", stdin=json.dumps(request))

        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, "")
        self.assertEqual(result.stderr, "invalid-input\n")
        for forbidden in (
            "Traceback",
            "OverflowError",
            str(PACKAGE_ROOT),
            str(SCRIPTS),
            "/",
        ):
            self.assertNotIn(forbidden, result.stderr)

    def test_invalid_values_never_appear_in_stderr(self) -> None:
        secret = "credential-shaped-secret-value"
        broken = {**REGISTRY, "workspaceId": secret}
        self.assert_safe_error(
            run_cli("validate-registry", stdin=json.dumps(broken)),
            "invalid-input",
            secret,
        )

        self.assert_safe_error(
            run_cli("unknown-" + secret, stdin="{}"),
            "cli-usage-error",
            secret,
        )

    def test_validate_registry_rejects_database_url_or_id_on_data_source_locator(self) -> None:
        for key, value in (
            ("url", notion_url(DATABASE_IDS["reports"])),
            ("databaseId", DATABASE_IDS["reports"]),
        ):
            with self.subTest(key=key):
                broken = json.loads(json.dumps(REGISTRY))
                broken["reports"][key] = value
                self.assert_safe_error(
                    run_cli("validate-registry", stdin=json.dumps(broken)),
                    "invalid-input",
                    value,
                )

    def test_unreadable_or_non_utf8_paths_use_one_value_free_category(self) -> None:
        secret = "credential-shaped-missing-path"
        self.assert_safe_error(
            run_cli("schema", f"/tmp/{secret}.json"),
            "input-read-error",
            secret,
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "invalid-utf8.json"
            path.write_bytes(b"\xff")
            result = run_cli("schema", str(path))
        self.assert_safe_error(result, "input-read-error", str(path))

    def test_exact_input_shapes_reject_extra_payload_or_extra_path_arguments(self) -> None:
        self.assert_safe_error(
            run_cli("schema", stdin='{"unexpected":true}'), "invalid-input"
        )
        self.assert_safe_error(
            run_cli("schema", "-", "second.json", stdin="{}"),
            "cli-usage-error",
            "second.json",
        )

    def test_verify_live_rejects_workspace_access_locator_or_schema_contradictions(self) -> None:
        base = {
            "registry": REGISTRY,
            "workspaceId": WORKSPACE_ID,
            "toolAccess": TOOL_ACCESS,
            "schemaProjections": schema_projections(),
            "viewProjections": view_projections(),
        }
        broken_values = []

        wrong_workspace = json.loads(json.dumps(base))
        wrong_workspace["workspaceId"] = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
        broken_values.append(wrong_workspace)

        missing_access = json.loads(json.dumps(base))
        missing_access["toolAccess"]["updatePages"] = False
        broken_values.append(missing_access)

        wrong_locator = json.loads(json.dumps(base))
        wrong_locator["schemaProjections"]["reports"]["dataSourceId"] = STORIES_ID
        broken_values.append(wrong_locator)

        wrong_schema = json.loads(json.dumps(base))
        wrong_schema["schemaProjections"]["reports"]["properties"]["Name"] = "rich_text"
        broken_values.append(wrong_schema)

        wrong_view = json.loads(json.dumps(base))
        wrong_view["viewProjections"]["reportsRecent"]["dataSourceId"] = STORIES_ID
        broken_values.append(wrong_view)

        for value in broken_values:
            with self.subTest(value=value):
                self.assert_safe_error(
                    run_cli("verify-live", stdin=json.dumps(value)),
                    "invalid-input",
                )

    def test_task6_runtime_modules_import_no_network_connector_model_or_process_clients(self) -> None:
        prohibited_roots = {
            "http",
            "httpx",
            "notion_client",
            "openai",
            "requests",
            "socket",
            "subprocess",
        }
        prohibited_full = {"urllib.request"}
        imported: set[str] = set()
        for path in (
            SCRIPTS / "world_memory" / "cli.py",
            SCRIPTS / "world_memory" / "bootstrap.py",
        ):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imported.update(alias.name for alias in node.names)
                elif isinstance(node, ast.ImportFrom) and node.module:
                    imported.add(node.module)
        self.assertFalse({name.split(".")[0] for name in imported} & prohibited_roots)
        self.assertFalse(imported & prohibited_full)

    def test_main_uses_only_explicit_safe_exception_categories(self) -> None:
        tree = ast.parse(
            (SCRIPTS / "world_memory" / "cli.py").read_text(encoding="utf-8")
        )
        main = next(
            node
            for node in tree.body
            if isinstance(node, ast.FunctionDef) and node.name == "main"
        )
        caught: set[str] = set()
        for handler in (
            node for node in ast.walk(main) if isinstance(node, ast.ExceptHandler)
        ):
            if isinstance(handler.type, ast.Name):
                caught.add(handler.type.id)
            elif isinstance(handler.type, ast.Tuple):
                caught.update(
                    item.id
                    for item in handler.type.elts
                    if isinstance(item, ast.Name)
                )

        self.assertTrue({"RecursionError", "OverflowError"}.issubset(caught))
        self.assertFalse(
            {
                "SystemExit",
                "KeyboardInterrupt",
                "MemoryError",
                "Exception",
                "BaseException",
            }
            & caught
        )


if __name__ == "__main__":
    unittest.main()
