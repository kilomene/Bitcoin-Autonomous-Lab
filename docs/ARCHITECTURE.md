# Architecture

## Decisions for Task 001

1. **Bitcoin Core is the only source of chain truth.** The Lab does not
   parse blk files or trust third party APIs for chain data. Every
   read goes through Bitcoin Core JSON-RPC (node/rpc_client.py).
2. **Regtest first for experiments; mainnet live since 2026-11-13.**
   All Task 001 and Task 002 experiments ran against a local Regtest
   node. Mainnet pool mining was ordered by the owner on 2026-11-13
   and runs live (mining/mainnet_live.py, supervised by
   mining/autopilot.py) against public-pool.io in solo payout mode;
   the switch to the lab's own solo server is staged and armed for
   when the lab's own mainnet node finishes syncing. (The original
   Task 001 text said mainnet was paused by owner instruction; that
   phase ended on 2026-11-13.)
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
- mining/: pow.py and pow_engine.py (double SHA-256, nbits target
  math, merkle roots, subsidy schedule), engine.py (getblocktemplate
  mining engine with the EXP-025 template cache), solo_server.py and
  solo_mainnet.py (the lab's own Stratum solo server and its mainnet
  runner), stratum_client.py (pool Stratum client), mainnet_live.py
  (live mainnet pool runner), autopilot.py (supervisor),
  candidate_verify.py (exact candidate verification, EXP-036),
  mining_statistics.py and probability.py (EXP-037),
  work_checkpoint.py (EXP-038), wallet_gen.py (lab wallet
  generation); cpu/ holds the kernels: bal_avx512_dual.c (the
  production v512dual backend), bal_avx512_mb.c (v512),
  bal_avx512_flags.c (flags batch), bal_batch.c (C batch backend),
  bal_miner.c and bal_sha_intrin.c (the earlier standalone C miner
  and the SHA-NI intrinsics unit).
- gpu/: engine.py is the production ComputeEngine despite the
  historical directory name: it hosts the dispatch chain for every
  backend (CUDA when a real device passes the self-test, then
  v512dual, v512, the C batch backend, then Python hashlib). The
  CUDA package under gpu/cuda/ is real code, but this VM has no GPU
  device, so no GPU backend is ever selected here.
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
build). He resolved it on 2026-11-13: the repository is public
(github.com/kilomene/Bitcoin-Autonomous-Lab) and stays public. The
code is written to open-source standards either way (LICENSE,
CONTRIBUTING, no secrets).
