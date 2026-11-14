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
5. Memory bandwidth (2.739 GB/s single-stream under
   contention, per the saved probe record; an unsourced
   4.0 GB/s figure in earlier revisions is withdrawn) is
   orders above mining's needs; compute and latency chains
   are the binding constraints.

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

## Documentation corrections (Stage 5 authorization, 2026-11-14)

- header_and_midstate_analysis.md: the first nonce-dependent
  EXPANDED schedule word is W18, not W19
  (W18 = sigma1(W16) + W11 + sigma0(W3) + W2; the t-15 input
  is the nonce word W3). W19 also appeared in
  message_schedule_research.md and is corrected there too.
  Indexing correction only; the 67/192 ceiling is unchanged.
- cpu_microarchitecture.md: reconciled with the saved probe
  record (tools/machine_probe_2026-11-14.json). Probe-session
  load average is 8.66 (not 10.7, which had no saved source;
  loads above 10 belong to the separate EXP-000 baseline
  sessions), and memory-copy bandwidth is 2.739 GB/s (the
  unsourced 4.0 GB/s figure is withdrawn; the same figure in
  README.md bottleneck B5 is corrected to match).

## Stage 5 results (2026-11-14, EXP-002 and EXP-003)

- H-02 BUILT AND FULLY CORRECT: the direct SHA-NI kernel in
  experiments/h02_shani/ produces the entire message
  schedule with SHA256MSG1/SHA256MSG2, zero scalar schedule
  words. Equivalence of the MSG path is proven by a scalar
  twin build (identical rounds, scalar schedule, zero MSG
  instructions) producing byte-identical digests, on top of
  120,000 randomized differentials vs hashlib across three
  prefix variants and 5,000 vs production.
- The MSG schedule alone is worth about 2.6x at equal
  rounds: scalar twin 2T median 751,524 H/s vs MSG kernel
  1,966,395 H/s in the same session (bench_h02.py).
- Medians favour the new kernels in every session measured
  (decision run, interleaved: at 2 threads production
  1,183,205, H-02 2,068,798, H-01 streams=2 1,932,862,
  streams=4 3,084,485 H/s). At 1 thread the new kernels'
  ranges fully clear production's range.
- H-01 MEASURED: interleaving works. Per-worker streams=2
  is 2.36x streams=1 within one session; streams=4 has the
  highest medians and the tightest decision-run spread
  (37.0 percent) despite heavy register spills (365 xmm
  stack ops in the blended hot function): latency hiding
  outweighs spill cost on this core, as measured.
- H-03 prefix precomputation: implemented in three correct
  variants; the effect is below this VM's noise floor and
  the spreads fully overlap. Recorded INCONCLUSIVE, not as
  a gain and not as a refutation.
- NOT INTEGRATED, by the rule: at the 2-thread tuned
  configuration the decision-run ranges still overlap
  (production best sample 2,442,181 vs streams=4 minimum
  2,130,229), because this contended VM's session spread
  (production 142.3 percent in that run) exceeds any
  margin measurable today. Production is byte-identical.
  The kernels, tests, and benchmark drivers stay in the
  research tree for a quieter-window decision re-run.

## Not established (and not claimed)

- No production integration: the strict beyond-spread test
  at 2 threads is not met yet (see Stage 5 results).
  Production code is unchanged.
- Nothing about GPU, FPGA, or ASIC performance; those gates
  remain exactly as Tasks 002/003 left them: UNVERIFIED on
  this hardware.
- No cycles-per-hash or IPC figures; perf counters are
  unavailable in this guest.

## The one-sentence summary

The direct SHA-NI kernel is built, proven correct, and
faster by median in every session; on a VM this noisy the
honest verdict is "repeat the decision run in a quieter
window", not a production swap on overlapping ranges.

## Pointer: the extreme optimization tree (2026-11-14)

The Grand Research Mandate's first assignment (investigation
and documentation only) is recorded in
research/sha256d/extreme_optimization/: a master plan, the
mathematical map, CPU execution and memory analyses, a
reverse-engineering review, a ranked family comparison,
116 new X-series hypotheses, the permanent experiment
format with EXP-000 to EXP-003 backfilled, a bottleneck
analysis (including the mainnet_live.py uncounted-span
leftover, filed as a pipeline fix direction), a performance
roadmap whose target assessment concludes that 500 GH/s
and 140 TH/s are aggregate-fleet scale (about 25,000 and
about 7 million cores at the optimistic per-core ceiling
estimate of about 20 MH/s), and a final report whose first
recommended experiment is the quiet-window decision re-run
this file already calls for. Production remains unchanged.

