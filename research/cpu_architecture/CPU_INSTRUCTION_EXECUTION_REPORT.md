# CPU Instruction Execution Report

Deliverable: CPU_INSTRUCTION_EXECUTION_REPORT.md (Master
Assignment BR-008, CPU execution and compiler).
Date: 2026-11-15. Status: specification and status document.
No benchmark was run for this report. Every figure below is a
completed measurement cited to its experiment, its session
conditions and its host. Rates are host-bound: a figure
without its host is not a figure in this programme.

Hosts of record. Two guest hosts carry all measurements in
this report:

- AMD EPYC 9D25 (guest, hostname htch-runtime): AVX-512F,
  DQ, CD, BW, VL, VBMI, VBMI2, IFMA, VNNI, BF16, BITALG,
  VPOPCNTDQ, VP2INTERSECT, plus AVX2, SHA-NI, GFNI, VAES,
  BMI2, ADX (EXP-031 profile, /proc/cpuinfo flags).
- Intel Xeon Platinum 8321HC (guest): AVX-512F, BW, VL,
  VNNI. No SHA extensions, no VBMI (EXP-028 record).

The VM alternates between these hosts across replacements.
Production kernels are built with the restricted flag set
-mavx512f -mavx512bw, never -march=native, and re-probe via
CPUID at load, so the same binaries run on both (section 7).

## 1. The unit of execution: one SHA-256 round

SHA-256d mining executes, per candidate, three 64-round
compressions minus the reusable prefix: the first pass over
the 80-byte header is two chunks, of which the first chunk
is nonce-independent for a fixed template; the second pass
over the 32-byte inner digest is one chunk with zero reuse.
The conventional accounting is 64 + 3 = 67 of 192 rounds
reusable per template; the remaining 125 rounds per
candidate are the irreducible per-candidate work in the
conventional implementation. That accounting is a
conventional remainder, not a proven universal lower bound
(EXP-033 restatement).

Everything in this report is about how those 125 rounds are
executed on a modern CPU: what one round costs in vector
instructions, how many candidates are in flight at once, and
which instruction forms carry the work.

## 2. Instruction-level structure of the round (EXP-020)

EXP-020 ran two automated searches (e-graph equality
saturation and SMT-guided superoptimisation) over the joint
cone of one full round plus the schedule cone that feeds it,
in the vocabulary {VPADDD, VPTERNLOGD, classic bitwise,
VPROLD, VPSRLD}, with equivalence proven by z3 UNSAT on all
three outputs jointly behind a 1,000,000-sample differential
filter.

Findings:

- The joint round-plus-schedule cost is optimal at 28
  vector operations per steady-state round within the
  searched vocabulary. The assembled lower bound is:
  12 offset-producing ops (each of the four sigmas depends
  on exactly three distinct nonzero offsets of one variable,
  so each sigma needs at least 3 offset ops), plus 4 sigma
  combining ops, plus at least 1 ternlog each for Ch and
  Maj, plus at least 10 adds (7 for the (a', e') output pair
  by an exhaustive addition-network counting proof, 3 for
  the schedule sum). 12 + 4 + 2 + 10 = 28, and the extracted
  form achieves 28, so it is optimal in that vocabulary.
- Each sigma individually costs at least 4 ops (3 rotations
  plus 1 XOR3 combine), and the four sigmas cost at least 16
  together. These minima were later proven exactly by
  EXP-033 as well.
- No nontrivial subexpression is shared between any two of
  S1, Ch, S0, Maj, s0, s1. The only sharing in the joint
  cone is T1 between the a' and e' outputs, already present
  in the incumbent.
- Addition networks: the T1 five-operand sum needs a
  minimum of 4 adds, the schedule four-operand sum a
  minimum of 3 adds; carry-save forms price above both
  (section 6).

Production emits 29, not 28. The mechanically audited
census of the production round body (v_compress16 in
mining/cpu/bal_avx512_mb.c, gcc -O3 with the restricted
flags) is 29 arithmetic ops per steady-state round:
10 vprold/vprord, 2 vpsrld, 7 vpternlogd, 10 vpaddd. Gcc
already folds every sigma XOR triple into a single ternlog
(immediate 0x96, four times) and Ch into one ternlog
(0xE4), and already adds S1 last in T1. The single gap is
Maj: gcc emits two chained VPTERNLOGD (immediates 0x60 then
0x78) where the proven form is one VPTERNLOGD (immediate
0xE8). That is a compiler codegen gap, not a graph
discovery: the graph search found nothing the compiler had
missed except this one op.

