# Task 004: Audit and Hardening

Scope: the Tasks 003 to 006 surface (PoW engine, ComputeEngine and
CUDA bridge, mining engine, autonomous agent, mining statistics in
the intelligence store). Adversarial tests: tests/test_adversarial.py
and tests/test_gpu_compute.py, all passing.

## Real defects found during the port and fixed at the root

1. Regtest subsidy interval (consensus-critical). The mining
   engine's coinbase check used the mainnet halving interval
   (210000) on regtest, where the interval is 150. At height 150
   the engine rejected a valid template (coinbasevalue 2500002820
   against a computed 5000002820). Found live, not by inspection.
   Fix: coinbase_subsidy takes the halving interval as a chain
   parameter, the engine selects it from the node's chain, and the
   Task 002 block analyzer got the same correction.
2. CUDA constant table visibility. The shared SHA-256 header kept
   its round constants in a host static array, which nvcc device
   code cannot read (build error on first compile). Fix: a
   __device__ copy of the table with a single accessor used by both
   host and device code, keeping one source of truth for the values.
3. Dead placeholder code in the witness stripper (first draft)
   removed before it ever shipped in a result.

## Fail-closed checks now enforced and tested

- Template transactions are re-parsed; a txid that does not match
  the recomputed hash of the raw data rejects the whole template.
  Missing template fields raise instead of being guessed.
- The coinbase value must equal subsidy plus selected fees exactly.
- The computed witness commitment must agree with Core's
  default_witness_commitment when Core provides one.
- check_pow rejects negative, overflow, zero and above-limit
  targets, and short headers, each with its own reason code.
- The store is parameterized everywhere; a hostile string shaped
  like SQL is stored as data and the schema survives.
- ComputeEngine refuses zero, oversize and nonce-boundary-crossing
  batches before allocating anything, and independently re-verifies
  every candidate digest on the CPU.
- The autonomous agent refuses mainnet unless the caller explicitly
  opts in; errors in a cycle are recorded as events, never swallowed.

## Residual notes

- The live test suites share one chain and one mempool, so a
  leftover transaction from another suite can leak into a block a
  later suite analyzes (observed: a two-spend block where a test
  expected exactly one). Suites now drain the mempool to a known
  state before their strict assertions, and the adversarial suite
  polls getblocktemplate briefly for its spend. Two consecutive
  full-suite runs (make test-all, 7 suites) pass with this hygiene.
- The CUDA runtime result on this machine is error 35 (no driver,
  no device). That is an environment fact, not a code defect; the
  CPU backend is the authority here and the fallback reason is
  recorded on every run.
