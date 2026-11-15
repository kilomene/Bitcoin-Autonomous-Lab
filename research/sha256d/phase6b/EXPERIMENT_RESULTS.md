# Phase 6B Experiment Results

Running record for EXP-024 to EXP-029. Opened
2026-11-14 with Assignment A. Entries below began as
reservations; results are appended here (and written
in full in the per-experiment files) as experiments
close. EXP-024 closed 2026-11-15 (record appended
below the table).

Record format per experiment: unique ID, source
commit (remote head at experiment start, bound by
blob comparison), hypothesis, mathematical basis,
implementation details, proof or differential
evidence, machine-code evidence, benchmark
methodology, raw results (append-only session files),
statistical analysis, decision, follow-up.

| ID | Experiment | Status |
|---|---|---|
| EXP-024 | AVX-512 mask-based early-exit search | COMPLETE 2026-11-15: PROMISING HYPOTHESIS (primary criterion not met); not integrated |
| EXP-025 | EXP-023 cache correctness and identity repair | COMPLETE 2026-11-15: ACCEPTED as a correctness repair (all six predeclared elements pass); not integrated |
| EXP-026 | Extreme AVX-512 execution research | COMPLETE 2026-11-15: C2 DualMask VERIFIED IMPROVEMENT (search scope); C1 TernMask ESTABLISHED NEGATIVE; C2 INTEGRATED 2026-11-14 as backend v512dual (see the integration record at the end of this file) |
| EXP-027 | New computational representations | COMPLETE 2026-11-15: characterised search, all spaces closed at stated scopes, no candidate survived proof plus costing; not integrated |
| EXP-028 | Cross-architecture software research | COMPLETE 2026-11-15: roadmap and dispatch specification; AVX-512 VERIFIED on 2 hosts, SHA-NI MEASURED in research, AVX2/ARM SPECIFIED UNVERIFIED; not integrated |
| EXP-029 | Parallel and distributed CPU execution | COMPLETE 2026-11-15: allocator proven by test, overhead measured local-prototype only, regtest height 829; multi-machine UNVERIFIED; not integrated |

Baseline of record for all Phase 6B comparisons:
CURRENT_PRODUCTION_AUDIT.md sections 2, 4 and 6
(production v512; EXP-017 decision measurements;
EXP-000 C baseline; live system observation), with
raw evidence in research/sha256d/phase6/benchmarks/
and the experiment registry.

## EXP-024 record (closed 2026-11-15)

Source commit: remote head at experiment start
2bc63b49a16b15d899d4eab85379f9b957015dcf (Assignment A
baseline; local tree equal by blob comparison except
the live evidence log). Hypothesis: Y-089 / Y-100
(search must not materialise all digests). Basis:
audit trace section 4.1 of EXP024_MASK_SEARCH.md;
the opmask lexicographic compare proven in EXP-022
batch scope. Implementation: research kernel
avx512_mb_mask_search.c (designs B, C, scan arm D/E,
batch form), production untouched. Proof: gates G1
to G9 all PASS (149,932 differential nonces vs
hashlib; candidate-set equivalence at densities 0,
2^-16, 2^-8, 1; target and nonce boundaries; exact
wave accounting incl. 29 extra recounted hit spans;
ASan/UBSan clean). Fresh regtest blocks through the
mask kernel via production MiningEngine: height 824
hash 63794c057b32200815533cfe59126a057fa158f69750e0a020d42e82fd2caf14
(design C), height 825 hash
48605bb7111942760c57601c2962097bd3cd4264d415d85f6dd8df4d5a1e9737
(design B), both accepted and re-verified. Machine
code: vm_group carries 15 opmask-writing vpcmp
instructions and exactly 8 zmm digest staging stores
behind a kortestw mask guard (zero digest stores on
the miss path); the production library carries 0
vpcmp instructions and compares scalar byte by byte.
Benchmarks: EXP-017 protocol, 27 sessions x 120
pairs, raw files under phase6b/benchmarks/exp024/.
Primary (B vs production, density 0, 2T): pooled
1.169x [1.031, 1.327], significant pooled and in 1
of 3 sessions. C vs production (density 0, 2T):
1.416x [1.255, 1.603], significant in every session
and pooled. Control (B vs B): 0.920x [0.817, 1.035],
null. B at 1 thread: 1.264x pooled, 1 of 3 sessions.
Hit density 2^-12: B 1.073x and C 1.099x vs
production, neither significant; C vs B 1.035x,
null. Scan (complete-the-span): time to candidate
6.16x slower median than early exit, ESTABLISHED
NEGATIVE for search. Pure batch rerun (kept
separate): flags vs production batch 1.649x [1.466,
1.860], reproducing EXP-022. Decision: the
predeclared criterion (primary significant in every
session and pooled) is NOT met; classification
PROMISING HYPOTHESIS; C is the leading form but is
not promoted post hoc, and at density 0 its margin
cannot be attributed to adaptive extraction, which
never executes on the miss path. Not integrated; no
gap-model change. Follow-up: EXP-024b confirmation
with C predeclared as primary plus a same-process
B/C interleave arm (specified in
EXP024_MASK_SEARCH.md).

