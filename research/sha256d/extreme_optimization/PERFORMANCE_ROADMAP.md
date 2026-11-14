# Performance Roadmap and the Honest Target Assessment

All measured figures cite their experiment records. All
derived figures show their arithmetic. Estimates are
labelled estimates with their assumptions stated.

## 1. Best verified rates on this VM (measured)

From EXP-000, EXP-002, EXP-003, all on the lab VM (EPYC
9D25 KVM, 4 vCPUs, cap about 1.5 effective CPUs, live
miner and node contending):

| Configuration | Median H/s | Record |
|---|---|---|
| Production C, 1 thread | 1,314,704 | EXP-000 |
| Production C, 2 threads (tuned) | 1,627,792 | EXP-000 |
| Production C, 4 threads (unstable, spread 82.6%) | 2,512,762 | EXP-000 |
| H-02 single-stream, 2 threads (in-session) | 1,966,395 | EXP-002 |
| H-01 streams=2, per worker (1 thread) | 2,515,315 | EXP-003 |
| H-01 streams=4, per worker (1 thread) | 3,298,604 | EXP-003 |
| H-01 streams=4, whole VM total (2 threads) | 3,481,103 | EXP-003 |
| H-01 streams=4, decision run, 2 threads | 3,084,485 | EXP-003 |
| Live miner status rate (real templates) | about 3,013,312 | ../statistical_mining_analysis.md |

Reading: the best verified per-worker rate is about
3.30 MH/s; the best verified whole-VM total is about
3.48 MH/s, and it is capped by the VM's roughly 1.5
effective CPUs, not by the kernels. Per-worker and
whole-VM figures are different claims and are never
interchanged in this programme.

Update 2026-11-14 (EXP-004 to EXP-009 batch; full
records in EXPERIMENT_REGISTRY.md and
EXP004_009_REPORT.md):

| Configuration | Median H/s | Record |
|---|---|---|
| H-01 streams=4, decision re-run, 2 threads | 4,212,571 | EXP-004 |
| H-01 streams=4 strided, 2 threads | 3,473,271 | EXP-005 |
| H-01 streams=6 blocked, 2 threads | 2,593,711 | EXP-005 |
| Phase pipeline, 2 threads | 2,104,688 | EXP-008 |
| AVX-512 mb16, 2 threads (combined session) | 6,526,467 | EXP-007 |
| AVX-512 mb16, 2 threads (confirmation) | 3,195,024 | EXP-007 |

The AVX-512 multi-buffer is now the fastest measured
implementation on this VM on a median basis at 2
threads, reproduced in two interleaved sessions; its
spread (106.5 percent in the combined session) is the
widest measured and it holds no separation claim.
EXP-004's decision re-run failed the beyond-spread
criterion a second time, so nothing from this batch is
integrated and production remains the EXP-000 row set.
None of these numbers moves the target arithmetic of
section 3: the best batch median, 6.53 MH/s at 2 threads
on a capped guest, is still about 77,000x below 500
GH/s, and the ceiling argument of section 2 is
unchanged.

## 2. The per-core ceiling (estimate, arithmetic shown)

Per-nonce work after all proven precomputation: 125
rounds (61 of block 2 plus 64 outer). In the H-02 kernel
this is 63 SHA256RNDS2 plus 48 schedule instructions,
inside a measured hot function of 494 instructions per
nonce (EXP-002 assembly record; the static instruction
count of hash_p1, used here as the per-nonce dynamic
count to first order).

Estimate assumptions, stated: a core sustaining an
average of 2 to 4 retired instructions per cycle on this
instruction mix, at either the guest-reported frequency
of 1.5 GHz (the only frequency observable inside the VM)
or an assumed 3.0 GHz physical clock (labelled
assumption; boost behaviour is unobservable in this
guest).

- Cycles per hash: 494 / 4 = about 124 (at IPC 4);
  494 / 2 = 247 (at IPC 2).
- At 1.5 GHz: 6.1 MH/s (IPC 2) to 12.1 MH/s (IPC 4).
- At 3.0 GHz: 12.1 MH/s (IPC 2) to 24.3 MH/s (IPC 4).

So the per-core ceiling for a kernel of this shape is in
the low tens of MH/s: a planning band of roughly
10 to 25 MH/s per core, with about 20 MH/s as the
optimistic planning figure. Sanity floor: even if a
kernel executed nothing but RNDS2 and retired one per
cycle, 63 RNDS2 per hash bounds it to 47.6 MH/s at
3.0 GHz; no software on one core passes that bound
without changing the round count, which the algorithm
definition forbids.

Headroom from here: the best measured per-worker rate
(3.30 MH/s) sits about 6x below the 20 MH/s planning
figure and about 14x below the absolute RNDS2 floor.
That is the entire remaining software prize on one core:
roughly one order of magnitude, at most, and most of it
is contested by register pressure and the VM cap.

## 3. The gap to the targets (arithmetic shown)

Targets: 500 GH/s = 5.0 x 10^11 H/s.
140 TH/s = 1.4 x 10^14 H/s.

### 3.1 Multiples of the best verified rates

- Versus best per-worker (3,298,604 H/s): 500 GH/s is
  5.0e11 / 3.30e6 = about 152,000x away; 140 TH/s is
  about 4.24 x 10^7 x away.
