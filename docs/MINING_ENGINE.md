# Tasks 005/006: Autonomous Mining Engine and Agent

Status: implemented, tested live. Code: mining/engine.py,
agent/autonomous.py, gpu/engine.py. Tests:
tests/test_mining_engine.py, tests/test_adversarial.py. Evidence:
evidence/regtest/task003-006-evidence.json.

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
