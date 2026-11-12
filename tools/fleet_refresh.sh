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
# The deployed site. Its saved prices can be stale even when main is fresh, if GitHub's deploy
# step fails (it did six times on 2026-11-11). Change this after the repository moves.
SITE_URL=${GOLISANO_SITE_URL:-https://kevinhsykes.github.io/golisano-club-display}
# Live-site check: on one computer only (GOLISANO_SERVED_CHECK=1), so two hosts never take turns
# redeploying. GitHub Pages caches api/quotes for up to 10 minutes and a query string does not
# bypass it, so the limit is 45 minutes (30 + cache + margin).
SERVED_CHECK=${GOLISANO_SERVED_CHECK:-}
MAX_SERVED_AGE_MIN=${GOLISANO_MAX_SERVED_AGE_MIN:-45}
REDEPLOY_COOLDOWN_MIN=${GOLISANO_REDEPLOY_COOLDOWN_MIN:-45}
MIN_HEAD_AGE_MIN=${GOLISANO_MIN_HEAD_AGE_MIN:-15}
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
  git add -A data/source web/data web/api || { log "git add failed"; return 1; }
  git diff --cached --quiet; local d=$?
  [ "$d" = 0 ] && { log "no price change"; return 2; }
  [ "$d" = 1 ] || { log "git diff failed ($d)"; return 1; }
  git -c user.name="price-refresh[$HOST]" -c user.email="price-refresh@users.noreply.github.com" \
    commit -q -m "Price snapshot $(date -u +%Y-%m-%dT%H:%MZ) ($HOST)"
}

# Age in minutes of the prices the live site serves (api/quotes), or "unknown".
served_age() {
  curl -fsS --max-time 20 "$SITE_URL/api/quotes?t=$(date +%s)" 2>/dev/null | python3 -c '
import sys, json, datetime
try:
    t = datetime.datetime.fromisoformat(json.load(sys.stdin)["collected_at_utc"].replace("Z", "+00:00"))
    print(int((datetime.datetime.now(datetime.timezone.utc) - t).total_seconds() // 60))
except Exception:
    print("unknown")'
}

# Main is fresh but the live site is not: the deploy failed or never ran. Ask GitHub to run the
# pages workflow (one API call); if that fails, push an empty commit, which also deploys.
# Waits until the newest commit on main is 15 minutes old (deploy time plus the Pages cache), and
# allows one redeploy per REDEPLOY_COOLDOWN_MIN by either path (state file on this computer).
# Known gap: the last check on KPC (offset 0) is 4:17 PM ET, so a deploy that fails after that is not
# retried until the next market day.
redeploy_if_served_stale() {
  [ "$SERVED_CHECK" = 1 ] || return 0
  local head_age age last
  head_age=$(( $(date +%s) - $(git log -1 --format=%ct origin/main) ))
  [ "$head_age" -ge $(( MIN_HEAD_AGE_MIN * 60 )) ] || return 0
  age=$(served_age)
  if [ "$age" = unknown ]; then log "live site prices: could not read $SITE_URL/api/quotes"; return 0; fi
  [ "$age" -gt "$MAX_SERVED_AGE_MIN" ] || return 0
  last=$(cat "$STATE_DIR/last-redeploy" 2>/dev/null || echo 0)
  if [ $(( $(date +%s) - last )) -lt $(( REDEPLOY_COOLDOWN_MIN * 60 )) ]; then
    log "live site still ${age} min stale after a recent redeploy; waiting"; return 0
  fi
  log "live site serves ${age}-min-old prices while main is fresh; redeploying"
  if [ -n "$DRY_RUN" ]; then log "dry run: no redeploy"; return 0; fi
  # Fail closed: without a recorded cooldown, do not redeploy.
  date +%s > "$STATE_DIR/last-redeploy" || { log "cannot record the redeploy cooldown; not redeploying"; return 0; }
  if timeout 60 gh workflow run pages -R "$REPO_SLUG" --ref main 2>/dev/null; then log "asked GitHub to run pages"; return 0; fi
  git reset -q --hard origin/main && \
    git -c user.name="price-refresh[$HOST]" -c user.email="price-refresh@users.noreply.github.com" \
      commit -q --allow-empty -m "Redeploy: live site prices ${age} min old ($HOST)" && \
    timeout 120 git push -q origin HEAD:main && log "pushed an empty commit to redeploy" || log "redeploy push failed"
}

state=$(check_freshness)
case "$state" in
  fresh*) log "prices are fresh (${state#fresh }); nothing to do"
          redeploy_if_served_stale; exit 0 ;;
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
