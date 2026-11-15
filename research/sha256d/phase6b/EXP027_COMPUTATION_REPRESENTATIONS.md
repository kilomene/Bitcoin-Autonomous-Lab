# EXP-027: New Computational Representations

Experiment ID: EXP-027 (reserved 2026-11-14, Phase 6B).
Status: COMPLETE (executed 2026-11-15). Track: B
(breakthrough discovery).
Verdict at experiment level: the predeclared
characterised search is complete. Every named
candidate space ends in one of the four required
states. No candidate survived proof plus costing,
so no kernel was compiled and no EXP-017 benchmark
was triggered. Nothing is integrated. The result is
a successful EXP-027 with a negative outcome: the
spaces outside the EXP-020 vocabulary that this
experiment searched are closed by proof,
counterexample, census or measured price, each
within its stated scope. No statement in this record
is a global lower bound on exact SHA-256d.

Host of record: AMD EPYC 9D25 126-Core Processor,
guest 4 vCPUs, about 1.5 effective shared CPUs.
Flags present and relevant: avx512f, avx512bw,
avx512dq, avx512vl, avx512vbmi, avx512vbmi2,
avx512ifma, gfni, vaes, sha_ni. Builds that needed
GFNI used -O3 -mavx512f -mavx512bw -mgfni (the extra
flag recorded per candidate); hosts without GFNI
exist in this fleet's history, so a GFNI dispatch
would have needed a probe and fallback in any case.

Incumbent costs used throughout (EXP-020 census,
joint round plus schedule = 28 vector ops: 12 offset
ops, 6 combines, 10 adds): Sigma0/Sigma1 4 ops each
(3 rotations + 1 XOR3 ternlog), sigma0/sigma1 4 ops
each, Ch 1 ternlog, Maj 1 ternlog, T1 five-operand
sum 4 VPADDD, schedule four-operand sum 3 VPADDD.

Artifacts: proofs/exp027_proofs_20261115T055244Z.json
(legs L1 to L8), proofs/exp027_vocab_search_
20261115T055625Z.json (searches S1 to S3),
benchmarks/exp027/exp027_records_20261115T055700Z
.json (hardware differentials, price micro),
benchmarks/exp027_proofs.py, benchmarks/exp027/
exp027_hw_diff.c, benchmarks/exp027/exp027_micro.c,
phase6/src/exp027_vocab_search.py (the discovery
harness extension; discovery_harness.py itself is
unmodified, spot-checked in S3).

## Predeclared hypothesis and criterion

Unchanged from the reservation stub: exact
representations outside the vocabulary
{VPADDD, VPTERNLOGD, classic bitwise, VPROLD,
VPSRLD} might price below the incumbent for at
least one cone. Per candidate: exact input and
output defined; equivalence proven (z3 UNSAT) or a
SAT counterexample filed; differential testing at
programme standard (1,000,000 samples for
cone-level forms); costing under the phase cost
model with the search vocabulary stated; compiled
candidates gated and benchmarked under EXP-017
before any performance language. Criterion 5 was
not triggered by any candidate, and this record
says so wherever a lesser experiment might have
substituted a micro number for a kernel verdict.
The one measured price below (candidate 2) is an
EXP-019-style form price, labelled as such.

## C1. GFNI affine forms

Exact input/output: a candidate form maps a 32-bit
state word (or the (e,f,g) / (a,b,c) triple) to the
Sigma, sigma, Ch or Maj output word, exactly, using
VGF2P8AFFINEQB as its nonlinear or linear engine.

Equivalence evidence. (a) The four sigma maps ARE
GF(2)-linear: z3 UNSAT for Sigma(a^b) != Sigma(a) ^
Sigma(b), for Sigma0, Sigma1, sigma0, sigma1 (L1).
So GFNI networks for them exist in principle.
(b) Ch and Maj are NOT GF(2)-affine: z3 SAT
produced affinity violations for both, and both
counterexample models were re-verified numerically
in plain Python (L1). No affine instruction, GFNI
included, computes Ch or Maj, in any composition
that stays affine. (c) A single GFNI instruction
for Sigma0 is refuted for every matrix, constant
and preceding byte shuffle: the dependency census
(proofs L2, search S2) shows every Sigma0 output
byte depends on all four input bytes (fan-in
exactly 3 per output bit), while a per-byte affine
instruction makes each output byte a function of
exactly one input byte. The filed pair x =
305419896, x' = 305420152 differs only in byte 1
yet Sigma0 differs in byte 0. (d) The hardware
semantics model used here was itself verified:
1,000,000 random bytes through VGF2P8AFFINEQB vs
the scalar model, 0 mismatches, after two wrong
conventions were caught and discarded by the same
differential (records file, T1).

