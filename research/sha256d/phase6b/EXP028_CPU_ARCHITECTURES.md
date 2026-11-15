# EXP-028: Cross-Architecture Software Research

Experiment ID: EXP-028 (reserved 2026-11-14, Phase 6B).
Status: COMPLETE 2026-11-15 as a roadmap and dispatch
specification. Per-family verdicts in section 7: one
family is VERIFIED as a dispatch matter on two hosts
(AVX-512 MB, production), one family is MEASURED in
research on one host class (SHA extensions), and the
remaining families are SPECIFIED, UNVERIFIED, with no
rate quoted for any of them. Nothing is integrated by
this experiment; production is byte-identical at close.
Track: A (supporting).

Programme objectives, at full height, unchanged by
anything in this document: 500 GH/s is the minimum
system-performance objective and 140 TH/s is the
larger objective. This roadmap is about running the
same exact SHA-256d correctly on whatever processor a
machine happens to have. It claims no step toward
either objective by itself.

## 1. Predeclared hypothesis and criterion (unchanged)

Hypothesis: for each architecture family below, the
strongest known software strategy for exact SHA-256d
can be specified, feature-detected at runtime, and
gated to byte-identical output against the reference,
so that a portable dispatch layer (the ComputeEngine
pattern extended) selects the best available
implementation per machine with a safe fallback, and
no architecture's numbers are ever compared under
different accounting rules.

Criterion, per architecture, all of: (1) feature
detection specified and implemented in a flag-free
probe translation unit (the bal_avx512_probe.c
pattern), never by executing the kernel speculatively;
(2) runtime selection with safe fallback to the next
slower correct backend, ending at portable C or
hashlib; (3) the full gate set passes on the
architecture's own harness; (4) benchmarks, where a
machine exists, under the EXP-017 protocol with the
host recorded in full; where no machine exists, the
status is SPECIFIED, UNVERIFIED and no rate is quoted.
A one-thread result on one machine is never compared
with a multi-thread result on another without the
distinction stated in the same sentence.

How the criterion is met, honestly: items 1 and 2 are
met for the whole dispatch layer by the probe and
specification verified in section 5 (this host).
Item 3 is met today only where a gated kernel exists:
AVX-512 MB (production gates, two hosts) and the
SHA-NI streams family (research gates, one host
class). For AVX2, ARM and the wider AVX-512 subsets,
items 1 and 2 are specified and their probe bits are
implemented in the verified probe, but item 3 cannot
pass until a kernel and a machine exist; those
families therefore close as SPECIFIED, UNVERIFIED,
which is the criterion's own stated outcome for
machines that do not exist here, not a pass.

## 2. The dispatch discipline (what production proves)

Production dispatch today (CURRENT_PRODUCTION_AUDIT.md
sections 2 and 3, re-verified for this experiment):

1. mining/mainnet_live.py builds gpu.engine
   .ComputeEngine with requested="auto".
2. Order: CUDA (never selected here, no GPU exists),
   then v512, then the OpenSSL C backend, then the
   Python hashlib enumeration. requested="c" pins C.
3. _try_v512: library existence, ctypes load (executes
   no kernel code), hasattr completeness check for
   bal_v512_supported BEFORE any argtypes assignment
   (the D-1 fix), the flag-free probe call requiring
   exactly AVX-512F plus AVX-512BW, a completeness
   check that bal_v_batch2 and bal_v_search2 exist,
   then a 256-nonce self-test batch whose every digest
   must equal hashlib double SHA-256. Any failure
   leaves the backend unselected, records the reason,
   and falls through to C.
4. The probe TU (mining/cpu/bal_avx512_probe.c) is
   compiled with no vector flags and answers
   __builtin_cpu_supports("avx512f") and ("avx512bw"),
   which also implies the OS zmm state check. The
   build compiles the kernel TU separately with the
   restricted flags -mavx512f -mavx512bw, never
   -march=native, and the post-integration audit's
   objdump census confirmed zero DQ, VL, VBMI, VBMI2
   or IFMA mnemonics in the production kernel.
5. After selection, a one-time measured thread tuning
   runs over the real counted search.

Two-host survival evidence: the same production build
selected v512 and kept mining on the AMD EPYC 9D25
host (SHA extensions, full AVX-512 including VBMI2
and IFMA) and, after the VM replacement of 2026-11-14
about 18:08 UTC, on the Intel Xeon Platinum 8321HC
host (AVX-512F/BW/VL/VNNI, no SHA extensions, no
VBMI). Research libraries built with -march=native or
SHA instructions faulted with SIGILL on the Intel
host; the production library, built with restricted
flags and gated by the probe, did not. That contrast
is the empirical core of this roadmap: restricted
flag sets plus probe gating are what make a binary
portable across hosts whose feature sets differ.

