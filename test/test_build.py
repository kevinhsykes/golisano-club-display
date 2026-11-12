"""build.py guards, run against a scratch copy of the inputs: python3 -m unittest discover -s test -p 'test_*.py'"""
import datetime
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


class BuildGuards(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="club-build-"))
        shutil.copy(ROOT / "build.py", self.tmp)
        shutil.copytree(ROOT / "tools", self.tmp / "tools", ignore=shutil.ignore_patterns("__pycache__"))
        shutil.copytree(ROOT / "data", self.tmp / "data")
        (self.tmp / "web").mkdir()
        self.src = self.tmp / "data" / "source"

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def build(self):
        return subprocess.run([sys.executable, "build.py", "--out", str(self.tmp / "out.json")], cwd=self.tmp,
                              capture_output=True, text=True)

    def edit(self, name, fn):
        p = self.src / name
        d = json.loads(p.read_text())
        fn(d)
        p.write_text(json.dumps(d))

    def test_builds_as_committed(self):
        r = self.build()
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_saved_snapshot_without_a_held_symbol_is_skipped_not_fatal(self):
        # A snapshot saved after the MU/CAT buy but before they were recorded (no MU/CAT quotes).
        cur = json.loads((self.src / "quotes-current.json").read_text())
        stale = {**cur, "collected_at_utc": "2026-11-11T18:32:11Z",
                 "quotes": [{**q, "provider_update_at_utc": "2026-11-11T18:32:00Z"} for q in cur["quotes"] if q["symbol"] not in ("MU", "CAT")]}
        self.edit("historical-quotes.json", lambda h: h.append(stale))
        r = self.build()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("skipped", r.stderr)
        out = json.loads((self.tmp / "out.json").read_text())
        self.assertNotIn("2026-11-11T18:32:00Z", [h["as_of_utc"] for h in out["history"]])

    def test_current_quotes_missing_a_holding_refuses(self):
        self.edit("quotes-current.json", lambda d: d.update(quotes=[q for q in d["quotes"] if q["symbol"] != "MU"]))
        r = self.build()
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("MU", r.stderr)

    def test_trade_after_the_newest_quote_refuses(self):
        # Derive the time from the saved quotes: a fixed date stops being "late" once newer quotes land.
        cur = json.loads((self.src / "quotes-current.json").read_text())
        newest = max(datetime.datetime.fromisoformat(q["provider_update_at_utc"].replace("Z", "+00:00"))
                     for q in cur["quotes"])
        late = newest + datetime.timedelta(minutes=5)

        def add(d):
            d["transactions"].append({"id": "late", "type": "buy", "symbol": "AAPL", "trade_date": late.date().isoformat(),
                                      "executed_at_utc": late.strftime("%Y-%m-%dT%H:%M:%SZ"), "shares": "1", "price": "355",
                                      "fees": None, "status": "confirmed"})
        self.edit("positions.json", add)
        r = self.build()
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("after the newest saved quote", r.stderr)

    def test_unconfirmed_trade_refuses(self):
        self.edit("positions.json", lambda d: d["transactions"][0].update(status="pending_fill"))
        r = self.build()
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("pending_fill", r.stderr)


if __name__ == "__main__":
    unittest.main()
