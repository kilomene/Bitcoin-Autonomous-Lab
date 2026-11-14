# Phase 6, Open Problems

The questions this phase exists to answer, stated
precisely enough that an answer, positive or
negative, is recognisable. Each problem names what
would settle it. Nothing here is a claim.

## OP-1. Does any equivalent computation graph evaluate SHA-256d with materially fewer primitive operations than the conventional graph?

The central Workstream A problem, opened formally
by the Task 2A correction: the conventional count
(125 round evaluations per nonce after the 67
reusable rounds) is not a proven lower bound.
Settled by: a proven candidate graph with a lower
priced cost under the discovery system's cost model
(COMPUTATION_GRAPH_RESEARCH.md), or cone-by-cone
characterisation results that bound what the
searched spaces contain. EXP-020 is the first
campaign. EXP-016 closed the nonce-separation
sub-question negatively; the general problem is
untouched by that result.

## OP-2. What is the true cost structure of the schedule recurrence under redundant representations?

Carry-save and related representations defer carry
propagation; whether the deferral survives the
schedule's resolution points (feeding s1 and T1)
at a profit is unpriced. Settled by: EXP-019's
per-distance price list, then the Y-001 engine if
the list shows a profitable distance class.

## OP-3. Why does the AVX-512 kernel's rate not track steal like the scalar control?

Observed in EXP-007, sharpened in EXP-010
(correlations +0.221 versus -0.521), mechanism
unknown. Candidate mechanisms: host wide-vector
issue behaviour, frequency behaviour under vector
load, the kernel's own memory-backed staging.
Settled by: Y-097's heterogeneous pairing and
EXP-018's spill audit, read together; either could
falsify one candidate, and the problem stays open
until one mechanism predicts a new observation.

## OP-4. Can any kernel decision be made reproducibly on a capped, shared VM, and under what statistic?

Three decision failures (EXP-004, batch rerun,
EXP-010) say the current procedure cannot separate
candidates whose medians differ from production by
2 to 3x. Settled by: EXP-017's three sub-verdicts,
including a control null (Y-103) and an injected-
effect recovery (Y-101). If EXP-017's answer is
that no statistic on this VM decides at the effect
sizes available, that is a programme-level fact
that reroutes kernel work to bare-metal or
dedicated-window assumptions, stated as such.

## OP-5. What does the register file actually permit at vector width?

The dual-batch shape wants 32 zmm to hold 16
states plus schedule; EXP-011's implementation
spilled state to memory 48 times per body. Whether
a full-unroll register-resident form exists is a
construction question (EXP-018), and its negative
form (an argument from live-range width that no
such form exists at this unroll depth) would be
equally valuable and is currently unproven either
way.

## OP-6. Where does confirmation become the binding cost as kernel rates rise?

EXP-009 priced confirmation at about 1.1
microseconds per candidate (about 2.8 percent of a
core at regtest density at 6.5M H/s) and node
validation at 3.96 ms median per round trip. The
crossover kernel rate at which confirmation, not
search, bounds a worker is computable from those
numbers but depends on network difficulty (the
candidate density), so it is a function, not a
constant. Settled by: Y-105's repricing at the
next successful kernel decision, recomputed per
deployment shape.

## OP-7. Is there cross-nonce structure beyond the prefix that no dependence argument can see?

EXP-016 proves every state word is fully,
nonlinearly nonce-dependent from round 8 (block
2). Dependence arguments cannot exclude sharing
based on value collisions or algebraic identities
that hold despite full dependence. No candidate
mechanism is registered; the problem is recorded
so that its openness is explicit and so that any
future proposal must name a mechanism, not a hope.
Tier: UNPROVEN BREAKTHROUGH, untouched.

## OP-8. The outer hash

All Phase 6 mathematics so far concerns block 2 of
the inner hash, the only place a single word
varies. The outer hash's input is the full inner
digest: no word is fixed across candidates, so no
precomputation, separation, or prefix structure
applies, and the conventional 64 rounds are the
whole story there under every known technique.
Whether any graph-level structure exists for a
compression whose entire input varies per
candidate is open in the same sense as OP-1 and
is expected to be settled, if at all, by OP-1's
machinery applied to the outer cone.
