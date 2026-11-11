"""Tests for build.py (stdlib unittest only, no third-party deps).

Every test runs build.main() against a TEMP copy of data/source inside
tempfile.TemporaryDirectory, with build.ROOT/SRC/OUT redirected, so the repo's
web/ and data/ trees are never read for output nor written to.

Privacy claims checked here come from README "Public vs full data" (as corrected on
packet/readmeaudit): the public payload carries relative units plus each holding's average
cost per share, and no share counts or position dollar totals. Case 2 asserts the "shares" /
"cost_basis" / "value" / "market_value" KEYS are absent (not redacted to empty/null), that
avg_cost is present and quantized exactly as build.py writes it, and that the source dollar
totals appear nowhere in the file.
"""
import csv
import io
import importlib.util
import json
import shutil
import tempfile
import unittest
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def _load_build_module():
    spec = importlib.util.spec_from_file_location("build_under_test", REPO / "build.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# Imported once; each test re-points ROOT/SRC/OUT at its own temp dir in setUp.
build = _load_build_module()


def money(value):
    return str(Decimal(str(value)).quantize(Decimal("0.01"), ROUND_HALF_UP))


STATEMENT_HEADER = ["symbol", "name", "shares", "statement_market_value", "cost_basis",
                    "reported_cost_per_share", "unrealized_gain", "purchase_date",
                    "statement_date", "currency"]


def quote(symbol, price, previous_close, provider_update_at_utc, session="closed"):
    return {"symbol": symbol, "price": price, "previous_close": previous_close,
            "provider_update_at_utc": provider_update_at_utc,
            "retrieved_at_utc": "2026-10-27T00:00:00Z", "session": session,
            "provider": "test fixture", "source_url": f"https://example.com/{symbol}"}


class BuildTestCase(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.src = self.root / "data" / "source"
        shutil.copytree(REPO / "data" / "source", self.src)
        self.out = self.root / "web" / "data" / "portfolio.json"
        self.public_out = self.root / "web" / "data" / "portfolio.public.json"
        # Redirect every path build.py uses so the repo's web/ and data/ are untouched.
        for attr, value in (("ROOT", self.root), ("SRC", self.src), ("OUT", self.out)):
            self.addCleanup(setattr, build, attr, getattr(build, attr))
            setattr(build, attr, value)

    # -- fixture / source helpers -------------------------------------------------

    def write_source_json(self, name, data):
        (self.src / name).write_text(json.dumps(data), encoding="utf-8")

    def write_statement(self, rows):
        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=STATEMENT_HEADER)
        writer.writeheader()
        for row in rows:
            record = {key: "" for key in STATEMENT_HEADER}
            record.update({"statement_date": "2026-09-22", "currency": "USD", **row})
            writer.writerow(record)
        (self.src / "statement-20260922.csv").write_text(buf.getvalue(), encoding="utf-8")

    def statement_rows(self):
        with open(self.src / "statement-20260922.csv", newline="", encoding="utf-8") as fh:
            return list(csv.DictReader(fh))

    def positions(self):
        return json.loads((self.src / "positions.json").read_text(encoding="utf-8"))

    def read_payload(self, path=None):
        return json.loads((path or self.out).read_text(encoding="utf-8"))


class TestFullBuild(BuildTestCase):
    def test_holdings_count_matches_positions_and_statement_value_is_exact(self):
        build.main(public=False, out=self.out)
        payload = self.read_payload()
        opening = self.positions()["opening_positions"]

        self.assertEqual(len(payload["holdings"]), len(opening))
        self.assertEqual({h["symbol"] for h in payload["holdings"]},
                         {p["symbol"] for p in opening})

        rows = self.statement_rows()
        expected_value = money(sum(Decimal(r["statement_market_value"]) for r in rows))
        expected_basis = money(sum(Decimal(r["cost_basis"]) for r in rows))
        self.assertEqual(payload["statement"]["value"], expected_value)
        self.assertEqual(payload["statement"]["basis"], expected_basis)
        self.assertEqual(payload["amounts"], "shown")

    def test_full_holdings_carry_source_share_counts_and_cost_basis(self):
        build.main(public=False, out=self.out)
        payload = self.read_payload()
        by_symbol = {h["symbol"]: h for h in payload["holdings"]}
        for row in self.statement_rows():
            holding = by_symbol[row["symbol"]]
            self.assertEqual(holding["shares"], str(Decimal(row["shares"])))
            self.assertEqual(holding["cost_basis"], money(row["cost_basis"]))


class TestPublicBuild(BuildTestCase):
    """README "Public vs full data": the public payload gives relative units plus average
    cost per share, with no share counts and no position dollar totals. build.py writes
    avg_cost on purpose (units x avg_cost reproduces total cost without revealing position
    size), so its presence and exact quantization are asserted, not its absence."""

    def test_public_omits_share_counts_cost_basis_and_dollar_values(self):
        build.main(public=True, out=self.public_out)
        raw = self.public_out.read_text(encoding="utf-8")
        payload = self.read_payload(self.public_out)

        self.assertEqual(payload["amounts"], "hidden")

        # Keys absent, not redacted to empty (README privacy claim).
        self.assertNotIn('"shares"', raw)
        self.assertNotIn('"cost_basis"', raw)
        for holding in payload["holdings"]:
            self.assertNotIn("shares", holding)
            self.assertNotIn("cost_basis", holding)
            self.assertNotIn("value", holding)
            self.assertNotIn("market_value", holding)
            self.assertIn("units", holding)
            # avg_cost is present on purpose (units x avg_cost reproduces total cost without
            # revealing position size): a string quantized to exactly six decimal places.
            self.assertIsInstance(holding["avg_cost"], str)
            self.assertRegex(holding["avg_cost"], r"^\d+\.\d{6}$")

        # ...and it must equal build.py's own formula applied to the source statement:
        # cost_basis / shares, quantized to 1e-6, half-up.
        by_symbol = {h["symbol"]: h for h in payload["holdings"]}
        for row in self.statement_rows():
            expected_avg = str((Decimal(row["cost_basis"]) / Decimal(row["shares"]))
                               .quantize(Decimal("1e-6"), ROUND_HALF_UP))
            self.assertEqual(by_symbol[row["symbol"]]["avg_cost"], expected_avg)

        self.assertIsNone(payload["statement"]["value"])
        self.assertIsNone(payload["statement"]["basis"])
        for point in payload["history"]:
            self.assertNotIn("value", point)
            self.assertIn("index", point)

        # No source dollar amount survives anywhere in the file.
        rows = self.statement_rows()
        self.assertNotIn(money(sum(Decimal(r["statement_market_value"]) for r in rows)), raw)
        self.assertNotIn(money(sum(Decimal(r["cost_basis"]) for r in rows)), raw)

    def test_public_keeps_every_holding(self):
        build.main(public=True, out=self.public_out)
        payload = self.read_payload(self.public_out)
        opening = self.positions()["opening_positions"]
        self.assertEqual(len(payload["holdings"]), len(opening))


class TestMissingQuote(BuildTestCase):
    def test_missing_quote_is_reported_and_no_output_is_written(self):
        current = json.loads((self.src / "quotes-current.json").read_text(encoding="utf-8"))
        current["quotes"] = [q for q in current["quotes"] if q["symbol"] != "NVDA"]
        self.write_source_json("quotes-current.json", current)

        with self.assertRaises(SystemExit) as ctx:
            build.main(public=False, out=self.out)

        message = str(ctx.exception)
        self.assertIn("NVDA", message)     # the missing holding is named
        self.assertIn("missing", message)  # reported as missing, not dropped
        self.assertFalse(self.out.exists())  # no payload, so no made-up price ships


class TestDecimalExactness(BuildTestCase):
    def test_totals_match_decimal_sum_to_the_cent_where_float_drifts(self):
        # Fixture chosen so the exact decimal total (3.015) needs ROUND_HALF_UP:
        # a float build sums to 3.0149999999999997 and lands on "3.01".
        self.write_statement([
            {"symbol": "SPY", "name": "SPDR S&P 500 ETF Trust", "shares": "7",
             "statement_market_value": "1.005", "cost_basis": "100.00"},
            {"symbol": "AAPL", "name": "Apple", "shares": "3",
             "statement_market_value": "1.005", "cost_basis": "9.00"},
            {"symbol": "AMD", "name": "Advanced Micro Devices", "shares": "3",
             "statement_market_value": "1.005", "cost_basis": "9.00"},
        ])
        self.write_source_json("positions.json", {
            "schema": "club-portfolio.v1", "currency": "USD",
            "opening_observation": "statement-20260922", "instruments": [],
            "opening_positions": [
                {"symbol": "SPY", "shares": "7", "cost_basis": "100.00"},
                {"symbol": "AAPL", "shares": "3", "cost_basis": "9.00"},
                {"symbol": "AMD", "shares": "3", "cost_basis": "9.00"},
            ],
        })
        self.write_source_json("quotes-current.json", {
            "schema": "portfolio-quotes.v1", "collected_at_utc": "2026-10-27T00:00:00Z",
            "quotes": [quote("SPY", "700.65", "698.00", "2026-10-26T20:00:01Z"),
                       quote("AAPL", "10.10", "10.02", "2026-10-26T20:00:01Z"),
                       quote("AMD", "20.20", "19.95", "2026-10-26T20:00:01Z")],
        })
        self.write_source_json("historical-quotes.json", [{
            "quotes": [quote("SPY", "690.00", "688.00", "2026-10-20T20:00:00Z"),
                       quote("AAPL", "9.00", "8.90", "2026-10-20T20:00:00Z"),
                       quote("AMD", "19.00", "18.80", "2026-10-20T20:00:00Z")],
        }])
        self.write_source_json("instrument-profiles.json", {"instruments": []})

        # Document the drift a float implementation would have shown.
        float_values = [1.005, 1.005, 1.005]
        self.assertNotEqual(money(sum(float_values)), "3.02")
        self.assertEqual(money(sum(float_values)), "3.01")

        build.main(public=False, out=self.out)
        payload = self.read_payload()

        # Statement total is the exact Decimal sum rounded half-up to the cent.
        expected_total = money(sum(Decimal("1.005") for _ in range(3)))
        self.assertEqual(expected_total, "3.02")
        self.assertEqual(payload["statement"]["value"], expected_total)
        self.assertEqual(payload["statement"]["basis"], "118.00")

        history = payload["history"]
        self.assertEqual(history[0]["value"], "3.02")       # statement point
        self.assertEqual(history[0]["spy"], "0.14")         # 1.005 / 7 shares
        # Snapshot totals: 7x690.00 + 3x9.00 + 3x19.00 and 7x700.65 + 3x10.10 + 3x20.20.
        self.assertEqual(history[2]["value"], "4914.00")
        self.assertEqual(history[3]["value"], "4995.45")

        # avg_cost keeps six places so units x avg_cost can reproduce the basis.
        spy = next(h for h in payload["holdings"] if h["symbol"] == "SPY")
        self.assertEqual(spy["avg_cost"], "14.285714")      # 100.00 / 7, half-up


if __name__ == "__main__":
    unittest.main()
