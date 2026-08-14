"""Validation for the static Notion-native installation registry."""

from __future__ import annotations

from dataclasses import dataclass
import re
from urllib.parse import parse_qsl, urlparse
from uuid import UUID


SCHEMA_VERSION = "notion-native-v2"

_UUID_IN_PATH_SEGMENT = re.compile(
    r"(?<![0-9a-f])[0-9a-f]{8}-?[0-9a-f]{4}-?[0-9a-f]{4}-?[0-9a-f]{4}-?[0-9a-f]{12}(?![0-9a-f])",
    re.IGNORECASE,
)
_FIRST_PARTY_NOTION_SUFFIXES = ("notion.so", "notion.com")
_VIX_PUBLIC_CSV_URL = (
    "https://docs.google.com/spreadsheets/d/"
    "15xqjZq8di2UqrePpYR_p72j5FCj-WTEDC4rdjZSqc_w/export?format=csv&gid=0"
)
_VIX_PUBLIC_CSV_PATH = (
    "/spreadsheets/d/"
    "15xqjZq8di2UqrePpYR_p72j5FCj-WTEDC4rdjZSqc_w/export"
)
_VIX_SYMBOLS = ("VIX9D", "VIX", "VIX3M", "VIX6M")


@dataclass(frozen=True)
class PageLocator:
    """A Notion page address whose URL is bound to the same page UUID."""

    page_id: str
    url: str


@dataclass(frozen=True)
class DataSourceLocator:
    """A Notion data source address, independent of its database container ID."""

    data_source_id: str


@dataclass(frozen=True)
class ViewLocator:
    """A saved Notion view URL bound to one database container and view UUID."""

    url: str
    database_id: str
    view_id: str


@dataclass(frozen=True)
class VixSpreadsheetSource:
    """The one approved public VIX spreadsheet address and symbol contract."""

    public_csv_url: str
    expected_symbols: tuple[str, ...]

    def __post_init__(self) -> None:
        _validate_vix_public_csv_url(self.public_csv_url)
        _validate_vix_symbols(self.expected_symbols)


@dataclass(frozen=True)
class MarketSources:
    """Immutable public market-source addresses for one installation."""

    vix_spreadsheet: VixSpreadsheetSource

    def __post_init__(self) -> None:
        if not isinstance(self.vix_spreadsheet, VixSpreadsheetSource):
            raise ValueError("vix_spreadsheet must be a VixSpreadsheetSource")


@dataclass(frozen=True)
class Registry:
    """The immutable address book embedded in a World Memory schedule prompt."""

    schema_version: str
    workspace_id: str
    hub: PageLocator
    collections: DataSourceLocator
    stories: DataSourceLocator
    story_changes: DataSourceLocator
    reports: DataSourceLocator
    reports_recent: ViewLocator
    stories_current: ViewLocator
    market_sources: MarketSources

    @classmethod
    def from_mapping(cls, value: object) -> "Registry":
        expected = {
            "schemaVersion",
            "workspaceId",
            "hub",
            "collections",
            "stories",
            "storyChanges",
            "reports",
            "views",
            "marketSources",
        }
        if not isinstance(value, dict) or set(value) != expected:
            raise ValueError("registry keys must match notion-native-v2")
        if value["schemaVersion"] != SCHEMA_VERSION:
            raise ValueError("schemaVersion must be notion-native-v2")

        views = value["views"]
        expected_views = {"reportsRecent", "storiesCurrent"}
        if not isinstance(views, dict) or set(views) != expected_views:
            raise ValueError("view registry keys do not match")

        return cls(
            schema_version=SCHEMA_VERSION,
            workspace_id=normalize_uuid(value["workspaceId"], "workspaceId"),
            hub=parse_page_locator(value["hub"]),
            collections=parse_data_source_locator(value["collections"]),
            stories=parse_data_source_locator(value["stories"]),
            story_changes=parse_data_source_locator(value["storyChanges"]),
            reports=parse_data_source_locator(value["reports"]),
            reports_recent=parse_view_locator(views["reportsRecent"]),
            stories_current=parse_view_locator(views["storiesCurrent"]),
            market_sources=parse_market_sources(value["marketSources"]),
        )

    def to_mapping(self) -> dict[str, object]:
        """Return the canonical prompt-safe JSON-compatible registry mapping."""
        return {
            "schemaVersion": self.schema_version,
            "workspaceId": self.workspace_id,
            "hub": page_locator_to_mapping(self.hub),
            "collections": data_source_locator_to_mapping(self.collections),
            "stories": data_source_locator_to_mapping(self.stories),
            "storyChanges": data_source_locator_to_mapping(self.story_changes),
            "reports": data_source_locator_to_mapping(self.reports),
            "views": {
                "reportsRecent": view_locator_to_mapping(self.reports_recent),
                "storiesCurrent": view_locator_to_mapping(self.stories_current),
            },
            "marketSources": market_sources_to_mapping(self.market_sources),
        }


