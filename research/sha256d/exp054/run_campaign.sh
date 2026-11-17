#!/bin/bash
# EXP-054 Gate 4 campaign chain: the 13 predeclared
# sessions, one at a time, in the fixed chain order of
# PREDECLARATION.md (control, g2, g4, g8, g1, g2, g4,
# g8, control, g1, g2, g4, g8), 30,000 pairs each,
# 390,000 pairs total. Sessions are append-only; a
# session interrupted by a VM replacement leaves no
# file and is rerun, never resumed.
set -u
cd /home/hatch/workspace/bitcoin-autonomous-lab/research/sha256d/exp054
LOG=RAW_RESULTS/campaign.log
echo "CAMPAIGN_START $(date -u +%Y-%m-%dT%H:%M:%SZ)" >> "$LOG"
for cmp in control_dual_self search_g2_vs_dual search_g4_vs_dual \
           search_g8_vs_dual search_g1_vs_dual search_g2_vs_dual \
           search_g4_vs_dual search_g8_vs_dual control_dual_self \
           search_g1_vs_dual search_g2_vs_dual search_g4_vs_dual \
           search_g8_vs_dual; do
  echo "SESSION_START $cmp $(date -u +%Y-%m-%dT%H:%M:%SZ)" >> "$LOG"
  python3 exp054_paired_bench.py --comparison "$cmp" \
      --pairs 30000 >> "$LOG" 2>&1
  echo "SESSION_END $cmp rc=$? $(date -u +%Y-%m-%dT%H:%M:%SZ)" >> "$LOG"
done
echo "CAMPAIGN_ALL_SESSIONS_DONE $(date -u +%Y-%m-%dT%H:%M:%SZ)" >> "$LOG"
