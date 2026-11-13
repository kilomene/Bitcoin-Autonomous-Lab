# Architecture

## Decisions for Task 001

1. **Bitcoin Core is the only source of chain truth.** The Lab does not
   parse blk files or trust third party APIs for chain data. Every
   read goes through Bitcoin Core JSON-RPC (node/rpc_client.py).
2. **Regtest first, mainnet paused.** All Task 001 and Task 002
   experiments run against a local Regtest node. The earlier Stratum
   CPU mining code is preserved under mining/ but paused by owner
   instruction for this phase.
3. **Python standard library only, for now.** The RPC client uses
   urllib; storage in later tasks uses sqlite3 from the standard
   library. No dependency is added without a reason recorded here.
   The CPU miner engine remains C with OpenSSL for SHA-NI speed.
4. **Secrets are generated locally, never stored in the repo.** The
   node manager creates a random RPC password on first setup and keeps
   it in .local/regtest/ (gitignored, 0600). Code reads credentials
   from the environment or that local config, never from source.
5. **Binaries live outside the repo.** Bitcoin Core is downloaded to
   ~/workspace/bitcoin-core-dist by scripts/setup-bitcoin-core.sh and
   checksum verified against the official SHA256SUMS. The repo holds
   code and evidence, not 48 MB tarballs.
6. **Every claim needs an evidence file.** RPC milestone outputs are
   written to evidence/regtest/ exactly as returned by the node
   (minus credentials, which RPC responses never contain anyway).

## Module map

- node/: rpc_client.py (typed JSON-RPC wrapper, retries, explicit
  errors), node_manager.py (setup, start, stop, status of the
  Regtest bitcoind; config generation).
- blockchain/: monitor.py (height, block lookups, new-block watcher)
  plus the Task 002 Intelligence Engine: store.py (SQLite),
  transactions.py (TxInspector), analysis.py (BlockAnalyzer with
  independent merkle and PoW verification), service.py
  (MonitorService with reorg handling and failure resilience).
- mining/: pow.py (double SHA-256, nbits target math, merkle roots,
  subsidy schedule), cpu/bal_miner.c (SHA-NI CPU engine),
  stratum_client.py (paused mainnet experiment, preserved),
  wallet_gen.py (paused mainnet experiment support, preserved).
- gpu/: research gate. No implementation until Core integration is
  proven, per owner restriction. Current VM has no GPU.
- agent/: interface.py, structured JSON answers from live RPC data,
  including Regtest block generation.
- dashboard/: status.py, a JSON snapshot CLI that a future web
  dashboard will poll.
- tests/: correctness proofs against known mainnet data (genesis)
  plus live Regtest integration tests.
- scripts/: setup and operational entry points.
- evidence/: session logs and RPC milestone evidence.

## Data flow, Regtest milestone

agent/interface or tests -> node.rpc_client (HTTP JSON-RPC with
generated credentials) -> bitcoind (Regtest, datadir .local/regtest)
-> blockchain data returned as JSON -> evidence files.

## Repository visibility

The owner described this project in two ways across instructions:
open-source as the eventual goal (Task 001 brief), and private until
the evidence is reviewed (his direct order when commissioning the
build). The repo stays private until the owner resolves that in one
message; the code is written to open-source standards either way
(LICENSE, CONTRIBUTING, no secrets).
