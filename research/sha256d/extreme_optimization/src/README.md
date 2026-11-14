# src/

Experimental source code for X-series experiments in
../HYPOTHESIS_REGISTRY.md. Research code only: nothing here
is linked by production. Each experiment gets its own
subdirectory named after its registry id (for example
x031_avx512_multibuffer/), containing the source, its build
script, and a short README stating the hypothesis tested.

The existing H-02 and H-01 kernels remain where they were
built, in ../experiments/h02_shani/, and are cited from this
tree rather than copied.

Contents added by the EXP-004 to EXP-009 batch
(2026-11-14; flat layout for this batch, build with
build.sh; compiled libraries are build outputs and are
not committed):

- shani_core.h: copy of the H-02 core header the batch's
  kernels build against.
- h01_geo.c (EXP-005): H-01 geometry extension, streams
  1, 2, 3, 4, 6, blocked and strided assignment;
  libbal_geo.so.
- h01_hsf.c (EXP-006): schedule-first hand-scheduled
  variant of the geometry kernel; libbal_hsf.so.
- avx512_mb.c (EXP-007): AVX-512 16-way multi-buffer
  SHA-256d; libbal_v512.so.
- freq_gate.c (X-041): sustained AVX-512 frequency
  behaviour probe (standalone program).
- h01_phase.c (EXP-008): cross-nonce phase pipelining;
  libbal_phase.so.
