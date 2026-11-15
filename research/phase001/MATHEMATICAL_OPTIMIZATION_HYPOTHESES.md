# Phase 001, Deliverable 16: Mathematical Optimization Hypotheses from the Genesis Deconstruction

Project: NOVA SHA-X, Research Phase 001, Wave 4.
Scope: hypotheses that arise specifically from reading the 0.1.3 implementation as mathematics: its data layout, its representation choices, and the work it visibly repeats. Each hypothesis gets: the derivation from source, its tier, the prior-art check inside our own programme (EXP-016, EXP-020, EXP-024, EXP-026, EXP-027, EXP-033 and the Phase 6B registry), and either the deciding experiment or the refutation pointer. The discipline of this deliverable is that most genesis-era inefficiencies turn out to be already decided, in production, or refuted; the table at the end says which, so nothing decided is carried forward as open.

## H-1. Midstate reuse (the optimization the original skipped)

- **Derivation.** Deliverable 10 proves chunk 1 of the header compression is nonce-independent; Deliverable 11 proves BlockSHA256 nevertheless re-runs InitState and all 64 rounds on every candidate, twice per candidate when the outer pass is counted. The reusable quantity is exactly 64 of 192 rounds per candidate, plus chunk 2's rounds 0 to 2 state evolution and schedule words W[16], W[17] (Deliverable 9 and 10), for the conventional total of 67 of 192 (about 34.9 percent).
- **Tier.** PROVEN IDENTITY (the dependency facts), EXACT OPTIMIZATION (proven) as an accounting statement about rounds not executed.
- **Prior art in our programme.** This is NOVA's founding optimization: the production C backend is a midstate batch (mining/cpu/bal_batch.c), and the AVX-512 kernels carry the template-fixed prefix per batch (NOVA audit sections 1 and 2). EXP-033 section 3.2 restates the 67-round figure as conventional accounting and explicitly not a proven lower bound.
- **Status.** CLOSED AS IMPLEMENTED. Not an open hypothesis. The remaining mathematical question in this area is not whether the prefix is reusable but whether any representation makes the non-reusable remainder cheaper, which is EXP-033's closed map and the E2 item (Deliverable 15 section 5), not a midstate question.

## H-2. The 56 word byte-reversals per candidate

- **Derivation.** Wave 3 (Deliverable 11 section 3) counted the per-candidate endianness work of BlockSHA256's little-endian path: 16 input words byte-reversed per 64-byte block, 3 blocks per candidate (2 for the header pass, 1 for the outer pass), plus 8 output state words byte-reversed on the final block of each pass counted in the same total: 48 input reversals and 8 output reversals, 56 per candidate. The reversals apply to every word, including the fully invariant first block whose reversed form is identical on every candidate.
- **Tier.** The count is a STATISTICAL OBSERVATION in the weak sense of a source census (exact, from code, not sampled). Any claim that removing them yields a specific rate gain is a HYPOTHESIS REQUIRING EXPERIMENT.
- **Prior art in our programme.** EXP-027 C3 established the governing principle with measurements and counterexamples: representation changes pay their conversion cost once at the boundary (message in, digest out), never per round; production kernels already absorb endianness at the boundary by construction (templates are stored as pre-reversed words; the kernel ABI takes bytes). The 0.1.3 cost exists because its Transform API takes host-order words per call, forcing per-call conversion; no NOVA kernel has that API shape. The hypothesis "eliminate per-candidate reversals" is therefore already decided by architecture: the cost it targets does not exist in the production path.
- **Deciding experiment, if anyone insists on a residual claim.** Name the specific production kernel alleged to still pay per-candidate reversals, then run the EXP-017 paired protocol on a variant with the reversal hoisted. Until a kernel is named, there is nothing to decide: the census result is that the 56 reversals are a property of the historical code, fully explained, and absent from the modern one.
- **Status.** CLOSED (explained by the boundary-conversion principle, EXP-027 C3; production already conforms).

## H-3. Rotating-window state representation

