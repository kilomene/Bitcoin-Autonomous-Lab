# Research to Production Pipeline

Date: 2026-11-15. How research becomes tested production
functionality in NOVA SHA-X, as implemented by
agent/intelligence/loop.py (OptimisationLoop) and
agent/intelligence/experiments.py (ExperimentRunner), Master
Build Milestone 3 on the Milestone 1 foundation. The pipeline is
an enforced state machine over records, not a description of
good intentions: transitions happen in one order, two gates can
refuse, and every advance is permission-checked (L2 loop_advance)
and written to the audit log when the loop is wired to one.

## The 17-step cycle, as implemented

The mandate's section 5 cycle has 17 steps. loop.py implements
them as a 15-state chain plus the two terminal states
rolled_back and failed:

| Mandate step | Loop state |
|---|---|
| 1. Observe the real mining system | observe |
| 2. Identify a measurable weakness, and 3. Form a hypothesis | hypothesise |
| 4. Search previous research for related findings | check_prior_research (rejected-hypothesis gate on entry) |
| 5. Analyse the relevant source code | analyse_source |
| 6. Derive the proposed change | derive_change |
| 7. Check mathematical correctness | mathematical_correctness |
| 8. Create an isolated experimental implementation | isolated_implementation |
| 9. Run correctness tests | correctness_tests |
| 10. Run controlled performance measurements | controlled_measurement |
| 11. Compare against the production baseline | compare_baseline |
| 12. Perform independent candidate verification | independent_verification |
| 13. Test block acceptance where applicable | block_acceptance |
| 14. Record the complete evidence | record_evidence |
| 15. Integrate only when acceptance criteria are satisfied | integrated (integrate gate on entry) |
| 16. Monitor the production result | monitor |
| 17. Roll back if the integrated implementation violates its acceptance criteria | rolled_back (terminal) |

A record also carries its hypothesis text, keywords, the
implementation author, whether it makes a performance claim, its
evidence bundle, and a full timestamped history. advance() moves
exactly one state; a record at monitor cannot advance further;
fail() moves any non-terminal record to failed with a reason.

## The two gates

Rejected-hypothesis gate (hypothesise to check_prior_research):
if the record's keywords all match a REJECTED research memory
entry (memory.was_rejected), the advance is refused with a
LoopRefusal carrying the citation (entry id, title, status,
source). The record is unchanged. If the loop has no memory
bound, the gate cannot fire and the record's history says so
(prior_check_skipped_no_memory); with no keywords, the check is
skipped. The gate matches recorded wording exactly, which is a
known limitation (see docs/AGENT_CAPABILITIES.md).

Integrate gate (record_evidence to integrated), implemented by
validate_integrate_evidence. The evidence bundle must contain:

- a correctness pass;
- a differential pass;
- an independent verification record with an author, where the
  author differs from the implementation author, and the record
  itself passes;
- when the record makes a performance claim, an EXP-017 style
  statistical verdict: at least 3 sessions, a pooled ratio above
  1, and a confidence interval for the relative improvement
  (pooled ratio minus 1) lying entirely above 0 (ci_low above 0
  and ci_high at least ci_low).

An incomplete bundle is refused with every missing or inadequate
item named in the refusal. This is the EXP-017 protocol as the
integration gate, per the owner's adopted decision rule
(2026-11-14): 3 or more sessions, paired blocks, adjusted
bootstrap interval entirely above 0, plus the correctness gates.
No second benchmarking statistic exists in the pipeline.

## The experiment runner

ExperimentRunner (experiments.py) is how steps 8 to 14 execute:

- create_experiment opens a loop record and a sandbox directory
  under .local/agent-experiments/<experiment_id>/, then advances
  through the hypothesise gate immediately, so a rejected
  hypothesis is refused at creation.
- target_path resolves paths inside the sandbox and raises
  SandboxEscape on parent traversal or absolute escapes;
  write_file writes only through it.
- run_command executes an argv list only (a shell string is
  refused with TypeError), with cwd inside the sandbox, capturing
  stdout and stderr to per-run evidence files, and records the
  exit code and wall time in the record history.
