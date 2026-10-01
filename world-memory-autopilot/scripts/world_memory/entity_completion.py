"""Pure required-review and completion checks; no connector or persistent ledger."""

from .extensions import POLICY, ROLES
from .llm_plan import validate_llm_plan
from .registry import normalize_uuid


def _keys(value, expected, label):
    if type(value) is not dict or set(value) != set(expected):
        raise ValueError(f"invalid {label} fields")


def _strings(value):
    if type(value) is not list or any(type(v) is not str or not v.strip() for v in value):
        raise ValueError("expected nonempty strings")
    if len(value) != len(set(value)):
        raise ValueError("duplicate strings")
    return value


def review_required(context):
    """Derive the obligation from the observed policy/readiness, never a default."""
    _keys(context, {"policy", "readiness", "reason"}, "entity context")
    if context["policy"] not in (POLICY, "disabled"):
        raise ValueError("invalid entity policy")
    if context["readiness"] not in ("ready", "disabled", "unavailable", "incomplete"):
        raise ValueError("invalid entity readiness")
    if (context["policy"] == "disabled") != (context["readiness"] == "disabled"):
        raise ValueError("inconsistent entity context")
    if type(context["reason"]) is not str:
        raise ValueError("invalid entity context reason")
    if context["readiness"] != "ready" and not context["reason"].strip():
        raise ValueError("inactive entity review needs a reason")
    return context["policy"] == POLICY and context["readiness"] == "ready"


def validate_plan_request(value):
    """Public plan boundary: missing context and old optional flags fail closed."""
    fields = {"candidate", "knownStoryIds", "evidenceItemIds", "expectedReportType",
              "entityContext"}
    _keys(value, fields, "plan request")
    required = review_required(value["entityContext"])
    stories = {normalize_uuid(v, "knownStoryIds") for v in _strings(value["knownStoryIds"])}
    evidence = set(_strings(value["evidenceItemIds"]))
    candidate = value["candidate"]
    if not required and type(candidate) is dict:
        if "entityPlan" in candidate or "entityReview" in candidate:
            raise ValueError("inactive extension cannot plan entities")
    plan = validate_llm_plan(
        candidate, known_story_locators=stories, evidence_item_ids=evidence,
        expected_report_type=value["expectedReportType"],
        entity_review_required=required,
    )
    if value["entityContext"]["readiness"] in ("unavailable", "incomplete"):
        if value["entityContext"]["reason"] not in plan["report"]["dataGaps"]:
            raise ValueError("extension failure requires its exact report gap")
    return plan


def complete_entity_review(value):
    """Account for every reviewed proposal using caller-observed write outcomes.

    A missing outcome degrades completion rather than disappearing into a zero
    count. Confirmed IDs are caller-supplied connector evidence, not proof of I/O.
    """
    _keys(value, {"validation", "outcomes", "linkGaps"}, "entity completion")
    plan = validate_plan_request(value["validation"])
    context = value["validation"]["entityContext"]
    required = review_required(context)
    outcomes = value["outcomes"]
    if type(outcomes) is not list or len(outcomes) > 150:
        raise ValueError("invalid entity outcomes")
    gaps = list(_strings(value["linkGaps"]))
    result = {"status": "completed", "reviewedClusters": 0,
              "notApplicableClusters": 0, "deferredClusters": 0,
              "counts": {role: {s: 0 for s in
                  ("created", "updated", "unchanged", "deferred", "failed", "missing")}
                  for role in ROLES}, "warnings": gaps}
    if not required:
        if outcomes or gaps:
            raise ValueError("inactive or failed review cannot have entity outcomes")
        result["status"] = "disabled" if context["readiness"] == "disabled" else "degraded"
        result["reason"] = context["reason"]
        if result["status"] == "degraded":
            result["warnings"].append(result["reason"])
        return result

    review = plan["entityReview"]
    result["reviewedClusters"] = len(review)
    for row in review:
        if row["disposition"] == "not-applicable":
            result["notApplicableClusters"] += 1
        elif row["disposition"] == "deferred":
            result["deferredClusters"] += 1
            gaps.append(row["reason"])
    proposals = {(role, row["key"]) for role in ROLES for row in plan["entityPlan"][role]}
    seen = set()
    for row in outcomes:
        _keys(row, {"role", "key", "status", "pageId", "reason"}, "entity outcome")
        if type(row["role"]) is not str or type(row["key"]) is not str:
            raise ValueError("invalid entity outcome identity")
        identity = (row["role"], row["key"])
        if identity not in proposals or identity in seen:
            raise ValueError("unknown or duplicate entity outcome")
        seen.add(identity)
        status = row["status"]
        if status not in ("created", "updated", "unchanged", "deferred", "failed"):
            raise ValueError("invalid entity outcome status")
        if type(row["reason"]) is not str or not row["reason"].strip():
            raise ValueError("entity outcome needs a reason")
        if status in ("created", "updated", "unchanged"):
            normalize_uuid(row["pageId"], "confirmed entity page")
        elif row["pageId"] is not None:
            normalize_uuid(row["pageId"], "known entity page")
        result["counts"][row["role"]][status] += 1
        if status in ("deferred", "failed"):
            gaps.append(f"{row['role']}: {row['reason']}")
    for role, key in sorted(proposals - seen):
        result["counts"][role]["missing"] += 1
        gaps.append(f"{role}: planned entity outcome missing")
    if gaps:
        result["status"] = "degraded"
    elif not proposals:
        result["status"] = "no-change"
    result["warnings"] = list(dict.fromkeys(gaps))
    return result
