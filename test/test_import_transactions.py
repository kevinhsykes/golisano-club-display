"""Tests for tools/import_transactions.py (python3 -m unittest test/test_import_transactions.py -v).

Runs the importer against checked-in fixture CSVs and a temp copy of the real
positions.json; the real file is never modified by these tests.
"""
import contextlib, importlib.util, io, json, tempfile, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "tools" / "import_transactions.py"
FIXTURES = ROOT / "test" / "fixtures"
POSITIONS = ROOT / "data" / "source" / "positions.json"

spec = importlib.util.spec_from_file_location("import_transactions", SCRIPT)
imp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(imp)


def run(argv):
    """Run the script's main(); returns (exit_code, stdout)."""
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        code = imp.main(argv)
    return code, out.getvalue()


class ImportTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.positions = Path(self.tmp.name) / "positions.json"
        self.positions.write_bytes(POSITIONS.read_bytes())
        # Deterministic baseline: start every test from an empty transactions[] no matter
        # what the real file currently holds, keeping the file's formatting style.
        doc = json.loads(self.positions.read_text(encoding="utf-8"))
        doc["transactions"] = []
        self.positions.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")

    def transactions(self):
        return json.loads(self.positions.read_text(encoding="utf-8"))["transactions"]

    def import_sample(self, extra=()):
        return run([str(FIXTURES / "transactions-sample.csv"), "--positions", str(self.positions), *extra])


