# Phase 001, Deliverable 15: Cryptographic Research Opportunities

Project: NOVA SHA-X, Research Phase 001, Wave 4.
Subject: what the genesis deconstruction legitimately opens on the cryptographic side, and, with equal weight, what it does not. Every entry carries one of the programme's five tiers: PROVEN IDENTITY, EXACT OPTIMIZATION (proven), STATISTICAL OBSERVATION, HYPOTHESIS REQUIRING EXPERIMENT, SPECULATIVE CRYPTANALYSIS. Reduced-round results are never presented as relevant to full-round SHA-256d. The closure map of EXP-033 (research/sha256d/exp033/MATHEMATICAL_INVESTIGATION.md), EXP-027 (phase6b/EXP027_COMPUTATION_REPRESENTATIONS.md) and the standing rejected list (research/sha256d/rejected_hypotheses.md) is applied throughout: anything already refuted is recorded as refuted, with its pointer, and is not re-proposed.

## 1. What the genesis source itself contributes to the cryptographic picture

Three source facts frame everything below:

1. The 0.1.3 tree contains no cryptanalysis, no reduced-round experiment, and no commentary on SHA-256's security properties. Its SHA-256 is a vendored Crypto++ extract used as a black box, plus OpenSSL. Any cryptographic research programme is ours, not a recovery of the original author's intent.
2. The construction the consensus depends on is exactly SHA256(SHA256(80-byte header)) with the comparison hash <= target (Deliverables 11 and 12). The security-relevant object is the full 64-round function applied twice; nothing in the original code weakens, truncates or approximates it.
3. The one place the original code touches the function's structure, the miner's hand-rolled padding and block primitive, is proven byte-equivalent to the standard (Deliverable 11; Deliverable 19 executes the equivalence). There is no historical implementation quirk to exploit: the genesis engine computes the genuine function.

## 2. PROVEN IDENTITY tier (settled mathematics, usable as ground)

| # | Identity or fact | Evidence |
|---|---|---|
| C-1 | Ch and Maj alternative macro forms equal the textbook forms bit for bit | Deliverable 8; executed on 100,000 random triples in Deliverable 19 |
| C-2 | W[18] nonce delta is exactly sigma0(nonce); W[19] nonce delta is exactly the nonce; state words a and e after 3 rounds are integer-affine in the nonce with slope 1 | EXP-016 derivation; EXP-033 section 3.1: 100,000 samples plus z3 UNSAT on the negations with fully symbolic template words |
| C-3 | The schedule's nonce dependence is exactly linear for W[18] and W[19] and nonlinear from W[20] onward | EXP-033 section 3.1: z3 counterexample for W[20] linearity, numerically re-verified (D(n1 xor n2) = 43171369 vs D(n1) xor D(n2) = 3724592575) |
| C-4 | Sigma0 and Sigma1 each need exactly 4 instructions over {ADD, LUT, ROTR, SHR} with independent side values, and exactly 4 even under cone-conditioned operands (shape E1 excluded) | EXP-033 sections 2.3: CEGIS UNSAT at iteration 0, incumbents z3-proven exact |
| C-5 | The 3:2 carry-save compressor identity a+b+c = s + 2*Maj(a,b,c) holds exactly | EXP-027 leg L4: z3 UNSAT plus 1,000,000 scalar differentials (the identity is proven; its USE is costed out, see section 4) |
| C-6 | The four sigma maps are GF(2)-linear; Ch and Maj are not GF(2)-affine | EXP-027 leg L1: z3 UNSAT for linearity of the sigmas; SAT counterexamples for Ch and Maj affinity |

## 3. EXACT OPTIMIZATION (proven) tier

| # | Optimization | Status in NOVA |
|---|---|---|
| C-7 | Midstate reuse: the 64 chunk-1 rounds are template-constant (Deliverable 10 proves the dependency fact; Deliverable 11 proves the original skipped it) | In production since the C midstate backend (NOVA audit section 1); the accounting identity is 67 of 192 rounds reusable per template in the conventional arrangement (EXP-033 section 3.2, restated there as accounting, NOT a lower bound) |
| C-8 | Padding and block-framing precomputation per template | Present in the original itself (FormatHashBlocks) and in every NOVA backend |
| C-9 | Schedule words W[16] and W[17] of chunk 2 are nonce-independent and precomputable per template | Dependency fact proven (Deliverable 9); part of the conventional 67-round accounting |

Nothing else is in this tier. In particular, no entry below this line may be described as an optimization until it is measured under the EXP-017 protocol (Deliverable 18).

## 4. Already refuted: recorded so they are not re-proposed