The one-op candidate (P6C-007, Maj as a single ternlog,
emitted census 28) passed the full gate set (108,000
randomized differentials against hashlib, zero mismatches;
genesis, boundary, accounting and regtest candidate-set
gates all pass) and was benchmarked under the EXP-017
protocol: pooled ratio 1.051x, CI [0.935, 1.182], positive
point estimate in all three sessions but not significant in
any session or pooled. Under the adopted decision rule it
is NOT a verified improvement and it is NOT integrated.
The 29 versus 28 gap is therefore a known, bounded,
unclaimed residual: at most one op in 29 of round cost,
inside measurement noise on this VM.

## 3. Data parallelism: the multi-buffer form

The round's dependency chain is serial within one
candidate: T1 depends on e, f, g, h and the round's W and
K; the critical path runs through the S1 chain into T1 and
into the next round's e. Nothing reorders this within one
hash. The modern answer is width, not depth: many
candidates' chains interleaved so the pipeline stays full.

Production form (v512, mining/cpu/bal_avx512_mb.c): one
zmm register holds one state word for 16 independent
candidates (16-lane multi-buffer). Each vector op of the
section 2 census advances all 16 candidates by one round
step. The message schedule is computed in-vector from the
16-word ring; rotations are single VPROLD instructions
(AVX2 needs 3 ops for the same rotation: shift pair plus
OR, which is the structural reason the AVX2 kernel trails
per core, section 5).

DualMask form (v512dual, mining/cpu/bal_avx512_dual.c,
EXP-026 candidate C2): two 16-lane batches are kept
register-resident together (dual-batch residency), and the
target comparison is performed in the opmask domain inside
the kernel, extracting candidates only for groups whose
mask is nonzero. The audited compress function
(v_compress16x2_reg) is 1,085 instructions. EXP-017
verdicts, AMD EPYC 9D25 host, search scope:

- C2 DualMask vs production v512 search, 2 threads: pooled
  1.718x, CI [1.511, 1.955], pairs won 78.9 percent,
  significant in every session and pooled. VERIFIED
  IMPROVEMENT, integrated as backend v512dual.
- C2 DualMask vs its strongest single ingredient (mask
  compare alone, EXP-024b design C): pooled 1.444x,
  CI [1.288, 1.618]. VERIFIED.
- C2 at 1 thread: pooled 1.967x. VERIFIED.
- C1 TernMask: ESTABLISHED NEGATIVE. C3, C4, C5 were killed
  at the cost model before benchmarking.

Mask search lineage, for the record: EXP-024's predeclared
primary design B failed its criterion (pooled 1.169x, only
1 of 3 sessions significant); design E (span scan) is an
ESTABLISHED NEGATIVE for search (about 6.16x slower);
EXP-024b design C (single-batch mask search) is VERIFIED
at pooled 1.398x, CI [1.242, 1.578], in search scope, and
exists only in research code. It is not dispatched in
production; the production fallback chain is v512dual,
v512, C, hashlib (NOVA repository audit, section 5).

Live consequence, stated as observation and not as a
benchmark: after the DualMask integration, live miner
session rates of 20.6 to 21.5M H/s were observed on the
AMD host (single live sessions under contention; Phase 6B
final report). The pre-integration live observation basis
was 11.15M H/s.

## 4. The SHA-NI form: latency-bound chains and streams

SHA-NI provides dedicated round instructions
(SHA256RNDS2, two rounds per instruction including its own
Ch and Maj) and dedicated schedule instructions
(SHA256MSG1, SHA256MSG2). Two facts govern this form:

1. A single nonce chain is latency-bound. SHA256RNDS2
   forms a serial dependency chain; one chain cannot fill
   the core. The Stage 5 measurement note records the
   evidence: if RNDS2 were throughput-bound, interleaving
   independent chains could not have produced the measured
   gains. The binding constraint is single-chain latency
   plus this guest's scheduling noise.
2. The schedule machinery is worth more than the round
   instructions. EXP-002 measured the MSG1/MSG2 schedule
   alone at about 2.6x over a scalar schedule at equal
   rounds, same-session medians. EXP-032 confirmed the
   point from the other side (below).

H-02 is the direct SHA-NI kernel with the schedule built
entirely from SHA256MSG1/MSG2. H-01 interleaves NS
independent nonce streams (1, 2 or 4) in lockstep inside
one worker so the RNDS2 latency chains overlap. Measured
standing:

