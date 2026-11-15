# EXP-026: Extreme AVX-512 Execution Research

Experiment ID: EXP-026 (reserved 2026-11-14, Phase 6B).
Status: COMPLETE (executed 2026-11-15; record appended at the end of this file under "Experiment record").
Track: A (near-term engineering).
Depends on: EXP-024's measured result (its mask and
extraction costs are design inputs here).

## Predeclared hypothesis

A combined AVX-512 execution design, chosen from a
written cost model before it is built (register
budget, spill census, data-movement census, dependency
chains), can beat the production single-batch kernel
(bal_v_search2 / bal_v_batch2) under the EXP-017 rule.
The combination space is: EXP-018's register-resident
dual-batch structure, EXP-020's single-ternlog
Boolean forms, EXP-022's flags comparison, EXP-024's
mask search and extraction strategy, alternative state
layouts and schedule-ring representations, and
instruction scheduling against execution-port balance.

Negative knowledge carried in, binding on the design:
EXP-018 achieved residency and gained nothing
significant (state traffic was not the binding cost);
EXP-020 proved a one-op census gain that was
rate-neutral; EXP-006 showed spill reduction can be
exactly repaid by store/load traffic. A combination
is therefore not assumed faster for being a
combination: each candidate design must state, before
it is built, which measured cost it removes and what
it adds.

## Predeclared success criterion

1. A written cost model per candidate design exists
   before the design is compiled (instruction census,
   register estimate from live ranges, spill estimate,
   data-movement census, critical path), in the style
   of phase6/COMPUTATION_GRAPH_RESEARCH.md section 4.
2. Any design whose cost model requires more live
   vector registers than the architecture provides
   (32 zmm) carries its quantified spill cost in the
   model; a design that wins on arithmetic and loses
   on data movement is recorded as such, not tuned
   silently.
3. Correctness gates identical in kind to EXP-024's
   (differentials, candidate-set equivalence,
   boundaries, exact accounting, genesis, sanitizers
   where available) pass before timing.
4. Performance under the EXP-017 protocol: at least
   3 sessions, paired blocks, randomised order,
   equal-pair controls null, adjusted CI entirely
   above 0 in every session and pooled, against
   production and against the strongest single
   ingredient (so a combination must beat its best
   part, not only the baseline).
5. Machine-code evidence for every timed design:
   hot-function instruction count, frame size,
   stack-op census, intended-primitive presence,
   compiled with the recorded flags on the recorded
   host.

## Gates

Cost model filed; correctness gates as above;
assembly audit filed; benchmark protocol as above;
fresh regtest block before any integration proposal.
Integration is a separate owner decision under the
master plan section 6.

## Scope notes

Exploration list from the directive (section 6):
multiple independent vector batches; register-resident
state; alternative state layouts; schedule-ring
representations; candidate-mask fusion; digest
materialisation reduction; instruction scheduling;
execution-port balance; register pressure; spill
elimination; data movement; load/store pressure;
cache behaviour; vector-to-scalar extraction;
instruction dependency chains; compiler-generated
code; hand-scheduled assembly when the cost model
justifies it.

## Cost model (filed 2026-11-15, before any candidate is compiled)

Host of record: AMD EPYC 9D25 126-Core Processor, guest
4 vCPUs, about 1.5 effective shared CPUs, AVX-512F and
AVX-512BW present (also DQ, VL, VBMI, VBMI2, IFMA, GFNI,
SHA-NI on this host; no candidate may require more than
AVX-512F plus AVX-512BW). All builds use the restricted
flag set -O3 -mavx512f -mavx512bw, never -march=native.

Reference costs, measured by earlier experiments and
used as the model's inputs (not re-derived here):
- Production single-batch round: 29 vector ops per
  steady-state round as emitted; the EXP-020 vocabulary
  optimum is 28; the difference is Maj emitted as two
  chained ternlogs instead of one 0xE8 ternlog.
- EXP-012 proved gcc already applies VPTERNLOGD to the
  classic cones where it can: both the production base
  library and the EXP-024 mask library carry exactly 7
  vpternlog instructions in objdump today.