- Versus best whole-VM total (3,481,103 H/s): about
  144,000x and about 4.02 x 10^7 x.
- Versus tuned production (1,627,792 H/s): about
  307,000x and about 8.6 x 10^7 x.

### 3.2 Core counts required

At the best measured per-worker rate (3.30 MH/s per
core-class worker):

- 500 GH/s needs about 152,000 cores.
- 140 TH/s needs about 42.4 million cores.

At the optimistic per-core ceiling estimate (20 MH/s):

- 500 GH/s needs about 25,000 cores.
- 140 TH/s needs about 7.0 million cores.

In 64-core servers at the ceiling rate (1.28 GH/s per
server): about 390 servers for 500 GH/s, and about
109,000 servers for 140 TH/s. In VMs identical to this
one at its best verified total: about 144,000 VMs for
500 GH/s, about 40 million for 140 TH/s.

### 3.3 Context that sizes the targets

- 140 TH/s is approximately the output of one modern
  ASIC miner unit (../results/RESEARCH.md cites about
  200 TH/s for a current unit).
- The whole Bitcoin network runs at hundreds of
  exahashes per second (../docs/HONEST-LIMITS.md); even
  140 TH/s would be a negligible share of it.
- At the current difficulty (134.8 trillion;
  expected hashes per block = difficulty x 2^32 =
  about 5.79 x 10^23, per ../statistical_mining_analysis.md),
  even 500 GH/s expects a block only every about
  3.7 x 10^4 years solo, and 140 TH/s every about
  131 years. The lab's present whole-VM rate expects one
  in about 5.3 x 10^9 years (about 1.13 x 10^10 years at
  the EXP-000 baseline rate). These are the same
  geometric law at different rates, and they are why
  real mining at any of these scales is pooled.

## 4. The conclusion, in plain terms

500 GH/s and 140 TH/s are aggregate-fleet objectives,
not single-machine ones. No CPU, and no software running
on one CPU, reaches them: the fixed 192-round structure
of SHA-256d bounds one core to the low tens of MH/s no
matter how good the implementation is, and this lab has
measured its way to within about one order of magnitude
of that bound. Reaching 500 GH/s with CPUs means tens of
thousands of cores at ceiling-class software, or about
150,000 cores at the best rate verified today. Reaching
140 TH/s with CPUs means millions of cores; in silicon
it means roughly one ASIC unit, which is what that
number describes in the real world.

The credible mission, and the one this roadmap funds
with effort, is therefore twofold: (1) close the
remaining per-core gap toward the ceiling with verified
kernels, because per-core rate multiplies whatever fleet
ever exists; and (2) treat fleet aggregation as a
separate engineering claim, to be demonstrated only on
real machines under the lab's own evidence standard,
never by multiplying a benchmark by a hoped-for machine
count. A fleet figure is claimed when the fleet exists
and is measured, per machine and in aggregate, labelled
separately (mandate section 9).

## 5. What demonstrating the targets would require

Stated as engineering requirements, not plans:

- For 500 GH/s: about 25,000 cores running ceiling-class
  verified kernels (or about 152,000 at today's best
  verified per-worker rate), with per-machine dispatch,
  a work source that keeps them fed (the solo server
  pattern, scaled), per-machine measurement, and an
  aggregate measurement taken from the work source's own
  accounting, not from summing self-reports.
- For 140 TH/s: about 7 million cores at ceiling-class
  rates, or the honest admission that this target is an
  ASIC-scale figure, demonstrable by CPUs only as a
  datacenter-scale fleet that this lab does not have and
  is not pretending to have.
- In both cases: power, cooling, and operations at the
  corresponding scale, which are outside this lab's $0
  constraint and are named here so the requirement list
  is complete rather than flattering.

## 6. Ranked research phases from here

Phase 1: measurement hygiene and the integration
decision. X-067 (quiet-window decision re-run), X-070
(steal covariate), X-072 (paired-run design), X-069
(session fingerprinting). Exit: H-01 streams=4 integrated
under the rule, or the question closed with separated
ranges that say no.

Phase 2: kernel geometry and assembly. X-001, X-019,
X-002, X-003 (stream counts), X-004, X-005 (assignment
and waves), X-006, X-007 (hand-scheduled assembly),
X-016, X-024 (cheap structural wins), X-009 (phase
pipelining). Exit: the SHA-NI family's measured optimum
on this core, with its assembly record.

Phase 3: the vector family. X-031, X-032, X-034
(multi-buffer prototypes and control), X-041 (frequency
drift gate), X-020, X-021 (design options), X-033
(AVX2). Exit: the family ranked by measurement against
the Phase 2 champion, or refuted with its cost anatomy
recorded (X-034 decides which).

Phase 4: pipeline repricing at the new rate. X-059,
X-060, X-061 (candidate construction), H-04 (flags-only
output), H-05 and H-14 (span economics), X-062
(preemption). Exit: end-to-end mined-rate measurements
through mining/engine.py, not kernel-only figures.

Phase 5: automation. X-049 (generator and sweep), X-095
(optimizer over the grid), X-096 (fuzzing at scale),
X-091 to X-094 (superoptimizer line). Exit: the
experimentation loop runs the geometry and codegen
searches standing, with Workstream F verification in the
loop.

Phase 6: fleet, only if hardware appears. X-082
(dispatch), X-107 (portability). No phase is scheduled
against machines that do not exist.
