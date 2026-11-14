# Phase 6, Computation Graph Research: the automated discovery system

Workstream A asks whether a mathematically
equivalent computation graph can evaluate SHA-256d
with materially less work than the conventional
graph. Phase 6's answer to "how would we know" is
this system: a discovery loop that generates
candidate graphs, proves or kills each one, prices
the survivors, and hands at most a few to the
benchmark harness. Intuition-generated candidates
(the Y registry's method so far) remain welcome,
but they enter the same pipeline at the same gates.

## 1. Objects and scope

The unit of search is the expression DAG over one
of three cones, in increasing size:

- T1 cone: the five-operand modular addition
  network feeding e (Sigma1(e) + Ch(e,f,g) + h +
  K_t + W_t), plus the parallel T2 cone
  (Sigma0(a) + Maj(a,b,c)). Operands are symbolic
  32-bit words; the network's shape (tree structure,
  operand order, carry-save levels) is the search
  space.
- Round cone: T1 and T2 plus the Boolean functions
  and big sigmas of one full round, with the eight
  state words as inputs and (a', e') as outputs.
- Two-round cone: the round cone composed with
  itself, where cross-round subexpression sharing
  becomes visible. This is the largest space the
  system attempts, and only after the smaller cones
  are characterised.

Representations searched, in order: plain modular
addition networks; carry-save (sum, carry) pairs
with priced resolution points (the EXP-019 price
list is the cost model); Boolean networks over
AND, OR, XOR, NOT with VPTERNLOGD as a native
3-input primitive (its cost is one instruction, so
the search prices Boolean subgraphs in ternlog
units, not gate units).

## 2. Candidate generation

Three generators, run in this order per cone:

### 2.1 E-graph equality saturation

Expressions are interned in an e-graph
(src/discovery_harness.py implements a first,
deliberately small version: hash-consed nodes,
union-find equivalence classes, saturation passes,
cost extraction). The rewrite set is stated here in
full; a candidate produced by rules outside this
set is not a saturation candidate and must name
its generator.

