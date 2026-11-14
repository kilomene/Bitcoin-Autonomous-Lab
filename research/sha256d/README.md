# NOVA SHA-X: SHA-256d Research Programme

This tree is the research record for accelerating Bitcoin's exact
SHA-256d computation in this lab. It follows one rule set: exact
consensus hashing only, every claim tied to a measurement or a
proof, failed experiments kept, and production code changed only
when an improvement is proven beyond measurement noise on this
machine.

Programme charter stages: (1) repository and machine assessment,
(2) mathematical reconstruction, (3) trusted baseline, (4)
mathematical alternatives, (5) CPU microarchitecture, (6)
automated discovery, (7) mining pipeline intelligence, (8)
integration of verified improvements only, (9) real-world
validation, (10) extended architectures. This pass completed
Stages 1 to 3, pulled the Boolean-equivalence part of Stage 4
forward, and ran the first experiment (EXP-001).

## Implementation map: every SHA-256d execution path in the repo

| Path | Source | Entry points | Midstate | Schedule | Threading | Counting | Role |
|---|---|---|---|---|---|---|---|
| Production C (OpenSSL) | mining/cpu/bal_batch.c | bal_c_batch2, bal_c_search2 (plus legacy wrappers) | Yes: block 1 compressed once per header via OpenSSL SHA256_Init/Transform state | Inside OpenSSL SHA256_Transform (SHA-NI dispatch on this CPU) | pthreads, per-search context (bal_search.h), spans partition the range | Counted: out_attempted is actual per-worker attempts summed | Production backend "c", selected by ComputeEngine after a live self-test |
| SHA-intrinsics experiment | mining/cpu/bal_sha_intrin.c | bal_i_batch2, bal_i_search2 | Partial: inner state snapshot after round 1 (rounds are computed in SHA256RNDS2 pairs, nonce enters round 3) | Scalar C, recomputed per nonce (schedule_impl); no SHA256MSG1/MSG2 anywhere | Same bal_search.h context design | Counted, same ABI as production | Experimental only, never auto-selected; measured at about half the production rate |
| Pure Python SHA-256 | mining/pow_engine.py (PureSHA256) | sha256_pure, double_sha256_pure | No | 64-word, from FIPS 180-4 | Single thread | Exact loop counts in callers | Reference and verification; the independent implementation the C paths are checked against |
| Python hashlib | gpu/engine.py (backend "cpu"), mining paths | hashlib.sha256 twice | No (hashlib computes per call; midstate not exposed) | Inside OpenSSL | Single thread per call | Counted at call sites (Task 003.9 definitions) | Fallback backend, always honestly reported as "cpu" |
| CUDA shared source | gpu/cuda/kernels/sha256.h, gpu/cuda/engine.cu | bal_cuda_batch, persistent context ABI | Yes, device-side, keyed to the exact header | Full and circular variants in shared source | CUDA threads, one nonce per thread | Candidate records plus Task 003.8/003.9 accounting fields | Reference only in this programme (no GPU on this VM; device execution UNVERIFIED) |
| Standalone miner | mining/cpu/bal_miner.c (bal-miner binary) | search and bench modes | No midstate (full header hash per nonce via OpenSSL) | Inside OpenSSL | pthreads with disjoint slices (Task 003.3) | Actual per-worker attempts | Diagnostics and independent cross-check; slowest native path by design |

Selection: gpu/engine.py ComputeEngine tries CUDA (only after the
production-path self-test passes, Task 003.6), then the C library,
then Python. mining/cpu/miner.py CpuMiner restricts itself to CPU
backends for regtest work. mining/engine.py MiningEngine drives
getblocktemplate mining through ComputeEngine with clamped batch
counts (Task 003.2) and counted searches (Task 001).

## Optimizations already implemented (verified in earlier tasks)

1. Block-1 midstate reuse in the production C path: 64 rounds paid
   once per template instead of once per nonce.
2. Early-exit counted search (bal_c_search2): workers stop at the
   first verified candidate; attempts are actual, not requested.