## 3. The generalised probe (implemented, this host)

benchmarks/exp028_probe.c generalises the production
probe to every family in scope. It is compiled with
no architecture flags, contains no vector or
extension instruction (verified at the object level,
section 5), and exports a 16-bit feature mask:
AVX-512F, BW, DQ, VL, VBMI, VBMI2, IFMA, VNNI, AVX2,
SHA, SSE4.1, SSE4.2, BMI1, BMI2, ADX, AES. On a
non-x86 build every x86 bit reads 0 by construction.

benchmarks/exp028_dispatch.py is the dispatch
specification in executable form. Selection order
(first whose full chain passes): avx512-mb (probe
F+BW, library complete, hashlib self-test), then
shani-streams (probe SHA+SSE4.1+SSE4.2, complete,
self-test), then avx2-mb (probe AVX2, complete,
self-test), then c-openssl (complete, self-test),
then hashlib as the portable floor. CUDA sits above
the list where a device exists; this programme has
no GPU, so the CUDA position is inherited from
production's order and is UNVERIFIED here, as it has
been since Task 002. The ARM family slots between
avx2-mb and c-openssl on non-x86 builds (section 4.5).
Rules carried verbatim from production: a probe bit
alone never selects; completeness is checked before
any call (the D-1 pattern); the self-test is a
hashlib differential, not a smoke run; every failure
records a reason and falls through; only an explicit
single-backend request may raise.

## 4. Per-family roadmaps

### 4.1 AVX-512, production subset (F plus BW)

Strategy: the 16-lane multi-buffer kernel,
mining/cpu/bal_avx512_mb.c (production v512), with
the EXP-024 mask compare and the EXP-026 DualMask
form as recorded, gated, not-integrated successors
in the same family. Detection: probe bits 0 and 1,
exactly the production predicate. Dispatch position:
first CPU family. Gates: already the production gate
set (196,608 differentials at integration, fresh
regtest blocks, live soak), re-run on any new host
before its numbers are quoted. Status: VERIFIED
(dispatch and correctness) on two hosts, AMD EPYC
9D25 and Intel Xeon Platinum 8321HC; rates are
host-bound and are quoted only with their host and
thread count attached (gap model section 1).

### 4.2 AVX-512, wider subsets (DQ, VL, VBMI, VBMI2, IFMA, VNNI)

Strategy: no wider-subset kernel exists in this
programme, and none is currently motivated.
EXP-020 closed the steady-state round at 28 vector
ops within the classic vocabulary, and EXP-027
priced the two wider-subset ideas that could change
the census: GFNI affine forms (the sigma maps are
GF(2)-linear but every Sigma0 output byte depends on
all four input bytes, flooring any GFNI network at
11 ops against the incumbent 4; Ch and Maj proven
non-affine) and the 52-bit IFMA accumulation form
(proven exact, costed at 5 ops against 4 VPADDD).
VBMI shuffle rotations were refuted exhaustively for
the pure form and measured at 2.00x the VPROLD price
for the mixed form (EXP-027). Detection: probe bits
2 to 7 are implemented and verified on this host, so
a future wider-subset kernel can be gated the day a
costed design survives proof. Status: SPECIFIED
(detection), UNVERIFIED (no kernel), no rate quoted.
Any future kernel in this family must additionally
prove it never executes on a host lacking its subset:
the Intel 8321HC host (no VBMI) is the standing
counterexample that makes this a gate, not a hope.

### 4.3 SHA extensions (Intel and AMD SHA-NI)