## EXP-025 record (closed 2026-11-15)

Source state: local tree at Assignment A baseline
(local checkout carries no .git; production files
verified byte-identical to their pre-experiment
hashes at close). Hypothesis: the EXP-023
prototype's 8-field fingerprint does not cover every
input that can change the cached objects, so silent
stale serves exist. Basis: full dependency matrix
derived field by field from mining/engine.py
build_candidate, build_coinbase and mining/pow.py
(EXP025_CACHE_CORRECTNESS.md section 2): the
construction's complete input set is the payout
address, chain, version, previousblockhash, height,
bits, target, coinbasevalue, coinbaseaux flags,
per-transaction data, txid and fee in order, and
default_witness_commitment, with mintime, curtime
and the extranonce as per-build inputs. Defect
demonstration (against the unmodified prototype,
record defect_demo_20261115T051355Z.json): FIVE
stale-serve shapes with the fingerprint unchanged
(middle transaction replaced; witness-only change
with txid fixed; middle reorder; flags change;
target change) and TWO validation bypasses (fee
raised with coinbasevalue fixed; wrong commitment
field), plus two proven output-irrelevant gaps
(fee moved with total fixed; curtime, read fresh).
Implementation: exp025_repaired.py, a layered
identity (family, transaction, coinbase and header
keys under one dsha256 identity) covering the full
dependency set; sibling serves recompute the
identity from scratch and raise on any mismatch.
Proof: 19 adversarial invalidation cases pass three
ways each; positive controls prove reuse happens
only under identical identity (prepares 1, hits 1);
1,320 randomised differential cases byte-identical
to production build_candidate (gates record
gates_20261115T051501Z.json). Regtest: block built
with construction through the repaired cache
accepted, height 826, hash
4d43835d08290e3db41d3953c47e3e39d213f4b2166299c16be38cd57a3e8734.
Performance re-check (EXP-017 protocol, 3 sessions
x 60 pairs per comparison, this host AMD EPYC
9D25): steps500 pooled 23.02x [20.22, 25.93],
significant in every session and pooled, VERIFIED;
family500 pooled 1.083x [1.022, 1.151], significant
pooled and in 1 of 3 sessions, NOT VERIFIED under
the predeclared rule. Identity cost decomposition:
one sibling identity recomputation is 3.573 ms
median against 4.499 ms for a full uncached build
at 500 transactions, which is why the family shape
keeps only about 1.08x while the steps shape (the
shape the live GBT loop exercises) keeps the full
gain. Decision: ACCEPTED on all six predeclared
correctness elements; the EXP-023 prototype in its
original form stays unsafe and unintegrated; the
repaired design is a recorded recommendation for
the owner's decision, not integrated. Follow-up:
any integration must use the repaired identity and
re-run the post-integration audit; a cheaper
complete identity (if one is ever proven) is a new
experiment, not an edit to this one.

## EXP-026 record (closed 2026-11-15)

