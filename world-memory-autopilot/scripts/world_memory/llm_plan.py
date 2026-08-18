"""Validate ephemeral structured plans returned by an injected LLM boundary.

This module deliberately has no persistence, connector, or LLM-client code.
The Workspace Agent supplies structured candidate/evidence input and owns any
model invocation.  A returned control object is accepted only after exact
shape and binding validation; it is then copied for the caller's temporary
use.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Callable

from .notion_layout import DATABASE_SCHEMAS


def _schema_options(database: str, property_name: str) -> tuple[str, ...]:
    properties = DATABASE_SCHEMAS[database]["properties"]
    descriptor = properties[property_name]
    return tuple(descriptor["options"])


# Keep shared controlled vocabularies anchored to the static logical schema.
# notion_layout is intentionally connector-neutral and does not import this
# module, so this remains a one-way, cycle-free dependency.
CHANGE_TYPES = _schema_options("storyChanges", "Change Type")
DIRECTIONS = _schema_options("storyChanges", "Direction")
LEVELS = _schema_options("stories", "Importance")
REPORT_TYPES = _schema_options("reports", "Report Type")

_STATUSES = _schema_options("stories", "Status")
_CATEGORIES = _schema_options("stories", "Category")
_REGIONS = _schema_options("stories", "Regions")
_STANCES = _schema_options("reports", "Stance")
_DATA_QUALITIES = _schema_options("reports", "Data Quality")
REPORT_SECTION_IDS = (
    "key-takeaway",
    "market-status",
    "medium-term-context",
    "key-indicators",
    "watch-items",
    "issues-of-interest",
    "sources-and-data",
)
_REPORT_MARKDOWN_H2S = (
    "## Key Takeaway",
    "## 시장 현황",
    "## 중장기 맥락",
    "## 주요 지표들",
    "## 지켜봐야 할 것들",
    "## 관심을 가져볼 만한 이슈들",
    "## 출처·데이터 안내",
)
_STORY_MARKDOWN_SECTIONS = (
    "# 현재 판단",
    "## 전파 경로",
    "## 강화 근거",
    "## 반대 근거와 불확실성",
    "## 무효화 조건",
    "## 다음 확인점",
    "## 관련 Story",
)
_CHANGE_MARKDOWN_SECTIONS = (
    "# 무엇이 바뀌었나",
    "## 왜 바뀌었나",
    "## 시장에 미치는 의미",
    "## 다음 확인점",
)

_TOP_LEVEL_KEYS = frozenset({"report", "storyDecisions", "evidenceClusters"})
_REPORT_KEYS = frozenset(
    {"type", "stance", "confidence", "dataQuality", "dataGaps", "markdown"}
)
_DECISION_KEYS = frozenset(
    {
        "action",
        "storyLocator",
        "name",
        "status",
        "category",
        "regions",
        "changeType",
        "direction",
        "importance",
        "confidence",
        "currentView",
        "storyMarkdown",
        "changeMarkdown",
        "relatedStoryLocators",
        "evidenceItemIds",
    }
)
_CLUSTER_KEYS = frozenset(
    {
        "clusterId",
        "importance",
        "evidenceItemIds",
        "reportSections",
        "storyLocators",
    }
)
_SENSITIVE_KEY_PARTS = frozenset(
    {
        "authorization",
        "credential",
        "secret",
        "token",
        "password",
        "cookie",
        "apikey",
        "api_key",
        "connector",
        "connectorpayload",
        "connector_payload",
        "rawpayload",
        "raw_payload",
    }
)


@dataclass(frozen=True)
class ValidationContext:
    """Known bindings that a plan is allowed to reference for one invocation."""

    known_story_locators: frozenset[str]
    evidence_item_ids: frozenset[str]
    expected_report_type: str


@dataclass(frozen=True)
class PlanAttempt:
    """The bounded outcome of generating and validating one temporary plan."""

    status: str
    plan: dict[str, object] | None
    errors: tuple[str, ...]
    attempts: int


def _is_string(value: object) -> bool:
    return type(value) is str


def _add_exact_keys(
    value: object, *, expected: frozenset[str], label: str, errors: list[str]
) -> dict[str, object] | None:
    if type(value) is not dict:
        errors.append(f"{label} must be an object")
        return None
    if any(not _is_string(key) for key in value):
        errors.append(f"{label} has non-string keys")
        return None
    actual = set(value)
    missing = expected - actual
    extra = actual - expected
    if missing:
        errors.append(f"{label} has missing required keys")
    if extra:
        errors.append(f"{label} has unexpected keys")
    return value


def _required_string(
    mapping: dict[str, object], key: str, *, label: str, errors: list[str], nonempty: bool = False
) -> str | None:
    value = mapping.get(key)
    if not _is_string(value):
        errors.append(f"{label}.{key} must be a string")
        return None
    if nonempty and not value.strip():
        errors.append(f"{label}.{key} must not be empty")
    return value


def _required_markdown(
    mapping: dict[str, object],
    key: str,
    *,
    label: str,
    required_sections: tuple[str, ...],
    errors: list[str],
) -> str | None:
    value = _required_string(
        mapping, key, label=label, errors=errors, nonempty=True
    )
    if value is None or not value.strip():
        return value
    field_label = f"{label}.{key}"
    headings = _markdown_headings(value)
    if not headings or headings[0] != required_sections[0]:
        errors.append(
            f"{field_label} first heading must be {required_sections[0]}"
        )
        return value
    h1_headings = tuple(
        heading
        for heading in headings
        if heading.startswith("# ") and not heading.startswith("## ")
    )
    if len(h1_headings) != 1:
        errors.append(f"{field_label} must contain exactly one H1 heading")
        return value

    cursor = -1
    for required in required_sections:
        try:
            cursor = headings.index(required, cursor + 1)
        except ValueError:
            errors.append(
                f"{field_label} required sections must appear in order"
            )
            break
    return value


def _required_report_markdown(
    mapping: dict[str, object],
    key: str,
    *,
    label: str,
    report_type: str | None,
    errors: list[str],
) -> str | None:
    value = _required_string(
        mapping, key, label=label, errors=errors, nonempty=True
    )
    if value is None or not value.strip():
        return value

    field_label = f"{label}.{key}"
    headings = _markdown_headings(value)
    h1_headings = tuple(
        heading
        for heading in headings
        if heading.startswith("# ") and not heading.startswith("## ")
    )
    if not headings or headings[0] not in h1_headings:
        errors.append(f"{field_label} first heading must be one nonempty H1")
    if len(h1_headings) != 1:
        errors.append(f"{field_label} must contain exactly one H1 heading")

    h2_headings = tuple(
        heading
        for heading in headings
        if heading.startswith("## ") and not heading.startswith("### ")
    )
    if h2_headings != _REPORT_MARKDOWN_H2S:
        errors.append(
            f"{field_label} must contain the approved H2 sections exactly once and in order"
        )
    elif report_type in REPORT_TYPES:
        sections = _report_section_lines(value)
        _validate_key_takeaway(
            sections["## Key Takeaway"], field_label=field_label, errors=errors
        )
        minimum = 2 if report_type == "briefing" else 3
        for heading in ("## 시장 현황", "## 중장기 맥락"):
            _validate_narrative_section(
                sections[heading],
                heading=heading,
                report_type=report_type,
                minimum=minimum,
                field_label=field_label,
                errors=errors,
            )
    return value


def _report_section_lines(value: str) -> dict[str, tuple[str, ...]]:
    """Return visible block-level lines for each approved Report H2 section."""

    sections: dict[str, list[str]] = {
        heading: [] for heading in _REPORT_MARKDOWN_H2S
    }
    current: str | None = None
    fence: tuple[str, int] | None = None

    for line in value.splitlines():
        content = _markdown_block_content(line)
        if content is None:
            if current is not None and sections[current] and sections[current][-1] != "":
                sections[current].append("")
            continue

        if fence is not None:
            candidate = _fence_run(content)
            if (
                candidate is not None
                and candidate[0] == fence[0]
                and candidate[1] >= fence[1]
                and not candidate[2].strip(" \t")
            ):
                fence = None
                if current is not None and sections[current] and sections[current][-1] != "":
                    sections[current].append("")
            continue

        candidate = _fence_run(content)
        if candidate is not None and not (
            candidate[0] == "`" and "`" in candidate[2]
        ):
            fence = candidate[0], candidate[1]
            if current is not None and sections[current] and sections[current][-1] != "":
                sections[current].append("")
            continue

        heading = content.rstrip()
        if heading in sections:
            current = heading
            continue
        if current is not None:
            sections[current].append(content.rstrip())

    return {heading: tuple(lines) for heading, lines in sections.items()}


def _markdown_list_item(line: str) -> tuple[str, str] | None:
    """Classify one visible CommonMark block-level list marker."""

    if len(line) >= 2 and line[0] in "-+*" and line[1] in " \t":
        return "unordered", line[2:].strip()

    index = 0
    while index < len(line) and line[index].isdigit():
        index += 1
    if (
        1 <= index <= 9
        and index + 1 < len(line)
        and line[index] in ".)"
        and line[index + 1] in " \t"
    ):
        return "ordered", line[index + 2 :].strip()
    return None


def _validate_key_takeaway(
    lines: tuple[str, ...], *, field_label: str, errors: list[str]
) -> None:
    visible = [line for line in lines if line.strip()]
    items = [_markdown_list_item(line) for line in visible]
    if (
        not 3 <= len(items) <= 5
        or any(item is None or item[0] != "unordered" or not item[1] for item in items)
    ):
        errors.append(
            f"{field_label} Key Takeaway must contain 3 to 5 nonempty unordered list items"
        )


def _prose_paragraph_count(lines: tuple[str, ...]) -> int:
    count = 0
    inside_paragraph = False
    for line in lines:
        if line.strip():
            if not inside_paragraph:
                count += 1
                inside_paragraph = True
        else:
            inside_paragraph = False
    return count


def _validate_narrative_section(
    lines: tuple[str, ...],
    *,
    heading: str,
    report_type: str,
    minimum: int,
    field_label: str,
    errors: list[str],
) -> None:
    section_name = heading.removeprefix("## ")
    visible = [line for line in lines if line.strip()]
    has_nonprose_block = any(
        _markdown_list_item(line) is not None or line.lstrip().startswith("#")
        for line in visible
    )
    if has_nonprose_block:
        errors.append(
            f"{field_label} {section_name} must use prose paragraphs without top-level lists or headings"
        )
        return

    paragraph_count = _prose_paragraph_count(lines)
    if paragraph_count < minimum:
        errors.append(
            f"{field_label} {section_name} must contain at least {minimum} prose paragraphs for {report_type}"
        )


def _markdown_headings(value: str) -> tuple[str, ...]:
    headings: list[str] = []
    fence: tuple[str, int] | None = None
    for line in value.splitlines():
        content = _markdown_block_content(line)
        if content is None:
            continue

        if fence is not None:
            candidate = _fence_run(content)
            if (
                candidate is not None
                and candidate[0] == fence[0]
                and candidate[1] >= fence[1]
                and not candidate[2].strip(" \t")
            ):
                fence = None
            continue

        candidate = _fence_run(content)
        if candidate is not None and not (
            candidate[0] == "`" and "`" in candidate[2]
        ):
            fence = candidate[0], candidate[1]
            continue

        heading = content.rstrip()
        prefix, separator, _ = heading.partition(" ")
        if separator and 1 <= len(prefix) <= 6 and set(prefix) == {"#"}:
            headings.append(heading)
    return tuple(headings)


def _markdown_block_content(line: str) -> str | None:
    """Return content at CommonMark block indentation, or ignore code indentation."""

    column = 0
    offset = 0
    while offset < len(line) and line[offset] in (" ", "\t"):
        if line[offset] == " ":
            column += 1
        else:
            column += 4 - (column % 4)
        offset += 1
        if column > 3:
            return None
    return line[offset:]


def _fence_run(content: str) -> tuple[str, int, str] | None:
    """Return a possible fenced-code marker character, width, and remainder."""

    if not content or content[0] not in ("`", "~"):
        return None
    marker = content[0]
    width = 0
    while width < len(content) and content[width] == marker:
        width += 1
    if width < 3:
        return None
    return marker, width, content[width:]


def _string_list(
    mapping: dict[str, object], key: str, *, label: str, errors: list[str]
) -> list[str] | None:
    value = mapping.get(key)
    if type(value) is not list:
        errors.append(f"{label}.{key} must be a list of strings")
        return None
    invalid_indexes = [str(index) for index, item in enumerate(value) if not _is_string(item)]
    if invalid_indexes:
        errors.append(
            f"{label}.{key} must contain only strings; invalid indexes: {', '.join(invalid_indexes)}"
        )
        return None
    return value


def _require_unique_strings(
    values: list[str], *, label: str, errors: list[str]
) -> None:
    if len(set(values)) != len(values):
        errors.append(f"{label} must contain unique members")


def _one_of(
    value: str | None, *, allowed: tuple[str, ...], label: str, errors: list[str]
) -> None:
    if value is not None and value not in allowed:
        errors.append(f"{label} must be one of: {', '.join(allowed)}")


def _validate_evidence_clusters(
    value: object,
    *,
    known_story_locators: set[str],
    evidence_item_ids: set[str],
    errors: list[str],
) -> None:
    if type(value) is not list:
        errors.append("evidenceClusters must be a list")
        return

    seen_cluster_ids: set[str] = set()
    covered_evidence: set[str] = set()
    for index, raw_cluster in enumerate(value):
        label = f"evidenceClusters[{index}]"
        cluster = _add_exact_keys(
            raw_cluster, expected=_CLUSTER_KEYS, label=label, errors=errors
        )
        if cluster is None:
            continue

        cluster_id = _required_string(
            cluster, "clusterId", label=label, errors=errors, nonempty=True
        )
        if cluster_id is not None and cluster_id.strip():
            if cluster_id in seen_cluster_ids:
                errors.append("duplicate clusterId in evidenceClusters")
            else:
                seen_cluster_ids.add(cluster_id)

        importance = _required_string(
            cluster, "importance", label=label, errors=errors
        )
        _one_of(
            importance,
            allowed=LEVELS,
            label=f"{label}.importance",
            errors=errors,
        )

        cluster_evidence = _string_list(
            cluster, "evidenceItemIds", label=label, errors=errors
        )
        if cluster_evidence is not None:
            _require_unique_strings(
                cluster_evidence,
                label=f"{label}.evidenceItemIds",
                errors=errors,
            )
            if not cluster_evidence:
                errors.append(f"{label}.evidenceItemIds must not be empty")
            for item_id in cluster_evidence:
                if item_id not in evidence_item_ids:
                    errors.append(
                        f"{label}.evidenceItemIds must contain known item IDs"
                    )
                elif item_id in covered_evidence:
                    errors.append(
                        "evidenceClusters must bind each evidence item exactly once"
                    )
                else:
                    covered_evidence.add(item_id)

        report_sections = _string_list(
            cluster, "reportSections", label=label, errors=errors
        )
        if report_sections is not None:
            _require_unique_strings(
                report_sections,
                label=f"{label}.reportSections",
                errors=errors,
            )
            if not report_sections:
                if importance == "high":
                    errors.append(
                        f"{label} high-importance cluster requires a Report section"
                    )
                else:
                    errors.append(f"{label}.reportSections must not be empty")
            for section_id in report_sections:
                _one_of(
                    section_id,
                    allowed=REPORT_SECTION_IDS,
                    label=f"{label}.reportSections",
                    errors=errors,
                )

        story_locators = _string_list(
            cluster, "storyLocators", label=label, errors=errors
        )
        if story_locators is not None:
            _require_unique_strings(
                story_locators,
                label=f"{label}.storyLocators",
                errors=errors,
            )
            for story_locator in story_locators:
                if story_locator not in known_story_locators:
                    errors.append(
                        f"{label}.storyLocators must contain known locators"
                    )

    if covered_evidence != evidence_item_ids:
        errors.append(
            "evidenceClusters must cover every evidence item exactly once"
        )


def validate_llm_plan(
    value: object,
    *,
    known_story_locators: set[str],
    evidence_item_ids: set[str],
    expected_report_type: str,
) -> dict[str, object]:
    """Return an independent accepted plan or raise one aggregate ``ValueError``.

    No JSON text parsing, semantic classification, persistence, or fallback
    defaulting belongs in this deterministic boundary.
    """

    errors: list[str] = []
    plan = _add_exact_keys(value, expected=_TOP_LEVEL_KEYS, label="plan", errors=errors)
    if plan is None:
        raise ValueError("; ".join(errors))

    report = _add_exact_keys(
        plan.get("report"), expected=_REPORT_KEYS, label="report", errors=errors
    )
    if report is not None:
        report_type = _required_string(report, "type", label="report", errors=errors)
        _one_of(report_type, allowed=REPORT_TYPES, label="report.type", errors=errors)
        if report_type is not None and report_type != expected_report_type:
            errors.append("report.type does not match expected_report_type")
        stance = _required_string(report, "stance", label="report", errors=errors)
        _one_of(stance, allowed=_STANCES, label="report.stance", errors=errors)
        confidence = _required_string(report, "confidence", label="report", errors=errors)
        _one_of(confidence, allowed=LEVELS, label="report.confidence", errors=errors)
        data_quality = _required_string(report, "dataQuality", label="report", errors=errors)
        _one_of(data_quality, allowed=_DATA_QUALITIES, label="report.dataQuality", errors=errors)
        _string_list(report, "dataGaps", label="report", errors=errors)
        _required_report_markdown(
            report,
            "markdown",
            label="report",
            report_type=report_type,
            errors=errors,
        )

    decisions_value = plan.get("storyDecisions")
    if type(decisions_value) is not list:
        errors.append("storyDecisions must be a list")
    else:
        seen_update_locators: set[str] = set()
        for index, raw_decision in enumerate(decisions_value):
            label = f"storyDecisions[{index}]"
            decision = _add_exact_keys(
                raw_decision, expected=_DECISION_KEYS, label=label, errors=errors
            )
            if decision is None:
                continue

            action = _required_string(decision, "action", label=label, errors=errors)
            _one_of(action, allowed=("create", "update"), label=f"{label}.action", errors=errors)
            locator = _required_string(decision, "storyLocator", label=label, errors=errors)
            if action == "create" and locator is not None and locator != "":
                errors.append(f"{label}.storyLocator must be empty for action=create")
            elif action == "update":
                if locator is not None and not locator:
                    errors.append(
                        f"{label}.storyLocator must be nonempty for action=update"
                    )
                elif locator is not None and locator not in known_story_locators:
                    errors.append(f"{label}.storyLocator must be a known locator for action=update")
                if locator and locator in seen_update_locators:
                    errors.append("duplicate storyLocator in storyDecisions")
                if locator:
                    seen_update_locators.add(locator)

            _required_string(decision, "name", label=label, errors=errors, nonempty=True)
            status = _required_string(decision, "status", label=label, errors=errors)
            _one_of(status, allowed=_STATUSES, label=f"{label}.status", errors=errors)
            category = _required_string(decision, "category", label=label, errors=errors, nonempty=True)
            _one_of(category, allowed=_CATEGORIES, label=f"{label}.category", errors=errors)
            regions = _string_list(decision, "regions", label=label, errors=errors)
            if regions is not None:
                for region in regions:
                    _one_of(region, allowed=_REGIONS, label=f"{label}.regions", errors=errors)
            change_type = _required_string(decision, "changeType", label=label, errors=errors)
            _one_of(change_type, allowed=CHANGE_TYPES, label=f"{label}.changeType", errors=errors)
            direction = _required_string(decision, "direction", label=label, errors=errors)
            _one_of(direction, allowed=DIRECTIONS, label=f"{label}.direction", errors=errors)
            importance = _required_string(decision, "importance", label=label, errors=errors)
            _one_of(importance, allowed=LEVELS, label=f"{label}.importance", errors=errors)
            decision_confidence = _required_string(decision, "confidence", label=label, errors=errors)
            _one_of(
                decision_confidence,
                allowed=LEVELS,
                label=f"{label}.confidence",
                errors=errors,
            )
            _required_string(decision, "currentView", label=label, errors=errors, nonempty=True)
            _required_markdown(
                decision,
                "storyMarkdown",
                label=label,
                required_sections=_STORY_MARKDOWN_SECTIONS,
                errors=errors,
            )
            _required_markdown(
                decision,
                "changeMarkdown",
                label=label,
                required_sections=_CHANGE_MARKDOWN_SECTIONS,
                errors=errors,
            )
            related_locators = _string_list(
                decision, "relatedStoryLocators", label=label, errors=errors
            )
            known_related_count = 0
            if related_locators is not None:
                for related_locator in related_locators:
                    if related_locator in known_story_locators:
                        known_related_count += 1
                    else:
                        errors.append(
                            f"{label}.relatedStoryLocators must contain known locators"
                        )
            if change_type == "relationship-changed" and known_related_count == 0:
                errors.append(
                    f"{label}.relationship-changed requires relatedStoryLocators with a known Story"
                )
            item_ids = _string_list(decision, "evidenceItemIds", label=label, errors=errors)
            if item_ids is not None:
                for item_id in item_ids:
                    if item_id not in evidence_item_ids:
                        errors.append(f"{label}.evidenceItemIds must contain known item IDs")

    _validate_evidence_clusters(
        plan.get("evidenceClusters"),
        known_story_locators=known_story_locators,
        evidence_item_ids=evidence_item_ids,
        errors=errors,
    )

    if errors:
        raise ValueError("; ".join(errors))
    return deepcopy(plan)


def _is_sensitive_key(key: str) -> bool:
    compact = key.replace("-", "").replace("_", "").lower()
    return any(
        sensitive.replace("_", "") in compact
        for sensitive in _SENSITIVE_KEY_PARTS
    )


def _safe_evidence_copy(value: object) -> object:
    """Copy structured evidence while dropping credential/connector payload fields."""

    if type(value) is dict:
        return {
            key: _safe_evidence_copy(item)
            for key, item in value.items()
            if _is_string(key) and not _is_sensitive_key(key)
        }
    if type(value) is list:
        return [_safe_evidence_copy(item) for item in value]
    return deepcopy(value)


def _repair_payload(input_payload: dict[str, object], errors: tuple[str, ...]) -> dict[str, object]:
    evidence = input_payload.get("evidence", [])
    return {
        "evidence": _safe_evidence_copy(evidence),
        "validationErrors": list(errors),
    }


def _attempt(
    generate: Callable[[dict[str, object]], object],
    payload: dict[str, object],
    context: ValidationContext,
) -> tuple[dict[str, object] | None, tuple[str, ...]]:
    try:
        candidate = generate(payload)
    except Exception as exc:  # Generator is an external boundary.
        return None, (f"generator_failed_{type(exc).__name__.lower()}",)
    try:
        plan = validate_llm_plan(
            candidate,
            known_story_locators=set(context.known_story_locators),
            evidence_item_ids=set(context.evidence_item_ids),
            expected_report_type=context.expected_report_type,
        )
    except ValueError as exc:
        return None, tuple(str(exc).split("; "))
    return plan, ()


def run_plan_with_repair(
    generate: Callable[[dict[str, object]], object],
    *,
    input_payload: dict[str, object],
    validation_context: ValidationContext,
) -> PlanAttempt:
    """Generate at most twice, using one evidence-only repair request on failure."""

    first_plan, first_errors = _attempt(generate, input_payload, validation_context)
    if first_plan is not None:
        return PlanAttempt("accepted", first_plan, (), 1)

    second_plan, second_errors = _attempt(
        generate,
        _repair_payload(input_payload, first_errors),
        validation_context,
    )
    if second_plan is not None:
        return PlanAttempt("accepted", second_plan, (), 2)
    return PlanAttempt("invalid", None, second_errors, 2)
