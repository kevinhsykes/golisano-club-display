"""Import the club's brokerage trade-history CSV into data/source/positions.json.

docs/TRADE-HISTORY-REQUEST.md asks Dave for the trade history; when that CSV arrives,
one command lands it in the data model:

    python3 tools/import_transactions.py transactions.csv
    python3 tools/import_transactions.py transactions.csv --dry-run   # preview, writes nothing

The CSV needs columns for date, symbol, action/type, shares and price (header names are
matched case- and spacing-insensitively; "Trade Date", "Quantity" and "Unit Price" all work,
and dividend rows may put the cash amount in the price column or an "Amount" column; a cash
dividend with both uses the Amount, which is the payment).
When a file has both a trade date and a settlement/run/process date column, the trade date
is used; a file with only a settlement/run/process date column is rejected.
Supported actions: buy, sell, dividend, reinvest (a reinvested dividend imports as a
dividend row with the shares it bought, which the row must state).

Writes positions.json `transactions[]` rows of the shape the pages expect:
    {"date": "YYYY-MM-DD", "symbol": "AAPL", "type": "buy|sell|dividend",
     "shares": "1.5000", "price": "190.25"}

Rules: only facts in the CSV are written (nothing is inferred or estimated); unknown action
codes are a hard error naming the CSV line; re-running the same file never duplicates rows
(dedupe on date+symbol+type+shares+price); every key of positions.json other than
`transactions[]` stays byte-identical.
"""
import argparse, json, re, sys
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Header cells -> canonical columns (matched lower-cased, trimmed, spaces/hyphens collapsed).
HEADER_ALIASES = {
    "date": {"date", "trade date", "transaction date"},
    "symbol": {"symbol", "ticker"},
    "action": {"action", "type", "action type", "transaction type", "activity", "transaction"},
    "shares": {"shares", "quantity", "qty"},
    "price": {"price", "unit price", "price per share", "share price", "trade price"},
    "amount": {"amount", "total amount", "cash amount"},
}

# Date headers that are the trade date, vs ones that are NOT the trade date. A settlement,
# run or process date is when the trade cleared, not when it happened; if a file offers only
# those, we fail rather than silently record the wrong day.
TRADE_DATE_ALIASES = {"date", "trade date", "transaction date"}
NON_TRADE_DATE_ALIASES = {"settlement date", "run date", "process date"}

# CSV action codes -> the canonical action. A reinvestment is stored as a dividend row
# with the shares it bought — which it must state; a cash dividend may carry none.
ACTION_CODES = {
    "buy": "buy", "buy to open": "buy", "purchase": "buy", "bought": "buy",
    "sell": "sell", "sell to open": "sell", "sell to close": "sell", "sale": "sell", "sold": "sell",
    "dividend": "dividend", "div": "dividend", "cash dividend": "dividend",
    "reinvest": "reinvest", "reinvestment": "reinvest", "dividend reinvest": "reinvest",
    "dividend reinvestment": "reinvest", "reinvested dividend": "reinvest",
    "reinvest shares": "reinvest",
}


class ImportRowError(ValueError):
    """A row we refuse to guess about; message names the CSV line."""


def norm_header(cell):
    return re.sub(r"[\s_-]+", " ", cell.strip().lstrip("﻿").lower()).strip()


def map_headers(row):
    """Map a CSV header row to canonical column names."""
    cols = {}
    date_hits = []  # (column index, is_trade_date) for every date-ish header, in file order
    for i, cell in enumerate(row):
        h = norm_header(cell)
        if not h:
            continue
        if h in TRADE_DATE_ALIASES:
            date_hits.append((i, True))
            continue
        if h in NON_TRADE_DATE_ALIASES:
            date_hits.append((i, False))
            continue
        match = [name for name, aliases in HEADER_ALIASES.items() if h in aliases]
        if match:
            cols.setdefault(match[0], i)  # first occurrence wins
    if date_hits:
        trade = [i for i, is_trade in date_hits if is_trade]
        if trade:
            cols["date"] = trade[0]  # the trade date wins over settlement/run/process dates
        else:
            cols["_non_trade_date"] = date_hits[0][0]  # flagged; parse_csv refuses it
    return cols


def norm_date(raw, name, lineno):
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%m/%d/%Y", "%m/%d/%y"):
        try:
            return datetime.strptime(raw, fmt).strftime("%Y-%m-%d")
        except ValueError:
            pass
    raise ImportRowError(f"{name} line {lineno}: cannot parse date {raw!r}")


def norm_decimal(raw, name, lineno, what, allow_zero):
    try:
        d = Decimal(raw.strip().replace(",", "").replace("$", ""))
    except (InvalidOperation, AttributeError):
        raise ImportRowError(f"{name} line {lineno}: {what} is not a number: {raw!r}")
    if not d.is_finite():
        raise ImportRowError(f"{name} line {lineno}: {what} is not a finite number: {raw!r}")
    if d < 0 or (d == 0 and not allow_zero):
        raise ImportRowError(f"{name} line {lineno}: {what} must be positive: {raw!r}")
    return d


