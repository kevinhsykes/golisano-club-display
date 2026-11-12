#!/bin/bash
# Backup price refresh that runs on the current owner's own computers (see docs/HANDOFF.md).
# GitHub's scheduled `pages` run is the primary refresh. This script acts only when the saved
# prices on origin/main (collected_at_utc in data/source/quotes-current.json) are older than
# MAX_AGE_MIN minutes. Then it refreshes in a dedicated clone on this host and pushes to main;
# the push starts the `pages` workflow, which deploys. It uses git only: no GitHub API calls,
# so the API rate limit cannot stop it.
# Install or remove it with tools/fleet_refresh_install.sh. Nothing in the site needs it.
set -uo pipefail

REPO_SLUG=${GOLISANO_REPO:-kevinhsykes/golisano-club-display}
STATE_DIR=${GOLISANO_STATE_DIR:-$HOME/.local/share/golisano-refresh}
CLONE="$STATE_DIR/repo"
MAX_AGE_MIN=${GOLISANO_MAX_AGE_MIN:-16}
NODE=${GOLISANO_NODE:-node}           # Node 22 or newer (the Worker test imports JSON with "with")
DRY_RUN=${GOLISANO_DRY_RUN:-}          # set to 1: do everything except the push
HOST=$(hostname -s)
mkdir -p "$STATE_DIR"

log() { echo "$(date -u +%FT%TZ) [$HOST] $*"; }

# One run at a time on this host.
exec 9>"$STATE_DIR/lock"
flock -n 9 || { log "another run holds the lock; skip"; exit 0; }

if [ ! -d "$CLONE/.git" ]; then
  timeout 120 git clone -q "https://github.com/$REPO_SLUG.git" "$CLONE" || { log "clone failed"; exit 1; }
fi
cd "$CLONE" || exit 1

# Prints "fresh <age>" or "stale <age|reason>" for the saved prices on origin/main.
check_freshness() {
  timeout 60 git fetch -q origin main || { echo "error fetch"; return; }
  git show origin/main:data/source/quotes-current.json 2>/dev/null | python3 -c '
import sys, json, datetime
max_age = int(sys.argv[1])
try:
    t = datetime.datetime.fromisoformat(json.load(sys.stdin)["collected_at_utc"].replace("Z", "+00:00"))
except Exception as e:
    print("stale unreadable:" + type(e).__name__); sys.exit()
age = (datetime.datetime.now(datetime.timezone.utc) - t).total_seconds() / 60
if age < -5:
    print(f"stale future-dated:{-age:.0f}min")      # a clock or data fault: refresh to replace it
elif age < max_age:
    print(f"fresh {age:.0f}min")
else:
    print(f"stale {age:.0f}min")
' "$MAX_AGE_MIN"
}

# Build a fresh snapshot commit on top of origin/main. The clone belongs to this script, so a hard
# reset is safe and no generated file is ever left behind to block the next run.
build_commit() {
  git reset -q --hard origin/main && git clean -qfdx -- data web || return 1
  timeout 120 python3 tools/snapshot_quotes.py || { log "snapshot_quotes failed"; return 1; }
  timeout 180 python3 tools/snapshot_history.py || log "history refresh failed; previous files kept"
  timeout 120 python3 build.py >/dev/null && timeout 120 python3 build.py --public --out web/data/portfolio.public.json >/dev/null \
    || { log "build failed"; return 1; }
  timeout 300 "$NODE" --test test/core.test.mjs test/worker.test.mjs >"$STATE_DIR/last-test.log" 2>&1 \
    || { log "node tests failed (see $STATE_DIR/last-test.log)"; return 1; }
  timeout 300 python3 -m unittest discover -s test -p 'test_*.py' >>"$STATE_DIR/last-test.log" 2>&1 \
    || { log "python tests failed (see $STATE_DIR/last-test.log)"; return 1; }
  git checkout -q -- web/version.json 2>/dev/null || true   # CI writes the deployed build stamp
  git add -A data/source web/data web/api
  git diff --cached --quiet && { log "no price change"; return 2; }
  git -c user.name="price-refresh[$HOST]" -c user.email="price-refresh@users.noreply.github.com" \
    commit -q -m "Price snapshot $(date -u +%Y-%m-%dT%H:%MZ) ($HOST)"
}

state=$(check_freshness)
case "$state" in
  fresh*) log "prices are fresh (${state#fresh }); nothing to do"; exit 0 ;;
  error*) log "git fetch failed"; exit 1 ;;
esac
log "prices are stale (${state#stale }); refreshing on this host"

for attempt in 1 2; do
  build_commit; rc=$?
  [ "$rc" = 2 ] && exit 0
  [ "$rc" = 0 ] || exit 1
  if [ -n "$DRY_RUN" ]; then log "dry run: built $(git rev-parse --short HEAD), not pushed"; exit 0; fi
  if timeout 120 git push -q origin HEAD:main; then log "pushed $(git rev-parse --short HEAD)"; exit 0; fi
  # Someone pushed first. If it was a fresh snapshot, ours is not needed. Otherwise rebuild on
  # their commit (never rebase generated files, never force-push).
  state=$(check_freshness)
  case "$state" in
    fresh*) log "another refresh landed first; dropping ours"; exit 0 ;;
    error*) log "git fetch failed after a rejected push"; exit 1 ;;
  esac
  log "push rejected (attempt $attempt); rebuilding on the new origin/main"
done
log "push failed twice"; exit 1
