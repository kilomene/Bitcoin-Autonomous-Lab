#!/bin/bash
# EXP-054 campaign continuation. The original chain
# (run_campaign.sh) was killed by an exec-session
# reaping event at about 03:29Z, 10,000 pairs into
# chain position 6 (the second search_g2_vs_dual
# session). That session left no file, per the
# driver's write-at-end design. Positions 1 to 5 are
# complete on disk (control, g2, g4, g8, g1). This
# script runs exactly the remaining predeclared
# positions 6 to 13, in the predeclaration's chain
# order, one at a time: g2, g4, g8, control, g1, g2,
# g4, g8. No completed session is rerun; the
# interrupted session is rerun from zero, never
# resumed, per PREDECLARATION.md.
set -u
cd /home/hatch/workspace/bitcoin-autonomous-lab/research/sha256d/exp054
LOG=RAW_RESULTS/campaign.log
echo "CAMPAIGN_RESUMED $(date -u +%Y-%m-%dT%H:%M:%SZ) after interruption; positions 6-13" >> "$LOG"
for cmp in search_g2_vs_dual search_g4_vs_dual search_g8_vs_dual \
           control_dual_self search_g1_vs_dual search_g2_vs_dual \
           search_g4_vs_dual search_g8_vs_dual; do
  echo "SESSION_START $cmp $(date -u +%Y-%m-%dT%H:%M:%SZ)" >> "$LOG"
  python3 exp054_paired_bench.py --comparison "$cmp" \
      --pairs 30000 >> "$LOG" 2>&1
  echo "SESSION_END $cmp rc=$? $(date -u +%Y-%m-%dT%H:%M:%SZ)" >> "$LOG"
done
echo "CAMPAIGN_ALL_SESSIONS_DONE $(date -u +%Y-%m-%dT%H:%M:%SZ)" >> "$LOG"
