# Master Research Findings

NOVA SHA-X Master Assignment, deliverable 18. Date: 2026-11-15.

The master synthesis of the programme: what is now known, in the
order the Master Assignment asked the questions, with every claim
carrying its tier and its pointer. The detailed records are the 19
deliverables of this assignment, the Phase A audit, the pinned Core
source audit set, the EXP-030 to EXP-038 records, and Phase 001.

Targets, at full height throughout: **500 GH/s minimum system
objective; 140 TH/s larger objective.** Neither is claimed,
lowered, or replaced by a milestone anywhere in this document.

## 1. The Bitcoin protocol and Core truth (Phase B; BR-001, BR-002)

Established from the pinned Bitcoin Core v28.1 source (commit
32efe850438ef22e2de39e562af557872a402c31), not from the deployed
binary's behaviour alone:

- The mining-relevant protocol is fully mapped
  (COMPLETE_BITCOIN_PROTOCOL_MAP.md): the 80-byte header (byte
  identical in layout since 2009), coinbase rules with the BIP34
  height push and 100-block maturity, Merkle construction with the
  CVE-2012-2459 mutation check, the exact integer PoW rule,
  retargeting with its factor-of-4 clamp and its 2015-step
  walk-back present in both eras, GBT template supply with its
  RPC-layer cache, BIP22 submission semantics, layered validation,
  chain selection by accumulated work, and BIP152/headers/inv
  propagation.
- Core contains **no production miner and no mining hash path**.
  Header hashing is the generic single-stream CSHA256 through
  HashWriter; CSHA256 has **no midstate API**; the multi-way
  SHA256D64 machinery serves the Merkle tree only
  (BITCOIN_CORE_SOURCE_AUDIT.md). The only in-tree nonce loop is
  the regtest GenerateBlock utility.
- **Extranonce is entirely client-side.** IncrementExtraNonce does
  not exist anywhere in v28.1; the server coinbase scriptSig is
  exactly CScript() << nHeight << OP_0 (node/miner.cpp:161), and
  the OP_0 is the fossil of the space where the 0.1.3 miner kept
  its local counter.
- **submitblock null is not best-chain proof.** Null means the
  block was processed by ProcessNewBlock; membership in the active
  chain is a separate observation. NOVA's EXP-036 client rule
  (record verbatim, classify, decide acceptance from chain state)
  is the correct behaviour, and it is implemented.
- Corrections to the assignment's own assumptions, recorded in the
  Core audit: there is no sha256_shani.cpp (it is
  sha256_x86_shani.cpp plus sha256_arm_shani.cpp, plus sse4 and
  sse41 files); no block_template_manager exists in v28.1
  (BlockAssembler behind interfaces::Mining is the whole template
  engine); v28.1 is autotools-only; SetCompact itself never
  rejects (all rejection lives in CheckProofOfWork).

## 2. The mathematical truth (Phases C and E; BR-003, BR-005, BR-013, BR-014)

- The exact function is specified bit for bit
  (SHA256D_MATHEMATICAL_SPECIFICATION.md): 3 chunks, 192 rounds,
  all 72 constants recomputed from prime roots with zero
  mismatches, padding byte-exact for both passes, byte order
  stated at all five boundaries.
- The nonce-dependence structure is PROVEN: chunk 1 is
  nonce-free (its output is the midstate); the nonce enters at
  chunk 2 word W[3]; W[18] is the first nonce-dependent expanded
  word; state saturation completes by round 6 of chunk 2; pass 2
  is fully nonce-mixed and admits zero reuse.
- The conventional precomputation accounting (67 of 192 rounds
  reusable per template) is exactly that: accounting, **not a
  lower bound** (EXP-033 restatement, binding on all programme
  documents).
- Target mathematics is exact in both eras and the eras are
  reconciled (PROOF_OF_WORK_AND_DIFFICULTY_SPECIFICATION.md):
  modern SetCompact masks to 23 bits and reports negative and
  overflow for CheckProofOfWork to reject; the 0.1.3 BIGNUM decode
  lets the sign bit become a true sign and getuint256 silently
  drops it, with the nBits-equality gate as the on-chain backstop
  in both eras. For every historically valid encoding the two
  decode identically. Floating-point difficulty is a display
  quantity only, in both eras, always.
