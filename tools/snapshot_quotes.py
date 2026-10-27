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
HEALTH = ROOT / "web" / "data" / "refresh-health.json"
UA = {"User-Agent": "Mozilla/5.0"}


def yahoo(sym):
    y = sym.replace("/", "-")
    req = urllib.request.Request(f"https://query1.finance.yahoo.com/v8/finance/chart/{y}?interval=1d&range=1d", headers=UA)
    return json.load(urllib.request.urlopen(req, timeout=15))["chart"]["result"][0]["meta"]


def one_line(exc):
    """An exception as the single line the health record can hold."""
    return " ".join(f"{type(exc).__name__}: {exc}".split())[:200]


def write_health(attempted_at_utc, ok, requested, written, error):
    """Published with the site (web/data/, served by Pages): the pages show whether the
    last refresh attempt ran and what happened, even when it failed."""
    rec = {"attempted_at_utc": attempted_at_utc, "ok": ok, "provider": "yahoo-snapshot",
           "symbols_requested": requested, "symbols_written": written, "error": error}
    HEALTH.parent.mkdir(parents=True, exist_ok=True)
    HEALTH.write_text(json.dumps(rec, indent=1) + "\n", encoding="utf-8")


def main():
    now = datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0)
    f = lambda d: d.strftime("%Y-%m-%dT%H:%M:%SZ")
    symbols, rows, error = [], [], None
    try:
        positions = json.loads((SRC / "positions.json").read_text(encoding="utf-8"))
        symbols = [p["symbol"] for p in positions["opening_positions"]]
        for s in symbols:
            m = yahoo(s)
            t = datetime.datetime.fromtimestamp(m["regularMarketTime"], datetime.timezone.utc)
            rows.append({
                "symbol": s, "price": f"{m['regularMarketPrice']:.2f}", "previous_close": f"{(m.get('regularMarketPreviousClose') or m.get('previousClose') or m['chartPreviousClose']):.2f}",
                "currency": m.get("currency", "USD"), "provider_update_at_utc": f(t), "retrieved_at_utc": f(now),
                "session": "regular" if m.get("currentTradingPeriod") and m["currentTradingPeriod"]["regular"]["start"] <= m["regularMarketTime"] < m["currentTradingPeriod"]["regular"]["end"] else "closed",
                "provider": "Yahoo Finance (snapshot)", "source_url": f"https://finance.yahoo.com/quote/{s.replace('/', '-')}/",
                "delay_label": "Snapshot of Yahoo Finance's quote page; personal-use data, not licensed for public display",
            })
            time.sleep(0.3)
    except Exception as e:
        error = one_line(e)
    ok = error is None and len(rows) == len(symbols)
    # On failure the previous quotes-current.json / api files are kept and the record still
    # says what happened; the process still exits non-zero so the workflow run stays red.
    write_health(f(now), ok, len(symbols), len(rows),
                 error if error else (None if ok else f"got {len(rows)} of {len(symbols)} quotes"))
    if not ok:
        sys.exit(f"got {len(rows)} of {len(symbols)} quotes; nothing written" + (f"; {error}" if error else ""))
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
