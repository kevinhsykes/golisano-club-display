#!/usr/bin/env python3
"""Recent headlines for the companies the club holds -> web/data/news.json.

Source: Yahoo Finance per-ticker RSS (feeds.finance.yahoo.com/rss/2.0/headline?s=<TICKER>).
Yahoo's Terms of Service, section 2(o) "RSS Feeds" (https://legal.yahoo.com/us/en/yahoo/terms/otos/index.html),
allow showing the feed's content "without modification", with attribution to Yahoo and a link to
the full article, and with no advertising. So this file keeps each title exactly as the feed gave
it (no rewriting, no summary, no description text), keeps each item's own article link, and the
page that shows it credits "Headlines via Yahoo Finance". Never add ads next to these items.

Yahoo may stop the feeds at any time. Every failure is quiet: a symbol whose fetch fails keeps its
previous items (until they age out) and is listed in `symbols_failed`; if every symbol fails the
previous file is kept untouched and the exit code is non-zero (the workflow ignores it).

An item is kept when its title names the ticker or the company, is no older than KEEP_DAYS, and
is not a duplicate (same link, or same title, within the file). Funds (SPY) are skipped.
"""
import datetime
import email.utils
import json
import re
import sys
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
from holdings import current_symbols  # noqa: E402

OUT = ROOT / "web" / "data" / "news.json"
FEED = "https://feeds.finance.yahoo.com/rss/2.0/headline?s={s}&region=US&lang=en-US"
UA = "GolisanoInvestmentClubDisplay/1.0 (+https://kevinhsykes.github.io/golisano-club-display/; club portfolio headlines)"
SOURCE = "Yahoo Finance"
KEEP_DAYS = 7
PAUSE = 1.0             # seconds between requests
SKIP = {"SPY"}          # funds
SCHEMA = "company-news.v1"

# Names a headline may use for a holding, besides what instruments carry. Matched as whole words.
ALIASES = {"GOOGL": ["Alphabet", "Google"], "META": ["Meta", "Facebook"], "BRK/B": ["Berkshire"], "AMD": ["AMD"],
           "UPS": ["United Parcel Service"], "SOFI": ["SoFi"], "NVDA": ["Nvidia"], "MU": ["Micron"], "MKSI": ["MKS Inc", "MKS Instruments"]}
# Other organisations that share a holding's name, and generic market-research press releases.
NOT_THE_COMPANY = {"AAPL": ["Apple Hospitality"], "AMZN": ["Amazon rainforest", "Amazon River", "Amazon basin"],
                   "BRK/B": ["Berkshire Hills", "Berkshire Grey", "Berkshire Bank"], "META": ["Meta Materials", "Meta Financial"]}
# Market-research press releases ("Global Parcel Delivery Market Report 2026"), not news that uses
# "market share" or "market outlook" in passing.
_NOISE = re.compile(r"\bmarket (report|size|research)\b|\bglobal\b.*\bmarket\b.*\b(report|forecast|20\d\d)\b", re.I)
RUN_BUDGET = 240        # seconds for the whole fetch; later symbols keep their previous items
_SUFFIX = re.compile(r"\s+(class\s+[a-z]|inc\.?|corp\.?|corporation|co\.?|ltd\.?)$", re.I)


def tickers(symbol):
    """Forms a headline may print for the ticker: BRK/B -> BRK.B, BRK-B, BRK/B."""
    return {symbol, symbol.replace("/", "."), symbol.replace("/", "-")}


def company_names(symbol, name):
    """Company names to look for, class suffix removed ("Meta Platforms Class A" -> "Meta Platforms")."""
    base = name or ""
    while _SUFFIX.search(base):
        base = _SUFFIX.sub("", base)
    out = [n for n in [base, *ALIASES.get(symbol, [])] if n]
    return list(dict.fromkeys(out))


def mentions(title, symbol, name):
    """True when the title names the ticker or the company: exact case, whole words (so "meta-analysis" is
    not Meta), not another organisation with the same name, and not a market-research press release."""
    if _NOISE.search(title) or any(x.casefold() in title.casefold() for x in NOT_THE_COMPANY.get(symbol, [])):
        return False
    for t in tickers(symbol):
        if re.search(r"(?<![A-Za-z0-9.\-/])" + re.escape(t) + r"(?![A-Za-z0-9\-/]|\.[A-Za-z0-9])", title):
            return True
    for n in company_names(symbol, name):
        if re.search(r"(?<![A-Za-z0-9])" + re.escape(n) + r"(?![A-Za-z0-9])", title):
            return True
    return False