Boolean rules (all proven equivalences in this
lab's records): commutativity and associativity of
AND, OR, XOR; De Morgan; XOR as (x or y) and not
(x and y); Ch in its three proven forms (classic,
Ch_alt, and the ternlog form with immediate 0xCA);
Maj in its three proven forms (classic,
Maj_alt_A, Maj_alt_B, ternlog 0xE8); absorption and
idempotence; double negation. Arithmetic rules:
commutativity and associativity of modular
addition; distribution of rotations over XOR is
NOT a rule (false in general) and its absence is
deliberate; addition-chain reassociation is free
(the T1 enumeration in the harness covers all
1,680 ordered full binary trees over the five
operands, 14 shapes times 120 permutations,
proving depth 3 is achievable and minimal, so tree
shape is searched, not assumed).
Ternlog rule: any 3-input Boolean subgraph whose
truth table matches a single immediate becomes one
ternlog node at cost 1 (the harness computes the
immediate from the table, not from a lookup of
known cases).

Saturation runs to a node budget, not to a time
budget, so runs are reproducible on a noisy
machine: budgets are 50k nodes (T cones), 500k
(round cone), and the two-round cone starts only
when the round cone's closure is characterised.
Extraction is by the cost model of section 4.

### 2.2 SAT/SMT-guided rewriting

Where saturation's fixed set cannot reach, a
solver-guided pass proposes rewrites: for a target
subgraph, z3 is asked for an equivalent expression
over a bounded grammar (operators from section 1,
depth bounded per pass), with equivalence checked
by the same UNSAT gate as every candidate. This is
Y-015's engine; it runs on the same cones as 2.1 so
yields are comparable. Grammar depth and solver
timeout are recorded per candidate; a timeout is a
null result, not a failure of the candidate.

### 2.3 Bounded superoptimisation

For the T1 and T2 cones only: enumerate instruction
sequences over the vector instruction subset
(VPTERNLOGD, VPADD, VPXOR, VPSRL/VPSLL pairs for
rotations, VPSHUFB where relevant) up to a length
bound, in the style of classic superoptimisation,
with each sequence's semantics evaluated on random
inputs first (cheap filter) and proven by z3
before recording. Length bounds: 12 instructions
(T cones) in the first campaign. This is the
generator most likely to find forms no human would
write, and the one whose outputs need the assembly
audit of section 5 most.

## 3. The equivalence proof gate

No candidate exists as a programme record until it
carries a proof artifact. The route follows
proofs/boolean_cone_search.py, the lab's existing
pattern (the same code that proved the ternlog
results three ways):

1. z3 bit-vector UNSAT: assert candidate != target
   for symbolic inputs; UNSAT is equivalence.
   proofs/ artifacts are stored as JSON with the
   claim, the solver result, and the exact
   expressions, as discovery_harness.py already
   writes for P6C-001 to P6C-004.
2. Differential check: 1M random inputs through
   both forms in the reference implementation
   (cheap, catches encoding slips the solver
   cannot, such as a transcription error between
   proof expression and benchmark expression).
3. For addition networks, associativity and
   commutativity of modular addition make tree
   reassociation exact by theorem; the record says
   so instead of spending solver time, and the
   differential check still runs.

A candidate that fails the gate is recorded as
REJECTED with its failing artifact; the loop never
silently drops a corpse, because the corpse list is
how the search space gets characterised.

## 4. Cost model and pricing

Extraction and ranking use a stated cost model, in
this order of fidelity: (1) static instruction
census of the extracted form, in the census style
of PERFORMANCE_CEILING.md set C; (2) critical-path
depth of the DAG under unit-latency ops with
addition latency 1 (vector) and rotation pairs
counted as their instruction count; (3) register
estimate from the DAG's live-range width. A
candidate must beat the incumbent on census AND
not lose on depth by more than the census gain;
ties go to the incumbent (the burden of proof is
on novelty). The EXP-019 carry-save price list
plugs into this model as the resolution-cost table
when it exists; until then carry-save candidates
carry their resolution cost explicitly in the
record.

## 5. Compilation and assembly hooks

Proven candidates that survive pricing are compiled
through the programme's existing research-kernel
route: a variant file in extreme_optimization/src/
following the exp00X pattern, built with the
recorded compiler configuration (the record carries
compiler, version, flags, and the source hash).
The assembly audit is mechanical and mandatory:
instruction count of the hot function, frame size,
stack-op count, presence of the intended primitive
instructions (RNDS2, MSG, ternlog immediates),
absence of calls in the hot path. Every prior
surprise in this programme (EXP-001's libcrypto
discovery, EXP-006's round trip, EXP-011's
memory-backed state) was visible in the assembly
before it was visible in the timings; the audit is
where candidates go to be understood, not merely
measured.

## 6. Benchmark integration

A candidate that passes sections 3 to 5 earns a
benchmark under the current decision discipline,
and from EXP-017 onward under the measurement
stack: paired interleaving (Y-102), steal
covariates, pinned manifest (Y-108), and the
predeclared criterion style of EXP-010 (candidate
minimum against incumbent maximum across rounds,
medians reported alongside). No candidate is
described with performance language before this
step completes; the record's benchmark field stays
"not run" until it does, as the four seed records
below demonstrate.

## 7. Candidate record format

One JSON object per candidate, stored in proofs/
for proof-stage candidates and promoted to the
experiment registry on benchmarking:

    {
      "id": "P6C-001",
      "cone": "boolean Ch",
      "source_transformation": "e-graph saturation, ternlog rule",
      "target_expression": "...",
      "candidate_expression": "...",
      "proof": {"method": "z3 UNSAT", "artifact": "proofs/discovery_demo_results.json"},
      "cost": {"incumbent": 3, "candidate": 1, "model": "instruction count"},
      "compiler_config": null,
      "assembly_audit": null,
      "benchmark": "not run",
      "status": "proven, unbenchmarked",
      "note": "..."
    }

## 8. Stopping and promotion rules

- Saturation stops at its node budget or at
  fixpoint, whichever comes first; the closure
  size is part of the cone's characterisation.
- A cone is characterised when two consecutive
  campaigns (different seeds, same budgets) produce
  no new proven candidate beating the incumbent on
  the cost model. Characterisation is a result:
  it converts "we have not found a better graph"
  into "this space, this rewrite set, this budget:
  none exists", which is the strongest negative the
  programme can honestly state.
- Promotion: proven + priced + assembly-audited +
  benchmarked under the decision procedure =
  eligible for an EXP number and, separately, an
  integration decision. Nothing promotes on
  saturation output, solver output, or a single
  session's timings.
- The loop's overall stop for Workstream A is not
  defined by a date: it stops per cone by
  characterisation, and the phase reports the
  characterised cones as its negative results with
  the same prominence as any positive.

## 9. Built now: seed candidates

src/discovery_harness.py (e-graph-lite saturation,
ternlog extraction, T1 chain enumeration, z3 gate)
was built and run for this assignment. Its four
records (proofs/discovery_demo_results.json) all
reproduce known results, which is the point of a
seed run: the machinery finds Ch as one ternlog
(immediate 202 = 0xCA, classic cost 3, z3 UNSAT),
Maj as one ternlog (232 = 0xE8; the seeded classic
form costs 5, and the record notes EXP-012's proven
classic minimum is 4), the Ch alternative form at
equal cost 3, and the T1 five-operand chain space
(1,680 trees, minimum depth 3, all at 4 additions).
A discovery system that cannot reproduce EXP-012
from scratch would not be trusted on unknown cones;
this one can, and EXP-020 is where it is pointed
at the full round.
