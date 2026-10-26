"""Build web/data/portfolio.json for the TV and Canvas views.

Inputs live in data/source/ (copied from the KPC personal-portfolio repo):
  positions.json, statement-20260922.csv, quotes-current.json,
  historical-quotes.json, instrument-profiles.json, xnys-calendar.json

Run:  python build.py            -> web/data/portfolio.json, full (dollar amounts included)
      python build.py --public --out web/data/portfolio.public.json
                                 -> percent-only payload (no shares, basis or dollars)

The public payload omits the data itself; hiding numbers with CSS is not enough
for a page anyone can open.
"""
import csv
import json
import sys
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "data" / "source"
OUT = ROOT / "web" / "data" / "portfolio.json"

# Sept 29 composite value recorded by the earlier dashboard (after-hours last trades,
# unchanged statement shares). Its per-symbol quotes are not in data/source.
SEPT29 = {"date": "2026-09-29", "as_of_utc": "2026-09-29T23:59:51Z", "value": "107591.94", "spy": "764.20",
          "kind": "after-hours composite",
          "note": "Sum of statement shares x Sept 29 after-hours last trades"}


# TradingView exchange-prefixed symbols for the detail charts.
TV_SYMBOLS = {"AAPL": "NASDAQ:AAPL", "AMD": "NASDAQ:AMD", "AMZN": "NASDAQ:AMZN", "BRK/B": "NYSE:BRK.B",
              "CEG": "NASDAQ:CEG", "DOCN": "NYSE:DOCN", "GOOGL": "NASDAQ:GOOGL", "LIN": "NASDAQ:LIN",
              "META": "NASDAQ:META", "MKSI": "NASDAQ:MKSI", "MSFT": "NASDAQ:MSFT", "NFLX": "NASDAQ:NFLX",
              "NVDA": "NASDAQ:NVDA", "RDDT": "NYSE:RDDT", "SOFI": "NASDAQ:SOFI", "SPY": "AMEX:SPY",
              "TSLA": "NASDAQ:TSLA", "UPS": "NYSE:UPS"}


def dec(x):
    return Decimal(str(x))


def money(x):
    return str(dec(x).quantize(Decimal("0.01"), ROUND_HALF_UP))


def load(name):
    return json.loads((SRC / name).read_text(encoding="utf-8"))


def snapshot_value(shares, quotes):
    by = {q["symbol"]: q for q in quotes}
    missing = [s for s in shares if s not in by]
    if missing:
        raise SystemExit(f"snapshot missing symbols: {missing}")
    return sum(shares[s] * dec(by[s]["price"]) for s in shares)


def main(public, out):
    positions = load("positions.json")
    profiles = {p["symbol"]: p for p in load("instrument-profiles.json")["instruments"]}
    names = {i["symbol"]: i["name"] for i in positions["instruments"]}
    with open(SRC / "statement-20260922.csv", newline="", encoding="utf-8") as fh:
        statement = {r["symbol"]: r for r in csv.DictReader(fh)}

    shares = {p["symbol"]: dec(p["shares"]) for p in positions["opening_positions"]}
    basis = {p["symbol"]: dec(p["cost_basis"]) for p in positions["opening_positions"]}
    if set(shares) != set(statement):
        raise SystemExit("positions.json and statement CSV disagree on symbols")

    current = load("quotes-current.json")
    history_snaps = load("historical-quotes.json")

    statement_value = sum(dec(r["statement_market_value"]) for r in statement.values())
    # SPY on the statement date is implied from its statement value (value / shares).
    spy_statement = (dec(statement["SPY"]["statement_market_value"]) / shares["SPY"]).quantize(Decimal("0.01"))
    history = [{"date": "2026-09-22", "as_of_utc": "2026-09-22T13:45:00Z", "value": statement_value, "spy": str(spy_statement),
                "kind": "statement", "note": "Sept 22 statement market value (PDF as of 9:45 AM ET)"}]
    history.append({**SEPT29, "value": dec(SEPT29["value"])})
    for snap in history_snaps + [current]:
        closed = all(q.get("session") == "closed" for q in snap["quotes"])
        latest = max(q["provider_update_at_utc"] for q in snap["quotes"])
        history.append({"date": latest[:10], "as_of_utc": latest,
                        "value": snapshot_value(shares, snap["quotes"]),
                        "kind": "close" if closed else "intraday",
                        "spy": next(q["price"] for q in snap["quotes"] if q["symbol"] == "SPY"),
                        "note": "Statement shares x saved quotes"})

    total_basis = sum(basis.values())
    holdings = []
    for sym in shares:
        prof = profiles.get(sym, {})
        h = {"symbol": sym, "name": names.get(sym, sym),
             "industry": prof.get("industry"), "type": prof.get("type"),
             "description": prof.get("description"), "ir_url": prof.get("investorRelationsUrl"),
             "tv_symbol": TV_SYMBOLS[sym],
             # Six places so units x avg_cost reproduces total cost in the public build.
             "avg_cost": str((basis[sym] / shares[sym]).quantize(Decimal("1e-6"), ROUND_HALF_UP))}
        if not public:
            h["shares"] = str(shares[sym])
            h["cost_basis"] = money(basis[sym])
        holdings.append(h)

    if public:
        # Relative units let the page recompute weights from live prices without
        # revealing share counts or dollar size: units = shares / sum(shares * avg_cost).
        scale = total_basis
        for h in holdings:
            h["units"] = str((shares[h["symbol"]] / scale).quantize(Decimal("1e-12")))
        first = history[0]["value"]
        history = [{k: v for k, v in pt.items() if k != "value"} |
                   {"index": str((pt["value"] / first * 100).quantize(Decimal("0.01")))}
                   for pt in history]
    else:
        for pt in history:
            pt["value"] = money(pt["value"])

    quotes = [{k: q[k] for k in ("symbol", "price", "previous_close", "provider_update_at_utc",
                                 "retrieved_at_utc", "session", "provider", "source_url")}
              for q in current["quotes"]]

    payload = {
        "schema": "club-display.v1",
        "amounts": "hidden" if public else "shown",
        "club": {"name": "Investment Club", "org": "Golisano Institute"},
        "statement": {"date": "2026-09-22",
                      "value": None if public else money(statement_value),
                      "basis": None if public else money(total_basis),
                      "units_value": str((statement_value / total_basis).quantize(Decimal("1e-12")))
                      if public else None},
        "disclosure": ("Shares and cost basis come from the Sept 22, 2026 statement and are assumed "
                       "unchanged. Excludes cash, dividends, fees and later trades. Educational display, "
                       "not investment advice."),
        "holdings": holdings,
        "quotes": {"collected_at_utc": current["collected_at_utc"], "items": quotes, "meta": None},
        # The pages poll this (served by worker/index.js) and fall back to the saved quotes.
        "live_quotes_url": "api/quotes",
        "history": history,
        "calendar": load("xnys-calendar.json"),
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=1, default=str), encoding="utf-8")
    print(f"wrote {out} ({'public' if public else 'full'}): "
          f"{len(holdings)} holdings, {len(history)} history points")


if __name__ == "__main__":
    args = sys.argv[1:]
    out = Path(args[args.index("--out") + 1]).resolve() if "--out" in args else OUT
    main(public="--public" in args, out=out)
