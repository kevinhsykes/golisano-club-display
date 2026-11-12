# Instructions for AI coding tools

This repository runs the Golisano Investment Club's portfolio site and cafe TV display. Club
members and AI tools both change it, through issues and pull requests. Read `README.md` first.
`docs/HANDOFF.md` explains who owns what.

## Hard rules

- Never invent a trade, a fill price, a share count, a fee or a date. Record only what a person
  gives you (a brokerage confirmation, a screenshot, or a written message), and quote the source
  in the trade row's `source` field. If a price is not the brokerage fill, set `"estimated": true`.
- Record a trade as a new row in `data/source/positions.json` `transactions`. Never edit
  `opening_positions` or `data/source/statement-20260922.csv`.
- A stop-loss shows on the TV only with `"status": "adopted"`. Do not adopt one unless the club
  decided it, and say who decided and when.
- This repository is public. Never commit a token, password, API key, account number or a
  member's personal details.
- Do not change the price source or remove the "Saved prices, not a live feed" and delay notices
  (README, "Display rules").

## Before you open a pull request

1. Run `python3 tools/snapshot_quotes.py` if you added a new symbol.
2. Run `python3 build.py` and `python3 build.py --public --out web/data/portfolio.public.json`.
3. Run `npm test` and `python3 -m unittest discover -s test -p 'test_*.py'`. All tests must pass.
4. For a change to a page, open it at the TV size (1920x1080) and at phone width, and put a
   screenshot in the pull request.

## How the club works here

- A trade, a display problem or an idea starts as an issue (templates in `.github/ISSUE_TEMPLATE`).
- A change goes in through a pull request that links its issue. A second member reviews it.
- Every push to `main` deploys the site in about one minute. Only the automatic price refresh
  pushes to `main` directly. People and AI tools use pull requests.