3. Thread auto-tuning at startup (tune_c_threads probes this
   machine and picked 2 threads here).
4. Per-search concurrency context with C11 atomics and a
   mutex-published winner (Task 001), shared by both C libraries.
5. Template judgement in the live miner: GBT longpoll, about 1 s
   span preemption, stale-template rejection, independent
   candidate confirmation before submission.
6. CUDA-side (device) midstate, candidate filtering, persistent
   context, and overflow recovery by sub-batch splitting
   (Tasks 002, 003, 003.8), host-proven, device-unverified.
7. Accounting separation (Task 003.9): requested, unique
   coverage, backend, device, researched, and verification
   hashes are distinct fields with scoped invariants.

## Bottlenecks, each with its evidence

B1. The production per-nonce cost is two OpenSSL SHA256_Transform
    calls plus per-call context handling in our wrapper.
    Evidence: hash_nonce in the compiled library is 408
    instructions with a 416-byte stack frame (objdump, EXP-001)
    for what is conceptually 125 rounds of work; the compression
    itself lives in libcrypto (128 sha256rnds2 sites there, 0 in
    our library). The wrapper overhead is ours to attack; the
    compression is OpenSSL's.
B2. The intrinsics path recomputes the full message schedule in
    scalar C for every nonce and contains zero sha256msg
    instructions (objdump count 0, vs 3 sha256rnds2 sites).
    Evidence: it measures about 0.52x the production rate at
    2 threads in EXP-000. This is the largest single known gap
    between the two native paths.
B3. Throughput scaling flattens and destabilizes past 2 threads.
    Evidence: EXP-000 medians 1.31M (1T), 1.63M (2T), 2.51M (4T)
    H/s with spreads of 27%, 13%, 83%: the VM cap (about 1.5
    effective CPUs on a shared host, load average above 10 during
    the baseline) makes added threads buy contention, not cores.
B4. Single-call latency through the Python/ctypes boundary is
    overhead-dominated: median 31.4 us for a count=1 batch call
    vs an amortized 0.76 us per hash at 1 thread (EXP-000). Any
    caller issuing small batches pays roughly 40x the hash cost
    in crossing and thread-setup overhead. Mining spans are
    sized near 1 s of work in the live miner for this reason.
B5. Memory bandwidth is not the constraint: a STREAM-style copy
    measures 2.739 GB/s single-stream under contention (probe
    record; corrected from an unsourced 4.0 GB/s, see
    cpu_microarchitecture.md) while
    a mining thread consumes a 32-byte digest per hash; the
    working set per worker is registers plus a few hundred stack
    bytes. Compute and latency chains bind, not DRAM.
B6. Candidate verification on CPU costs about 3.5 to 5.7 us per
    candidate (Tasks 003, 003.8 measurements). Irrelevant at
    mainnet targets, material at easy regtest targets where
    candidates are dense; accounted as verification_hashes.

## Tree layout

- mathematical_foundations.md, header_and_midstate_analysis.md:
  the Stage 2 derivation.
- boolean_equivalence.md + tools/boolean_proof.py: proven
  alternative Ch and Maj forms with three independent checks.
- cpu_microarchitecture.md + tools/probe_machine.py +
  tools/machine_probe_2026-11-14.json: the Stage 1 machine
  profile, reproducible.
- assembly_analysis.md: what the compiled code actually does.
- experiments/bench_harness.py: the one harness for baseline and
  all comparisons. experiments/compiler_sweep.py: EXP-001.
  experiments/exp000_baseline.json, exp001_compiler_sweep.json:
  raw results.
- experiment_registry.md: EXP-000, EXP-001, and the ranked
  hypothesis registry (H-01 to H-24) with statuses.
- research_roadmap.md, message_schedule_research.md,
  round_optimization.md, compiler_experiments.md,
  automated_discovery.md, mining_pipeline_optimization.md,
  statistical_mining_analysis.md, research_findings.md,
  rejected_hypotheses.md: the remaining programme documents.