Strategy: the H-01/H-02 family. One nonce per chain
is latency-bound on SHA256RNDS2, so the strongest
known form interleaves independent chains: H-02's
direct kernel with the schedule built entirely by
SHA256MSG1 and SHA256MSG2 (EXP-002: the MSG schedule
alone is worth about 2.6x over the scalar schedule at
equal rounds, same-session medians), at the EXP-005
geometry of 4 streams, strided assignment (EXP-003
per-worker 1-thread median 3.30M H/s on the AMD EPYC
9D25 guest; EXP-005 2-thread median 3.47M H/s for
streams=4 strided on the same host class; both
figures are this programme's own measurements on that
host, quoted with thread counts because the criterion
requires it in the same sentence). Detection: probe
bits 9, 10, 11 (SHA plus SSE4.1 plus SSE4.2), the
predicate bal_xarch_shani_ok in the EXP-028 probe.
Dispatch position: second, below AVX-512 MB, because
EXP-021 measured the homogeneous MB pool above the
SHA-NI pool head to head on this guest (pooled 1.363x
at 2 threads and 1.329x at 4 threads, both thread
counts on the AMD host, EXP-017 protocol) and mixed
pools between them (an established negative for
heterogeneous pairing at equal partitions). Gates:
the EXP-002/003/005 gate sets stand as this family's
harness record (120,000 differentials in EXP-002;
108,000 per stream count in EXP-003; at least 100,000
per geometry variant in EXP-005; genesis re-found;
wave-exact accounting). Status: MEASURED in research
on AMD SHA hosts. Intel SHA hosts: SPECIFIED,
UNVERIFIED (no Intel SHA machine has been available;
the 8321HC host has no SHA extensions). No rate is
quoted for Intel SHA.

### 4.4 AVX2

Strategy: an 8-lane multi-buffer kernel of the same
shape as the AVX-512 MB kernel at half the lane
width (registry X-032 names the AVX-512 8-way form;
the AVX2 form is its 256-bit analogue), with
rotations by VPSRLD/VPROLD-class sequences (AVX2 has
no dword rotate; the standard form is shift pairs
plus OR, which is why this family is expected below
AVX-512 per core, an expectation, not a measurement).
Detection: probe bit 8. Dispatch position: third,
the fallback that keeps pre-AVX-512 x86 machines on a
vector path instead of dropping straight to C.
Gates before any number: build the kernel, pass the
full gate set (differentials vs hashlib, candidate
set equivalence, target and nonce boundaries, exact
accounting, genesis) on an AVX2 host, then EXP-017
benchmarks with the host recorded. Status: SPECIFIED,
UNVERIFIED. No kernel is built and no rate is quoted.
This is the highest-value unbuilt family in the
roadmap, because AVX2-only machines are common; it
is still unbuilt because this programme's hosts have
all carried AVX-512, and building it is a new
experiment (next unreserved ID EXP-030), not part of
this roadmap's evidence.

### 4.5 ARMv8 SHA-256 plus NEON

Strategy: the SHA-NI family's analogue. ARMv8
Cryptographic Extensions provide SHA256H, SHA256H2,
SHA256SU0 and SHA256SU1, a rounds-plus-schedule
structure directly parallel to SHA256RNDS2 plus
MSG1/MSG2, so the strongest known form is again
multi-stream interleaving of independent chains to
hide the serial round latency, with NEON holding the
per-stream states. Detection: never by executing the
instructions. On Linux the probe reads the OS
capability interface (getauxval AT_HWCAP, the SHA2
bit) from a plain C translation unit with no crypto
flags, the exact analogue of the flag-free x86 probe;
on other systems the OS equivalent. The probe TU is
specified here; it is not compiled in this
experiment because no ARM machine exists to compile
or run it on, and an x86-compiled ARM probe would
prove nothing. Dispatch position: on a non-x86 build,
the ARM SHA family takes the shani-streams slot
(below any future ARM wide-vector MB form, above
NEON-only and C). Fallback chain on ARM: SHA2
extensions, then NEON multi-buffer (specified only),
then portable C, then hashlib. Gates: identical set,
on ARM hardware, before any number. Status:
SPECIFIED, UNVERIFIED in full. No rate is quoted,
no kernel exists, no probe binary exists.

### 4.6 Portable C and hashlib (the floor)

Strategy: the production OpenSSL C backend
(mining/cpu/bal_batch.c) and, below it, the Python
hashlib enumeration. These are the correctness
reference as well as the floor: every family's
self-test is a differential against hashlib, and
every candidate from every backend is independently
re-verified before use (gpu/engine.py
verify_candidate). EXP-000 baselines on the AMD
guest: C 1 thread median 1,314,704 H/s, hashlib
304,444 H/s (EXP-000 protocol, that host, those
thread counts). Status: VERIFIED (production, both
hosts the programme has run).

### 4.7 Other architectures

RISC-V: the Zknh extension defines SHA-256
instructions; no machine, no kernel, no probe is
available to this programme. Named here so the
dispatch table has a place for it; status SPECIFIED
in name only, UNVERIFIED, no rate. GPU/CUDA: outside
this experiment's CPU scope; its gates remain
UNVERIFIED since Task 002 for lack of a device, and
nothing in this roadmap changes that.

## 5. Verification performed for this experiment