Costing. Any GFNI form of Sigma0 needs at least 4
partial vectors (one per input byte, by the census)
each costing at least a shuffle plus a GFNI, plus
3 XOR combines: floor 11 ops. The byte-slice
construction costs 35 ops (4 slices x (1 broadcast
+ 4 GFNI + 3 byte blends) + 3 XOR). Incumbent: 4
ops. Dispatch would also need GFNI probing and a
fallback for hosts without it.

Verdict: proven-equivalent-and-costed-out for the
sigma maps (linearity proven, construction and
floor both far above the incumbent); refuted by
counterexample for Ch and Maj (non-affinity) and
for the single-instruction Sigma0 form.
Classification: ESTABLISHED NEGATIVE.

## C2. VPSHUFB-based rotations

Exact input/output: ROTR(x, k) for the rotation
amounts the round and schedule use (2, 6, 7, 11,
13, 17, 18, 19, 22, 25), computed with byte
shuffles as the moving part.

Equivalence evidence. (a) Pure shuffle forms are
refuted exhaustively: the automated search S1
tested all 625 per-dword byte-select patterns
(zeroing allowed) against ROTR13 and against
Sigma0 on 10,038 discriminating inputs; survivors
0 for both targets. The filed witness (L3) is one
input whose ROTR13 byte 0 (98) is none of its own
bytes and not zero, which alone kills every pure
pattern. (b) The mixed construction IS exact:
byte-rotate by one byte (what a within-dword
shuffle does, equal to ROTR 8) followed by ROTR 5
as shift/or equals ROTR 13, z3 UNSAT (L3), and the
compiled construction matched scalar ROTR13 on
1,000,000 random dwords, 0 mismatches (records
T2). (c) Byte-multiple rotations (8, 16, 24) are
one shuffle, but no Sigma or sigma rotation amount
is a byte multiple except none; the amounts are
listed above.

Costing and measured price. The mixed construction
is 4 ops (shuffle, VPSRLD, VPSLLD, VPOR) against 1
VPROLD. An EXP-019-style register-resident price
micro (three sessions, forms verified equal before
timing) measured the shuffle form at 2.00x the
VPROLD price in every session (ratios 1.999,
1.998, 2.005). The 3-op shift/or form tied VPROLD
on throughput (1.000, 1.000, 1.002; the two shifts
issue on separate ports) but costs 3 census ops
against 1 and a two-level dependency chain against
one level, so it wins nothing the census or the
chain can spend. A first, buffer-streaming micro
measured the load path instead and was discarded;
the records file says so.

Verdict: pure forms refuted by exhaustive search
and counterexample; mixed form proven-equivalent-
and-costed-out, with a measured price against it.
Classification: ESTABLISHED NEGATIVE.

## C3. Alternative state representations

Exact input/output: the eight 32-bit state words
carried between rounds in a transformed domain,
with every round function computed exactly.

Rotated state (carry each word pre-rotated by a
fixed k). The temptation is real and proven: Ch
and Sigma0 commute with rotation, z3 UNSAT for
both equivariances (L5). The representation dies
on addition: z3 SAT counterexample (a =
4238003950, b = 1835872561, k = 7), numerically
rechecked, shows ROTR(a+b) != ROTR(a) + ROTR(b),
because carries propagate along the unrotated bit
order. Every round performs adds whose operands
and results are state words (10 of the 28 census
ops), so each add would need its operands
unrotated and its result re-rotated: the
representation pays rotations to save rotations.
Refuted by counterexample as a pure representation;
costed out as a hybrid.

Byte-swapped state. Same shape, same death: z3
SAT counterexample (a = 2105020371, b =
1660427895), numerically rechecked, shows byte
swap does not commute with addition either (L5).
Production already pays the endian conversion
once at the message and digest boundary, which is
the cheapest place it can be paid. Refuted by
counterexample.

Bitsliced state. Closed by measurement before
this experiment: EXP-015 implemented the full
32-lane bitsliced form and measured about 0.03x
of the multi-buffer kernel (ripple-carry plane
adds swamp the free rotations). Not re-run;
cited as the standing measurement. ESTABLISHED
NEGATIVE on this core.

