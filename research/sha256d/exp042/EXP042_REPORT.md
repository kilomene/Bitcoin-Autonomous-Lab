# EXP-042: the E2 synthesis attempt (Phase 002 step 5)

Date: 2026-11-15. Host: AMD EPYC 9D25 (recorded; the
live mainnet miner, node and autopilot were never
touched, restarted or interacted with; all work was
solver processes inside the lab tree). Solver: z3
5.4.1 (Python package z3-solver 5.4.1, installed into
the lab venv .local/z3venv on this host; no z3 was
present in any pre-existing environment here). No
timing runs of any kind were made in this step; this
is a synthesis and proof exercise only. Nothing was
pushed. No fleet agents were activated.

## Solver budget, stated before the results

Time box: at most about 90 minutes (5,400 s) of
solver wall time in total across all runs, at most 2
solver processes at once (in the event, all solver
work ran strictly one process at a time). Actual
solver wall consumed: about 3,904 s (about 65
minutes); about 1,496 s of the box was left unspent
because every planned sub-case had reached a verdict.
Accounting per run is in section 5.

## 1. The question

EXP-033 (H-033-05) left exactly one shape unrefuted
in the round-cone problem. A round cone is

  a-cone: inputs (T1, T2, a, b) ->
          (s = T1 + T2, Sigma0(s), Maj(s, a, b))
  e-cone: inputs (d, T1, e, f) ->
          (s = d + T1, Sigma1(s), Ch(s, e, f))

over the vocabulary V = {ADD, LUT(any imm), ROTR(any
k), SHR(any k)}, k in 1..31, with a proven incumbent
cost of 6 instructions per cone (1 ADD, 3 ROTR and 1
LUT for the Sigma, 1 LUT for Maj or Ch). EXP-033
proved the Sigma minimum is exactly 4 given the
produced word and arbitrary independent side values
(H-033-03, H-033-04), and excluded shape E1
(correlation exploitation through s = T1 + T2) by
cone-conditioned synthesis over the pool
(s, T1, T2, a, b) at L = 3 (H-033-13, H-033-14). The
one shape left open was E2: the Sigma output routed
through the Maj (resp. Ch) value, so the Boolean
instruction sits inside the Sigma sub-DAG and the
1 + 4 + 1 accounting bounds only 5. The full-cone
CEGIS at L = 5 (H-033-02) had returned synth unknown
at a 600 s timeout on an 82-example seed: inconclusive,
not a refutation. Ceiling if E2 existed: 1 instruction
per cone, at most about 2 ops per round against the
EXP-020 28-op round optimum.

## 2. The reduction that decides E2

Take any 5-instruction cone program and let D be the
set of instructions the Sigma output transitively
depends on, excluding the ADD that produces s.

Case 1, the Boolean instruction is not in D. Then D
has at most 3 instructions (5 minus the ADD minus the
Boolean instruction) and its operands come only from
the pool (s, T1, T2, a, b) on the a-side, resp.
(s, d, T1, e, f) on the e-side. H-033-13 and H-033-14
prove no such 3-instruction program computes the
Sigma. Excluded before this experiment began.

Case 2, shape E2 proper: the Boolean instruction is
in D. Remove it from D. The remaining instructions
number at most 3, and every operand they use is one
of: the sum s, the two sum inputs, the two other cone
inputs, the Boolean value m itself (Maj(s, a, b),
resp. Ch(s, e, f)), or a prior result of the remaining
instructions. So the remainder is a straight-line
program of length at most 3 over the 6-value pool

  (s, p, q, x, y, m)

computing Sigma(s), where (p, q) are the sum inputs
and (x, y) the other cone inputs. EXP-042 synthesises
exactly this: L = 3 over that pool, with m given as a
free pool input on every example. Giving m for free,
available from the first instruction, only enlarges
the program space (a real E2 program can use m only
after spending its Boolean instruction), so UNSAT of
this synthesis refutes case 2, and any SAT candidate
would be a genuine construction (cone program: ADD,
the Boolean LUT, then the 3 found instructions, with
indices remapped), to be verified exactly before
being believed. Programs of length below 3 are
covered, since the L = 3 encoding admits unused
instructions.

