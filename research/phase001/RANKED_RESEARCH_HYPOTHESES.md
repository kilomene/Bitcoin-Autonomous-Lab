# Phase 001, Deliverable 21: Ranked Research Hypotheses for the Next Phase

Project: NOVA SHA-X, Research Phase 001, Wave 4.
Contents: every OPEN item from Deliverables 15 and 16, plus the standing items the wider programme carries, ranked by expected value, decidability and cost. Already-refuted items are excluded by design; they live in Deliverable 15 section 4 and Deliverable 16's summary table with their pointers, and must not re-enter this list. Gates vocabulary: EXP-017 (the paired protocol of Deliverable 18 section 3), CG (correctness gates: byte-exact differentials, zero mismatches), RT (fresh regtest block through the candidate path), AUD (post-integration independent audit), OWN (owner decision required before work starts).

Ranking rationale, stated once: decidability and bounded cost rank above raw ceiling, because the programme's history is that small decidable items close and large speculative ones consume seasons. Expected value is judged against the standing targets (500 GH/s minimum, 140 TH/s larger) honestly: no single item below moves those targets by itself, and none is ranked as if it did.

## The ranked list

### Rank 1. EXP-032 tier dispatch integration (AVX2 multi-buffer, SHA-NI streams-4)
- **Kind:** engineering integration of verified kernels. Source: EXP-032 record; Deliverable 17 section 2.
- **Expected value:** portability of verified rates (1.409x and 2.861x over the C batch) to every non-AVX-512 host, including future fleet machines; zero effect on current AVX-512 hosts. Highest certainty of any item on this list: the kernels and their measurements already exist.
- **Decidability:** complete. The question is not whether it works but whether integration preserves the verified behaviour.
- **Cost:** low to moderate: dispatch plumbing, replacement of the negative single-stream SHA-NI unit's role, full differential suite.
- **Gates:** CG, RT, AUD. No new EXP-017 campaign required beyond confirming the integrated path reproduces the EXP-032 arms; if integration changes any measured path, EXP-017 applies in full.

### Rank 2. Category F end-to-end benchmark construction
- **Kind:** measurement infrastructure. Source: NOVA audit section 9; Deliverable 18 sections 1 and 7.
- **Expected value:** the programme currently cannot state any end-to-end rate, which caps the honesty of every pipeline claim; an F harness converts functional proof (regtest, live shares) into a measurable quantity and exposes where pipeline time actually goes (template acquisition, construction, verification, submission).
- **Decidability:** complete; it is a build task with a defined design (Deliverable 18).
- **Cost:** moderate. Includes candidate verification cost instrumentation.
- **Gates:** the framework's own rules (manifest, raw retention, category discipline). No integration decision rests on it until it exists.