class TestImportTransactions(ImportTestCase):
    def test_buy_sell_dividend_reinvest_rows(self):
        code, _ = self.import_sample()
        self.assertEqual(code, 0)
        self.assertEqual(self.transactions(), [
            {"date": "2026-01-05", "symbol": "AAPL", "type": "buy", "shares": "2.0000", "price": "190.25"},
            {"date": "2026-02-10", "symbol": "MSFT", "type": "sell", "shares": "1.0000", "price": "415.60"},
            {"date": "2026-03-01", "symbol": "KO", "type": "dividend", "shares": "0.0000", "price": "0.485"},  # amount kept at CSV precision, never rounded
            {"date": "2026-03-15", "symbol": "VTI", "type": "dividend", "shares": "0.2417", "price": "290.50"},
        ])

    def test_reimport_is_idempotent(self):
        code, _ = self.import_sample()
        self.assertEqual(code, 0)
        snapshot = self.positions.read_bytes()
        code, again = self.import_sample()
        self.assertEqual(code, 0)
        self.assertIn("added 0 row(s)", again)
        self.assertIn("now 4 transaction(s) (4 already present", again)
        self.assertEqual(self.positions.read_bytes(), snapshot)  # second run wrote nothing new

    def test_unknown_action_is_hard_error_naming_line(self):
        code, _ = run([str(FIXTURES / "transactions-bad-action.csv"), "--positions", str(self.positions)])
        self.assertEqual(code, 2)
        err = io.StringIO()
        with self.assertRaises(imp.ImportRowError) as cm:
            imp.parse_csv(FIXTURES / "transactions-bad-action.csv")
        err.write(str(cm.exception))
        self.assertIn("line 3", err.getvalue())
        self.assertIn("unknown action", err.getvalue())

    def test_dry_run_leaves_positions_json_byte_identical(self):
        before = self.positions.read_bytes()
        code, out = self.import_sample(extra=["--dry-run"])
        self.assertEqual(code, 0)
        self.assertIn("file not written", out)
        self.assertIn('"type": "buy"', out)
        self.assertEqual(self.positions.read_bytes(), before)

    def test_other_keys_stay_byte_identical(self):
        orig = json.loads(POSITIONS.read_text(encoding="utf-8"))
        self.import_sample()
        new = json.loads(self.positions.read_text(encoding="utf-8"))
        del orig["transactions"], new["transactions"]
        self.assertEqual(orig, new)
        # Formatting style is preserved too (indent=2 + trailing newline, like the repo file).
        text = self.positions.read_text(encoding="utf-8")
        self.assertEqual(text, json.dumps(json.loads(text), indent=2) + "\n")

    def test_header_and_value_tolerant_parsing(self):
        csv = Path(self.tmp.name) / "odd.csv"
        csv.write_text(
            '"  Trade  Date ",Symbol, ACTIVITY ,Qty,Price Per Share\n'
            "01/05/2026,AAPL,Buy To Open,1.5,$75.10\n"
            "\n"
            "2026-01-06,V, cash dividend ,,1.20\n",
            encoding="utf-8")
        code, _ = run([str(csv), "--positions", str(self.positions)])
        self.assertEqual(code, 0)
        self.assertEqual(self.transactions(), [
            {"date": "2026-01-05", "symbol": "AAPL", "type": "buy", "shares": "1.5000", "price": "75.10"},
            {"date": "2026-01-06", "symbol": "V", "type": "dividend", "shares": "0.0000", "price": "1.20"},
        ])

    def test_missing_shares_on_buy_names_line(self):
        csv = Path(self.tmp.name) / "bad.csv"
        csv.write_text("Date,Symbol,Action,Shares,Price\n2026-01-05,AAPL,Buy,,190.25\n", encoding="utf-8")
        with self.assertRaises(imp.ImportRowError) as cm:
            imp.parse_csv(csv)
        self.assertIn("line 2", str(cm.exception))

    def test_cash_dividend_prefers_explicit_amount_over_price(self):
        csv = Path(self.tmp.name) / "div-amount.csv"
        csv.write_text(
            "Date,Symbol,Action,Shares,Price,Amount\n"
            "2026-01-05,AAPL,Dividend,0,0.25,12.34\n"  # a per-share price is present; the cash amount wins
            "2026-01-06,MSFT,Dividend,0,0,5.67\n",       # zero per-share price no longer rejects the row
            encoding="utf-8")
        code, _ = run([str(csv), "--positions", str(self.positions)])
        self.assertEqual(code, 0)
        self.assertEqual(self.transactions(), [
            {"date": "2026-01-05", "symbol": "AAPL", "type": "dividend", "shares": "0.0000", "price": "12.34"},
            {"date": "2026-01-06", "symbol": "MSFT", "type": "dividend", "shares": "0.0000", "price": "5.67"},
        ])

    def test_reinvest_without_shares_is_a_hard_error_naming_line(self):
        csv = Path(self.tmp.name) / "reinvest-no-shares.csv"
        csv.write_text("Date,Symbol,Action,Amount\n2026-03-15,VTI,Reinvest,70.21\n", encoding="utf-8")
        code, _ = run([str(csv), "--positions", str(self.positions)])
        self.assertEqual(code, 2)
        self.assertEqual(self.transactions(), [])  # nothing was written
        with self.assertRaises(imp.ImportRowError) as cm:
            imp.parse_csv(csv)
        self.assertIn("line 2", str(cm.exception))
        self.assertIn("reinvest", str(cm.exception))

    def test_non_finite_numbers_are_rejected_naming_line(self):
        for value in ("Infinity", "NaN"):
            csv = Path(self.tmp.name) / f"nonfinite-{value.lower()}.csv"
            csv.write_text(
                f"Date,Symbol,Action,Shares,Price\n2026-01-05,AAPL,Buy,{value},190.25\n",
                encoding="utf-8")
            code, _ = run([str(csv), "--positions", str(self.positions)])
            self.assertEqual(code, 2, value)
            self.assertEqual(self.transactions(), [], value)  # nothing was written
            with self.assertRaises(imp.ImportRowError) as cm:
                imp.parse_csv(csv)
            self.assertIn("line 2", str(cm.exception), value)
            self.assertIn("finite", str(cm.exception), value)

    def test_trade_date_beats_settlement_date_in_either_order(self):
        cases = [
            ("Settlement Date,Trade Date", "2026-01-07,2026-01-05"),
            ("Trade Date,Settlement Date", "2026-01-05,2026-01-07"),
        ]
        for header, dates in cases:
            csv = Path(self.tmp.name) / "two-dates.csv"
            csv.write_text(
                f"{header},Symbol,Action,Shares,Price\n"
                f"{dates},AAPL,Buy,2,190.25\n",
                encoding="utf-8")
            code, _ = run([str(csv), "--positions", str(self.positions)])
            self.assertEqual(code, 0, header)
            self.assertEqual(self.transactions(), [
                {"date": "2026-01-05", "symbol": "AAPL", "type": "buy",
                 "shares": "2.0000", "price": "190.25"},
            ], header)

    def test_settlement_date_only_is_a_hard_error_naming_header(self):
        csv = Path(self.tmp.name) / "settle-only.csv"
        csv.write_text(
            "Settlement Date,Symbol,Action,Shares,Price\n"
            "2026-01-07,AAPL,Buy,2,190.25\n",
            encoding="utf-8")
        code, _ = run([str(csv), "--positions", str(self.positions)])
        self.assertEqual(code, 2)
        self.assertEqual(self.transactions(), [])  # nothing was written
        with self.assertRaises(imp.ImportRowError) as cm:
            imp.parse_csv(csv)
        self.assertIn("'Settlement Date'", str(cm.exception))
        self.assertIn("trade date", str(cm.exception))


if __name__ == "__main__":
    unittest.main()
