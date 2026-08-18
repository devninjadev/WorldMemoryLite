"""Deterministic validation for one-shot, read-only Notion registry recovery.

The caller owns the single Notion search and exact fetches.  This module only
checks the supplied observations and either emits a normal registry or one of
three bounded recovery outcomes.  It performs no search, connector call,
mutation, persistence, or repair.
"""

from __future__ import annotations

from urllib.parse import urlparse

from .notion_layout import DATABASE_SCHEMAS, HUB_MARKER, HUB_TITLE
from .registry import (
    DEFAULT_VIX_SPREADSHEET_SOURCE,
    SCHEMA_VERSION,
    MarketSources,
    Registry,
    market_sources_to_mapping,
    normalize_uuid,
    notion_page_id_from_url,
)


_DATABASE_KEYS = ("collections", "stories", "storyChanges", "reports")
_VIEW_CONTRACTS = {
    "reportsRecent": {
        "name": "Reports Recent",
        "databaseKey": "reports",
        "displayProperties": [
            "Name",
            "Report Type",
            "Window Start",
            "Window End",
            "Created At",
            "Collection",
            "Stories",
        ],
        "sorts": ['"Window End" DESC', '"Created At" DESC'],
    },
    "storiesCurrent": {
        "name": "Stories Current",
        "databaseKey": "stories",
        "displayProperties": [
            "Name",
            "Status",
            "Category",
            "Regions",
            "Importance",
            "Confidence",
            "Current View",
            "First Seen",
            "Last Evidence At",
            "Last Updated",
            "Related Stories",
            "Created At",
        ],
        "sorts": ['"Last Evidence At" DESC', '"Last Updated" DESC'],
    },
}
_CANDIDATE_KEYS = frozenset(
    {"pageId", "url", "title", "marker", "workspaceRoot", "installation"}
)


def resolve_registry_discovery(value: object) -> dict[str, object]:
    """Resolve exactly one structurally valid v2 Hub from supplied observations."""

    _require_exact_keys(value, frozenset({"workspaceId", "candidates"}), "input")
    workspace_id = normalize_uuid(value["workspaceId"], "workspaceId")
    candidates = value["candidates"]
    if type(candidates) is not list:
        raise ValueError("candidates must be a list")

    eligible: list[dict[str, object]] = []
    for candidate in candidates:
        _require_exact_keys(candidate, _CANDIDATE_KEYS, "candidate")
        if type(candidate["title"]) is not str or type(candidate["marker"]) is not str:
            raise ValueError("candidate title and marker must be strings")
        if type(candidate["workspaceRoot"]) is not bool:
            raise ValueError("workspaceRoot must be a boolean")
        if (
            candidate["title"] == HUB_TITLE
            and candidate["marker"] == HUB_MARKER
            and candidate["workspaceRoot"]
        ):
            eligible.append(candidate)

    if not eligible:
        return _outcome("not-found", "world-memory-location-not-found")
    if len(eligible) != 1:
        return _outcome("ambiguous", "world-memory-location-ambiguous")

    try:
        registry = _registry_from_candidate(workspace_id, eligible[0])
    except (TypeError, ValueError):
        return _outcome("structure-mismatch", "world-memory-structure-mismatch")
    return {"status": "recovered", "error": "", "registry": registry}


