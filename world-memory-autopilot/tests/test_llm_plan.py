"""Tests for temporary, validated LLM story-plan control output."""

from __future__ import annotations

import copy
import unittest

from world_memory.llm_plan import (
    CHANGE_TYPES,
    DIRECTIONS,
    LEVELS,
    REPORT_TYPES,
    PlanAttempt,
    ValidationContext,
    run_plan_with_repair,
    validate_llm_plan,
)


STORY_ID = "story-1"
INPUT = {
    "evidence": [
        {
            "itemId": "item-1",
            "title": "A verified market development",
            "summary": "Structured evidence supplied by the Workspace Agent.",
            "sourceUrl": "https://example.test/article",
        }
    ],
    "storyCandidates": [{"locator": STORY_ID, "name": "Existing story"}],
    "connectorPayload": {"authorization": "Bearer should-not-be-replayed"},
    "credentials": {"apiKey": "must-not-be-replayed"},
}
CTX = ValidationContext(
    known_story_locators=frozenset({STORY_ID}),
    evidence_item_ids=frozenset({"item-1"}),
    expected_report_type="world-memory",
)
REPORT_MARKDOWN = """# 🌍 변동성은 낮지만 경계는 남아 있다

요약.

## Key Takeaway

- 주식시장의 방향은 견조하지만 에너지발 물가 위험이 남아 있어 전체 환경은 엇갈린다.
- 낮은 단기 변동성은 즉각적인 공포가 제한적이라는 근거지만 중기 위험까지 사라졌다는 뜻은 아니다.
- 유가와 장기금리가 함께 오르면 미국 성장주와 한국 수입물가에 부담이 전해질 수 있다.

## 시장 현황

S&P 500은 높은 수준을 유지했고 단기 변동성은 낮았다. 위험선호가 급격히 꺾였다는 가격 증거는 아직 없다.

반면 원유 가격은 지정학적 공급 우려를 반영해 상승했다. 주식과 에너지가 서로 다른 위험 신호를 보내는 혼합 국면이다.

유가 상승이 장기금리와 기대인플레이션으로 이어지면 미국 성장주와 한국의 수입물가에 부담이 전해질 수 있다. 아직 그 전이는 가격에서 뚜렷하게 확인되지 않았다.

## 중장기 맥락

이전 보고서의 낮은 단기 공포 판단은 유지된다. 다만 에너지 위험이 더해져 위험선호의 질은 약해졌다.

공급 차질이 현실화되면 유가, 기대인플레이션, 장기금리 순으로 충격이 누적될 수 있다. 공급 차질 없이 발언과 제재에 머물면 영향은 제한될 가능성이 높다.

다음 보고서에서는 원유 상승의 지속성과 장기금리 반응을 함께 확인해야 한다. 둘 중 하나가 되돌려지면 현재의 경계 판단도 약해진다.

## 주요 지표들

주요 지표.

## 지켜봐야 할 것들

확인점.

## 관심을 가져볼 만한 이슈들

관심 이슈.

## 출처·데이터 안내

없음."""
OBSERVED_FAILURE_MARKDOWN = """# 유가는 올랐지만 주식시장의 공포는 번지지 않았다

## Key Takeaway

에너지 가격은 지정학 위험을 반영하기 시작했지만 금융시장은 아직 이를 국지적 충격으로 보는 모습이다.

## 시장 현황

- S&P 500은 높은 수준을 유지했다.
- VIX 곡선은 우상향했다.
- WTI와 브렌트유는 상승했다.

## 중장기 맥락

현재 시장은 에너지 인플레이션 위험과 낮은 주식 변동성을 동시에 가격에 담고 있다.

## 주요 지표들

- S&P 500과 VIX

## 지켜봐야 할 것들

- 유가와 장기금리

## 관심을 가져볼 만한 이슈들

- 공급망 정책

## 출처·데이터 안내

공개 시장 자료."""
V011_REPORT_MARKDOWN = """# 한눈에 보기

요약.

## 지금 시장을 움직이는 이야기

핵심 Story.

## 자산별 전개

자산별 전개.

## 강화된 Story와 약화된 Story

변화.

## 반대 근거와 불확실성

반대 근거.

## 다음 확인점

다음 일정.

## 데이터 공백

없음."""
STORY_MARKDOWN = """# 현재 판단

현재 판단.

## 전파 경로

전파 경로.

## 강화 근거

- 근거

## 반대 근거와 불확실성

- 반대 근거

## 무효화 조건

- 조건

## 다음 확인점

- 확인점

## 관련 Story

- 관련 Story"""
CHANGE_MARKDOWN = """# 무엇이 바뀌었나

변화.

## 왜 바뀌었나

이유.

## 시장에 미치는 의미

시장 의미.

## 다음 확인점

확인점."""
VALID = {
    "report": {
        "type": "world-memory",
        "stance": "neutral",
        "confidence": "medium",
        "dataQuality": "complete",
        "dataGaps": [],
        "markdown": REPORT_MARKDOWN,
    },
    "storyDecisions": [
        {
            "action": "update",
            "storyLocator": STORY_ID,
            "name": "Existing story",
            "status": "active",
            "category": "macro",
            "regions": ["US", "GLOBAL"],
            "changeType": "reframed",
            "direction": "reframes",
            "importance": "medium",
            "confidence": "medium",
            "currentView": "The current view is materially unchanged.",
            "storyMarkdown": STORY_MARKDOWN,
            "changeMarkdown": CHANGE_MARKDOWN,
            "relatedStoryLocators": [],
            "evidenceItemIds": ["item-1"],
        }
    ],
    "evidenceClusters": [
        {
            "clusterId": "cluster-1",
            "importance": "high",
            "evidenceItemIds": ["item-1"],
            "reportSections": ["key-takeaway", "market-status"],
            "storyLocators": [STORY_ID],
        }
    ],
}


