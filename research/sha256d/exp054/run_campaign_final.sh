#!/bin/bash
# EXP-054 campaign final continuation. A VM
# replacement at about 05:29Z killed the continuation
# chain during chain position 12 (the third
# search_g4_vs_dual session, 6,000 pairs in, no file
# written). Positions 1 to 11 are complete on disk:
# control 2, g1 2, g2 3, g4 2, g8 2, all recorded on
# the AMD EPYC 9D25 host. The replacement host is an
# AMD EPYC 9D64 (AVX-512F/BW present, verified). This
# script runs exactly the remaining predeclared
# positions 12 and 13 (g4, then g8), one at a time,
# from zero, never resumed, per PREDECLARATION.md.
# The two sessions' manifests record the new host;
# the report discloses the host split (11 sessions on
# EPYC 9D25, 2 on EPYC 9D64). Every session is
# internally paired on one host, and the EXP-017
# statistic's per-session intercepts absorb level
# shifts between sessions.
set -u
cd /home/hatch/workspace/bitcoin-autonomous-lab/research/sha256d/exp054
LOG=RAW_RESULTS/campaign.log
echo "CAMPAIGN_RESUMED $(date -u +%Y-%m-%dT%H:%M:%SZ) after VM replacement; positions 12-13 on new host" >> "$LOG"
for cmp in search_g4_vs_dual search_g8_vs_dual; do
  echo "SESSION_START $cmp $(date -u +%Y-%m-%dT%H:%M:%SZ)" >> "$LOG"
  python3 exp054_paired_bench.py --comparison "$cmp" \
      --pairs 30000 >> "$LOG" 2>&1
  echo "SESSION_END $cmp rc=$? $(date -u +%Y-%m-%dT%H:%M:%SZ)" >> "$LOG"
done
echo "CAMPAIGN_ALL_SESSIONS_DONE $(date -u +%Y-%m-%dT%H:%M:%SZ)" >> "$LOG"