Source state: local tree at Assignment A baseline;
production files verified byte-identical to their
pre-experiment hashes at close. Cost model filed
before any candidate was compiled (five candidates;
C3 register schedule ring, C4 phase pipelining and
C5 hand scheduling killed at the model with
quantified reasons). Built: C1 TernMask (EXP-024
mask kernel with explicit VPTERNLOGD cones, Ch 0xCA,
Maj 0xE8, XOR3 0x96) and C2 DualMask (EXP-018
register-resident dual-batch compress, unchanged,
plus the EXP-024 opmask compare per batch and
lowest-lane extraction only on a hit batch;
dual-atomic 32-lane early exit). Gates all PASS
before timing (record gates_20261115T052557Z.json;
the preserved pre-fix record
gates_20261115T052511Z.json shows the gates catching
a real transcription defect in C2, an outer length
word of 640 for 256, before it was fixed): batch
differentials 155,061 (C1) and 161,531 (C2) nonces
byte-identical to hashlib and production;
candidate-set equivalence at densities 0, 2^-16,
2^-8, 1; target and nonce boundaries; exact
accounting under each candidate's own atomicity
rule; genesis re-found by both; ASan/UBSan clean.
Machine code: C2 dual compress 1,085 instructions
with 96 vpternlog; C1's explicit cones produced no
distinct codegen in the inlined search group (576
instructions, identical census to the mask kernel).
Benchmarks (EXP-017 protocol, 21 sessions x 120
pairs, density 0): C2 vs production at 2 threads
pooled 1.718x [1.511, 1.955], significant in every
session; C2 vs its strongest single ingredient
(mask C) pooled 1.444x [1.288, 1.618], significant
in every session; C2 vs production at 1 thread
pooled 1.967x, significant in every session. C1 vs
production at 2 threads pooled 1.083x, not
significant; C1 vs mask C pooled 0.764x [0.677,
0.859]: slower than its own ingredient. Control
(mask C vs mask C) pooled 0.992x, null. Regtest:
C2 block height 827, hash
3bee3dae4d9d8b0c99c38cc6130cc75f5e517491be59fec68c7e31d5128e6c49;
C1 block height 828, hash
6b0822ef4f6874a2a1aa74ea0c18a0b1b0616b1fed61d3009be624e6604e9589;
both accepted through the production MiningEngine
with a research search shim, labelled as such.
Decision: C2 DualMask is a VERIFIED IMPROVEMENT
(search scope, density 0) under the owner's EXP-017
rule and is eligible to propose integration to the
owner; it is NOT integrated. C1 TernMask is an
ESTABLISHED NEGATIVE as a combination and is
retired. Full record:
phase6b/EXP026_AVX512_EXECUTION.md.

## EXP-024b record (closed 2026-11-15)

Lettered confirmation run of EXP-024 (owner
approved 2026-11-14; run after EXP-025 and
EXP-026; not a new ID, next unreserved stays
EXP-030). Predeclared before timing in
EXP024_MASK_SEARCH.md: primary design C vs
production search, density 0, 2 threads, EXP-017
protocol, criterion adjusted CI entirely above 0
in every session and pooled. Compact gates PASS
(131,072 differentials for C vs hashlib and
production; candidate equivalence at densities 0
and 2^-12; genesis re-found by C), on top of the
full EXP-024 gate set for this exact kernel.
Primary result: pooled 1.398x [1.242, 1.578],
pairs won 68.3%, significant in every session
(+0.387, +0.291, +0.323) and pooled: CRITERION
MET. Control C vs C null (0.956x [0.850, 1.080]).
Supporting 1 thread: 1.463x [1.301, 1.648], every
session significant. Same-process B/C interleave:
C over B pooled 1.011x [0.895, 1.140], pairs won
50.0%, null in every session: the EXP-024 B/C
divergence was a per-process layout and scheduling
effect, not a code effect; the mask compare form
itself (shared by B and C) carries the gain.
Decision: design C is a VERIFIED IMPROVEMENT
(search scope, density 0). Not integrated.
Recommendation, recorded at fallback strength
only: EXP-026 DualMask (1.718x, also verified)
remains the leading integration candidate; C adds
a certified single-batch fallback form and the
closed attribution record, and does not displace
DualMask. Full record: EXP024_MASK_SEARCH.md,
EXP-024b sections; raw data in
phase6b/benchmarks/exp024b/.

## EXP-027 record (closed 2026-11-15)