- EXP-003: H-01 at streams 4, per-worker 1-thread median
  3.30M H/s, AMD EPYC 9D25 guest. EXP-005: streams 4
  strided, 2-thread median 3.47M H/s, same host class.
- EXP-017 decision set: streams 4 strided vs production
  pooled 2.80x, CI [2.53, 3.09]. VERIFIED (batch scope).
- EXP-032 (AMD host, 2 threads, EXP-017 protocol):
  H-01 streams-4 batch vs production C batch pooled
  2.861x, CI [2.671, 3.089], significant in every session.
  VERIFIED IMPROVEMENT, batch scope. Against the v512dual
  batch it reaches 0.726x, CI [0.672, 0.783]; in search
  scope against the dual search, 0.349x, CI [0.315,
  0.385]. The batch-to-search drop is structural: the dual
  search compares in opmask and extracts only on a hit
  group, while the H-01 search materialises each wave's
  digests and compares scalar.
- EXP-021: head to head on the AMD guest, the homogeneous
  multi-buffer pool beats the SHA-NI pool (pooled 1.363x
  at 2 threads, 1.329x at 4 threads), and heterogeneous
  pairing of the two families is an ESTABLISHED NEGATIVE.
  This is why SHA-NI sits below AVX-512 MB in the dispatch
  order wherever both exist.

The negative that defines the form's boundary: the
production translation unit mining/cpu/bal_sha_intrin.c
(single stream, scalar schedule, snapshot after round 1)
measured pooled 0.517x, CI [0.497, 0.536], of the
production C batch in EXP-032: ESTABLISHED NEGATIVE as a
batch backend. The C batch it loses to runs OpenSSL's
SHA256_Transform, which on this CPU is itself SHA-NI code
with the MSG schedule. The difference between the two
SHA-NI kernels is the schedule machinery and the snapshot
depth, not the round instructions. ComputeEngine does not
dispatch bal_sha_intrin.c at all (NOVA audit, section 1).

Register picture for H-01 at streams 4 (EXP-032): 4 stream
states (8 xmm) plus 4 message vectors (4 xmm) live. Streams
beyond 4 are not part of the H-01 design and were not
attempted.

## 5. The AVX2 form (EXP-032)

EXP-032 built an 8-lane AVX2 multi-buffer kernel
(research/sha256d/exp032/src/avx2_mb.c), a lane-width port
of the production AVX-512 kernel with its structure,
template handling and accounting preserved, built with
-mavx2 only. Correctness: 274,925 batch digests
byte-identical against hashlib within the experiment's
1,358,210 total digest verifications, zero mismatches.

Verdicts (AMD host, 2 threads, EXP-017 protocol):

- AVX2 MB batch vs production C batch: pooled 1.409x,
  CI [1.340, 1.480], significant in every session.
  VERIFIED IMPROVEMENT, batch scope.
- AVX2 MB batch vs v512dual batch: 0.371x, CI [0.340,
  0.403]. AVX2 search vs v512dual search: 0.134x,
  CI [0.122, 0.147]. On an AVX-512 host it is not
  competitive; its value is portability to AVX2-only
  hosts.
- Structural cost: AVX2 rotations expand to shift pairs
  plus OR (3 ops where VPROLD spends 1), and the lane
  width is 8 against 16. Register pressure: 8 state
  vectors and 16 schedule vectors in 16 ymm registers;
  the compiler spills schedule vectors to the stack ring
  by design (the W[16] ring is stack-resident, as in the
  AVX-512 original).
- Host caveat, stated in the EXP-032 report and binding
  here: rates on a genuinely AVX2-only host are
  UNVERIFIED. This host's AVX2 units are Zen 4 units that
  also execute AVX-512; per-core AVX2 throughput on a
  part without AVX-512 may differ. Correctness is
  host-independent; the ratio is this host's.

## 6. Port, latency and representation reasoning (EXP-027, EXP-032)

