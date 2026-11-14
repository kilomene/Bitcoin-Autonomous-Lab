# Performance Ceiling Report (Next Research Phase, Part C)

Date: 2026-11-14. Machine: the lab VM, AMD EPYC 9D25
KVM guest, 4 vCPUs capped near 1.5 effective CPUs,
sha_ni, AVX2, AVX-512 (F, DQ, BW, VL, VBMI2 and more),
gcc 13.3, OpenSSL 3.0.13. The mainnet node was still
in initial block download during this batch; the live
miner and node ran throughout and were not altered.

This report separates three kinds of statement into
three sections: MEASURED (observed on this machine
under stated conditions), THEORETICAL (derived, with
the derivation shown and every assumption labelled),
and SPECULATIVE (possibilities with no measurement
behind them). The eight mandated questions are
answered in section 4, drawing only on sections 1
to 3. No ceiling is declared without its derivation.

## 1. MEASURED

### 1.1 Rates actually observed

Best verified figures, each from its experiment
record, all on this VM under contention:

| Configuration | Median H/s | Record |
|---|---|---|
| Production C, 2 threads (tuned) | 1,627,792 | EXP-000 |
| H-02 SHA-NI single stream, 2 threads | 1,966,395 | EXP-002 |
| H-01 streams=4, per worker, 1 thread | 3,298,604 | EXP-003 |
| H-01 streams=4 strided, 2 threads | 3,473,271 | EXP-005 |
| AVX-512 MB16, 2 threads (combined) | 6,526,467 | EXP-007 |
| AVX-512 MB16, 2 threads (confirmation) | 3,195,024 | EXP-007 |
| MB16, 2 threads (EXP-011..015 session 3) | 4,199,223 | EXP-011..015 |
| Bitslice32, 2 threads | 172,365 to 186,090 | EXP-015 |

Spreads on this guest are routinely 50 to 150
percent; the EXP-011..015 sessions saw spreads up to
250 percent in individual configurations. Medians
across sessions for the same kernel differ by up to
2x. Any single-session figure is a sample, not a
constant of the machine.

### 1.2 Structural facts established by measurement

- The hot compression of the production path lives
  in libcrypto; the lab's compiled wrapper around it
  is 408 instructions with a 416-byte stack frame and
  contains zero SHA256RNDS2 (EXP-001 assembly audit).
- The H-02 hand kernel's hot function is 494
  instructions per nonce, with 63 SHA256RNDS2 and
  the message schedule produced by SHA256MSG1 and
  SHA256MSG2; its scalar-schedule twin is about 2.6x
  slower at equal rounds (EXP-002).
- The existing intrinsics kernel contains zero
  SHA256MSG instructions; its roughly 0.52x rate is
  structural (Task 001 audit, R-05).
- The rolled AVX-512 MB compress loop is 116
  instructions and already contains 7 VPTERNLOGD;
  an explicit-ternlog rewrite compiles to 111
  instructions with 6 VPTERNLOGD and performs at
  parity (EXP-012). The compiler had already made
  the Boolean optimization.
- Single-chain execution is latency-bound on this
  core: interleaving independent chains raised
  per-worker throughput 2.36x at 2 streams (EXP-003)
  and the stream curve is flat-topped from 3 to 6
  streams with heavy spills at 4 (frame 1,536 B,
  790 xmm stack ops in the inlined walker, EXP-005).
- The dual-batch MB compress body is 239
  instructions with 48 vmovdqa64: its state and
  schedule rings are memory-backed (EXP-011
  assembly audit).
- Pipeline costs at production spans are small and
  measured: per-call boundary overhead under 0.1
  percent at span 65,536 (EXP-009); search is
  99.958 percent of a stub mine cycle's wall time;
  candidate construction costs about 17.8 us per
  transaction and one validateaddress round trip of
  3.963 ms median against the real node (EXP-009).
- Candidate confirmation by hashlib costs about
  1.1 us per candidate, about 2.8 percent of one
  core at regtest density and 6.5M H/s (EXP-009).
- Memory is not the constraint: digest stores run
  about 106 MB/s against a measured copy floor of
  2.739 GB/s (EXP-000/009, machine probe).
- The guest reports a constant 1,497.75 MHz; no
  cpufreq interface and no performance counters
  exist inside the guest (machine probe).

## 2. THEORETICAL (derivations shown, assumptions labelled)

### 2.1 The fixed work per hash

SHA-256d applies three 64-round compressions per
hash. Per template, block 1 (64 rounds) is computed
once and amortized to zero across a span. The
block-2 prefix through round 2 (3 rounds) is
nonce-independent (the nonce word W3 is first
consumed in round 3, and the first expanded schedule
word depending on it is W18). Proven in
mathematical_foundations.md and
header_and_midstate_analysis.md; not an assumption.

