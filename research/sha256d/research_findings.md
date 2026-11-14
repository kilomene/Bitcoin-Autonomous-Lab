# Research Findings: First Pass (2026-11-14)

What this pass actually established, stated at the strength
the evidence supports.

## Established by measurement

1. The production CPU backend on this VM, at its tuned
   2 threads, sustains a median of about 1.63 MH/s under
   live contention (EXP-000), with 1-thread at 1.31 MH/s
   and an unstable 4-thread median of 2.51 MH/s whose 82.6%
   spread disqualifies it as a planning figure.
2. The SHA-intrinsics path runs at about 0.52x production,
   and the cause is structural and visible in its compiled
   form: zero sha256msg instructions, scalar schedule
   recomputed per nonce.
3. Compiler flags on the production source are exhausted as
   an avenue: five gcc variants, none better than production
   flags, generated wrapper code identical across native
   variants (EXP-001, a clean negative result).
4. Single-hash requests through Python cost about 31 us of
   boundary overhead against an amortized 0.76 us per hash
   in batch: batching discipline, already practiced by the
   miners, is worth more than any micro-optimization of a
   single call.
5. Memory bandwidth (about 4.0 GB/s single-stream under
   contention) is orders above mining's needs; compute and
   latency chains are the binding constraints.

## Established by proof or derivation

6. The precomputation ceiling is 67 of 192 rounds per
   template. Production already captures 64 of them. The
   remaining 3 (block-2 rounds 0..2) are worth about 2.4% of
   per-nonce work and are reachable only in a hand kernel,
   because OpenSSL's Transform API works on whole blocks.
7. The nonce first affects block-2 state at round 3, with
   the canonical byte map in
   header_and_midstate_analysis.md reconciled against the
   intrinsics code's round-1 snapshot (a SHA256RNDS2 pairing
   artifact, worth exactly one round).
8. Ch_alt, Maj_alt_A, and Maj_alt_B are exactly equivalent
   to the reference Boolean functions, proven three
   independent ways (exhaustive bit proof, 1M-sample
   differential, z3 UNSAT). Their benefit is unmeasured and
   confined to code that evaluates rounds outside
   SHA256RNDS2.

## Established by audit

9. The mining pipeline (template, construction, search,
   confirmation, submission, acceptance) has no structural
   waste at current rates; its costs are measured and
   bounded (mining_pipeline_optimization.md).
10. At the current network difficulty (134.8 trillion,
    live-decoded), expected time to a block at measured
    rates is billions of years and 24 h discovery
    probability is on the order of 10^-13
    (statistical_mining_analysis.md). The programme's value
    case is the linearity of probability in hash rate, not
    an expectation of discovery.

## Not established (and not claimed)

- No implementation in this pass is faster than production.
  Production code is unchanged.
- Nothing about GPU, FPGA, or ASIC performance; those gates
  remain exactly as Tasks 002/003 left them: UNVERIFIED on
  this hardware.
- No cycles-per-hash or IPC figures; perf counters are
  unavailable in this guest.

## The one-sentence summary

The easy wins are taken and the flag drawer is empty; the
remaining large lever on this machine is a purpose-built,
multi-stream SHA-NI kernel (H-01 on H-02), and the programme
now has the baseline, proofs, and registry to build it
honestly.
