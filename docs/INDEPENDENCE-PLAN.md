# Independence plan through February 2027

## Objective

The club must operate the portfolio site and cafe TVs without Kevin's accounts, computers, credentials, or unavailable knowledge after February 2027.

This is a plan only. No step in this document was executed.

Read `docs/ARCHITECTURE.md` for the current data flows and dependency inventory. Use `docs/HANDOFF.md` for the routine checklist.

## Roles

Assign people to these roles before Phase 0 ends. One person can hold two roles, but the trade recorder and trade reviewer must be different people.

| Role | Responsibility |
|---|---|
| Club officer | Owns the work, dates, decisions, and officer-to-officer handoff |
| Faculty sponsor | Owns recovery access and approves Institute coordination |
| Site maintainer | Runs builds, tests, deployments, and technical checks |
| Trade recorder | Records fills and supporting evidence |
| Trade reviewer | Checks trades against evidence before publication |
| Institute signage administrator | Changes and checks Yodeck items and physical TVs |
| Canvas instructor | Changes and checks the Canvas link |
| Kevin | Supplies the current repository, existing knowledge, and transfer help until graduation |

Use role names in the durable records. Keep the current names and contact details in club-controlled storage rather than in the public repository.

## Decisions the club and Institute must make

Record each decision, its date, and its approvers in club-controlled storage. Do not leave the decision only in a meeting chat.

| Decision | Options | Recommendation |
|---|---|---|
| Repository and organization ownership | Institute-owned organization, club organization with faculty oversight, or a faculty member's personal account | Use an Institute-approved club organization. Give the faculty sponsor and at least one club officer owner access. Avoid another personal-account dependency. |
| Site address and hosting | Organization GitHub Pages, an Institute-managed custom domain on Pages, Institute hosting, or Cloudflare | Transfer to organization GitHub Pages first. Keep the repository name to limit changes. Consider an Institute-managed custom domain later. |
| Public price-data licence | Licensed feed, TradingView board only, or no public price display | Apply for a licensed non-profit feed now. Use `board.html` as the interim TV display after its terms are checked. Remove Yahoo-powered public displays until the licence allows them. |
| Trade recording | One officer, faculty only, or any member | Assign one trade recorder and a separate trade reviewer. Require fill evidence and a checked build for every trade. |
| Dollar amounts on public pages | Full payload, percent-only public payload, or member-only full data | Current decision: the full payload with dollar amounts (Kevin Sykes, 2026-10-26, README "Public vs full data"). The next officers and the faculty sponsor should confirm it or switch to the percent-only payload. `?amounts=hide` only hides numbers on screen. The JSON still carries them. |
| Backup price refresh | Another student's computer, an Institute-managed computer, or GitHub only | Use GitHub as the only routine refresher. Add a backup only on an Institute-managed host with a scoped club credential. |
| Cloudflare Worker | Deploy after licensing or keep GitHub Pages | Keep GitHub Pages during transfer. Deploy the Worker only after the club owns the feed licence, Cloudflare account, and operating procedure. |
| Custom domain | Keep the organization Pages address or use an Institute domain | Keep the organization Pages address for the transfer. Add a custom domain only if Institute staff own DNS and renewal. |
| Account recovery | Officer only, faculty only, or two controlled recovery paths | Give the faculty sponsor and club officer separate recovery methods. Store recovery evidence outside the public repository. |

## How the club works on GitHub

The club runs the site the way its members run other team projects on GitHub. Work is visible and reviewable, and no one person holds it in their head.

- **Issues** are the to-do list and the record. A trade starts as a "Record a trade" issue (`.github/ISSUE_TEMPLATE/record-a-trade.yml`) with the brokerage fill or a screenshot. A display problem starts as a "Display or site problem" issue. Ideas and decisions (stop-loss rules, the data licence, the payload) are issues too, so the discussion and the decision stay with the code.
- **Pull requests** carry every change. The PR template (`.github/pull_request_template.md`) asks for the checks and screenshots. A second member reviews before merge. Only the automatic price refresh writes to `main` directly.
- **AI tools** follow `AGENTS.md`. They never invent a fill, they add trades as new rows only, and they never commit secrets to this public repository.
- **Labels** `trade` and `display` sort the work. The club can add more.
- **Contributions are tracked by the pull requests themselves.** Since 2026-11-12 every change goes through a pull request, including the work done before the club has its own organization. Each pull request says who asked for the change, who reviewed it, and which issue it closes. The list of merged pull requests is the club's record of who did what. GitHub keeps issues, pull requests, reviews and commit history when the repository moves to an organization, so nothing has to be copied.

