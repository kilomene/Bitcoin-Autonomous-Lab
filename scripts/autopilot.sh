#!/usr/bin/env bash
# BAL Autopilot control: start | stop | status | log
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p .local

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
      nohup python3 mining/autopilot.py $AU \
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
  *)
    echo "usage: $0 start|stop|status|log [lines]" >&2
    exit 2
    ;;
esac
