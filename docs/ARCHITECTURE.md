# Architecture and dependency inventory

## Scope and evidence

This document describes the repository at commit `b2ccd50`. Code claims come from the files cited below.

The live site address, GitHub account ownership, Yodeck setup, Canvas link, and home-computer timers are task-supplied facts. Their live consoles were not inspected. Items that the repository cannot prove are marked UNKNOWN.

No migration steps in this document or in `docs/INDEPENDENCE-PLAN.md` were executed.

## System summary

The production system is a static GitHub Pages site. GitHub Actions builds the site and refreshes saved Yahoo Finance quotes. Two systemd user timers on Kevin's computers provide a backup refresh.

Yodeck loads `tv.html` on the cafe TVs. The club's Canvas course links to `index.html`. Both pages read the same generated portfolio data.

The Cloudflare Worker is an alternative host and quote path. It is not deployed today. It has no live Cloudflare account, namespace, or feed credential.

```text
Brokerage statement + hand-recorded trades + saved quotes + profiles + calendar
                                  |
                                  v
                         build.py and holdings.py
                                  |
                 +----------------+----------------+
                 |                                 |
                 v                                 v
       web/data/portfolio.json       web/data/portfolio.public.json
       full payload, generated       percent-only payload, committed
                 |                                 |
                 +----------------+----------------+
                                  v
                     HTML pages and web/core.js
                                  |
                    +-------------+-------------+
                    |                           |
                    v                           v
             Yodeck TV browser             Canvas link
```

## Components

| Component | Purpose | Evidence |
|---|---|---|
| `data/source/statement-20260922.csv` | Frozen opening shares, market values, and cost basis from September 22, 2026 | CSV rows and `build.py` |
| `data/source/positions.json` | Frozen opening positions, instrument names, TradingView symbols, and later transactions | `opening_positions`, `instruments`, and `transactions` |
| `tools/holdings.py` | Validates trades and calculates shares, average cost, cash flows, and realized gains | `transactions`, `holdings_at`, and `_walk` |
| `data/source/instrument-profiles.json` | Company descriptions, types, industries, and issuer links | `instruments` and `build.py` |
| `data/source/xnys-calendar.json` | NYSE holidays, early closes, and a stated valid range | `range`, `weekday_holidays`, and `early_closes` |
| `data/source/quotes-current.json` | Latest complete saved quote set | Written by `tools/snapshot_quotes.py` |
| `data/source/historical-quotes.json` | Earlier daily portfolio quote sets used for history | Read by `build.py` and appended by `tools/snapshot_quotes.py` |
| `build.py` | Checks the statement, applies trades, values history, and writes browser payloads | `main` and `write_version` |
| `tools/snapshot_quotes.py` | Fetches current Yahoo Finance quotes and writes the static quotes API | `yahoo` and `main` |
| `tools/snapshot_history.py` | Fetches one year of daily Yahoo Finance closes for each current holding | `fetch` and `main` |
| `.github/workflows/pages.yml` | Refreshes quotes, builds, tests, commits generated data, and deploys Pages | `build` and `deploy` jobs |
| `tools/fleet_refresh.sh` | Refreshes stale prices from a dedicated clone and pushes to `main` | `check_freshness` and `build_commit` |
| `tools/fleet_refresh_install.sh` | Installs, checks, and removes the systemd user backup timer | `install`, `status`, and `uninstall` |
| `web/core.js` | Shared quote merging, market clock, freshness checks, calculations, and charts | Exported functions |
| `web/index.html` | Phone and laptop portfolio view linked from Canvas | `boot`, `poll`, and `render` |
| `web/tv.html` | Full-screen portfolio view loaded by Yodeck | `boot`, `poll`, `rotate`, and `renderStatus` |
| `web/trades.html` | Trade history and realized gains | `boot` and `render` |
| `web/board.html` | TradingView price widgets without portfolio calculations | `SYMBOLS` and widget setup |
| `web/screens.html` | Directory of display pages and copyable relative addresses | `screens` and `base` |
| `canvas/portfolio-page.html` | Template for a Canvas link, not an embedded dashboard | HTML comment and anchor |
| `tools/demo_serve.py` | Optional local demonstration server and quote loop | `refresh_loop` and server setup |
| `worker/index.js` | Undeployed Cloudflare assets, quote API, history API, health API, and cron | `fetch`, `refresh`, and `scheduled` |
| `worker/providers.js` | Twelve Data and Tiingo adapters for the undeployed Worker | `PROVIDERS` |
| `wrangler.jsonc` | Undeployed Worker configuration and placeholder KV namespace ID | `kv_namespaces`, `triggers`, and `vars` |
| `test/` | Build, holdings, browser math, and Worker tests with local fixtures | Test files and workflow commands |