| Shape | Verdict and pointer |
|---|---|
| Statistical structure in full-round output (bias exploitation, prediction) | ESTABLISHED NEGATIVE. Lab measurements: one-bit bias about 0.49 at 16 rounds, 0.08 at 20, indistinguishable from noise from 24 rounds on; full-round sample bit fraction 0.49998. rejected_hypotheses.md R-01. Reduced-round bias is a property of a different, weaker function and has no bearing on the 64-round construction |
| Early partial target check / digest-prefix screening to skip work | ESTABLISHED NEGATIVE. Every digest word depends on all 64 outer rounds plus feed-forward; no partial verdict exists. rejected_hypotheses.md R-06; EXP-033 section 3.4; Deliverable 11 section 6 |
| Outer-hash precomputation or representation change of the double hash as a whole | ESTABLISHED NEGATIVE. 48 of 48 outer schedule words and 64 of 64 outer rounds are digest-dependent. EXP-033 section 3.3; EXP-027 C6 census |
| GF(2)-linear schedule representation past W[19] | REFUTED by the W[20] counterexample (C-3 above) |
| Carry-save / redundant representation deferral across the round boundary | ESTABLISHED NEGATIVE. Every produced word is bitwise-consumed in the next round; deferral distance is exactly 0. EXP-027 C4; EXP-033 section 2.4 |
| Rotated or byte-swapped state representations | REFUTED by z3 counterexample: neither commutes with addition. EXP-027 C3 |
| GFNI affine forms for Ch/Maj; single-instruction GFNI Sigma | REFUTED (non-affinity; byte fan-in census). GFNI sigma constructions exist but cost at least 11 ops against the 4-op incumbent: costed out. EXP-027 C1 |
| VPSHUFB rotation forms | Pure forms refuted exhaustively; mixed form exact but measured at 2.00x the VPROLD price. EXP-027 C2 |
| Bitsliced state | ESTABLISHED NEGATIVE by measurement: about 0.03x of the multi-buffer kernel. EXP-015 via EXP-027 C3 |
| Cross-round subterm sharing (nontrivial shared nodes across the boundary) | Census result 0 shared nontrivial nodes. EXP-027 C6. (Non-sharing restructuring is a different question: see E2 and section 5.) |
| Non-sharing cross-round graph restructuring in the R1 to R6 word-level rewrite system | ESTABLISHED NEGATIVE at stated bounds: e-graph saturation converged for the rounds-only case with costs identical; joint case bounded by its class cap. EXP-033 section 2.1 |
| K+W constant folding; heterogeneous worker pairing; span-scan mask search; TernMask | ESTABLISHED NEGATIVE by measurement in EXP-014, EXP-021, EXP-024 design E, EXP-026 C1 respectively |

## 5. HYPOTHESIS REQUIRING EXPERIMENT tier (open, decidable, honestly stated)

Only one genuinely open cryptographic-structure item survives the closure map, and it is inherited, not new:

**E2 (standing open item, UNPROVEN BREAKTHROUGH tier in EXP-033's own labelling):** a cone program of 5 instructions might exist if the Sigma sub-DAG routes its output through the Maj (resp. Ch) value, so the Boolean instruction sits inside the Sigma accounting and the proven 1 + 4 + 1 = 6 decomposition no longer bounds the cone at 6. Status, exactly as EXP-033 section 2.3 leaves it: shape E1 (correlation exploitation through T1 and T2 as separate operands) is EXCLUDED for both cones by cone-conditioned CEGIS UNSAT; the full-cone CEGIS attack at L = 5 was INCONCLUSIVE (solver timeout at 600 s under host contention), which is evidence of nothing in either direction. No program of the E2 shape is known. A decision requires a synthesis that counts the Boolean output inside the Sigma sub-DAG, a hand proof, or a solver budget far beyond this host's. Expected value if true: at most one instruction per cone, two per round, against a 28-op round optimum (EXP-020); the ceiling is therefore small and known in advance. This item is carried into Deliverable 21 at its true rank, not promoted.

Two further items are open only in the weak sense that their search bounds were finite, and are recorded so the record is complete: the joint (rounds plus schedule) e-graph case hit its class cap without converging (EXP-033 section 5), and restructuring models outside the word-level vocabulary (bit-level circuits with cross-word carry structure, fusion across more than two rounds, vector rotates or funnel shifts as single ops) are untouched territory in the UNPROVEN BREAKTHROUGH tier with no evidence for or against. Neither is a research opportunity with a positive indicator; both are statements about where the map ends.

## 6. STATISTICAL OBSERVATION tier

| # | Observation | Standing |
|---|---|---|
| C-10 | Chain winners under the lab's search follow the geometric law; elapsed unsuccessful time does not raise the next trial's probability (memorylessness) | Derived mathematics (Deliverable 12 section 8), consistent with the lab's recorded samples (R-01). An observation about the model, not a lever |
| C-11 | Reduced-round bias exists and decays to noise by about 24 rounds | Measured on reduced-round variants only. It characterizes the safety margin of the full construction; it is not a property of the function Bitcoin uses and opens no attack on it |

## 7. SPECULATIVE CRYPTANALYSIS tier

For completeness, the speculative space is named and bounded, not pursued: differential or linear cryptanalysis of full-round SHA-256, collision or preimage attacks on SHA-256d, and chosen-input structural attacks. Standing facts: no published result threatens full-round SHA-256 preimage resistance; the lab's own reduced-round measurements (C-11) show the statistical footholds dying roughly 40 rounds before the function ends; the directive for this phase forbids presenting any such direction as a breakthrough, and this deliverable records that no item in this tier has any supporting evidence from Phase 001 work. Any future work here would begin as literature study under BR-014, not as an experiment with an expected payoff.

## 8. Summary

The genesis deconstruction's cryptographic yield is mostly a map of closures, and that is its value: the exact identities that exist (C-1 to C-6) are pinned with proofs, the one optimization the original skipped (midstate) was already NOVA's foundation, the attractive shortcuts are refuted with pointers, and exactly one small, precisely named shape (E2) remains unrefuted and inconclusive. Phase 001 found no new cryptographic opening in the 0.1.3 material, and this deliverable claims none.
