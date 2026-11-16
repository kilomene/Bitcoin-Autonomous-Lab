# Milestones 3, 4 and 5 Build: Optimisation Loop, Adaptive Scheduler, Resource Registry

Master Build Mandate sections 5, 6.3, 7 and 14. Built on the
Milestone 1 agent intelligence package (agent/intelligence/)
and the Milestone 2 live awareness layer. Date: 2026-11-15
(built and demonstrated 2026-11-16 00:41 to 00:47 UTC).
Host: htch-runtime, AMD EPYC 9D25 guest (the alternating VM
of EXP-031; about 2 effective CPUs by that characterisation).
The live mainnet miner, autopilot and pruned node ran
throughout every measurement and were never touched by this
work. Every rate below is a contended figure measured
alongside that production load, through the production
search path, and is labelled with its conditions. No rate
here is an EXP-017 verdict.

## What was built

Three new modules in agent/intelligence/, importing the
existing package and modifying none of it:

| File | Lines | Contents |
|---|---|---|
| agent/intelligence/experiments.py | 303 | ExperimentRunner: the Milestone 3 optimisation loop made executable |
| agent/intelligence/scheduler.py | 357 | Scheduler: machine profile, measured bake-off, thread sweep (Milestone 4) |
| agent/intelligence/resources.py | 334 | ResourceRegistry: workers, exact assignment, coverage (Milestone 5) |
| tests/test_agent_operations.py | 375 | Test suite for all three modules |

The only existing file edited is the Makefile: a
test-agent-operations target was added and test-all now
depends on 36 targets (was 35). Production code (mining/,
gpu/, agent/autonomous.py, agent/interface.py and every
existing agent/intelligence module) is untouched.

## Milestone 3: experiments.py

An ExperimentRunner bound to the Agent facade:

- create_experiment(hypothesis, keywords, author) opens a
  loop.py record and a sandbox directory under
  .local/agent-experiments/<experiment_id>/, then advances
  the record through the hypothesise gate. A hypothesis
  matching a REJECTED research memory entry is refused by
  the loop's own gate, with the citation (pinned by test:
  K+W folding keywords refuse with the EXP-014 citation).
- run_command(argv, timeout_s) executes an argv list (a
  shell string is refused with TypeError) with cwd inside
  the sandbox, captures stdout and stderr to per-run
  evidence files in the sandbox, and records exit code and
  wall time in the loop record history.
- target_path(rel) resolves a path and asserts containment
  inside the sandbox; parent traversal and absolute escapes
  raise SandboxEscape (pinned by test).
- assemble_evidence() collects the sandbox's evidence JSON
  files (schema: correctness_pass, differential_pass,
  independent_verifier or null, exp017 or null) into the
  bundle loop.validate_integrate_evidence consumes. The
  exp017 interval, stated for the pooled ratio, is converted
  to the gate's relative-improvement form (ratio minus 1).
  Merging is conservative: passes must hold in every file
  that states them.
- The runner never edits production code and never
  integrates. attempt_integrate only asks the gate and
  reports its verdict; a pass would be a record decision,
  and production integration remains a separate gated act.

## Milestone 4: scheduler.py

Designs R-23 (measured bake-off backend selection) and R-35
(offline benchmark through the real search path) from
research/master_build/HISTORICAL_OPPORTUNITY_REGISTER.md.
Every measurement runs ComputeEngine.search_first_counted
against a fixed work unit (header bytes(range(80)), target
1, 262,144 hashes), thread count set through the gpu.engine
C_THREADS global, rate computed as the engine's attempted
count over wall time: category E, the complete production
search path (the EXP-031 load probe method).

### Machine profile and effective-CPU probe

Auto-dispatch backend: v512dual. Median rates over 3
repetitions of 262,144 hashes: 1 thread 2,991,015 H/s,
2 threads 3,442,786 H/s. Scaling ratio 1.15, reported as
the effective-CPU estimate with its method stated (median
2-thread rate over median 1-thread rate through the
production search path; a scaling ratio, not a core count).
The estimate sits below EXP-031's about 2 effective CPUs
because it was taken under heavier contention (the live
miner at full rate on the same guest); it is an estimate of
scaling under load, and the report records it as such
rather than reconciling it away.

