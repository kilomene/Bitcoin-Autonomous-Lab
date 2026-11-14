# Automated Discovery: the Research Loop as a System

## The loop every candidate must travel

1. State the hypothesis and its mathematical or architectural
   rationale in the registry before building anything.
2. Generate the candidate in the research tree or as a
   separately built library; production sources are not the
   sketchpad.
3. Prove or test correctness: formal proof where the claim
   is algebraic (the boolean_proof.py pattern: exhaustive
   bit proof plus randomized differential plus an SMT check
   when available), differential testing against hashlib and
   the pure Python reference everywhere else, genesis vector
   always.
4. Compile under the compiler protocol
   (compiler_experiments.md) and inspect the per-nonce
   function's assembly.
5. Benchmark with experiments/bench_harness.py only, at
   least 3 repeats, median and spread recorded.
6. Decide by the registry rule: keep as candidate,
   inconclusive on this VM, or reject with the reason kept.
7. Integrate only under the integration rule (real median
   gain beyond spread, correctness proven, full suite green,
   fresh regtest block through the changed path).

## Tooling that exists today

- tools/probe_machine.py: live machine profile; candidates
  must cite the profile they were measured under.
- tools/boolean_proof.py: the equivalence prover pattern,
  reusable for any future bitwise identity (schedule sigma
  functions are the obvious next client: their alternative
  rotate/shift decompositions are also bitwise identities,
  provable by the same 1-bit method only where no shifts
  cross bit positions; shift-involving identities need the
  randomized plus SMT legs, which the script already has).
- experiments/bench_harness.py: the comparison harness with
  built-in correctness gates.
- experiments/compiler_sweep.py: the template for build
  variant experiments.
- z3: available at $0 in a workspace venv (installed for
  Deliverable 4); SMT equivalence checks for arithmetic
  rearrangements (mod 2^32 addition groupings) are the next
  use.

## Tooling planned, tied to registry items

- A candidate-kernel scaffold for H-02/H-01 that builds a
  research SHA-NI kernel, runs the correctness gates, dumps
  its assembly summary, and benchmarks it, in one command.
  This is the single highest-value automation for Stage 5.
- A sweep driver over stream counts (1, 2, 4) and schedule
  variants (full, circular) for that scaffold, emitting
  registry-ready rows.
- PGO and clang legs for the compiler protocol if a hand
  kernel lands (H-12).

## Anti-patterns this system exists to prevent

- Benchmarking a candidate against a stale or differently
  conditioned baseline.
- Reporting a best run instead of a median with spread.
- Letting a candidate's own author be its only verifier:
  the harness's hashlib gates are not optional.
- Losing a negative result. EXP-001's rejection is filed
  with the same care as a win would be.