Source state: local tree at Assignment A baseline;
production files verified byte-identical to their
pre-experiment hashes at close. Track B. Hypothesis:
exact representations outside the vocabulary closed
by EXP-020 price below the incumbent for at least
one cone. Method per candidate: exact input and
output defined in EXP027_COMPUTATION_
REPRESENTATIONS.md; equivalence by z3 (UNSAT) or a
filed SAT counterexample; 1,000,000-sample
differentials for cone-level forms; costing under
the phase cost model with vocabularies stated.
Results by space. GFNI: the four sigma maps are
proven GF(2)-linear (z3 UNSAT), but every Sigma0
output byte depends on all four input bytes, which
refutes every single-instruction per-byte affine
form (filed counterexample pair) and puts any GFNI
network at a floor of 11 ops (construction 35)
against the incumbent's 4; Ch and Maj are proven
non-affine by z3 SAT counterexamples, numerically
rechecked, so no affine form computes them; the
GFNI hardware semantics model itself was verified
at 1,000,000 bytes, 0 mismatches, after two wrong
conventions were caught by the same differential.
VPSHUFB rotations: exhaustive search of all 625
per-dword byte-select patterns on 10,038 inputs
found 0 survivors for ROTR13 and Sigma0; the mixed
shuffle plus shift/or construction is proven exact
(z3 UNSAT; 1,000,000-dword hardware differential,
0 mismatches) at 4 ops against 1 VPROLD, and a
register-resident price micro measured it at 2.00x
the VPROLD price in all three sessions. State
representations: rotated and byte-swapped states
are refuted by z3 SAT counterexamples to addition
equivariance (both numerically rechecked; Ch and
Sigma0 do commute with rotation, which is what
makes the rotated form tempting); bitslicing stays
closed by EXP-015's measurement; cross-lane delta
state loses its premise to EXP-016. Carry-save
beyond the schedule: the compressor identity is
re-proven (z3 UNSAT; 1,000,000-triple differential),
and the new structural result is that every round
addition's deferral distance is exactly 0 (all
state outputs are bitwise-consumed next round), so
at the standing 3-instruction compressor price T1
costs 6 or 8 against 4 VPADDD. Addition networks:
the binary-add counting floor (4 for T1, 3 for the
schedule sum) is met by the incumbent; Kogge-Stone
lookahead censuses at about 18 ops per add;
delayed carry is refuted by the distance-0 result;
the 52-bit IFMA accumulation form is proven exact
(z3 UNSAT on overflow and on the low-32 equality;
1,000,000-sample model differential) at 5 ops
against 4. Joint optimisation: hash-consing census
finds 0 nontrivial subterms shared across the round
boundary (17 new nodes per round), and the outer
compression has all 48 computed schedule words
dependent on the inner digest with 0 digest-
independent rounds; non-sharing cross-round
restructuring is left explicitly open with its
blocker (search-space size). Schedule forms: the
unrolled direct form reaches exactly 259,905 tree
nodes at W63 against the recurrence DAG's 384 ops;
a linear schedule form is refuted by EXP-016.
Automated selection: the harness extension
(phase6/src/exp027_vocab_search.py, harness itself
unmodified and spot-checked) extracted no cone
below its EXP-020-vocabulary cost under any single
extension. Decision: EXP-027 is a successful
characterised search with a negative result; every
space is ESTABLISHED NEGATIVE at its stated scope
except the one explicitly open sub-space; no
VERIFIED IMPROVEMENT and no PROMISING HYPOTHESIS;
no kernel was compiled, so no EXP-017 benchmark
was triggered and none is claimed. Not integrated.
Full record: phase6b/EXP027_COMPUTATION_
REPRESENTATIONS.md; proofs in phase6b/proofs/
(exp027_proofs and exp027_vocab_search records);
differentials and price micro in
phase6b/benchmarks/exp027/.

## EXP-028 record (closed 2026-11-15)