def replace_report_section(markdown: str, heading: str, replacement: str) -> str:
    """Replace one exact H2 body in a test fixture without production helpers."""

    start = markdown.index(f"{heading}\n") + len(heading) + 1
    next_heading = markdown.find("\n## ", start)
    if next_heading < 0:
        next_heading = len(markdown)
    return markdown[:start] + f"\n{replacement.strip()}\n" + markdown[next_heading:]


class LlmPlanValidationTests(unittest.TestCase):
    def test_exports_schema_compatible_enums(self) -> None:
        self.assertIn("reframed", CHANGE_TYPES)
        self.assertIn("connects", DIRECTIONS)
        self.assertEqual(LEVELS, ("high", "medium", "low"))
        self.assertEqual(REPORT_TYPES, ("briefing", "world-memory"))

    def test_accepts_valid_update_plan_without_persisting_control_json(self) -> None:
        result = validate_llm_plan(
            VALID,
            known_story_locators={STORY_ID},
            evidence_item_ids={"item-1"},
            expected_report_type="world-memory",
        )
        self.assertEqual(result["storyDecisions"][0]["changeType"], "reframed")
        self.assertIsNot(result, VALID)
        self.assertIsNot(result["report"], VALID["report"])
        self.assertIsNot(result["evidenceClusters"], VALID["evidenceClusters"])
        self.assertIsNot(
            result["evidenceClusters"][0], VALID["evidenceClusters"][0]
        )

    def test_accepts_generated_report_h1_and_exact_approved_h2_layout(self) -> None:
        result = validate_llm_plan(
            VALID,
            known_story_locators={STORY_ID},
            evidence_item_ids={"item-1"},
            expected_report_type="world-memory",
        )

        headings = [
            line
            for line in result["report"]["markdown"].splitlines()
            if line.startswith("#")
        ]
        self.assertEqual(
            headings,
            [
                "# 🌍 변동성은 낮지만 경계는 남아 있다",
                "## Key Takeaway",
                "## 시장 현황",
                "## 중장기 맥락",
                "## 주요 지표들",
                "## 지켜봐야 할 것들",
                "## 관심을 가져볼 만한 이슈들",
                "## 출처·데이터 안내",
            ],
        )

    def test_rejects_observed_prose_takeaway_list_market_and_shallow_context(self) -> None:
        broken = copy.deepcopy(VALID)
        broken["report"]["markdown"] = OBSERVED_FAILURE_MARKDOWN

        with self.assertRaisesRegex(ValueError, "Key Takeaway"):
            validate_llm_plan(
                broken,
                known_story_locators={STORY_ID},
                evidence_item_ids={"item-1"},
                expected_report_type="world-memory",
            )

    def test_key_takeaway_requires_three_to_five_unordered_items(self) -> None:
        cases = {
            "two-items": "- 첫째 판단\n- 둘째 판단",
            "six-items": "\n".join(f"- 판단 {index}" for index in range(1, 7)),
            "ordered-items": "1. 첫째 판단\n2. 둘째 판단\n3. 셋째 판단",
            "prose": "판단과 근거와 영향을 한 문단에 함께 쓴다.",
        }

        for name, takeaway in cases.items():
            with self.subTest(name=name):
                broken = copy.deepcopy(VALID)
                broken["report"]["markdown"] = replace_report_section(
                    REPORT_MARKDOWN, "## Key Takeaway", takeaway
                )
                with self.assertRaisesRegex(ValueError, "Key Takeaway"):
                    validate_llm_plan(
                        broken,
                        known_story_locators={STORY_ID},
                        evidence_item_ids={"item-1"},
                        expected_report_type="world-memory",
                    )

    def test_report_type_controls_narrative_paragraph_minimums(self) -> None:
        two_paragraphs = (
            "현재 시장은 위험선호와 공급 충격 우려가 공존한다.\n\n"
            "다음 확인점은 유가 상승이 장기금리로 전이되는지 여부다."
        )
        markdown = replace_report_section(
            REPORT_MARKDOWN, "## 시장 현황", two_paragraphs
        )
        markdown = replace_report_section(
            markdown, "## 중장기 맥락", two_paragraphs
        )

        briefing = copy.deepcopy(VALID)
        briefing["report"]["type"] = "briefing"
        briefing["report"]["markdown"] = markdown
        validate_llm_plan(
            briefing,
            known_story_locators={STORY_ID},
            evidence_item_ids={"item-1"},
            expected_report_type="briefing",
        )

        world_memory = copy.deepcopy(VALID)
        world_memory["report"]["markdown"] = markdown
        with self.assertRaisesRegex(ValueError, "at least 3 prose paragraphs"):
            validate_llm_plan(
                world_memory,
                known_story_locators={STORY_ID},
                evidence_item_ids={"item-1"},
                expected_report_type="world-memory",
            )

    def test_briefing_rejects_one_narrative_paragraph(self) -> None:
        broken = copy.deepcopy(VALID)
        broken["report"]["type"] = "briefing"
        broken["report"]["markdown"] = replace_report_section(
            REPORT_MARKDOWN,
            "## 중장기 맥락",
            "현재 판단과 다음 확인점을 한 문단에 압축했다.",
        )

        with self.assertRaisesRegex(ValueError, "at least 2 prose paragraphs"):
            validate_llm_plan(
                broken,
                known_story_locators={STORY_ID},
                evidence_item_ids={"item-1"},
                expected_report_type="briefing",
            )

    def test_narrative_sections_reject_top_level_lists(self) -> None:
        cases = {
            "unordered-market": (
                "## 시장 현황",
                "- 주가는 견조하다.\n- 유가는 상승했다.\n- 전이는 아직 제한적이다.",
            ),
            "ordered-context": (
                "## 중장기 맥락",
                "1. 기존 판단은 유지된다.\n2. 공급 충격을 확인한다.\n3. 금리 전이를 본다.",
            ),
        }

        for name, (heading, body) in cases.items():
            with self.subTest(name=name):
                broken = copy.deepcopy(VALID)
                broken["report"]["markdown"] = replace_report_section(
                    REPORT_MARKDOWN, heading, body
                )
                with self.assertRaisesRegex(ValueError, "must use prose paragraphs"):
                    validate_llm_plan(
                        broken,
                        known_story_locators={STORY_ID},
                        evidence_item_ids={"item-1"},
                        expected_report_type="world-memory",
                    )

    def test_narrative_sections_have_no_maximum_and_ignore_code_markers(self) -> None:
        seven_paragraphs = "\n\n".join(
            f"문단 {index}은 서로 다른 증거 역할을 설명한다."
            for index in range(1, 8)
        )
        seven_paragraphs += (
            "\n\n```text\n- 코드 안 목록은 산문 형식 위반이 아니다.\n```"
            "\n\n    1. 들여쓴 코드도 목록으로 계산하지 않는다."
        )
        markdown = replace_report_section(
            REPORT_MARKDOWN, "## 시장 현황", seven_paragraphs
        )
        markdown = replace_report_section(
            markdown,
            "## 중장기 맥락",
            "S&P 500의 위험-보상은 엇갈린다. 2026년 수치는 문장이지 목록이 아니다.\n\n"
            "장기금리 전이는 아직 확인되지 않았다.\n\n"
            "다음 보고서에서 유가와 금리를 함께 점검한다.",
        )

        accepted = copy.deepcopy(VALID)
        accepted["report"]["markdown"] = markdown
        result = validate_llm_plan(
            accepted,
            known_story_locators={STORY_ID},
            evidence_item_ids={"item-1"},
            expected_report_type="world-memory",
        )
        self.assertEqual(result["report"]["markdown"], markdown)

    def test_key_takeaway_ignores_list_markers_inside_code(self) -> None:
        takeaway = (
            "- 첫째 판단\n- 둘째 판단\n- 셋째 판단\n\n"
            "```text\n- 코드 안 항목은 네 번째 판단이 아니다.\n```\n\n"
            "    - 들여쓴 코드 안 항목도 판단이 아니다."
        )
        accepted = copy.deepcopy(VALID)
        accepted["report"]["markdown"] = replace_report_section(
            REPORT_MARKDOWN, "## Key Takeaway", takeaway
        )

        result = validate_llm_plan(
            accepted,
            known_story_locators={STORY_ID},
            evidence_item_ids={"item-1"},
            expected_report_type="world-memory",
        )
        self.assertEqual(result["report"]["markdown"], accepted["report"]["markdown"])

    def test_rejects_missing_duplicated_reordered_or_legacy_report_layout(self) -> None:
        missing = REPORT_MARKDOWN.replace("## 출처·데이터 안내", "")
        duplicated = REPORT_MARKDOWN + "\n\n## 시장 현황\n\n중복."
        reordered = REPORT_MARKDOWN.replace(
            "## 시장 현황", "## REORDER-TEMP"
        ).replace("## 중장기 맥락", "## 시장 현황").replace(
            "## REORDER-TEMP", "## 중장기 맥락"
        )
        extra_h1 = REPORT_MARKDOWN + "\n\n# 뒤늦은 제목\n\n본문."
        cases = {
            "missing": missing,
            "duplicated": duplicated,
            "reordered": reordered,
            "extra-h1": extra_h1,
            "complete-v0.11-layout": V011_REPORT_MARKDOWN,
        }

        for name, markdown in cases.items():
            with self.subTest(name=name):
                broken = copy.deepcopy(VALID)
                broken["report"]["markdown"] = markdown
                with self.assertRaisesRegex(ValueError, "report.markdown"):
                    validate_llm_plan(
                        broken,
                        known_story_locators={STORY_ID},
                        evidence_item_ids={"item-1"},
                        expected_report_type="world-memory",
                    )

    def test_story_and_change_markdown_keep_their_fixed_h1_contracts(self) -> None:
        for field in ("storyMarkdown", "changeMarkdown"):
            with self.subTest(field=field):
                broken = copy.deepcopy(VALID)
                old_h1 = broken["storyDecisions"][0][field].splitlines()[0]
                broken["storyDecisions"][0][field] = broken["storyDecisions"][0][
                    field
                ].replace(old_h1, "# generated replacement", 1)
                with self.assertRaisesRegex(ValueError, f"{field}.*first heading"):
                    validate_llm_plan(
                        broken,
                        known_story_locators={STORY_ID},
                        evidence_item_ids={"item-1"},
                        expected_report_type="world-memory",
                    )

    def test_required_headings_inside_indented_code_are_rejected_for_every_role(self) -> None:
        cases = (
            (
                "report",
                "markdown",
                "    # Hidden Report\n"
                "    ## Key Takeaway\n"
                "    ## 시장 현황\n"
                "    ## 중장기 맥락\n"
                "    ## 주요 지표들\n"
                "    ## 지켜봐야 할 것들\n"
                "    ## 관심을 가져볼 만한 이슈들\n"
                "    ## 출처·데이터 안내",
            ),
            (
                "story",
                "storyMarkdown",
                "    # 현재 판단\n"
                "    ## 전파 경로\n"
                "    ## 강화 근거\n"
                "    ## 반대 근거와 불확실성\n"
                "    ## 무효화 조건\n"
                "    ## 다음 확인점\n"
                "    ## 관련 Story",
            ),
            (
                "change",
                "changeMarkdown",
                "    # 무엇이 바뀌었나\n"
                "    ## 왜 바뀌었나\n"
                "    ## 시장에 미치는 의미\n"
                "    ## 다음 확인점",
            ),
        )

        for owner, field, markdown in cases:
            with self.subTest(owner=owner):
                broken = copy.deepcopy(VALID)
                target = (
                    broken["report"]
                    if owner == "report"
                    else broken["storyDecisions"][0]
                )
                target[field] = markdown
                with self.assertRaisesRegex(ValueError, field):
                    validate_llm_plan(
                        broken,
                        known_story_locators={STORY_ID},
                        evidence_item_ids={"item-1"},
                        expected_report_type="world-memory",
                    )

    def test_invalid_fence_closers_never_release_required_headings(self) -> None:
        cases = (
            (
                "report-trailing-text",
                "report",
                "markdown",
                "```python\n"
                "untrusted code\n"
                "```not-a-valid-closing-fence\n"
                "# Hidden Report\n"
                "## Key Takeaway\n"
                "## 시장 현황\n"
                "## 중장기 맥락\n"
                "## 주요 지표들\n"
                "## 지켜봐야 할 것들\n"
                "## 관심을 가져볼 만한 이슈들\n"
                "## 출처·데이터 안내",
            ),
            (
                "story-shorter-marker",
                "story",
                "storyMarkdown",
                "````json\n"
                "untrusted code\n"
                "```\n"
                "# 현재 판단\n"
                "## 전파 경로\n"
                "## 강화 근거\n"
                "## 반대 근거와 불확실성\n"
                "## 무효화 조건\n"
                "## 다음 확인점\n"
                "## 관련 Story",
            ),
            (
                "change-tilde-trailing-text",
                "change",
                "changeMarkdown",
                "~~~~style\n"
                "untrusted code\n"
                "~~~~not-a-valid-closing-fence\n"
                "# 무엇이 바뀌었나\n"
                "## 왜 바뀌었나\n"
                "## 시장에 미치는 의미\n"
                "## 다음 확인점",
            ),
            (
                "different-marker-character",
                "change",
                "changeMarkdown",
                "~~~style\n"
                "untrusted code\n"
                "```\n"
                "# 무엇이 바뀌었나\n"
                "## 왜 바뀌었나\n"
                "## 시장에 미치는 의미\n"
                "## 다음 확인점",
            ),
        )

        for name, owner, field, markdown in cases:
            with self.subTest(name=name):
                broken = copy.deepcopy(VALID)
                target = (
                    broken["report"]
                    if owner == "report"
                    else broken["storyDecisions"][0]
                )
                target[field] = markdown
                with self.assertRaisesRegex(ValueError, field):
                    validate_llm_plan(
                        broken,
                        known_story_locators={STORY_ID},
                        evidence_item_ids={"item-1"},
                        expected_report_type="world-memory",
                    )

    def test_accepts_commonmark_fences_and_headings_at_three_space_indentation(self) -> None:
        cases = (
            (
                "report",
                "markdown",
                "   ```python\n"
                "   # ignored code heading\n"
                "   ````  \t\n"
                + "\n".join("   " + line for line in REPORT_MARKDOWN.splitlines()),
            ),
            (
                "story",
                "storyMarkdown",
                "   ~~~~text\n"
                "   # ignored code heading\n"
                "   ~~~~~\t\n"
                + "\n".join("   " + line for line in STORY_MARKDOWN.splitlines()),
            ),
            (
                "change",
                "changeMarkdown",
                "   ````markdown\n"
                "   # ignored code heading\n"
                "   ````\n"
                + "\n".join("   " + line for line in CHANGE_MARKDOWN.splitlines()),
            ),
        )

        for owner, field, markdown in cases:
            with self.subTest(owner=owner):
                plan = copy.deepcopy(VALID)
                target = (
                    plan["report"]
                    if owner == "report"
                    else plan["storyDecisions"][0]
                )
                target[field] = markdown
                result = validate_llm_plan(
                    plan,
                    known_story_locators={STORY_ID},
                    evidence_item_ids={"item-1"},
                    expected_report_type="world-memory",
                )
                self.assertEqual(
                    (
                        result["report"]
                        if owner == "report"
                        else result["storyDecisions"][0]
                    )[field],
                    markdown,
                )

    def test_accepts_high_importance_cluster_without_a_story_decision(self) -> None:
        plan = copy.deepcopy(VALID)
        plan["storyDecisions"] = []
        plan["evidenceClusters"][0]["storyLocators"] = []

        result = validate_llm_plan(
            plan,
            known_story_locators={STORY_ID},
            evidence_item_ids={"item-1"},
            expected_report_type="world-memory",
        )

        self.assertEqual(result["storyDecisions"], [])
        self.assertEqual(result["evidenceClusters"][0]["storyLocators"], [])

    def test_clusters_require_exact_keys_unique_nonempty_ids_and_closed_importance(self) -> None:
        cases = []

        missing_key = copy.deepcopy(VALID)
        del missing_key["evidenceClusters"][0]["storyLocators"]
        cases.append((r"evidenceClusters\[0\] has missing required keys", missing_key))

        extra_key = copy.deepcopy(VALID)
        extra_key["evidenceClusters"][0]["semanticLabel"] = "untrusted"
        cases.append((r"evidenceClusters\[0\] has unexpected keys", extra_key))

        empty_id = copy.deepcopy(VALID)
        empty_id["evidenceClusters"][0]["clusterId"] = "   "
        cases.append(("clusterId.*must not be empty", empty_id))

        duplicate_id = copy.deepcopy(VALID)
        duplicate_id["evidenceClusters"][0]["evidenceItemIds"] = ["item-1"]
        second_cluster = copy.deepcopy(duplicate_id["evidenceClusters"][0])
        second_cluster["evidenceItemIds"] = ["item-2"]
        second_cluster["storyLocators"] = []
        duplicate_id["evidenceClusters"].append(second_cluster)
        cases.append(("duplicate clusterId", duplicate_id))

        bad_importance = copy.deepcopy(VALID)
        bad_importance["evidenceClusters"][0]["importance"] = "critical"
        cases.append(("importance.*one of", bad_importance))

        for error, broken in cases:
            with self.subTest(error=error):
                evidence_ids = (
                    {"item-1", "item-2"}
                    if len(broken["evidenceClusters"]) == 2
                    else {"item-1"}
                )
                with self.assertRaisesRegex(ValueError, error):
                    validate_llm_plan(
                        broken,
                        known_story_locators={STORY_ID},
                        evidence_item_ids=evidence_ids,
                        expected_report_type="world-memory",
                    )

    def test_clusters_require_known_bindings_and_closed_report_sections(self) -> None:
        broken = copy.deepcopy(VALID)
        broken["evidenceClusters"][0]["evidenceItemIds"] = ["unknown-evidence"]
        broken["evidenceClusters"][0]["storyLocators"] = ["unknown-story"]
        broken["evidenceClusters"][0]["reportSections"] = ["story-debug"]

        with self.assertRaisesRegex(
            ValueError,
            "evidenceItemIds.*known.*reportSections.*one of.*storyLocators.*known",
        ):
            validate_llm_plan(
                broken,
                known_story_locators={STORY_ID},
                evidence_item_ids={"item-1"},
                expected_report_type="world-memory",
            )

    def test_clusters_require_unique_members_and_exactly_once_evidence_coverage(self) -> None:
        duplicate_members = copy.deepcopy(VALID)
        duplicate_members["evidenceClusters"][0]["evidenceItemIds"] = [
            "item-1",
            "item-1",
        ]
        duplicate_members["evidenceClusters"][0]["reportSections"] = [
            "market-status",
            "market-status",
        ]
        duplicate_members["evidenceClusters"][0]["storyLocators"] = [
            STORY_ID,
            STORY_ID,
        ]
        with self.assertRaisesRegex(ValueError, "unique"):
            validate_llm_plan(
                duplicate_members,
                known_story_locators={STORY_ID},
                evidence_item_ids={"item-1"},
                expected_report_type="world-memory",
            )

        duplicate_across_clusters = copy.deepcopy(VALID)
        duplicate_across_clusters["evidenceClusters"][0]["importance"] = "medium"
        second_cluster = {
            "clusterId": "cluster-2",
            "importance": "low",
            "evidenceItemIds": ["item-1"],
            "reportSections": ["sources-and-data"],
            "storyLocators": [],
        }
        duplicate_across_clusters["evidenceClusters"].append(second_cluster)
        with self.assertRaisesRegex(ValueError, "exactly once"):
            validate_llm_plan(
                duplicate_across_clusters,
                known_story_locators={STORY_ID},
                evidence_item_ids={"item-1", "item-2"},
                expected_report_type="world-memory",
            )

        missing_evidence = copy.deepcopy(VALID)
        with self.assertRaisesRegex(ValueError, "cover every evidence item exactly once"):
            validate_llm_plan(
                missing_evidence,
                known_story_locators={STORY_ID},
                evidence_item_ids={"item-1", "item-2"},
                expected_report_type="world-memory",
            )

    def test_every_cluster_has_report_coverage_and_high_cluster_cannot_be_empty(self) -> None:
        for importance in ("high", "medium", "low"):
            with self.subTest(importance=importance):
                broken = copy.deepcopy(VALID)
                broken["evidenceClusters"][0]["importance"] = importance
                broken["evidenceClusters"][0]["reportSections"] = []
                expected_error = (
                    "high-importance.*Report section"
                    if importance == "high"
                    else "reportSections.*must not be empty"
                )
                with self.assertRaisesRegex(ValueError, expected_error):
                    validate_llm_plan(
                        broken,
                        known_story_locators={STORY_ID},
                        evidence_item_ids={"item-1"},
                        expected_report_type="world-memory",
                    )

    def test_rejects_unknown_story_and_evidence(self) -> None:
        broken = copy.deepcopy(VALID)
        broken["storyDecisions"][0]["storyLocator"] = "unknown"
        broken["storyDecisions"][0]["evidenceItemIds"] = ["missing"]
        with self.assertRaisesRegex(ValueError, "storyLocator.*evidenceItemIds"):
            validate_llm_plan(
                broken,
                known_story_locators={STORY_ID},
                evidence_item_ids={"item-1"},
                expected_report_type="world-memory",
            )

    def test_rejects_extra_keys(self) -> None:
        broken = copy.deepcopy(VALID)
        broken["report"]["rawConnectorResponse"] = {"token": "no"}
        with self.assertRaisesRegex(ValueError, "report has unexpected keys"):
            validate_llm_plan(
                broken,
                known_story_locators={STORY_ID},
                evidence_item_ids={"item-1"},
                expected_report_type="world-memory",
            )

    def test_rejects_non_string_dict_keys_with_a_stable_error(self) -> None:
        with self.assertRaisesRegex(ValueError, "plan has non-string keys"):
            validate_llm_plan(
                {0: "untrusted"},
                known_story_locators={STORY_ID},
                evidence_item_ids={"item-1"},
                expected_report_type="world-memory",
            )

    def test_rejects_bool_instead_of_string_or_list_value(self) -> None:
        broken = copy.deepcopy(VALID)
        broken["report"]["markdown"] = True
        broken["storyDecisions"][0]["regions"] = True
        with self.assertRaisesRegex(ValueError, "markdown.*regions"):
            validate_llm_plan(
                broken,
                known_story_locators={STORY_ID},
                evidence_item_ids={"item-1"},
                expected_report_type="world-memory",
            )

    def test_rejects_empty_markdown(self) -> None:
        broken = copy.deepcopy(VALID)
        broken["report"]["markdown"] = "   \n"
        broken["storyDecisions"][0]["storyMarkdown"] = ""
        broken["storyDecisions"][0]["changeMarkdown"] = "\t"
        with self.assertRaisesRegex(ValueError, "markdown.*storyMarkdown.*changeMarkdown"):
            validate_llm_plan(
                broken,
                known_story_locators={STORY_ID},
                evidence_item_ids={"item-1"},
                expected_report_type="world-memory",
            )

    def test_rejects_duplicate_decisions_for_one_story(self) -> None:
        broken = copy.deepcopy(VALID)
        broken["storyDecisions"].append(copy.deepcopy(broken["storyDecisions"][0]))
        with self.assertRaisesRegex(ValueError, "duplicate.*storyLocator"):
            validate_llm_plan(
                broken,
                known_story_locators={STORY_ID},
                evidence_item_ids={"item-1"},
                expected_report_type="world-memory",
            )

    def test_rejects_relationship_change_without_known_related_story(self) -> None:
        broken = copy.deepcopy(VALID)
        broken["storyDecisions"][0]["changeType"] = "relationship-changed"
        with self.assertRaisesRegex(ValueError, "relationship-changed.*relatedStoryLocators"):
            validate_llm_plan(
                broken,
                known_story_locators={STORY_ID},
                evidence_item_ids={"item-1"},
                expected_report_type="world-memory",
            )

    def test_rejects_scheduled_merge_or_split_action(self) -> None:
        for action in ("merge", "split"):
            with self.subTest(action=action):
                broken = copy.deepcopy(VALID)
                broken["storyDecisions"][0]["action"] = action
                with self.assertRaisesRegex(ValueError, "action"):
                    validate_llm_plan(
                        broken,
                        known_story_locators={STORY_ID},
                        evidence_item_ids={"item-1"},
                        expected_report_type="world-memory",
                    )

    def test_rejects_report_type_mismatch(self) -> None:
        with self.assertRaisesRegex(ValueError, "report.type"):
            validate_llm_plan(
                VALID,
                known_story_locators={STORY_ID},
                evidence_item_ids={"item-1"},
                expected_report_type="briefing",
            )

    def test_create_requires_empty_locator_and_update_requires_known_locator(self) -> None:
        create = copy.deepcopy(VALID)
        create["storyDecisions"][0]["action"] = "create"
        create["storyDecisions"][0]["storyLocator"] = STORY_ID
        update = copy.deepcopy(VALID)
        update["storyDecisions"][0]["storyLocator"] = ""
        for broken in (create, update):
            with self.assertRaisesRegex(ValueError, "storyLocator"):
                validate_llm_plan(
                    broken,
                    known_story_locators={STORY_ID},
                    evidence_item_ids={"item-1"},
                    expected_report_type="world-memory",
                )

    def test_update_rejects_empty_locator_even_if_context_contains_empty(self) -> None:
        broken = copy.deepcopy(VALID)
        broken["storyDecisions"][0]["storyLocator"] = ""

        with self.assertRaisesRegex(ValueError, "storyLocator.*nonempty"):
            validate_llm_plan(
                broken,
                known_story_locators={"", STORY_ID},
                evidence_item_ids={"item-1"},
                expected_report_type="world-memory",
            )

    def test_story_content_rejects_a_page_title_before_the_fixed_first_heading(self) -> None:
        cases = (
            ("story", "storyMarkdown", "# Existing Story · duplicate\n\n" + STORY_MARKDOWN),
            ("story", "changeMarkdown", "# Existing Story Change\n\n" + CHANGE_MARKDOWN),
        )
        for owner, field, markdown in cases:
            with self.subTest(owner=owner, field=field):
                broken = copy.deepcopy(VALID)
                target = broken["report"] if owner == "report" else broken["storyDecisions"][0]
                target[field] = markdown
                with self.assertRaisesRegex(ValueError, f"{field}.*first heading"):
                    validate_llm_plan(
                        broken,
                        known_story_locators={STORY_ID},
                        evidence_item_ids={"item-1"},
                        expected_report_type="world-memory",
                    )

    def test_rejects_late_or_duplicated_h1_across_all_content_types(self) -> None:
        cases = (
            (
                "report",
                "markdown",
                REPORT_MARKDOWN,
                "# 🌍 변동성은 낮지만 경계는 남아 있다",
            ),
            ("story", "storyMarkdown", STORY_MARKDOWN, "# 현재 판단"),
            ("story", "changeMarkdown", CHANGE_MARKDOWN, "# 무엇이 바뀌었나"),
        )
        for owner, field, markdown, required_h1 in cases:
            for appended_h1 in ("# 뒤늦은 제목", required_h1):
                with self.subTest(
                    owner=owner, field=field, appended_h1=appended_h1
                ):
                    broken = copy.deepcopy(VALID)
                    target = (
                        broken["report"]
                        if owner == "report"
                        else broken["storyDecisions"][0]
                    )
                    target[field] = f"{markdown}\n\n{appended_h1}\n\n중복 본문"
                    with self.assertRaisesRegex(
                        ValueError, f"{field}.*exactly one H1"
                    ):
                        validate_llm_plan(
                            broken,
                            known_story_locators={STORY_ID},
                            evidence_item_ids={"item-1"},
                            expected_report_type="world-memory",
                        )

    def test_rejects_missing_or_out_of_order_required_markdown_sections(self) -> None:
        cases = (
            (
                "report",
                "markdown",
                REPORT_MARKDOWN.replace("## 출처·데이터 안내\n\n없음.", ""),
            ),
            (
                "story",
                "storyMarkdown",
                STORY_MARKDOWN.replace(
                    "## 전파 경로\n\n전파 경로.\n\n## 강화 근거",
                    "## 강화 근거\n\n- 근거\n\n## 전파 경로",
                ),
            ),
            (
                "story",
                "changeMarkdown",
                CHANGE_MARKDOWN.replace("## 시장에 미치는 의미\n\n시장 의미.\n\n", ""),
            ),
        )
        for owner, field, markdown in cases:
            with self.subTest(owner=owner, field=field):
                broken = copy.deepcopy(VALID)
                target = broken["report"] if owner == "report" else broken["storyDecisions"][0]
                target[field] = markdown
                with self.assertRaisesRegex(ValueError, f"{field}.*sections.*order"):
                    validate_llm_plan(
                        broken,
                        known_story_locators={STORY_ID},
                        evidence_item_ids={"item-1"},
                        expected_report_type="world-memory",
                    )