Per-nonce work therefore has a hard floor of
192 - 67 = 125 rounds: 61 rounds of block 2 plus 64
rounds of the outer compression. No representation
change removes rounds; equivalent computation
graphs evaluate the same 125 round functions per
nonce. This is the single fact that bounds
everything below.

### 2.2 Assumption set A: measured instruction mix at an assumed IPC

Basis (measured): the H-02 hot function executes
494 instructions per nonce (EXP-002 static count of
hash_p1, used as the dynamic count to first order).

Assumptions (labelled): sustained IPC of 2 or 4 on
this instruction mix; clock either the
guest-observed 1.5 GHz or an assumed 3.0 GHz
physical clock (boost behaviour is unobservable in
this guest).

Derivation: cycles per hash = 494 / IPC.
- IPC 2: 247 cycles. At 1.5 GHz: 6.1 MH/s per core.
  At 3.0 GHz: 12.1 MH/s.
- IPC 4: 123.5 cycles. At 1.5 GHz: 12.1 MH/s.
  At 3.0 GHz: 24.3 MH/s.

Set A band: about 6 to 24 MH/s per core for a
kernel of the H-02 shape.

### 2.3 Assumption set B: SHA256RNDS2 issue bound

Basis (measured): the H-02 implementation executes
63 SHA256RNDS2 per nonce (31 for block 2, 32 for
the outer hash, in its two-round packing).

Assumptions (labelled): RNDS2 retires at most one
per cycle (its throughput on this core class); the
rest of the instruction stream (schedule, shuffles,
adds) somehow costs nothing extra, which is
deliberately generous.

Derivation: hashes per second per core <= clock / 63.
- At 1.5 GHz: 23.8 MH/s.
- At 3.0 GHz: 47.6 MH/s.

This is an absolute bound for any kernel using this
round packing on one core; loosening the packing to
the instruction's full four-round form at most
halves the RNDS2 count, giving an outer envelope of
about 95 MH/s at 3.0 GHz under the same generous
assumptions, at which point the schedule and
Boolean instructions the bound ignores become the
real limit (set C prices them).

Latency companion (assumption labelled): if one
RNDS2 step's latency is about 4 cycles (published
figures for this core class; not measurable in this
guest), a single dependency chain needs at least
63 x 4 = 252 cycles per hash, about 6.0 MH/s per
stream at 1.5 GHz. Interleaving independent chains
is how measured kernels approach the issue bound
from this latency bound; EXP-003's stream scaling
is the experimental signature of exactly this gap.

### 2.4 Assumption set C: multi-buffer instruction-count bound

Basis (counted from avx512_mb.c source and
spot-checked against objdump): per round, per
16-lane group, the vector ops are:
- schedule generation: small-sigma0 (2 vprold +
  1 shift + 1 ternlog) = 4; small-sigma1 = 4;
  schedule word sum = 3 adds; subtotal 11.
- round proper: Sigma1 = 3 vprold + 1 ternlog = 4;
  Ch = 1 ternlog; T1 = 4 adds; Sigma0 = 4;
  Maj = 1 ternlog; T2 = 1 add; e and a updates =
  2 adds; subtotal 16.
Total: 27 vector ops per round for 16 hashes.

Derivation: per-nonce rounds = 128 (block 2 plus
outer; block 1 amortized). Vector ops per hash =
128 x 27 / 16 = 216. Group overheads (nonce vector
construction, staging, extraction) add an estimated
10 to 15 percent (labelled estimate from the
v_group instruction census), giving about 240
effective ops per hash.

Assumptions (labelled): sustained vector arithmetic
issue of 1 or 2 ops per cycle. On a double-pumped
512-bit implementation the wide ops occupy the
units for two cycles, nearer the 1 end; on a native
512-bit implementation, nearer 2. The guest does
not expose which microarchitecture generation it
runs, so the range is the honest statement. Clock
1.5 or 3.0 GHz as before.

- 1 op/cycle: 1.5e9 / 240 = 6.3 MH/s per core at
  1.5 GHz; 12.5 MH/s at 3.0 GHz.
- 2 ops/cycle: 12.5 MH/s at 1.5 GHz; 25 MH/s at
  3.0 GHz.

Set C band: about 6 to 25 MH/s per core.

