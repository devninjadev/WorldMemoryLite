"""Regression coverage for omitted review and incomplete entity work, without I/O."""

import copy
import io
import json
import unittest

from world_memory.cli import main
from world_memory.entity_completion import complete_entity_review, validate_plan_request
from world_memory.llm_plan import ValidationContext, run_plan_with_repair
from world_memory.feed import FEEDS, FeedOutcome
from world_memory.notion_payloads import prepare_report, report_page
from world_memory.registry import Registry
from world_memory.windows import Window
from datetime import datetime, timezone
from world_memory.market import MarketSnapshot, ProviderResult
from world_memory.workflow import WriteOutcome, build_user_result

PAGE = "11111111-1111-4111-8111-111111111111"
MARKDOWN = """# 다음 주 발표를 기다리는 시장
## Key Takeaway
- 고용 발표는 금리 기대를 바꿀 수 있어 다음 주 확인이 필요하다.
- 현재 표본에서는 기존 관점을 바꿀 새 기업 정보가 없다.
- 마지막 완결 거래일의 가격은 발표 이후의 반응을 보여주지 않는다.
## 시장 현황
현재 가격은 마지막 완결 거래일의 관측이다. 발표 이후 가격 반응은 아직 관측되지 않았다.

금리 변화가 성장주 할인율에 전달될 수 있다. 실제 반응은 다음 거래일의 관측으로 확인한다.

단일 가격 변화만으로 원인을 단정하지 않는다. 신용과 시장폭이 동반하는지 확인할 필요가 있다.

## 중장기 맥락
이번 표본에서는 기존 거시 관점을 바꿀 새로운 사건을 확인하지 못했다. 발표 일정은 이미 알려진 것이다.

고용과 물가 변화는 정책 기대에 영향을 줄 수 있다. 현재 관점을 바꿀지는 다음 발표를 읽고 판단한다.

정책 변화와 실제 주문 사이에는 시차가 존재한다. 그 시차를 확인할 자료가 아직 충분하지 않다.

## 주요 지표들
마지막 완결 세션을 사용했다.
## 지켜봐야 할 것들
다음 발표와 금리 반응.
## 관심을 가져볼 만한 이슈들
할인율과 기업 실적의 관계.
## 출처·데이터 안내
외부 접속 없는 합성 테스트 근거.
"""


def request(planned=False, report_type="world-memory"):
    plan = {"report": {"type": report_type, "stance": "neutral", "confidence": "medium",
        "dataQuality": "complete", "dataGaps": [], "markdown": MARKDOWN},
        "storyDecisions": [], "evidenceClusters": [{"clusterId": "c1", "importance": "medium",
        "evidenceItemIds": ["e1"], "reportSections": ["key-takeaway"], "storyLocators": []}],
        "entityPlan": {"industries": [], "companies": [], "events": []},
        "entityReview": [{"clusterId": "c1", "disposition": "not-applicable", "companyKeys": [],
        "industryKeys": [], "eventKeys": [], "reason": "기존 일정의 반복이며 새 기업·산업·사건 변화가 없다."}]}
    if planned:
        plan["entityPlan"]["companies"] = [{"key": "co1", "name": "Example Memory",
            "aliases": [], "tickers": ["NASDAQ:EXAMPLE"], "listingStatus": "listed",
            "evidenceItemIds": ["e1"], "memory": {"currentView": "메모리 수요를 관찰한다.",
            "change": "새 실적 일정이 발표됐다.", "nextCheck": "실적과 가이던스를 확인한다."}}]
        plan["entityReview"][0].update(disposition="planned", companyKeys=["co1"], reason="실적 일정과 현재 관점을 기록한다.")
    return {"candidate": plan, "knownStoryIds": [], "evidenceItemIds": ["e1"],
        "expectedReportType": report_type,
        "entityContext": {"policy": "additive-entities-v1", "readiness": "ready", "reason": ""}}


def completion(planned=False, status=None):
    value = {"validation": request(planned), "outcomes": [], "linkGaps": []}
    if status:
        value["outcomes"] = [{"role": "companies", "key": "co1", "status": status,
            "pageId": PAGE if status in ("created", "updated", "unchanged") else None,
            "reason": "확인한 처리 결과"}]
    return value