## Existing GitHub organizations (checked 2026-11-12)

A GitHub search found an organization `Golisano-Institute-for-Business` ("Golisano Institute for Business and Entrepreneurship", website golisanoinstitute.org, created 2025-03-28). It has no public repositories and no public members, and its owners are UNKNOWN. An older empty organization `Golisano-Institute` also exists (created 2025-01-15). No investment-club organization was found. Before the club creates its own organization, ask Institute staff whether they own `Golisano-Institute-for-Business`. If they do, the club repository can live there (Step 1.1, "select the existing Institute organization"), or the Institute can approve a separate club organization.

## Phase 0: Preserve the system and name owners

Target: complete in November 2026.

### Step 0.1: Assign roles and record access

**Owner:** Club officer with the faculty sponsor.

**Prerequisites:** The club can contact the Institute signage administrator and Canvas instructor.

**Actions:**

1. Fill every role in the role table.
2. Name a primary and backup organization owner.
3. Record who can administer GitHub, Yodeck, Canvas, and the cafe players.
4. Record the repository, Pages address, Yodeck item names, Canvas course, and backup computers.
5. Store the access inventory in club-controlled storage.
6. Keep passwords, tokens, recovery codes, and API keys out of that inventory.

**Check:** Each role has a named person. Each person can state which system they control and how they recover access.

**Rollback:** No live component changes. Correct the inventory and role assignments.

### Step 0.2: Make an independent repository backup

**Owner:** Site maintainer.

**Prerequisites:** Club-controlled storage exists. The faculty sponsor can control access to it.

**Actions:**

1. Create a mirror from the public repository without embedding a credential:

   ```sh
   git clone --mirror https://github.com/kevinhsykes/golisano-club-display.git <backup-directory>
   ```

2. Record the source commit and backup date.
3. Store a second copy in a separate club-controlled location.
4. Save the Actions and Pages settings as dated screenshots or text.
5. Save the Yodeck and Canvas address inventory with the backup record.
6. Exclude credentials and recovery codes from the backup.

**Check:**

```sh
git -C <backup-directory> rev-parse HEAD
git -C <backup-directory> fsck --full
```

The reported commit must match the source commit selected for the backup. Both backup locations must be readable by the faculty sponsor and site maintainer.

**Rollback:** No live component changes. Replace a bad backup with a new mirror.

### Step 0.3: Capture the operating baseline

**Owner:** Site maintainer with the Institute signage administrator and Canvas instructor.

**Prerequisites:** Market-hours access to the Actions page and physical access to the TVs.

**Actions:**

1. Record the latest successful `pages` run and its commit.
2. Record the newest quote time and `Price snapshot` commit.
3. Open `index.html`, `tv.html`, `trades.html`, `screens.html`, and `board.html`.
4. Check every TV and the Canvas link.
5. Run these commands on each backup computer:

   ```sh
   tools/fleet_refresh_install.sh status
   systemctl --user list-timers --all
   ```

6. Record the old `golisano-refresh` timer state (disabled 2026-11-11; files still in `~/.local/bin` and `~/.config/systemd/user` on KPC).
7. Record the Git push credential location (GitHub CLI login on each backup computer) without copying its value.

**Check:** The baseline names every working page, every physical screen, every timer, and every credential location. Any unreadable item stays UNKNOWN.

**Rollback:** No live component changes. Correct the baseline record.

### Step 0.4: Close the documentation gaps

**Owner:** Kevin with the site maintainer.

**Prerequisites:** Steps 0.1 through 0.3 are complete.

**Actions:**

1. Document the exact old timer names and cleanup procedure.
2. Document the calendar generation command and its Python environment.
3. Document the brokerage evidence and reconciliation process.
4. Document the owner who checks Actions after failures.
5. Add the duplicated `web/board.html` symbol list to the per-trade runbook.
6. Record all remaining UNKNOWN items with an owner and deadline.

**Check:** The site maintainer can find a written procedure for each routine task and each known failure.

**Rollback:** No live component changes. Correct the documents.

## Phase 1: Build club ownership and practice the handoff

