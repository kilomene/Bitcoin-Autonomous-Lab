#!/usr/bin/env bash
# Regtest node control: scripts/regtest.sh start|stop|status
set -euo pipefail
cd "$(dirname "$0")/.."
python3 -m node.node_manager "${1:-status}"
