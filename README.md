# Bitcoin Autonomous Lab

An autonomous Bitcoin infrastructure and mining research lab: a
Bitcoin Core full node under programmatic control, a blockchain
monitoring and analysis engine, Proof-of-Work research, and an
AI-agent interface over all of it. Built task by task, tested on a
real (Regtest) node, with evidence files for every claim.

Repository status: private while the owner reviews the evidence.
The code follows open-source standards (MIT license, CONTRIBUTING)
so the visibility decision is the owner's alone.

## Current status

- Task 001 (foundation, Regtest integration): complete and tested.
  See docs/TASK-001.md and evidence/regtest/task001-evidence.json.
- Task 002 (Blockchain Intelligence Engine): complete and tested.
  SQLite block and transaction storage, a monitoring service with
  reorganization handling, transaction intelligence with exact fee
  accounting, and block analysis with independent merkle and PoW
  verification. See docs/TASK-002.md and
  evidence/regtest/task002-evidence.json.
- Mainnet mining experiments from the initial build are paused by
  owner instruction for this phase. Their session logs remain in
  evidence/ as historical record, with limits stated in
  docs/HONEST-LIMITS.md.
- GPU work is gated until the Core integration milestones pass.
  The current VM has no GPU.

## Quick start (Regtest)

```
scripts/setup-bitcoin-core.sh 28.1     # download + checksum verify
python3 -m node.node_manager start     # configures local credentials
python3 -m agent.interface status      # live chain info as JSON
python3 -m agent.interface generate 5  # mine 5 Regtest blocks
make test                              # correctness proofs
python3 tests/test_regtest_integration.py --evidence
```

## Structure

- node/: Bitcoin Core integration, JSON-RPC client, node lifecycle.
- blockchain/: block and transaction monitoring.
- mining/: Proof-of-Work primitives, CPU engine, paused Stratum work.
- gpu/: GPU acceleration research (gated).
- agent/: autonomous agent interface (structured JSON answers).
- dashboard/: monitoring snapshots and analytics.
- tests/: known-data correctness proofs and Regtest integration tests.
- docs/: architecture, task records, evidence protocol, honest limits.
- scripts/: setup and operational scripts.
- evidence/: live session logs and RPC milestone evidence.

## Design rules

- Bitcoin Core RPC is the only source of chain truth.
- No hardcoded secrets, ever. Node credentials are generated locally
  into a gitignored config with 0600 permissions.
- No simulated functionality presented as real. If it is not backed
  by a test or an evidence file, the docs say so.
- Full honesty about scale: read docs/HONEST-LIMITS.md before drawing
  conclusions from any mining numbers in this repository.