## Batch EXP-004 to EXP-009 (2026-11-14)

Full records: extreme_optimization/EXPERIMENT_REGISTRY.md
and extreme_optimization/EXP004_009_REPORT.md.

- EXP-004: the X-067 decision re-run failed the strict
  beyond-spread criterion a second time (streams=4 median
  4,212,571 vs production 1,463,346 at 2 threads; streams=4
  min 2,057,942 below production max 2,346,013; steal only
  2.24 percent, so runnable-load fluctuation is the noise).
  No integration; production byte-identical.
- EXP-005: geometry map complete (streams 1, 2, 3, 4, 6;
  blocked and strided; all gate-verified with wave-exact
  accounting). Best at 2 threads: streams=4 strided.
- EXP-006: schedule-first hand scheduling cuts spill ops
  790 to 117 and gains nothing; spills are not the binding
  cost. Negative result, mechanism recorded.
- EXP-007: AVX-512 16-way multi-buffer is the fastest
  measured implementation on this VM on a median basis at
  2 threads (6,526,467 and 3,195,024 H/s in two interleaved
  sessions), widest variance, no separation claim. X-041
  frequency gate inconclusive under contention.
- EXP-008: phase pipelining is at parity with a second
  same-phase stream; no phase premium on this core.
- EXP-009: X-059 priced by measurement (validateaddress
  round trip 3.963 ms median dominates build_candidate
  below about 250 transactions; re-verification about
  17.8 us per transaction; exactly one validateaddress
  and one getblockchaininfo per call). No span-size
  interaction measurable; search is 99.958 percent of a
  stub mine cycle's wall at an empty template.

Tier summary (MASTER_RESEARCH_PLAN.md classification):
VERIFIED IMPROVEMENT: MSG schedule, stream interleaving,
strided assignment tendency, AVX-512 multi-buffer medians,
the X-059 prices. PROMISING HYPOTHESIS: hand-scheduled
assembly (weakened), phase pipelining elsewhere, AVX2
8-way for narrower machines. UNPROVEN BREAKTHROUGH:
anything beyond the per-core ceiling narrative.

## Pointer: Next Research Phase, Parts B to D (2026-11-14)

The Y-series registry (108 hypotheses), the
performance ceiling report (three derived
assumption sets; per-core ceiling in the low tens
of MH/s under every set), and experiment batch
EXP-011 to EXP-015 live in the extreme_optimization
tree (EXP011_ONWARD_REPORT.md). Headlines: the
Boolean cone is at its proven minimum in the
compiled MB kernel (EXP-012, z3 plus exhaustive
search); bitslicing is refuted by implementation
at about 30x below MB (EXP-015); dual-batch MB
and cross-lane sharing are promising but
unseparated on this guest (EXP-011, EXP-013);
K+W folding does not pay as implemented
(EXP-014). No verified improvement this batch and
no integration; production is byte-identical.

## Pointer: EXP-010 Part A decision closure (2026-11-14)

