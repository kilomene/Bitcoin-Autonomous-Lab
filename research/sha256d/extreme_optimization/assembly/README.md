# assembly/

Generated assembly listings and instruction accounting for
candidate kernels. The standing rules (from
../assembly_analysis.md) apply:

1. Count instructions and stack usage in the function that
   runs per nonce, not in the whole library.
2. A source transformation that leaves the generated code
   unchanged is not an optimization; check before
   benchmarking.
3. Spills in the per-nonce function are a reject signal for
   register-pressure reasons, recorded in the experiment
   entry.
4. perf counters are unavailable in this guest, so
   dependency chains are reasoned from the listing and
   confirmed or refuted by wall-clock harness results,
   never reported as measured IPC.

Existing listings were produced by
../experiments/h02_shani/asm_report.py (objdump) and are
summarized in ../assembly_analysis.md.
