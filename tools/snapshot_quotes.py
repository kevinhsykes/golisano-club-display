"""Refresh data/source/quotes-current.json and web/api/quotes from a public quote page.

This is a SNAPSHOT for internal club review and demos. It is not a licensed live feed for a
public screen; the licensed path is the Cloudflare Worker (worker/index.js) on Twelve Data or
Tiingo. Run:  python3 tools/snapshot_quotes.py   then   python3 build.py && python3 build.py --public --out web/data/portfolio.public.json
"""
import json, sys, time, datetime, urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "data" / "source"
API = ROOT / "web" / "api" / "quotes"
UA = {"User-Agent": "Mozilla/5.0"}


def yahoo(sym):
    y = sym.replace("/", "-")
    req = urllib.request.Request(f"https://query1.finance.yahoo.com/v8/finance/chart/{y}?interval=1d&range=1d", headers=UA)
    return json.load(urllib.request.urlopen(req, timeout=15))["chart"]["result"][0]["meta"]


def main():
    positions = json.loads((SRC / "positions.json").read_text(encoding="utf-8"))
    symbols = [p["symbol"] for p in positions["opening_positions"]]
    now = datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0)
    f = lambda d: d.strftime("%Y-%m-%dT%H:%M:%SZ")
    rows = []
    for s in symbols:
        m = yahoo(s)
        t = datetime.datetime.fromtimestamp(m["regularMarketTime"], datetime.timezone.utc)
        rows.append({
            "symbol": s, "price": f"{m['regularMarketPrice']:.2f}", "previous_close": f"{m['chartPreviousClose']:.2f}",
            "currency": m.get("currency", "USD"), "provider_update_at_utc": f(t), "retrieved_at_utc": f(now),
            "session": "regular" if m.get("currentTradingPeriod") and m["currentTradingPeriod"]["regular"]["start"] <= m["regularMarketTime"] < m["currentTradingPeriod"]["regular"]["end"] else "closed",
            "provider": "Yahoo Finance (snapshot)", "source_url": f"https://finance.yahoo.com/quote/{s.replace('/', '-')}/",
            "delay_label": "Snapshot of Yahoo Finance's quote page; personal-use data, not licensed for public display",
        })
        time.sleep(0.3)
    if len(rows) != len(symbols):
        sys.exit(f"got {len(rows)} of {len(symbols)} quotes; nothing written")
    old = json.loads((SRC / "quotes-current.json").read_text(encoding="utf-8"))
    hist_path = SRC / "historical-quotes.json"
    hist = json.loads(hist_path.read_text(encoding="utf-8"))
    # Keep one saved snapshot per day in history (the last one for that day wins).
    if old["collected_at_utc"][:10] != f(now)[:10] and old["collected_at_utc"] not in [h["collected_at_utc"] for h in hist]:
        hist.append(old)
        hist_path.write_text(json.dumps(hist, indent=1), encoding="utf-8")
    snap = {"schema": "portfolio-quotes.v1", "collected_at_utc": f(now), "quotes": rows,
            "note": "Snapshot for internal club review and demos; not a licensed feed for public display."}
    (SRC / "quotes-current.json").write_text(json.dumps(snap, indent=1), encoding="utf-8")
    # Static stand-in for the Worker's /api/quotes so the pages work without Cloudflare.
    api = {"schema": "portfolio-quotes.v1", "collected_at_utc": f(now),
           "quotes": [{k: q[k] for k in ("symbol", "price", "previous_close", "provider_update_at_utc", "retrieved_at_utc", "session", "provider", "source_url")} for q in rows],
           "meta": None, "health": {"attempted_at_utc": f(now), "provider": "yahoo-snapshot", "ok": True}}
    API.parent.mkdir(parents=True, exist_ok=True)
    API.write_text(json.dumps(api, indent=1), encoding="utf-8")
    newest = max(q["provider_update_at_utc"] for q in rows)
    print(f"wrote {len(rows)} quotes, collected {f(now)}, newest quote {newest}")


if __name__ == "__main__":
    main()
