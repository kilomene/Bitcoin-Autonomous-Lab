# EXP-056 predeclaration (written before any solver run)

Written: 2026-11-17, before any EXP-056 measurement,
synthesis query or solver run of any kind was executed.
This file's sha256 is pinned in every EXP-056 driver
and in the test suite. EXP-056 is portfolio
NOVA-ER-0016: the H-033-02 residual cone closure
attempt. It runs last in the Stage 9 portfolio order,
in idle solver windows, strictly time-boxed. EXP-052
stays reserved for NOVA-ER-0012 (bake-off hardening).

## The question, stated exactly

A round cone is one of

  a-cone: inputs (T1, T2, a, b) ->
          (s = T1 + T2, Sigma0(s), Maj(s, a, b))
  e-cone: inputs (d, T1, e, f) ->
          (s = d + T1, Sigma1(s), Ch(s, e, f))

over the vocabulary V = {ADD, LUT(any imm), ROTR(any
k), SHR(any k)}, k in 1..31, straight-line programs,
with a proven incumbent cost of 6 instructions per
cone (1 ADD for s, 3 ROTR and 1 LUT for the Sigma,
1 LUT for Maj or Ch). Hypothesis H-033-02 (EXP-033
hypothesis registry): a straight-line program of 5
instructions over V computes a full round cone.

What is already closed, and is NOT reopened here:

- H-033-03 and H-033-04 (EXP-033): the Sigma minimum
  given the produced word and arbitrary independent
  side values is exactly 4.
- H-033-13 and H-033-14 (EXP-033): shape E1
  (correlation exploitation through the summands of
  s inside the Sigma sub-DAG) is excluded for both
  cones.
- EXP-042: shape E2 (the Sigma output routed through
  the Maj or Ch value) is refuted for both cones, and
  with it every 5-instruction cone program under the
  stated bounds: straight-line over V, cone length 5,
  the sum s produced by a single ADD of the two sum
  inputs, the Boolean output produced by a single
  LUT instruction. Under those bounds the cone
  minimum is exactly 6.

The residual generality of H-033-02, and the exact
space this experiment attacks, is therefore:

  ALL straight-line programs of length exactly 5
  over V, for each cone, with NO decomposition
  assumptions: the three outputs (s, Sigma(s),
  Maj/Ch(s, x, y)) may be produced by any of the 5
  instructions in any arrangement, and in particular
  the shapes EXP-042 listed as out of bounds are in
  scope here: (i) s produced by two or more
  instructions (Sigma and the Boolean function
  sharing a multi-instruction sum construction),
  (ii) the Boolean output produced by two or more
  instructions with Sigma computed in the remaining
  instructions over a pool including those
  intermediates, and (iii) any mixture of (i) and
  (ii).

Nothing broader is attacked: cone length stays 5,
the vocabulary stays V, the targets stay the two
cones above. No space EXP-042 or EXP-033 closed is
reopened; the closed bounds are a subset of this
space, attacked here only as part of the whole.

The only prior instrument that covers this space,
the full-cone CEGIS at L = 5 (EXP-033 encoding,
no decomposition assumptions), is inconclusive:
EXP-033 timed out at 600 s on an 82-example seed;
EXP-042 timed out at 1,500 s (a-cone) and 1,400 s
(e-cone) on a 22-example seed, both at CEGIS
iteration 0. Nothing about the residual shapes is
known either way. There is no directional
hypothesis; this entry buys information, per the
portfolio.

## Instrument: canonicalised full-cone CEGIS

The synthesiser (src/exp056_cone_synth.py) is the
EXP-033 full-cone CEGIS encoding with the following
canonicalisation constraints added. Each is argued
sound here, before any run: the constrained space
must contain a representative of every length-5
program over V that computes a cone, so that an
UNSAT verdict on the constrained space refutes the
whole space, and a SAT candidate is a genuine
program (verified exactly before being believed,
as in EXP-033 and EXP-042).

- C1, unused-slot fixing. In the EXP-033 semantics,
  an ADD reads selector slots 0 and 1 only, ROTR
  and SHR read slot 0 only, the amount is read only
  by ROTR and SHR, and the LUT immediate is read
  only by LUT. Fixing unread slots and fields to
  canonical constants (ADD slot 2 = 0; ROTR and SHR
  slots 1 and 2 = 0; amount = 1 for ADD and LUT;
  immediate = 0 for non-LUT) changes no computed
  value of any program.
- C2, ADD commutativity. For ADD instructions,
  selector slot 0 <= selector slot 1. ADD is
  commutative, so every program has an equivalent
  with its ADD operands so ordered.