### Bake-off (2 threads, 262,144 hashes, 3 repetitions, medians)

| Tier | Eligible | Median rate (H/s) | Repetitions (H/s) |
|---|---|---|---|
| CUDA | no | n/a | pin not eligible on this machine; the dispatch cascaded to hashlib (no GPU exists here) |
| v512dual | yes | 2,409,210 | 3,378,823 / 2,409,210 / 2,392,899 |
| v512 | yes | 3,182,548 | 8,353,674 / 2,543,524 / 3,182,548 |
| shani | yes | 3,207,924 | 6,145,923 / 3,207,924 / 3,178,754 |
| avx2 | yes | 1,302,144 | 962,718 / 1,302,144 / 1,909,864 |
| C | yes | 640,345 | 510,086 / 927,513 / 640,345 |
| hashlib | yes | 162,815 | 113,865 / 162,815 / 220,712 |

Winner: shani at 3,207,924 H/s. Read this honestly: the
margin over v512 is 0.8 percent and repetition spread is
wide under contention, so the winner is inside run-to-run
noise and is NOT a verdict that shani is the better tier.
The bake-off is an advisory host profile in the R-23 sense;
it changes nothing in production dispatch, which remains
the shipped EXP-039 order with v512dual selected live. A
short 262,144-hash workload also compresses the differences
the long EXP-017 campaigns measured (the live miner
sustains about 20.6 MH/s on v512dual in production spans,
a different measurement from this fixed small work unit).

Cache behaviour: the result was written to
.local/agent-scheduler.json keyed by CPU model plus a hash
of the instruction flags, with a timestamp. An immediate
second call with use_cache and a 3600 s maximum age returned
the cached result (from_cache true, cache age 0.0 s, same
winner) without re-measuring.

### Thread sweep (winner tier shani, same workload, medians)

| Threads | Median rate (H/s) | Repetitions (H/s) |
|---|---|---|
| 1 | 840,377 | 698,369 / 1,272,935 / 840,377 |
| 2 | 2,828,234 | 2,150,450 / 2,828,234 / 7,834,480 |
| 4 | 3,205,348 | 3,205,348 / 4,681,237 / 2,548,100 |

Recommendation: 4 threads for the shani tier on this host
under these conditions (argmax of the medians). Total
scheduler demonstration runtime (profile, bake-off, cached
read, sweep): 10.5 s, well inside the 4 minute budget.

### Target gap, stated as required

The bake-off winner rate, 3,207,924 H/s under the demo
conditions above, is 0.000642 percent of the 500 GH/s
minimum objective (gap factor about 155,864) and about
0.0000023 percent of the 140 TH/s larger objective. The
standing verified live figure remains about 20.6 MH/s
(0.00412 percent of 500 GH/s). Neither target is approached
by these results and neither is lowered.

## Milestone 3 demonstration: one real experiment

Experiment exp-20261116T004628Z-83dafa, hypothesis "search
batch size changes C backend throughput" (not in the
registries), author agent-m345, performance claim true.
A sandbox script (bench.py, run through run_command, exit
code 0, wall 4.90 s) measured the ComputeEngine C backend
through search_first_counted at 2 threads, target 1, 3
repetitions each, strictly sequentially:

| Search range per call | Rates (H/s) | Median (H/s) |
|---|---|---|
| 65,536 | 720,712 / 1,757,127 / 577,105 | 720,712 |
| 131,072 | 1,396,011 / 1,485,023 / 779,077 | 1,396,011 |

