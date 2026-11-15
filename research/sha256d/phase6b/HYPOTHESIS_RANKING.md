# Phase 6B Hypothesis Ranking: EXP-024 to EXP-029

Ranking of the six Phase 6B workstreams, written for
Assignment A (2026-11-14). Criteria: expected
information value per unit of effort, dependence on
prior results, closeness to the production path, and
the directive's own execution order (section 16) and
two-track rule (section 11). The ranking orders work;
it does not grade truth. The directive fixes the
execution order A to H; this ranking explains the
priority inside that order and where parallel effort
belongs.

## Ranking

### 1. EXP-024, mask-based early-exit search (Track A)

Highest priority, first experiment. Rationale: EXP-022
proved the mask comparison mechanism in batch scope
(VERIFIED IMPROVEMENT, pooled 1.82x at sparse
candidates) but the live miner never paid the batch
epilogue, so the one proven mechanism has never been
measured where it would matter. The audit
(CURRENT_PRODUCTION_AUDIT.md, digest trace) shows the
production search materialises all 16 digests of every
group and compares them scalar, one by one, even on a
miss: the exact cost EXP-022 removed in batch scope is
present in the search path in a different shape. Cheap
to test (the comparison code exists and is gated),
decisive either way, and its result gates EXP-026's
combined designs.

### 2. EXP-025, EXP-023 cache correctness (Track A)

Second, and a hard gate, not an optimisation. EXP-023
produced the largest measured construction gains of
the programme (18.49x per extranonce step at 500
transactions) and an integration recommendation, but
the audit confirms its cache identity is an 8-field
fingerprint that omits witness data, transaction
serialisation, fees, the witness commitment inputs and
more (full list in EXP025_CACHE_CORRECTNESS.md). Until
the identity is proven complete, the prototype is a
correctness risk, not an asset. The work is analysis
and adversarial testing, cheap relative to its value:
it either unlocks the largest pipeline gain available
or closes it honestly.

### 3. EXP-027, new computational representations (Track B)

Third by sequence, first by strategic weight. EXP-020
closed the full round at 28 vector ops inside one
stated vocabulary, and EXP-019 closed carry-save for
the schedule at the pricing level. What remains
genuinely open is outside that vocabulary: GFNI affine
forms, shuffle-based rotations, alternative state and
addition representations, joint optimisation across
rounds and across the three compressions. The
directive requires Track B to receive meaningful
effort in parallel; EXP-027 is that effort. Expected
value is dominated by the tail: most candidates will
be rejected, and a single survivor changes the
per-unit factor in PERFORMANCE_GAP_MODEL.md.

### 4. EXP-026, extreme AVX-512 execution research (Track A)

Fourth. The combined design space (EXP-018 register
residency, EXP-020 single-ternlog forms, EXP-022
flags, EXP-024 mask search) is real, but EXP-018's
lesson is that residency alone was not the binding
cost, and EXP-020's lesson is that a proven op-count
gain can be rate-neutral. EXP-026 therefore starts
from a cost model and from EXP-024's measured result,
not from combination enthusiasm. Ranked below EXP-024
because its design inputs depend on EXP-024's
measurements.

### 5. EXP-028, cross-architecture software research

Fifth. Portability is a stated requirement (the
programme must not be tied to one virtual CPU; this
VM alone has presented hosts with and without SHA
extensions and VBMI across replacements). The work is
well understood engineering per architecture (detect,
select, fall back, preserve exact output), so its
research risk is low and its urgency is below the
open questions above. It rises in priority the moment
any second machine class becomes available to measure
on; without one, several of its gates are UNVERIFIED
by construction, as the GPU gates are today.

### 6. EXP-029, parallel and distributed execution

Sixth as a research question, first as bookkeeping
discipline. The coordination problems (exact nonce
partitioning, duplicate prevention, failure recovery)
are solvable with known techniques, and the gap model
shows deployment scale is a resource question more
than a research question at current per-unit rates.
Its accounting separations (unique coverage, actual
computations, repeats, verification, submissions) are
adopted as standing definitions from the start of the
phase, ahead of any distributed build, so no future
aggregate figure can be inflated by construction.

## Notes

- EXP-024 and EXP-025 are sequential gates in the
  directive's order and start first.
- EXP-027 runs in parallel with Track A per the
  two-track rule; its rank here reflects start order,
  not effort share.
- Any workstream that produces a candidate for
  production re-enters through the integration rules
  in PHASE6B_MASTER_PLAN.md section 6, regardless of
  rank.