- C3, output distinctness. The three output
  selectors are pairwise distinct. Sound on the
  seed set used: the driver asserts, before any
  query, that for each pair of cone targets some
  seed example gives them different values, so any
  program matching the seed already has distinct
  selectors; the constraint only removes symmetric
  duplicates.
- C4, every instruction used. Each instruction is
  an output or is read by a later instruction's
  selector slots. Without loss of generality: take
  any program of length at most 5 computing a cone;
  delete its dead instructions (it still computes
  the cone, and every remaining instruction is
  used); if fewer than 5 remain, append LUT copy
  instructions (immediate 0xF0 copies the first
  operand) chained from an existing value and route
  one output selector through the chain, until the
  length is exactly 5 and every instruction is
  used. The encoding counts a read through any
  selector slot, including slots the reader's op
  does not semantically use, which only weakens C4
  (the encoded space is a superset of the truly
  all-used space), so the padding argument still
  guarantees a representative inside the encoded
  space.
- C5, profile split (Stage B only). Fixing the
  multiset of op kinds (the counts of ADD, LUT,
  ROTR, SHR summing to 5) partitions the space
  into 56 disjoint profiles whose union is the
  whole space. A profile UNSAT closes that profile
  only.

Encoding A is the above, with rotation and shift
amounts as 32-bit bit-vectors constrained to 1..31,
as in EXP-033. Encoding B (Stage C only) is the
same canonicalised space with amounts as integers
in 1..31 and rotation and shift realised by a
selection over the 31 concrete rotations (the
bit-blasting bound made explicit: an amount is a
5-bit quantity). Both encodings describe the same
program space; a verdict from either is a verdict
about that space, subject to the gates and the
control below.

Seed set, fixed here: 16 examples per cone: the 10
edge inputs (v, v, v, v) for v in {0, 1, 2, 0xFFFFFFFF,
0xFFFFFFFE, 0x80000000, 0x7FFFFFFF, 0xAAAAAAAA,
0x55555555, 0x12345678}, 2 Boolean-stress inputs
(0, 0xFFFFFFFF, 0xAAAAAAAA, 0x55555555) and
(0xFFFFFFFF, 0, 0x55555555, 0xAAAAAAAA), and 4
random inputs from random.Random(20261119). CEGIS
iterations add exact-verification counterexamples
to the seed, as in EXP-033.

## Gates and control, run before any result is read

- G0 gates (both cones): the known 6-instruction
  incumbent programs match the cone targets on
  1,000,000 random inputs in plain Python (0
  mismatches required), and are proven exact in z3
  over symbolic cone inputs (negation UNSAT
  required). Any gate failure stops the campaign:
  nothing downstream is believed.
- C0 control (SAT-capability of the canonicalised
  encoding): the planted 5-instruction program P5
  over inputs (v0, v1, v2, v3),
    i0: ROTR(v0, 7)
    i1: ADD(v1, i0)
    i2: LUT(0x96, i1, v2, v3)
    i3: SHR(i2, 3)
    i4: ADD(i3, i1)
  with outputs (i1, i2, i4), all instructions used,
  all four op kinds present. Synthesis (encoding A)
  over 16 examples of P5's behaviour must return
  SAT, and the found program must be proven exactly
  equivalent to P5 in z3 and match it on 200,000
  random inputs in plain Python (0 mismatches).
  Per-query cap 900 s. If the control query returns
  unknown, one retry with 8 examples at a 600 s cap
  is predeclared. If both return unknown, the
  canonicalised encoding is treated as unproven on
  the SAT side and the campaign falls back to the
  plain EXP-033 encoding (imported unchanged) for
  Stage A, and Stage B is dropped: this fallback is
  fixed here, not improvised later. An UNSAT from
  the canonicalised encoding is believed only if
  the control passed.

## Stages and time box

Solver wall budget: 6,600 s (110 minutes, 1.83
solver-hours) in total, summed over EVERY z3 query
this experiment runs (gate verifications, control,
all stages, candidate verifications), as recorded
per query by the drivers. Wall-clock cap for the
whole campaign: 12,600 s (3.5 hours), including
plain-Python differentials and bookkeeping. One
solver process at a time, nice priority 19, never
parallel with any benchmark or test suite. The
drivers checkpoint after every query to
RAW_RESULTS/exp056_checkpoint.json (stage, cone,
profile, verdict, solver wall consumed); a restarted
driver resumes from the checkpoint and never
repeats a completed query.

- Stage A: canonicalised full-cone CEGIS (encoding
  A, or the plain EXP-033 encoding under the C0
  fallback), a-cone then e-cone, seed 16, per-query
  timeout 1,500 s, at most 3 CEGIS iterations per
  cone. A cone is CLOSED on synthesis UNSAT at any
  iteration (UNSAT on the seed is a proof at this
  scope, as in EXP-033). A SAT candidate stops the
  whole campaign and goes to the verification
  protocol below.