Cross-lane delta state (store one lane's state
and per-lane differences). Premise refuted by
EXP-016: state affinity in the nonce dies at S_8
and every word is fully nonlinear from S_9, so
past round 8 no exact cheap relation between
lanes exists to store; and materialising a lane's
state from (base, delta) costs an XOR per word
per round while saving no cone. The template-
fixed prefix that does exist (rounds 0 to 2) is
EXP-013's, measured below the noise floor there.
Refuted premise (EXP-016 proof) plus costing.

Redundant (sum, carry) state pairs are the
carry-save candidate and are treated in C4, where
the consumption argument closes them.

Verdict: every state representation examined is
refuted by counterexample, refuted in premise by
an earlier proof, or closed by an earlier
measurement. Classification: ESTABLISHED
NEGATIVE (each sub-form with its own evidence
class, stated above).

## C4. Carry-save beyond the schedule design

Exact input/output: the round's addition cones
(T1, T2, the (a', e') pair, the state update)
carried in redundant (sum, carry) form across one
or more rounds, exactly.

What EXP-019 closed was the schedule recurrence's
pricing. This experiment's new element is the
consumption structure of the round cones, which
EXP-019 did not price. Equivalence of the
compressor itself is re-proven here: z3 UNSAT for
a + b + c != s + (Maj(a,b,c) << 1) (L4), and the
identity matched on 1,000,000 random triples in
scalar C (records T3).

The structural fact: in the schedule, a sum's
consumers sit at separations 0, 1 and 6 rounds,
and EXP-019 priced resolution against those. In
the round function, every state word produced by
an addition is consumed BITWISE in the very next
round: a' feeds Sigma0 and Maj, e' feeds Sigma1
and Ch, and the pass-through words feed Ch and
Maj. A bitwise consumer cannot read a redundant
pair at all; the pair must be resolved (one
VPADDD) before any use, so the deferral distance
for every round addition is exactly 0 rounds.
There is no second consumer class to amortise
against. The one arithmetic consumer, the next
round's T1, could absorb a pair only by becoming
a six-operand sum, which costs the same extra add
that resolution costs, and its own outputs are
again bitwise-consumed.

Costing at the standing resolution price
(EXP-019: one software compressor = 3
instructions, 2 VPTERNLOGD + 1 VPSLLD): T1 costs
6 ops with one carry-save level or 8 with two,
against 4 VPADDD (EXP-020 pricing table, which
used this same corrected price). The schedule sum
costs 5 or 7 against 3. Carry-save loses on count
at distance 0 everywhere in the round, and the
consumption argument shows distance 0 is the only
distance the round offers.

Verdict: proven-equivalent-and-costed-out.
Classification: ESTABLISHED NEGATIVE. Scope note:
this closes carry-save for the SHA-256 round and
schedule cones on this instruction set at the
standing compressor price; a future instruction
that resolves a pair in one op would reopen the
pricing, and would be a new experiment.

## C5. Addition networks, delayed carry, mixed forms

Exact input/output: the five-operand T1 sum and
the four-operand schedule sum, exactly, under
network shapes other than the incumbent add tree.

Counting floor (stated with its vocabulary): in
any network of binary additions, reducing 5
operands to 1 sum takes at least 4 adds, and the
incumbent achieves 4; reducing 4 takes at least 3
and the incumbent achieves 3 (EXP-020's addition
BFS agrees: T1 minimum 4, schedule minimum 3).
Depth floor for 5 operands is 3 levels, also
achieved. No binary-add network beats the
incumbent's count; this is a counting statement
about binary-add networks, not a global bound.

Carry-lookahead networks (Kogge-Stone shape):
costed by census. A software prefix add spends
about 2 ops on generate/propagate, about 3 ops
per prefix level (two combines plus an alignment
shift) over 5 levels for 32 bits, and a final XOR:
about 18 ops against 1 VPADDD per addition.
Labelled a cost-model census estimate; no form
was built, because the census gap is an order of
magnitude. Proven-equivalent in principle
(textbook construction), costed out.

Delayed carry propagation across rounds: refuted
by the C4 consumption argument (deferral distance
0 for every round addition; the schedule's
binding consumer sits at separation 1 per
EXP-019). A carry produced in round t has no
consumer in round t+1 that can accept it
unresolved.

