#!/usr/bin/env bash
# PAUSED per Task 001 restrictions (no mainnet mining in this phase).
# This script ran the pre-Task-001 mainnet Stratum sessions whose logs
# live in evidence/. It is kept for the record and refuses to run so
# nobody restarts mainnet mining by accident during the Regtest phase.
set -euo pipefail
echo "run-live.sh is paused: Task 001 restricts this phase to Regtest." >&2
echo "See docs/TASK-001.md for the current milestone." >&2
exit 3
