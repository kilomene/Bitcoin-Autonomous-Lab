# Experiment Reports: Master Build Index

Date: 2026-11-15. Index of the experiment-grade evidence produced
by the Master Build (Milestones 2 to 6). Append-only: entries are
added, never rewritten. Each entry gives a one-line verdict and
points at the full record; the full record is the evidence, this
index is only a map.

| # | Record | One-line verdict | Full record |
|---|---|---|---|
| E1 | Batch-size experiment (exp-20261116T004628Z-83dafa): C backend throughput at 65,536 vs 131,072 search range per call, 3 contended repetitions each, with a hashlib differential inside the same sandbox script | Medians hint a larger range amortises per-call overhead (720,712 vs 1,396,011 H/s), but the integrate gate REFUSED with exactly two missing items (independent verification record, EXP-017 statistical verdict); nothing integrated, no production claim | research/master_build/MILESTONE345_BUILD.md, Milestone 3 demonstration section |
| E2 | Backend bake-off and thread sweep (Milestone 4): all seven dispatch tiers measured through the real production search path on a fixed 262,144-hash work unit, 3 repetitions, medians; thread sweep on the winner | Advisory host profile only: shani won at 3,207,924 H/s with a 0.8 percent margin inside run-to-run noise, explicitly NOT a verdict against v512dual; sweep recommended 4 threads for shani under those conditions; production dispatch unchanged | research/master_build/MILESTONE345_BUILD.md, Milestone 4 sections |
| E3 | Resource registry randomised campaign (Milestone 5): 240 trials, small ranges (16 chunks of 256 nonces, 4 batches per chunk), injected worker deaths and reassignments (4,759 reassignments in total) | Exact in every trial: completed coverage pairwise disjoint and the registry's unique coverage equalled an independent model's union; deterministic seeds reproduce the campaign exactly | research/master_build/MILESTONE345_BUILD.md, Milestone 5 section; also run inside tests/test_agent_operations.py |
| E4 | Milestone 6 end-to-end demonstration: agent inspection, production MiningEngine cycle, submission, node acceptance, agent-side EXP-036 verification of the accepted block | Chain executed end to end on regtest: block at height 1445, hash 027df87dbaf2d87100922ddb55d0d5bbd513fae8c1787152073afb56c823a34e, verifier classification block_candidate with digests in agreement; a regtest block, not evidence about mainnet | research/master_build/MILESTONE6_E2E.md; script research/master_build/m6_e2e_demo.py |
| E5 | Milestone 2 live rate observation: backend_hashes counter delta over the 120.99 s interval bracketing a 120 s window on the live production miner, with degradation and coverage reports in the same cycle | Live backend rate measured at 24,544,788 H/s under production conditions on the contended VM (an observation, not a benchmark); zero degradation flags; share rate 0 in the window, unremarkable at pool difficulty 1 | research/master_build/MILESTONE2_LIVE_AWARENESS.md |
| E6 | Rejected-hypothesis refusal (supporting record for E1's pipeline): a K+W constant folding loop record advanced against the real research memory | Refused at the hypothesise gate with the EXP-014 citation before any experiment ran; the pipeline's negative evidence that decided questions stay decided | research/master_build/MILESTONE2_LIVE_AWARENESS.md, final section |

Standing note: none of these records is an EXP-017 verdict, and
none changes a production claim. Rates measured during this build
were taken alongside the live miner on a shared, capped guest and
are labelled with those conditions in their full records.
