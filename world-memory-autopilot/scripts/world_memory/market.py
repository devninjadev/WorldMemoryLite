"""Provider-independent aggregation of partial market-source results."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Callable, Iterable


_ERROR_LIMIT = 240


@dataclass(frozen=True)
class ProviderResult:
    """A single adapter result; adapters report errors instead of raising them."""

    provider: str
    status: str
    values: dict[str, object]
    error: str
    stage: str = ""


@dataclass(frozen=True)
class MarketSnapshot:
    """All observed provider results plus usable values and explicit gaps."""

    status: str
    providers: tuple[ProviderResult, ...]
    values: dict[str, object]
    gaps: tuple[str, ...]


MarketAdapter = Callable[[], ProviderResult]


def collect_market_providers(
    providers: Iterable[tuple[str, MarketAdapter]], *, max_workers: int = 5
) -> tuple[ProviderResult, ...]:
    """Run independent adapters concurrently without leaking an adapter exception."""
    if isinstance(max_workers, bool) or not isinstance(max_workers, int) or max_workers <= 0:
        raise ValueError("max_workers must be a positive integer")
    configured = tuple((_require_provider(name), adapter) for name, adapter in providers)
    if not all(callable(adapter) for _, adapter in configured):
        raise ValueError("market adapters must be callable")
    if not configured:
        return ()

    collected: dict[int, ProviderResult] = {}
    with ThreadPoolExecutor(max_workers=min(max_workers, len(configured))) as executor:
        pending = {
            executor.submit(_run_adapter, name, adapter): index
            for index, (name, adapter) in enumerate(configured)
        }
        for future in as_completed(pending):
            index = pending[future]
            name = configured[index][0]
            try:
                collected[index] = future.result()
            except Exception as exc:  # Defensive boundary for executor-level failures.
                collected[index] = ProviderResult(
                    name,
                    "error",
                    {},
                    _exception_error("market_collector", exc),
                    "fetch",
                )
    return tuple(collected[index] for index in range(len(configured)))


def combine_market_results(results: Iterable[ProviderResult]) -> MarketSnapshot:
    """Combine independent provider results without letting one failure erase data."""
    providers: list[ProviderResult] = []
    values: dict[str, object] = {}
    gaps: list[str] = []
    for result in results:
        normalized = _normalize_result(result)
        providers.append(normalized)
        if normalized.status == "not-attempted":
            continue
        if normalized.status == "error":
            gaps.append(f"{normalized.provider}: {normalized.error}")
            continue
        for key, value in normalized.values.items():
            values.setdefault(key, value)

    if values:
        status = "partial" if gaps else "ok"
    else:
        status = "unavailable"
    return MarketSnapshot(status, tuple(providers), values, tuple(gaps))


def validate_market_snapshot(value: object) -> MarketSnapshot:
    """Require one snapshot to exactly match the canonical provider contract."""

    if not isinstance(value, MarketSnapshot):
        raise ValueError("market must be a MarketSnapshot")
    if (
        type(value.status) is not str
        or type(value.providers) is not tuple
        or type(value.values) is not dict
        or type(value.gaps) is not tuple
    ):
        raise ValueError("market snapshot has an invalid shape")
    try:
        canonical = combine_market_results(value.providers)
    except (TypeError, ValueError) as exc:
        raise ValueError("market contains invalid provider results") from exc
    if value != canonical:
        raise ValueError("market snapshot contradicts canonical provider results")
    return value


def _run_adapter(name: str, adapter: MarketAdapter) -> ProviderResult:
    try:
        result = adapter()
    except Exception as exc:
        return ProviderResult(
            name,
            "error",
            {},
            _exception_error("market_adapter", exc),
            "fetch",
        )
    if not isinstance(result, ProviderResult):
        return ProviderResult(name, "error", {}, "market_provider_error", "parse")
    if result.provider != name:
        return ProviderResult(name, "error", {}, "market_provider_error", "parse")
    try:
        return _normalize_result(result)
    except ValueError:
        category = (
            "market_provider_empty_values"
            if result.status == "ok"
            and type(result.values) is dict
            and not result.values
            and result.error == ""
            and result.stage == ""
            else "market_provider_error"
        )
        return ProviderResult(name, "error", {}, category, "parse")


def _normalize_result(result: ProviderResult) -> ProviderResult:
    if not isinstance(result, ProviderResult):
        raise ValueError("market results must be ProviderResult values")
    provider = _require_provider(result.provider)
    if type(result.values) is not dict:
        raise ValueError("provider values must be an object")
    if type(result.error) is not str or type(result.stage) is not str:
        raise ValueError("provider error and stage must be strings")
    if result.status == "ok":
        if not result.values or result.error or result.stage:
            raise ValueError("ok provider results require only nonempty values")
        return ProviderResult(provider, "ok", dict(result.values), "")
    if result.status == "error":
        if result.values or not result.error.strip() or result.stage not in {"fetch", "parse"}:
            raise ValueError("error provider results require an attempted failure stage")
        return ProviderResult(
            provider, "error", {}, "market_provider_error", result.stage
        )
    if result.status == "not-attempted":
        if result.values or result.error or result.stage:
            raise ValueError("not-attempted provider results cannot contain observations")
        return ProviderResult(provider, "not-attempted", {}, "")
    raise ValueError("provider status must be ok, error, or not-attempted")


def _require_provider(value: object) -> str:
    if isinstance(value, bool) or not isinstance(value, str) or not value.strip():
        raise ValueError("provider must be a nonempty string")
    return " ".join(value.split())


def _exception_error(category: str, exc: Exception) -> str:
    """Return a stable adapter diagnostic without exposing exception text."""
    return f"{category}_{exc.__class__.__name__.lower()}"[:_ERROR_LIMIT]