Target: complete before January 2027.

### Step 1.1: Create and protect the organization

**Owner:** Faculty sponsor with the club officer.

**Prerequisites:** The Institute approves the organization ownership decision. Both initial owners have GitHub accounts.

**Actions:**

1. Create the approved organization or select the existing Institute organization.
2. Add the faculty sponsor and club officer as owners.
3. Add the site maintainer with the least access needed for the work.
4. Add Kevin as a temporary administrator for the transfer.
5. Turn on two-factor authentication for each owner.
6. Configure organization recovery under faculty control.
7. Record the owners and recovery method in the access inventory.
8. Add club members who work on the site as organization members, so they can open issues and pull requests.
9. Protect `main`: require a pull request with one approving review from another member, and require the `checks` job (`.github/workflows/checks.yml`, which runs the builds and all tests on every pull request) to pass. Allow the price-refresh commits through (the GitHub Actions bot) so scheduled refreshes still land.

**Check:** The faculty sponsor and club officer can each open the organization owner settings. Kevin is not the only owner. A test pull request from a member needs a second member's review before it can merge.

**Rollback:** Remove incorrect memberships. Keep the current repository in place until the transfer phase.

### Step 1.2: Practice a local build and recovery

**Owner:** Site maintainer with Kevin available for questions.

**Prerequisites:** The maintainer has Python 3.12, Node 22 or newer, Git, and a fresh clone.

**Actions:**

1. Clone the repository without using Kevin's working directory.
2. Create a disposable practice branch.
3. Change only the `source` note on an existing practice transaction. Do not change shares, prices, or execution times.
4. Run:

   ```sh
   python3 build.py
   python3 build.py --public --out web/data/portfolio.public.json
   npm test
   python3 -m unittest discover -s test -p 'test_*.py'
   ```

5. Read the diff and confirm that the practice note is the only source-data change.
6. Restore from the independent mirror into a second disposable directory.
7. Run the same builds and tests in the restored copy.
8. Delete the disposable branch after the checks.

**Check:** Both clones produce passing tests. The maintainer can explain the full payload, public payload, generated version file, and static quotes API.

**Rollback:**

```sh
git restore data/source/positions.json web/data/portfolio.public.json
```

Delete only the disposable practice directories and branch.

### Step 1.3: Practice the trade process with the next real fill

**Owner:** Trade recorder and trade reviewer.

**Prerequisites:** A real club trade has fill evidence. Step 1.2 passed.

**Actions:**

1. Open a "Record a trade" issue with the fill evidence.
2. Create a branch from the current `main` and add one row per fill to `data/source/positions.json`.
3. Link the fill evidence in the transaction `source` without exposing account credentials.
4. Mark an estimated price only under the estimate rules in the README.
5. For a new symbol, update `positions.json`, `instrument-profiles.json`, `worker/index.js`, and `web/board.html`.
6. Refresh quotes when the newest saved quote predates the trade.
7. Run both builds and all tests.
8. Have the trade reviewer compare every fill with the evidence.
9. Commit, push the branch, and open a pull request that links the issue. Wait for the `checks` job to pass.
10. Have the trade reviewer approve the pull request, then merge it. The merge to `main` deploys the site.
11. After the `pages` run finishes, check `trades.html`, `index.html`, `tv.html`, and `board.html` on the live site.

**Check:** The reviewer confirms the shares, execution times, prices, fees, estimate labels, and realized gains. All tests pass. All affected pages show the trade correctly.

**Rollback:** Revert the trade commit through a reviewed change. Redeploy the previous source state. Do not alter the frozen statement.

### Step 1.4: Decide the public feed and amount exposure

**Owner:** Faculty sponsor and club officer with Institute procurement or legal support as needed.

**Prerequisites:** The club knows which pages are public and which dollar amounts they expose.

**Actions:**

1. Record the data-licence decision.
2. Apply for the selected non-profit or display licence in the Institute's name when appropriate.
3. Get written confirmation that the plan covers the cafe TVs and Canvas-linked page.
4. Record whether real-time, delayed, consolidated, or partial-market prices are allowed.
5. Review TradingView's current terms before using `board.html` as the interim public display.
6. Confirm or change the payload decision. Today the site publishes dollar amounts (decided 2026-10-26).
7. Give any paid commitment to the authorized Institute approver.

