"""Write web/data/history/<SYMBOL>.json: one year of daily closes plus key stats per holding.

The web view's holding detail dialog draws its chart and indicator readings from these files,
so the page needs no third-party script. Same snapshot caveat as snapshot_quotes.py: Yahoo
Finance data for internal club use and demos, not a licensed public-display feed.

Run:  python3 tools/snapshot_history.py          (about 20 s for 18 symbols)
"""
import datetime
import json
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "data" / "source"
OUT = ROOT / "web" / "data" / "history"
UA = {"User-Agent": "Mozilla/5.0"}


def fetch(sym):
    y = sym.replace("/", "-")
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{y}?interval=1d&range=1y"
    req = urllib.request.Request(url, headers=UA)
    res = json.load(urllib.request.urlopen(req, timeout=20))["chart"]["result"][0]
    meta, ts = res["meta"], res["timestamp"]
    closes = res["indicators"]["quote"][0]["close"]
    adj = (res["indicators"].get("adjclose") or [{}])[0].get("adjclose") or closes
    points = [{"date": datetime.datetime.fromtimestamp(t, datetime.timezone.utc).strftime("%Y-%m-%d"),
               "close": round(c, 4)}
              for t, c in zip(ts, closes) if c is not None]
    asof = datetime.datetime.fromtimestamp(meta["regularMarketTime"], datetime.timezone.utc)
    return {
        "symbol": sym, "name": meta.get("longName") or meta.get("shortName"), "exchange": meta.get("fullExchangeName"),
        "currency": meta.get("currency", "USD"),
        "as_of_utc": asof.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "price": meta.get("regularMarketPrice"), "previous_close": meta.get("chartPreviousClose"),
        "day_high": meta.get("regularMarketDayHigh"), "day_low": meta.get("regularMarketDayLow"),
        "volume": meta.get("regularMarketVolume"),
        "week52_high": meta.get("fiftyTwoWeekHigh"), "week52_low": meta.get("fiftyTwoWeekLow"),
        "closes": points,
        "source": "Yahoo Finance chart API snapshot (daily closes, unadjusted)",
        "retrieved_at_utc": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


def main():
    positions = json.loads((SRC / "positions.json").read_text(encoding="utf-8"))
    symbols = [p["symbol"] for p in positions["opening_positions"]]
    OUT.mkdir(parents=True, exist_ok=True)
    done = 0
    for s in symbols:
        try:
            data = fetch(s)
        except Exception as e:  # keep the previous file for this symbol
            print(f"{s}: fetch failed, previous file kept: {e}", file=sys.stderr)
            continue
        if len(data["closes"]) < 100:
            print(f"{s}: only {len(data['closes'])} closes, previous file kept", file=sys.stderr)
            continue
        (OUT / f"{s.replace('/', '-')}.json").write_text(json.dumps(data, indent=1), encoding="utf-8")
        done += 1
        time.sleep(0.3)
    print(f"wrote {done} of {len(symbols)} history files to {OUT}")
    if done != len(symbols):
        sys.exit(1)


if __name__ == "__main__":
    main()
