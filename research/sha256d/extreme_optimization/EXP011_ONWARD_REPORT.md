# Experiment Batch Report: EXP-011 to EXP-015

Date: 2026-11-14. This batch is Part D of the Next
Research Phase order (five highest-priority new
hypotheses, implemented separately, production
baseline preserved). Part B (the Y-series registry)
is HYPOTHESIS_REGISTRY_Y.md in this directory; Part C
(the performance ceiling report) is
PERFORMANCE_CEILING.md. Part A (the post-sync
decision closure) is handled separately by its own
watcher; EXP-010 is reserved for it in the registry
numbering, and no Part A work was done here.

Kernels: src/avx512_mb2.c (EXP-011), src/
avx512_mb_tern.c (EXP-012), src/avx512_mb_share.c
(EXP-013), src/avx512_mb_kw.c (EXP-014),
src/bitslice32.c (EXP-015). Tests:
tests/test_exp011_onward.py over the shared gate set
in tests/gates.py. Proofs:
proofs/boolean_cone_search.py and
proofs/boolean_cone_results.json. Raw benchmarks:
benchmarks/exp011_onward_kernels.json (session C)
and benchmarks/exp011_confirm.json (session B);
session A's figures were printed by the same script
and are transcribed below (its JSON was overwritten
by session B before archiving; the rerun that
produced session C restored a full combined record).

Machine and conditions: EPYC 9D25 KVM guest, 4
vCPUs capped near 1.5 effective CPUs, live mainnet
pool miner and pruned mainnet node (still in
initial block download) running throughout.
Contention in these sessions was the worst of the
programme so far: individual configuration spreads
ran from 21 percent (bitslice, characteristically
stable) to 250 percent. Every rate below is a
median of 5 interleaved rounds of 1M hashes unless
stated, and every cross-kernel claim is made
against the same session's AVX-512 MB16 baseline,
never across sessions.

Correctness, all five variants: the full gate set
passed before benchmarking: 108,000 randomized
SHA-256d differentials versus hashlib per variant
(9 trials of 12,000, zero mismatches), genesis
digest and genesis search (nonce 2083236893),
boundary nonces and ranges (max-only, range ending
exactly at 2^32, crossing rejected with -2, empty
rejected with -1), five template variations tracked
against hashlib, target exact-equality accepted and
target-minus-one rejected, regtest-easy candidate
set equal to a Python recount (82 candidates over
20,000), and exact accounting including each
variant's group semantics (the genesis early-exit
probe ends at attempted exactly 50,016 for all
five variants; partial-group backend accounting
asserted per variant: 100,016 for the 16-lane
family at count 100,003, 100,032 for bitslice).

## EXP-011 (Y-series candidate, dual-batch MB): two interleaved 16-lane batches per worker

