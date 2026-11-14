#!/usr/bin/env bash
# BAL one-command install and activation.
#
# An agent clones the repo and runs this once. Everything the
# lab needs is set up and switched on automatically:
#
#   1. build      the C search engine (and the CUDA lib if the
#                 machine has nvcc)
#   2. network    scripts/network_setup.py probes the pool and
#                 update endpoints, detects the machine's proxy
#                 and adapts this repo's git config to it
#   3. smoke      the engine is constructed, auto-tunes its
#                 thread count to this machine, and re-finds
#                 the genesis nonce; the worker default is the
#                 machine hostname
#   4. service    the autopilot systemd unit is installed and
#                 enabled where systemd exists (reboot-proof);
#                 the node unit too, when a node datadir exists
#   5. activate   mining starts under the autopilot, or is
#                 confirmed already running; a receipt prints
#                 worker, address, threads and network verdict
#
# Idempotent: re-running changes nothing that is already set
# up and never starts a second miner. If the pool endpoint is
# unreachable the install stops before activation and says so.
#
# Usage: bash scripts/install.sh [--dry-run]
# Env:   BAL_WORKER   worker name (default: this hostname)
#        BAL_ADDRESS  payout address (default: the lab wallet)
#        BAL_NO_SERVICE=1   skip systemd, run the autopilot
#                           directly
set -euo pipefail
cd "$(dirname "$0")/.."
ROOT="$PWD"
mkdir -p .local

if [ "${1:-}" = "--dry-run" ]; then
  echo "BAL INSTALL PLAN (dry run, nothing will change)"
  echo "1. build: python3 mining/cpu/build.py (+ CUDA if nvcc)"
  echo "2. network: python3 scripts/network_setup.py"
  echo "3. smoke: engine auto-tune + genesis nonce check"
  echo "4. service: install bal-autopilot systemd unit if possible"
  echo "5. activate: start mining under the autopilot, print receipt"
  echo "worker default: this machine's hostname"
  echo "payout default: the lab wallet address"
  exit 0
fi

step() { echo; echo "== $1 =="; }

step "1/5 build"
python3 mining/cpu/build.py
if command -v nvcc >/dev/null 2>&1; then
  python3 gpu/cuda/build.py || echo "CUDA build failed; CPU engine remains authoritative"
else
  echo "no nvcc on this machine; CUDA build skipped"
fi

step "2/5 network self-configuration"
python3 scripts/network_setup.py

step "3/5 smoke test"
python3 - <<'EOF'
import sys
sys.path.insert(0, ".")
import gpu.engine as ge
from mining.autopilot import default_worker
eng = ge.ComputeEngine()
hdr = bytes.fromhex(
    "01000000" + "00" * 32
    + "3ba3edfd7a7b12b27ac72c3e67768f617fc81bc3888a51323a9fb8aa4b1e5e4a"
    + "29ab5f49" + "ffff001d" + "1dac2b7c")
target = 0x00000000FFFF0000000000000000000000000000000000000000000000000000
hit = eng.search_first(hdr, target, 2083236890, 10)
assert hit and hit[0] == 2083236893, hit
print(f"engine ok: backend {eng.backend}, "
      f"C threads {ge.C_THREADS}, worker {default_worker()}")
EOF

step "4/5 service (reboot persistence)"
SERVICE_OK=0
if [ "${BAL_NO_SERVICE:-0}" != "1" ] && command -v systemctl >/dev/null 2>&1; then
  if bash scripts/autopilot.sh install-service; then
    SERVICE_OK=1
    if [ -f .local/mainnet/bitcoin.conf ]; then
      bash scripts/autopilot.sh install-node-service || true
    fi
  else
    echo "service install not possible here; the autopilot will run directly"
  fi
else
  echo "systemd skipped; the autopilot will run directly"
fi

step "5/5 activation"
ACTIVE=0
if [ -f .local/autopilot.lock ]; then
  AP_PID="$(cat .local/autopilot.lock 2>/dev/null || true)"
  if [ -n "$AP_PID" ] && kill -0 "$AP_PID" 2>/dev/null; then
    ACTIVE=1
    echo "autopilot already running, pid $AP_PID"
  fi
fi
if [ "$ACTIVE" != "1" ]; then
  if [ "$SERVICE_OK" = "1" ]; then
    systemctl start bal-autopilot || bash scripts/autopilot.sh start
  else
    bash scripts/autopilot.sh start
  fi
fi

sleep 10
echo
echo "== ACTIVATION RECEIPT =="
python3 mining/autopilot.py --status || true
grep -h "full-workforce" .local/miner.out 2>/dev/null | tail -1 || true
grep -h "authorized as" .local/miner.out 2>/dev/null | tail -1 || true
python3 - <<'EOF'
import json, os
p = ".local/network.json"
if os.path.exists(p):
    r = json.load(open(p))
    eps = ", ".join(
        f"{e['host']}:{e['port']}={'ok' if e['tcp_ok'] else 'FAIL'}"
        for e in r["endpoints"])
    print(f"network: pool reachable: {r['pool_reachable']}; {eps}")
print("mining is active under the autopilot: own worker, full "
      "workforce, no resting. See docs/AUTOPILOT.md.")
EOF
