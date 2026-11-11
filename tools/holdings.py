"""Holdings at any moment: the Sept 22 statement positions plus recorded trades.

data/source/positions.json keeps the statement positions frozen in `opening_positions` and
adds every later trade to `transactions`. Each trade takes effect at `executed_at_utc`.
A buy adds shares and cost (price x shares + fees). A sell removes shares and removes cost
pro rata (average cost). The money a trade moves counts as an outside flow, because the
club's cash balance is not on record: it is not gain and not loss.

build.py, tools/snapshot_quotes.py and tools/snapshot_history.py all read holdings here,
so a new symbol is fetched, valued and shown from one recorded trade.
"""
from decimal import Decimal

STATEMENT_DATE = "2026-09-22"


def dec(x):
    return Decimal(str(x))


def _check(t):
    """Refuse a trade row the build cannot value honestly. Returns the row unchanged."""
    tid = t.get("id") or f"{t.get('type')} {t.get('symbol')}"
    if t.get("status") != "confirmed":
        raise ValueError(f"transaction {tid}: status is {t.get('status')!r}, not 'confirmed'")
    if t.get("type") not in ("buy", "sell"):
        raise ValueError(f"transaction {tid}: type {t.get('type')!r} is not supported (buy, sell)")
    for k in ("symbol", "executed_at_utc", "shares", "price"):
        if not t.get(k):
            raise ValueError(f"transaction {tid}: {k} is missing")
    if not (dec(t["shares"]) > 0 and dec(t["price"]) > 0):
        raise ValueError(f"transaction {tid}: shares and price must be greater than zero")
    if t.get("fees") is not None and dec(t["fees"]) < 0:
        raise ValueError(f"transaction {tid}: fees cannot be negative")
    if t["executed_at_utc"][:10] <= STATEMENT_DATE:
        raise ValueError(f"transaction {tid}: dated on or before the {STATEMENT_DATE} statement")
    return t


def transactions(positions):
    """Confirmed trades, checked, oldest first."""
    return sorted((_check(t) for t in positions.get("transactions") or []), key=lambda t: t["executed_at_utc"])


def trade_amount(t):
    """Cash that left (buy, positive) or came back (sell, negative) for one trade."""
    gross = dec(t["shares"]) * dec(t["price"])
    fees = dec(t["fees"]) if t.get("fees") is not None else Decimal(0)
    return gross + fees if t["type"] == "buy" else -(gross - fees)


def holdings_at(positions, ts=None):
    """(shares, cost) dicts per symbol, for trades effective at or before `ts` (ISO UTC); None = all.
    Symbols with zero shares are left out. Order: statement symbols first, then by first buy."""
    shares, cost, _ = _walk(positions, ts)
    return shares, cost


def realized_gains(positions, ts=None):
    """One row per sell at or before `ts`: proceeds (after fees), the average cost removed, gain."""
    return _walk(positions, ts)[2]


def _walk(positions, ts):
    realized = []
    shares = {p["symbol"]: dec(p["shares"]) for p in positions["opening_positions"]}
    cost = {p["symbol"]: dec(p["cost_basis"]) for p in positions["opening_positions"]}
    for t in transactions(positions):
        if ts is not None and t["executed_at_utc"] > ts:
            break
        s, n = t["symbol"], dec(t["shares"])
        if t["type"] == "buy":
            shares[s] = shares.get(s, Decimal(0)) + n
            cost[s] = cost.get(s, Decimal(0)) + trade_amount(t)
        else:
            held = shares.get(s, Decimal(0))
            if n > held:
                raise ValueError(f"transaction {t.get('id')}: sells {n} {s} but only {held} are held")
            removed = cost[s] * n / held
            realized.append({"id": t.get("id"), "symbol": s, "executed_at_utc": t["executed_at_utc"],
                             "estimated": bool(t.get("estimated")), "proceeds": -trade_amount(t),
                             "cost": removed, "gain": -trade_amount(t) - removed})
            cost[s] = cost[s] - removed
            shares[s] = held - n
    keep = [s for s in shares if shares[s] > 0]
    return {s: shares[s] for s in keep}, {s: cost[s] for s in keep}, realized


def current_symbols(positions):
    return list(holdings_at(positions)[0])


def flows_between(positions, t0, t1):
    """Net outside flow (dollars) from trades effective after t0 and at or before t1."""
    return sum((trade_amount(t) for t in transactions(positions) if t0 < t["executed_at_utc"] <= t1), Decimal(0))