This VM exposes no hardware performance counters
(perf_event_paranoid 4; perf_event_open returns EPERM even
as uid 0; EXP-031). No IPC, cycle or cache-miss claim is
therefore made anywhere in this programme. Port and
latency reasoning rests on three evidence kinds: op-count
censuses of compiled code (EXP-020), latency-chain
structure (the round's serial dependency, section 3), and
paired wall-clock measurement under the EXP-017 protocol.
Within those limits, EXP-027 closed the representation
spaces outside the EXP-020 vocabulary, each at its stated
scope:

- GFNI affine forms: the four sigma maps are GF(2)-linear
  (proven), but every Sigma0 output byte depends on all
  four input bytes, flooring any GFNI network at 11 ops
  against the incumbent 4. Ch and Maj are proven
  non-affine by counterexample. ESTABLISHED NEGATIVE.
- VPSHUFB rotations: the pure form is refuted
  exhaustively; the mixed form measured at 2.00x the
  VPROLD price. ESTABLISHED NEGATIVE.
- Rotated or byte-swapped state domains: refuted, because
  carries propagate along the unrotated bit positions and
  every addition forces a de-rotation and re-rotation.
  ESTABLISHED NEGATIVE.
- Carry-save beyond the schedule: every round addition has
  deferral distance exactly 0 (each sum is consumed by a
  nonlinear operation in the same round), so carry-save
  has nothing to defer to; priced at 6 to 8 ops against
  the plain 4 for T1. ESTABLISHED NEGATIVE.
- Addition networks and delayed carry: the counting floor
  (section 2) is met by the incumbent; lookahead forms
  costed out. IFMA accumulation (VPMADD52) prices at 5 ops
  against 4 VPADDD for T1 and 4 against 3 for the schedule
  sum. ESTABLISHED NEGATIVE.
- Cross-round and cross-compression sharing: census found
  0 nontrivial subterms shared across the round boundary
  and 0 digest-independent outer rounds. ESTABLISHED
  NEGATIVE at the stated DAG scope. EXP-033 later closed
  the one sub-space EXP-027 left open (non-sharing
  cross-round graph restructuring) at its stated bounds,
  leaving exactly one unrefuted shape in the programme,
  E2 (Sigma output routed through the Maj/Ch value),
  labelled UNPROVEN BREAKTHROUGH with its full-cone attack
  INCONCLUSIVE. E2 is not an execution result and no rate
  attaches to it.

EXP-032 added one mechanism-level finding about where
batch gains live. The flags form (section 7) wins in batch
scope by avoiding 32 digest bytes per hash written into a
caller's buffer and extracted per lane. In search scope
that traffic does not exist: the materialised digests live
in a 512-byte stack array that stays in L1 and is compared
immediately, so the 8-word opmask compare and its mask
bookkeeping cost about what the saved extraction returns.
This is why a verified batch gain measured 0.967x (not
significant) when given a dedicated search entry, and why
kernel-scope results in this programme are never promoted
to search-scope claims without a search-scope measurement.

## 7. Dispatch reality today (production source)

Read from gpu/engine.py (ComputeEngine.__init__, line
840; dispatch block lines 862 to 897) and confirmed by the
NOVA repository audit (sections 1 and 2):

Selection order for the search backend:

1. CUDA, only if requested in (auto, cuda, cuda-only):
   library load, device present, and a production
   self-test with CPU re-verification must all pass. No
   GPU device exists on any lab host; CUDA has never been
   selected here and no GPU rate exists.
2. v512dual (_try_v512dual, line 1099): the DualMask
   backend, selected on this AMD host.
3. v512 (_try_v512, line 977): the preserved AVX-512
   multi-buffer fallback.
4. C (_try_c, line 899): the OpenSSL midstate batch
   backend, bal_c_search2.
5. Python hashlib (backend "cpu"): the floor, and the
   verification authority for every backend's self-test.

Selection discipline, identical in shape for v512 and
v512dual: the library file must exist; it is loaded with
ctypes (loading executes no kernel code); the flag-free
probe bal_v512_supported must exist, checked with hasattr
BEFORE any argtypes assignment (the audit D-1 rule), and
must return true, confirming exactly AVX-512F and
AVX-512BW via __builtin_cpu_supports; the counted entry
points must all be present as a completeness list before
any is called; then a self-test batch must reproduce
hashlib digests exactly. Any failure leaves the backend
unselected with the reason recorded, and selection falls
through. After selection, thread tuning probes thread
counts with the real counted search over 2^20 nonces and
keeps the measured peak.

The search path itself (search_first_counted, line 1459)
dispatches on the selected backend to the native counted
search entries only: v512dual to bal_vd_search2 (line
1513), v512 to bal_v_search2 (line 1561), C to
bal_c_search2 (line 1605), anything else to the
batch_search fallback. Every hit is rechecked in Python
through verify_candidate.

The flags batch (EXP-022) is selected independently
(_try_v512flags, line 1269) when the request is auto, v512
or v512dual. It never changes the search backend. Its only
production caller chain is batch_search (routing block
lines 1937 to 1950) through _vf_batch_flagged (line 1385)
to bal_v_batchf2, and the flags library exports no search
entry point at all. The production benchmark for the flags
adoption is pooled 1.441x, CI [1.261, 1.645], batch scope
only (PRODUCTION_INTEGRATION_LOG Entry 3). EXP-032 then
measured the flags question on the real search path three
ways and closed it: flags batch used as search is 2.565x
slower than the native dual search; a dedicated flags-form
search entry is 0.967x against the v512 search, not
significant, any gain bounded at about 1.06x; the same
entry reaches 0.493x of the dual search. No flags search
integration exists or is recommended.

What is verified but NOT dispatched, stated plainly:

- The EXP-032 AVX2 multi-buffer kernel (1.409x batch over
  C, VERIFIED) exists only in research code. A host with
  AVX2 but no AVX-512F+BW falls back to C today.
- The EXP-032 H-01 streams-4 SHA-NI kernel (2.861x batch
  over C, VERIFIED) exists only in research code. The
  production SHA-NI translation unit is the older
  single-stream form measured at 0.517x (ESTABLISHED
  NEGATIVE), and ComputeEngine does not dispatch it.
- EXP-024b design C mask search (1.398x, VERIFIED) exists
  only in research code.

Integrating any of these is a separate step with its own
gates and independent audit, recommended only if a target
host class without AVX-512 becomes a real deployment
prospect (EXP-032, section 10).

## 8. Two-host portability (EXP-028)

EXP-028 verified the AVX-512 F+BW kernel family on both
host classes, AMD EPYC 9D25 and Intel Xeon Platinum
8321HC, as a dispatch and correctness matter. The
portability mechanism is the build discipline plus the
probe:

- The AVX-512 translation units are compiled with the
  restricted flags -mavx512f -mavx512bw (mining/cpu/
  build.py), never -march=native. The post-integration
  objdump census of the production kernel found zero DQ,
  VL, VBMI, VBMI2 or IFMA mnemonics.
- The probe translation unit (mining/cpu/
  bal_avx512_probe.c) is compiled with no vector flags
  and contains only scalar code, so it cannot fault on a
  machine lacking any probed feature.
- The same production build selected v512 and kept mining
  on both hosts. Research libraries built with
  -march=native or with SHA instructions faulted with
  SIGILL on the Intel host; the production library did
  not. That contrast is the empirical core of the
  portability claim.
- The C batch library is built with -march=native by
  design (build.py line 140): it is a host-built fallback,
  rebuilt per host, and is recorded as such wherever its
  rates are quoted.
- The SHA-NI probe matters in both directions: the AMD
  guest has SHA-NI, the Intel guest does not. Any dispatch
  that assumed SHA-NI from the vendor string alone would
  fault on the Intel host; the probe-first rule already in
  production covers it.
- Wider AVX-512 subsets (DQ, VL, VBMI, VBMI2, IFMA, VNNI):
  detection bits are implemented and verified in the
  EXP-028 generalised probe, but no wider-subset kernel
  exists, because EXP-020 closed the round at its
  vocabulary optimum and EXP-027 priced the two
  wider-subset ideas (GFNI, IFMA) above the incumbent.
  Status: SPECIFIED, UNVERIFIED, no rate quoted.
- ARMv8 SHA2 plus NEON and RISC-V Zknh: specified in the
  EXP-028 dispatch table only. No kernel, no machine, no
  rate.

## 9. Summary of the execution picture

- One round costs 28 vector ops at the proven optimum
  within the searched vocabulary; production emits 29, the
  difference being one gcc Maj codegen op whose fix
  measured not significant and is not integrated.
- Throughput comes from width and residency: 16 lanes per
  wave in v512, two resident batches plus in-kernel opmask
  compare in v512dual (1.718x over v512 search, VERIFIED),
  4 interleaved latency chains in the SHA-NI H-01 form
  (2.861x over C batch, VERIFIED, undispatched), 8 lanes
  in the AVX2 form (1.409x over C batch, VERIFIED,
  undispatched).
- The live search path is the native counted search entry
  of the selected backend. The flags form serves batch
  enumeration only; its search-scope form is measured and
  closed.
- Every representation space outside the round vocabulary
  that the programme has searched is closed at its stated
  scope, except E2, which is unproven and carries no rate.
- All figures are contended-VM measurements on the hosts
  named. The measurement rules that keep them honest are
  specified in research/hashrate/
  HASHRATE_MEASUREMENT_SPECIFICATION.md, and the capacity
  of the VM itself is characterised in research/
  cpu_architecture/VM_RESOURCE_CAPACITY_REPORT.md.