def parse_date(text):
    try:
        d = email.utils.parsedate_to_datetime((text or "").strip())
    except (TypeError, ValueError):
        return None
    if d is None:
        return None
    if d.tzinfo is None:
        d = d.replace(tzinfo=datetime.timezone.utc)
    return d.astimezone(datetime.timezone.utc)


def iso(d):
    return d.strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_feed(xml_bytes, symbol, name, now):
    """Items of one feed that pass the filters. The title is the feed's own text, only stripped of outer whitespace."""
    root = ET.fromstring(xml_bytes)
    cutoff = now - datetime.timedelta(days=KEEP_DAYS)
    out = []
    for it in root.iter("item"):
        title = (it.findtext("title") or "").strip()
        link = (it.findtext("link") or "").strip()
        when = parse_date(it.findtext("pubDate"))
        if not title or not when or urllib.parse.urlparse(link).scheme != "https":
            continue                      # incomplete rows are dropped; nothing is filled in
        if when < cutoff or when > now + datetime.timedelta(hours=1):
            continue
        if not mentions(title, symbol, name):
            continue
        row = {"symbol": symbol, "title": title, "link": link, "published_utc": iso(when)}
        pub = (it.findtext("source") or "").strip()
        if pub:
            row["publisher"] = pub
        out.append(row)
    return out


def dedupe(rows):
    """Newest first; one row per link and per identical title (the first, newest, wins)."""
    seen_link, seen_title, out = set(), set(), []
    for r in sorted(rows, key=lambda x: (x["published_utc"], x["link"]), reverse=True):
        key_t = re.sub(r"\s+", " ", r["title"]).casefold()
        if r["link"] in seen_link or key_t in seen_title:
            continue
        seen_link.add(r["link"])
        seen_title.add(key_t)
        out.append(r)
    return out


def merge(previous, fresh, failed, now):
    """Fresh items, plus the previous items of symbols that failed (while still inside the age window)."""
    cutoff = iso(now - datetime.timedelta(days=KEEP_DAYS))
    kept = [i for i in previous if i.get("symbol") in failed and str(i.get("published_utc", "")) >= cutoff]
    return dedupe(fresh + kept)


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/rss+xml, application/xml"})
    return urllib.request.urlopen(req, timeout=20).read()


def main(fetch=get, pause=PAUSE):
    positions = json.loads((ROOT / "data" / "source" / "positions.json").read_text(encoding="utf-8"))
    names = {i["symbol"]: i.get("name") for i in positions.get("instruments", [])}
    symbols = [s for s in current_symbols(positions) if s not in SKIP]
    now = datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0)
    try:
        previous = json.loads(OUT.read_text(encoding="utf-8")).get("items", [])
    except (OSError, ValueError):
        previous = []
    fresh, failed, empty = [], [], []
    started = time.monotonic()
    for n, s in enumerate(symbols):
        if time.monotonic() - started > RUN_BUDGET:
            print(f"{s}: skipped, time budget used")
            failed.append(s)
            continue
        if n:
            time.sleep(pause)
        try:
            root_items = fetch(FEED.format(s=urllib.parse.quote(s.replace("/", "-"))))
            if not ET.fromstring(root_items).findall(".//item"):
                empty.append(s)      # no news (or a blank feed): keep the previous items rather than none
                continue
            fresh += parse_feed(root_items, s, names.get(s), now)
        except Exception as e:
            print(f"{s}: {type(e).__name__}: {e}")
            failed.append(s)
    if len(failed) + len(empty) == len(symbols):
        sys.exit("no feed returned items; previous file kept")
    doc = {"schema": SCHEMA, "source": SOURCE, "checked_at_utc": iso(now),
           "symbols_checked": [s for s in symbols if s not in failed], "symbols_failed": failed,
           "symbols_empty": empty,
           "items": merge(previous, fresh, set(failed) | set(empty), now)}
    tmp = OUT.with_suffix(".tmp")
    tmp.write_text(json.dumps(doc, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(OUT)
    print(f"{len(doc['items'])} headlines from {len(doc['symbols_checked'])} holdings; failed: {failed or 'none'}")


if __name__ == "__main__":
    main()
