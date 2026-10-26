# What the display still needs from the club's records (ask Dave)

The Sept 22, 2026 cost-basis export gives shares, cost basis and market value for the 18 holdings.
It does not give the items below. Each one unlocks a specific improvement on the pages.

| Needed | Why | Where it goes |
|---|---|---|
| Trade history: every buy and sell with date, symbol, shares and price (a "Transactions" or "History" export from the brokerage, any date range from the club's first trade) | Turns "gain on what we paid" into real returns over time and lets the chart start at the club's start date | `data/source/positions.json` `transactions[]`, one row per trade |
| Club start date (first funding or first trade) | Chart origin and the "since inception" figure | `positions.json` `opening_observation` |
| Cash balance on the statement date | Portfolio value today excludes cash; with it the page can show total account value | `positions.json` `cash` |
| Dividends received (date, symbol, amount) and whether they are reinvested | Total return, and reinvested shares change the share counts | `transactions[]` with `type: "dividend"` |
| Newer statement (any month after Sept 2026) | Reconciles shares and cost basis after any trade | `data/source/statement-YYYYMMDD.csv` |

Known from the Sept 22 export: short-term unrealized gain $9,040.18 (8.97%), long-term $0.00,
so every current lot was bought after Sept 22, 2025. Nothing on the pages assumes a purchase date.

Suggested message:

> Dave, for the cafe TV display we have the Sept 22 cost-basis export. Could you send the account's
> transaction history export (all trades since the club's first purchase, with dates), the cash
> balance, and the dividend history? A CSV export from the brokerage is ideal. That lets the display
> show real returns since the club started instead of gain over cost.