Boolean/arithmetic mixed form (52-bit
accumulation, AVX-512 IFMA): represent the T1 sum
in a 52-bit accumulator via VPMADD52LUQ with a
multiplier of 1, masking to 32 bits once at the
end. Exactness proven: z3 UNSAT for the five
32-bit operands' sum reaching 2^52, and UNSAT for
its low 32 bits differing from the mod-2^32 chain
(L6); the accumulation semantics matched the
chain on 1,000,000 random operand sets in a numpy
model, 0 mismatches, maximum sum under 2^35
(records file; the instruction itself was not
executed, and the record labels the differential
as a model differential). Cost: 4 accumulations +
1 mask = 5 ops against 4 VPADDD for T1, and the
accumulator domain cannot persist across any
bitwise consumption (C4), so the form buys
nothing within a round either. Proven-equivalent-
and-costed-out. Classification: ESTABLISHED
NEGATIVE for the accumulation form; the counting
floor and the lookahead census close the rest of
this space at the stated scopes.

## C6. Joint optimisation across rounds and compressions

Exact input/output: two consecutive rounds (or
the three compressions of SHA-256d) computed
jointly, exactly, with subexpressions shared
across the boundary wherever the graphs allow.

Across rounds. Hash-consing census (L7): two
composed rounds built as interned DAGs create 17
nontrivial nodes each, and the number of
nontrivial nodes shared across the round boundary
is 0. Round t+1's cones take round t's outputs
(a', e') and the pass-through words as atoms;
nothing computed in round t is recomputed in
round t+1, and nothing in round t+1 coincides
with a round-t subterm. The only sharing inside a
round, T1 feeding both a' and e', is already the
incumbent's structure. This is an exact statement
about shared subterms in the DAG model searched;
it is not a bound on restructurings that change
the graph's shape, and the record does not claim
one. Within that scope the cross-round sharing
premise is refuted: there is nothing to share.

Across compressions. The sharing that exists is
already in production: block 1 of the inner
compression is template-fixed (the 67-round
precomputation ceiling) and the outer compression
admits zero reuse (foundation result). The
remaining question was whether part of the outer
compression can execute before the inner finishes.
Dependency census (L7): all 48 computed schedule
words of the outer compression depend on the
inner digest (its message words 0 to 7 ARE the
digest, and the recurrence propagates the
dependence to every computed word), and zero
complete outer rounds are digest-independent
(rounds 0 to 7 consume digest words directly;
rounds 8 to 15 consume state already dependent on
them). Cross-compression partial execution is
refuted by dependency, exactly.

Verdict: refuted by census within the stated DAG
and dependency models. Classification:
ESTABLISHED NEGATIVE at that scope. Left open,
explicitly: graph restructurings that are not
sharing (for example a fused two-round Boolean
network found by a solver over 192 rounds of
state) remain unsearched; the blocker is search
space size, stated in OPEN_PROBLEMS terms in the
summary below, not a claim that nothing exists.

## C7. Algebraic partial evaluation and schedule forms

Template partial evaluation. The template-fixed
fragment of block 2 (rounds 0 to 2, schedule
words W16/W17) is EXP-013's ground: implemented
there, effect about 2.4 percent of per-nonce
work, measured below this VM's noise floor,
retained as a combination ingredient. EXP-027
adds nothing there and does not re-measure it.
K+W constant folding is EXP-014's, rejected by
measurement there. Both are cited, not reopened.

A GF(2)-linear schedule representation is refuted
by EXP-016: W20 is the first schedule word whose
nonce dependence is fully nonlinear (z3
counterexample, numerically verified there), and
the recurrence's modular adds keep every later
word out of any purely linear form. The linear
parts that do exist (the sigma maps, C1) are
already single ternlogs in the incumbent.

Direct (unrolled) schedule representation.
Census (L8): the recurrence DAG costs 8 ops per
computed word, 384 ops for W16 to W63. The
unrolled expression tree, sharing nothing, costs
49 nodes at W20, 97 at W24, 209 at W28, 401 at
W31 and exactly 259,905 nodes at W63. A direct
form either pays that growth or reintroduces
sharing, and shared unrolling IS the recurrence
DAG. Proven-equivalent-and-costed-out by census.

Symbolic simplification and dependency-graph
restructuring within one round are EXP-020's
searched ground (28-op optimum inside its
vocabulary); EXP-027's contribution there is the
extended-vocabulary check in C8, which found no
cone where an outside-vocabulary form undercuts
the incumbent's extraction.