- **Derivation.** Deliverable 8: the Crypto++ Transform names its eight state words through rotating macros a(i) to h(i) over a fixed T[8] array, so the per-round state rotation costs zero data movement; only two slots are written per round. At source level this is an exact renaming identity.
- **Tier.** PROVEN IDENTITY at the representation level.
- **Prior art, and a distinction that must not be blurred.** Two different ideas share the word "rotation" and have opposite verdicts:
  - *Register renaming / compile-time rotation* (this hypothesis): standard practice in every serious SHA-256 kernel, including NOVA's; the compiler performs the renaming for register-resident state. EXP-018 tested the adjacent idea directly: a register-resident dual-batch design with compile-time argument rotation achieved residency but its rate was NOT significant under EXP-017 (pooled 1.087x, confidence interval crossing 0); residency alone did not pay, because the multi-buffer kernel's bottleneck is not state movement.
  - *Rotated state domain* (computing in a rotated representation of the values): REFUTED by counterexample in EXP-027 C3, because rotation does not commute with addition. That refutation does not touch renaming, and renaming's identity does not rescue the domain idea. The two must never be cited for each other.
- **Status.** CLOSED. The identity is real and already universal practice; the measurable version (EXP-018) did not produce a verified gain.

## H-4. Circular schedule buffer implications

- **Derivation.** Deliverable 8 and 9: the 0.1.3 schedule is a 16-word circular buffer expanded in place by blk2, just in time inside each round macro. The alternative representation is a fully materialized W[64]. The two are the same function; the question is purely which layout a given execution engine prefers.
- **Tier.** PROVEN IDENTITY (the in-place regrouping is proven exact in Deliverable 9).
- **Prior art in our programme.** EXP-027 C4 and EXP-033 section 2.4 priced the schedule's arithmetic: four-operand schedule sum at 3 VPADDD is at its counting floor, and carry-save forms cost more. EXP-032 measured the layout question's modern form: the SHA-NI path's advantage is precisely its hardware schedule machinery (sha256msg instructions fold the expansion into the round unit), while the production single-stream SHA-NI translation unit that recomputes the schedule in scalar C is the established negative (about 0.52x of the C batch). In the AVX-512 multi-buffer kernels the schedule is register-resident and interleaved with rounds, which is the circular buffer's modern descendant.
- **Status.** CLOSED as a representation identity; its performance content was decided per engine by EXP-027 and EXP-032. No standalone experiment is meaningful: schedule layout only matters as part of a whole-kernel candidate judged under EXP-017.

## H-5. Padding precomputation

- **Derivation.** Deliverable 11: FormatHashBlocks frames both passes once per template; only the 4 length bytes and zero-fill are written, and the framing is proven byte-identical to standard FIPS padding for all inputs under 2^32 bits (executed in Deliverable 19).
- **Tier.** PROVEN IDENTITY, EXACT OPTIMIZATION (proven) in the trivial sense that per-candidate framing work is zero in both the original and NOVA.
- **Prior art.** Universal: every NOVA backend frames per template, never per candidate. The original deserves the credit line: of all the per-candidate redundancies in the 0.1.3 loop, framing is the one it already avoided.
- **Status.** CLOSED AS IMPLEMENTED in both codebases.

## H-6. Prefix sharing of chunk 2 rounds 0 to 2 (the EXP-013 ground)

- **Derivation.** Deliverables 9 and 10 quantify exactly what is shareable beyond the midstate: chunk 2 rounds 0 to 2 evolve no nonce-tainted state, and W[16], W[17] are template constants. This is the same territory EXP-013 measured as cross-lane prefix sharing in the multi-buffer setting.
- **Tier.** The dependency facts are PROVEN IDENTITY. Any rate claim is HYPOTHESIS REQUIRING EXPERIMENT.
- **Prior art.** EXP-013: measured ratios straddle 1.0; the shareable fraction is about 2.4 percent of per-nonce work, below this VM's noise floor. EXP-027 C7 retained it explicitly as a combination ingredient: neither promoted nor closed.
- **Deciding experiment.** Only in combination: if a future kernel candidate is built for another reason, include or exclude the prefix share as an ablation arm under EXP-017. A standalone run cannot resolve a 2.4 percent effect on this host (EXP-031 characterization).
- **Status.** OPEN ONLY AS A COMBINATION INGREDIENT. Carried to Deliverable 21 at low rank.

