# Handoff: running the club's portfolio site and TV screens

Kevin Sykes built and runs this site until he graduates in February 2027. This page tells the next
owner what they get, what to do each week, and what to do before the handoff. The README has the
technical detail. This page links to it. Read `docs/ARCHITECTURE.md` for the complete system and
dependency inventory. Read `docs/INDEPENDENCE-PLAN.md` for the phased plan through February 2027.

## What the club owns

| Part | Where it lives | Who must have access |
|---|---|---|
| Code, data and price history | This GitHub repository | The club's GitHub organization, plus a faculty sponsor as second admin |
| The website | GitHub Pages, built from this repository | Same as above |
| Price refresh | `.github/workflows/pages.yml`, on GitHub's own runners | Nothing extra: it moves with the repository |
| TV screens | Yodeck, one Web Page item per screen (see README, "TV setup") | The Institute staff who run Yodeck |
| Canvas link | The club's Canvas course points to `/index.html` | The course's instructor |

Nothing in this list depends on Kevin's computers or accounts after the transfer.

## Before Kevin leaves (checklist)

1. Pick the next owner (an officer) and a faculty sponsor. Both need GitHub accounts.
2. Create a GitHub organization for the club, or use one that the Institute gives. Add both people as owners.
3. Kevin removes his backup refresh (below) from every computer that runs it. Do this before the
   transfer: GitHub forwards git pushes to the new address, so a backup that is left running keeps
   writing to the club's repository.
4. Transfer the repository (README, "Hand it to the school", steps 1 to 4).
5. Open the new site address and the `pages` workflow page. Make sure that a "Price snapshot"
   commit arrives within 30 minutes during market hours.
6. Change each Yodeck Web Page item and the Canvas link to the new address. `/screens.html` lists
   every address. GitHub does not forward the old `kevinhsykes.github.io` address, so a screen
   that still uses it goes blank.
7. Look at every TV screen and the Canvas link once.
8. The new owner records one practice trade on a branch and runs the checks. Then they delete the branch.
9. Decide the price source with the faculty sponsor. The saved prices come from a Yahoo Finance
   snapshot, which is for personal use, not for a public screen (README, "Which feed"). Apply for a
   licensed feed (the Twelve Data non-profit program first), or show only `board.html` on the
   public TVs until a licensed feed runs.

## Weekly and per-trade work

- **After a trade:** add one row per fill to `data/source/positions.json`. README, "When the portfolio changes", shows the exact fields. A new ticker needs three more small edits that the same section lists. A test fails until all of them are done.
- **Stop-loss levels:** put them in the trade row (`stop_loss`). The TV's "New positions" panel shows the level for 14 days after the buy.
- **No fill price yet:** record the trade with `"estimated": true`. The pages mark it "EST". If the club accepts the estimate and no fill will come, add `"fill_expected": false` and a `price_note`.
- **Nothing else is routine.** Prices refresh by themselves every 15 minutes while the market is open.

## Yearly work

- Before January 2028, regenerate `data/source/xnys-calendar.json` (README, "Yearly").
- Once a year, read the "Which feed" section of the README. The saved prices come from a Yahoo
  Finance snapshot, which is for personal use. A licensed feed (the Twelve Data non-profit program
  is the first one to try) is the correct long-term source for a public screen.

## When something looks wrong

| You see | Do this |
|---|---|
| Yellow banner "prices stopped updating" on a market day | Open the repository's Actions tab. Read the last failed `pages` run. Click "Run workflow" to try again. |
| Grey banner | The market is closed. Nothing is wrong. |
| A wrong share count or price | Fix the trade row in `positions.json`. Do not edit `opening_positions` or the statement CSV. |
| A TV shows an old page | The page reloads itself every 6 hours and when the site changes. Restart the screen in Yodeck. |
| The `pages` workflow shows "disabled" | GitHub turns off scheduled workflows in a public repository after 60 days with no repository activity. Click "Enable workflow" on the Actions tab. |

## Kevin's backup refresh (goes away at the handoff)

GitHub sometimes delays or skips scheduled runs. Until February, Kevin's own computers also refresh
the prices as a backup. This backup is not part of what the club owns.

- **What it does:** `tools/fleet_refresh.sh` runs every 15 minutes in market hours on Kevin's
  computers KPC and fn, at different minutes. It reads `collected_at_utc` from the saved prices on
  GitHub. If the prices are less than 16 minutes old, it stops. If they are older, it refreshes
  the prices in its own copy of the repository, runs the checks, and pushes. The push starts the
  normal `pages` workflow, which deploys the site.
- **Why it uses no GitHub API:** it uses only git, so the API rate limit of Kevin's shared
  token cannot stop it.
- **Commits:** its commit messages end with the computer's name, for example
  "Price snapshot ... (kpc)". GitHub's own commits have no computer name.
- **Install:** `tools/fleet_refresh_install.sh install <offset-minutes>` on each computer.
  KPC uses offset 0 and fn uses offset 7. The computer needs git, Python 3.12, Node 22 or
  newer (set `GOLISANO_NODE` if `node` is older), and push access to the repository.
- **Check:** `tools/fleet_refresh_install.sh status`.
- **Remove:** `tools/fleet_refresh_install.sh uninstall` on each computer. Then delete
  `~/.local/share/golisano-refresh`.

A successor who wants a backup of their own can run the same installer on a computer that they
control. It is optional.

The site works without the backup. After the transfer, GitHub's scheduled run is the only refresh.
If GitHub skips a run, the next run 15 minutes later catches up.