Verdict: the schedule-representation and partial
evaluation spaces are costed out or refuted as
above, with EXP-013's prefix sharing left exactly
where EXP-013 left it (a real, sub-noise
ingredient, neither promoted nor closed).
Classification: ESTABLISHED NEGATIVE for the
linear and direct schedule forms; EXP-013's form
keeps its own earlier classification.

## C8. Automated instruction selection, extended vocabularies

Tooling: phase6/src/exp027_vocab_search.py, a new
file extending the discovery harness (the harness
itself is unmodified; S3 spot-checks it by
re-deriving Ch's ternlog immediate 0xCA with a z3
UNSAT proof through the harness's own gate).

Searches run: S1, the exhaustive single-shuffle
search of C2 (625 patterns, 10,038 inputs, 0
survivors for ROTR13 and for Sigma0). S2, the
byte-locality computation behind C1's refutation
of every single-instruction GFNI form (Sigma0 is
not byte-local, so the 2^64 matrix space needs no
enumeration). S3, the extraction table: for each
cone, the best cost under the EXP-020 vocabulary
and under each single extension (GFNI, VPSHUFB,
carry-save at the corrected price, VPMADD52).
No extension lowers any cone: Sigma cones stay 4
(GFNI floor 11, construction 35), rotations stay
1 (shuffle best 4), Ch/Maj stay 1 (GFNI refuted),
T1 stays 4 (carry-save 6, IFMA 5), the schedule
sum stays 3 (carry-save 5, IFMA 4), and the joint
census therefore stays 28 within the searched
forms. That sentence is a statement about the
vocabularies and constructions searched, recorded
with them in the S3 artifact; it is not a global
lower bound, and this record makes no such claim.

Verdict: the automated search over the extended
vocabularies is complete for the stated spaces
and finds no improvement. Classification: the
search itself is the deliverable; its outcome is
an ESTABLISHED NEGATIVE for the extended
single-instruction and per-cone construction
spaces searched.

## Depth statement

Deep treatment (proofs, 1,000,000-sample
differentials, and where relevant a measured
price): C1 GFNI, C2 shuffle rotations, C4
carry-save, C5 addition networks and the IFMA
form, C8 automated selection. Medium treatment
(formal counterexamples plus standing programme
measurements): C3 state representations. Triage
by exact census: C6 joint optimisation (the
censuses answer the sharing and dependency
questions exactly, which is why no solver search
was spent there) and C7 schedule forms (census
plus the standing EXP-013/014/016 results). The
one space left explicitly open is non-sharing
graph restructuring across the round boundary
(C6), blocked by search-space size; everything
else named in the stub is closed at a stated
scope.

## Summary of verdicts

| Space | End state | Tier |
|---|---|---|
| GFNI affine forms | costed out (sigma); refuted (Ch, Maj, single-form Sigma) | ESTABLISHED NEGATIVE |
| VPSHUFB rotations | refuted (pure); costed out with measured price (mixed) | ESTABLISHED NEGATIVE |
| State representations | refuted by counterexample / prior proof / prior measurement | ESTABLISHED NEGATIVE |
| Carry-save beyond schedule | proven equivalent, costed out (distance-0 consumption) | ESTABLISHED NEGATIVE |
| Addition networks, delayed carry, mixed | counting floor met by incumbent; lookahead costed out; IFMA costed out; delay refuted | ESTABLISHED NEGATIVE |
| Joint rounds / compressions | refuted by census at stated scope; non-sharing restructuring left open with blocker | ESTABLISHED NEGATIVE (scoped); one sub-space OPEN |
| Partial evaluation, schedule forms | costed out / refuted; EXP-013 form unchanged | ESTABLISHED NEGATIVE |
| Automated selection over vocabularies | search complete, no cone improved | ESTABLISHED NEGATIVE |

No VERIFIED IMPROVEMENT and no PROMISING
HYPOTHESIS arises from EXP-027. No kernel was
built, so no machine-code audit or EXP-017
benchmark exists for this experiment; the
predeclared gates for compiled candidates were
never triggered, and no performance language is
used anywhere in this record beyond the labelled
form-price micro of C2. Production is
byte-identical (verified by sha256 at close), the
live miner was not touched, and nothing here is
integrated or proposed for integration. The
targets stand at full height: 500 GH/s minimum
objective, 140 TH/s larger objective; EXP-027 is
discovery work and claims nothing toward them.
