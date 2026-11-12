#!/bin/bash
# Install, remove or show the backup price refresh (tools/fleet_refresh.sh) as a systemd user
# timer on this computer. See docs/HANDOFF.md, "Backup refresh".
#   tools/fleet_refresh_install.sh install <offset-minutes 0-12>
#   tools/fleet_refresh_install.sh uninstall
#   tools/fleet_refresh_install.sh status
# The timer fires every 15 minutes in US market hours (New York time), <offset> minutes after
# :02/:17/:32/:47. Give each computer a different offset so that they take turns.
set -euo pipefail
UNIT=golisano-fleet-refresh
UNIT_DIR="$HOME/.config/systemd/user"
BIN="$HOME/.local/bin/golisano-fleet-refresh"
SRC="$(cd "$(dirname "$0")" && pwd)/fleet_refresh.sh"

case "${1:-}" in
  install)
    off="${2:?usage: $0 install <offset-minutes 0-12>}"
    [[ "$off" =~ ^[0-9]+$ ]] && [ "$((10#$off))" -le 12 ] || { echo "offset must be 0-12" >&2; exit 2; }
    off=$((10#$off))   # "08" is not valid octal in bash arithmetic
    for t in git python3 flock timeout; do command -v "$t" >/dev/null || { echo "missing: $t" >&2; exit 2; }; done
    node_bin="${GOLISANO_NODE:-$(command -v node || true)}"
    node_major=$("$node_bin" -p 'process.versions.node.split(".")[0]' 2>/dev/null || echo 0)
    [ "$node_major" -ge 22 ] || { echo "need Node 22 or newer (found ${node_major:-none} at ${node_bin:-nowhere}); set GOLISANO_NODE" >&2; exit 2; }
    m() { printf "%02d" $(( $1 + off )); }
    mkdir -p "$UNIT_DIR" "$(dirname "$BIN")"
    install -m 755 "$SRC" "$BIN"
    cat >"$UNIT_DIR/$UNIT.service" <<EOF
# Backup price refresh for the Golisano club site. Source: tools/fleet_refresh.sh in the repo.
# Remove: tools/fleet_refresh_install.sh uninstall
[Unit]
Description=Golisano club site backup price refresh (acts only when the site is stale)
After=network-online.target
[Service]
Type=oneshot
ExecStart=$BIN
Environment=GOLISANO_NODE=$node_bin
Environment=GOLISANO_SERVED_CHECK=${GOLISANO_SERVED_CHECK:-}
TimeoutStartSec=900
Nice=10
EOF
    cat >"$UNIT_DIR/$UNIT.timer" <<EOF
[Unit]
Description=Golisano club site backup price refresh, US market hours
[Timer]
OnCalendar=Mon..Fri 09:$(m 32),$(m 47) America/New_York
OnCalendar=Mon..Fri 10..15:$(m 2),$(m 17),$(m 32),$(m 47) America/New_York
OnCalendar=Mon..Fri 16:$(m 2),$(m 17) America/New_York
Persistent=false
AccuracySec=30s
[Install]
WantedBy=timers.target
EOF
    systemctl --user daemon-reload
    systemctl --user enable --now "$UNIT.timer"
    systemctl --user list-timers "$UNIT.timer" --no-pager
    ;;
  uninstall)
    systemctl --user disable --now "$UNIT.timer" 2>/dev/null || true
    # Also end a run in progress, so it cannot push after the repository moves.
    systemctl --user stop "$UNIT.service" 2>/dev/null || true
    rm -f "$UNIT_DIR/$UNIT.service" "$UNIT_DIR/$UNIT.timer" "$BIN"
    systemctl --user daemon-reload
    echo "removed. The clone in ~/.local/share/golisano-refresh stays; delete it by hand if you want."
    ;;
  status)
    systemctl --user list-timers "$UNIT.timer" --no-pager || true
    journalctl --user -u "$UNIT.service" -n 10 --no-pager || true
    ;;
  *) sed -n '2,8p' "$0"; exit 2 ;;
esac
