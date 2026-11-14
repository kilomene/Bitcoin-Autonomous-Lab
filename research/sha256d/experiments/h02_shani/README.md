# EXP-002 / EXP-003: Direct SHA-NI kernels (H-02, H-01, H-03)

Stage 5 authorization, executed 2026-11-14. Research tree
only: production is byte-identical (integration rule not
met, see the registry's EXP-003 decision entry).

## Files

- shani_core.h: shared SHA-NI core. Org-form state, MSG1/
  MSG2 schedule (whitepaper GENA/GENB), template with
  midstate + round-1 snapshot + round-2 snapshot, block-2
  in three prefix modes, outer hash via the same machinery.
- h02_shani.c: H-02 library source (libbal_h02.so). Counted
  ABI mirroring production: bal_h_batch2, bal_h_search2,
  plus bal_h_batch2_full / bal_h_batch2_p2 prefix variants
  and bal_h_compress (raw one-block compression, FIPS gate).
  Built with -DBAL_H_SCALAR_SCHED it becomes the scalar
  twin (libbal_h02_scalar.so), the equivalence reference.
- h01_multistream.c: H-01 library source (libbal_h01.so).
  Streams 1/2/4 interleaved inside one worker thread,
  blocked chunks, wave dispatch, counted ABI bal_m_batch2 /
  bal_m_search2 with wave-semantics accounting.
- build.sh: gcc -O3 -march=native -msha builds all three
  libraries. Built .so files are local artifacts and are
  not committed.
- test_h02.py / test_h01.py: correctness gates (all pass;
  120,000 + 324,000 randomized differentials, genesis,
  boundaries, templates, targets, exact accounting).
- bench_h02.py / bench_h01.py / bench_decision.py:
  EXP-000-protocol benchmarks; the decision driver runs
  all contenders round-robin interleaved in one session.
- asm_report.py: objdump instruction accounting.
- exp002_benchmarks.json, exp003_benchmarks.json,
  exp_decision_benchmarks.json: raw benchmark records.

## Headline results

- MSG schedule vs scalar schedule at equal rounds: about
  2.6x (2T medians 1,966,395 vs 751,524 H/s, same session).
- Interleaving: per-worker streams=2 is 2.36x streams=1
  in-session; streams=4 highest medians, heavy spills
  (365 xmm stack ops) that cost less than the latency hid.
- Decision run at 2 threads (interleaved medians):
  production 1,183,205; H-02 2,068,798; H-01 s2 1,932,862;
  H-01 s4 3,084,485 H/s. Ranges still overlap production's
  best sample, so the strict integration rule is NOT met
  and production is unchanged. Full record:
  ../../experiment_registry.md (EXP-002, EXP-003).
