# Tasks 005/006: Autonomous Mining Engine and Agent

Status: implemented, tested live. Code: mining/engine.py,
agent/autonomous.py, gpu/engine.py. Tests:
tests/test_mining_engine.py, tests/test_adversarial.py. Evidence:
evidence/regtest/task003-006-evidence.json.

Dating note: the design description below is the Task 005/006
engine as built on 2026-11-13. The current backend and production
state is recorded in the 2026-11-15 update at the end of this
document.

## How a cycle works

1. getblocktemplate (segwit rules) from the lab node.
2. Every template transaction is re-parsed: txid and wtxid are
   recomputed from the raw data (witness stripping implemented in
   mining/engine.py) and must match Core's values.
3. The coinbase pays exactly subsidy plus fees; the subsidy uses
   the chain's halving interval (150 on regtest, 210000 elsewhere)
   and is cross-checked against the template's coinbasevalue.
4. With witness transactions present, the BIP141 witness commitment
   is computed and checked against Core's
   default_witness_commitment.
5. Nonce search runs in batches through the ComputeEngine: CUDA
   when a real device passes the self-test, otherwise CPU with the
   reason recorded. Every candidate is re-verified on the CPU
   before submission. Exhaustion escalates to the next extranonce
   (coinbase rebuilt, merkle root recomputed).
6. submitblock; a block counts as mined only when submitblock
   returns no error AND the block is the node's best block.

generatetoaddress is never used by this path.

## The agent

AutonomousMiner runs diagnostics first (a measured benchmark picks
nothing; it records the backend and its fallback reason), then
cycles with batch size adaptation from measured batch times. Every
cycle, decision and error lands in the intelligence store
(mining_cycles table and chain_events). The agent refuses mainnet
without an explicit allow_mainnet=True.

## Live evidence (milestone run, 2026-11-13)

Three cycles, tip 162 to 165, all accepted; the middle cycle
included a real segwit spend (2 transactions, 2820 sats fees).
Earlier the same day the engine mined across the regtest halving
boundary at height 150, where the subsidy drops to 25 BTC.

## Performance after the deepening pass

The ComputeEngine gained a midstate-optimized C backend
(mining/cpu/bal_batch.c, OpenSSL SHA-NI): the first compression of
each header is computed once, so a nonce costs two compressions.
Measured on this VM: about 2.0M H/s through the full engine path
(backend "c") against about 0.6M H/s for Python hashlib batches;
the raw library call peaks above 8M H/s. Backend order is CUDA,
then C, then Python; every candidate is still CPU verified.

## Update, 2026-11-15: current engine state

The ComputeEngine dispatch order is now CUDA (no device on this
VM, never selected), v512dual, v512, the C batch backend, then
Python hashlib. v512dual (mining/cpu/bal_avx512_dual.c, the
DualMask kernel from EXP-026) is the production search backend;
v512 (mining/cpu/bal_avx512_mb.c) is preserved behind it. The
EXP-022 flags batch (bal_v_batchf2 in mining/cpu/bal_avx512_flags.c)
serves batch consumers only and is not in the live search path.
MiningEngine carries the EXP-025 template cache (layered dsha256
identity, bounded at 128 entries, uncached construction preserved
as fallback) and opt-in EXP-038 work checkpoints
(mining/work_checkpoint.py). Candidates on both the pool and solo
paths are verified exactly by mining/candidate_verify.py
(EXP-036: hashlib and pure-Python agreement plus the integer
consensus target test) before submission, and a submission counts
as accepted only on chain confirmation.