**Check:** The written terms name the actual display use. The selected pages and payload match the decision.

**Rollback:** Stop the Yahoo-powered public display. Use an approved prices-only display or remove price content until the licence is settled.

### Step 1.5: Rehearse the address cutover

**Owner:** Site maintainer, Institute signage administrator, and Canvas instructor.

**Prerequisites:** The organization exists. The complete Yodeck and Canvas inventory exists.

**Actions:**

1. Write the future address as `https://<org>.github.io/golisano-club-display/` without creating a guessed organization name.
2. List every old and new Yodeck Web Page address.
3. List the old and new Canvas link.
4. Choose a market-hours cutover window with Institute staff present.
5. Prepare the previous Yodeck and Canvas values for rollback.
6. Prepare an approved outage display for a failed cutover.
7. Agree who checks each physical TV and the Canvas course.

**Check:** Every old address has a named replacement, a person assigned to change it, and a person assigned to check it.

**Rollback:** No live component changes. Correct the cutover sheet.

## Phase 2: Transfer the repository and change public addresses

Target: complete in January 2027, with at least four weeks before graduation.

### Step 2.1: Freeze changes and stop Kevin's writers

**Owner:** Kevin with the site maintainer.

**Prerequisites:** The cutover window started. The independent backup passed its checks. The organization can receive the repository.

**Actions:**

1. Stop merging changes into `main` during the cutover.
2. Run this command from the repository on KPC and fn:

   ```sh
   tools/fleet_refresh_install.sh uninstall
   ```

3. Stop and disable the older `golisano-refresh` timer using the exact units recorded in Phase 0.
4. Confirm that no old or new refresh service is active.
5. Check `~/.config/systemd/user` and `~/.local/bin` for the recorded old and new paths.
6. Leave `~/.local/share/golisano-refresh` untouched until the transfer checks pass.
7. Record the last backup-refresh commit and service state.

**Check:** Neither computer can start a price-refresh service. No new host-suffixed `Price snapshot` commit appears during the freeze.

**Rollback:** If the transfer is canceled before ownership changes, reinstall the new timer with the recorded offsets. Use offset 0 on KPC and offset 7 on fn. Restore the old timer only from its recorded unit files.

### Step 2.2: Transfer repository ownership

**Owner:** Kevin with the faculty sponsor and club officer.

**Prerequisites:** Step 2.1 passed. The organization has two non-Kevin owners. Kevin has transfer permission.

**Actions:**

1. Open the repository Settings page.
2. Use General, then Transfer ownership.
3. Select the approved organization.
4. Keep the name `golisano-club-display`.
5. Confirm that the faculty sponsor, club officer, site maintainer, and Kevin have the intended access.
6. Update each maintainer's local remote after the transfer:

   ```sh
   git remote set-url origin https://github.com/<org>/golisano-club-display.git
   git fetch origin
   ```

7. Record the transfer time and commit.

**Check:**

```sh
git ls-remote https://github.com/<org>/golisano-club-display.git
```

The organization repository shows the expected `main` commit. Both non-Kevin owners can open its administration settings.

**Rollback:** Transfer the repository back only if the new home cannot administer it and Kevin still has the required access. Repeat the timer and address freeze before any reverse transfer.

### Step 2.3: Restore Actions and Pages in the new home

**Owner:** Site maintainer with an organization owner.

**Prerequisites:** Step 2.2 passed. Organization policy allows the required workflow permissions.

**Actions:**

1. Open Settings, then Pages.
2. Select GitHub Actions as the source if the transfer did not preserve it.
3. Open the Actions settings and allow the required workflows.
4. Under Workflow permissions, select read and write permissions when organization policy permits them.
5. Confirm that the `pages` workflow keeps its declared contents, Pages, and identity-token permissions.
6. Run the `pages` workflow manually.
7. Read any failed step and fix its cause before retrying.
8. Record the run identifier and deployed commit.

**Check:** The build and deploy jobs pass. The new organization address serves all five HTML pages. A market-hours `Price snapshot` commit arrives within 30 minutes.

**Rollback:** Keep the repository transfer in place if only Pages or Actions failed. Restore the settings and rerun the workflow. Use the prepared outage display until the new address works.

### Step 2.4: Replace account-specific references

**Owner:** Site maintainer with a reviewer.

**Prerequisites:** The organization site deploys successfully.

