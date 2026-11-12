"""Checks for tools/snapshot_updates.py (no network): python3 -m unittest discover -s test -p 'test_*.py'"""
import datetime
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
from snapshot_updates import cik_map, filings, label, merge, sec_ticker  # noqa: E402

SINCE = datetime.date(2026, 11, 2)
SUBMISSIONS = {"filings": {"recent": {
    "accessionNumber": ["0000723125-26-000041", "0000723125-26-000040", "0000723125-26-000039", "0000723125-26-000030", "0000723125-26-000029"],
    "form": ["8-K", "4", "10-Q", "8-K", "8-K"],
    "filingDate": ["2026-11-10", "2026-11-09", "2026-11-05", "2026-10-01", "not-a-date"],
    "items": ["2.02,9.01", "", "", "5.02", "8.01"],
}}}


class Label(unittest.TestCase):
    def test_reports(self):
        self.assertEqual(label("10-Q", ""), "Form 10-Q: quarterly report")
        self.assertEqual(label("10-K", None), "Form 10-K: annual report")

    def test_8k_items_in_plain_words_without_the_routine_exhibits_item(self):
        self.assertEqual(label("8-K", "2.02,9.01"), "Form 8-K: results of operations")
        self.assertEqual(label("8-K", "5.02, 7.01, 8.01"), "Form 8-K: a director or officer change; a Regulation FD disclosure")

    def test_unknown_or_missing_items_are_not_guessed(self):
        for items in ("", None, "9.01", "6.66"):
            self.assertEqual(label("8-K", items), "Form 8-K: current report")


class Tickers(unittest.TestCase):
    def test_exact_ticker_only(self):
        m = cik_map({"0": {"cik_str": 18230, "ticker": "CAT", "title": "CATERPILLAR INC"},
                     "1": {"cik_str": 1067983, "ticker": "BRK-B", "title": "BERKSHIRE HATHAWAY INC"},
                     "2": {"cik_str": 1, "ticker": "CATO", "title": "CATO CORP"}})
        self.assertEqual(m["CAT"], (18230, "CATERPILLAR INC"))
        self.assertEqual(m[sec_ticker("BRK/B")], (1067983, "BERKSHIRE HATHAWAY INC"))
        self.assertEqual(sec_ticker("BRK.B"), "BRK-B")
        self.assertNotIn("CA", m)


class Filings(unittest.TestCase):
    def setUp(self):
        self.rows = filings("MU", 723125, "MICRON TECHNOLOGY INC", SUBMISSIONS, SINCE)

    def test_only_wanted_forms_inside_the_window_with_a_real_date(self):
        self.assertEqual([r["id"] for r in self.rows], ["0000723125-26-000041", "0000723125-26-000039"])

    def test_row_fields(self):
        r = self.rows[0]
        self.assertEqual((r["symbol"], r["form"], r["filed"], r["source"]), ("MU", "8-K", "2026-11-10", "SEC EDGAR"))
        self.assertEqual(r["label"], "Form 8-K: results of operations")
        self.assertEqual(r["url"], "https://www.sec.gov/Archives/edgar/data/723125/000072312526000041/0000723125-26-000041-index.htm")


class Merge(unittest.TestCase):
    def row(self, i, sym, filed):
        return {"id": i, "symbol": sym, "filed": filed}

    def test_failed_symbols_keep_previous_items_and_others_do_not(self):
        previous = [self.row("a", "MU", "2026-11-09"), self.row("b", "CAT", "2026-11-08"), self.row("old", "MU", "2026-10-01")]
        fresh = [self.row("c", "CAT", "2026-11-10")]
        out = merge(previous, fresh, {"MU"}, SINCE)
        self.assertEqual([r["id"] for r in out], ["c", "a"])   # newest first; CAT's old row is replaced, MU's stale row dropped

    def test_one_row_per_filing(self):
        out = merge([self.row("a", "MU", "2026-11-09")], [self.row("a", "MU", "2026-11-09")], {"MU"}, SINCE)
        self.assertEqual(len(out), 1)


if __name__ == "__main__":
    unittest.main()