- The optimisation frontier is closed at stated scopes
  (CRYPTANALYSIS_AND_SHORTCUT_RESEARCH.md): the round is optimal
  at 28 vector ops within the EXP-020 vocabulary; Sigma minima are
  proven exact at 4; statistical bias is dead by 24 rounds;
  screening, outer precomputation, schedule linearity past W[19],
  carry-save deferral, GFNI forms, shuffle rotations, rotated
  state, bitslicing, K+W folding and cross-round sharing are all
  ESTABLISHED NEGATIVE with pointers.
- Exactly one shape remains open: **E2**, the Sigma-through-Maj/Ch
  cone, UNPROVEN BREAKTHROUGH, full-cone attack INCONCLUSIVE,
  ceiling at most about 2 ops per round. It is the programme's
  only unrefuted mathematical shape and it carries no rate.

## 3. The performance truth (Phase D; BR-008, BR-009, BR-010)

All figures are EXP-017 protocol results on the AMD EPYC 9D25
guest, contended-VM measurements, from the binding rate table
(HASHRATE_MEASUREMENT_SPECIFICATION.md section 9):

| Figure | Verdict |
|---|---|
| v512 AVX-512 MB vs production C, batch | VERIFIED 3.55x [3.17, 3.97] |
| Production v512dual search vs production C search | VERIFIED 6.781x [6.154, 7.467] |
| EXP-026 DualMask vs v512 search | VERIFIED 1.718x [1.511, 1.955], integrated as v512dual |
| EXP-024b design C mask search | VERIFIED 1.398x [1.242, 1.578], not integrated |
| EXP-022 flags batch (production benchmark) | VERIFIED 1.441x [1.261, 1.645], batch scope only |
| EXP-032 AVX2 MB batch vs C | VERIFIED 1.409x [1.340, 1.480], not dispatched |
| EXP-032 SHA-NI streams-4 batch vs C | VERIFIED 2.861x [2.671, 3.089], not dispatched |
| Production SHA-NI intrin batch | ESTABLISHED NEGATIVE 0.517x [0.497, 0.536] |
| Flags-form search entry | 0.967x NOT SIGNIFICANT; flags are batch-only in production, by measurement and by source |

Live observation (not a benchmark): the production miner sustains
20.6 to 21.5M H/s session rates on v512dual on the AMD host. The
VM itself delivers about 2 effective CPUs of its claimed 4 vCPUs
under a 61 to 64 percent busy baseline, with no accessible
performance counters (EXP-031; VM_RESOURCE_CAPACITY_REPORT.md).
Category status: A unmeasured by design, B reference only, C
components only, D strong, E controlled search-arm evidence plus
live observations, **F nonexistent as a measurement**.

## 4. The genesis baseline truth (Phase 001; BR-001 to BR-006 groundwork)

From the verified v0.1.3 tree (SNI RAR, cross-source CRC agreement
on 47 of 48 files, the 48th verified by internal consistency and
flagged as such):

- Two SHA-256 implementations coexisted: OpenSSL for all general
  hashing, a vendored Crypto++ extract (src/sha.cpp) for the miner
  alone, because it needed raw state access.
- The original miner reused **no midstate**: InitState fresh per
  candidate, so 64 of its 192 rounds per candidate were provably
  redundant. The one mining-specific capability neither Bitcoin
  codebase ever adopted, 2009 or 2026, is the one NOVA is built on.
- The nonce starts at 1; **nonce 0 is never hashed**; per-template
  coverage is exactly 2^32 - 1; the extranonce is a local CBigNum
  counter; the reward function reads the global best height, a
  quirk miner and validator share only because both call the same
  function in the same state.
- The word "difficulty" does not exist in 0.1.3.
- Phase 001's independent verification suite passed 36 of 36
  checks, and its honest closing statement stands: it measured no
  hash rate, proved no lower bound, and found **no new open
  mathematical hypothesis** in the genesis material. Every
  candidate it raised was already proven and in production,
  already refuted in this programme, or an artifact of the 0.1.3
  API shape that production does not have.

## 5. The production truth (Phases A and G; BR-012, BR-015, BR-016)

- The Phase A audit verified the research record against source
  on every material point: DualMask integrated and selected,
  design C verified and genuinely not integrated, the flags form
  batch-only with no search entry in the library or the call
  graph, the EXP-025 fingerprint complete over the construction's
  dependency set, and the EXP-034 and EXP-036 defects closed in
  source, not merely in reports (NOVA_REPOSITORY_AUDIT.md).
- The production architecture is four paths over one dispatch core
  and one verification stage (NOVA_PRODUCTION_MINING_
  ARCHITECTURE.md): live pool mining (the only evidence-producing
  path), the GBT engine path, the staged solo path behind an armed
  cutover, and the research prototypes, clearly separated.