Source state: local tree at Assignment A baseline;
production files verified byte-identical to their
pre-experiment hashes at close. Scope: the roadmap
and dispatch specification for every CPU family in
the directive's section 8. Implementation (research
tree only): benchmarks/exp028_probe.c, a flag-free
probe TU generalising mining/cpu/bal_avx512_probe.c
to a 16-bit feature mask (AVX-512F/BW/DQ/VL/VBMI/
VBMI2/IFMA/VNNI, AVX2, SHA, SSE4.1/4.2, BMI1/2, ADX,
AES), and benchmarks/exp028_dispatch.py, the
dispatch specification in executable form (order:
avx512-mb, shani-streams, avx2-mb, c-openssl,
hashlib; probe predicate, library completeness
before any call per the D-1 pattern, then a hashlib
self-test at every step; ARM specified into the
shani slot on non-x86 builds). Verification on this
host (AMD EPYC 9D25 guest, 4 vCPUs): the probe object
contains zero vector or extension mnemonics
(objdump census, scalar only); the returned mask
0xffff agreed bit for bit with /proc/cpuinfo; both
family predicates true; five dispatch scenarios all
selected as expected (this host avx512-mb; forced
probe failure c-openssl; incomplete vector libraries
c-openssl; failed v512 self-test shani-streams; no
libraries hashlib). Record probe_20261115T060117Z
.json, verdict PASS; the earlier FAIL record
(probe_20261115T060106Z.json) is preserved and was a
harness expectation error, documented in the
experiment file. Per-family verdicts: AVX-512 F+BW
MB VERIFIED (dispatch and correctness) on two hosts,
the AMD EPYC 9D25 and the Intel Xeon Platinum
8321HC (the restricted-flag production build
survived both; -march=native research libraries
faulted SIGILL on the Intel host, which lacks SHA
extensions and VBMI); SHA extensions MEASURED in
research on AMD (EXP-002 MSG schedule about 2.6x
same-session; EXP-003 streams=4 per-worker 1-thread
median 3.30M H/s; EXP-005 streams=4 strided 2-thread
median 3.47M H/s; EXP-021 MB pool above SHA-NI pool
1.363x at 2 threads and 1.329x at 4 threads, same
host, thread counts stated with the ratios);
Intel SHA SPECIFIED, UNVERIFIED, no rate; AVX-512
wider subsets SPECIFIED (detection implemented),
UNVERIFIED, no kernel, with EXP-027's priced-out
GFNI and IFMA forms recorded as the reason none is
motivated; AVX2 SPECIFIED, UNVERIFIED, no kernel
built, no rate quoted, named the highest-value
unbuilt family (a build would be a new experiment,
next unreserved ID EXP-030); ARMv8 SHA2 plus NEON
SPECIFIED in full (OS capability probe, never
instruction execution), UNVERIFIED, no machine, no
rate; RISC-V Zknh named only; portable C and
hashlib VERIFIED as the floor and the reference.
Accounting rules for cross-machine honesty are
filed as section 6 of the experiment file (host,
flags, allocation, thread count and contention in
every record; both sides' thread counts in the same
sentence as any ratio). Decision: predeclared
criterion MET as a roadmap and dispatch
specification, with the gate and benchmark items
satisfied per family exactly where a machine
exists. Not integrated; no gap-model change.
Full record: phase6b/EXP028_CPU_ARCHITECTURES.md;
artifacts in phase6b/benchmarks/exp028/.

## EXP-029 record (closed 2026-11-15)

Source state: local tree at Assignment A baseline;
production files verified byte-identical at close.
Implementation (research tree only):
benchmarks/exp029_allocator.py, a coordinator-side
range allocator over one declared nonce range per
template: tiled chunk partition (tiling invariant
asserted), exclusive pull leases, cumulative
progress, idempotent completion keyed by chunk,
fail_worker requeue with examined_before accounting,
work stealing by shrink-before-grant tail split,
JSON snapshot/restore with lease drop, heartbeat
and stale detection, and an accounting() report
carrying the standing separations (unique coverage,
actual, repeated, verification, candidate
submissions; the last two structurally 0 at this
layer). Coverage proof (record allocator_tests_
20261115T061200Z.json): targeted cases exact
(duplicate delivery leaves unique at 4 with the
duplicate counted; death after 5 of 8 reported gives
repeated exactly 5 and actual 13 on completion;
steal preserves the partition invariant and exact
64 coverage; restart at 3 reported gives repeated
exactly 3 on re-lease; stale detection exact;
range ending at 2^32 exact) plus a randomised
campaign of 120 trials (random starts, counts 1 to
2000, chunks 3 to 777, 1 to 8 workers, death,
duplicate, steal and restart injections) in which
every trial's completed intervals union exactly to
the declared range, pairwise disjoint, with 20,474
repeated computations across 67 trials all
accounted and none inside unique coverage.
Coordination overhead (record overhead_20261115
T061203Z.json), LOCAL IN-PROCESS PROTOTYPE ONLY on
this host (AMD EPYC 9D25 guest, about 1.5 effective
CPUs, live miner and node running), 120,000 hashlib
full-scan nonces: 1 worker 460,929 unique/s
(efficiency 1.000), 2 workers 477,355 (0.518),
4 workers chunk 10,000 493,484 (0.268), 4 workers
chunk 1,000 401,237 (0.218). Aggregate unique
coverage rose monotonically; finer chunks cost
measurable throughput; the efficiency figures
mostly price thread contention on this oversubscribed
guest and are not distributed-system results.
Multi-machine overhead, propagation latency and
linear scaling are UNVERIFIED and carry no numbers.
End-to-end gate: the distributed path (allocator
plus 2 worker threads, each a production
ComputeEngine requested="c", production
MiningEngine building and submitting) mined a fresh
regtest block accepted by Core, height 829, hash
781cc4ef7fc3e583ff6fa9bf277c780083b7252a9d5ede4fed5d213e691a2e8f,
nonce 2048 (record regtest_20261115T061212Z.json);
the winning batch's allocator record shows unique
coverage 65,536 of 65,536, repeated 0, complete.
Known limitation filed in the experiment document:
the allocator's complete() credits actual with the
full chunk size, an upper bound for hit-stopped
chunks; engine-level attempted is exact; unique
coverage is unaffected. Centralised versus
decentralised comparison filed (experiment file
section 8): centralised chosen on coverage safety
(disjointness by construction, one-hop propagation,
idempotent recovery), decentralised considered and
not chosen for the partition-divergence coverage
risk. Decision: criteria 1, 3 and 4 met; criterion
2 met at the largest configuration actually run
with larger configurations UNVERIFIED by rule; the
hypothesis's linear-scaling clause is UNVERIFIED
beyond this host. No claim toward 500 GH/s or
140 TH/s; gap model unchanged. Not integrated.
Full record: phase6b/EXP029_DISTRIBUTED_EXECUTION
.md; artifacts in phase6b/benchmarks/exp029/.
Thirty experiment IDs now recorded (EXP-000 to
EXP-029 plus EXP-024b); next unreserved ID stays
EXP-030.