def registry():
    def uid(n):
        return f"{n:08d}-1111-4111-8111-111111111111"
    return {"schemaVersion": "notion-native-v2", "workspaceId": uid(1),
        "hub": {"pageId": uid(2), "url": "https://app.notion.com/p/" + uid(2)},
        **{role: {"dataSourceId": uid(n)} for n, role in enumerate(
            ("collections", "stories", "storyChanges", "reports"), 3)},
        "views": {role: {"url": f"https://app.notion.com/p/{uid(n)}?v={uid(n+2)}"}
            for n, role in enumerate(("reportsRecent", "storiesCurrent"), 7)},
        "marketSources": {"vixSpreadsheet": {"publicCsvUrl":
            "https://docs.google.com/spreadsheets/d/15xqjZq8di2UqrePpYR_p72j5FCj-WTEDC4rdjZSqc_w/export?format=csv&gid=0",
            "expectedSymbols": ["VIX9D", "VIX", "VIX3M", "VIX6M"]}}}


def preparation():
    return {"registry": registry(), "window": {"start": "2026-09-28T00:00:00Z", "end": "2026-09-28T06:00:00Z"},
        "validation": request(), "relations": {}}


class ReportPreparationTests(unittest.TestCase):
    def test_incomplete_decision_returns_concrete_review_work(self):
        value = preparation()
        del value["validation"]["candidate"]["entityReview"][0]["reason"]
        result = prepare_report(value)
        self.assertEqual(result["status"], "needs-review")
        self.assertEqual(result["clustersToReview"][0]["clusterId"], "c1")
        self.assertNotIn("request", result)

    def test_missing_review_returns_work_then_accepts_the_completed_decision(self):
        value = preparation()
        review = value["validation"]["candidate"].pop("entityReview")
        pending = prepare_report(value)
        self.assertEqual(pending["status"], "needs-review")
        self.assertNotIn("request", pending)
        self.assertEqual(pending["clustersToReview"][0]["clusterId"], "c1")
        value["validation"]["candidate"]["entityReview"] = review
        self.assertEqual(prepare_report(value)["status"], "ready")

    def test_report_payload_does_not_contain_internal_review(self):
        value = preparation()
        value["validation"]["candidate"]["entityReview"][0]["reason"] = "INTERNAL_REVIEW_ONLY"
        prepared = prepare_report(value)
        self.assertNotIn("INTERNAL_REVIEW_ONLY", json.dumps(prepared["request"]))
        self.assertNotIn("entityReview", json.dumps(prepared["request"]))

    def test_direct_builder_cannot_bypass_missing_review(self):
        value = request()
        del value["candidate"]["entityReview"]
        window = Window(datetime(2026, 9, 28, tzinfo=timezone.utc), datetime(2026, 9, 28, 6, tzinfo=timezone.utc))
        with self.assertRaises(ValueError):
            report_page(Registry.from_mapping(registry()), window, value)


