# Phase 6, Rejected Approaches (consolidated)

One record for every approach this programme has
closed, with its evidence and the condition under
which it may be reopened. Sources: ../rejected_
hypotheses.md (R-01 to R-06, the standing record),
the experiment registry verdicts for EXP-011 to
EXP-015, and EXP-016 (this phase). A closed
approach reopens only by contradicting the named
evidence, not by restating the idea.

## From the standing record (R-01 to R-06)

### R-01: Statistical or reduced-round exploitation

Claim: structure in SHA-256d output, or in
reduced-round variants, can shortcut the search.
Evidence: chi-square and avalanche measurements
show no exploitable bias surviving past round 24
(../results/RESEARCH.md), and any reduced-round
evaluation computes a different function, not
SHA-256d. Status: REJECTED, permanent for exact
mining. Reopen: a bias measured at full rounds
with pool-grade or Core-grade acceptance evidence,
which no one has produced anywhere.

### R-02: "Lite" screening instead of the full hash

Claim: a cheaper screen can confirm blocks without
computing the full double hash. Evidence:
confirmation is defined by the full outer digest;
a screen that sometimes disagrees is not
confirmation, and one that never disagrees costs
the full computation (H-16 analysis family).
Status: REJECTED.

### R-03: Compiler flags on the production wrapper

Claim: flag tuning hides a large win in the
production path. Evidence: EXP-001's full sweep;
the hot compression is libcrypto's hand-written
assembly, which flags do not touch, and no variant
beat the baseline. Status: REJECTED as measured.
Reopen: a different production backend, at which
point it is a new experiment, not this one.

### R-04: More threads than the tuned count

Claim: thread count beyond the tuned setting must
help. Evidence: repeated measurement on this VM,
most recently EXP-000; past 2 threads the cap
(about 1.5 effective CPUs) converts extra threads
into variance (4-thread spread 82.6 percent).
Status: REJECTED for this environment. Reopen: a
changed cap or core count, which the probe and the
tuner would show first.

### R-05: The intrinsics kernel's deficit is a tuning detail

Claim: the in-repo intrinsics kernel's roughly
0.52x rate is adjustable. Evidence: its compiled
form contains zero SHA256MSG instructions and
recomputes the schedule in scalar C per nonce
(Task 001 audit); the deficit is structural.
Status: REJECTED; the remedy was a different kernel
(H-02), which exists.

### R-06: Early partial target checks skipping the outer hash

Claim: a partial check on the inner result can
skip the outer hash for most candidates.
Evidence: the target compares the full outer
digest, every word of which depends on all 64
outer rounds plus feed-forward; no exact partial
check exists in that structure (H-16 analysis).
Status: REJECTED. Reopen: a written refutation of
the dependency argument, in advance.

## From the EXP-011 to EXP-015 batch

### EXP-011's integration claim (not the direction)

The dual-batch kernel's session-A rate (8.27M H/s
median) was never reproduced (cross-session ratios
0.58x to 2.27x), and its raw session-A data was
overwritten before archiving. The claim "dual-
batch is faster" is recorded as UNPROVEN, neither
accepted nor rejected; the direction continues as
Y-023 under EXP-018 with a spill-first design.
What is rejected is quoting the 8.27M figure as a
result.

### EXP-012's search direction (closed by success)

VPTERNLOGD Boolean cones: the search closed
because it succeeded completely. Immediates are
unique (Ch 0xCA, Maj 0xE8, XOR3 0x96) and classic
minima are proven (Ch 3 ops, Maj 4). There is
nothing left in this cone; further Boolean-cone
proposals must state what they add beyond a proven
minimum.

### EXP-013 as a standalone optimisation

Cross-lane prefix sharing measured below the VM
noise floor in both sessions. As a standalone rate
claim: REJECTED for this environment (undecidable
is not positive). As a combination ingredient it
remains registered, usable only alongside an
independently successful transform.

### EXP-014: K+W folding as implemented

Folding K_t + W_t ahead of the round moved an
addition into the latency-exposed position the
fold was meant to vacate; no gain in three
sessions. Status: REJECTED as implemented. The
general lesson is promoted to a gate in the
discovery system: preparation cost is counted
inside a candidate's census, never beside it
(COMPUTATION_GRAPH_RESEARCH.md, and Y-049's
designed experiment).

### EXP-015: Bitslicing on this core

Measured 0.11 to 0.19M H/s, about 0.03x the MB
kernel, across geometries. The Boolean economy
that motivates bitslicing elsewhere is already
captured here by ternlog at the proven minima.
Status: REJECTED for this core and instruction
set. Reopen: an instruction set in which the
Boolean primitives price differently (for example,
a wider ternlog or a bit-parallel primitive this
CPU lacks), stated in advance.

## From EXP-016 (Phase 6)

### Y-065: Nonce-affine schedule decomposition

Claim: W_t = C_t + L_t(nonce) for the expanded
schedule, with L cheap, splitting the schedule
into shared and per-nonce parts. Evidence: the
separation exists exactly for W18 (L = sigma0) and
W19 (L = identity), saves no work at either, and
fails from W20: delta-linearity violation rate
1.0 on 300 sampled pairs, a z3 counterexample
verified numerically in the reference
implementation (MATHEMATICAL_DISCOVERIES.md
MD-1). Status: REFUTED (proof grade). Reopen:
contradict a named step of MD-1.

### Y-075: Round-3 state delta decomposition

Claim: a (base, delta) state representation with
a cheaply propagated delta past round 3. Evidence:
the form is exact at S_4 only; round 4's fresh
words are already nonlinear in the nonce; the
affine words at S_5 to S_7 are unmodified register
copies awaiting consumption, not propagated
deltas (MD-1). Status: REFUTED (proof grade).
Reopen: as Y-065.

## Also closed by verdict, for completeness

- The EXP-010 decision (Part A closure, third
  failure of the predeclared criterion): no
  research kernel integrates into production on
  this machine. This is a decision record, not a
  claim that the kernels are equal; the medians
  differ and the criterion is the programme's law.
- Hand-scheduled register allocation as a
  technique against this compiler on this kernel
  family (EXP-006): measured negative; the
  compiler's allocation stands until a candidate
  arrives with its assembly audit attached.
