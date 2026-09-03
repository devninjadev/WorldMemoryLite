"""Build deterministic, human-readable Notion MCP request dictionaries.

The builders in this module do not call a connector.  They translate the
logical Notion-native model into the current official connector request shape,
including flattened DATE property keys at that transport boundary.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import datetime, timezone
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

from .feed import FeedItem, FeedOutcome, deduplicate_items
from .llm_plan import CHANGE_TYPES, DIRECTIONS, LEVELS
from .market import MarketSnapshot, ProviderResult, validate_market_snapshot
from .notion_layout import DATABASE_SCHEMAS
from .registry import Registry, normalize_uuid
from .windows import Window


_UTC = timezone.utc
_KST = ZoneInfo("Asia/Seoul")
_MARKET_PROPERTY_STATUS = {
    "ok": "complete",
    "partial": "partial",
    "unavailable": "unavailable",
}
_MARKDOWN_INLINE_CONTROLS = frozenset("\\*~`$[]<>{}|^")
_MARKDOWN_LINK_DESTINATION_HAZARDS = frozenset('\\`<>{}|^()"')
_HEX_DIGITS = frozenset("0123456789abcdefABCDEF")
_ARTICLE_LINK_LABEL = "기사 원문"
_COLLECTION_ITEMS_PER_PAGE = 50
_STORY_STATUS_OPTIONS = tuple(
    DATABASE_SCHEMAS["stories"]["properties"]["Status"]["options"]
)
_STORY_CATEGORY_OPTIONS = tuple(
    DATABASE_SCHEMAS["stories"]["properties"]["Category"]["options"]
)
_STORY_REGION_OPTIONS = tuple(
    DATABASE_SCHEMAS["stories"]["properties"]["Regions"]["options"]
)


def collection_page(
    registry: Registry,
    window: Window,
    outcomes: Iterable[FeedOutcome],
    market: MarketSnapshot,
) -> dict[str, object]:
    """Return one readable Collection request in ``notion-create-pages`` shape."""

    registry = _require_registry(registry)
    window = _require_window(window)
    feed_outcomes = _feed_outcomes(outcomes)
    market = _require_market(market)
    retained_items = deduplicate_items(feed_outcomes)
    success_count = sum(outcome.status == "ok" for outcome in feed_outcomes)
    failure_count = len(feed_outcomes) - success_count
    data_gaps = _collection_gaps(feed_outcomes, market)

    properties: dict[str, object] = {
        "Name": f"Collection · {_window_label(window)}",
        **_date_properties("Window Start", window.start),
        **_date_properties("Window End", window.end),
        "Feed Success Count": success_count,
        "Feed Failure Count": failure_count,
        "Item Count": len(retained_items),
        "Market Data Status": _MARKET_PROPERTY_STATUS[market.status],
    }
    if data_gaps:
        properties["Data Gaps"] = "; ".join(data_gaps)

    return _create_request(
        registry.collections.data_source_id,
        properties,
        _collection_markdown(window, feed_outcomes, retained_items, market),
    )


def collection_pages(
    registry: Registry,
    window: Window,
    outcomes: Iterable[FeedOutcome],
    market: MarketSnapshot,
) -> tuple[dict[str, object], ...]:
    """Return sequential, bounded Collection create requests for one window."""

    registry = _require_registry(registry)
    window = _require_window(window)
    feed_outcomes = _feed_outcomes(outcomes)
    market = _require_market(market)
    retained_items = deduplicate_items(feed_outcomes)
    chunks = tuple(
        retained_items[index : index + _COLLECTION_ITEMS_PER_PAGE]
        for index in range(0, len(retained_items), _COLLECTION_ITEMS_PER_PAGE)
    ) or ((),)
    page_count = len(chunks)
    requests: list[dict[str, object]] = []
    for page_index, chunk in enumerate(chunks, 1):
        chunk_ids = {item.item_id for item in chunk}
        page_outcomes = tuple(
            FeedOutcome(
                outcome.source_id,
                outcome.source_name,
                outcome.status,
                tuple(item for item in outcome.items if item.item_id in chunk_ids),
                outcome.error,
                outcome.retryable,
            )
            for outcome in feed_outcomes
        )
        request = collection_page(registry, window, page_outcomes, market)
        page = request["pages"][0]
        page["properties"]["Item Count"] = len(chunk)
        if page_count > 1:
            page["properties"]["Name"] += f" · {page_index}/{page_count}"
        requests.append(request)
    return tuple(requests)


def report_page(
    registry: Registry,
    window: Window,
    validated_plan: dict[str, object],
    relations: object = (),
) -> dict[str, object]:
    """Return one readable Report request from an already validated LLM plan."""

    registry = _require_registry(registry)
    window = _require_window(window)
    report = _validated_report(validated_plan)
    properties: dict[str, object] = {
        "Name": f"World Memory · {_window_label(window)}",
        "Report Type": report["type"],
        **_date_properties("Window Start", window.start),
        **_date_properties("Window End", window.end),
        "Stance": report["stance"],
        "Confidence": report["confidence"],
        "Data Quality": report["dataQuality"],
    }
    data_gaps = _string_list(report["dataGaps"], "report.dataGaps")
    if data_gaps:
        properties["Data Gaps"] = "; ".join(data_gaps)
    properties.update(_report_relations(relations))

    markdown = _nonempty_string(report["markdown"], "report.markdown")
    return _create_request(registry.reports.data_source_id, properties, markdown)


def story_page(
    registry: Registry,
    decision: dict[str, object],
    observed_at: datetime,
) -> dict[str, object]:
    """Return a new Story request with a readable current-state projection."""

    registry = _require_registry(registry)
    fields = _story_fields(decision, expected_action="create")
    properties = {
        **_story_properties(fields),
        **_date_properties("First Seen", observed_at),
        **_date_properties("Last Evidence At", observed_at),
        **_date_properties("Last Updated", observed_at),
    }
    related_stories = _relation_ids(
        fields["relatedStoryLocators"], "decision.relatedStoryLocators"
    )
    if related_stories:
        properties["Related Stories"] = related_stories
    return _create_request(
        registry.stories.data_source_id,
        properties,
        fields["storyMarkdown"],
    )


def story_update(
    page_id: str,
    decision: dict[str, object],
    observed_at: datetime,
) -> dict[str, object]:
    """Declare the two ordered ``notion-update-page`` calls for one Story."""

    page_id = normalize_uuid(page_id, "page_id")
    fields = _story_fields(decision, expected_action="update")
    if page_id != fields["storyLocator"]:
        raise ValueError("page_id must match decision.storyLocator")
    properties = {
        **_story_properties(fields),
        **_date_properties("Last Evidence At", observed_at),
        **_date_properties("Last Updated", observed_at),
    }
    related_stories = _relation_ids(
        fields["relatedStoryLocators"], "decision.relatedStoryLocators"
    )
    properties["Related Stories"] = related_stories
    return {
        "steps": [
            {
                "page_id": page_id,
                "command": "update_properties",
                "properties": properties,
            },
            {
                "page_id": page_id,
                "command": "replace_content",
                "new_str": _notion_transport_content(fields["storyMarkdown"]),
            },
        ]
    }


def story_change_page(
    registry: Registry,
    decision: dict[str, object],
    observed_at: datetime,
    relation_ids: object,
) -> dict[str, object]:
    """Return a Story Change request bound only to caller-confirmed page IDs."""

    registry = _require_registry(registry)
    fields = _story_fields(decision)
    relations = _story_change_relations(relation_ids)
    if (
        fields["action"] == "update"
        and relations["Primary Story"][0] != fields["storyLocator"]
    ):
        raise ValueError(
            "relation_ids.primaryStory must match decision.storyLocator for update"
        )
    observed_label = _observed_date_label(observed_at)
    properties: dict[str, object] = {
        "Name": f"{fields['name']} · {fields['changeType']} · {observed_label}",
        **_date_properties("Observed At", observed_at),
        "Change Type": fields["changeType"],
        "Direction": fields["direction"],
        "Strength": fields["importance"],
        "Confidence": fields["confidence"],
        **relations,
    }
    return _create_request(
        registry.story_changes.data_source_id,
        properties,
        fields["changeMarkdown"],
    )


def _create_request(
    data_source_id: str | None,
    properties: dict[str, object],
    content: str,
) -> dict[str, object]:
    if data_source_id is None:
        raise ValueError("registry data source locator is missing")
    return {
        "parent": {"data_source_id": data_source_id},
        "pages": [
            {
                "properties": properties,
                "content": _notion_transport_content(content),
            }
        ],
    }


def _notion_transport_content(content: str) -> str:
    """Preserve a logical leading H1 across the current Notion MCP transport."""
    if type(content) is not str:
        raise ValueError("content must be a string")
    return "<empty-block/>\n" + content if content.startswith("# ") else content


def _story_fields(
    value: object, *, expected_action: str | None = None
) -> dict[str, object]:
    if type(value) is not dict:
        raise ValueError("decision must be an object")
    action = value.get("action")
    if action not in {"create", "update"}:
        raise ValueError("decision.action must be create or update")
    if expected_action is not None and action != expected_action:
        raise ValueError(f"decision.action must be {expected_action}")

    fields: dict[str, object] = {
        "action": action,
        "storyLocator": _story_locator(value.get("storyLocator"), action),
        "name": _nonempty_string(value.get("name"), "decision.name"),
        "status": _enum_string(
            value.get("status"), _STORY_STATUS_OPTIONS, "decision.status"
        ),
        "category": _enum_string(
            value.get("category"), _STORY_CATEGORY_OPTIONS, "decision.category"
        ),
        "regions": _enum_string_list(
            value.get("regions"), _STORY_REGION_OPTIONS, "decision.regions"
        ),
        "changeType": _enum_string(
            value.get("changeType"), CHANGE_TYPES, "decision.changeType"
        ),
        "direction": _enum_string(
            value.get("direction"), DIRECTIONS, "decision.direction"
        ),
        "importance": _enum_string(
            value.get("importance"), LEVELS, "decision.importance"
        ),
        "confidence": _enum_string(
            value.get("confidence"), LEVELS, "decision.confidence"
        ),
        "currentView": _nonempty_string(
            value.get("currentView"), "decision.currentView"
        ),
        "storyMarkdown": _nonempty_string(
            value.get("storyMarkdown"), "decision.storyMarkdown"
        ),
        "changeMarkdown": _nonempty_string(
            value.get("changeMarkdown"), "decision.changeMarkdown"
        ),
        "relatedStoryLocators": _nonempty_string_list(
            value.get("relatedStoryLocators"), "decision.relatedStoryLocators"
        ),
    }
    return fields


def _story_properties(fields: dict[str, object]) -> dict[str, object]:
    return {
        "Name": fields["name"],
        "Status": fields["status"],
        "Category": fields["category"],
        "Regions": list(fields["regions"]),
        "Importance": fields["importance"],
        "Confidence": fields["confidence"],
        "Current View": fields["currentView"],
    }


def _story_change_relations(value: object) -> dict[str, list[str]]:
    if not isinstance(value, Mapping):
        raise ValueError("relation_ids must be a mapping of confirmed page IDs")
    allowed = {"primaryStory", "relatedStory", "report", "collection"}
    if any(type(key) is not str for key in value) or not set(value).issubset(allowed):
        raise ValueError("relation_ids contains an unsupported relation")
    if "primaryStory" not in value:
        raise ValueError("relation_ids.primaryStory is required")

    property_names = {
        "primaryStory": "Primary Story",
        "relatedStory": "Related Story",
        "report": "Related Report",
        "collection": "Related Collection",
    }
    properties: dict[str, list[str]] = {}
    for relation_name, property_name in property_names.items():
        if relation_name not in value:
            continue
        ids = _relation_ids(
            value[relation_name],
            f"relation_ids.{relation_name}",
            require_single=relation_name == "primaryStory",
        )
        if relation_name == "primaryStory" and len(ids) != 1:
            raise ValueError(
                "relation_ids.primaryStory must contain exactly one page UUID"
            )
        if ids:
            properties[property_name] = ids
    return properties


def _observed_date_label(value: datetime) -> str:
    _utc_iso(value)
    return value.astimezone(_KST).strftime("%Y-%m-%d")


def _collection_markdown(
    window: Window,
    outcomes: tuple[FeedOutcome, ...],
    retained_items: tuple[FeedItem, ...],
    market: MarketSnapshot,
) -> str:
    retained_by_source: dict[str, list[FeedItem]] = {}
    for item in retained_items:
        retained_by_source.setdefault(item.source_id, []).append(item)
    lines = [
        "# 수집 개요",
        "",
        f"- 구간: {_utc_iso(window.start)} → {_utc_iso(window.end)}",
        f"- 성공 피드: {sum(item.status == 'ok' for item in outcomes)}/{len(outcomes)}",
        f"- 시장 데이터: {_MARKET_PROPERTY_STATUS[market.status]}",
    ]
    for outcome in outcomes:
        lines.extend(("", f"## {_markdown_inline(outcome.source_name)}", ""))
        if outcome.status != "ok":
            lines.append(f"- 수집 실패: {_markdown_inline(outcome.error)}")
            continue
        source_items = retained_by_source.pop(outcome.source_id, [])
        if not source_items:
            lines.append("- 중복 제거 후 보존된 항목 없음")
            continue
        for item in source_items:
            lines.extend(
                (
                    f"### {_markdown_inline(item.title)}",
                    "",
                    f"- 게시 시각: {_markdown_inline(item.published_at)}",
                    f"- URL: {_rendered_article_link(item.url)}",
                    f"- 요약: {_markdown_inline(item.summary) if item.summary else '요약 없음'}",
                    "",
                )
            )

    lines.extend(("## 시장 데이터", ""))
    if not market.providers:
        lines.append("- 사용 가능한 시장 데이터 없음")
    for provider in market.providers:
        lines.append(_market_provider_line(provider))
    return "\n".join(lines).rstrip() + "\n"


def _market_provider_line(provider: ProviderResult) -> str:
    provider_name = _markdown_inline(provider.provider)
    if provider.status == "not-attempted":
        return f"- {provider_name}: 시도하지 않음"
    if provider.status != "ok":
        return f"- {provider_name}: 수집 실패 — {_markdown_inline(provider.error)}"
    values = ", ".join(
        f"{_markdown_inline(str(key))}: {_markdown_inline(str(value))}"
        for key, value in provider.values.items()
    )
    return f"- {provider_name}: {values}"


def _collection_gaps(
    outcomes: tuple[FeedOutcome, ...], market: MarketSnapshot
) -> tuple[str, ...]:
    values = [
        f"{_plain_text(outcome.source_name)}: {_plain_text(outcome.error)}"
        for outcome in outcomes
        if outcome.status != "ok"
    ]
    values.extend(_plain_text(gap) for gap in market.gaps)
    return tuple(dict.fromkeys(value for value in values if value))


def _feed_outcomes(outcomes: Iterable[FeedOutcome]) -> tuple[FeedOutcome, ...]:
    if isinstance(outcomes, (str, bytes)):
        raise ValueError("outcomes must contain FeedOutcome values")
    try:
        values = tuple(outcomes)
    except TypeError as exc:
        raise ValueError("outcomes must be iterable") from exc
    if not all(isinstance(value, FeedOutcome) for value in values):
        raise ValueError("outcomes must contain FeedOutcome values")
    if any(value.status not in {"ok", "error"} for value in values):
        raise ValueError("FeedOutcome status must be ok or error")
    return values


def _require_market(market: MarketSnapshot) -> MarketSnapshot:
    return validate_market_snapshot(market)


def _validated_report(value: object) -> dict[str, object]:
    if type(value) is not dict or type(value.get("report")) is not dict:
        raise ValueError("validated_plan.report must be an object")
    return value["report"]


def _report_relations(value: object) -> dict[str, list[str]]:
    if isinstance(value, Mapping):
        pairs = tuple(value.items())
    else:
        if isinstance(value, (str, bytes)):
            raise ValueError("relations must be a mapping or iterable of pairs")
        try:
            pairs = tuple(value)
        except TypeError as exc:
            raise ValueError("relations must be a mapping or iterable of pairs") from exc

    properties: dict[str, list[str]] = {}
    for pair in pairs:
        if not isinstance(pair, tuple) or len(pair) != 2:
            raise ValueError("relations must contain property and page-ID pairs")
        property_name, raw_ids = pair
        if property_name not in {"Collection", "Stories"}:
            raise ValueError("Report relation must be Collection or Stories")
        relation_ids = _relation_ids(raw_ids, f"relations.{property_name}")
        if relation_ids:
            properties[property_name] = relation_ids
    return properties


def _relation_ids(
    value: object, field_name: str, *, require_single: bool = False
) -> list[str]:
    raw_values = (value,) if type(value) is str else value
    if isinstance(raw_values, (bytes, Mapping)):
        raise ValueError(f"{field_name} must contain page ID strings")
    try:
        values = tuple(raw_values)
    except TypeError as exc:
        raise ValueError(f"{field_name} must contain page ID strings") from exc
    if require_single and len(values) != 1:
        raise ValueError(f"{field_name} must contain exactly one page UUID")
    if any(type(item) is not str or not item.strip() for item in values):
        raise ValueError(f"{field_name} must contain nonempty page ID strings")
    try:
        normalized = tuple(normalize_uuid(item, field_name) for item in values)
    except ValueError as exc:
        raise ValueError(f"{field_name} must contain page UUIDs") from exc
    return list(dict.fromkeys(normalized))


def _date_properties(property_name: str, value: datetime) -> dict[str, object]:
    return {
        f"date:{property_name}:start": _utc_iso(value),
        f"date:{property_name}:is_datetime": 1,
    }


def _utc_iso(value: object) -> str:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("date value must be a timezone-aware datetime")
    return value.astimezone(_UTC).isoformat().replace("+00:00", "Z")


def _window_label(window: Window) -> str:
    start = window.start.astimezone(_KST)
    end = window.end.astimezone(_KST)
    if start.date() == end.date():
        return f"{start:%Y-%m-%d %H:%M}–{end:%H:%M} KST"
    return f"{start:%Y-%m-%d %H:%M}–{end:%Y-%m-%d %H:%M} KST"


def _markdown_inline(value: object) -> str:
    text = _plain_text(value)
    return "".join(f"\\{char}" if char in _MARKDOWN_INLINE_CONTROLS else char for char in text)


def _rendered_article_link(value: object) -> str:
    url = _validated_article_url(value)
    return f"[{_ARTICLE_LINK_LABEL}]({url})"


def _validated_article_url(value: object) -> str:
    if type(value) is not str or not value:
        raise ValueError("article URL must be a nonempty string")
    if "\r" in value or "\n" in value:
        raise ValueError("article URL must not contain CR or LF")
    if any(char.isspace() for char in value):
        raise ValueError("article URL must not contain whitespace")
    if any(ord(char) < 32 or ord(char) == 127 for char in value):
        raise ValueError("article URL must not contain control characters")
    if any(char in _MARKDOWN_LINK_DESTINATION_HAZARDS for char in value):
        raise ValueError("article URL contains an unsafe Markdown link delimiter")
    for index, char in enumerate(value):
        if char == "%" and (
            index + 2 >= len(value)
            or value[index + 1] not in _HEX_DIGITS
            or value[index + 2] not in _HEX_DIGITS
        ):
            raise ValueError("article URL contains an invalid percent escape")
    try:
        parsed = urlparse(value)
        hostname = parsed.hostname
    except ValueError as exc:
        raise ValueError("article URL is malformed") from exc
    if parsed.scheme.lower() not in {"http", "https"} or not hostname:
        raise ValueError("article URL must use HTTP(S) and include a host")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("article URL must not contain credentials")
    try:
        parsed.port
    except ValueError as exc:
        raise ValueError("article URL has an invalid port") from exc
    return value


def _plain_text(value: object) -> str:
    return " ".join(value.split()) if type(value) is str else ""


def _nonempty_string(value: object, field_name: str) -> str:
    if type(value) is not str or not value.strip():
        raise ValueError(f"{field_name} must be a nonempty string")
    return value


def _string_list(value: object, field_name: str) -> tuple[str, ...]:
    if type(value) is not list or any(type(item) is not str for item in value):
        raise ValueError(f"{field_name} must be a list of strings")
    return tuple(value)


def _nonempty_string_list(value: object, field_name: str) -> tuple[str, ...]:
    values = _string_list(value, field_name)
    if any(not item.strip() for item in values):
        raise ValueError(f"{field_name} must contain nonempty strings")
    return values


def _enum_string(value: object, allowed: tuple[str, ...], field_name: str) -> str:
    normalized = _nonempty_string(value, field_name)
    if normalized not in allowed:
        raise ValueError(f"{field_name} is not supported")
    return normalized


def _enum_string_list(
    value: object, allowed: tuple[str, ...], field_name: str
) -> tuple[str, ...]:
    values = _nonempty_string_list(value, field_name)
    if any(item not in allowed for item in values):
        raise ValueError(f"{field_name} contains an unsupported value")
    return values


def _story_locator(value: object, action: object) -> str:
    if type(value) is not str:
        raise ValueError("decision.storyLocator must be a string")
    if action == "create":
        if value != "":
            raise ValueError("decision.storyLocator must be empty for create")
        return ""
    if not value:
        raise ValueError("decision.storyLocator must be nonempty for update")
    try:
        return normalize_uuid(value, "decision.storyLocator")
    except ValueError as exc:
        raise ValueError("decision.storyLocator must be a page UUID") from exc


def _require_registry(registry: object) -> Registry:
    if not isinstance(registry, Registry):
        raise ValueError("registry must be a Registry")
    return registry


def _require_window(window: object) -> Window:
    if not isinstance(window, Window):
        raise ValueError("window must be a Window")
    return window
