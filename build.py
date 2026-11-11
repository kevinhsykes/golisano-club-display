"""Build web/data/portfolio.json for the TV and Canvas views.

Inputs live in data/source/ (copied from the KPC personal-portfolio repo):
  positions.json, statement-20260922.csv, quotes-current.json,
  historical-quotes.json, instrument-profiles.json, xnys-calendar.json

positions.json keeps the Sept 22 statement in `opening_positions` (checked against the CSV)
and records every later trade in `transactions` (see tools/holdings.py). Each history point
is valued with the holdings held at that moment, so a new buy never changes past points, and
the return since the statement is time-weighted: the money a trade moves is not gain.

Run:  python build.py            -> web/data/portfolio.json, full (dollar amounts included)
      python build.py --public --out web/data/portfolio.public.json
                                 -> percent-only payload (no shares, basis or dollars)

The public payload omits the data itself; hiding numbers with CSS is not enough
for a page anyone can open.
"""
import csv, subprocess, datetime
import json
import sys
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "tools"))
from holdings import holdings_at, transactions, trade_amount, flows_between, realized_gains  # noqa: E402
SRC = ROOT / "data" / "source"
OUT = ROOT / "web" / "data" / "portfolio.json"

# Sept 29 composite value recorded by the earlier dashboard (after-hours last trades,
# unchanged statement shares). Its per-symbol quotes are not in data/source.
SEPT29 = {"date": "2026-09-29", "as_of_utc": "2026-09-29T23:59:51Z", "value": "107591.94", "spy": "764.20",
          "kind": "after-hours composite",
          "note": "Sum of statement shares x Sept 29 after-hours last trades"}


def dec(x):
    return Decimal(str(x))


def money(x):
    return str(dec(x).quantize(Decimal("0.01"), ROUND_HALF_UP))


def load(name):
    return json.loads((SRC / name).read_text(encoding="utf-8"))


def snapshot_value(shares, quotes, when=""):
    by = {q["symbol"]: q for q in quotes}
    missing = [s for s in shares if s not in by]
    if missing:
        raise SystemExit(f"snapshot {when} missing symbols held then: {missing}")
    return sum(shares[s] * dec(by[s]["price"]) for s in shares)


def write_version(out_dir):
    """web/version.json: the deployed build id. Pages poll it every minute and reload when it changes,
    so an improvement pushed to main reaches a TV that only holds the URL within about a minute."""
    try:
        build = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()
    except Exception:
        build = "unknown"
    built = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    (out_dir / "version.json").write_text(json.dumps({"build": build, "built_at_utc": built}) + "\n", encoding="utf-8")


def disclosure(trades):
    base = "Holdings: the Sept 22, 2026 statement"
    if trades:
        last = max(t["trade_date"] for t in trades)
        d = datetime.date.fromisoformat(last)
        base += f" plus trades recorded through {d.strftime('%b')} {d.day}"
        if any(t.get("estimated") for t in trades):
            base += " (some at estimated prices until the brokerage fills are recorded)"
    return (base + ". Cash, dividends and unrecorded fees are not included. Return since Sept 22 is "
            "time-weighted, so money moved by a trade is not counted as gain or loss. "
            "Educational display, not investment advice.")


