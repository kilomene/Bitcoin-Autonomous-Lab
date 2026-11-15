# Phase 001, Deliverable 22: Recommended Next Phase (Proposed Phase 002)

Project: NOVA SHA-X, Research Phase 001, Wave 4.
Status: PROPOSAL. Phase 002 begins only on the owner's word. This document proposes its scope, its order, its prohibitions, its mapping to the Master Assignment (work packages BR-001 to BR-017 and phases A to H), and the decision points that belong to the owner alone. It integrates the ranked list of Deliverable 21 without re-ranking it.

## 1. Proposed scope, in order

**Step 1. Close the dispatch gap (Deliverable 21, Rank 1).** Integrate the verified EXP-032 tiers (AVX2 multi-buffer batch at 1.409x, SHA-NI streams-4 batch at 2.861x, both versus the C batch on their recorded hosts) into production dispatch below the AVX-512 tiers, retiring the negative single-stream SHA-NI unit's dispatch role. Advances BR-008 (CPU execution) and BR-016 (integrated production engine); Master Assignment Phase G (production integration) under Phase H discipline (audit).

**Step 2. Build the category F benchmark (Rank 2).** Implement the end-to-end harness of Deliverable 18: template acquisition from the lab node, construction, search, candidate verification cost, submission, all under environment manifests with raw retention. Advances BR-010 (honest hashrate) and BR-016; Master Assignment Phase D (real performance).

**Step 3. Attack the 29 versus 28 gap (Rank 3).** One bounded codegen campaign against the proven EXP-020 bound. Advances BR-013 (mathematical optimisation, engineering edge) and BR-008; Phase D with Phase E method.

**Step 4. Wire the statistics (Rank 4) and finish the probability module (Rank 8).** Give mining_statistics a production caller with accounting identities checked against the evidence census; implement the BR-011 percentile outputs (median, 90th, 95th, 99th) in mining/probability.py against Deliverable 12's anchors. Advances BR-011 (probability) and BR-016; Phases D and E respectively, both small.

**Step 5. The E2 decision attempt (Rank 5), time-boxed.** Reformulate the full-cone synthesis to count the Boolean output inside the Sigma sub-DAG; run with a pre-agreed solver budget on the least contended host available; record SAT with a proven program, UNSAT closure, or a second INCONCLUSIVE with the budget stated. Any outcome closes the item further; a second inconclusive retires it until solver capacity changes materially. Advances BR-013 and BR-014; Phase E.

**Step 6. The EXP-035 overhead study (Rank 7), lab VMs only.** Measure coordinator, lease and candidate-queue overheads across machines of the lab's own class, with the campaign's failure injection, so the production-coordinator question reaches the owner as numbers. Advances BR-007 (nonce and search-space completeness), BR-015 (distributed CPU architecture) and BR-009 (VM capacity intelligence, as method); Phase F (search-space engineering).

**Step 7. Independent audit and phase report (standing).** An agent that authored none of steps 1 to 6 audits the integrated result against production code, in the pattern of the EXP-030 and EXP-036 audits; the phase closes with a final report in the EXP-030 final report's form, answering its questions with pointers to raw evidence. Advances BR-017; Phase H.

Items held out of the order deliberately: design C integration (Rank 6) waits on its owner decision and can slot after Step 1 if approved; e-graph strengthening (Rank 9) and the prefix-sharing ablation (Rank 10) run only as passengers on Steps 3 and 5 campaigns respectively, never as standalone spends.

## 2. What Phase 002 must not do

- Must not modify the v0.1.3 historical baseline, which remains immutable and read-only; Phase 001's verified tree is the permanent reference.
- Must not activate the fleet (the roughly 25 agents) for mining in any form without the owner's explicit decision; Step 6 uses lab VMs only.
- Must not integrate anything on a microbenchmark alone: EXP-017, correctness gates, regtest and the post-integration audit are all mandatory, per Deliverable 18.
- Must not lower the targets: 500 GH/s minimum system objective and 140 TH/s larger objective stand at full height, and no Phase 002 item may be reported as reaching them; honest per-item ceilings are stated in Deliverable 21.
- Must not present category D numbers as E or F, construction rates as hash rates, or theoretical extrapolations as measurements.
- Must not re-open refuted shapes (Deliverable 15 section 4) without new evidence of a different kind, and must not present E2 or any unproven item as a breakthrough at any point, including in summaries.
- Must not run benchmarks in parallel on the shared host, and must not pool results across a host replacement.
- Must not touch the live mainnet miner, the solo cutover arming, or the wallet material as part of any step; production-path changes go through the audit gate and the owner's standing rules, as in prior phases.

## 3. Master Assignment mapping (summary)

| Phase 002 step | Work packages advanced | Master Assignment phases |
|---|---|---|
| 1. Tier dispatch | BR-008, BR-016 | G (with H audit) |
| 2. Category F benchmark | BR-010, BR-016 | D |
| 3. 29 vs 28 gap | BR-008, BR-013 | D, E |
| 4. Statistics wiring; probability percentiles | BR-011, BR-016 | D, E |
| 5. E2 attempt | BR-013, BR-014 | E |
| 6. EXP-035 overhead study | BR-007, BR-009, BR-015 | F |
| 7. Audit and final report | BR-017 | H |

Phase 001 itself advanced BR-001 to BR-006 (protocol, Core source, exact SHA-256d, serialization, PoW, template and coinbase) and BR-012's source groundwork; Phase 002 as proposed is deliberately weighted to D through H, where the open items actually are.

## 4. Decision points that belong to the owner

1. **Whether Phase 002 runs at all, and in this order.** This document proposes; it does not authorize.
2. **Fleet activation for mining** (the EXP-035 question), informed, if Step 6 runs, by measured overheads rather than estimates. Until the owner decides, the fleet stays unactivated.
3. **EXP-024 design C integration** (Rank 6): a standing verified candidate awaiting an explicit yes or no.
4. **Experiment numbering:** any genuinely new experiment opened in Phase 002 takes the next unreserved ID, EXP-039 onward; re-tests and integrations of existing experiments keep their existing numbers.
5. **The E2 solver budget:** how much shared-host time a second attack on an inconclusive, small-ceiling item is worth, against everything else competing for the same machines.
6. **Any change to the live mining operation** (solo cutover posture, pool configuration, worker identity): untouched by this proposal and reserved as always.

## 5. Success criteria for Phase 002 (proposed)

Phase 002 succeeds if: the dispatch gap is closed under audit; a category F rate exists with a manifest and raw files; the 29 versus 28 question is answered either way; live statistics and complete probability outputs are in production; E2 is closed, proven, or formally retired with its budget recorded; and the coordinator question reaches the owner as measurements. It does not succeed or fail by the programme's block-discovery criterion, which stands above any single phase: a genuine, independently verified, submitted and accepted Bitcoin block, with the 500 GH/s and 140 TH/s objectives unlowered. Phase 001's closing position on that criterion is unchanged and is restated in this wave's summary to the owner: not met, 0 BTC, no block claimed.
