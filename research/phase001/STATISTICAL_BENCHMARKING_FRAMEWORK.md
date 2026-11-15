# Phase 001, Deliverable 18: Statistical Benchmarking Framework (Design)

Project: NOVA SHA-X, Research Phase 001, Wave 4.
Status: DESIGN ONLY. No performance benchmarks were run for this deliverable, per the wave rule. The framework codifies what the programme already does where it works (the EXP-017 protocol, the EXP-032 campaign discipline, the phase6/exp032 raw artifact practice) and names the gaps the NOVA audit found (no category A harness by design, no category F measurement at all, one stale category D figure in the README). It is written so that any future experiment, including the Phase 002 items in Deliverable 22, can cite it instead of re-deriving method.

## 1. Benchmark categories (Master Assignment definitions)

Six categories, never interchangeable, never reported under each other's names:

| Category | Definition | Existing harness (NOVA audit section 9) |
|---|---|---|
| A | Ordinary single SHA-256 compression throughput | None, correctly absent: no production consumer needs it |
| B | Ordinary double SHA-256 (unstructured input) | Reference loops only |
| C | Exact SHA-256d of the 80-byte header (single candidate, full framing) | Component benches |
| D | Mining kernel with reusable header state and target comparison (batch or search entry points over fixed header material) | gpu/benchmark.py, Makefile bal-miner bench, the per-experiment paired benches |
| E | Complete production search: candidate construction, work management, result handling included | Component-labelled pipeline bench (bench_exp009_pipeline.py), EXP-032 search arms, load probe; components labelled, never summed into an F claim |
| F | Complete end-to-end pipeline: template acquisition from a node, block construction, search, verification, submission | NONE. F is validated by regtest tests, not benchmarked. Building the F harness is a Phase 002 item (Deliverable 22) |

Rule F-1: a number's category is part of the number. Any report, README line or dashboard figure that states a rate without its category is defective; the audit's one mislabel (README "End to end engine rate 6,617,558 H/s", a category D batch figure from the C-backend era) is the standing example of the defect.

## 2. Metrics (required set per category)

Every benchmark run records, at minimum:

- **Central tendency and spread:** median (primary), minimum, maximum, and variance (or interquartile range) of the per-block rates; pooled estimates across sessions with bootstrap confidence intervals, as EXP-017 prescribes.
- **Correctness counters:** differentials run and mismatches (must be zero), regtest blocks mined where the protocol requires them.
- **CPU utilization:** process and host utilization over the run window; thread count; the host's claimed versus effective CPU characterization (section 4).
- **Thread scaling:** rates at 1, 2 and N threads for any multi-threaded arm, so saturation is visible rather than assumed (EXP-031 found saturation at 2 on this VM class; a scaling claim without the 1-thread anchor is invalid).
- **Instruction-level performance:** only where counters are actually accessible. On this VM class perf counters are NOT accessible (perf_event_paranoid 4, perf_event_open EPERM; EXP-031), so IPC and per-instruction claims are prohibited here; operation counts come from the census/SMT records (EXP-020), not from counters.
- **Candidate verification cost:** time to verify one candidate through the production verification path (candidate_verify), reported separately from search rate; verification is on the critical path of any found block and is part of category F.
- **Work coverage:** distinct headers hashed in the run, by construction of the paired blocks (65,536-hash blocks in EXP-017), never estimated from time multiplied by rate.
- **Duplicate work:** duplicates counted and reported as their own counter, per the EXP-035/037 accounting separation (repeated computations are recorded, never credited as coverage).
- **Benchmark stability:** per-session verdicts reported individually before pooling; a result that depends on one session is not a result (EXP-024 design B failed exactly this way: pooled 1.169x with only 1 of 3 sessions supporting it, correctly not integrated).

## 3. Controls: the EXP-017 decision protocol (adopted rule)

Integration and verdict decisions use EXP-017, unchanged:

1. At least 3 independent sessions per comparison.
2. Paired blocks of 65,536 hashes, same work in both arms.
3. Randomized AB/BA arm order within each session.
4. Adjusted bootstrap confidence interval for the ratio must lie entirely above 0 (for a claimed improvement) in every session and in the pooled estimate.
5. Full correctness gates: byte-exact differentials against the reference implementation, zero mismatches.
6. A fresh regtest block mined through the candidate path before integration.
7. Post-integration independent audit by an agent that did not author the change (the 2026-11-14 rule), before anything else moves.

