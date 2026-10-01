"""Execute current documented examples through the public market validator."""

import json
from pathlib import Path
import unittest

from tests.test_cli import run_cli
from tests.test_plugin_market import _bind_structured_payload

REFERENCE_PATHS = {"market-data": Path(__file__).resolve().parents[1] / "references/market-data.md"}


def _read(path):
    return path.read_text()


def _json_block_after(text, heading):
    tail = text.split(heading + "\n", 1)[1]
    return json.loads(tail.split("```json\n", 1)[1].split("\n```", 1)[0])


class DocumentedMarketExampleTests(unittest.TestCase):
    def test_documented_current_price_is_accepted_with_bound_evidence(self):
        fixture = _json_block_after(_read(REFERENCE_PATHS["market-data"]),
                                   "### Current price validator fixture")
        result = run_cli("validate-market-observation", "-", stdin=json.dumps(fixture))
        self.assertEqual(result.returncode, 0, result.stderr)
        response = json.loads(result.stdout)
        self.assertEqual(response["status"], "accepted")
        self.assertEqual(response["observation"]["price"], fixture["candidate"]["price"])
        self.assertNotIn("evidence", response)

    def test_documented_pair_requests_cross_the_real_validator_without_fill(self) -> None:
        """Catch wrong pair identities, minima, descriptors, or fabricated dates."""

        requests = _json_block_after(
            _read(REFERENCE_PATHS["market-data"]),
            "### Scheduled pair request fixtures",
        )
        cases = (
            ("credit-risk-pair", ("HYG", "LQD"), 6),
            ("market-breadth-pair", ("RSP", "SPY"), 21),
        )
        observed_trading_dates = (
            "2026-07-17",
            "2026-07-20",
            "2026-07-21",
            "2026-07-22",
            "2026-07-23",
            "2026-07-24",
            "2026-07-27",
            "2026-07-28",
            "2026-07-29",
            "2026-07-30",
            "2026-07-31",
            "2026-08-03",
            "2026-08-04",
            "2026-08-05",
            "2026-08-06",
            "2026-08-07",
            "2026-08-10",
            "2026-08-11",
            "2026-08-12",
            "2026-08-13",
            "2026-08-14",
        )
        for task1_name, symbols, minimum in cases:
            with self.subTest(task1_name=task1_name):
                request = requests[task1_name]
                self.assertEqual(request["capability"], "equity-pair-series")
                self.assertEqual(
                    tuple(item["symbol"] for item in request["instruments"]),
                    symbols,
                )
                self.assertEqual(request["minimumCommonDays"], minimum)
                dates = observed_trading_dates[-minimum:]
                series = []
                evidence_series = []
                bindings = []
                for index, instrument in enumerate(request["instruments"]):
                    rows = [
                        {"date": date, "value": 80.0 + index * 20 + row_index}
                        for row_index, date in enumerate(dates)
                    ]
                    series.append(
                        {
                            "instrument": {**instrument, "exchange": "NYSE Arca"},
                            "rows": rows,
                        }
                    )
                    evidence_series.append({"rows": rows})
                    bindings.append(
                        {"field": f"series.{index}.rows", "evidenceId": "ev-pair"}
                    )
                descriptor = (
                    f"equity-pair-series:{','.join(symbols)}:"
                    f"{request['startDate']}:{request['endDate']}"
                )
                payload = {
                    "request": request,
                    "candidate": {
                        "schemaVersion": "1.0",
                        "capability": "equity-pair-series",
                        "provider": "wolfram-language",
                        "sourceLocator": {
                            "kind": "provider-query",
                            "tool": "Wolfram Language",
                            "queryDescriptor": descriptor,
                        },
                        "fetchedAt": "2026-08-16T11:45:00Z",
                        "completeness": "complete",
                        "evidenceBindings": bindings,
                        "currency": "USD",
                        "valueBasis": "wolfram-daily-close",
                        "marketScope": "provider-market",
                        "session": "regular",
                        "series": series,
                    },
                    "evidence": [
                        {
                            "evidenceId": "ev-pair",
                            "format": "structured",
                            "content": {"series": evidence_series},
                        }
                    ],
                    "normalizationAttempt": 1,
                }
                _bind_structured_payload(payload, "ev-pair")
                completed = run_cli(
                    "validate-market-observation", "-", stdin=json.dumps(payload)
                )
                self.assertEqual(completed.returncode, 0, completed.stderr)
                self.assertEqual(json.loads(completed.stdout)["status"], "accepted")