Consistency check against section 1: EXP-007's
best whole-VM median, 6.53M H/s at 2 threads on a
guest capped near 1.5 effective CPUs, is about
4.4M H/s per effective core, just below set C's
1.5 GHz low end (6.3M), with contention spreads
covering the difference. The MB kernel is already
within roughly 1.5x of its instruction-count bound
at guest clocks; the remaining per-core headroom
in this family is mostly clock and cap, not code.

### 2.5 What the three sets agree on

Three different derivations (instruction mix,
dedicated-instruction issue, vector op census)
place one core's ceiling in the low tens of MH/s:
roughly 6 to 25 MH/s at defensible assumptions,
with 47.6 MH/s as a deliberately generous outer
bound for the SHA-NI packing and about 95 MH/s as
the loosest envelope. The best measured per-worker
rate (3.30M H/s, EXP-003) sits about 2x below the
low end of the bands and about 6x below the
planning figure of 20 MH/s used in
PERFORMANCE_ROADMAP.md. That factor, roughly one
order of magnitude at the very most, is the entire
remaining software prize on one core.

### 2.6 Requirements for the targets, per assumption set

500 GH/s = 5.0 x 10^11 H/s. 140 TH/s = 1.4 x 10^14
H/s. Cores required = target / per-core rate:

| Per-core basis | Rate | Cores for 500 GH/s | Cores for 140 TH/s |
|---|---|---|---|
| Best measured per worker (EXP-003) | 3.30M | about 152,000 | about 42.4M |
| Set A, guest clock, IPC 4 | 12.1M | about 41,000 | about 11.6M |
| Set A/C optimistic (3 GHz) | 24 to 25M | about 20,000 | about 5.6M |
| Set B outer bound (3 GHz) | 47.6M | about 10,500 | about 2.9M |

In 64-core servers at the optimistic 25M per core
(1.6 GH/s per server): about 313 servers for
500 GH/s and about 87,500 servers for 140 TH/s.
In VMs identical to this one at its best measured
whole-VM median (6.53M H/s, EXP-007): about 76,600
VMs for 500 GH/s and about 21.4M VMs for 140 TH/s.
At current difficulty (about 5.79 x 10^23 expected
hashes per block), even 500 GH/s expects a solo
block every about 3.7 x 10^4 years, and 140 TH/s
every about 131 years; the targets are throughput
milestones, not mining-income statements.

## 3. SPECULATIVE

The following are possibilities, not estimates.
None has a measurement behind it on this machine,
and none is used anywhere in section 2.

- A computation graph that evaluates the 125
  per-nonce rounds with materially fewer primitive
  operations than the current ~240 vector ops or
  494 scalar instructions per hash. The Boolean
  cone is already at its proven minima (EXP-012);
  the schedule decomposition ideas (Y-065, Y-075)
  are the only registered directions that even
  claim to reduce op counts, and both are
  UNPROVEN BREAKTHROUGH tier until their carry
  derivations exist.
- Exploiting structure in SHA-256 beyond
  representation: none is known that preserves
  exactness at full rounds, and the lab's own
  measurements (R-01) show the statistical
  structure dying by round 24 of 64.
- Fleet aggregation to the target scale: an
  engineering programme of tens of thousands of
  machines, outside this lab's $0 constraint and
  its hardware. It is listed here, not in the
  theoretical section, because no part of it has
  been demonstrated by this lab.

## 4. The eight questions

### Q1. What limits the current CPU implementation?