- EXP-024 mask group (vm_group): 576 instructions, 15
  opmask-writing vpcmp instructions, zero digest stores
  on a miss group, 8 zmm digest staging stores behind a
  kortestw guard. Production v_walk: 3,948 instructions
  (v_group inlined), zero vpcmp, scalar byte compare per
  lane, unconditional staging.
- EXP-018 dual compress (v_compress16x2_reg): 1,014
  instructions, frame 2,368 bytes, 90 zmm stack
  instructions (80 of them the two schedule rings at
  stack offsets 0x100 and 0x500, 10 spill-region ops).
  Its measured rate effect was pooled 1.087x, CI
  crossing zero: residency alone bought nothing
  significant.
- EXP-024 search verdicts: mask B pooled 1.169x vs
  production (primary criterion not met), mask C pooled
  1.416x vs production with per-session significance
  but not attributable to its design difference at
  density 0. Same-code control bound: about 8 percent
  layout and scheduling bias on this host class.

### Candidate C1: TernMask (mask C plus explicit ternlog cones)

Design: the EXP-024 mask kernel's v_compress16 with
every Boolean cone written explicitly as VPTERNLOGD:
Ch as 0xCA, Maj as a single 0xE8, and the four XOR3
sigma forms (schedule s0, s1, round S0, S1) as 0x96.
Search form is mask C (opmask compare, lowest-lane
extraction only).
- Measured cost it removes: at most the one-op Maj
  chain difference (29 to 28 ops per round, about
  3.4 percent of round census, 64 rounds times 3
  compressions per group but only block-2 and outer
  compressions are vector; block 1 is scalar). It also
  removes reliance on the compiler rediscovering the
  cones in this translation unit: the mask library
  today carries only 7 vpternlog instructions total,
  so the cones in v_compress16 are mostly NOT in
  ternlog form as compiled (the 7 sit in the scalar
  and flags paths). Upper bound if every cone
  collapses: Ch 2 ops to 1, Maj 3 ops to 1, each XOR3
  2 ops to 1, saving 5 ops per round of about 29,
  about 17 percent census, before port effects.
- Cost it adds: none in registers (ternlog is
  three-input, one-output, same live ranges). Risk,
  quantified in the model: VPTERNLOGD is a port-5-only
  instruction on several Intel cores and competes with
  shuffle traffic there; on this AMD host it dual
  issues more freely. The benchmark, not the model,
  decides.
- Register estimate: identical to mask C: 8 state,
  16 schedule ring (stack array, compiler managed),
  about 6 round temporaries live at once. Under 32
  zmm; no modelled spill change.
- Critical path: Maj chain shortens by one ternlog
  latency (about 1 cycle) per round on the T2 path;
  the a/e recurrence remains the binding chain.

### Candidate C2: DualMask (dual-batch residency plus mask compare)

Design: the EXP-018 register-resident dual-batch
kernel (explicit ternlog cones already in its source,
ring-relabeled state, two 16-lane batches per group
step) with the EXP-024 opmask lexicographic compare
applied to each batch's final state, digest staging
only for a batch whose mask is nonzero, extraction of
the lowest flagged lane of the first hit batch.
- Measured cost it removes: for a miss dual-group,
  all digest staging (2 batches times 8 zmm stores
  plus the scalar per-byte extraction loop over up to
  32 digests in the EXP-018 search walker) and all
  scalar v_meets compares. EXP-024 priced this removal
  on the single batch at a pooled 1.169x to 1.416x.
