# Investment Club portfolio on the cafe TVs — brief for Golisano media, Oct 26, 2026

## What we have, ready today

- **TV view** (`tv.html`): full-screen 16:9 page. Left card: portfolio value, today's change, SPY today, gain vs cost, change since the Sept 22 statement, holdings up/down, largest holding. Right side rotates four panels every 20 s: largest 9 holdings, the other 9, today's biggest moves with allocation bars, and a chart of gain over cost (portfolio vs our SPY position vs stock picks). Scrolling price tape and the exchange-required delay notice. Built for 1080p and 4K, kiosk mode, burn-in shift, auto-reload every 6 h, keeps last prices through network drops.
- **Web view** (`index.html`): phones and laptops, linked from the club's Canvas page. Sortable holdings table with cost basis, day and total gain, weights; click a stock for its chart and key stats.
- **Live board** (`board.html`): interim TV page using TradingView's free widget (15-minute delayed prices, no portfolio math). Needs no account or key.
- Prices on all pages as of 10:27 AM ET today: value $104,769, cost $100,832, gain +$3,937 (+3.90%), day +$339 (+0.33%).

## What the TV needs from the school

1. **A device per screen that opens a URL in kiosk mode** (any Chrome/Edge/Firefox box, a Raspberry Pi, a Chromecast with Google TV, or the signage player already driving the screens). The page is a normal web page; any signage system that shows a URL works.
2. **Hosting**: a Cloudflare account owned by the club or the Institute (free tier is enough: one Worker, one KV store, static pages). Deploy is one command once the account exists.
3. **A licensed price feed.** This is the only real cost, and the licence, not the price, decides it. Free and personal plans (Yahoo, Google, Finnhub, Alpaca, Alpha Vantage) do not allow showing prices to the public.

| Rank | Option | Cost | Notes |
|---|---|---|---|
| 1 | Twelve Data non-profit program | $0 if approved | Apply by email (support@twelvedata.com) with the Institute's 501(c)(3) letter; ask for the Venture plan and written confirmation that a public TV is covered. |
| 2 | Twelve Data Venture | about $149/mo (~$1,800/yr) | "External display data access". 18 stocks once a minute fits the cheapest tier. Confirm whether their "US Equities Add-On" is required for a public display. |
| 3 | Tiingo display tier | about $250/mo | Sales quote. Prices from one exchange (IEX). |
| 4 | Screenfeed | about $8 per TV/mo | Licensed for the TV only. No web page, no portfolio value. |
| 5 | Barchart, Intrinio, Polygon | quote, or $500–$3,000+/mo | Only if the first three fail. |

Questions to get answered in writing from any vendor: (a) does the plan cover a public display in a campus building; (b) is a separate exchange fee owed (Barchart lists $250/mo for delayed Nasdaq redistribution; 13 of our 18 holdings are Nasdaq-listed); (c) the delay they deliver (15-minute delayed is free of exchange fees; real-time on a public screen is not); (d) attribution wording required on screen.

## Who runs it after setup

- **Trades**: when the club's advisor confirms a trade, one person updates `data/source/positions.json` and the statement CSV, runs the build and tests, and redeploys (about 10 minutes). Symbols are validated; the Worker refuses a wrong set.
- **Feed**: the Worker refreshes once a minute on weekdays during market hours and keeps the last good prices if the vendor is down. A health endpoint shows the last attempt.
- **Yearly**: regenerate the NYSE holiday calendar before January 2028.
- Ownership: the Cloudflare account and the feed subscription should be in the Institute's or club's name, with a faculty sponsor as a second admin, so it survives officer turnover.

## Demo today without any of the above

On a laptop with the repo: `python3 tools/demo_serve.py`, then open `http://localhost:8765/tv.html` full screen. Prices refresh every minute from a Yahoo Finance snapshot (fine for a demo and internal use, not for the public screen). Screenshots of all panels are in `docs/`.

## Not on record yet

Purchase dates and the club's start date (ask Dave for the trade history), cash and dividends. Until then the chart compares gains on what we paid, not returns over the same period, and the pages say so.