Stated bounds of the refutation in section 4:
straight-line programs over V; cone length 5; the sum
s produced by a single ADD of the two sum inputs (the
only single instruction over V that computes the
sum); the Boolean output produced by a single LUT
instruction. That is exactly the E2 shape as named in
EXP-033. Shapes outside these bounds are listed in
section 6.

## 3. Method and soundness discipline

The synthesiser (src/exp042_e2_synth.py) is the
EXP-033 CEGIS encoding (src/exp033_sigma_synth.py)
generalised from a 5-value to the 6-value pool above:
per instruction, symbolic op kind, three symbolic
operand selectors, an 8-bit LUT immediate and a 32-bit
rotation or shift amount constrained to 1..31;
examples are cone inputs (p, q, x, y) expanded to
pool tuples ((p + q) mod 2^32, p, q, x, y, Bool(s,
x, y)), so every example is cone-realizable by
construction. A universally correct program matches
every example, so a synthesis UNSAT on the seed set
is a proof at the stated scope; no CEGIS iteration
beyond 0 was needed anywhere.

Gates run before any synthesis result was read, on
both cones: the known 4-instruction Sigma incumbent
over pool index 0 matched Sigma(s) on 200,000 random
cone inputs in plain Python (0 mismatches) and was
proven exact in z3 over symbolic cone inputs with s
and m derived (negation UNSAT). A control synthesis
then confirmed the encoder can find programs at all:
for the a-cone target ROTR(s, 2) ^ ROTR(s, 13) ^ m,
which has a known 3-instruction program over this
pool, the synthesiser returned SAT at iteration 0
(219.6 s) and the candidate passed a 200,000-sample
plain-Python differential. No candidate was produced
by any E2 query, so the candidate-verification
protocol (exact z3 over symbolic cone inputs, then
1,000,000-sample plain-Python differential of the
assembled cone) was not exercised; it is implemented
in the script and was exercised end to end by the
control and the gates.

Catch-all: with the decisive sub-cases settled, the
remaining budget reran the EXP-033 full-cone CEGIS at
L = 5 (src/exp042_fullcone.py drives the EXP-033
module unchanged, raising only the per-query
timeout), which makes no decomposition assumptions
and therefore also covers the out-of-bounds shapes of
section 6.

## 4. Results per sub-case

Gates, a-cone: PASS (differential 0 bad in 200,000;
exact z3 UNSAT of the negation).
Gates, e-cone: PASS (same).

Control, a-cone, L = 3 over the 6-value pool, target
ROTR(s, 2) ^ ROTR(s, 13) ^ m: SAT at iteration 0,
query wall 219.6 s, candidate passed the 200,000
sample differential. The encoding is sound and
SAT-capable on this pool and length.

E2, a-cone (Sigma0 through Maj): synthesis UNSAT at
iteration 0 on a 16-example seed (14 edge and
Boolean-stress cone inputs plus 2 random), query wall
540.3 s. No 3-instruction program over
(s, T1, T2, a, b, Maj(s, a, b)) computes Sigma0(s).
RAW_RESULTS/exp042_e2_a_s1_20261115T212816Z.json;
PROOFS/exp042_e2_a_s1_20261115T212816Z.json.

E2, e-cone (Sigma1 through Ch): synthesis UNSAT at
iteration 0 on a 16-example seed of the same shape,
query wall 214.0 s. No 3-instruction program over
(s, d, T1, e, f, Ch(s, e, f)) computes Sigma1(s).
RAW_RESULTS/exp042_e2_e_s1_20261115T213844Z.json;
PROOFS/exp042_e2_e_s1_20261115T213844Z.json.

