#!/usr/bin/env bash
# Run one live mining session and log evidence.
# Usage: scripts/run-live.sh <lab-btc-address> [duration-seconds]
set -euo pipefail
cd "$(dirname "$0")/.."
ADDR="${1:?lab btc address required}"
DUR="${2:-300}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
make bal-miner >/dev/null
python3 src/stratum_miner.py \
  --address "$ADDR" \
  --duration "$DUR" \
  --threads 4 \
  --miner ./bal-miner \
  --evidence "evidence/session-$STAMP.jsonl"
echo "evidence: evidence/session-$STAMP.jsonl"