- The gaps to the target architecture are enumerated, none hidden:
  no production coordinator or candidate queue (EXP-035 is a
  prototype), no category F benchmark, two verified dispatch tiers
  undispatched, statistics unwired, probability percentiles
  unimplemented (specified to signature level in the probability
  model), no version or ntime rolling, no longpoll caller, no
  Stratum V2, and 11 documentation contradictions unfixed
  (NOVA_BITCOIN_CORE_GAP_ANALYSIS.md).

## 6. The honest distance to the targets

From VM_RESOURCE_CAPACITY_REPORT.md section 9, as system counts
under stated assumptions, never as achieved performance:

- At the live basis (20.6M H/s observed): 500 GH/s is about
  **24,272 such systems**; 140 TH/s is about **6.80 million**.
- At the contended benchmark basis (14.8M H/s, EXP-032): 500 GH/s
  is about **33,800 such VMs**; 140 TH/s is about **9.5 million**.
- The probability model adds the discovery arithmetic at the
  current-era example difficulty (D = 134,823,837,323,272,
  2026-11-14): mean wait about 8.9e8 years at the measured rate,
  about 36,700 years at 500 GH/s, about 131 years at 140 TH/s,
  with a 7.35 percent chance of a block in ten years at the larger
  objective. These numbers are the model's, under the stated
  random-oracle assumption; they are why the success criterion is
  a discovered block and not a probability.

Nothing in the programme's verified results changes this distance
by an order of magnitude. The kernel family sits within about 1.5x
of its own instruction-count bound at guest clocks; the round is
proven optimal within its searched vocabulary; the closures of
section 2 are the reason no larger factor is on the table.

## 7. Recommended order of work

Phase 001's RECOMMENDED_NEXT_PHASE (the proposed Phase 002)
reconciled with the Master Assignment's phases: Phases A, B, C and
E are complete (truth, Bitcoin understanding, exact correctness,
mathematical research to its current bounds). What remains is
concentrated in D, F, G and H, and Phase 002's seven steps are
exactly that residue, in its order:

1. **Close the dispatch gap** (Phase G, audited under H):
   integrate the EXP-032 AVX2 and SHA-NI streams tiers below the
   AVX-512 tiers, under the full gate set.
2. **Build the category F benchmark** (Phase D): the end-to-end
   harness under the measurement specification, so pipeline claims
   become measurable.
3. **Attack the 29 versus 28 gap** (Phases D/E): one bounded
   codegen campaign against the proven bound; either outcome
   closes it.
4. **Wire the statistics and finish the probability module**
   (Phases D/E): a production record() caller with accounting
   identities checked against the evidence census; the seven
   specified probability functions implemented against their
   pinned anchors.
5. **The E2 decision attempt** (Phase E), time-boxed: a
   reformulated synthesis or a stated larger budget; SAT, UNSAT,
   or a second INCONCLUSIVE that retires the item until solver
   capacity changes materially.
6. **The EXP-035 overhead study** (Phase F), lab VMs only:
   coordinator, lease and queue overheads measured, so the
   production-coordinator question reaches the owner as numbers.
7. **Independent audit and phase report** (Phase H): the standing
   closing step, in the pattern of every prior phase.

Decision points that belong to the owner alone, unchanged: whether
Phase 002 runs and in this order; fleet activation for mining in
any form; design C integration; the E2 solver budget; any change
to the live mining operation. The 11 documentation contradictions
(section 5) need no decision, only the work, and belong in the next
phase's scope. Experiment numbering for genuinely new work starts
at EXP-039.

## 8. The success criterion, stated plainly

The programme's success criterion is discovering, independently
verifying, constructing and successfully submitting a valid
Bitcoin block, with the throughput objectives at full height
behind it: 500 GH/s minimum, 140 TH/s larger.

**That criterion is NOT MET.** No mainnet block has been found.
The balance is 0 BTC. Live mining runs on public-pool.io and its
highest evidence is pool-accepted shares (level E3: 248 accepted
at the EXP-037 full-log census, the count growing since), which
are not blocks and are never reported as blocks. The solo cutover
to our own node is staged and armed and has not fired, because the
node is still syncing. What this assignment has produced is the
complete, verified map the criterion will be pursued with: the
protocol truth, the mathematical truth, the performance truth, the
genesis baseline, and the exact list of what remains open. That is
what was commissioned, and it is not a block.