- assemble_evidence collects the sandbox's evidence JSON files
  (schema: correctness_pass, differential_pass,
  independent_verifier or null, exp017 or null) into the bundle
  the gate consumes. Merging is conservative: passes must hold in
  every file that states them; the verifier and the EXP-017 block
  come from the last file in sorted order that states them
  non-null. The exp017 interval, stated for the pooled ratio, is
  converted to the gate's relative-improvement form (ratio minus
  1).
- attempt_integrate only asks the gate and reports its verdict.
  The runner never edits production code and never integrates: a
  gate pass is a record decision, and production integration
  remains a separate gated act.

## The rollback path

Three layers, in the order they apply:

1. Loop level: rollback(record, reason) is available from the
   integrated and monitored states only, so a rollback claim
   always refers to something that was integrated; it moves the
   record to rolled_back and notes the reason in the history and
   the audit log.
2. Production level: an actual production integration is a
   separate act outside this package, executed the way the
   programme's integrations have always been executed (for
   example the EXP-039 tier dispatch, with the previous backends
   preserved behind the new ones, and scripts/solo_cutover.py as
   the standing template for a controlled production transition
   with automatic rollback on failed verification). The loop's
   gate pass authorises considering that act; it does not perform
   it.
3. Audit level: after any production integration, an independent
   agent (not the integration author) audits the actual
   production code before anything else moves (owner order,
   2026-11-14). Every integration in the programme's record
   (v512, EXP-025 cache, EXP-022 flags, v512dual, EXP-039) carries
   such an audit; a failed audit is itself a rollback trigger
   under step 17 of the cycle.

## Worked example 1: the K+W folding refusal

A loop record proposing K+W constant folding was advanced
through the real code path against the real research memory
(Milestone 2 demonstration, research/master_build/
MILESTONE2_LIVE_AWARENESS.md). The first advance (observe to
hypothesise) succeeded. The second was refused by the
rejected-hypothesis gate:

```text
state after first advance: hypothesise
REFUSAL: loop demo-kw-folding: hypothesis matches rejected
research memory entry EXP-014; re-proposing a rejected idea
is refused
CITATION: {
  "entry_id": "EXP-014",
  "title": "EXP-014: K+W constant folding for template-fixed MB rounds",
  "status": "REJECTED",
  "source": "research/sha256d/extreme_optimization/EXPERIMENT_REGISTRY.md"
}
```

EXP-014 rejected K+W folding in the original programme (no gain
as implemented). The pipeline's evidence value here is negative
and exactly as designed: the idea never reached an experiment,
no time was spent re-measuring a decided question, and the
refusal names its source. Precision recorded at the time: the
keywords that fired were ["K+W", "constant folding"]; ["K+W
folding"] alone did not match the registry's wording.

## Worked example 2: the batch-size experiment refusal

Experiment exp-20261116T004628Z-83dafa (Milestone 3
demonstration, research/master_build/MILESTONE345_BUILD.md),
hypothesis "search batch size changes C backend throughput", not
in the registries, performance claim true. A sandbox script
measured the ComputeEngine C backend through
search_first_counted at 2 threads, target 1, 3 repetitions each,
strictly sequentially: median 720,712 H/s at a 65,536 search
range per call and 1,396,011 H/s at 131,072. Inside the same
script, a differential against hashlib passed, and the evidence
JSON recorded correctness_pass true, differential_pass true,
independent_verifier null, exp017 null.

The runner walked the record to record_evidence and attempted
integration. The gate refused, naming exactly two missing items:
"independent verification record" and "EXP-017 statistical
verdict". Nothing was integrated and no production claim was
made. The medians hint that a larger range amortises per-call
overhead, but 3 contended repetitions are not an EXP-017 verdict
and the experiment's own author is not an independent verifier.
The experiment stands in the record as a measured hint awaiting
a properly run EXP-017 campaign and an independent verifier, if
anyone chooses to pursue it; the pipeline spent about 5 seconds
of sandbox execution to reach that position.

## What the pipeline does not do

It does not edit production code, run the EXP-017 harness itself
(the harness remains research/sha256d/phase6/benchmarks/
exp017_paired_bench.py, invoked as experiment commands), verify
candidates itself (that is mining/candidate_verify.py, reached
through the interface), or certify its own success: the gate's
independent-verification requirement exists precisely so the
author of a change cannot be its only checker.