## Gap model update pointer (Assignment G, 2026-11-15)

PERFORMANCE_GAP_MODEL.md section 5 (update dated
2026-11-15) recomputes the gap model from the
EXP-024 to EXP-029 records above. Headline: current
production basis unchanged (about 44,900 live-system
equivalents and 25,000 model planning cores for
500 GH/s; nothing from Phase 6B is integrated), plus
a clearly labelled derived DualMask scenario (about
26,100 equivalents and about 14,550 planning cores
for 500 GH/s, projection from the EXP-026 kernel
scope ratio 1.718x, not a system measurement).

## DualMask integration and audit record (closed 2026-11-15)

This record supersedes the "not integrated" status
in the EXP-026 record above and in the Assignment G
pointer (both written before the integration).

Integration: EXP-026 candidate C2 (DualMask)
integrated as production backend "v512dual" on the
owner's explicit decision of 2026-11-14, after
EXP-024b completed. Full record:
PRODUCTION_INTEGRATION_LOG.md Entry 1. Kernel
mining/cpu/bal_avx512_dual.c (byte-identical to the
research source after the documented renames);
dispatch CUDA, v512dual, v512, C; restricted build
flags -O3 -mavx512f -mavx512bw. Gates through the
production path: 197,616 differentials vs hashlib,
0 mismatches; candidate-set equivalence exact;
accounting parity exact; forced fallback three ways
lands on v512; suite 23 of 24 (only test-rtl fails,
on absent iverilog, pre-existing); fresh regtest
blocks accepted at heights 830 and 877. Deployment:
first pool-accepted share on v512dual at
2026-11-15T06:57:29Z; live session rates observed
20.6 to 21.5 MH/s (measured observations under
contention, not benchmarks); 205 accepted shares at
audit time.

Post-integration audit:
DUALMASK_POST_INTEGRATION_AUDIT.md, verdict PASS
WITH NOTES, zero defects (notes N-1 to N-3,
cosmetic and observational). The auditor's own
verification included 121,400 fresh differentials
(0 mismatches), an independent accounting
simulation, four forced-fallback constructions, and
a fresh regtest block accepted at height 910 (a
further block at 911 in the suite run).

Gap model consequence: PERFORMANCE_GAP_MODEL.md
section 6 (post-integration note, Assignment H)
recomputes the observation-based equivalents on the
v512dual live rates: about 24,000 live-system
equivalents for 500 GH/s at 20.6 MH/s observed
(24,272 by the arithmetic shown there). Planning
cores unchanged (theoretical band). EXP-024b's
design C remains verified but not integrated;
DualMask, which contains the mask compare, is the
integrated form.

Phase 6B close: PHASE6B_FINAL_REPORT.md
(Assignment H) carries the phase verdicts, the two
owner decisions still open (EXP-025 repaired cache
integration; EXP-022 flags batch shape adoption),
and the push record.