## Source data and portfolio calculations

### Opening statement

`data/source/statement-20260922.csv` is the opening record. `data/source/positions.json` repeats its shares and cost basis in `opening_positions`.

`build.py` compares the symbols, shares, and cost basis in both files. It stops when they disagree. The opening positions must stay unchanged when later trades are recorded.

The displayed portfolio excludes cash, dividends, unrecorded fees, and unrecorded trades. `build.py` puts this limitation in the payload disclosure. Exact purchase dates for the opening holdings are not on record in `data/source/positions.json`.

### Trades

The club records trades by hand in `data/source/positions.json`. Each transaction has a type, symbol, execution time, shares, price, status, and source. Optional fields cover fees, estimates, and stop-loss rules. A stop-loss has a `status`: only an `adopted` stop reaches the TV and portfolio page. A `proposed` stop (MU's 20% rule from the pitch notes, as of 2026-11-11) appears only on the trades page, marked for club discussion.

`tools/holdings.py` accepts only confirmed buy and sell rows after the statement date. It requires positive shares and prices. A buy adds shares and cost. A sell removes shares and average cost, then calculates a realized gain. A sale above the recorded holding stops the build.

The November 11, 2026 transactions record MU and CAT buys and a SPY sale. The SPY sale uses an accepted estimated price with `fill_expected` set to false. The source and estimate are preserved in `data/source/positions.json`.

A new symbol also needs entries in these places:

1. `instruments` in `data/source/positions.json`.
2. `data/source/instrument-profiles.json`.
3. `SYMBOLS` in `worker/index.js`.
4. `SYMBOLS` in `web/board.html` when the TradingView board must show it.

The README documents the first three locations. The fourth location is separate. The test `worker SYMBOLS are exactly the built holdings` in `test/worker.test.mjs` checks only the Worker list against the built payload. It does not check `web/board.html`.

### Build path

`build.py` reads the statement, positions, profiles, current quotes, historical quotes, and calendar. It then does the following work:

1. Checks the opening statement against `opening_positions`.
2. Applies confirmed trades at their execution times.
3. Rejects a current quote set that lacks a held symbol.
4. Rejects a trade later than the newest saved quote.
5. Values each saved history point with the holdings held at that time.
6. Calculates time-weighted return, cash flows, and realized gains.
7. Adds instrument details, new-position data, and stop-loss data.
8. Writes the full or public payload.
9. Writes `web/version.json` with the short Git commit and build time.

The full output defaults to `web/data/portfolio.json`. This file is ignored by `.gitignore`, but the workflow builds it into the Pages artifact. It contains shares, cost basis, and dollar values.

The public output uses relative units instead of shares and dollar values. The normal output path for that build is `web/data/portfolio.public.json`, which is committed. The pages can select it with `?data=data/portfolio.public.json`.

The `?amounts=hide` option hides dollar amounts in the interface. It does not remove dollar fields from a full payload. Anyone who can fetch that payload can still read those fields.

`web/version.json` is also ignored by `.gitignore`. The workflow generates it for deployment.

## Quote snapshot path

### Collection

`tools/snapshot_quotes.py` gets the current holdings from `tools/holdings.py`. It also keeps SPY in the quote set as a benchmark after a full SPY sale.

The script makes one Yahoo Finance chart request per symbol. It stores the price, previous close, quote time, retrieval time, session state, provider, and source URL. A failed symbol stops the script before it writes a new current snapshot.

The script writes two outputs:

- `data/source/quotes-current.json` for later builds and daily archiving.
- `web/api/quotes` as the static stand-in for the Worker quote API.

When the previous snapshot belongs to an earlier day, the script appends it to `data/source/historical-quotes.json`. It keeps the last saved snapshot for a day. An unreadable previous snapshot is not archived.

`tools/snapshot_history.py` separately fetches one year of daily closes into `web/data/history/<SYMBOL>.json`. It keeps the previous file when a symbol fetch fails or returns fewer than 100 closes. It exits with an error when any symbol fails.

The current `web/index.html` detail dialog loads TradingView widgets. It does not fetch these per-symbol history files. The workflow still refreshes, commits, and deploys these files.

The source comments and saved metadata identify Yahoo data as personal-use data. They say it is not licensed for public display. This is a current operational and licensing dependency, not a licensed production feed.

### GitHub Actions refresh

`.github/workflows/pages.yml` runs on pushes to `main`, on weekdays on a cron schedule, and on manual dispatch. The cron entries cover broad UTC hours for daylight and standard time. They are spaced 15 minutes apart during the stated market windows.

The quote scripts do not use the NYSE calendar to suppress an out-of-hours GitHub run. The workflow comment treats those extra runs as harmless.

On a scheduled or manual run, the workflow does this work:

1. Checks out the repository.
2. Installs Python 3.12 and Node 22.
3. Runs `tools/snapshot_quotes.py`.
4. Runs `tools/snapshot_history.py`, but keeps going if history fails.
5. Builds full and public payloads.
6. Runs the Node and Python tests.
7. Commits changes under `data/source`, `web/data`, and `web/api`.
8. Pushes the commit when generated files changed.
9. Uploads `web/` and deploys it to GitHub Pages.

On a push run, quote refresh is skipped during the normal first step. The build step fetches current quotes and retries once if the first full build fails. The same job then tests and deploys.

The workflow has `contents: write`, `pages: write`, and `id-token: write`. GitHub supplies the workflow credential. The repository contains no workflow token value.

GitHub can disable scheduled workflows after repository inactivity. `docs/HANDOFF.md` gives 60 days and describes the Actions page control for enabling the workflow again. The current live schedule state is UNKNOWN.

### Home-computer backup

`tools/fleet_refresh.sh` uses Git rather than the GitHub API. Its default remote is `kevinhsykes/golisano-club-display`. Its dedicated clone and logs live under `~/.local/share/golisano-refresh` by default.

Each run fetches `origin/main` and reads `collected_at_utc` from the saved quotes. Quotes newer than 16 minutes cause an exit without a build. Missing, old, unreadable, or far-future data causes a refresh attempt.

The refresh resets the dedicated clone to `origin/main`. It then runs both quote scripts, both builds, and all tests. A successful change is committed with the host name and pushed to `main`. A rejected push causes one rebuild on the newer remote state. The script never force-pushes.

`tools/fleet_refresh_install.sh` installs a user service and timer named `golisano-fleet-refresh`. The timer runs on New York market-hour schedules. Different offsets stagger the computers. `docs/HANDOFF.md` records offset 0 on KPC and offset 7 on fn.

The installer requires Git, Python 3, `flock`, `timeout`, systemd user services, and Node 22 or newer. `GOLISANO_NODE` can select a newer Node binary. `docs/HANDOFF.md` specifies Python 3.12 for these computers.

The uninstall action disables the timer, stops an active service, removes the new unit files and installed binary, and reloads systemd. It leaves the dedicated clone for manual deletion.

The older timer `golisano-refresh.timer` on KPC (script `~/.local/bin/golisano-refresh`, units in `~/.config/systemd/user/golisano-refresh.{service,timer}`) asked GitHub to run the workflow through the API, with a local fallback. It was disabled on 2026-11-11 when the new backup was installed. Its files are still on KPC. The new uninstall action does not remove them.

The backup pushes over HTTPS with the GitHub CLI's git credential helper (`gh auth git-credential`) on each computer, logged in as Kevin's GitHub account. No API token is used by the script itself, and the GitHub API rate limit does not apply to git pushes.

## Deployment path

GitHub Pages serves the `web/` directory uploaded by `.github/workflows/pages.yml`. The task-supplied production address is:

```text
https://kevinhsykes.github.io/golisano-club-display/
```

The workflow deploys after the build job succeeds. A failed quote fetch, build, or test prevents that run from deploying a new artifact. The previous deployed artifact remains the expected fallback, but the live result was not tested for this document.

The repository is public. Its source data includes statement values and cost basis. The deployed full payload also includes current shares and dollar calculations.

There is no custom domain. There is no Cloudflare deployment today. No paid service is part of the current stack.

## Browser behavior

### Shared behavior

`web/index.html`, `web/tv.html`, and `web/trades.html` load `data/portfolio.json` by default. The first two load `version.json` and poll `api/quotes`. The trades page tries the quotes API once during startup.

`mergeQuotes` in `web/core.js` accepts a snapshot only when it has the expected schema and a valid quote for every current holding. It ignores an incomplete or older snapshot. The pages keep their last good data after a fetch error.

`marketStatus` uses New York time and the saved calendar. `freshness` reports stale prices during market hours and old closing prices after the session. The interface shows a warning instead of treating old prices as current.

The full and public payloads use the same browser calculation code. `compute` calculates value, daily change, cost, gain, and weights. Other functions calculate time-weighted return and comparisons with SPY.

### Page inventory

| Page | Data and behavior |
|---|---|
| `web/index.html` | Loads the portfolio payload, polls quotes and the build version every 60 seconds, and reloads when the build ID changes. It also loads TradingView widgets in the holding detail dialog. |
| `web/tv.html` | Polls every 60 seconds and reloads when the build ID changes. It rotates panels every 20 seconds by default, shifts the layout every three minutes, and reloads every six hours. |
| `web/trades.html` | Loads the payload and tries one quote merge at startup. It groups trades by day and shows estimates and realized gains. |
| `web/board.html` | Loads TradingView widgets for a separate hard-coded symbol list. It rotates two groups every 20 seconds and reloads every six hours. It does not calculate portfolio value. |
| `web/screens.html` | Builds display addresses from the current page origin. Its GitHub source link and one kiosk example still name Kevin's account. |

A failed initial portfolio load has different behavior by page. The TV retries with a reload after one minute. The web and trades pages show an error and wait for a user reload.

The TV's six-hour reload is independent of Yodeck's own refresh setting. The README recommends leaving Yodeck refresh off or setting it to hours.

## TV and Canvas paths

### Cafe TVs

Institute staff manage Yodeck. Each screen uses a Web Page item that points to `tv.html`. Yodeck and the player fetch the public GitHub Pages address. The page then fetches its JSON, quotes, version file, and JavaScript from the same origin.

The TV number, Yodeck item names, playlist assignments, player models, network rules, and staff account details are UNKNOWN. No Yodeck credential belongs in this repository.

### Canvas

The club's Canvas course links to `index.html`. It is a link, not an iframe embed. `canvas/portfolio-page.html` is a template with a placeholder host. A maintainer must replace that placeholder before using the template.

The Canvas course identifier, instructor, current HTML, and course permissions are UNKNOWN. No Canvas credential belongs in this repository.

### TradingView

`web/board.html` depends on TradingView's external embedding script and delayed prices. The index page's detail dialog also loads TradingView scripts. These paths need third-party network access even when the main portfolio payload loads correctly.

The current TradingView terms for the club's exact public-display use were not reviewed for this document. That licence check is UNKNOWN.

## Undeployed Cloudflare path

`wrangler.jsonc` configures a Worker named `golisano-club-portfolio`. Its KV namespace ID is still `REPLACE_WITH_KV_NAMESPACE_ID`. The configured cron runs every minute during broad weekday UTC hours.

`shouldFetch` in `worker/index.js` uses the NYSE calendar. It allows fetches during the regular session and for 20 minutes after the close. `refresh` calls the selected provider, checks every symbol, rejects old or invalid data, and stores a complete snapshot in KV.

The Worker exposes these routes:

- `/api/quotes` returns the last complete snapshot.
- `/api/history` returns up to 400 daily closing entries.
- `/api/health` returns the last refresh result and market state.
- Other routes come from the static `web/` assets.

A provider failure updates health without replacing good quotes. The Worker supports Twelve Data and Tiingo through `worker/providers.js`. Each needs a licence that permits the intended display and a secret API key.

The static asset response adds `X-Frame-Options: DENY`. The current Canvas use is a link, so this header does not block that use. A future iframe embed would need a different design.

The GitHub Pages repository has a static `web/api/quotes` file. It does not contain a static `web/api/history` or `web/api/health` file. The history and health API routes described for the Worker are not equivalent static endpoints in this repository.

Cloudflare account ownership, deployment status beyond the task-supplied statement, namespace IDs, provider secrets, costs, and a production Worker URL are UNKNOWN.

## Routine operations

### After a trade

1. Get the fill evidence from the club's trade source.
2. Add one transaction per fill to `data/source/positions.json`.
3. Add the extra symbol records listed above when the symbol is new.
4. Update `web/board.html` when that board must include the symbol.
5. Run the quote and history scripts when the build needs newer quotes.
6. Run both builds.
7. Run `npm test` and the Python unittest command from the README.
8. Review the diff and commit the source and generated changes.
9. Check the Pages run and the affected pages after deployment.

Do not change the frozen statement to record a later trade. Use the estimate fields when the club accepts an estimated execution price.

### Monitoring

During market hours, check the Pages workflow and the newest `Price snapshot` commit. The handoff checklist uses a 30-minute bound for this check. On a TV, check that the timestamp advances and no stale banner appears.

After a deployment, check `index.html`, `tv.html`, `trades.html`, `screens.html`, and `board.html`. Check every physical TV and the Canvas link after an address change.

### Calendar

`data/source/xnys-calendar.json` states a range from January 1, 2026 through December 31, 2027. Its source is `exchange_calendars 4.13.2 XNYS`.

`web/tv.html` warns when the current date is outside this range. `marketStatus` still uses the fixed holiday and early-close lists. `shouldFetch` in `worker/index.js` does not check `calendarKnown`. The Worker therefore has no code-level stop at the range boundary. Future holidays and early closes can be wrong after the file expires.

The README and handoff checklist require regeneration before January 2028. The repository does not include the regeneration script or exact command. That procedure is UNKNOWN and must be documented before the first renewal.

## Dependency inventory

| Dependency | Owner or controller today | What breaks if it disappears | Replacement |
|---|---|---|---|
| Kevin's GitHub account | Kevin personal | Repository administration and the current account-based Pages address lose their owner | Transfer the repository to an Institute-approved organization with at least two owners |
| `kevinhsykes/golisano-club-display` repository | Kevin personal through GitHub | Source, source data, workflow, and history become unavailable if the repository is removed | Organization-owned repository plus an independent Git backup |
| GitHub Pages | GitHub under Kevin's account | All static pages and the static quotes API stop at the current address | Pages in the new organization, Institute static hosting, or the Worker asset path |
| Current `kevinhsykes.github.io` address | GitHub under Kevin's account | Existing Yodeck items and Canvas links fail when the address stops serving | Organization Pages address, an Institute-managed custom domain, or Institute hosting |
| GitHub Actions runners | GitHub, configured in Kevin's repository | Quote refresh, builds, tests, and deployment stop | Actions in the transferred repository or another maintained build runner |
| Workflow `GITHUB_TOKEN` permissions | GitHub and repository administrators | The workflow cannot commit quotes or deploy without the required permissions | Keep the declared permissions in `.github/workflows/pages.yml` and review organization Actions policy |
| `actions/checkout`, setup actions, and Pages actions | GitHub and action maintainers | Builds or deploys fail if an action tag or service fails | Pin or update actions through reviewed repository changes and rerun deployment |
| `ubuntu-latest` runner image | GitHub | Tool or operating-system changes can break the workflow | Pin a supported image when needed and test the workflow |
| Python 3.12 | GitHub runner and Kevin's computers | Builds and Python quote scripts fail without a compatible interpreter | Install Python 3.12 on a club-controlled build host or update the tested workflow version |
| Node 22 or newer | GitHub runner and Kevin's computers | Node tests fail or cannot import the Worker's JSON module | Install Node 22 or newer and set `GOLISANO_NODE` for the backup script |
| Git, Bash, `flock`, `timeout`, and systemd user services | Kevin's computers for the backup | The backup timer cannot install or run | Remove the backup dependency or use an Institute-managed Linux host |
| KPC and fn hardware, power, and network | Kevin personal | Backup refreshes stop when both computers or their networks are unavailable | GitHub remains primary. An optional Institute-managed host can replace the backup |
| `golisano-fleet-refresh` timers | Kevin personal | Backup refreshes stop, or an old timer can keep pushing after transfer | Uninstall before transfer. Reinstall only on an authorized managed host |
| Older `~/.local/bin/golisano-refresh` timer | Kevin personal | The old timer can duplicate refreshes or retain unwanted repository access | Inspect and remove the old service, timer, binary, and state after recording their exact names |
| Backup Git push credentials | UNKNOWN, on Kevin's computers | Backup pushes fail, or retained credentials can write after handoff | Remove old credentials after transfer. Use a scoped club credential only if a managed backup remains |
| Yahoo Finance chart endpoint | Yahoo, a third party | Current quotes and per-symbol history stop refreshing | Use a licensed provider adapter through the Worker or stop showing portfolio prices |
| Yahoo display rights | Yahoo terms and the club's usage | Public TV and Canvas display can violate the source terms | Get written display permission or replace the public pages with an allowed display such as the reviewed TradingView board |
| TradingView widgets | TradingView, a third party | `board.html` prices and index detail widgets fail or lose allowed use | Use a licensed provider for calculations or remove the affected widgets |
| Yodeck service | Institute staff and Yodeck | TV content cannot be managed, and service failure can blank displays | Institute signage support or another player that can open the replacement URL |
| TV players and cafe network | Institute | Screens cannot load or refresh the site | Institute hardware and network support. A local fallback display is optional |
| Canvas course and link | Institute instructor or course administrator | Members lose the portfolio entry point when Canvas or the link changes | Update the link in a course controlled by the instructor |
| Public internet and GitHub DNS | Third parties and Institute network | Browsers and runners cannot reach GitHub or quote providers | Restore network service or use Institute hosting with an independent fallback |
| Brokerage statement and fill evidence | Club and brokerage | Shares, cost, and realized gains cannot be reconciled accurately | Assign a trade recorder and reviewer. Preserve statement and fill records in club storage |
| Hand recording in `positions.json` | Kevin currently performs undocumented coordination work | New trades never reach the site, or bad rows stop builds | Assign a maintainer and use the documented per-trade checks |
| Duplicated symbol lists | Repository maintainers | The Worker test fails, or `board.html` omits a new holding | Update `worker/index.js` and `web/board.html` with each symbol change |
| NYSE calendar data | Repository maintainer and `exchange_calendars` upstream | Holiday, early-close, and Worker fetch decisions become wrong after 2027 | Regenerate and test the file before January 2028 |
| Kevin's operational knowledge | Kevin personal | Access recovery, trade reconciliation, timer cleanup, and calendar renewal can stall | Complete the practice handoff and record missing procedures in club documentation |
| Git backup and recovery knowledge | Currently UNKNOWN | A repository or account loss can remove the only working copy | Store a mirror in club-controlled storage and test a restore |
| Cloudflare account and KV | None today | Nothing current breaks because the Worker is not deployed | Create club-owned resources only after the club selects this hosting path |
| Licensed feed account and secret | None today | Nothing current breaks because the Worker is not deployed | Select a licensed provider and store its secret in the club-owned Worker account |
| Public dollar-data decision | Kevin made the current display decision | Privacy expectations can change after ownership transfer | Choose the full or public payload deliberately and record the club decision |

## Knowledge gaps and UNKNOWN items

The following items need live evidence or a named owner:

- The exact GitHub Pages, Actions, branch-protection, and organization settings are UNKNOWN.
- The exact backup credential type, scope, storage location, and revocation procedure are UNKNOWN.
- The older timer's service name, unit contents, installed files, and current state are UNKNOWN.
- Other clones, scheduled jobs, or credentials outside the documented paths are UNKNOWN.
- The number of TVs and their exact Yodeck configuration are UNKNOWN.
- The Canvas course, stored link HTML, and course administrator are UNKNOWN.
- The live availability of every external page and API was not tested.
- The exact calendar regeneration command and environment are UNKNOWN.
- The recurring brokerage reconciliation process and the next statement date are UNKNOWN.
- The club's long-term trade recorder and independent reviewer are UNKNOWN.
- Current legal approval for Yahoo or TradingView public display is UNKNOWN beyond the repository warnings.
- The production Worker account, URL, namespace, feed key, and licence are UNKNOWN because the Worker is not deployed.