In order of measured importance: (1) the fixed
125-round per-nonce workload (section 2.1) executed
as a dependency chain that a single stream cannot
parallelize (section 2.3's latency companion);
(2) the VM cap of about 1.5 effective CPUs, which
bounds the whole guest regardless of kernel;
(3) register pressure in every interleaved shape,
which converts directly into stack traffic
(EXP-005, EXP-011 audits); (4) the production
path's streaming-API wrapper and scalar-schedule
legacy choices (section 1.2); (5) contention from
the syncing node and neighbours, which dominates
measurement variance and has twice blocked the
integration decision statistic (EXP-004).

### Q2. Which limitations are software-related?

The wrapper shape around libcrypto (408
instructions, no prefix or interleave possible);
the intrinsics kernel's scalar schedule (R-05);
digest store traffic in batch mode (H-04 class);
Python boundary overhead per call (about 31 us,
EXP-000); candidate construction's repeated
verification and RPC (EXP-009, X-059); wave and
group atomicity overshoot in search accounting;
compiler codegen dependence (EXP-012 showed a key
optimization existing only as a compiler choice);
and the absence of the measured kernels from
production, which is a decision state, not a code
property: EXP-004's criterion has not been met
under this VM's contention.

### Q3. Which limitations arise from the CPU's physical execution architecture?

The 192-round algorithm structure itself (64 rounds
x 3 compressions, 125 per nonce after proven
precomputation); the per-round dependency chain
(T1 feeds e, which feeds the next round's Ch and
Sigma1); the latency and throughput of the SHA
round instructions; vector op issue width,
including whether 512-bit ops are double-pumped
on this core (unobservable here, hence the range
in set C); the architectural register file (16 xmm
for SHA-NI shapes, 32 zmm for vector shapes), which
every interleave experiment collides with; and the
virtualization layer's cap and steal, which are
physical facts of this deployment if not of the
silicon.

### Q4. What is the maximum theoretical throughput under different execution assumptions?

Section 2 in full: set A (measured instruction
mix) 6 to 24 MH/s per core; set B (RNDS2 issue)
23.8 MH/s at guest clock and 47.6 MH/s at an
assumed 3.0 GHz, with a loosest envelope near
95 MH/s; set C (vector op census) 6 to 25 MH/s
per core. Whole-VM on this guest, multiply by the
1.5 effective CPU cap: the guest's own ceiling is
in the low tens of MH/s in aggregate under every
set.

### Q5. Which assumptions have been experimentally verified?

Verified by measurement or audit: the 494
instruction hot function and its 63 RNDS2 (objdump,
EXP-002); the MB op census (source count with
objdump spot checks, EXP-007/012); ternlog presence
in compiled code (objdump); the precomputation
ceiling and the W18 boundary (derivation plus
every kernel's differential gates); the latency
bound's existence (stream scaling, EXP-003); the
spill costs (assembly audits, EXP-005/011); the VM
cap's effect (rate plateaus across thread counts,
EXP-000).
Assumed, not verified: IPC 2 to 4 sustained;
a 3.0 GHz physical clock; RNDS2 latency of about
4 cycles; vector issue of 1 to 2 ops per cycle;
the microarchitecture generation of the host.
Every number in section 2 that depends on an
assumed item is a range spanning it, by design.

### Q6. What software improvements could plausibly move the current performance?

Plausible, with sizes tied to the Y registry:
register-resident dual-batch MB (Y-023) attacking
EXP-011's 48 stack ops per dual body; schedule
generation distance in MB (Y-056, Y-025) against
the just-in-time schedule's place on the critical
path; in-register phase transpose (Y-029) removing
about 2 memory ops per hash at group boundaries;
the heterogeneous pipe pairing (Y-037, Y-097) if
the SHA and vector pipes are genuinely disjoint
here. Together these plausibly buy a factor of
about 1.5 to 3x per core over the best measured
kernel, landing inside set C's band. Nothing
registered plausibly buys 10x per core; the
op-count reductions that would (Y-065, Y-075) are
UNPROVEN BREAKTHROUGH tier. Pipeline work (X-059
class) moves end-to-end rates by single-digit
percent at current kernel speeds, more as kernels
speed up (EXP-009's interaction).

### Q7. What would be required to approach 500 GH/s and 140 TH/s?

Section 2.6's table: at the most optimistic
defensible per-core rate, about 20,000 cores for
500 GH/s and about 5.6M cores for 140 TH/s; at
measured rates, about 152,000 and about 42.4M
cores. Plus, in both cases: a work source that
feeds them (the solo server pattern, scaled), per
machine dispatch by measured capability (X-082
class), per machine measurement and an aggregate
taken from the work source's own accounting, and
the power and operations of a datacenter. None of
that exists in this lab, and the $0 constraint
forbids pretending otherwise.

### Q8. Which proposed approaches cannot achieve those targets on the available hardware?

Named plainly:
- Any software on this VM, or on any single CPU:
  the guest's aggregate ceiling under every
  assumption set in section 2 is five orders of
  magnitude below 500 GH/s.
- Bitslicing on this core (EXP-015: measured 20 to
  35x below the MB kernel; it is a refuted
  direction here, whatever its merits elsewhere).
- Statistical or reduced-round shortcuts (R-01):
  they do not compute exact SHA-256d, and their
  premise is measured dead by round 24.
- Lite screening and partial-state early abort
  (R-02, R-06): confirmation is the full hash;
  these save nothing exact.
- Compiler flags on the production wrapper
  (R-03, EXP-001): measured, no variant won.
- More threads than the cap feeds (R-04): measured
  variance, not rate.
- Phase pipelining as implemented (EXP-008:
  parity in the SHA-NI family) and K+W folding as
  implemented (EXP-014: no gain in three sessions):
  neither moves the rate it would need to move.
- Any approach whose mechanism requires fewer
  than the algorithm's 192 rounds of work per
  hash: the round count is the definition of the
  function being computed, not an implementation
  choice.
