# Data-use statement: Golisano Investment Club portfolio display

For the faculty sponsor. This is the use the club is asking to approve. It does not say a vendor has granted a feed.

## What the display holds

The display is the club's 18 holdings: symbols, weights, and (on the full pages) share counts, cost basis, and dollar value. Prices are snapshots, not a tape. Today those snapshots are refreshed from a saved Yahoo Finance file about every 15 minutes in market hours. A licensed feed, if one is later approved in writing, would replace that file. The display does not hold personal data: no student names, no account numbers, no grades, and no login.

## Where it is processed

GitHub Actions builds the site and refreshes the saved snapshot. GitHub Pages serves the pages (the cafe TV page, the member web page, and an interim board). If the club later deploys the Cloudflare Worker, that Worker would request the 18 quotes and store the latest set. No other processor is in use for this display.

## Who can see it

The TV page and the web page are public. Anyone who opens the address, and anyone in the cafe looking at the screen, can see the prices and the portfolio figures the pages show. Prices of listed stocks are public market data. The club's own holdings and dollar amounts are on that public page because club leadership (Kevin Sykes, 2026-10-26) chose to show dollar amounts on the interim cafe TV display. This statement asks the sponsor to approve that use going forward. A screen can be opened with amounts hidden if the sponsor wants percents only.

## Retention

The repo keeps the current snapshot and one closing snapshot per trading day in the history the site already stores. Old GitHub Actions runs follow GitHub's own retention. Nothing in this display is a student record.

## Delay notice and attribution

Pages say that prices are delayed at least 15 minutes, or, for the current saved file, that they are saved prices and not a live feed. A scrolling ticker repeats the notice. If a licensed feed is connected, the pages will show that vendor's required attribution in the wording the vendor writes down, and will keep the delay notice. The club will not label the board real-time.

## What the club will not do

- It will not redistribute raw quotes beyond the cafe screens and the one web page.
- It will not give students or visitors an API key, a download of the vendor's raw feed, or a right to reuse those quotes somewhere else.
- It will not claim the prices are real-time.
- It will not turn on a paid or non-profit feed until the vendor has confirmed in writing that a public campus screen and the member page are covered, and until the sponsor accepts that reply.
- It will not put the feed account in a student's name. The account owner stays the Institute or the club, with the faculty sponsor as a second admin.

Approving this statement approves the use above. It does not send an application and it does not select Twelve Data or Tiingo.