Hypothesis: the multi-buffer analogue of H-01
stream interleaving. One worker advancing two
independent 16-lane batches in a single round loop
(batch A's round t immediately followed by batch
B's round t) hides vector round latency the way
SHA-NI streams hid RNDS2 latency.

Method: src/avx512_mb2.c adds v_compress16x2 (a
round-step macro instantiated for two state sets)
and v_group2 (32 lanes per dual step); the walker
uses dual steps whenever at least 17 nonces remain
and the original single-group path below that.
Accounting is 32-group atomic; dummy lanes are
computed, never stored, never counted as coverage.

Assembly: v_compress16x2 is 239 instructions
(2.06x the 116-instruction single compress), with
14 VPTERNLOGD, 20 VPADDD and 48 VMOVDQA64: both
batches' states and schedule rings are
memory-backed, so the interleave is at scheduling
level, not register-resident. That is the design's
known cost and the target of Y-023.

Benchmarks (median H/s, ratio to same-session
MB16 in brackets):
- Session A: 1 thread 3,133,782 [0.97x];
  2 threads 8,267,078 [2.27x].
- Session B (confirmation, 3 contenders):
  1 thread 4,837,853 [1.41x];
  2 threads 3,465,514 [0.64x], with two late
  samples at 9.86M and 11.26M as load fell.
- Session C: 1 thread 2,101,533 [0.58x];
  2 threads 4,807,109 [1.15x].

Conclusion: NOT a verified improvement. The
direction is positive in three of six
session-configurations and the session A 2-thread
median is the highest 2-thread figure recorded in
the programme, but the result does not reproduce
across sessions on this guest, and the lab's
standard (EXP-004) is reproduction. Tier:
PROMISING HYPOTHESIS with measured support. The
mechanism has the H-01 precedent, and the assembly
record names the next design step (Y-023,
register-resident dual batch).

## EXP-012 (Y-013 class): VPTERNLOGD Boolean cone, searched and proven

Hypothesis: Ch and Maj, and the sigma XOR triples,
each cost several classic vector ops per round; if
a single ternary-logic instruction computes each,
the MB round sheds about 6 ops per round.

Formal work (the durable result of this
experiment): proofs/boolean_cone_search.py
establishes, first, that the VPTERNLOGD immediate
realizing each function is unique: Ch = 202
(0xCA), Maj = 232 (0xE8), XOR3 = 150 (0x96), found
by exhaustive search over all 256 immediates
against the 8-row truth tables (a complete proof
for a bitwise instruction). Second, an exact
op-count breadth-first search over classic
two-input ops (AND, OR, XOR, ANDNOT, free negated
leaves) proves the classic minima: Ch needs 3 ops,
Maj needs 4 ops, XOR3 needs 2 ops (closure level
sizes 8, 38, 152, 232, 256 tables). Third, z3
bit-vector proofs (UNSAT) that the closed forms
read off the winning tables equal the reference
Ch and Maj at 32-bit width, plus a 1,000,000
sample word-level differential with zero
mismatches.

Implementation and assembly: src/avx512_mb_tern.c
replaces every Boolean cone in v_compress16 with
the explicit ternlog forms. The compiled hot
function is 111 instructions with 6 VPTERNLOGD,
against the baseline's 116 instructions with 7
VPTERNLOGD: gcc had already discovered this
optimization in the baseline (the fact was first
noticed in this batch's pre-check objdump). The
explicit form is therefore a guarantee, not a
gain.

Benchmarks (ratio to MB16): session A 0.81x
(1 thread), 0.90x (2 threads); session C 0.97x,
1.13x. Parity within session noise, exactly as
the assembly comparison predicts.

Conclusion: VERIFIED as a codegen fact (the
compiler already exploits VPTERNLOGD in this
kernel; the Boolean cone is at its proven minimum
in the shipped code) and closed as a performance
hypothesis (no gain available). The pair
(baseline, ternlog twin) is adopted as the
programme's equal-pair noise control (Y-103).
Tier: the formal results are established facts;
the performance claim is a recorded null.

## EXP-013 (cross-lane sharing): shared block-2 prefix and schedule words in MB

Hypothesis: in MB, all 16 lanes share the block-2
schedule words W0..W2, the padding words W4..W15,
and the expanded words W16 and W17 (whose inputs
exclude the nonce word W3, per the corrected W18
analysis), and the working state after round 2 is
lane-independent. Computing rounds 0..2 once,
scalar, per template and broadcasting the shared
schedule words should remove 3 of 64 block-2
rounds and 2 schedule generations per group.

Method: src/avx512_mb_share.c computes the prefix
state and W16/W17 in v_template_init (scalar, once
per template) and starts the vector compress at
round 3 with a from-round compress variant.

Benchmarks (ratio to MB16): session A 1.06x
(1 thread), 1.11x (2 threads); session B 1.21x,
0.65x; session C 0.51x, 0.86x.

Conclusion: NOT reproduced. The predicted effect
(about 2.4 percent of per-nonce rounds) is an
order of magnitude below this guest's session
noise, the same conclusion H-03 reached in
EXP-002 for the SHA-NI family. The implementation
is correct and retained; the claim is neither
confirmed nor refuted at this noise floor, and
the report says so rather than rounding it into
either. Tier: PROMISING HYPOTHESIS, effect below
the measurable floor on this VM. Its natural home
is a combination (Y-093) or a quieter machine.

## EXP-014 (K+W folding): constant-folded round operands for template-fixed rounds

Hypothesis: for block-2 rounds 0..17 except round
3, the schedule word is a per-template constant
in every lane, so K[t] + W[t] folds once per
template and each such round saves one vector add
in T1 (17 adds saved of the block-2 total).

Method: src/avx512_mb_kw.c precomputes kw[t] =
K[t] + W[t] for the 17 rounds in the template and
uses a dedicated block-2 compress consuming the
folded operand (rounds 16 and 17 take their
schedule words from the shared scalars, as in
EXP-013, because the fold needs them).

Benchmarks (ratio to MB16): session A 0.65x
(1 thread), 0.93x (2 threads); session C 0.64x,
1.09x.

Conclusion: no gain as implemented, in any
session. The per-round broadcast of the folded
scalar and the branch structure around it cost
what the saved add was worth; the fold count (17
adds of about 240 effective ops per hash, about
7 percent of block 2's rounds but under 2 percent
of the whole) was always near the floor, and the
implementation overhead eats it. Tier: recorded
negative for this implementation shape; the
generalized recurrence-level version is Y-070
and would need its dependency analysis to show a
much larger foldable set before it is worth
building. Extends X-024 (template-fixed operands)
with a measurement in the vector family.

## EXP-015 (bitslice): 32-lane bitsliced SHA-256d, implemented and measured

Hypothesis (extending X-029, which was an analytic
bound only): a bitsliced implementation, with 32
hashes transposed into bit planes so rotations are
free (plane reindexing) and Boolean functions cost
one scalar op per plane, might beat the vector
family despite its ripple-carry additions.

Method: src/bitslice32.c implements the full
SHA-256d in bit planes: state as 32 uint32_t
planes per word, ripple-carry plane addition
(about 5 ops per bit per add), plane-reindexed
rotations and shifts, a rotating state offset so
rounds do not copy state, scalar midstate
broadcast into planes, group-atomic accounting
over 32 lanes.

A real bug was caught by the gates during
development and is recorded because it is the
kind the gates exist for: the first build's
bs_add re-read its input plane after writing the
output plane in the same iteration, corrupting
the carry whenever output aliased input (nearly
every call). The Python replica of the logic was
proven correct against hashlib first, isolating
the bug to the C transcription; the fix captures
operands before writing. All gates then passed,
including 108,000 differentials.

Benchmarks: 109,921 and 116,330 H/s medians at
1 thread; 172,365 and 186,090 at 2 threads;
spreads 21 to 41 percent, the tightest in the
batch. That is about 0.03x of the MB16 baseline
and about 0.13x of production in the same
sessions.

Conclusion: REJECTED by measurement on this core.
The ripple-carry addition tax (roughly 160 ops
per 32-bit add across planes, several adds per
round) exceeds the rotation savings by an order
of magnitude, confirming X-029's analytic bound
with an implementation. Tier: established
negative. The implementation is retained as the
reference for any future hybrid (Y-004) and
because a measured refutation is a programme
asset.

## Combination run

None was run, by the phase order's own rule:
combine only individually successful
transformations after their individual behaviour
is understood. No variant in this batch achieved
a reproduced individual improvement (EXP-011 and
EXP-013 are unseparated, EXP-014 is a negative,
EXP-012 is parity by design, EXP-015 is refuted),
so there was nothing eligible to combine. The
recorded follow-on is Y-093 (share inside dual
batch) and Y-023 (register-resident dual batch),
to be run in a quieter window, ideally the
post-sync window Part A waits for, where the
noise floor may finally sit below these effects.

## Conclusions by tier

VERIFIED IMPROVEMENT (measured and reproduced):
none in this batch. The batch's honest headline
is that it produced no new verified kernel
improvement, and it produced several things that
are worth as much: two closures, one refutation,
one formal result set, and a sharper map of where
the remaining headroom lives (PERFORMANCE_
CEILING.md sets the MB kernel within about 1.5x
of its instruction-count bound at guest clocks).

Established facts (not improvements, but settled):
the Boolean cone is at its proven minimum in the
compiled MB kernel (EXP-012, with unique ternlog
immediates and z3 proofs); bitslicing loses by
about 30x on this core (EXP-015); K+W folding as
implemented does not pay (EXP-014); the dual-batch
compress's cost is its memory-backed state
(EXP-011 assembly audit).

PROMISING HYPOTHESIS: dual-batch interleaving
(EXP-011, positive in half the configurations,
mechanism precedented by EXP-003) with its
register-resident successor Y-023; cross-lane
prefix sharing (EXP-013) as a combination
ingredient whose effect is below this VM's noise
floor; the Y-registry's top-ranked untested
entries (see the batch's Part B summary in the
registry itself).

UNPROVEN BREAKTHROUGH: unchanged from the
ceiling report. Nothing in this batch reduces
the 125-round per-nonce floor or beats the
op-count bounds of PERFORMANCE_CEILING.md
section 2; the two registered ideas that even
aim there (Y-065 nonce-affine schedule
decomposition, Y-075 round-3 delta decomposition)
remain derivations that do not yet exist.