**Actions:**

1. Find old account references:

   ```sh
   git grep -n kevinhsykes
   ```

2. Update production addresses and source links that must name the organization.
3. Include `web/screens.html` and any maintained backup default that still names Kevin.
4. Replace the placeholder in `canvas/portfolio-page.html` with the selected address when using that template.
5. Run both builds and all tests.
6. Review and merge the change through the club's normal review process.
7. Check the deployed `screens.html` copy buttons.

**Check:** Production links no longer depend on Kevin's account. Historical records may retain Kevin's name when it describes authorship or an old event.

**Rollback:** Revert the reference-change commit and redeploy. This does not reverse the repository transfer.

### Step 2.5: Change Yodeck

**Owner:** Institute signage administrator.

**Prerequisites:** The new `tv.html` works in a browser. The cutover sheet lists every item.

**Actions:**

1. Open each recorded Yodeck Web Page item.
2. Replace the old `tv.html` address with the new organization address.
3. Keep the intended panel and amount query parameters.
4. Leave Yodeck page refresh off or set it to hours.
5. Publish the changes to every assigned screen.
6. Restart a screen through Yodeck only if it keeps an old page.
7. Check every physical TV after its reload.

**Check:** Every TV loads the new address. The portfolio figures, quote timestamp, panel rotation, and warning banners work. No TV uses Kevin's Pages address.

**Rollback:** Restore the recorded Yodeck values only while the old site still serves. Otherwise use the prepared outage display or an approved working board address.

### Step 2.6: Change Canvas

**Owner:** Canvas instructor.

**Prerequisites:** The new `index.html` works. The instructor can edit the club course.

**Actions:**

1. Open the recorded Canvas page.
2. Change the portfolio link to the new organization `index.html` address.
3. Preserve `target="_blank"` and `rel="noopener"` when editing HTML.
4. Save and publish the page.
5. Open the link as a club member rather than only as the instructor.
6. Update the link text if it contains the old address.

**Check:** A club member can open the new portfolio page from Canvas. The browser address names the organization.

**Rollback:** Restore the previous Canvas HTML only while the old target works. Otherwise replace the link with an approved status message until the new page is restored.

### Step 2.7: Observe the transferred system

**Owner:** Site maintainer with the faculty sponsor.

**Prerequisites:** Steps 2.2 through 2.6 passed.

**Actions:**

1. Observe at least five market days.
2. Check the workflow, quote commits, page timestamps, and physical TVs each market day.
3. Record one manual workflow recovery practice.
4. Confirm that Kevin's computers made no new commits.
5. Remove the dedicated backup clones only after the observation period passes.
6. Remove Kevin's repository credentials from his backup computers after confirming their locations.
7. Keep Kevin's organization access until the final independence check.

**Check:** The club completes five market days without a Kevin computer, credential, or manual repair. All failures have a club-owned resolution record.

**Rollback:** Do not restore personal timers as the default response. Fix the club-owned workflow or use the approved fallback display while the club repairs the service.

## Phase 3: Replace the temporary data path and reduce remaining lock-in

Target: complete after transfer and before graduation where possible.

### Step 3.1: Bring public displays into the licence decision

**Owner:** Faculty sponsor and club officer with the site maintainer.

**Prerequisites:** Step 1.4 recorded the allowed public use.

**Actions:**

1. Point public TVs to the approved display.
2. Change the Canvas destination if the portfolio page lacks public-display rights.
3. Use `board.html` only after its TradingView terms and network path pass review.
4. Remove the Yahoo-powered page from public use until a licence covers it.
5. Deploy the public percent-only payload when the club selects that option.
6. Check the actual JSON response, not only the interface, when validating amount removal.

**Check:** Every public page uses an approved source and payload. No Yahoo-powered public page remains outside the written licence decision.

**Rollback:** Show the approved prices-only board or an outage message. Keep the source repository and internal records intact.

### Step 3.2: Deploy the Worker only after approval

**Owner:** Site maintainer with the faculty sponsor as account owner.

**Prerequisites:** A licensed feed, club-owned Cloudflare account, selected payload, operating budget approval, and a named maintainer all exist.

**Actions:**

1. Create or select the club-owned Cloudflare account.
2. Give the faculty sponsor and site maintainer appropriate access.
3. Install the Wrangler version selected through a reviewed repository change.
4. Authenticate with `npx wrangler login` under the club account.
5. Create the KV namespace:

   ```sh
   npx wrangler kv namespace create QUOTES
   ```