### Rank 3. The 29 versus 28 operation codegen gap (EXP-020 residue)
- **Kind:** engineering with a proven bound. Source: EXP-020; Deliverable 16, H-8.
- **Expected value:** bounded above by about 1/29 of round cost (about 3.4 percent) before second-order effects; the only item whose ceiling is a proven number rather than an estimate.
- **Decidability:** high: a hand-scheduled or intrinsics-forced Maj sequence either closes the emission gap or demonstrably cannot on the current compilers.
- **Cost:** low to moderate (one kernel site, two compilers' codegen to fight).
- **Gates:** EXP-017 in full, CG, RT, AUD.

### Rank 4. Production wiring of mining statistics (EXP-037 residue)
- **Kind:** engineering completion. Source: EXP-037/038 record; NOVA audit gap list.
- **Expected value:** the statistics module exists and is correct but has no production caller of record(); wiring it makes live coverage, duplicate and per-backend accounting real instead of reconstructed, which the Master Assignment's accounting rules require at scale.
- **Decidability:** complete.
- **Cost:** low.
- **Gates:** CG (accounting identities against the evidence log census), AUD. No benchmark gate: this changes observability, not the search path. Care required that wiring does not alter the live miner's behaviour; the EXP-036-era rule (audit before anything else moves) applies.

### Rank 5. E2: the Sigma-through-Maj/Ch cone shape
- **Kind:** mathematics. Tier: UNPROVEN BREAKTHROUGH (EXP-033's label); in this phase's five-tier vocabulary, SPECULATIVE CRYPTANALYSIS adjacent, carried as HYPOTHESIS REQUIRING EXPERIMENT for its deciding procedure. Source: EXP-033 section 2.3; Deliverable 15 section 5.
- **Expected value:** at most one instruction per cone, two per round, against the 28-op optimum: a ceiling of about 7 percent of round cost in the most optimistic reading, realistically less after scheduling effects. It is the only unrefuted mathematical shape in the programme, which is its real claim on attention.
- **Decidability:** partial. Shape E1 is already excluded; the full-cone attack timed out inconclusively. A decision needs a synthesis formulation that counts the Boolean output inside the Sigma sub-DAG, or a solver budget on an uncontended host far beyond this VM's (EXP-031: perf-limited, contended, about 2 effective CPUs).
- **Cost:** high in solver time, low in code.
- **Gates:** a found program must be proven exact (z3 equivalence over the cone, then 200,000+ differentials in the EXP-033 style) before any kernel work; any kernel then faces EXP-017, CG, RT, AUD in full. OWN applies to the solver-budget spend of time on shared infrastructure.

### Rank 6. EXP-024 design C integration decision (single-batch mask search)
- **Kind:** integration decision on a verified kernel (pooled 1.398x in its certified single-batch form). Source: Phase 6B record; Deliverable 16, H-9.
- **Expected value:** a faster certified fallback for single-batch consumers; the production dual-batch path is unaffected. Value is real but narrow.
- **Decidability:** the kernel is decided; the open question is integration value in the consumers that would use it.
- **Cost:** low to moderate.
- **Gates:** OWN first (the Phase 6B close left this as a standing candidate, not an instruction), then EXP-017 confirmation in the integrated consumer, CG, RT, AUD.

### Rank 7. EXP-035 overhead study, then the coordinator decision
- **Kind:** distributed-systems measurement preceding any production coordinator. Source: EXP-035 final report (prototype proven in simulation, 60 of 60 trials; multi-machine overhead UNVERIFIED).
- **Expected value:** the only path by which the fleet question becomes decidable with numbers instead of argument; prerequisite to any Work Lease Manager or Candidate Queue production work (the EXP-030 Phase B missing components).
- **Decidability:** the study is decidable; the coordinator decision it informs belongs to the owner.
- **Cost:** moderate to high (multi-machine harness, failure injection at campaign scale).
- **Gates:** OWN (fleet involvement in any form is the owner's decision; the study itself can run on lab VMs), CG for the accounting identities, AUD before any production integration.

### Rank 8. Probability percentile implementation (BR-011 completion)
- **Kind:** mathematics implementation gap. Source: Master Assignment BR-011; EXP-037/038 record (percentile outputs, median/90th/95th/99th, are not implemented in mining/probability.py).
- **Expected value:** completes the probability deliverable the Master Assignment names; improves planning honesty (expected time is routinely misread as a deadline; percentiles are the corrective).
- **Decidability:** complete; closed-form and numeric routes both exist from Deliverable 12's distribution results.
- **Cost:** low.
- **Gates:** unit verification against Deliverable 12's anchors (the suite of Deliverable 19 section 6 is the pattern), AUD as part of any release touching the module.

### Rank 9. Joint e-graph strengthening and out-of-vocabulary restructuring bounds
- **Kind:** mathematics, bound-raising. Source: EXP-033 sections 2.1 and 5.
- **Expected value:** converts two "searched to a bound" results into stronger closures (the joint rounds-plus-schedule case hit its class cap unconverged; bit-level circuits, multi-round fusion and funnel-shift vocabularies are unsearched). Value is negative-result value: a stronger map of what cannot work, which protects future effort.
- **Decidability:** partial; each strengthening is decidable, the space of models is not exhaustible.
- **Cost:** moderate to high in solver and design time.
- **Gates:** proof standards of EXP-033 (incumbents proven, counterexamples exhibited); no kernel gates unless something survives, which nothing here predicts.

### Rank 10. Chunk 2 prefix sharing as a combination ingredient (EXP-013 ground)
- **Kind:** kernel ingredient. Source: EXP-013; EXP-027 C7; Deliverable 16, H-6.
- **Expected value:** about 2.4 percent of per-nonce work at the theoretical top, below this host's noise floor standalone.
- **Decidability:** only in combination with another kernel change that justifies a campaign; standalone it is undecidable on this VM class (EXP-031).
- **Cost:** low as an ablation arm inside someone else's campaign; prohibitive standalone.
- **Gates:** EXP-017 as an ablation arm only, CG, RT, AUD with the host campaign.

## Items deliberately not ranked

- Everything in Deliverable 15 section 4 (refuted shapes): excluded, with pointers, permanently unless new evidence of a different kind appears.
- Fleet activation for mining: not a hypothesis; an owner decision (Deliverable 22).
- GPU work: no device exists on any lab host; there is nothing to rank.
- Any reduced-round cryptanalysis direction: SPECULATIVE CRYPTANALYSIS tier with no supporting evidence (Deliverable 15 section 7); a literature study under BR-014 may be scheduled on its own merits but carries no expected mining value and is not ranked as if it did.
