#!/usr/bin/env python3
"""Recent SEC filings by the companies the club holds -> web/data/updates.json.

Source: SEC EDGAR only (data.sec.gov submissions API). It is free, needs no key, and the
filing index is a public record. Each item is a factual label ("Micron filed Form 8-K:
results of operations") and a link to the filing on sec.gov. No article text is copied and
no summary is written. Publisher and aggregator news feeds are left out on purpose: their
terms do not clearly allow showing headlines on a public page and a public TV.

SEC fair-access rules: declare who is calling in the User-Agent (a name and a contact email)
and stay far below 10 requests a second. Set SEC_USER_AGENT, for example
"Golisano Investment Club display contact@example.edu". Without it nothing is fetched.

A symbol whose fetch fails keeps its previous items; the file records which symbols failed.
Funds (SPY) are skipped: a fund's filings are not company news.
"""
import datetime
import json
import os
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
from holdings import current_symbols  # noqa: E402

OUT = ROOT / "web" / "data" / "updates.json"
TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik:010d}.json"
FORMS = ("8-K", "10-Q", "10-K")
KEEP_DAYS = 10          # the pages show fewer days; this is only what the file carries
SKIP = {"SPY"}          # funds
SOURCE = "SEC EDGAR"

# Form 8-K item numbers, in plain words (sec.gov/files/form8-k.pdf). Unknown items are not guessed.
ITEMS_8K = {
    "1.01": "a material agreement", "1.02": "the end of a material agreement", "1.03": "bankruptcy or receivership",
    "1.05": "a material cybersecurity incident",
    "2.01": "a completed acquisition or sale of assets", "2.02": "results of operations",
    "2.03": "a new financial obligation", "2.05": "exit or restructuring costs", "2.06": "a material impairment",
    "3.01": "a listing notice", "3.02": "an unregistered sale of shares", "3.03": "a change to shareholder rights",
    "4.01": "a change of auditor", "4.02": "earlier financial statements that should not be relied on",
    "5.01": "a change in control", "5.02": "a director or officer change", "5.03": "a change to its bylaws or fiscal year",
    "5.07": "shareholder vote results", "7.01": "a Regulation FD disclosure", "8.01": "other events",
}
ROUTINE = {"9.01"}      # "financial statements and exhibits" accompanies almost every 8-K


def label(form, items):
    """What the filing is, without interpreting it."""
    if form == "10-Q":
        return "Form 10-Q: quarterly report"
    if form == "10-K":
        return "Form 10-K: annual report"
    named = [ITEMS_8K[i] for i in (x.strip() for x in (items or "").split(",")) if i in ITEMS_8K and i not in ROUTINE]
    return "Form 8-K: " + "; ".join(named[:2]) if named else "Form 8-K: current report"


def sec_ticker(symbol):
    return symbol.replace("/", "-").replace(".", "-").upper()


def cik_map(tickers_json):
    """SEC's own ticker file -> {ticker: (cik, company name)}. Exact ticker match only."""
    return {str(r["ticker"]).upper(): (int(r["cik_str"]), str(r["title"])) for r in tickers_json.values()}


def filings(symbol, cik, company, submissions, since):
    """Recent filings of the wanted forms, dated on or after `since` (a date)."""
    r = submissions["filings"]["recent"]
    out = []
    for acc, form, filed, items in zip(r["accessionNumber"], r["form"], r["filingDate"], r.get("items") or [""] * len(r["form"])):
        if form not in FORMS:
            continue
        try:
            day = datetime.date.fromisoformat(filed)
        except ValueError:
            continue                      # no date, no item: never invent one
        if day < since:
            continue
        out.append({
            "id": acc, "symbol": symbol, "company": company, "form": form, "label": label(form, items), "filed": filed,
            "source": SOURCE, "url": f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc.replace('-', '')}/{acc}-index.htm",
        })
    return out


def merge(previous, fresh, failed, since):
    """Fresh items, plus the previous items of symbols that failed this time. One row per filing."""
    kept = [i for i in previous if i.get("symbol") in failed and str(i.get("filed", "")) >= since.isoformat()]
    seen, rows = set(), []
    for i in sorted(fresh + kept, key=lambda x: (x["filed"], x["id"]), reverse=True):
        if i["id"] not in seen:
            seen.add(i["id"])
            rows.append(i)
    return rows


def get(url, ua):
    req = urllib.request.Request(url, headers={"User-Agent": ua, "Accept-Encoding": "identity"})
    return json.load(urllib.request.urlopen(req, timeout=20))


def main():
    ua = os.environ.get("SEC_USER_AGENT", "").strip()
    if "@" not in ua:
        print("SEC_USER_AGENT is not set (a name and a contact email); company updates not fetched, previous file kept")
        return
    positions = json.loads((ROOT / "data" / "source" / "positions.json").read_text(encoding="utf-8"))
    symbols = [s for s in current_symbols(positions) if s not in SKIP]
    now = datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0)
    since = now.date() - datetime.timedelta(days=KEEP_DAYS)
    try:
        previous = json.loads(OUT.read_text(encoding="utf-8")).get("items", [])
    except (OSError, ValueError):
        previous = []
    try:
        ciks = cik_map(get(TICKERS_URL, ua))
    except Exception as e:
        sys.exit(f"SEC ticker list failed ({e}); previous file kept")
    fresh, failed = [], []
    for s in symbols:
        hit = ciks.get(sec_ticker(s))
        if not hit:
            failed.append(s)
            continue
        try:
            fresh += filings(s, hit[0], hit[1], get(SUBMISSIONS_URL.format(cik=hit[0]), ua), since)
        except Exception as e:
            print(f"{s}: {e}")
            failed.append(s)
        time.sleep(0.5)
    if len(failed) == len(symbols):
        sys.exit("every symbol failed; previous file kept")
    doc = {
        "schema": "company-updates.v1", "source": SOURCE, "checked_at_utc": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "symbols_checked": [s for s in symbols if s not in failed], "symbols_failed": failed,
        "items": merge(previous, fresh, set(failed), since),
    }
    tmp = OUT.with_suffix(".tmp")
    tmp.write_text(json.dumps(doc, indent=1) + "\n", encoding="utf-8")
    tmp.replace(OUT)
    print(f"{len(doc['items'])} filings from {len(doc['symbols_checked'])} companies; failed: {failed or 'none'}")


if __name__ == "__main__":
    main()
