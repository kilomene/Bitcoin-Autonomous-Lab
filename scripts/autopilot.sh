#!/usr/bin/env bash
# BAL Autopilot control:
#   start | stop | status | log
#   install-service        install + enable the autopilot systemd
#                          unit (reboot persistence, no cron needed)
#   install-node-service   install + enable the mainnet node
#                          systemd unit (needs the .local/mainnet
#                          datadir; see docs/AUTOPILOT.md)
set -euo pipefail
cd "$(dirname "$0")/.."
ROOT="$PWD"
mkdir -p .local

install_unit() {
  # $1 = template in scripts/, $2 = unit name
  local tpl="$1" name="$2" dest="/etc/systemd/system/$2"
  if ! command -v systemctl >/dev/null 2>&1; then
    echo "no systemctl on this machine; run the autopilot with" >&2
    echo "'bash scripts/autopilot.sh start' instead." >&2
    return 1
  fi
  sed -e "s|REPLACE_REPO|$ROOT|g" \
      -e "s|REPLACE_DIST|$HOME/workspace/bitcoin-core-dist|g" \
      "scripts/$tpl" > "$dest"
  systemctl daemon-reload
  systemctl enable "$name"
  echo "installed and enabled $name"
}

case "${1:-status}" in
  start)
    AP_PID=""
    if [ -f .local/autopilot.lock ]; then
      AP_PID="$(cat .local/autopilot.lock 2>/dev/null || true)"
    fi
    if [ -n "$AP_PID" ] && kill -0 "$AP_PID" 2>/dev/null; then
      echo "autopilot already running, pid $AP_PID"
    else
      rm -f .local/autopilot.stop
      # Self-update is ON by default (checks every 15 minutes);
      # set BAL_AUTO_UPDATE=0 to disable.
      if [ "${BAL_AUTO_UPDATE:-1}" = "1" ]; then AU="--auto-update"; else AU=""; fi
      # Worker name: BAL_WORKER wins; otherwise the autopilot
      # itself defaults to this machine's hostname.
      WK=""
      if [ -n "${BAL_WORKER:-}" ]; then WK="--worker $BAL_WORKER"; fi
      nohup python3 mining/autopilot.py $AU $WK \
        >> .local/autopilot.out 2>&1 &
      echo "autopilot started, pid $!"
      sleep 3
      python3 mining/autopilot.py --status || true
    fi
    ;;
  stop)
    touch .local/autopilot.stop
    echo "stop requested; autopilot and miner will exit within seconds"
    ;;
  status)
    python3 mining/autopilot.py --status
    ;;
  log)
    tail -n "${2:-30}" .local/autopilot.log 2>/dev/null || \
      echo "no autopilot log yet"
    ;;
  install-service)
    install_unit bal-autopilot.service bal-autopilot.service
    echo "start it with: systemctl start bal-autopilot"
    ;;
  install-node-service)
    if [ ! -f .local/mainnet/bitcoin.conf ]; then
      echo ".local/mainnet/bitcoin.conf not found; create the" >&2
      echo "mainnet datadir first (see docs/AUTOPILOT.md)." >&2
      exit 1
    fi
    install_unit bal-bitcoind.service bal-bitcoind.service
    echo "start it with: systemctl start bal-bitcoind"
    ;;
  *)
    echo "usage: $0 start|stop|status|log [lines]|install-service|install-node-service" >&2
    exit 2
    ;;
esac
