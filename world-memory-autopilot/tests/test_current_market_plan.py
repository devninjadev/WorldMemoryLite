"""Provider policy regressions for the current TradingView and VIX routes."""

import unittest

from world_memory.market_plan import TOOL_ACCESS_KEYS, TRADINGVIEW_ACCESS_KEYS
from world_memory.plugin_market import build_plugin_market_plan


def plan(enabled=True):
    return build_plugin_market_plan(
        tool_access={key: enabled for key in TOOL_ACCESS_KEYS + TRADINGVIEW_ACCESS_KEYS},
        vix_public_csv_url="https://docs.google.com/spreadsheets/d/example/export?format=csv&gid=0",
        vix_symbols=("VIX9D", "VIX", "VIX3M", "VIX6M"),
    )


class CurrentMarketPlanTests(unittest.TestCase):
    def test_tradingview_is_first_for_supported_quote_and_history_capabilities(self):
        capabilities = plan()["capabilities"]
        for name in ("equity-current-price", "equity-daily-bars", "credit-risk-pair",
                     "market-breadth-pair", "treasury-yield-curve", "economic-time-series"):
            with self.subTest(capability=name):
                self.assertEqual(capabilities[name]["providers"][0], "tradingview")

    def test_vix_uses_google_finance_and_excludes_tradingview(self):
        route = plan()["capabilities"]["volatility-term-structure"]
        self.assertEqual(route["providers"], [
            "google-finance", "wolfram-language", "wolfram-alpha", "cboe", "spreadsheet"])
        self.assertNotIn("tradingview", route["providers"])

    def test_public_fallbacks_remain_when_no_connector_is_available(self):
        capabilities = plan(False)["capabilities"]
        self.assertEqual(capabilities["volatility-term-structure"]["providers"],
                         ["google-finance", "cboe", "spreadsheet"])
        self.assertEqual(capabilities["treasury-yield-curve"]["providers"],
                         ["treasury-csv", "treasury-xml"])
        self.assertEqual(capabilities["economic-time-series"]["providers"],
                         ["fred-batch", "fred-page"])

    def test_wolfram_alpha_does_not_supply_macro_series_or_treasury_curves(self):
        capabilities = plan()["capabilities"]
        for name in ("economic-time-series", "treasury-yield-curve"):
            with self.subTest(capability=name):
                self.assertNotIn("wolfram-alpha", capabilities[name]["providers"])
                self.assertIn("wolfram-language", capabilities[name]["providers"])


if __name__ == "__main__":
    unittest.main()