class RequiredReviewTests(unittest.TestCase):
    def test_missing_context_and_old_flag_are_rejected(self):
        for legacy in (False, True):
            value = request()
            del value["entityContext"]
            if legacy:
                value["entityReviewRequired"] = False
            with self.assertRaises(ValueError):
                validate_plan_request(value)

    def test_missing_review_fails_for_both_report_types(self):
        for kind in ("briefing", "world-memory"):
            for field in ("entityPlan", "entityReview"):
                value = request(report_type=kind)
                del value["candidate"][field]
                with self.assertRaises(ValueError):
                    validate_plan_request(value)

    def test_valid_no_change_and_planned_company(self):
        for planned in (False, True):
            value = request(planned)
            self.assertEqual(validate_plan_request(value), value["candidate"])

    def test_missing_cluster_and_memory_fail(self):
        value = request(True)
        value["candidate"]["entityReview"] = []
        with self.assertRaises(ValueError):
            validate_plan_request(value)
        value = request(True)
        del value["candidate"]["entityPlan"]["companies"][0]["memory"]
        with self.assertRaises(ValueError):
            validate_plan_request(value)

    def test_deferred_review_reason_stays_internal(self):
        value = request()
        value["candidate"]["entityReview"][0].update(disposition="deferred", reason="신원 확인 미완료")
        result = complete_entity_review({"validation": value, "outcomes": [], "linkGaps": []})
        self.assertEqual(result["status"], "degraded")
        self.assertEqual(value["candidate"]["report"]["dataGaps"], [])

    def test_report_only_escape_is_rejected(self):
        value = request()
        del value["candidate"]["entityPlan"], value["candidate"]["entityReview"]
        value["entityReviewFailure"] = "필수 검토 검증 실패"
        value["candidate"]["report"].update(dataQuality="limited", dataGaps=[value["entityReviewFailure"]])
        with self.assertRaises(ValueError):
            validate_plan_request(value)

    def test_disabled_and_unavailable_are_explicit(self):
        for state in ("disabled", "unavailable", "incomplete"):
            value = completion()
            validation = value["validation"]
            del validation["candidate"]["entityPlan"], validation["candidate"]["entityReview"]
            validation["entityContext"] = {"policy": "disabled" if state == "disabled" else "additive-entities-v1",
                "readiness": state, "reason": "관측한 정책 또는 접근 상태"}
            if state != "disabled":
                with self.assertRaises(ValueError):
                    validate_plan_request(validation)
                validation["candidate"]["report"]["dataGaps"] = [validation["entityContext"]["reason"]]
            self.assertEqual(complete_entity_review(value)["status"], "disabled" if state == "disabled" else "degraded")

    def test_repair_cannot_forget_required_review(self):
        calls = []
        candidate = request()["candidate"]
        del candidate["entityReview"]
        ctx = ValidationContext(frozenset(), frozenset({"e1"}), "world-memory", True)
        result = run_plan_with_repair(lambda payload: calls.append(payload) or candidate,
            input_payload={"evidence": []}, validation_context=ctx)
        self.assertEqual((result.status, len(calls)), ("invalid", 2))

    def test_cli_rejects_omission_and_emits_checked_no_change(self):
        for command, value, expected_code in (("validate-llm-plan", {}, 2),
                ("complete-entity-review", completion(), 0)):
            out, err = io.StringIO(), io.StringIO()
            code = main([command, "-"], stdin=io.StringIO(json.dumps(value)), stdout=out, stderr=err)
            self.assertEqual(code, expected_code)
            if not code:
                self.assertEqual(json.loads(out.getvalue())["status"], "no-change")


class CompletionTests(unittest.TestCase):
    def test_missing_outcome_is_degraded(self):
        result = complete_entity_review(completion(True))
        self.assertEqual(result["status"], "degraded")
        self.assertEqual(result["counts"]["companies"]["missing"], 1)

    def test_successful_and_unsuccessful_outcomes(self):
        for status in ("created", "updated", "unchanged", "deferred", "failed"):
            result = complete_entity_review(completion(True, status))
            self.assertEqual(result["status"], "degraded" if status in ("deferred", "failed") else "completed")
            self.assertEqual(result["counts"]["companies"][status], 1)

    def test_unknown_duplicate_and_unconfirmed_success_rejected(self):
        for case in ("unknown", "duplicate", "unconfirmed"):
            value = completion(True, "updated")
            if case == "unknown":
                value["outcomes"][0]["key"] = "unknown"
            elif case == "duplicate":
                value["outcomes"].append(copy.deepcopy(value["outcomes"][0]))
            else:
                value["outcomes"][0]["pageId"] = None
            with self.assertRaises(ValueError):
                complete_entity_review(value)

    def test_link_gap_degrades_and_does_not_change_input(self):
        value = completion(True, "updated")
        value["linkGaps"] = ["Report Story 연결 실패"]
        before = copy.deepcopy(value)
        self.assertEqual(complete_entity_review(value)["status"], "degraded")
        self.assertEqual(value, before)

    def test_report_success_alone_cannot_be_completed(self):
        market = MarketSnapshot("ok", (ProviderResult("test", "ok", {"SPY": 100}, ""),), {"SPY": 100}, ())
        base = dict(report_markdown=MARKDOWN,
            report_outcome=WriteOutcome("report", "confirmed", f"https://app.notion.com/p/{PAGE}", ""),
            feed_outcomes=tuple(FeedOutcome(f.id, f.name, "ok", (), "", False) for f in FEEDS), market=market)
        self.assertEqual(build_user_result(**base)["status"], "degraded")
        self.assertEqual(build_user_result(**base, entity_completion=completion())["status"], "completed")
        self.assertEqual(build_user_result(**base, entity_completion=completion(True))["status"], "degraded")

    def test_reuse_is_not_a_new_review(self):
        market = MarketSnapshot("unavailable", (), {}, ())
        result = build_user_result(report_markdown="", report_outcome=WriteOutcome("reused", "confirmed", PAGE, ""),
            feed_outcomes=(), market=market)
        self.assertEqual(result["status"], "reused")
        self.assertNotIn("entityCompletion", result)


if __name__ == "__main__":
    unittest.main()