- Stage B: for each cone still open after Stage A,
  the C5 profile split: all 56 op-kind profiles in
  the fixed order (count of ADD descending, then
  LUT descending, then ROTR descending, then SHR
  descending), one iteration-0 query per profile,
  per-query timeout 240 s, seed 16, until the
  profiles are exhausted or the solver box is.
  A profile UNSAT closes that profile for that
  cone. A SAT candidate stops everything and goes
  to verification.
- Stage C: only if solver box remains after Stage
  B: encoding B full-cone queries for cones still
  open, per-query timeout at most 1,200 s, seed 16,
  a-cone first, within whatever box remains.
- No query is launched whose timeout would exceed
  the remaining solver box by more than 60 s of
  slack. When the box is spent, the campaign stops,
  whatever its state: the time box is a stopping
  rule, not a target to overrun.

## SAT candidate verification protocol

A candidate is believed only after BOTH: (1) exact
z3 verification over symbolic cone inputs (negation
UNSAT) using the EXP-033 verify construction, and
(2) a 1,000,000-sample plain-Python differential
against the cone target with 0 mismatches, run by
an independent code path (the campaign driver's own
evaluator, not the synthesiser's model extraction).
A verified candidate is a major result: the report
must lead with it, give the program explicitly, and
record that NO production integration follows from
it in this experiment (any integration is a
separate owner-gated step; by EXP-041's evidence a
1-op cone saving is not expected to change elapsed
time on this core in any case).

## Classification branches, predeclared

- Both cones CLOSED (UNSAT over the full residual
  space, by any combination of stages, with G0 and
  C0 passed): H-033-02 is CLOSED as an ESTABLISHED
  NEGATIVE at the full residual generality; the
  cone minimum over V is exactly 6 unconditionally
  within the straight-line length-5 scope; EXP-056
  registry status REJECTED (the 5-instruction cone
  hypothesis is rejected), with an exp056 update
  note appended to the H-033-02 registry entry, as
  EXP-042 did for H-033-05.
- A verified SAT construction for either cone:
  H-033-02 is VERIFIED for that cone (a genuine new
  discovery, not a reopening of a rejected item,
  per the portfolio); EXP-056 registry status
  PROVEN; the other cone's state is recorded as it
  stands.
- Anything else (box exhausted with cones or
  profiles still open): the portfolio failure
  criterion applies verbatim: another timeout at
  the predeclared budget, recorded as INCONCLUSIVE
  with the budget stated. H-033-02 stays open,
  status UNPROVEN BREAKTHROUGH, narrowed by exactly
  the subspaces recorded as exhausted (profiles
  closed per cone, stages completed); EXP-056
  registry status UNDER_INVESTIGATION. No stronger
  wording is permitted by this branch.

## Hard lines and scope

- No production code changes. This is a research
  experiment under research/sha256d/exp056/ plus
  the test suite, Makefile and registry appends.
- The live miner, autopilot, node and endpoint
  config are untouched; .local/mining-endpoint.json
  is not read or written by any driver here.
- No other machine is contacted. No rate is claimed
  or implied anywhere in this experiment.
- Solver: z3 5.4.1 (z3-solver Python package) in the
  lab venv .local/z3venv, the same solver as
  EXP-033 and EXP-042. Host: AMD EPYC 9D25
  (confirmed from /proc/cpuinfo at build start).
  Contention from the live stack is part of the
  recorded conditions and affects only how long
  queries take, never what UNSAT means.
- Every UNSAT or exhaustion claim must be
  reproducible from the recorded seed, the recorded
  solver version, and the drivers as shipped.

## UNVERIFIED register (predeclared, stands regardless of outcome)

- Any subspace not exhausted when the box expires
  is UNVERIFIED and stays open: the report must name
  it precisely (per cone: which stages completed,
  which profiles closed, which remain).
- Programs of length 5 over any vocabulary larger
  than V (for example including SHL or multi-operand
  add): out of scope by definition, UNVERIFIED.
- Programs of length below 5 in the residual
  generality: covered only insofar as the length-5
  space contains them by padding (C4 argument); a
  length-5 UNSAT therefore covers them, and a
  length-5 timeout leaves them exactly as open as
  the length-5 space.
- Behaviour on other hosts, including Intel:
  UNVERIFIED; solver verdicts are host-independent
  as mathematics, but every run here is the AMD
  EPYC 9D25 host under live-stack contention.
- Any production consequence of a construction, if
  one is found: UNVERIFIED and not attempted.