## H-7. K+W constant folding

- **Derivation suggested by the source.** The round sum K_t + W_t appears in every round of every implementation, and the genesis code adds them at use time (Deliverable 8), inviting the idea of pre-adding constants to schedule words.
- **Tier and prior art.** Already decided: EXP-014 REJECTED K+W folding; EXP-027 C7 records the rejection. It is listed here because the genesis reading suggests it afresh, which is exactly the re-proposal failure this deliverable exists to prevent.
- **Status.** CLOSED, REFUTED (EXP-014). Do not re-propose.

## H-8. The 29 versus 28 operation gap (a codegen item, not mathematics)

- **Derivation.** EXP-020 proved the joint round-plus-schedule optimum is 28 vector operations in the searched vocabulary (SMT lower bound, matching construction); production emits 29 because of a compiler Maj codegen gap. The genesis deconstruction adds nothing to this; it is recorded because it is the largest known gap between a proven bound and production in the whole programme, and it is an engineering gap, not a mathematical hypothesis.
- **Prior art.** Variant P6C-007 attacked a neighbouring form and measured 1.051x, not significant, not integrated.
- **Deciding experiment.** A hand-scheduled or intrinsics-forced Maj sequence closing the gap, judged by EXP-017 with the post-integration audit rule. Expected value bounded by about 1/29 of round cost before second-order effects.
- **Status.** OPEN AS ENGINEERING. Carried to Deliverable 21.

## H-9. Single-batch mask search (EXP-024 design C)

- **Derivation.** Not a genesis hypothesis; recorded because Deliverable 21 must rank all standing open items and this is the only other VERIFIED kernel result awaiting an integration decision. Design C (single-batch mask search) measured pooled 1.398x under EXP-017 in the Phase 6B campaign and was not integrated; production kept the dual-batch form.
- **Status.** OPEN AS AN INTEGRATION DECISION (kernel verified; integration value unproven). Gated by the owner's decision and the post-integration audit rule. Carried to Deliverable 21.

## Summary table

| ID | Hypothesis | Tier | Status |
|---|---|---|---|
| H-1 | Midstate reuse | PROVEN IDENTITY / EXACT OPTIMIZATION | Closed, in production |
| H-2 | 56 byte-reversals per candidate | STATISTICAL OBSERVATION (census) | Closed, explained by EXP-027 C3 boundary principle; absent from production |
| H-3 | Rotating-window state | PROVEN IDENTITY | Closed; measurable form not significant (EXP-018); distinct from refuted rotated domain (EXP-027 C3) |
| H-4 | Circular schedule buffer | PROVEN IDENTITY | Closed; per-engine content decided by EXP-027 C4 and EXP-032 |
| H-5 | Padding precomputation | PROVEN IDENTITY / EXACT OPTIMIZATION | Closed, in both codebases |
| H-6 | Chunk 2 prefix sharing (rounds 0 to 2) | PROVEN IDENTITY (facts) / HYPOTHESIS REQUIRING EXPERIMENT (rate) | Open only as combination ingredient (EXP-013, EXP-027 C7) |
| H-7 | K+W folding | n/a | Closed, refuted (EXP-014) |
| H-8 | 29 vs 28 op codegen gap | Engineering, not a hypothesis | Open as engineering (EXP-020) |
| H-9 | Single-batch mask search | Verified kernel (EXP-017) | Open as integration decision (EXP-024 design C) |

The honest headline: the genesis deconstruction produced no new open mathematical hypothesis. Its five candidate ideas resolve to two proven identities already in production, two representation identities already decided per engine, one explained historical cost, and one sub-noise ingredient. The genuinely open mathematical item in the programme remains E2 (Deliverable 15), which predates this phase.