On this host only (AMD EPYC 9D25 126-Core guest, 4
vCPUs, flags including avx512f/bw/dq/vl/vbmi/vbmi2/
ifma/vnni, avx2, sha_ni; benchmarks/exp028/):

1. Probe object safety: exp028_probe.c compiled with
   no architecture flags; the objdump census of the
   object lists only scalar mnemonics (add, and, call,
   cmove, mov, or, ret, sete, shr, sub, test and
   similar), zero vector or extension mnemonics. The
   probe cannot fault on a machine lacking any probed
   feature, which is the point of the pattern.
2. Probe truth: the returned mask was 0xffff (all 16
   bits set) and every bit agreed with the matching
   /proc/cpuinfo flag on this host.
3. Predicates: bal_xarch_v512_ok and bal_xarch_shani_ok
   both true on this host, matching production's live
   v512 selection and this host's sha_ni flag.
4. Dispatch scenarios (exp028_dispatch.py): with all
   libraries present and self-tests passing, this
   host's bits select avx512-mb; forced probe failure
   (bits 0) selects c-openssl (the shani and avx2
   predicates are false and the C predicate is
   unconditional); incomplete libraries for the three
   vector families (the D-1 pattern, completeness
   checked before any call) select c-openssl; a failed
   v512 self-test falls through to shani-streams; no
   libraries at all selects hashlib. All five
   expectations met.
5. Record: probe_20261115T060117Z.json, verdict PASS.
   The earlier probe_20261115T060106Z.json record,
   verdict FAIL, is preserved append-only: its failure
   was a wrong expectation in the test harness (the
   incomplete-library scenario initially left the AVX2
   library complete, and the dispatcher correctly
   selected avx2-mb), not a probe or dispatch defect.
   The scenario was corrected and the run repeated.

No kernel was benchmarked in this experiment and no
EXP-017 run was triggered: the families with machines
already carry their measurements (sections 4.1, 4.3,
4.6), and the families without machines carry no
numbers by rule.

## 6. Accounting rules for cross-machine honesty

Standing for every future per-architecture record:

1. Every rate is recorded with, in the same record:
   host model, full relevant flag set, vCPU or core
   allocation, thread count, kernel identity and
   build flags, and whether a live miner or node was
   contending on the host.
2. Comparisons state both sides' thread counts and
   hosts in the same sentence as the ratio. A pooled
   EXP-017 ratio is valid only within one host.
3. Accounting identity per backend is the Task 003.9
   set (requested, unique coverage, backend hashes
   including dummy lanes, device hashes, researched,
   verification, candidates), so a 16-lane wave
   backend and a 1-chain SHA backend report the same
   quantities under the same names.
4. Wave-atomic backends count attempted as completed
   waves times lanes; early-exit positions inside a
   wave are not claimed as savings. SHA-stream
   backends count by their wave rule from EXP-003.
   The rule travels with the backend and is named in
   its record.
5. A rate measured on a shared or contended guest is
   labelled as such and is never presented as a bare
   hardware figure.

## 7. Per-family verdicts

| Family | Detection | Kernel | Verdict |
|---|---|---|---|
| AVX-512 F+BW MB | production probe, verified | production v512 | VERIFIED on 2 hosts (dispatch and correctness); successors EXP-024 C and EXP-026 DualMask gated, not integrated |
| AVX-512 wider subsets | probe bits implemented, verified this host | none | SPECIFIED, UNVERIFIED; EXP-027 priced the candidate forms out |
| SHA extensions (AMD) | probe predicate implemented, verified this host | H-01/H-02 research | MEASURED in research (EXP-002/003/005); not integrated |
| SHA extensions (Intel) | same predicate | same kernels, unrun there | SPECIFIED, UNVERIFIED; no rate |
| AVX2 MB | probe bit implemented, verified this host | none (X-032 class) | SPECIFIED, UNVERIFIED; no rate; highest-value unbuilt family |
| ARMv8 SHA2 plus NEON | specified (OS capability probe) | none | SPECIFIED, UNVERIFIED; no rate, no machine |
| RISC-V Zknh | named only | none | SPECIFIED in name only, UNVERIFIED |
| Portable C / hashlib | unconditional | production | VERIFIED (the floor and the reference) |

Predeclared criterion outcome: MET as a roadmap and
dispatch specification, with items 3 and 4 of the
criterion satisfied per family exactly where the
criterion's own machine-existence clause says they
can be, and recorded as SPECIFIED, UNVERIFIED where
they cannot. No integration. Follow-up, if the owner
wants it: the AVX2 kernel as a new experiment under
EXP-030; ARM the day an ARM machine exists.
