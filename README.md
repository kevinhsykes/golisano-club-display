# Golisano Investment Club — portfolio display

A cafe TV view and a web page (linked from the club's Canvas course) showing the club's
18 holdings with prices that refresh every minute while the market is open.

| Page | Path | Use |
|---|---|---|
| Live board (interim) | `/board.html` | TV view that works today with no account or key: TradingView's free widget shows 15-minute-delayed prices for the 18 holdings. No portfolio value. Also works opened as a local file. |
| TV view | `/tv.html` | Full-screen 16:9 display for the cafe once a licensed feed runs: value, day change, gain, four rotating panels. |
| Web view | `/` (`index.html`) | Phones and laptops. The Canvas page links here. Sortable holdings table. |
| Quotes API | `/api/quotes` | Latest complete set of 18 quotes (last good set if a refresh fails). |
| History API | `/api/history` | One closing snapshot per trading day. |
| Health | `/api/health` | Last refresh attempt, error text if it failed, newest quote time. |

## How prices get here

```
Cloudflare cron (every minute, weekdays)          browser (TV / web)
  -> NYSE calendar: open, or <=20 min after close    -> loads data/portfolio.json (holdings)
  -> one request to the quote feed for 18 symbols   -> polls /api/quotes every 60 s
  -> validate all 18, never older than stored        -> recomputes value, day change, weights
  -> KV "quotes:latest" (+ "history" after close)    -> shows "Prices delayed 15 minutes · source"
```

A failed or partial refresh never replaces good prices. The pages show a yellow banner when
prices stop updating during market hours, and a grey one when the market is closed.

## Display rules (why prices are delayed)

Exchanges do not charge for prices delayed at least 15 minutes, but every display must say so
at or near the top, and a scrolling ticker must repeat the notice at least every 90 seconds
(CTA, UTP, Nasdaq, NYSE and Cboe policies). Both pages do this from the feed's metadata.
Real-time prices on a public screen need exchange display licences that cost far more than
the club can justify. The feed vendor's own terms must also allow showing its data to other
people; most free and personal plans do not.

## Which feed

The feed's licence decides this, not its price. Checked 2026-10-21:

| Feed | Cost | Can it be shown on the TV and Canvas? |
|---|---|---|
| Twelve Data non-profit program | $0 if approved | Yes, if the granted plan covers external display. Apply in the Institute's name (it is a 501(c)(3)). |
| Twelve Data Venture | from $149/mo (610 credits/min; $499 top tier) | Yes for commercial display; confirm whether the "US Equities Add-On" is needed for a public TV. `PROVIDER=twelvedata`. |
| Tiingo EOD + IEX redistribution | $250/mo (startup) | Yes: display redistribution tier, sold through sales. `PROVIDER=tiingo`. |
| TradingView widgets | $0 | Prices only (no export, so no portfolio math). Used by `board.html`. |
| Twelve Data Basic/Grow, Finnhub, Alpaca, Massive (Polygon), Tiingo Starter/Power, Alpha Vantage, FMP, EODHD, Google Finance, Yahoo | various | No: personal or internal use only, or no redistribution. No adapter on purpose. |

Twelve Data's default US feed is real-time from venues covering about 5% of US volume, so the
pages label it "not sourced from all markets" (`MARKET_SCOPE=partial`).

## Public vs full data

`python build.py --public --out web/data/portfolio.public.json` writes a payload with no share
counts, cost basis or dollar values: only relative units, so the pages show returns, weights and
day change in percent. `python build.py` writes the full payload with dollar values. The deployed
site uses the full payload: Kevin Sykes decided on 2026-10-26 that showing dollar amounts on the
cafe TV is fine. To switch a screen to percent only, open `tv.html?amounts=hide`, or point
`?data=data/portfolio.public.json` at the public payload.

## Hosting today: GitHub Pages (live since 2026-10-26)

The site is served from this repository by GitHub Pages: https://kevinhsykes.github.io/golisano-club-display/
(`/tv.html` for the cafe TV, `/index.html` for phones and laptops). `.github/workflows/pages.yml`
deploys `web/` on every push to `main` and, every 15 minutes during US market hours, refreshes the
saved prices from a Yahoo Finance snapshot and commits them back. That snapshot is personal-use data,
so the pages say "Saved prices, not a live feed"; the licensed feed below replaces it for the public
screen. The deployed `web/data/portfolio.json` is built in the workflow and carries dollar amounts;
use `?amounts=hide` on either page to show percentages only.

### Hand it to the school

1. In GitHub: Settings > General > Transfer ownership, to the Institute's or club's GitHub organization
   (or a faculty sponsor's account). History, the workflow and the Pages site move with it; the site
   address becomes `https://<org>.github.io/golisano-club-display/`.
2. In the new home: Settings > Pages > Source "GitHub Actions" (one click if it did not carry over),
   and Settings > Actions > allow workflows. Push once or run the `pages` workflow by hand.
3. Point the TV devices at the new `/tv.html` address and the Canvas link at `/index.html`.
4. Add a second admin (faculty sponsor) so the site survives officer turnover.

## Deploy (club- or institute-owned Cloudflare account)

```sh
npm install --save-dev wrangler
npx wrangler login
npx wrangler kv namespace create QUOTES           # put the id in wrangler.jsonc
npx wrangler secret put TWELVEDATA_KEY            # or TIINGO_KEY with PROVIDER "tiingo"
python build.py --public --out web/data/portfolio.json
npm test
npx wrangler deploy
```

Then open `/api/health` during market hours; `last_attempt.ok` should be `true` and
`newest_quote_utc` within a few minutes of now.

## When the portfolio changes

Holdings live in `data/source/positions.json` and the statement CSV. After the outside
professional confirms a trade, update shares and cost basis there, add the new statement
snapshot, rebuild, test, and redeploy. Add or remove the symbol in `SYMBOLS`
(`worker/index.js`) in the same change; the Worker refuses any set that is not exactly
those symbols.

## Yearly

`data/source/xnys-calendar.json` covers 2026-2027 (generated with `exchange_calendars`).
Regenerate it before January 2028, or the Worker stops fetching once the calendar runs out.

## Checks

`npm test` runs the math (Oct 9 figures to the cent), market clock (holidays, early close,
daylight saving), freshness rules, the public payload's privacy, and the Worker's refresh
logic against a fake feed and fake storage.

## TV setup

Open `https://<host>/tv.html` full screen in kiosk mode on the cafe TV's device. Options:
`?amounts=hide` (percent only), `?panel=holdings|movers` (pin one panel), `?rotate=40`
(seconds per panel). The page reloads itself every 6 hours and survives network drops by
keeping the last prices with an age warning.
