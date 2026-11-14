# Research Roadmap

Sequence follows the charter's execution order. Each stage
names its entry condition and its exit evidence; a stage is
done when its evidence exists in this tree, not when its
documents do.

## Stage 1: Repository and machine intelligence assessment
Status: DONE in this pass. Evidence: cpu_microarchitecture.md
(with reproducible probe), the implementation map and
bottleneck list in README.md, assembly_analysis.md.

## Stage 2: Mathematical reconstruction
Status: DONE in this pass. Evidence:
mathematical_foundations.md, header_and_midstate_analysis.md
(canonical indexing, nonce entry at block-2 round 3, prefix
ceiling of 67 of 192 rounds, invariance classes).

## Stage 3: Baseline measurement
Status: DONE in this pass. Evidence: EXP-000
(baseline_performance.md, experiments/exp000_baseline.json),
harness frozen as the comparison standard.

## Stage 4: Mathematical alternatives
Status: STARTED. Boolean equivalences proven
(boolean_equivalence.md) and registered as H-06 for
implementation contexts where they can matter. Schedule
representations analyzed (message_schedule_research.md).
Next: sigma-function decompositions evaluated only if a
hand kernel (Stage 5) gives them somewhere to live.

## Stage 5: CPU microarchitecture (NEXT)
Entry: Stages 1 to 3, done. Work: H-02 (direct SHA-NI
kernel with real schedule instructions), then H-01
(multi-stream interleaving on top of it), with H-03, H-06,
H-07 folded in as variants of the same scaffold, and H-04
(candidates-only batch output) as a parallel small win.
Exit evidence: a research kernel that is differentially
exact and either beats production beyond spread (proceed to
Stage 8) or is filed as a measured rejection.

## Stage 6: Automated research
Status: STARTED. The loop, harness, prover pattern, and
compiler protocol exist (automated_discovery.md). Next: the
candidate-kernel scaffold that runs gates, assembly summary,
and benchmarks in one command, plus the stream-count sweep
driver.

## Stage 7: Mining pipeline intelligence
Status: AUDITED in this pass (mining_pipeline_optimization.md,
findings F1 to F3, no structural waste at current rates).
Work items H-05, H-13, H-14, H-15 are queued behind Stage 5
because a faster kernel re-prices every tradeoff. The solo
server cutover (own node as work source) is the stage's
forcing event when the node finishes syncing.

## Stage 8: Integration
Entry condition: a Stage 5 candidate that clears the
integration rule. Nothing from this pass qualifies: EXP-001
was a rejection, so production is byte-identical by design.
Exit evidence when it happens: full make test-all (only the
known test-rtl environment failure), a fresh regtest block
through the changed backend, and a README status log entry.

## Stage 9: Real-world validation
Continuous: the live mainnet pool miner is the standing
validation that templates, judgement, confirmation, and
submission work against the real network (accepted shares,
never reported as blocks). Regtest remains the block
acceptance standard for every integrated change.

## Stage 10: Extended architecture research
Parked by the charter's own ordering and by hardware:
H-20 to H-23 are BLOCKED entries in the registry. The GPU
design work from Tasks 002/003 is complete and host-proven;
it waits for a device, not for more documents. FPGA and ASIC
records live in results/FPGA_RESULTS.md and
results/ASIC_RESULTS.md.

## Immediate next actions, in order

1. Build the H-02 kernel scaffold (automated_discovery.md).
2. Run H-02, fold in H-03 and H-07 variants, benchmark.
3. Run H-01 stream counts on the winning H-02 form.
4. Land H-04 independently (small, low risk).
5. Re-run EXP-000 to confirm the baseline has not drifted.