def _registry_from_candidate(
    workspace_id: str, candidate: dict[str, object]
) -> dict[str, object]:
    hub_id = normalize_uuid(candidate["pageId"], "pageId")
    hub_url = _string(candidate["url"], "url")
    if notion_page_id_from_url(hub_url) != hub_id:
        raise ValueError("Hub URL does not match pageId")

    installation = candidate["installation"]
    _require_exact_keys(
        installation, frozenset({"databases", "views"}), "installation"
    )
    raw_databases = installation["databases"]
    _require_exact_keys(raw_databases, frozenset(_DATABASE_KEYS), "databases")

    database_observations: dict[str, dict[str, str]] = {}
    registry: dict[str, object] = {
        "schemaVersion": SCHEMA_VERSION,
        "workspaceId": workspace_id,
        "hub": {"pageId": hub_id, "url": hub_url},
    }
    for key in _DATABASE_KEYS:
        observed = raw_databases[key]
        _require_exact_keys(
            observed,
            frozenset(
                {
                    "title",
                    "databaseUrl",
                    "parentPageId",
                    "dataSourceId",
                    "properties",
                }
            ),
            "database",
        )
        if observed["title"] != DATABASE_SCHEMAS[key]["title"]:
            raise ValueError("database title does not match")
        if normalize_uuid(observed["parentPageId"], "parentPageId") != hub_id:
            raise ValueError("database parent does not match Hub")
        database_url = _database_url(observed["databaseUrl"])
        data_source_id = normalize_uuid(observed["dataSourceId"], "dataSourceId")
        if _property_projection(observed["properties"]) != _expected_properties(key):
            raise ValueError("database property projection does not match")
        database_observations[key] = {
            "databaseUrl": database_url,
            "dataSourceId": data_source_id,
        }
        registry[key] = {"dataSourceId": data_source_id}

    raw_views = installation["views"]
    _require_exact_keys(raw_views, frozenset(_VIEW_CONTRACTS), "views")
    registry_views: dict[str, object] = {}
    for key, contract in _VIEW_CONTRACTS.items():
        observed = raw_views[key]
        _require_exact_keys(
            observed,
            frozenset(
                {
                    "name",
                    "databaseUrl",
                    "viewId",
                    "dataSourceId",
                    "displayProperties",
                    "sorts",
                }
            ),
            "view",
        )
        database = database_observations[contract["databaseKey"]]
        if observed["name"] != contract["name"]:
            raise ValueError("view name does not match")
        if _database_url(observed["databaseUrl"]) != database["databaseUrl"]:
            raise ValueError("view database does not match")
        if normalize_uuid(observed["dataSourceId"], "view dataSourceId") != database[
            "dataSourceId"
        ]:
            raise ValueError("view data source does not match")
        if observed["displayProperties"] != contract["displayProperties"]:
            raise ValueError("view display properties do not match")
        if observed["sorts"] != contract["sorts"]:
            raise ValueError("view sorts do not match")
        view_id = normalize_uuid(observed["viewId"], "viewId")
        registry_views[key] = {
            "url": database["databaseUrl"] + "?v=" + view_id.replace("-", "")
        }

    registry["views"] = registry_views
    registry["marketSources"] = market_sources_to_mapping(
        MarketSources(vix_spreadsheet=DEFAULT_VIX_SPREADSHEET_SOURCE)
    )
    return Registry.from_mapping(registry).to_mapping()


def _expected_properties(key: str) -> dict[str, str]:
    return {
        name: descriptor["type"]
        for name, descriptor in DATABASE_SCHEMAS[key]["properties"].items()
    }


def _property_projection(value: object) -> dict[str, str]:
    if type(value) is not dict or any(
        type(name) is not str or type(property_type) is not str
        for name, property_type in value.items()
    ):
        raise ValueError("properties must be a name/type object")
    return {
        name: "rich_text" if property_type == "text" else property_type
        for name, property_type in value.items()
    }


def _database_url(value: object) -> str:
    url = _string(value, "databaseUrl")
    parsed = urlparse(url)
    if parsed.query or parsed.fragment or parsed.params:
        raise ValueError("databaseUrl must not contain query, fragment, or params")
    notion_page_id_from_url(url)
    return url


def _string(value: object, field_name: str) -> str:
    if type(value) is not str or not value or value != value.strip():
        raise ValueError(f"{field_name} must be a nonempty string")
    return value


def _require_exact_keys(value: object, expected: frozenset[str], label: str) -> None:
    if type(value) is not dict or set(value) != expected:
        raise ValueError(f"{label} keys do not match")


def _outcome(status: str, error: str) -> dict[str, object]:
    return {"status": status, "error": error, "registry": None}