- Cost it adds: two compare chains per dual group
  (2 times 8 word compares, about 16 vpcmp plus mask
  ops, against one chain per 16 lanes in C1, so the
  per-lane compare cost is unchanged); early-exit
  granularity coarsens from 16 to 32 nonces (at the
  primary density 0 this costs nothing; at hit density
  about 2^-12 it wastes at most 16 extra computed
  nonces per hit, about 0.4 percent of a 65,536 block
  at the median hit position); the dual compress's
  measured stack traffic stands (90 zmm stack ops per
  dual group in the EXP-018 audit, of which 80 are
  schedule-ring traffic, about 1.25 stack ops per
  round per batch, comparable per lane to the single
  batch's stack schedule ring).
- Register estimate: 16 state vectors live across the
  dual compress by construction, plus about 8 round
  temporaries and 2 compare temporaries: about 26
  live zmm peak, inside the 32 register file; the
  EXP-018 audit's 10 spill-region zmm ops are the
  quantified spill cost, already inside its measured
  rate.
- Critical path: the two batches are independent
  chains; the recurrence per batch is unchanged, but
  the scheduler sees two independent a/e chains, which
  is the one structural latency advantage over C1.

### Candidate C3: register schedule ring, single batch. KILLED at the model.

Keeping W[16] as named registers costs 16 zmm plus 8
state plus at least 6 round temporaries plus compare
temporaries: 30 to 32 live before the schedule
expansion's own inputs (W[t-15], W[t-2] are ring
members, but s0/s1 outputs and the K+W add need 3
more). Peak exceeds 32 zmm, so at least 2 to 4 values
spill per round across 48 expanded rounds times 2
vector compressions: at least 192 extra zmm store/load
pairs per group against a modelled saving of the
stack schedule traffic the compiler already keeps in
L1 at about 1 cycle. EXP-006's lesson applies exactly:
spill reduction repaid by store/load traffic. Killed.

### Candidate C4: phase pipelining and two-group software pipelining. KILLED.

EXP-008 measured phase pipelining at parity. A
two-group software pipeline without dual residency is
C2 with worse register behaviour; with residency it
is C2. Subsumed, not built separately.

### Candidate C5: hand-scheduled assembly for port balance. KILLED as a standalone.

The out-of-order window on this core class already
reorders across the round boundary; EXP-006 hand
scheduling was negative. No modelled cost it removes
that C1 and C2 do not. Recorded, not built.

### Decision

Build C1 and C2. Each must beat production AND its
strongest single ingredient: for C1 the ingredient is
mask C; for C2 the ingredients are mask C (compare)
and the EXP-018 dual kernel (structure), and the
binding ingredient comparison is mask C. Equal-pair
controls must return null.

## Experiment record (2026-11-15)

Executed 2026-11-15, about 05:24 to 05:38 UTC, on AMD
EPYC 9D25 126-Core Processor (guest 4 vCPUs, about 1.5
effective shared CPUs; AVX-512F/BW present). Both
candidate libraries built with -O3 -mavx512f
-mavx512bw, never -march=native. The live mainnet
miner and node ran throughout and were not altered
(heartbeat at close: autopilot pid 2394, miner pid
2397, shares_accepted_total 195). Production files
byte-identical to their pre-experiment sha256
snapshots, verified at close. Status: COMPLETE.

### Implementations

- C1 TernMask: research source
  extreme_optimization/src/avx512_mb_exp026_tern.c,
  built as libbal_e26t.so. The EXP-024 mask kernel
  with every Boolean cone in v_compress16 written
  explicitly as VPTERNLOGD (Ch 0xCA, Maj single 0xE8,
  XOR3 sigma forms 0x96); search form is mask C
  (bal_v_e26t_search2), batch form bal_v_e26t_batch2.
- C2 DualMask: research source
  extreme_optimization/src/avx512_mb_exp026_dual.c,
  built as libbal_e26d.so. The EXP-018
  register-resident dual-batch kernel, compress
  unchanged, plus a new walker (bal_v_e26d_search2):
  per dual group, each batch's final state is
  compared with the EXP-024 opmask lexicographic
  compare; digest staging only for a batch whose
  mask is nonzero, and only its lowest flagged lane
  is extracted. Early exit is dual-atomic (32 lanes);
  a span tail under 17 nonces uses the original
  single-group path. One transcription defect was
  caught by the gates before timing (the outer
  block length word of batch A written as 640
  instead of 256 in the new group function) and
  fixed; the gate record before the fix is preserved
  (gates_20261115T052511Z.json) as evidence the gates
  bind.