def validate_registry(value: object) -> dict[str, object]:
    """Validate and normalize an untrusted schedule registry mapping."""
    return Registry.from_mapping(value).to_mapping()


def normalize_uuid(value: object, field_name: str) -> str:
    """Return a lower-case dashed UUID while rejecting bool and non-strings."""
    if isinstance(value, bool) or not isinstance(value, str):
        raise ValueError(f"{field_name} must be a UUID string")
    try:
        return str(UUID(value))
    except (AttributeError, TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} must be a UUID string") from exc


def parse_page_locator(value: object) -> PageLocator:
    """Validate the exact Hub locator and bind its page UUID to its URL."""
    expected = {"pageId", "url"}
    if not isinstance(value, dict) or set(value) != expected:
        raise ValueError(f"locator keys for page must be exactly {sorted(expected)}")

    identifier = normalize_uuid(value["pageId"], "pageId")
    url = value["url"]
    if isinstance(url, bool) or not isinstance(url, str):
        raise ValueError("Notion URL must be a string")
    bind_url_identifier(url, identifier)
    return PageLocator(page_id=identifier, url=url)


def parse_data_source_locator(value: object) -> DataSourceLocator:
    """Validate an exact data-source locator without a database URL or ID."""
    expected = {"dataSourceId"}
    if not isinstance(value, dict) or set(value) != expected:
        raise ValueError(
            f"locator keys for data_source must be exactly {sorted(expected)}"
        )
    return DataSourceLocator(
        data_source_id=normalize_uuid(value["dataSourceId"], "dataSourceId")
    )


def parse_view_locator(value: object) -> ViewLocator:
    """Validate an exact saved-view URL without persisting mutable view state."""
    expected = {"url"}
    if not isinstance(value, dict) or set(value) != expected:
        raise ValueError(f"locator keys for view must be exactly {sorted(expected)}")
    url = value["url"]
    if isinstance(url, bool) or not isinstance(url, str):
        raise ValueError("Notion view URL must be a string")
    parsed = urlparse(url)
    if parsed.fragment:
        raise ValueError("Notion view URL must not contain a fragment")
    try:
        query = parse_qsl(parsed.query, keep_blank_values=True, strict_parsing=True)
    except ValueError as exc:
        raise ValueError("Notion view URL query is invalid") from exc
    if len(query) != 1 or query[0][0] != "v":
        raise ValueError("Notion view URL must contain only one v parameter")
    database_id = notion_page_id_from_url(url)
    view_id = normalize_uuid(query[0][1], "Notion view ID")
    return ViewLocator(url=url, database_id=database_id, view_id=view_id)


def parse_market_sources(value: object) -> MarketSources:
    """Validate the exact immutable public market-source registry shape."""
    if not isinstance(value, dict) or set(value) != {"vixSpreadsheet"}:
        raise ValueError("marketSources keys must be exactly ['vixSpreadsheet']")
    source = value["vixSpreadsheet"]
    expected = {"publicCsvUrl", "expectedSymbols"}
    if not isinstance(source, dict) or set(source) != expected:
        raise ValueError(
            "marketSources.vixSpreadsheet keys must be publicCsvUrl and expectedSymbols"
        )
    symbols = source["expectedSymbols"]
    if type(symbols) is not list:
        raise ValueError("expectedSymbols must be a list")
    return MarketSources(
        vix_spreadsheet=VixSpreadsheetSource(
            public_csv_url=source["publicCsvUrl"],
            expected_symbols=tuple(symbols),
        )
    )