6. Put the returned ID in `wrangler.jsonc`.
7. Set the provider and delay metadata to match the licence.
8. Store the selected feed secret without committing it:

   ```sh
   npx wrangler secret put TWELVEDATA_KEY
   ```

   Use `TIINGO_KEY` instead when Tiingo is selected.

9. Build the selected payload and run all tests.
10. Deploy with `npx wrangler deploy`.
11. Check `/api/health`, `/api/quotes`, and `/api/history` during market hours.
12. Test every HTML page on the Worker address.
13. Change Yodeck and Canvas only after the Worker passes the same observation process used for Pages.

**Check:** `last_attempt.ok` is true. `newest_quote_utc` advances within the licensed feed's expected delay. A simulated bad provider response preserves the last good quotes. The faculty sponsor can administer the account without Kevin.

**Rollback:** Point Yodeck and Canvas back to the last approved working address. Disable the Worker cron before disabling the feed credential. Keep the KV data until the club confirms that rollback succeeded.

### Step 3.3: Add a custom domain only with Institute ownership

**Owner:** Faculty sponsor and Institute DNS administrator.

**Prerequisites:** The Institute selects and controls the domain. The target host works without the domain.

**Actions:**

1. Record the domain owner, registrar, renewal owner, and DNS administrator.
2. Configure the host through GitHub Pages or Cloudflare documentation.
3. Configure HTTPS through the selected host.
4. Test the exact domain and every page path.
5. Change Yodeck and Canvas through their checked cutover procedures.
6. Keep the organization Pages address as a checked fallback where the host supports it.

**Check:** The domain serves the correct pages with valid HTTPS. Institute staff can renew and change DNS without Kevin.

**Rollback:** Remove the new domain from Yodeck and Canvas. Restore the last working host address. Leave DNS removal to the Institute after service recovery.

### Step 3.4: Establish recurring club operations

**Owner:** Club officer, site maintainer, trade recorder, and trade reviewer.

**Prerequisites:** The selected host and display path are stable.

**Actions:**

1. Assign the weekly Actions and page check.
2. Assign the per-trade recorder and reviewer for the academic term.
3. Schedule the annual feed-licence and public-data review.
4. Schedule calendar regeneration before January 2028.
5. Schedule a restore test for the independent Git backup.
6. Schedule an officer-to-officer practice handoff before each graduation cycle.
7. Record all schedules in a club-owned calendar with two recipients.
8. Triage open issues at each club meeting: assign an owner to each new trade, display problem and decision.

**Check:** Each recurring task has a named owner, backup owner, due date, and evidence location.

**Rollback:** Reassign a missed task immediately. Record any missed check as UNKNOWN until someone performs it.

## Phase 4: Prove independence before Kevin graduates

Target: complete by February 2027, before Kevin's last day.

### Step 4.1: Run the final independence test

**Owner:** Faculty sponsor, club officer, and site maintainer without Kevin's active help.

**Prerequisites:** All earlier phases passed. At least one real trade went through the club-owned process.

**Actions:**

1. Sign in with only club and faculty access.
2. Open organization settings and confirm two non-Kevin owners.
3. Run a manual `pages` deployment.
4. Record a safe practice source-note change on a disposable branch and run all tests.
5. Restore the independent backup into a clean directory and run all tests.
6. Change no Yodeck address, but prove that Institute staff can open and edit every item.
7. Prove that the Canvas instructor can edit the link.
8. Check all pages, every TV, and the Canvas member view.
9. Confirm that no routine task uses KPC, fn, or Kevin's credentials.
10. Resolve or explicitly accept every remaining UNKNOWN item.

**Check:** Club personnel complete every task without Kevin. The evidence record includes run identifiers, commits, dates, and physical-screen checks.

**Rollback:** Keep Kevin's temporary access only for a named failed item. Set a short repair deadline before graduation. Do not mark independence complete while that item remains open.

### Step 4.2: Remove Kevin's remaining access

**Owner:** Faculty sponsor and club officer with Kevin.

**Prerequisites:** Step 4.1 passed with no open failure.

**Actions:**