- Killed at the cost model: C3 (register schedule
  ring, quantified spill), C4 (phase pipelining,
  EXP-008 parity, subsumed by C2), C5 (hand-scheduled
  assembly, EXP-006 negative). See the cost model
  section above.

### Gates (all before timing; all PASS)

Driver: phase6b/benchmarks/exp026_gates.py; passing
record: benchmarks/exp026/gates_20261115T052557Z.json.
G1 batch differentials: C1 155,061 nonces and C2
161,531 nonces byte-identical to hashlib and to the
production batch. G2 candidate-set equivalence over
40 spans at densities 0, about 2^-16, 2^-8 and 1
(exact recount minimum at 1 thread; true member at 2
and 3 threads) for both candidates. G3 target
boundaries exact. G4 14 nonce-boundary spans exact,
including ranges ending at 2^32. G5 exact accounting
(C1 production wave rule; C2 dual-atomic rule
simulated independently), miss and hit shapes. G6
genesis nonce 2083236893 re-found by both. G7
invalid arguments return -1 and -2 as production.
G8 lowest lane of a full group. Sanitizers:
exp026_san_driver.c built per kernel under
ASan/UBSan (-fno-sanitize-recover=all) prints
SAN_DRIVER_OK for both kernels (leak detection
disabled in this environment, which blocks
LeakSanitizer under ptrace; ASan and UBSan proper
were active and clean).

### Machine-code evidence

Audit: phase6b/benchmarks/exp026_asm_audit.py;
record: benchmarks/exp026/asm_audit_20261115T053022Z.json.
C1 v_compress16 standalone: 131 instructions, 6
vpternlog; whole library 6 vpternlog, 30 vpcmp. The
mask library's v_compress16: 133 instructions, 7
vpternlog; whole library 7 vpternlog, 30 vpcmp. In
the inlined vm_group both libraries measure 576
instructions with the same staging census: the
explicit ternlog source form did NOT survive as a
distinct codegen advantage in the search path, which
is consistent with the benchmark outcome below.
C2 v_compress16x2_reg: 1,085 instructions, 96
vpternlog (the EXP-018 source's explicit cones do
survive in the dual compress), frame 2,304 bytes;
whole library 103 vpternlog, 30 vpcmp (the new
compare). Production base library: 7 vpternlog, 0
vpcmp.

### Benchmarks (EXP-017 protocol, measured)

21 sessions, 120 pairs plus 8 warmup pairs each,
65,536-hash blocks, randomised AB/BA, density 0
(mainnet-like), rate = attempted / elapsed. Raw
sessions: benchmarks/exp026/session_*.json.
Analysis: exp026_analyze_incremental.py importing
the EXP-017 statistic unchanged; records
benchmarks/exp026/analysis_inc_*.json. Only paired
ratios carry verdicts; absolute medians varied with
host contention, as recorded per session.

C2 DualMask vs production search, 2 threads:
significant in every session and pooled.

| session | prod median H/s | dual median H/s | adjusted log-ratio [95% CI] | sig |
|---|---|---|---|---|
| 052838 | 8,550,578 | 15,230,852 | +0.690 [+0.464, +0.917] | yes |
| 052843 | 8,159,530 | 14,012,011 | +0.531 [+0.300, +0.760] | yes |
| 052847 | 9,481,644 | 14,856,203 | +0.402 [+0.181, +0.615] | yes |
| pooled | | | +0.541, ratio 1.718x [1.511, 1.955], pairs won 78.9% | yes |

C2 DualMask vs mask C (its strongest single
ingredient), 2 threads: significant in every
session and pooled.

| session | mask C median H/s | dual median H/s | adjusted log-ratio [95% CI] | sig |
|---|---|---|---|---|
| 052851 | 13,252,517 | 17,857,881 | +0.263 [+0.053, +0.473] | yes |
| 052857 | 8,725,192 | 13,137,776 | +0.505 [+0.307, +0.677] | yes |
| 052903 | 8,899,926 | 13,047,192 | +0.354 [+0.136, +0.572] | yes |
| pooled | | | +0.367, ratio 1.444x [1.288, 1.618], pairs won 74.2% | yes |

