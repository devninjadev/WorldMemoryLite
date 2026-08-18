"""Contract tests for provider-independent partial market aggregation."""

from __future__ import annotations

import unittest

from world_memory.market import (
    ProviderResult,
    collect_market_providers,
    combine_market_results,
)


class MarketAggregationTests(unittest.TestCase):
    def test_parallel_provider_collection_restores_order_and_isolates_adapter_errors(self) -> None:
        secret = "https://api-key:super-secret@example.com/authorization?token=leak"
        results = collect_market_providers((
            ("google-finance", lambda: ProviderResult("google-finance", "ok", {"SPY": 651.2}, "")),
            ("cboe", lambda: (_ for _ in ()).throw(RuntimeError(secret))),
        ))
        self.assertEqual(tuple(result.provider for result in results), ("google-finance", "cboe"))
        self.assertEqual(results[0].values, {"SPY": 651.2})
        self.assertEqual(results[1].status, "error")
        self.assertEqual(results[1].error, "market_adapter_runtimeerror")
        self.assertEqual(results[1].stage, "fetch")
        self.assertNotIn(secret, results[1].error)

    def test_collector_normalizes_successful_empty_adapter_result_to_error(self) -> None:
        results = collect_market_providers((
            ("google-finance", lambda: ProviderResult("google-finance", "ok", {}, "")),
        ))
        self.assertEqual(results, (
            ProviderResult(
                "google-finance",
                "error",
                {},
                "market_provider_empty_values",
                "parse",
            ),
        ))

    def test_cboe_failure_does_not_discard_google_finance(self) -> None:
        snapshot = combine_market_results((
            ProviderResult("google-finance", "ok", {"SPY": 651.2}, ""),
            ProviderResult("cboe", "error", {}, "parser failed", "parse"),
        ))
        self.assertEqual(snapshot.status, "partial")
        self.assertEqual(snapshot.values, {"SPY": 651.2})
        self.assertEqual(snapshot.gaps, ("cboe: market_provider_error",))

    def test_cboe_failure_preserves_spreadsheet_values(self) -> None:
        snapshot = combine_market_results((
            ProviderResult("spreadsheet", "ok", {"USD/KRW": 1387.5}, ""),
            ProviderResult("cboe", "error", {}, "parser failed", "parse"),
        ))
        self.assertEqual(snapshot.status, "partial")
        self.assertEqual(snapshot.values, {"USD/KRW": 1387.5})

    def test_bounded_provider_error_codes_survive_without_raw_detail(self) -> None:
        snapshot = combine_market_results(
            (
                ProviderResult(
                    "alpaca", "error", {}, "premium-feed-required", "fetch"
                ),
                ProviderResult("wolfram", "error", {}, "raw secret detail", "parse"),
            )
        )
        self.assertEqual(
            snapshot.gaps,
            (
                "alpaca: premium-feed-required",
                "wolfram: market_provider_error",
            ),
        )

    def test_all_market_providers_can_be_unavailable_without_exception(self) -> None:
        snapshot = combine_market_results((
            ProviderResult("google-finance", "error", {}, "timeout", "fetch"),
            ProviderResult("cboe", "error", {}, "parser failed", "parse"),
        ))
        self.assertEqual(snapshot.status, "unavailable")
        self.assertEqual(snapshot.values, {})
        self.assertEqual(
            snapshot.gaps,
            ("google-finance: market_provider_error", "cboe: market_provider_error"),
        )

    def test_attempted_failure_and_not_attempted_have_distinct_truth(self) -> None:
        snapshot = combine_market_results((
            ProviderResult("spreadsheet", "ok", {"VIX": 14.58}, ""),
            ProviderResult("cboe", "error", {}, "ignored raw detail", "parse"),
            ProviderResult("google-finance", "not-attempted", {}, ""),
        ))

        self.assertEqual(snapshot.status, "partial")
        self.assertEqual(snapshot.values, {"VIX": 14.58})
        self.assertEqual(snapshot.gaps, ("cboe: market_provider_error",))
        self.assertEqual(
            snapshot.providers,
            (
                ProviderResult("spreadsheet", "ok", {"VIX": 14.58}, ""),
                ProviderResult(
                    "cboe", "error", {}, "market_provider_error", "parse"
                ),
                ProviderResult("google-finance", "not-attempted", {}, ""),
            ),
        )

    def test_complete_wolfram_treasury_short_circuits_fallbacks_truthfully(self) -> None:
        snapshot = combine_market_results((
            ProviderResult(
                "wolfram-language",
                "ok",
                {
                    "UST.2Y": 3.61,
                    "UST.5Y": 3.74,
                    "UST.10Y": 4.02,
                    "UST.30Y": 4.61,
                },
                "",
            ),
            ProviderResult("wolfram-alpha", "not-attempted", {}, ""),
            ProviderResult("treasury-csv", "not-attempted", {}, ""),
            ProviderResult("treasury-xml", "not-attempted", {}, ""),
        ))

        self.assertEqual(snapshot.status, "ok")
        self.assertEqual(snapshot.gaps, ())
        self.assertEqual(
            tuple(result.status for result in snapshot.providers),
            ("ok", "not-attempted", "not-attempted", "not-attempted"),
        )

    def test_partial_wolfram_vix_preserves_components_and_fallback_fills_only_gaps(self) -> None:
        snapshot = combine_market_results((
            ProviderResult(
                "wolfram-language",
                "partial",
                {"VIX9D": 15.2, "VIX": 16.4},
                "market_provider_partial",
            ),
            ProviderResult(
                "cboe",
                "ok",
                {"VIX9D": 99.0, "VIX": 99.0, "VIX3M": 17.1, "VIX6M": 18.0},
                "",
            ),
        ))

        self.assertEqual(snapshot.status, "partial")
        self.assertEqual(
            snapshot.values,
            {"VIX9D": 15.2, "VIX": 16.4, "VIX3M": 17.1, "VIX6M": 18.0},
        )
        self.assertEqual(
            snapshot.gaps,
            ("wolfram-language: market_provider_partial",),
        )

    def test_malformed_status_stage_or_value_combinations_fail_closed(self) -> None:
        malformed = (
            ProviderResult("provider", "unknown", {}, ""),
            ProviderResult("provider", "ok", {}, ""),
            ProviderResult("provider", "ok", {"VIX": 14.58}, "raw detail"),
            ProviderResult("provider", "ok", {"VIX": 14.58}, "", "fetch"),
            ProviderResult("provider", "error", {"VIX": 14.58}, "raw", "parse"),
            ProviderResult("provider", "error", {}, "", "parse"),
            ProviderResult("provider", "error", {}, "raw", ""),
            ProviderResult("provider", "error", {}, "raw", "transform"),
            ProviderResult("provider", "not-attempted", {"VIX": 14.58}, ""),
            ProviderResult("provider", "not-attempted", {}, "raw detail"),
            ProviderResult("provider", "not-attempted", {}, "", "fetch"),
            ProviderResult("provider", "partial", {}, "market_provider_partial"),
            ProviderResult("provider", "partial", {"VIX": 14.58}, ""),
            ProviderResult("provider", "partial", {"VIX": 14.58}, "raw detail"),
            ProviderResult(
                "provider",
                "partial",
                {"VIX": 14.58},
                "market_provider_partial",
                "parse",
            ),
        )
        for result in malformed:
            with self.subTest(result=result), self.assertRaises(ValueError):
                combine_market_results((result,))

    def test_first_successful_provider_value_wins_without_losing_other_values(self) -> None:
        snapshot = combine_market_results((
            ProviderResult("google-finance", "ok", {"SPY": 651.2, "QQQ": 580.0}, ""),
            ProviderResult("spreadsheet", "ok", {"SPY": 650.0, "USD/KRW": 1387.5}, ""),
        ))
        self.assertEqual(snapshot.status, "ok")
        self.assertEqual(snapshot.values, {"SPY": 651.2, "QQQ": 580.0, "USD/KRW": 1387.5})
        self.assertEqual(snapshot.gaps, ())


if __name__ == "__main__":
    unittest.main()