1. Remove Kevin's organization owner or repository administrator access.
2. Remove Kevin's Cloudflare and feed access if those services exist.
3. Remove any remaining personal backup timers, binaries, clones, and push credentials using the recorded inventory.
4. Preserve Kevin's authorship in Git history and documentation.
5. Give the final access inventory and unresolved-risk list to the faculty sponsor and new officer.
6. Record the independence completion date.

**Check:** Kevin has no administrative or write credential. The club still passes the deployment, trade, TV, Canvas, and recovery checks.

**Rollback:** Use organization recovery under faculty control. Do not restore a personal dependency as the routine operating model.

## Timeline

| Deadline | Required result |
|---|---|
| November 2026 | Roles assigned. Repository and settings backed up. Timers and credentials inventoried. Baseline recorded. |
| December 2026 | Organization has two owners. Local build and restore practice passed. Feed and payload decisions started. Cutover sheet complete. |
| Before January 2027 | Phase 1 complete. Next real trade used for recorder and reviewer practice when one occurs. |
| January 2027 | Repository transferred. Kevin's timers stopped. Actions and Pages work under the organization. Yodeck and Canvas use the new address. |
| January to February 2027 | Five-market-day observation passed. Public licence path settled or interim display active. Optional Worker and domain work completed only if approved. |
| February 2027 | Final independence test passed. Kevin's access and personal-computer dependencies removed. |
| Before January 2028 | NYSE calendar regenerated and tested under club ownership. |

## Risk register

| Risk | Effect | Control |
|---|---|---|
| Old Pages address stops after transfer | Yodeck and Canvas can fail immediately | Change every recorded address in one staffed cutover window and check every consumer |
| Repository has one owner | Absence or graduation locks out the club | Keep at least two non-Kevin organization owners with separate recovery paths |
| A backup timer survives transfer | Kevin's computer can keep writing to the club repository | Stop old and new units before transfer and monitor host-suffixed commits |
| Backup credentials remain on Kevin's computers | Retained write access remains after handoff | Inventory and remove each credential after the observation period |
| GitHub disables the cron after inactivity | Quotes become stale without an obvious code failure | Check Actions weekly and after breaks. Re-enable the workflow when needed |
| Yahoo blocks or changes its endpoint | Current prices and history stop | Keep last good data, monitor timestamps, and move to a licensed provider |
| Yahoo or TradingView terms do not allow the display | The club can publish data outside its rights | Get written approval or remove the affected public display |
| A trade row is wrong or incomplete | The build fails or public figures are wrong | Use fill evidence, separate review, builds, and all tests before merge |
| A new symbol misses a duplicated list | The Worker test fails or `board.html` omits the holding | Update both Worker and board lists in the per-trade runbook |
| The full payload exposes more data than intended | Shares and dollar values remain publicly fetchable | Deploy the public payload and inspect its JSON when percent-only display is selected |
| Calendar data expires | Holidays, early closes, and Worker refreshes become wrong after 2027 | Document the generator and schedule renewal before January 2028 |
| A Worker is deployed before ownership and licensing are ready | A new personal account or unlicensed feed replaces the old dependency | Keep it undeployed until account, licence, budget, and maintainer checks pass |
| A custom domain depends on a student | DNS or renewal fails after graduation | Use Institute-owned DNS and renewal only |
| Backup exists but cannot be restored | Repository recovery fails when needed | Run restore builds and tests in Phase 1 and on a recurring schedule |
| Live settings differ from the repository | The written plan misses a timer, screen, or permission | Treat unreadable settings as UNKNOWN and complete the live inventory before cutover |
| The five-day observation skips a market closure | Refresh problems remain hidden | Include normal market sessions in the observation period and record closures separately |
| Public repository history retains sensitive data | Transfer alone does not remove old published values | Review data exposure before transfer and use the public payload going forward |

## Completion criteria

The club can call the system independent only when all of these statements have current evidence:

- Two non-Kevin owners control the repository and recovery path.
- GitHub Actions or the selected host deploys without Kevin's credentials.
- No Kevin computer runs a refresh, deployment, or monitoring dependency.
- Every TV and the Canvas link use a club-controlled address.
- A named recorder and reviewer process trades without Kevin.
- Public prices and dollar amounts match written club and Institute decisions.
- A club-controlled backup restores into a tested working copy.
- Routine monitoring, calendar renewal, licence review, and officer handoff have owners.
- The final independence test passed before Kevin's access was removed.
