"""Bounded additive entity schema and ephemeral evidence-bound entity plans.

No I/O or persistence. The host resolves locators and executes additions through
its current official Notion MCP schema, then reads back only changed structure.
"""

from copy import deepcopy
from datetime import datetime
from .notion_layout import DATABASE_SCHEMAS
from .registry import validate_registry, normalize_uuid

POLICY = "additive-entities-v1"
ROLES = ("industries", "companies", "events")


def relation(target):
    return {"type": "relation", "target": target, "required": False}


ENTITY_SCHEMAS = {
    "industries": {
        "title": "World Memory Industries",
        "properties": {
            "Name": {"type": "title"},
            "Aliases": {"type": "rich_text"},
            "Definition": {"type": "rich_text"},
        },
    },
    "companies": {
        "title": "World Memory Companies",
        "properties": {
            "Name": {"type": "title"},
            "Aliases": {"type": "rich_text"},
            "Tickers": {"type": "rich_text"},
            "Listing Status": {
                "type": "select",
                "options": ["listed", "private", "delisted", "unconfirmed"],
            },
            "Industries": relation("industries"),
        },
    },
    "events": {
        "title": "World Memory Events",
        "properties": {
            "Name": {"type": "title"},
            "Occurred At": {"type": "date"},
            "Claim": {"type": "rich_text"},
            "Companies": relation("companies"),
            "Industries": relation("industries"),
            "Collection": relation("collections"),
            "Report": relation("reports"),
            "Stories": relation("stories"),
        },
    },
}
EXTENSION_PROPERTIES = {
    "stories": {
        "Companies": relation("companies"),
        "Industries": relation("industries"),
        "Events": relation("events"),
    },
    "storyChanges": {"Events": relation("events")},
}


def extension_plan(value):
    """Plan additions from exact fetched schema projections; never row scans.

    sources covers every registered source with {dataSourceId, properties}.
    Properties use {type, options?, target?}; target is the observed relation's
    actual data-source UUID. Omission of a registered source is unknown, not absent.
    """
    keys = {"registry", "workspaceId", "hubPageId", "policy", "sources"}
    if type(value) is not dict or set(value) != keys:
        raise ValueError("invalid extension input")
    registry = validate_registry(value["registry"])
    if value["policy"] != POLICY:
        raise ValueError("extension policy not authorized")
    if (
        normalize_uuid(value["workspaceId"], "workspaceId") != registry["workspaceId"]
        or normalize_uuid(value["hubPageId"], "hubPageId") != registry["hub"]["pageId"]
    ):
        raise ValueError("extension installation mismatch")
    bindings = {
        k: registry[k]["dataSourceId"]
        for k in ("collections", "stories", "storyChanges", "reports")
    }
    bindings.update(
        {k: v["dataSourceId"] for k, v in registry.get("entitySources", {}).items()}
    )
    sources = value["sources"]
    if type(sources) is not dict or set(sources) != set(bindings):
        raise ValueError("registered source observation missing or unregistered source")
    for role, source in sources.items():
        if (
            type(source) is not dict
            or set(source) != {"dataSourceId", "properties"}
            or normalize_uuid(source["dataSourceId"], "dataSourceId") != bindings[role]
            or type(source["properties"]) is not dict
        ):
            raise ValueError("source observation mismatch")
    actions = []
    conflicts = []
    for role, schema in DATABASE_SCHEMAS.items():
        for name, descriptor in schema["properties"].items():
            actual = sources[role]["properties"].get(name)
            if type(actual) is not dict or actual.get("type") != descriptor["type"]:
                conflicts.append(
                    {"role": role, "property": name, "reason": "core-schema-mismatch"}
                )
    # Create bases first. Relations are emitted only when both actual IDs exist.
    for role in ROLES:
        if role not in bindings:
            schema = ENTITY_SCHEMAS[role]
            actions.append(
                {
                    "operation": "create-database",
                    "role": role,
                    "parentPageId": registry["hub"]["pageId"],
                    "title": schema["title"],
                    "properties": {
                        k: deepcopy(v)
                        for k, v in schema["properties"].items()
                        if v["type"] != "relation"
                    },
                }
            )
    desired = {k: v["properties"] for k, v in ENTITY_SCHEMAS.items()}
    desired.update(EXTENSION_PROPERTIES)
    for role, properties in desired.items():
        if role not in bindings:
            continue
        additions = {}
        for name, descriptor in properties.items():
            expected = deepcopy(descriptor)
            if expected["type"] == "relation":
                if expected["target"] not in bindings:
                    continue
                expected["target"] = bindings[expected["target"]]
            actual = sources[role]["properties"].get(name)
            if actual is None:
                additions[name] = expected
            elif type(actual) is not dict or actual.get("type") != expected["type"]:
                conflicts.append(
                    {"role": role, "property": name, "reason": "type-mismatch"}
                )
            elif (
                expected["type"] == "relation"
                and actual.get("target") != expected["target"]
            ):
                conflicts.append(
                    {
                        "role": role,
                        "property": name,
                        "reason": "relation-target-mismatch",
                    }
                )
            elif expected["type"] == "select" and (
                type(actual.get("options")) is not list
                or not set(expected["options"]).issubset(actual["options"])
            ):
                conflicts.append(
                    {"role": role, "property": name, "reason": "options-mismatch"}
                )
        if additions:
            actions.append(
                {
                    "operation": "add-properties",
                    "role": role,
                    "dataSourceId": bindings[role],
                    "properties": additions,
                }
            )
    return {
        "extensionVersion": "entities-v1",
        "status": "conflict"
        if conflicts
        else ("upgrade-needed" if actions else "ready"),
        "actions": [] if conflicts else actions,
        "conflicts": conflicts,
    }