def _validate_vix_public_csv_url(value: object) -> None:
    if type(value) is not str or not value or value != value.strip():
        raise ValueError("publicCsvUrl must be the approved public CSV URL")
    try:
        parsed = urlparse(value)
        port = parsed.port
        query = parse_qsl(parsed.query, keep_blank_values=True, strict_parsing=True)
    except ValueError as exc:
        raise ValueError("publicCsvUrl is invalid") from exc
    if (
        parsed.scheme != "https"
        or parsed.hostname != "docs.google.com"
        or parsed.username is not None
        or parsed.password is not None
        or port is not None
        or parsed.path != _VIX_PUBLIC_CSV_PATH
        or parsed.params
        or parsed.fragment
        or query != [("format", "csv"), ("gid", "0")]
        or not query[1][1].isdigit()
        or int(query[1][1]) < 0
        or value != _VIX_PUBLIC_CSV_URL
    ):
        raise ValueError("publicCsvUrl must be the approved public CSV URL")


def _validate_vix_symbols(value: object) -> None:
    if type(value) is not tuple or value != _VIX_SYMBOLS:
        raise ValueError("expectedSymbols must match the approved ordered symbols")


DEFAULT_VIX_SPREADSHEET_SOURCE = VixSpreadsheetSource(
    public_csv_url=_VIX_PUBLIC_CSV_URL,
    expected_symbols=_VIX_SYMBOLS,
)


def bind_url_identifier(url: str, identifier: str) -> None:
    """Require a Notion HTTPS URL whose final path component includes its UUID."""
    url_identifier = notion_page_id_from_url(url)
    if identifier != url_identifier:
        raise ValueError("Notion URL UUID does not match declared ID")


def notion_page_id_from_url(url: object) -> str:
    """Return the sole canonical page UUID from a current first-party Notion URL."""
    if isinstance(url, bool) or not isinstance(url, str):
        raise ValueError("Notion URL must be a string")
    parsed = urlparse(url)
    hostname = (parsed.hostname or "").lower()
    if parsed.scheme != "https" or not is_first_party_notion_hostname(hostname):
        raise ValueError("Notion URL must use a first-party notion.so or notion.com host")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("Notion URL must not contain credentials")
    try:
        port = parsed.port
    except ValueError as exc:
        raise ValueError("Notion URL has an invalid port") from exc
    if port is not None:
        raise ValueError("Notion URL must not contain an explicit port")

    final_segment = parsed.path.rstrip("/").rsplit("/", 1)[-1]
    matches = _UUID_IN_PATH_SEGMENT.findall(final_segment)
    if not matches:
        raise ValueError("Notion URL final path segment must contain a UUID")
    if len(matches) != 1:
        raise ValueError("Notion URL final path segment must contain one page UUID")
    return normalize_uuid(matches[0], "Notion URL ID")


def is_first_party_notion_hostname(value: object) -> bool:
    """Return whether a hostname belongs to the current Notion app domains."""
    if type(value) is not str or not value:
        return False
    hostname = value.lower().rstrip(".")
    return any(
        hostname == suffix or hostname.endswith(f".{suffix}")
        for suffix in _FIRST_PARTY_NOTION_SUFFIXES
    )


def page_locator_to_mapping(locator: PageLocator) -> dict[str, str]:
    """Serialize the Hub locator to its exact public mapping shape."""
    if not isinstance(locator, PageLocator):
        raise ValueError("page locator is invalid")
    return {"pageId": locator.page_id, "url": locator.url}


def data_source_locator_to_mapping(locator: DataSourceLocator) -> dict[str, str]:
    """Serialize a data-source locator to its exact public mapping shape."""
    if not isinstance(locator, DataSourceLocator):
        raise ValueError("data source locator is invalid")
    return {"dataSourceId": locator.data_source_id}


def view_locator_to_mapping(locator: ViewLocator) -> dict[str, str]:
    """Serialize a saved-view locator to its exact public mapping shape."""
    if not isinstance(locator, ViewLocator):
        raise ValueError("view locator is invalid")
    return {"url": locator.url}


def market_sources_to_mapping(value: MarketSources) -> dict[str, object]:
    """Serialize only immutable public source addresses, never runtime state."""
    if not isinstance(value, MarketSources):
        raise ValueError("market sources are invalid")
    source = value.vix_spreadsheet
    return {
        "vixSpreadsheet": {
            "publicCsvUrl": source.public_csv_url,
            "expectedSymbols": list(source.expected_symbols),
        }
    }
