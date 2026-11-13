# Tasks 003 to 006: live run results (2026-11-13)

Command: python3 scripts/milestone_003_006.py
Machine record: evidence/regtest/task003-006-evidence.json

## CUDA

- nvcc 12.9.86 installed from NVIDIA's apt repo; engine.cu compiled
  to libbal_cuda.so; host build of the shared SHA-256 source matched
  hashlib on every vector (genesis hash, FIPS million-byte, 49,907
  regtest target hits in 100k nonces).
- Runtime device count: CUDA error 35 (no driver, no device on this
  VM). Backend selected: CPU, reason recorded. No GPU result claimed.

## PoW engine cross-verification

- 163 live regtest headers checked by the pure Python engine:
  hash and PoW agree with Core on all 163, zero mismatches.
- 6 real mainnet headers (fixtures) verified under the mainnet pow
  limit; tampered header rejected as high-hash.

## Autonomous mining

- 3 cycles in the milestone run, tip 162 to 165, all accepted by
  Bitcoin Core through getblocktemplate and submitblock.
- Cycle at height 164 included a real segwit spend: 2 transactions,
  2820 sats in fees, witness commitment path exercised.
- Same day, the engine also mined block 150, the regtest halving
  boundary (subsidy 25 BTC), which is where the audit found and
  fixed the subsidy interval defect (docs/AUDIT-004.md).
- Benchmark: about 335K to 345K H/s CPU batches on this VM.

## Test suites

make test-all: known-block proofs, regtest integration, intelligence
engine, PoW engine, GPU compute, mining engine, adversarial. All
passing at push time.