Benchmarks run one at a time on this host, never in parallel: parallel runs corrupt the statistics on a shared-CPU VM (programme standing rule, from the EXP-017 era). A run contaminated by a co-running benchmark is discarded, not averaged.

## 4. Environment manifest (required with every run)

Every session file carries a manifest; a rate without a manifest is UNVERIFIED:

- Host CPU model and full flag list (the lab has run two materially different hosts: AMD EPYC 9D25 with full AVX-512 plus SHA-NI, and Intel Xeon Platinum 8321HC with AVX-512F/BW/VL/VNNI and no SHA extensions; results do not transfer silently between them).
- Compiler and exact build flags (production vector libraries: restricted -mavx512f -mavx512bw, never -march=native; the C batch library's -march=native is by design and must be recorded as such).
- VM characterization per EXP-031: claimed vCPUs, measured effective CPUs, baseline busy fraction, load average, steal range, memory. On this VM class: 4 claimed, about 2 effective, baseline 61 to 64 percent busy, load 7.0 to 7.5, steal 1.4 to 2.7 percent.
- Backend actually selected by the production probe (not the intended one), and the dispatch order in force.
- Git head or content hash of every source file in the measured path.

## 5. Raw artifact retention

- Session outputs are append-only files in the experiment's RAW_RESULTS directory (the phase6/benchmarks and exp032 practice), never overwritten; a rerun creates a new file.
- The manifest of section 4 is stored with the raw numbers, in the same file or a sibling with a shared session identifier.
- Published summaries cite the raw file paths; any number that cannot be traced to a raw file is withdrawn.
- Failures and contaminated runs are retained and labelled, not deleted (the EXP-024 and EXP-032 records keep their negative arms for exactly this reason).

## 6. Separating algorithmic gains from hardware, compiler and environment

The framework's core honesty rule, in five parts:

1. **Same-host pairing.** An algorithmic claim is only ever a ratio between two arms measured on the same host in the same sessions (the EXP-017 pairing). Cross-host ratios are reported, if at all, as UNVERIFIED beyond correctness.
2. **Compiler separation.** If the two arms differ in compiler or flags, the comparison measures the pair (algorithm, toolchain), and the report must say so; an algorithm-only claim requires identical toolchain settings except the change under test.
3. **Environment covariates.** Steal, load and baseline busy are recorded per session; a session whose covariates depart materially from the campaign's norm is flagged in the raw file and its exclusion or inclusion is decided before pooling, never after seeing the verdict.
4. **Host changes reset campaigns.** This VM is replaced frequently and the replacement may change CPU model (it has). A campaign spanning a host change is two campaigns; pooling across the change is prohibited.
5. **Category discipline.** Algorithmic gains are claimed at the category measured (D for kernel work). Promotion of a D gain to an E or F claim requires measuring at that category; the pipeline benches exist precisely because kernel gains have repeatedly failed to survive contact with candidate construction (the EXP-025 lesson: the steps500 construction rate of 23.02x is a construction figure, never a hash rate).

## 7. Current-state honesty (as of this deliverable)

- Categories A and B: unmeasured by design; no claims exist or are needed.
- Category C: measured only as components inside D/E benches.
- Category D: the programme's strongest evidence base (EXP-017 campaigns for v512, v512dual, EXP-032 tiers).
- Category E: component-labelled measurements exist; no single E rate is published, correctly.
- Category F: no benchmark exists. The end-to-end path is proven functionally (regtest blocks through the full stack, live pool shares) but has no rate, and none may be quoted until the F harness is built and run under this framework.
- Probability and coverage reporting follow Deliverable 12's formulas and the EXP-037 evidence counting; expected-time figures are model outputs and are labelled with the random-oracle assumption wherever they appear.

## 8. What this framework forbids (summary)

Reporting a rate without its category; pooling across hosts or across contaminated sessions; integrating on a microbenchmark alone; quoting theoretical or planning figures (for example core-count extrapolations toward the 500 GH/s target) as measurements; deleting negative arms; and presenting a benchmark's median without its spread and session verdicts. Each prohibition corresponds to a real incident or a real near-miss in the programme record, which is why they are written here as rules rather than advice.