def fmt_number(d, min_dp):
    """Fixed-point string: no exponent, trailing zeros trimmed, at least min_dp decimals."""
    s = format(d, "f")
    if "." not in s:
        return s + "." + "0" * min_dp
    s = s.rstrip("0")
    int_part, dp = s.split(".")
    return int_part + "." + dp.ljust(min_dp, "0")


def parse_csv(path):
    """Parse the brokerage CSV into transactions[] rows. Never invents a fact."""
    import csv
    rows, seen = [], set()
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.reader(f)
        try:
            header = next(reader)
        except StopIteration:
            raise ImportRowError(f"{Path(path).name}: file is empty (no header row)")
        cols = map_headers(header)
        if "_non_trade_date" in cols:
            only = header[cols["_non_trade_date"]].strip()
            raise ImportRowError(
                f"{Path(path).name}: found only a {only!r} column for dates; that is not the "
                f"trade date. Add a trade date column and re-run.")
        missing = [c for c in ("date", "symbol", "action") if c not in cols]
        if missing:
            raise ImportRowError(
                f"{Path(path).name}: header is missing column(s) {', '.join(missing)}; "
                f"found: {[h for h in header if norm_header(h)]}")

        for lineno, raw in enumerate(reader, start=2):
            if not any(cell.strip() for cell in raw):
                continue  # blank line
            need = lambda name: raw[cols[name]].strip() if name in cols and cols[name] < len(raw) else ""
            action = need("action")
            action_code = ACTION_CODES.get(norm_header(action))
            if action_code is None:
                raise ImportRowError(
                    f"{Path(path).name} line {lineno}: unknown action {action!r} "
                    f"(supported: buy, sell, dividend, reinvest)")
            # A reinvestment imports as a dividend row carrying the shares it bought.
            row_type = "dividend" if action_code == "reinvest" else action_code
            is_cash_div = action_code == "dividend"
            date = norm_date(need("date"), Path(path).name, lineno)
            symbol = need("symbol").upper()
            if not symbol:
                raise ImportRowError(f"{Path(path).name} line {lineno}: missing symbol")
            shares_raw, price_raw, amount_raw = need("shares"), need("price"), need("amount")
            if action_code == "reinvest" and not shares_raw:
                raise ImportRowError(
                    f"{Path(path).name} line {lineno}: reinvest row missing shares "
                    f"(a reinvestment stores the shares it bought; a cash dividend may use 0)")
            if action_code in ("buy", "sell") and not shares_raw:
                raise ImportRowError(f"{Path(path).name} line {lineno}: {row_type} row missing shares")
            if row_type == "dividend" and amount_raw and (is_cash_div or not price_raw):
                # Cash dividend: the Amount column is the payment; a per-share price is not.
                # Reinvestment: only when no unit price is given does the amount stand in.
                price_raw = amount_raw
            if not price_raw:
                raise ImportRowError(f"{Path(path).name} line {lineno}: {row_type} row missing price/amount")
            shares = (norm_decimal(shares_raw, Path(path).name, lineno, "shares",
                                   allow_zero=is_cash_div)
                      if shares_raw else Decimal(0))
            price = norm_decimal(price_raw, Path(path).name, lineno, "price", allow_zero=False)
            row = {"date": date, "symbol": symbol, "type": row_type,
                   "shares": fmt_number(shares, 4), "price": fmt_number(price, 2)}
            key = tuple(row.values())
            if key not in seen:
                seen.add(key)
                rows.append(row)
    return rows


def merge(existing, incoming):
    """Append only rows not already in transactions[]; returns (merged, added_count)."""
    present = {tuple(r.get(k, "") for k in ("date", "symbol", "type", "shares", "price"))
               for r in existing}
    merged = list(existing)
    added = 0
    for row in incoming:
        key = tuple(row.values())
        if key not in present:
            present.add(key)
            merged.append(row)
            added += 1
    return merged, added


def main(argv=None):
    ap = argparse.ArgumentParser(description="Import a brokerage trade-history CSV into positions.json.")
    ap.add_argument("csv", help="brokerage transaction-history CSV export")
    ap.add_argument("--positions", default=str(ROOT / "data" / "source" / "positions.json"),
                    help="positions.json to update (default: data/source/positions.json)")
    ap.add_argument("--dry-run", action="store_true",
                    help="print the rows that would be added and write nothing")
    args = ap.parse_args(argv)

    try:
        incoming = parse_csv(args.csv)
        pos_path = Path(args.positions)
        doc = json.loads(pos_path.read_text(encoding="utf-8"))
    except ImportRowError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    merged, added = merge(doc.get("transactions", []), incoming)
    already = len(incoming) - added

    if args.dry_run:
        print(f"would add {added} row(s) to {pos_path} ({already} already present); file not written:")
        for row in incoming:
            marker = " " if tuple(row.values()) in {tuple(r.get(k, "") for k in ("date", "symbol", "type", "shares", "price")) for r in doc.get("transactions", [])} else "+"
            print(f"  {marker} {json.dumps(row)}")
        return 0

    doc["transactions"] = merged
    pos_path.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    print(f"added {added} row(s) to {pos_path}, now {len(merged)} transaction(s) "
          f"({already} already present, unchanged)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