C2 vs production, 1 thread: pooled 1.967x [1.742,
2.216], significant in every session (+0.658,
+0.782, +0.582), pairs won 80.0%.

C1 TernMask vs production, 2 threads: pooled 1.083x
[0.942, 1.238], no session significant. C1 vs
production, 1 thread: pooled 1.174x [1.037, 1.330],
significant in 2 of 3 sessions. C1 vs mask C,
2 threads: pooled 0.764x [0.677, 0.859], pairs won
34.2%: the combination is SLOWER than its own
strongest ingredient, decisively in two sessions
and pooled.

Equal-pair control, mask C vs mask C, 2 threads:
pooled 0.992x [0.871, 1.134], no session
significant: null, as the protocol requires.

### Fresh regtest gate (PASS)

Driver: phase6b/benchmarks/exp026_regtest.py; record:
benchmarks/exp026/regtest_20261115T053746Z.json. The
harness binds each candidate into the production
block-building path through a research shim exposing
the counted-search interface (production
mining/engine.py MiningEngine builds and submits;
the shim re-verifies every candidate with hashlib,
fail-closed; the production ComputeEngine is not the
search backend in this harness).
- C2 DualMask block: height 827, hash
  3bee3dae4d9d8b0c99c38cc6130cc75f5e517491be59fec68c7e31d5128e6c49,
  nonce 50000, accepted.
- C1 TernMask block: height 828, hash
  6b0822ef4f6874a2a1aa74ea0c18a0b1b0616b1fed61d3009be624e6604e9589,
  nonce 2, accepted.

### Verdicts

- C2 DualMask: VERIFIED IMPROVEMENT (search scope,
  density 0). It meets the predeclared criterion in
  full: cost model filed first, gates passed before
  timing, adjusted CI entirely above 0 in every
  session and pooled against production (1.718x at
  2 threads, 1.967x at 1 thread) AND against its
  strongest single ingredient, mask C (1.444x at
  2 threads), control null, regtest block accepted.
  Why it works, per the evidence: EXP-018's
  residency alone was rate-neutral and EXP-024's
  mask compare alone was promising but uncertified;
  the combination removes BOTH the digest
  materialisation of 32 lanes per dual group and
  the latency exposure of a single dependency chain
  (two independent a/e chains interleave). It is
  eligible to propose integration to the owner
  under the master plan section 6 gates. It is NOT
  integrated by this experiment.
- C1 TernMask: ESTABLISHED NEGATIVE as a
  combination. It does not beat production
  significantly at 2 threads and is significantly
  slower than its own ingredient (mask C, pooled
  0.764x). The explicit ternlog cones change census
  on paper and nothing useful in the emitted search
  code. Retired; the compiler's own cone selection
  in the mask kernel stands.
- C3, C4, C5: killed at the cost model, recorded
  above; no code built, no claim made.

Effect on PERFORMANCE_GAP_MODEL.md: the model's
production baseline is unchanged (nothing is
integrated), but Assignment G should record C2 as a
verified research result: at the session medians
observed, a DualMask search core sustains roughly
13 to 18M H/s per worker thread pair under live
contention on this host class. The mission targets
stand at full height: 500 GH/s minimum objective,
140 TH/s larger objective. A 1.72x search increment
on a system of this size does not move those
targets materially and is reported as an
intermediate result, not as progress claimed
against them beyond its measured ratio.

### Files

Created: extreme_optimization/src/
avx512_mb_exp026_tern.c, avx512_mb_exp026_dual.c,
libbal_e26t.so, libbal_e26d.so;
phase6b/benchmarks/exp026_gates.py,
exp026_san_driver.c, exp026_paired_bench.py,
exp026_analyze_incremental.py, exp026_asm_audit.py,
exp026_regtest.py; records under
phase6b/benchmarks/exp026/ (21 session files, 2
gates records including the preserved pre-fix
failure, 1 asm audit, 7 analysis records, 1 regtest
record). No production file was modified.