def _strings(value, *, nonempty=False):
    if (
        type(value) is not list
        or any(type(v) is not str or not v.strip() for v in value)
        or len(set(value)) != len(value)
        or (nonempty and not value)
    ):
        raise ValueError("invalid entity string list")
    return value


def validate_entity_plan(value, evidence_item_ids, *, require_company_memory=False):
    """Validate semantic proposals without resolving identities by keywords.

    Keys are invocation-local references, never durable IDs. Candidate names,
    aliases and tickers do not authorize selecting or creating a company.
    """
    if type(value) is not dict or set(value) != set(ROLES):
        raise ValueError("invalid entity plan")
    keys = {}
    fields = {
        "companies": {
            "key",
            "name",
            "aliases",
            "tickers",
            "listingStatus",
            "evidenceItemIds",
        },
        "industries": {"key", "name", "aliases", "definition", "evidenceItemIds"},
        "events": {
            "key",
            "name",
            "occurredAt",
            "claim",
            "companyKeys",
            "industryKeys",
            "evidenceItemIds",
        },
    }
    for role in ROLES:
        if type(value[role]) is not list or len(value[role]) > 50:
            raise ValueError("invalid entity batch")
        keys[role] = set()
        for row in value[role]:
            expected = fields[role]
            if role == "companies" and (require_company_memory or
                                       type(row) is dict and "memory" in row):
                expected = expected | {"memory"}
            if type(row) is not dict or set(row) != expected:
                raise ValueError("invalid entity fields")
            for name in ("key", "name"):
                if type(row[name]) is not str or not row[name].strip():
                    raise ValueError("missing entity identity")
            if row["key"] in keys[role]:
                raise ValueError("duplicate entity key")
            keys[role].add(row["key"])
            if not set(_strings(row["evidenceItemIds"], nonempty=True)).issubset(
                evidence_item_ids
            ):
                raise ValueError("unbound entity evidence")
            if role != "events":
                _strings(row["aliases"])
            if role == "companies":
                if "memory" in row:
                    memory = row["memory"]
                    if (type(memory) is not dict or
                        set(memory) != {"currentView", "change", "nextCheck"} or
                        any(type(v) is not str or not v.strip() for v in memory.values())):
                        raise ValueError("invalid company memory")
                _strings(row["tickers"])
                if (
                    row["listingStatus"]
                    not in ENTITY_SCHEMAS["companies"]["properties"]["Listing Status"][
                        "options"
                    ]
                ):
                    raise ValueError("invalid listing status")
                if any(
                    t.count(":") != 1
                    or any(not p or p.strip() != p for p in t.split(":"))
                    for t in row["tickers"]
                ):
                    raise ValueError("ticker requires exchange")
                if row["listingStatus"] == "listed" and not row["tickers"]:
                    raise ValueError("listed company needs verified ticker")
                if row["listingStatus"] == "private" and row["tickers"]:
                    raise ValueError("private company cannot have current listing")
            if role == "industries" and (
                type(row["definition"]) is not str or not row["definition"].strip()
            ):
                raise ValueError("industry definition required")
            if role == "events":
                if type(row["claim"]) is not str or not row["claim"].strip():
                    raise ValueError("event claim required")
                if row["occurredAt"] is not None:
                    if type(row["occurredAt"]) is not str:
                        raise ValueError("invalid event time")
                    parsed = datetime.fromisoformat(
                        row["occurredAt"].replace("Z", "+00:00")
                    )
                    if len(row["occurredAt"]) != 10 and parsed.tzinfo is None:
                        raise ValueError("event time requires timezone")
                if not set(_strings(row["companyKeys"])).issubset(
                    keys["companies"]
                ) or not set(_strings(row["industryKeys"])).issubset(
                    keys["industries"]
                ):
                    raise ValueError("unbound event relation")
    return deepcopy(value)


def validate_entity_review(value, entity_plan, clusters, data_gaps):
    """Check coverage and bindings; the model owns applicability and importance."""
    if type(value) is not list or len(value) != len(clusters):
        raise ValueError("entity review must cover every cluster")
    by_cluster = {c["clusterId"]: set(c["evidenceItemIds"]) for c in clusters}
    proposals = {role: {r["key"]: set(r["evidenceItemIds"]) for r in entity_plan[role]}
                 for role in ROLES}
    used = {role: set() for role in ROLES}
    seen = set()
    fields = {"clusterId", "disposition", "companyKeys", "industryKeys", "eventKeys", "reason"}
    for row in value:
        if type(row) is not dict or set(row) != fields:
            raise ValueError("invalid entity review fields")
        cluster = row["clusterId"]
        if type(cluster) is not str or cluster not in by_cluster or cluster in seen:
            raise ValueError("unbound or duplicate entity review cluster")
        seen.add(cluster)
        disposition = row["disposition"]
        if (type(disposition) is not str or
            disposition not in {"planned", "not-applicable", "deferred"} or
            type(row["reason"]) is not str or not row["reason"].strip()):
            raise ValueError("invalid entity review decision")
        total = 0
        for field, role in (("companyKeys", "companies"), ("industryKeys", "industries"),
                            ("eventKeys", "events")):
            keys = _strings(row[field])
            total += len(keys)
            for key in keys:
                if key not in proposals[role] or not proposals[role][key] & by_cluster[cluster]:
                    raise ValueError("unbound entity review proposal")
                used[role].add(key)
        if (disposition == "planned") != (total > 0):
            raise ValueError("planned review requires proposals; other decisions require no keys")
    if any(used[role] != set(proposals[role]) for role in ROLES):
        raise ValueError("entity proposal missing review")
    return deepcopy(value)
