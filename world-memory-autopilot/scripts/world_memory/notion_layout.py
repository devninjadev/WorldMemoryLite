"""Static, logical Notion schema descriptors for a fresh native installation.

The descriptors deliberately describe logical DATE properties.  Connector
payload builders own any transport-specific date key flattening.
"""

from __future__ import annotations

from copy import deepcopy


SCHEMA_VERSION = "notion-native-v2"
HUB_TITLE = "World Memory · Notion Native"
HUB_MARKER = "World Memory storage contract: notion-native-v2"

DATABASE_TITLES: dict[str, str] = {
    "collections": "World Memory Collections",
    "stories": "World Memory Stories",
    "storyChanges": "World Memory Story Changes",
    "reports": "World Memory Reports",
}

# This descriptor is intentionally connector-neutral.  `target` is the local
# database key that setup resolves to a Notion data source ID when creating a
# relation.  `self` distinguishes the Story self-relation from cross-database
# relations.  No transport payload key syntax belongs in this module.
DATABASE_SCHEMAS: dict[str, dict[str, object]] = {
    "collections": {
        "title": "World Memory Collections",
        "properties": {
            "Name": {"type": "title", "required": True},
            "Window Start": {"type": "date", "required": True},
            "Window End": {"type": "date", "required": True},
            "Feed Success Count": {"type": "number", "required": True},
            "Feed Failure Count": {"type": "number", "required": True},
            "Item Count": {"type": "number", "required": True},
            "Market Data Status": {
                "type": "select",
                "required": True,
                "options": ["complete", "partial", "unavailable", "not-requested"],
            },
            "Data Gaps": {"type": "rich_text", "required": False},
            "Created At": {"type": "created_time", "required": False},
        },
    },
    "stories": {
        "title": "World Memory Stories",
        "properties": {
            "Name": {"type": "title", "required": True},
            "Status": {
                "type": "select",
                "required": True,
                "options": ["emerging", "active", "cooling", "resolved"],
            },
            "Category": {
                "type": "select",
                "required": True,
                "options": [
                    "macro",
                    "rates",
                    "fx",
                    "equity",
                    "credit",
                    "commodity",
                    "policy",
                    "geopolitics",
                    "technology",
                    "other",
                ],
            },
            "Regions": {
                "type": "multi_select",
                "required": True,
                "options": ["US", "KR", "CN", "JP", "EU", "GLOBAL"],
            },
            "Importance": {
                "type": "select",
                "required": True,
                "options": ["high", "medium", "low"],
            },
            "Confidence": {
                "type": "select",
                "required": True,
                "options": ["high", "medium", "low"],
            },
            "Current View": {"type": "rich_text", "required": True},
            "First Seen": {"type": "date", "required": True},
            "Last Evidence At": {"type": "date", "required": True},
            "Last Updated": {"type": "date", "required": True},
            "Related Stories": {
                "type": "relation",
                "required": False,
                "target": "stories",
                "self": True,
            },
            "Created At": {"type": "created_time", "required": False},
        },
    },
    "storyChanges": {
        "title": "World Memory Story Changes",
        "properties": {
            "Name": {"type": "title", "required": True},
            "Observed At": {"type": "date", "required": True},
            "Change Type": {
                "type": "select",
                "required": True,
                "options": [
                    "created",
                    "strengthened",
                    "weakened",
                    "reframed",
                    "relationship-changed",
                    "cooled",
                    "resolved",
                ],
            },
            "Direction": {
                "type": "select",
                "required": True,
                "options": [
                    "strengthens",
                    "weakens",
                    "reframes",
                    "connects",
                    "closes",
                    "neutral",
                ],
            },
            "Strength": {
                "type": "select",
                "required": True,
                "options": ["high", "medium", "low"],
            },
            "Confidence": {
                "type": "select",
                "required": True,
                "options": ["high", "medium", "low"],
            },
            "Primary Story": {
                "type": "relation",
                "required": True,
                "target": "stories",
            },
            "Related Story": {
                "type": "relation",
                "required": False,
                "target": "stories",
            },
            "Related Report": {
                "type": "relation",
                "required": False,
                "target": "reports",
            },
            "Related Collection": {
                "type": "relation",
                "required": False,
                "target": "collections",
            },
            "Created At": {"type": "created_time", "required": False},
        },
    },
    "reports": {
        "title": "World Memory Reports",
        "properties": {
            "Name": {"type": "title", "required": True},
            "Report Type": {
                "type": "select",
                "required": True,
                "options": ["briefing", "world-memory"],
            },
            "Window Start": {"type": "date", "required": True},
            "Window End": {"type": "date", "required": True},
            "Stance": {
                "type": "select",
                "required": True,
                "options": ["risk-on", "neutral", "defensive", "mixed"],
            },
            "Confidence": {
                "type": "select",
                "required": True,
                "options": ["high", "medium", "low"],
            },
            "Data Quality": {
                "type": "select",
                "required": True,
                "options": ["complete", "partial", "limited"],
            },
            "Data Gaps": {"type": "rich_text", "required": False},
            "Collection": {
                "type": "relation",
                "required": False,
                "target": "collections",
            },
            "Stories": {
                "type": "relation",
                "required": False,
                "target": "stories",
            },
            "Created At": {"type": "created_time", "required": False},
        },
    },
}


def bootstrap_manifest() -> dict[str, object]:
    """Return an independent logical manifest for one fresh Notion setup."""
    return {
        "schemaVersion": SCHEMA_VERSION,
        "hubTitle": HUB_TITLE,
        "marker": HUB_MARKER,
        "databases": deepcopy(DATABASE_SCHEMAS),
    }