class LlmPlanRepairTests(unittest.TestCase):
    def test_repairs_once_then_accepts(self) -> None:
        responses = iter(({"bad": True}, VALID))
        result = run_plan_with_repair(
            lambda payload: next(responses),
            input_payload=INPUT,
            validation_context=CTX,
        )
        self.assertEqual(result.status, "accepted")
        self.assertEqual(result.attempts, 2)
        self.assertEqual(result.plan, VALID)
        self.assertEqual(result.errors, ())

    def test_never_calls_generator_more_than_twice(self) -> None:
        calls: list[dict[str, object]] = []
        result = run_plan_with_repair(
            lambda payload: calls.append(payload) or {"bad": True},
            input_payload=INPUT,
            validation_context=CTX,
        )
        self.assertEqual(result.status, "invalid")
        self.assertEqual(len(calls), 2)
        self.assertEqual(result.attempts, 2)
        self.assertIsNone(result.plan)
        self.assertNotEqual(result.errors, ())

    def test_repair_input_is_limited_to_evidence_and_validation_errors(self) -> None:
        calls: list[dict[str, object]] = []
        result = run_plan_with_repair(
            lambda payload: calls.append(payload) or {"bad": True},
            input_payload=INPUT,
            validation_context=CTX,
        )
        self.assertEqual(result.status, "invalid")
        self.assertEqual(set(calls[1]), {"evidence", "validationErrors"})
        self.assertEqual(calls[1]["evidence"], INPUT["evidence"])
        self.assertTrue(calls[1]["validationErrors"])
        serialized_repair = repr(calls[1])
        self.assertNotIn("should-not-be-replayed", serialized_repair)
        self.assertNotIn("must-not-be-replayed", serialized_repair)

    def test_repair_input_drops_nested_raw_connector_payload(self) -> None:
        calls: list[dict[str, object]] = []
        input_with_nested_connector = copy.deepcopy(INPUT)
        input_with_nested_connector["evidence"][0]["connector"] = {
            "cookie": "also-must-not-be-replayed"
        }
        run_plan_with_repair(
            lambda payload: calls.append(payload) or {"bad": True},
            input_payload=input_with_nested_connector,
            validation_context=CTX,
        )
        self.assertNotIn("connector", calls[1]["evidence"][0])
        self.assertNotIn("also-must-not-be-replayed", repr(calls[1]))

    def test_repair_errors_do_not_replay_story_locator_values(self) -> None:
        calls: list[dict[str, object]] = []
        duplicated_locator = "credential-shaped-locator"
        invalid = copy.deepcopy(VALID)
        invalid["storyDecisions"][0]["storyLocator"] = duplicated_locator
        invalid["storyDecisions"].append(copy.deepcopy(invalid["storyDecisions"][0]))
        context = ValidationContext(
            known_story_locators=frozenset({duplicated_locator}),
            evidence_item_ids=frozenset({"item-1"}),
            expected_report_type="world-memory",
        )
        run_plan_with_repair(
            lambda payload: calls.append(payload) or invalid,
            input_payload=INPUT,
            validation_context=context,
        )
        self.assertNotIn(duplicated_locator, repr(calls[1]["validationErrors"]))

    def test_repair_errors_do_not_replay_unexpected_key_text_or_value(self) -> None:
        calls: list[dict[str, object]] = []
        secret_key = "credential-shaped-unexpected-key"
        secret_value = "credential-shaped-unexpected-value"
        result = run_plan_with_repair(
            lambda payload: calls.append(payload) or {secret_key: secret_value},
            input_payload=INPUT,
            validation_context=CTX,
        )
        self.assertEqual(result.status, "invalid")
        self.assertEqual(result.attempts, 2)
        self.assertNotIn(secret_key, repr(calls[1]["validationErrors"]))
        self.assertNotIn(secret_value, repr(calls[1]["validationErrors"]))

    def test_repair_errors_do_not_replay_cluster_ids_or_unknown_binding_values(self) -> None:
        calls: list[dict[str, object]] = []
        secret_cluster = "credential-shaped-cluster-id"
        secret_evidence = "credential-shaped-evidence-id"
        secret_story = "credential-shaped-story-id"
        invalid = copy.deepcopy(VALID)
        invalid["evidenceClusters"][0]["clusterId"] = secret_cluster
        invalid["evidenceClusters"][0]["evidenceItemIds"] = [secret_evidence]
        invalid["evidenceClusters"][0]["storyLocators"] = [secret_story]

        result = run_plan_with_repair(
            lambda payload: calls.append(payload) or invalid,
            input_payload=INPUT,
            validation_context=CTX,
        )

        self.assertEqual(result.status, "invalid")
        self.assertEqual(result.attempts, 2)
        serialized_errors = repr(calls[1]["validationErrors"])
        self.assertNotIn(secret_cluster, serialized_errors)
        self.assertNotIn(secret_evidence, serialized_errors)
        self.assertNotIn(secret_story, serialized_errors)

    def test_non_string_key_plan_is_bounded_to_one_repair(self) -> None:
        calls: list[dict[str, object]] = []
        result = run_plan_with_repair(
            lambda payload: calls.append(payload) or {0: "untrusted"},
            input_payload=INPUT,
            validation_context=CTX,
        )
        self.assertEqual(result.status, "invalid")
        self.assertEqual(result.attempts, 2)
        self.assertEqual(len(calls), 2)
        self.assertEqual(result.errors, ("plan has non-string keys",))

    def test_plan_attempt_is_immutable_result_record(self) -> None:
        accepted = PlanAttempt("accepted", copy.deepcopy(VALID), (), 1)
        self.assertEqual(accepted.status, "accepted")
        with self.assertRaises(AttributeError):
            accepted.status = "invalid"


if __name__ == "__main__":
    unittest.main()