Inside the same script, a differential against hashlib
(double SHA-256 of the header carrying nonce 0, compared
with the search path's returned digest at maximal target)
passed, and the evidence JSON recorded correctness_pass
true, differential_pass true, independent_verifier null,
exp017 null.

Gate outcome: the runner walked the record to
record_evidence and attempted integration. The gate REFUSED,
naming exactly two missing items: "independent verification
record" and "EXP-017 statistical verdict". That is the
mandate working as designed: the medians above hint that a
larger range amortises per-call overhead, but 3 contended
repetitions are not an EXP-017 verdict and the experiment's
own author is not an independent verifier, so nothing was
integrated and no production claim is made.

## Milestone 5: resources.py

A ResourceRegistry persisted as JSON (default
.local/agent-resources.json, injectable path, atomic write
via temp file plus os.replace):

- register_worker records identity, machine, CPU model,
  effective CPUs, instruction list and backend.
  heartbeat stamps liveness.
- assign refuses any overlap with an active or completed
  assignment sharing the same job identity and extranonce
  space, refuses a nonce end above 2^32 (an end of exactly
  2^32 is allowed), and refuses unknown workers.
- complete marks an assignment completed ONLY when
  batches_completed equals batches_total; a partial report
  records progress and leaves it active. Repeated
  computations accumulate as their own counter and never
  enter unique coverage (mandate section 10.1).
- reassign moves an unfinished assignment to another
  worker, preserving completed-batch progress as the new
  frontier; the move completes nothing, and completed
  assignments cannot be reassigned.
- unique_coverage(job_identity) returns the union size of
  completed ranges plus completed prefixes of active ranges
  (batch progress covers a range from its start in order,
  the EXP-038 frontier model), computed by interval
  merging, with the method stated in the result.

Randomised campaign result (run identically by the test
suite and by the demonstration): 240 trials, small ranges
(16 chunks of 256 nonces, 4 batches per chunk), injected
worker deaths and reassignments (4,759 reassignments in
total). In every trial, completed coverage was pairwise
disjoint and the registry's unique coverage equalled an
independent model's union computed in the test. Deterministic
seeds: the campaign reproduces exactly.

## Tests

- tests/test_agent_operations.py: ALL PASSED, 10,306 checks
  (including the 240-trial campaign's per-step assertions),
  about 47 s wall. Covers the rejected-hypothesis refusal
  with citation, sandbox containment refusal, shell-string
  refusal, a real tiny experiment end to end with the gate
  refusing an incomplete bundle and accepting a complete
  synthetic one, scheduler measurement through the real
  ComputeEngine on the C tier (positive rate, exact attempted
  count), winner ordering on synthetic tables, fresh-cache
  service, and the full resources pin set. The full bake-off
  is deliberately not run inside the suite; it is the
  demonstration above.
- tests/test_agent_intelligence.py: ALL PASSED, 86 checks.
- tests/test_agent_awareness.py: ALL PASSED, 50 checks.
- Makefile: test-agent-operations added; test-all is now
  36 targets.

## Honest limits

- Single machine only. The registry is a single-process,
  single-machine component. It implements no network
  protocol and claims no multi-machine behaviour.
- Contended host. Every demonstration rate was measured
  alongside the live miner on a shared, capped guest;
  repetition spreads are wide and the bake-off winner's
  margin is inside noise. These are host profiles, not
  EXP-017 verdicts.
- Short workload. 262,144 hashes per repetition is a
  profiling unit (R-35), not a sustained-rate benchmark.
- The scheduler is advisory. It does not change production
  dispatch, thread tuning or the live miner in any way.
- The experiment runner's gate pass would still not be a
  production integration; that remains a separate gated act
  under the standing post-integration audit rule.

## Remaining gaps

Milestone 5 remainder: the production wire protocol and a
persistent coordinator remain unbuilt (specified in
EXP-035, not implemented); multi-machine coordination
overhead, real-network propagation latency and cross-machine
linear scaling remain UNVERIFIED (EXP-043 closed only the
in-process and loopback parts on this VM). Fleet activation
remains the owner's decision and has not been attempted.

Milestone 6: an agent-driven end-to-end verification
demonstration (agent to mining engine to candidate discovery
to independent verification to block construction to
submission to node acceptance, on regtest, with the accepted
block height and hash recorded as one chained demonstration)
has not yet been run. Its components exist and are tested
separately (live awareness, the interface's candidate
verification through mining/candidate_verify.py, the
EXP-036/EXP-040 regtest acceptances), but the chained
Milestone 6 demonstration is the next piece of work.