def main(public, out):
    positions = load("positions.json")
    profiles = {p["symbol"]: p for p in load("instrument-profiles.json")["instruments"]}
    names = {i["symbol"]: i["name"] for i in positions["instruments"]}
    tv_symbols = {i["symbol"]: i.get("tv_symbol") for i in positions["instruments"]}
    with open(SRC / "statement-20260922.csv", newline="", encoding="utf-8") as fh:
        statement = {r["symbol"]: r for r in csv.DictReader(fh)}

    open_shares = {p["symbol"]: dec(p["shares"]) for p in positions["opening_positions"]}
    open_basis = {p["symbol"]: dec(p["cost_basis"]) for p in positions["opening_positions"]}
    if set(open_shares) != set(statement):
        raise SystemExit("positions.json opening_positions and statement CSV disagree on symbols")
    for sym, row in statement.items():
        if open_shares[sym] != dec(row["shares"]) or open_basis[sym] != dec(row["cost_basis"]):
            raise SystemExit(f"positions.json and statement CSV disagree on {sym}: "
                             f"shares {open_shares[sym]} vs {row['shares']}, basis {open_basis[sym]} vs {row['cost_basis']}")
    try:
        trades = transactions(positions)
        shares, basis = holdings_at(positions)          # held now: statement + every recorded trade
    except ValueError as e:
        raise SystemExit(f"positions.json: {e}")
    missing_tv = [s for s in shares if not tv_symbols.get(s)]
    if missing_tv:
        raise SystemExit(f"positions.json instruments need a tv_symbol for: {missing_tv}")

    current = load("quotes-current.json")
    history_snaps = load("historical-quotes.json")
    newest_quote = max(q["provider_update_at_utc"] for q in current["quotes"])
    late = [t["id"] for t in trades if t["executed_at_utc"] > newest_quote]
    if late:
        raise SystemExit(f"trades {late} are after the newest saved quote ({newest_quote}); "
                         "run python3 tools/snapshot_quotes.py first")
    no_quote = sorted(set(shares) - {q["symbol"] for q in current["quotes"]})
    if no_quote:
        raise SystemExit(f"quotes-current.json has no quote for current holdings {no_quote}; "
                         "run python3 tools/snapshot_quotes.py")

    statement_value = sum(dec(r["statement_market_value"]) for r in statement.values())
    # SPY on the statement date is implied from its statement value (value / shares).
    spy_statement = (dec(statement["SPY"]["statement_market_value"]) / open_shares["SPY"]).quantize(Decimal("0.01"))
    history = [{"date": "2026-09-22", "as_of_utc": "2026-09-22T13:45:00Z", "value": statement_value, "spy": str(spy_statement),
                "kind": "statement", "note": "Sept 22 statement market value (PDF as of 9:45 AM ET)"}]
    history.append({**SEPT29, "value": dec(SEPT29["value"])})
    for snap in history_snaps + [current]:
        closed = all(q.get("session") == "closed" for q in snap["quotes"])
        latest = max(q["provider_update_at_utc"] for q in snap["quotes"])
        held, _ = holdings_at(positions, latest)
        have = {q["symbol"] for q in snap["quotes"]}
        if snap is not current and not set(held) <= have:
            # Saved before a trade was recorded (e.g. a trade entered a day late): skip the point.
            # The time-weighted chain stays right because flows are summed between kept points.
            print(f"history point {latest} skipped: no quote for {sorted(set(held) - have)}", file=sys.stderr)
            continue
        history.append({"date": latest[:10], "as_of_utc": latest,
                        "value": snapshot_value(held, snap["quotes"], latest),
                        "kind": "close" if closed else "intraday",
                        "spy": next((q["price"] for q in snap["quotes"] if q["symbol"] == "SPY"), None),
                        "note": "Shares held then x saved quotes"})
    # Per point: cost held then, SPY position then, the outside flow since the previous point,
    # and the time-weighted return since the statement (flows count at the start of a period).
    twr, prev = Decimal(0), None
    for pt in history:
        held, cost = holdings_at(positions, pt["as_of_utc"])
        pt["cost"] = sum(cost.values())
        pt["spy_shares"] = held.get("SPY", Decimal(0))
        pt["spy_cost"] = cost.get("SPY", Decimal(0))
        pt["flow"] = flows_between(positions, prev["as_of_utc"], pt["as_of_utc"]) if prev else Decimal(0)
        sold = realized_gains(positions, pt["as_of_utc"])
        pt["realized"] = sum((r["gain"] for r in sold), Decimal(0))      # gain locked in by sales so far
        pt["sold_cost"] = sum((r["cost"] for r in sold), Decimal(0))     # cost basis those sales removed
        if prev:
            twr = (1 + twr) * pt["value"] / (prev["value"] + pt["flow"]) - 1
        pt["twr"] = str(twr.quantize(Decimal("1e-8"), ROUND_HALF_UP))
        prev = pt

    total_basis = sum(basis.values())
    open_total_basis = sum(open_basis.values())
    # First buy of each symbol not on the statement, and the stop rule recorded with its latest buy.
    opened, stops = {}, {}
    for t in trades:
        if t["type"] == "buy":
            if t["symbol"] not in open_shares and t["symbol"] not in opened:
                opened[t["symbol"]] = {"date": t["trade_date"], "executed_at_utc": t["executed_at_utc"],
                                       "time_note": t.get("time_note"), "price": t["price"]}
            stops[t["symbol"]] = t.get("stop_loss")
    holdings = []
    for sym in shares:
        prof = profiles.get(sym, {})
        h = {"symbol": sym, "name": names.get(sym, sym),
             "industry": prof.get("industry"), "type": prof.get("type"),
             "description": prof.get("description"), "ir_url": prof.get("investorRelationsUrl"),
             "tv_symbol": tv_symbols[sym],
             # Six places so units x avg_cost reproduces total cost in the public build.
             "avg_cost": str((basis[sym] / shares[sym]).quantize(Decimal("1e-6"), ROUND_HALF_UP))}
        if sym in opened:
            h["opened"] = opened[sym]
        if stops.get(sym):
            st = stops[sym]
            h["stop"] = {"price": st["price"], "pct_below_buy": st.get("pct_below_buy"),
                         "rule": st.get("rule"), "kind": st.get("kind")}
        if not public:
            h["shares"] = str(shares[sym])
            h["cost_basis"] = money(basis[sym])
        holdings.append(h)
    flows = [{"effective_utc": t["executed_at_utc"], "amount": trade_amount(t)} for t in trades]
    realized = realized_gains(positions)
    # Trade log for web/trades.html. The public build drops share counts and dollar amounts.
    gains = {r["id"]: r for r in realized}
    trade_log = []
    for t in trades:
        row = {"id": t.get("id"), "type": t["type"], "symbol": t["symbol"], "name": names.get(t["symbol"], t["symbol"]),
               "trade_date": t["trade_date"], "executed_at_utc": t["executed_at_utc"], "time_note": t.get("time_note"),
               "price": t["price"], "estimated": bool(t.get("estimated")),
               "price_note": t.get("price_note") or ("Estimated price; replaced when the brokerage fill is recorded."
                                                     if t.get("estimated") else None),
               "stop": ({"price": t["stop_loss"]["price"], "rule": t["stop_loss"].get("rule")} if t.get("stop_loss") else None)}
        if public:
            row["shares_units"] = str((dec(t["shares"]) / open_total_basis).quantize(Decimal("1e-12")))
        else:
            row |= {"shares": t["shares"], "fees": t.get("fees"), "amount": money(abs(trade_amount(t)))}
            if t.get("id") in gains:
                row |= {"realized_gain": money(gains[t["id"]]["gain"]), "cost_removed": money(gains[t["id"]]["cost"])}
        trade_log.append(row)

    if public:
        # Relative units let the page recompute weights from live prices without
        # revealing share counts or dollar size: units = shares / sum(shares * avg_cost).
        # The scale stays the statement's total cost, so units and the index do not move when
        # a trade is recorded; later trades show up as cost above 1.0 in these units.
        scale = open_total_basis
        u = lambda x: str((dec(x) / scale).quantize(Decimal("1e-12")))
        for h in holdings:
            h["units"] = u(shares[h["symbol"]])
        first = history[0]["value"]
        history = [{k: v for k, v in pt.items() if k not in ("value", "cost", "spy_shares", "spy_cost", "flow", "realized", "sold_cost")} |
                   {"index": str((pt["value"] / first * 100).quantize(Decimal("0.000001"))),
                    "cost_units": u(pt["cost"]), "spy_units": u(pt["spy_shares"]), "spy_cost_units": u(pt["spy_cost"]),
                    "flow_units": u(pt["flow"]), "realized_units": u(pt["realized"]), "sold_cost_units": u(pt["sold_cost"])}
                   for pt in history]
        flows = [{"effective_utc": f["effective_utc"], "amount_units": u(f["amount"])} for f in flows]
        realized = [{"symbol": r["symbol"], "executed_at_utc": r["executed_at_utc"], "estimated": r["estimated"],
                     "gain_units": u(r["gain"]), "cost_units": u(r["cost"])} for r in realized]
    else:
        for pt in history:
            for k in ("value", "cost", "spy_cost", "flow", "realized", "sold_cost"):
                pt[k] = money(pt[k])
            pt["spy_shares"] = str(pt["spy_shares"])
        flows = [{"effective_utc": f["effective_utc"], "amount": money(f["amount"])} for f in flows]
        realized = [{"symbol": r["symbol"], "executed_at_utc": r["executed_at_utc"], "estimated": r["estimated"],
                     "gain": money(r["gain"]), "cost": money(r["cost"]), "proceeds": money(r["proceeds"])} for r in realized]

    quotes = [{k: q[k] for k in ("symbol", "price", "previous_close", "provider_update_at_utc",
                                 "retrieved_at_utc", "session", "provider", "source_url")}
              for q in current["quotes"]]

    payload = {
        "schema": "club-display.v1",
        "amounts": "hidden" if public else "shown",
        "club": {"name": "Investment Club", "org": "Golisano Institute"},
        "statement": {"date": "2026-09-22",
                      "value": None if public else money(statement_value),
                      "basis": None if public else money(open_total_basis),
                      "units_value": str((statement_value / open_total_basis).quantize(Decimal("1e-12")))
                      if public else None},
        "disclosure": disclosure(trades),
        "holdings": holdings,
        # Trades after the statement: money moved in (buy) or out (sell). The pages use these to
        # keep the time-weighted return honest between saved points.
        "flows": flows,
        # Gains locked in by sales (proceeds less the average cost removed); the pages add them to
        # unrealized gain so a sale does not look like a loss.
        "realized": realized,
        "trades": trade_log,
        "quotes": {"collected_at_utc": current["collected_at_utc"], "items": quotes, "meta": None},
        # The pages poll this (served by worker/index.js) and fall back to the saved quotes.
        "live_quotes_url": "api/quotes",
        "history": history,
        "calendar": load("xnys-calendar.json"),
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=1, default=str), encoding="utf-8")
    write_version(ROOT / "web")
    print(f"wrote {out} ({'public' if public else 'full'}): "
          f"{len(holdings)} holdings, {len(history)} history points")


if __name__ == "__main__":
    args = sys.argv[1:]
    out = Path(args[args.index("--out") + 1]).resolve() if "--out" in args else OUT
    main(public="--public" in args, out=out)
