"""Checks for tools/holdings.py: python3 -m unittest discover -s test -p 'test_*.py'"""
import copy
import json
import sys
import unittest
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
from holdings import current_symbols, flows_between, holdings_at, realized_gains, transactions  # noqa: E402

POSITIONS = json.loads((ROOT / "data" / "source" / "positions.json").read_text(encoding="utf-8"))
OPEN_COST = Decimal("100831.99")


def with_trades(*rows):
    p = copy.deepcopy(POSITIONS)
    p["transactions"] = list(rows)
    return p


def buy(**kw):
    row = {"id": "t", "type": "buy", "symbol": "MU", "trade_date": "2026-11-11", "executed_at_utc": "2026-11-11T17:54:00Z",
           "shares": "7", "price": "824.70", "fees": None, "status": "confirmed"}
    row.update(kw)
    return row


class RecordedTrades(unittest.TestCase):
    def test_statement_only_before_the_buy(self):
        shares, cost = holdings_at(POSITIONS, "2026-11-10T21:00:00Z")
        self.assertEqual(len(shares), 18)
        self.assertNotIn("MU", shares)
        self.assertEqual(sum(cost.values()), OPEN_COST)

    def test_mu_and_cat_funded_by_spy(self):
        shares, cost = holdings_at(POSITIONS)
        self.assertEqual(shares["MU"], Decimal("7"))
        self.assertEqual(cost["MU"], Decimal("5772.900"))
        self.assertEqual(shares["CAT"], Decimal("8"))
        self.assertEqual(cost["CAT"], Decimal("4868.32"))
        self.assertEqual(shares["SPY"], Decimal("57"))
        self.assertEqual(sum(cost.values()).quantize(Decimal("0.01")), Decimal("101689.73"))
        self.assertEqual(len(current_symbols(POSITIONS)), 20)
        (r,) = realized_gains(POSITIONS)
        self.assertEqual(r["gain"].quantize(Decimal("0.01")), Decimal("874.86"))
        self.assertTrue(r["estimated"])
        self.assertEqual(realized_gains(POSITIONS, "2026-11-11T17:53:59Z"), [])

    def test_flow_counted_once_in_its_interval(self):
        self.assertEqual(flows_between(POSITIONS, "2026-11-10T21:00:00Z", "2026-11-11T18:00:00Z"), Decimal("-17.120"))
        self.assertEqual(flows_between(POSITIONS, "2026-11-11T18:00:00Z", "2026-11-12T18:00:00Z"), 0)
        self.assertEqual(flows_between(POSITIONS, "2026-11-01T00:00:00Z", "2026-11-11T17:53:59Z"), 0)

    def test_fees_add_to_cost(self):
        _, cost = holdings_at(with_trades(buy(fees="1.50")))
        self.assertEqual(cost["MU"], Decimal("5774.400"))

    def test_sell_removes_average_cost_and_closes_position(self):
        p = with_trades(buy(), buy(id="s", type="sell", shares="3", price="900", executed_at_utc="2026-11-12T15:00:00Z"))
        shares, cost = holdings_at(p)
        self.assertEqual(shares["MU"], Decimal("4"))
        self.assertEqual(cost["MU"].quantize(Decimal("0.01")), Decimal("3298.80"))
        self.assertEqual(flows_between(p, "2026-11-12T00:00:00Z", "2026-11-13T00:00:00Z"), Decimal("-2700"))
        closed = with_trades(buy(), buy(id="s", type="sell", shares="7", price="900", executed_at_utc="2026-11-12T15:00:00Z"))
        self.assertNotIn("MU", holdings_at(closed)[0])

    def test_refuses_rows_it_cannot_value(self):
        bad = [
            buy(status="pending_fill"),
            buy(price=None),
            buy(price="0"),
            buy(shares="-1"),
            buy(fees="-2"),
            buy(type="dividend"),
            buy(executed_at_utc="2026-09-22T15:00:00Z"),
            buy(executed_at_utc=None),
        ]
        for row in bad:
            with self.subTest(row=row), self.assertRaises(ValueError):
                holdings_at(with_trades(row))
        with self.assertRaises(ValueError):  # sells more than held
            holdings_at(with_trades(buy(), buy(id="s", type="sell", shares="8", executed_at_utc="2026-11-12T15:00:00Z")))
        # And the valid row passes.
        self.assertEqual(len(transactions(with_trades(buy()))), 1)


if __name__ == "__main__":
    unittest.main()