Full-cone catch-all, a-cone, L = 5, EXP-033 encoding,
22-example seed: synth unknown at the 1,500 s
per-query timeout (wall 1,504.2 s), iteration 0.
INCONCLUSIVE, reported as such.
RAW_RESULTS/exp042_fullcone_a_cone_20261115T214323Z
.json.

Full-cone catch-all, e-cone, L = 5, 22-example seed:
synth unknown at the 1,400 s per-query timeout (wall
1,402.2 s), iteration 0. INCONCLUSIVE, reported as
such. RAW_RESULTS/exp042_fullcone_e_cone_20261115T
221038Z.json.

## 5. Solver budget accounting

  Gates (both cones, z3 exact verifies; the stage
  also ran 400,000 plain-Python differentials):
  about 24 s.
  Control, a-cone: 219.6 s.
  E2 synthesis, a-cone: 540.3 s.
  E2 synthesis, e-cone: 214.0 s.
  Full-cone catch-all, a-cone: 1,504.2 s.
  Full-cone catch-all, e-cone: 1,402.2 s.
  Total: about 3,904 s of the 5,400 s box.

All solver processes ran one at a time on the shared
VM, alongside the live mainnet miner; contention is
part of the recorded conditions and affects only how
long queries took, never what UNSAT means.

## 6. Verdict and what remains open

Verdict: E2 is REFUTED at the stated bounds for both
cones. Tier: ESTABLISHED NEGATIVE at those bounds.
Combined with EXP-033 (E1 excluded by H-033-13 and
H-033-14; the independent-filler bound of H-033-03
and H-033-04), hypothesis H-033-05 is closed: no
5-instruction cone program over V exists via shape
E1 or shape E2, and the cone minimum over V is
exactly 6 under the stated bounds (straight-line,
cone length 5, sum by a single ADD, Boolean output by
a single LUT). The EXP-033 hypothesis registry entry
H-033-05 has been updated with a dated note recording
this. No construction was found, so there is nothing
to benchmark; no rate is claimed or implied.

What remains open, stated exactly: 5-instruction cone
programs outside the stated bounds, namely (i) the
sum s produced by two or more instructions (so Sigma
and Maj share a multi-instruction sum construction),
(ii) the Boolean output produced by two or more
instructions with Sigma computed in the remaining
instructions over a pool including those
intermediates, and (iii) any mixture of (i) and (ii).
These shapes are not the E2 shape EXP-033 named, and
the only instrument that covers them, the full-cone
CEGIS at L = 5, remains INCONCLUSIVE: EXP-033 timed
out at 600 s on an 82-example seed, and EXP-042 adds
two further timeouts at 1,500 s and 1,400 s on a
22-example seed, one per cone. H-033-02 therefore
stays open in that residual generality only. Anything
outside vocabulary V is out of scope by definition.

## 7. Files and reproducibility

  src/exp042_e2_synth.py: gates, control and the E2
  synthesis (the decisive instrument).
  src/exp042_fullcone.py: the catch-all driver
  (imports the EXP-033 cone synthesis unchanged).
  PROOFS/ and RAW_RESULTS/: one JSON per run, named
  exp042_e2_<cone>_<stage>_<timestamp>.json and
  exp042_fullcone_<cone>_<timestamp>.json, plus the
  console logs (control_a.log, s1_a.log, s1_e.log,
  fullcone_a.log, fullcone_e.log).

Rerun, from research/sha256d/exp042, with the lab
venv python (~/workspace/bitcoin-autonomous-lab/
.local/z3venv/bin/python):

  src/exp042_e2_synth.py a gates
  src/exp042_e2_synth.py e gates
  src/exp042_e2_synth.py a control 600000
  src/exp042_e2_synth.py a s1 1500000
  src/exp042_e2_synth.py e s1 1500000
  src/exp042_fullcone.py a_cone 1500000
  src/exp042_fullcone.py e_cone 1400000

(The last argument of the synthesis script is the
per-query timeout in milliseconds.)
