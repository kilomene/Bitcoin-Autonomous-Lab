# NOVA SHA-X: Extreme Optimization Programme

This directory holds the Grand Research Mandate workstream
tree, opened 2026-11-14. It extends, and does not replace,
the existing NOVA SHA-X research record in the parent
directory (research/sha256d/). All prior findings, experiment
records (EXP-000 to EXP-003), rejected hypotheses, and the
ranked H-01 to H-24 registry remain in force and are cited
from here, never rewritten.

## Layout

- MASTER_RESEARCH_PLAN.md: programme structure, workstreams
  A to G, governance, phasing.
- MATHEMATICAL_DISCOVERY.md: the complete mathematical map
  of SHA-256d and the transformation space, with each item
  marked established, hypothesis, or speculation.
- CPU_EXECUTION_RESEARCH.md: execution analysis grounded in
  this lab's measurements.
- MEMORY_AND_CACHE_RESEARCH.md: what mining actually moves,
  and the evidence that memory is not the binding constraint.
- REVERSE_ENGINEERING.md: how established implementations
  are structured, why, and which of their assumptions this
  lab's measurements support or contradict.
- ALTERNATIVE_IMPLEMENTATIONS.md: candidate implementation
  families ranked for this hardware.
- HYPOTHESIS_REGISTRY.md: the X-series registry, 100 plus
  distinct hypotheses (X-001 upward), separate from the
  H-series registry in ../experiment_registry.md.
- EXPERIMENT_REGISTRY.md: the permanent experiment record
  format (mandate section 10) with EXP-000 to EXP-003 and
  the integration decision run backfilled as imported
  entries.
- PERFORMANCE_ROADMAP.md: measured rates, the per-core
  ceiling estimate with its arithmetic shown, the honest
  quantitative assessment of the 500 GH/s and 140 TH/s
  targets, and the ranked research phases.
- BOTTLENECK_ANALYSIS.md: the production execution path end
  to end, where time goes, and the wasted work found in the
  code, file-cited.
- FINAL_RESEARCH_REPORT.md: the first assignment's report:
  state of knowledge and the five recommended experiments.

## Subdirectories

- src/: experimental source code for X-series experiments.
- tests/: correctness tests for those experiments.
- benchmarks/: raw benchmark records (JSON) for those
  experiments.
- proofs/: formal proof scripts and solver outputs.
- assembly/: generated assembly listings and instruction
  accounting for candidate kernels.

## Standing rules (inherited, unchanged)

- Exact SHA-256d only. No probabilistic shortcut, no
  reduced-round substitution, no coverage gap.
- Every performance figure cites its experiment record.
  Estimates are labelled estimates, with assumptions shown.
- Production code changes only under the integration rule:
  correctness proven, median improvement beyond spread at
  the tuned configuration, full suite green, fresh regtest
  block through the changed backend.
- Failed experiments are kept with the same care as wins.