The decision is closed. Run on the owner's
immediate order during initial block download
(the contention is part of the record), both
challengers again beat production on medians
(streams=4 strided 3,342,449 H/s, 2.76x; AVX-512
multi-buffer 3,551,903 H/s, 2.94x, median CIs
clear of production's) and again failed the
predeclared beyond-spread criterion on their
minimum rounds (1,440,195 and 2,006,621 against
production's maximum 2,288,008). Production C
remains the mining backend, byte-identical. The
multi-buffer kernel's variance is not a steal or
load-spike artefact: calm and spiked round
medians differ by 1.3 percent while its spread
is 207.7 percent against production's 115.8
percent under identical conditions. Full report:
extreme_optimization/EXP010_PART_A_REPORT.md.
Tier classification: no verified improvement at
the integration standard; the median superiority
under stated contention is a verified
measurement, not an integration.

## Pointer: Phase 6, first assignment (2026-11-14)

Phase 6's first assignment is complete. Headline
results: EXP-016 derived the nonce dependency of
block 2 exactly and refuted Y-065 and Y-075 as
work reductions (z3 proofs plus a numerically
verified counterexample at schedule word W20;
state affine in the nonce only after round 3,
fully nonlinear from the state after round 7 in
0-based indexing). The audit corrected three
overbroad conclusions in place: the 125-round
figure is the conventional evaluation's remaining
count, not a proven universal lower bound; the
ceiling models are labelled implementation-model
estimates with their assumptions collected; and
the memory conclusion is narrowed to DRAM
bandwidth, with register, spill and stack costs
recorded as first-order. All 108 Y hypotheses are
ranked under a published method
(phase6/HYPOTHESIS_RANKING.md), the discovery
system's first component is built and
seed-validated (phase6/COMPUTATION_GRAPH_RESEARCH
.md), and the next four experiments are selected
(EXP-017 measurement stack, EXP-018
register-resident dual-batch, EXP-019 carry-save
pricing, EXP-020 full-round rewriting). No
production change, no verified improvement
claimed. Full report: phase6/PHASE6_FINAL_REPORT
.md.

## Pointer: EXP-017 measurement stack (2026-11-14)

EXP-017 has run. The paired protocol and its
predeclared adjusted paired log-ratio statistic
are validated: both equal-pair controls null in
every session and pooled, the old min/max rule
passed a phantom difference in 0 of 6 control
sessions, and covariate adjustment was priced
near-neutral (the pairing carries the value).
Under the EXP-017 measurement rule, AVX-512 MB
(+1.2652 pooled, 3.55x) and streams=4 strided
(+1.0298, 2.80x) are significantly faster than
production in every session. Measurement result
only, not an integration; a decision-rule change
is proposed to the owner in
phase6/EXPERIMENT_RESULTS.md and not enacted.
Sub-verdicts: Y-103 PASS, Y-102 PASS at 65,536
hashes, Y-101 PARTIAL. Full record:
phase6/EXPERIMENT_RESULTS.md, EXP-017.

## Pointer: EXP-018 register-resident dual-batch (2026-11-14)

EXP-018 (Y-023) has run. The new kernel
(extreme_optimization/src/avx512_mb_reg.c)
achieves register residency for the
dual-batch state at the near-zero level
(one of sixteen state vectors in a single
stack slot, per the assembly audit in
phase6/benchmarks/exp018/asm_audit.json),
and passes the full correctness gate set.
Under the EXP-017 statistic it is not
significantly faster than single-batch MB
(pooled +0.0836, CI -0.0247 to +0.1902),
though it is significantly faster than
production (+1.5027, 4.49x). Verdict: not a
verified improvement; state traffic was not
the binding cost. No integration. Full
record: phase6/EXPERIMENT_RESULTS.md,
EXP-018.

## Pointer: AVX-512 MB integrated as the production backend (2026-11-14)

The owner adopted the EXP-017 statistic as
the programme's integration decision rule
(replacing the min/max separation rule) and
named the AVX-512 multi-buffer kernel the
integration target. It is now ComputeEngine
backend "v512": production translation unit
mining/cpu/bal_avx512_mb.c built with
restricted flags (-mavx512f -mavx512bw) into
libbal_v512.so, selected only when the
flag-free CPUID probe confirms AVX-512F and
AVX-512BW and a batch reproduces hashlib
digests, with clean fallback to the OpenSSL
C backend everywhere else. Gates through
the production path: 196,608 randomized
differentials exact, accounting parity with
wave semantics, fresh regtest blocks
accepted at heights 630 and 700, test-all
green except the pre-existing test-rtl
environment failure. The live miner was
restarted onto the new code and verified
(backend v512 in the miner log and status,
counter advancing, session rate 13.28M H/s
against 3.33M H/s in the previous C session).
Classification: VERIFIED IMPROVEMENT under
the adopted rule. Full record:
phase6/PHASE6_FINAL_REPORT.md, addendum of
2026-11-14.

## Pointer: post-integration audit of the AVX-512 MB backend (2026-11-14)

An independent audit re-derived the integration's
claims from the pushed tree, fresh builds and fresh
runs: production commit byte-identical to the remote
tree; kernel body byte-identical to the EXP-007
research source; dispatch feature set (AVX-512F plus
BW) confirmed by the auditor's own objdump census;
131,072 fresh differentials exact; wave accounting
matching an independent partition prediction exactly;
fail-closed rescan verified on both the batch and
search paths; fallback to C verified for probe
failure, missing library, probe-less library and a
broken MB build; a fresh auditor regtest block
accepted at height 702. Verdict: PASS WITH NOTES.
One latent dispatch defect (a probe-only library
raises out of ComputeEngine instead of falling back)
and one pre-existing accounting note on the live
status counter are recorded with reproducers. Full
audit: phase6/POST_INTEGRATION_AUDIT.md.

## Pointer: audit defect D-1 fixed (2026-11-14)

The audit's defect D-1 is resolved: _try_v512 in
gpu/engine.py and _smoke_v512 in mining/cpu/build.py
now guard every v512 kernel entry point with hasattr
checks, so a symbol-incomplete libbal_v512.so is
rejected as a whole with the missing entry points
named and selection falls back to C (reproducer
verified before and after; the stale mainnet_live.py
docstring, note N-2, is corrected in the same pass;
note N-1 is untouched by design). A permanent
regression gate (test_incomplete_library_fallback)
runs inside tests/test_avx512_integration.py. Full
test-all: 20 of 21 targets pass, only the
pre-existing test-rtl environment failure remains.
The live miner was not restarted; the deployed
library is complete, so D-1 was unreachable in the
running deployment, and the fix lands on the next
natural restart. Resolution record:
phase6/POST_INTEGRATION_AUDIT.md, resolution section
of 2026-11-14.

## Pointer: EXP-019 carry-save schedule pricing (2026-11-14)

EXP-019 (Y-002, then Y-001) has run in its
designed order: the per-distance price list
came first and no carry-save form passed its
gate, so no kernel was built. A software 3:2
compressor costs 3 instructions (2 VPTERNLOGD
plus a VPSLLD carry alignment the registry
costing omitted), making a resolved
carry-save schedule sum 5 or 7 instructions
with a 4 or 5 stage chain against the
incumbent's 3 VPADDD and 3 stages; measured,
the carry-save forms cost 1.17 to 1.53 times
the incumbent at separations 0 and 1, the
only separations where resolution is forced,
and are slower at every separation from 1 up
under L1-resident operands. Y-002 and Y-001
are REJECTED (established negative); the
price list is the discovery cost model's
resolution table. Full record:
phase6/EXPERIMENT_RESULTS.md, EXP-019.

## Pointer: EXP-020 full-round rewriting (2026-11-14)

EXP-020 (Y-014, Y-015) ran both discovery
engines over the full round plus the schedule
cone and closed it: the extracted graph costs
28 vector ops per steady-state round in the
AVX-512 vocabulary and an independently
assembled lower bound is also 28, so the
incumbent's graph is optimal in that
vocabulary. The one op below the emitted
production code is a codegen gap (gcc emits
Maj as two ternlogs where the proven form is
one); its gated variant kernel benchmarked at
a pooled adjusted log-ratio of +0.0493 (CI
-0.067 to +0.167), not significant, so no
verified improvement and no integration.
Full record: phase6/EXPERIMENT_RESULTS.md,
EXP-020.

## Pointer: audit note N-1 fixed (2026-11-14)

The post-integration audit's last open note is
resolved. mining/mainnet_live.py now accumulates
the engine's exact attempted count
(last_search_stats["attempted"]) for each
search_first call through a new call_attempts
helper, instead of the full requested span; the
displayed session rate derives from exact
attempts. Historical rates in earlier evidence
were computed on the inflated counter and are
left as recorded. A permanent regression gate
(tests/test_mainnet_live_accounting.py, make
test-mainnet-live, part of test-all) asserts
early-exit, full-miss and no-stats fallback
accounting on the auto and C backends. Full
test-all: 21 of 22 targets pass, only the
pre-existing test-rtl environment failure
remains. All audit notes are now resolved
(D-1, N-1, N-2). The live miner was not
restarted; the fix lands on the next natural
restart. Resolution record:
phase6/POST_INTEGRATION_AUDIT.md, N-1 resolution
addendum of 2026-11-14.

## Pointer: solo cutover staged and armed (2026-11-14)

The switch from public-pool.io to the lab's own solo server
is staged and armed, not fired: the mainnet node is still in
initial block download (block 412,094 of 975,822 headers at
staging). The solo server was audited for mainnet duty and
hardened (chain gate and IBD refusal in refresh_job,
tip-following JobRefresher broadcasts, per-worker share
accounting with a status snapshot, submitblock failure
capture, validated witness commitment parsing, ntime sanity,
suggest_difficulty acknowledgement). The miner's Stratum
endpoint is now config-driven (mining/endpoint_config.py,
.local/mining-endpoint.json; pool default preserves today's
behaviour exactly), the solo runner is mining/solo_mainnet.py
behind a bal-solo systemd unit installed at fire time, and
scripts/solo_cutover.py performs the one-shot switch with a
live subscribe self-check against the node tip, verification
from the server's per-worker accounting, and automatic
rollback. Goal cron bal-solo-cutover checks every 15
minutes, fires once when the node leaves IBD with blocks
within 2 of headers, and stands itself down on the terminal
marker. Share difficulty is 0.02 (an expected share every
about 7 s at the measured v512 session rate). Regtest
end-to-end re-proven in current form: block height 763,
hash 0000001325090ccf3e4108a2d2a3ca7832f91607d1259c1e970ee0940ec4a2de,
accepted by Core through a connected miner, with per-worker
accounting asserted. Full record: docs/SOLO_CUTOVER.md.
