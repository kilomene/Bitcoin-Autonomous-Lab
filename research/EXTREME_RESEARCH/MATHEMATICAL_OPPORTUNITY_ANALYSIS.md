# Mathematical Opportunity Analysis: NOVA SHA-X Extreme Research, Stage 2

Date: 2026-11-15. Scope: for each computational objective in the
production mining path, this document states the direct formulation
as production runs it today, every algebraically equivalent or
alternative formulation that prior work has established (with its
settled status and evidence pointer), what prior work has not
examined, and, for each genuinely open item, which cost model
governs it. Analysis only: no benchmark was run for this document,
no code was changed, and no settled result is re-opened.

Ground truth and sources:

- Stage 0: research/EXTREME_RESEARCH/REPOSITORY_RECONCILIATION.md
  and research/EXTREME_RESEARCH/EXPERIMENT_REGISTRY.json (97
  entries: 34 PROVEN, 27 INTEGRATED, 13 REJECTED, 12 NEW, 7
  EXPERIMENTAL, 2 UNDER_INVESTIGATION, 2 DEFERRED). Where the
  Stage 0 registry and the consolidated register
  (research/master_build/RESEARCH_OPPORTUNITY_REGISTER.md, 280
  rows) use different status words for the same item, the Stage 0
  registry governs here, because it was verified against current
  source.
- Stage 1: research/EXTREME_RESEARCH/
  SHA256D_PIPELINE_RECONSTRUCTION.md, MESSAGE_SCHEDULE_DEPENDENCY_GRAPH.md,
  MERKLE_AND_TRANSACTION_MATHEMATICS.md, SHA256_COMPLETE_MATHEMATICAL_MODEL.md.
- The verified rate table and measurement rules:
  research/hashrate/HASHRATE_MEASUREMENT_SPECIFICATION.md and the
  EXP-017 paired protocol (3 or more sessions, paired 65,536-hash
  blocks, randomised AB/BA order, adjusted bootstrap CI entirely
  above 0 in every session and pooled, plus full correctness gates).

Cost model vocabulary, used strictly throughout. These quantities
are not interchangeable, and several past confusions in this
programme came from treating one as another:

- Operations: the count of primitive instructions a formulation
  executes. A proven optimum in operations says nothing by itself
  about elapsed time (EXP-041 is the standing demonstration).
- Dependency depth: the length of the longest chain of dependent
  operations. This binds when the core is latency-limited rather
  than throughput-limited.
- Register pressure: the live-value footprint. This binds through
  spills to memory, which convert register operations into memory
  traffic.
- Memory traffic: bytes moved to and from caches and RAM. This
  binds when data does not stay resident.
- Executed rounds: how many of the 192 SHA-256d rounds actually
  run per candidate. This is fixed by the dependency graph except
  where a proven reuse applies.
- Elapsed time: the only quantity the mission is paid in. Every
  other model is a hypothesis about elapsed time, and each such
  hypothesis needs its own EXP-017 measurement before it is
  believed.

## 1. Header preparation and template construction

Direct formulation today. On the GBT path, mining/engine.py takes
a getblocktemplate response from Bitcoin Core, builds a
PreparedTemplate (coinbase, transaction set, Merkle structure,
header fields), and constructs candidates per extranonce step.
Construction is served by the EXP-025 template cache: a layered
dsha256 identity (family_key, tx_key, coinbase_key, header_key)
keys a bounded 128-entry cache, and build_candidate_uncached is
the preserved fallback. On the pool path, the template arrives as
a Stratum mining.notify and the miner builds no transactions at
all. On the solo path, mining/solo_server.py builds jobs from GBT
and serves coinbase parts plus a Merkle branch.

Established alternatives and their status:

- Per-call recomputation of all candidate material (the pre-cache
  form). Superseded. EXP-023 measured that the old
  build_candidate recomputed about 99.6 percent
  extranonce-independent work per call at 500 transactions.
- Y-076, extranonce-dimension midstate amortisation as specified:
  REJECTED (EXP-023). The named cache target changes with every
  extranonce step and the named cost does not exist in the code.
- Y-077, data-level candidate caching: VERIFIED at prototype
  level by EXP-023, proven unsafe in its first form by the
  EXP-025 adversarial campaign (5 stale serves, 2 validation
  bypasses with the fingerprint unchanged), repaired into the
  layered-identity design, and INTEGRATED as EXP-025. The
  steps500 figure of 23.02x is a candidate-construction rate,
  never a hash rate, and is labelled so everywhere it appears.
- Y-079, snapshot-depth decision table by template field: PROVEN
  (EXP-023 verified table over all 32 field subsets plus two
  boundary rows). This is the settled answer to which template
  fields a cache identity must cover, with the recorded boundary
  that mintime and curtime sit outside the identity and are read
  live per build (audit note N-2).
- X-059, candidate construction caching in MiningEngine:
  INTEGRATED through the same EXP-023 to EXP-025 line.

Not examined:

- Template setup cost share at production spans on the live pool
  path (register Y-081, NEW). EXP-040 priced construction on the
  GBT path at regtest difficulty (section 8 below); the pool path
  has a different cost shape (notify parsing, job swap, no
  transaction handling) and has never been priced.
- A prepared-work prefetch queue between template supply and
  search (register R-33, NEW; related X-056 and Y-035 template
  prefetch, both NEW and untested). EXP-040 measured the stage
  costs a prefetch would attack; no mechanism has been built.
- Self-contained template setup inside the research library
  (X-103, NEW), and template double-buffering in mine_cycle
  (X-064, EXPERIMENTAL, untested).

Open items and their cost models:

- Prefetch and double-buffering: elapsed time, specifically
  pipeline latency at template transitions. The operations count
  of construction is already minimised by EXP-025; what remains
  is whether search threads idle while the next template is
  prepared. At mainnet difficulty this latency amortises over an
  astronomical per-block search and is worth nothing; at solo
  and regtest difficulty it is a first-order cost. Any claim for
  this item must state the difficulty regime it applies to.
- Pool-path setup pricing (Y-081): elapsed time measurement
  only. There is no formulation question here at all; the gap is
  that one production path has never been instrumented.

## 2. Merkle maintenance

Direct formulation today. The GBT engine caches the branch
structure of the template's transaction set and recomputes only
the leftmost path per extranonce step:
PreparedTemplate.root_with_coinbase recomputes the root from the
cached branches after the coinbase leaf changes, which is the
one incremental Merkle update that is ever valid (Stage 1,
MERKLE_AND_TRANSACTION_MATHEMATICS.md section 3). The solo
server serves the branch directly (merkle_branch,
attach_witness). The pool path does no Merkle work: the pool
supplies the root.

Established results and their status:

- The invalidation rules are settled, not open: a branch node is
  reusable if and only if its entire leaf set is unchanged; the
  root is reusable if and only if the ordered TXID list is
  identical; the witness root follows the same rule over WTXIDs
  with the coinbase leaf fixed at zero. These are proven
  properties of the construction, applied through the EXP-025
  identity (Stage 1, section 6 table).
- EXP-034 closed the one real defect class found here: the solo
  server located the extranonce split in the full coinbase and
  applied it to the stripped coinbase, a 2-byte offset corruption
  on every SegWit template. Fixed at mining/solo_server.py line
  270; the auditor reproduced the corruption byte for byte
  pre-fix and mined a regtest block on the fixed path.
- Stage 1 re-verified the full TXID and witness trees against
  Core on real blocks (2,095 transactions at mainnet height
  450170; the complete BIP141 chain at regtest height 1491).

Not examined:

- Incremental Merkle spine per extranonce as a separately
  optimised structure (X-060, NEW, untested). The current
  implementation already recomputes only the affected path; what
  X-060 asks is whether the spine representation itself (layout,
  prefetch, vectorisation) can be improved. No measurement
  exists.
- Vectorised Merkle root for large templates (X-112, NEW,
  untested), and coinbase TXID caching across templates (X-113,
  EXPERIMENTAL, untested). Note the boundary: a coinbase TXID
  can only be cached across templates whose coinbase bytes are
  identical, which the EXP-025 coinbase_key already decides; the
  untested part is whether a second, finer cache below the
  template cache pays.
- In-place extranonce patching of the coinbase (X-061,
  EXPERIMENTAL, untested).

Open items and their cost models:

- All three are memory traffic and elapsed time at template
  scale, not operations in the hash kernel. A full root rebuild
  costs O(n) pair hashes over the transaction list; the current
  path costs O(log n) per extranonce step. The remaining
  questions are constant-factor: data layout of the spine and
  whether pair hashing at the top levels vectorises. These costs
  are paid once per template or once per extranonce step, never
  per nonce, so their ceiling is the construction budget priced
  by EXP-040 (about 206 ms per loaded block at regtest
  difficulty), not the search budget.

## 3. Chunk-1 midstate

Direct formulation today. Every production kernel consumes a
prepared first-block state: S_mid = Compress(IV, header bytes 0
to 63), computed once per template and reused for every nonce.
This is Phase 001 hypothesis H-1, INTEGRATED, and the one
mining-specific capability neither Bitcoin v0.1.3 nor Core
28.1 ever adopted (Phase 001 comparative report).

Established results and their status:

- The reuse itself is a proven identity, differentially verified
  in Stage 1 over 49,288 cases including boundary nonces.
- Y-077 two-level midstate caching for job families: INTEGRATED
  through EXP-025 (the template cache holds the prepared state
  under the layered identity).
- The accounting boundary is settled: 64 of 192 rounds are
  chunk-1 rounds, and with rounds 0 to 2 of chunk 2 the
  conventional template-reusable count is 67 of 192. The Stage 1
  reconstruction repeats the standing caution: this is an
  accounting of the conventional graph, not a lower bound on
  equivalent computations (Phase 6 correction OP-1).

Not examined:

- Vectorised block-1 computation for short-span amortisation
  (Y-032, NEW, untested): when spans are short (rapid template
  turnover, low-difficulty solo work), the scalar per-template
  midstate cost is paid often enough that computing block 1 for
  several templates at once in one multi-buffer pass could pay.
  Never built or measured.
- The midstate cost share on the live pool path at production
  span lengths. Spans there are long, so the expected share is
  negligible; it has simply never been measured, and the claim
  "negligible" currently rests on arithmetic, not evidence.

Open items and their cost models:

- Y-032 is an operations question (one vectorised block-1 pass
  versus k scalar passes) whose value converts to elapsed time
  only in the short-span regime. Outside that regime its benefit
  is zero by construction, so the experiment must be scoped to
  short spans or not run at all.

## 4. Chunk-2 schedule generation

Direct formulation today. The nonce enters chunk 2 as exactly
one loaded word, W3. Each kernel generates the 64-word schedule
per nonce in registers: the AVX-512 kernels use the vector
recurrence directly; the SHA-NI kernel generates the schedule
entirely with SHA256MSG1 and SHA256MSG2, and the Stage 5 record
prices that choice on its own: the MSG schedule alone is worth
about 2.6x over the scalar schedule in that kernel family.

Established results and their status:

- EXP-016 dependency identities, PROVEN and re-verified by
  EXP-033: W18 is the first nonce-dependent expanded word and
  its delta under a nonce change is exactly sigma0 of the nonce
  delta; W19's delta is exactly the nonce delta; W20 is the
  nonlinear onset (delta-linearity violation rate 1.0 measured;
  GF(2)-linearity refuted by a z3 counterexample). From W20
  onward every word is fully nonce-dependent. No exact delta
  shortcut survives past W19.
- Y-065 (nonce-affine schedule decomposition) and Y-075 (round-3
  delta decomposition): both REFUTED at proof grade by EXP-016.
  These are the same identities read from the other side.
- Carry-save schedule generation (Y-001, Y-002): REJECTED by
  EXP-019 at the price gate. A software 3:2 compressor costs 3
  instructions, not 2, and the recurrence bounds deferral to
  separation 1 because sigma1 consumes W[t] for W[t+2]. The
  incumbent add tree won at every relevant distance in the
  experiment's own winner table.
- The circular schedule buffer (Phase 001 H-4) is a PROVEN
  identity; whether a given engine uses it is a per-engine
  engineering decision already taken by EXP-027 and EXP-032,
  not an open question.
- EXP-027 closed, at stated scopes, the representation searches
  that touch the schedule: GFNI affine forms, VPSHUFB rotations,
  rotated and byte-swapped state, and IFMA accumulation.

Not examined:

- Block schedule generation in 16-word jumps (Y-069, NEW):
  producing the schedule a block at a time with a different
  dependency structure than the word-at-a-time recurrence. The
  recurrence itself is fixed; the question is scheduling and
  register blocking of its evaluation.
- Schedule word rematerialisation versus ring storage (Y-059,
  NEW), and schedule generation distance within a single
  multi-buffer batch (Y-056, NEW). Both ask where schedule words
  should live and how far ahead they should be produced.
- Alternative SHA256MSG grouping in the SHA-NI kernel (X-078,
  NEW), and schedule-ahead distance in the SHA-NI kernel (X-010,
  NEW).
- A sparsity-exploiting scalar schedule for template setup
  (Y-073, NEW): chunk 2 has five nonzero loaded words and ten
  zeros; a setup-time schedule for the nonce-independent prefix
  could exploit that sparsity. Setup only, never the per-nonce
  path.

Open items and their cost models:

- Y-069, Y-059, Y-056 and X-078 are register pressure and
  dependency depth questions, not operations questions. The
  operation count of the recurrence is fixed by its terms; what
  varies is how many schedule words must be live at once and
  whether sigma evaluations sit on the critical path into the
  rounds that consume them. On the AVX-512 kernels the schedule
  and the round state compete for the same 32 zmm registers, so
  a schedule-ahead choice is simultaneously a spill choice.
- Y-073 is an operations question confined to template setup;
  its ceiling is the setup budget, and it interacts with
  section 3's short-span question (Y-032).

## 5. The compression round

Direct formulation today. The production v512 kernel emits 29
vector operations per steady-state round (EXP-041 census: 12
offsets, 7 ternlog, 10 adds; Ch is already a single 0xe4
ternlog; Maj is the 0x60 plus 0x78 pair). The production
DualMask search body in v512dual already emits 28 per
batch-round. The live search path is v512dual.

Established results and their status. This is the most heavily
settled objective in the programme:

- EXP-012: the Boolean cones are CLOSED. Ch is the single
  ternlog 0xCA, Maj is 0xE8, XOR3 is 0x96; classic operation
  counts proven minimal.
- EXP-020: within its searched vocabulary, the full round is
  CLOSED at 28 vector operations per steady-state round, with
  an SMT lower bound of 28 in that vocabulary. Production v512
  emits 29 because of a compiler codegen gap on Maj.
- EXP-014: K+W folding REJECTED. Folding the round constant into
  the schedule word before the round does not pay.
- EXP-027: carry-save arithmetic beyond the schedule is closed
  (every round addition has deferral distance exactly 0);
  addition networks and cross-round subterm sharing are closed
  (census: 0 nontrivial subterms shared across the round
  boundary).
- EXP-033: e-graph equality saturation found no cheaper graph
  for the two-round round function (soundness: 380,520 enode
  evaluations, 0 mismatches). Sigma0 and Sigma1 minima are
  proven exactly 4 instructions over {ADD, LUT, ROTR, SHR}.
  Cone-conditioned synthesis is UNSAT for both Sigma cones.
- EXP-042: the E2 shape (routing the Sigma output through the
  Maj or Ch value, the last unrefuted shape from EXP-033) is
  REFUTED at its stated bounds for both cones. With E1 already
  excluded, the cone minimum over the vocabulary is exactly 6
  under those bounds.
- EXP-041: closing the 29-to-28 gap in v512 is an ESTABLISHED
  NULL. The two 28-op variants (tmaj, tfull) were built,
  censused at 28, differentially verified (648,000 digests), and
  measured NOT SIGNIFICANT under EXP-017 in batch and in search.
  The recorded mechanism is static-schedule reasoning: the
  second Maj ternlog sits on the S0 and T2 branch, which has
  slack against the T1 critical chain, so removing it shortens
  a non-critical path. EXP-041 also recorded the environment's
  resolution limit: two instruction-identical libraries
  disagreed with themselves across session batches by more than
  the gap's 3.4 percent ceiling, so effects at or below that
  ceiling cannot be resolved on this VM either way.

Not examined:

- A balanced T1 addition tree under a measured vector port
  model (Y-003, NEW), and a superoptimiser for the MB T1
  addition chain under a port model (Y-048, NEW). The T1 sum
  has five addends; its tree shape trades dependency depth
  against operation count, and no port-level model of this core
  has ever been validated. Hardware performance counters are
  not accessible on this VM (perf_event_open returns EPERM),
  so any port model here is unverifiable against counters and
  can only be tested end-to-end through EXP-017.
- Operand order forcing for bypass-friendly T2 (Y-063, NEW) and
  one-round-ahead Boolean precompute for Ch (Y-057, NEW):
  micro-scheduling questions of the same class as EXP-041,
  hence bounded by its resolution warning.
- Joint (Ch, Maj) cone search with shared intermediates
  (Y-013, NEW). The individual cones are closed by EXP-012;
  the joint question is whether computing both from shared
  intermediates beats the sum of the two optima. EXP-027's
  census found 0 shared subterms across the round boundary,
  which bounds but does not formally close the within-round
  joint question.

Open items and their cost models:

- The H-033-02 residual (see section 11): 5-instruction cones
  outside EXP-042's stated bounds, where the sum or the Boolean
  output is produced by two or more instructions. Cost model:
  operations, pursued for mathematical completeness. EXP-041's
  null is the standing evidence that even a proven one-operation
  saving at this site would not be expected to move elapsed
  time on this core.
- Y-003 and Y-048 are dependency depth questions. If the T1
  chain is on the critical path, a shallower tree at equal
  operations could pay where EXP-041's operation removal did
  not. That conditional is precisely what has never been
  measured, and it is the only round-level formulation question
  with a plausible elapsed-time mechanism left.

## 6. The outer hash

Direct formulation today. The outer compression runs all 64
rounds per candidate, in full, after the inner digest exists.
No part of it is precomputed, shared, or skipped, in any
backend.

Established results and their status:

- EXP-027 dependency census, PROVEN: all 48 computed schedule
  words of the outer compression depend on the inner digest,
  and zero complete outer rounds are digest-independent.
  EXP-033 hypothesis H-033-10 (some part of the outer
  compression is precomputable) is REJECTED on the same
  evidence: 48 of 48 words and 64 of 64 rounds are
  digest-dependent.
- H-033-12, partial outer digest comparison to abandon a trial
  early: REJECTED (EXP-033 scope 2). Comparison early exit
  saves no rounds, because the target test needs the completed
  digest's low word, which is a function of all rounds.
- Cross-compression partial execution is refuted by dependency,
  exactly (Stage 1 reconstruction, section 4).

Not examined:

- In-register transpose between block 2 and the outer hash
  (Y-029, NEW). The multi-buffer kernels hold 16 candidate
  states in transposed (structure-of-arrays) layout; the outer
  hash consumes one digest at a time in array layout. The cost
  of converting layout, and whether the outer hash for a group
  can run in the transposed domain (related: Y-005, comparison
  in the transposed domain, NEW), has never been isolated or
  measured. In search mode the outer hash runs only for mask
  hits, so this cost is density-dependent; in batch mode it
  runs for every candidate.
- Outer schedule staging during block-2 tail rounds (Y-067,
  NEW). The EXP-027 census bounds this tightly: every computed
  outer schedule word depends on the digest, which does not
  exist until block 2 finishes, so the only stageable material
  is the two padding constants. This item is listed for
  completeness; the existing evidence already confines it to a
  trivial residue, and it should be closed by citation rather
  than by experiment.
- Feed-forward folded into the final round (Y-060, NEW): an
  algebraic rearrangement of the last feed-forward addition.
  Exact by construction; the question is whether the compiler
  already emits it.

Open items and their cost models:

- Y-029 is a memory traffic and register movement question. Its
  size is bounded by 16 digests of 32 bytes per group in batch
  mode; whether that traffic is visible against 125 rounds of
  arithmetic per candidate is an empirical question nobody has
  priced.
- Y-060 is an operations question with an expected value near
  zero; it is a closure candidate, not an opportunity.

## 7. Target testing

Direct formulation today. Inside the search kernels, a mask or
flags test against the share target identifies candidate lanes
without materialising digests (the EXP-024 and EXP-026 forms;
R-06, return candidate nonces only, INTEGRATED). The batch path
uses the EXP-022 flags form. Every surviving candidate is then
judged by the exact integer test: pow_engine.check_pow with
Core SetCompact semantics, inside verify_candidate. The screen
is never the authority (R-05, INTEGRATED).

Established results and their status:

- EXP-024 design B (predeclared primary) FAILED its criterion;
  design E span scan is an ESTABLISHED NEGATIVE for search.
- EXP-024b design C: VERIFIED as a single-batch mask search,
  pooled 1.398x [1.242, 1.578] against the production search of
  its day. It was not integrated; production took the dual form.
- EXP-026 C2 DualMask: VERIFIED (pooled 1.718x against v512
  search, 1.444x against its strongest ingredient) and
  INTEGRATED as v512dual. C1 TernMask is an ESTABLISHED
  NEGATIVE.
- EXP-032 answered the flags-on-the-search-path question three
  ways, NEGATIVE: the flags batch path loses to native dual
  search by 2.565x; a dedicated flags search entry measured
  0.967x against v512 search, NOT SIGNIFICANT, with the gain
  bounded at about 1.06x; against dual, 0.493x. Flags remain a
  batch-scope feature only.

Not examined:

- Vectorised target comparison for batch consumers (X-088,
  EXPERIMENTAL, untested) and a target-specialised exact
  comparator (X-089, EXPERIMENTAL, untested).
- In-vector top-word pre-filter for search (Y-036, NEW) and
  per-word target thresholds for the in-vector filter (Y-091,
  NEW). These differ from H-033-12: they filter on schedule and
  state words inside the search, not on a partial outer digest,
  so the EXP-033 rejection does not cover them. They also
  differ from the integrated mask forms in where the threshold
  is applied.
- Feed-forward folded into the target comparison (X-030, NEW).

Open items and their cost models:

- The target test itself costs a handful of operations against
  125 rounds of compression; its operations model is negligible
  in every regime. The governing model is elapsed time through
  early-exit frequency, and only at low share difficulty: on
  the solo leg at difficulty 0.02, mask hits are dense enough
  that winner handling, digest materialisation for hits, and
  the verification handoff are real costs; at mainnet
  difficulty the test almost never fires and none of this
  matters. Every item in this section must be evaluated in the
  dense regime or not at all.

## 8. Candidate verification

Direct formulation today. EXP-036's mining/candidate_verify.py,
INTEGRATED: verify_candidate requires hashlib and pure-Python
agreement on the digest, then applies the integer check_pow
verdict. The file contains no floating-point operations at all.
The pool path (mainnet_live.py) and the solo path
(solo_server.py) both route candidates through it.
classify_submit_result and verify_chain_acceptance make
acceptance a best-chain fact, never a submitblock return value.
The GBT engine path does not call verify_candidate inside
mine_cycle; it relies on submitblock plus best-chain equality,
with the EXP-036 check available as an external wrap
(demonstrated end-to-end in Master Build Milestone 6, regtest
block at height 1445, auditor-reproduced at height 1493).
Whether verification moves inside the GBT cycle is roadmap item
F4, an owner decision, not an open technical question.

Established results and their status:

- EXP-036 itself: audited PASS with zero defects; it closed a
  real defect class (solo submitblock None treated as success;
  the Qaxe floating-point difficulty judging rejected as matrix
  item M03 in EXP-030 Phase A).
- EXP-040 measured the verification component end-to-end on the
  GBT pipeline: 2.5 to 3.9 ms per candidate through
  verify_candidate, inside totals of 0.065 s per block (empty),
  0.215 s (loaded, 501 transactions) and 3.299 s (amplified
  search) at regtest difficulty.

Not examined:

- Verification throughput as a fleet bound. Register R-13
  records that coordinator-side re-verification is the design,
  and the EXP-030 matrix (M27) budgets verifier throughput as
  the fleet-size limit, but no measurement of candidates per
  second through verify_candidate under load exists. At 2.5 to
  3.9 ms per candidate the single-thread bound is roughly 250
  to 400 candidates per second; whether that binds depends on
  fleet share density, which is itself unmeasured.
- Verification overlap at dense targets (X-063, NEW):
  pipelining verification of one candidate against search for
  the next, in the dense regime of section 7.

Open items and their cost models:

- Both are elapsed time per candidate in the dense regime.
  Verification is exact and non-negotiable; the only question
  is its throughput and overlap, never its content.

## 9. Search-space management

Direct formulation today. One miner process per machine,
supervised by mining/autopilot.py. Work identity on the GBT
path is the EXP-025 template identity plus the EXP-034
extranonce space (default (0, 64), validated, out-of-range
refused). The EXP-038 checkpoint records an exact frontier
(extranonce, nonce) keyed by template identity, extranonce
space and curtime basis, advancing only after a batch returns
without a hit, so unfinished work is never recorded as
completed. agent/autonomous.py is the only production caller.
The pool path has no equivalent frontier: its coverage rests on
the miner's separated statistics counters, a standing awareness
gap recorded in the Master Build.

Established results and their status:

- EXP-029: the distributed allocator's testable core is PROVEN
  (120 randomised trials with death, duplicate, steal and
  restart injections; completed intervals union exactly to the
  declared range, pairwise disjoint).
- EXP-035: the lease-based distribution design (extranonce2
  partitioned as (slot shifted left 25) OR counter, per the
  Qaxe M06 form; leases with unique IDs, fencing tokens and
  deadlines; restart honesty structural) is PROVEN at prototype
  level: a 60-trial randomised campaign completed 609,280
  declared positions exactly under 2,167 worker deaths, 1,564
  restarts, 801 coordinator restarts, 806 expiries, 694 steals
  and 6,708 reclaims, with 892 duplicate submissions all
  detected. Decision of record: no production integration in
  that phase.
- EXP-043 priced the prototype: core verbs are cheap and mostly
  constant (lease grant 3.1 to 4.7 microseconds, heartbeat 220
  ns, candidate submit 0.77 microseconds in-process); two
  prototype defects dominate at scale (the lease table is never
  pruned, so _holds_lease scans every record ever issued, 67
  percent of CPU in a 32-worker fault trial; snapshot deep-copies
  unbounded history, 420 ms at 8,192 chunks). The 128-worker
  fault trial failed to complete inside its 600 s cap and is
  recorded as a failed run. Loopback round trips for the
  prototype's message shapes: 33 to 54 microseconds per
  operation at one worker process, about 1 ms medians at 16
  processes under this VM's contention.
- EXP-037 statistics and EXP-038 frontier rules are INTEGRATED
  on the paths named above.

Not examined:

- Everything multi-machine: coordination overhead over a real
  network, propagation latency, cross-machine scaling. EXP-043
  closed the in-process and loopback parts only, on this VM.
  The production wire protocol and persistent coordinator are
  specified (EXP-035) and not built (roadmap F1). Fleet
  activation is roadmap F2, an owner decision.
- An exact searched-position frontier for the pool path. The
  live path's unique coverage is currently a counter-based
  claim, cross-checked against the pool's verdicts, not an
  interval-union claim of the EXP-038 kind.
- Hotplug worker attach and detach on a running coordinator
  (R-34, NEW) and quota-based allocation across endpoints
  (R-25, NEW): both presuppose the F1 coordinator.

Open items and their cost models:

- Coordination cost is elapsed time per completed position, and
  EXP-043 gives the local baseline (nanoseconds in-process,
  about 1.2 microseconds per position at 2 workers under fault
  mix, rising steeply with worker count in the prototype for
  implementation reasons, not design reasons). The design verbs
  are not the bottleneck; the two named prototype defects are,
  and both are implementation fixes inside F1, not research
  questions.
- The pool-path frontier is a correctness-of-accounting item,
  not a performance item: its cost model is the exactness of
  the coverage claim itself.

## 10. Backend dispatch and scheduling

Direct formulation today. gpu/engine.py ComputeEngine dispatches
in the order CUDA, v512dual, v512, shani, avx2, C, hashlib. Each
tier is gated by a flag-free CPUID probe and a hashlib self-test,
cascading downward on any failure; pins cascade only through
their own tier list. Thread count is a module-level C_THREADS
global in gpu/engine.py, mutated by probe functions and by the
agent scheduler's measurements; this shared mutable global is a
known defect assigned to the Autonomous Mining Brain Prompt 4
scope, recorded here because it is a dispatch-layer fact. The
agent scheduler (agent/intelligence/scheduler.py) runs an
advisory bake-off through the real search path and changes no
dispatch. Build discipline: production kernel translation units
use restricted flags (never -march=native), with one recorded
legacy exception (Stage 0 discrepancy D7: the shared _compile
helper still builds the older C batch and SHA-NI intrin
libraries with -march=native).

Established results and their status:

- EXP-028: the AVX-512 F plus BW family is VERIFIED on two
  hosts (AMD EPYC 9D25 and Intel Xeon Platinum 8321HC).
- EXP-031: this guest claims 4 vCPUs and delivers about 2
  effective CPUs (estimates 1.87 to 2.04); baseline load 61 to
  64 percent busy before probe load; the ceiling mechanism is
  unknown (no cpu.max at the visible cgroup root) and hardware
  counters are blocked.
- EXP-032 fallback verdicts: AVX2 batch 1.409x [1.340, 1.480]
  and SHA-NI streams-4 batch 2.861x [2.671, 3.089] against
  production C, both VERIFIED; production SHA-NI intrin batch
  0.517x, ESTABLISHED NEGATIVE.
- EXP-039 integrated the shani and avx2 tiers into production
  dispatch. Its own measurements of the byte-identical kernels
  differ from EXP-032 for AVX2: batch 1.252x [1.185, 1.322],
  search 1.300x [1.217, 1.390]; SHA-NI agrees (batch 2.812x,
  search 2.887x). The AVX2 discrepancy is confirmed real,
  unresolved, and changes no verdict (Stage 0 discrepancy D5).
- EXP-039 tier refusal on the SHA-less Intel host and on an
  AVX2-only host is established by probe construction only: the
  probe object code contains no vector or SHA instructions, and
  forced-fallback gates pass. It has never been executed on
  that hardware (EXP-039 audit note N-1; roadmap F7).
- Master Build Milestone 4 bake-off: at 2 threads on this host,
  shani was the nominal winner at 3,207,924 H/s against v512 at
  3,182,548 H/s, a 0.8 percent margin inside contention noise.
  The bake-off's effective-CPU probe read 1.15, contention
  depressed against EXP-031's about 2. Both numbers are
  recorded as advisory observations, not verdicts.
- EXP-021: heterogeneous worker pairs are an ESTABLISHED
  NEGATIVE under this VM's cap.

Not examined:

- Production adoption of the measured bake-off (R-23, NEW as a
  production feature): a margin rule over the static choice,
  re-runs on host change, and refusal behaviour verified
  empirically rather than by construction.
- A first-class offline benchmark mode in the production binary
  (R-35, EXPERIMENTAL by partial analogue): the scheduler's
  fixed-work-unit measurement exists at the agent layer; no
  production binary mode with a fixed bench work unit and no
  submission path exists.
- Drift across VM replacements (X-068, NEW) and session
  fingerprinting of benchmark records (X-069, NEW): the lab's
  hosts alternate between two CPU models across replacements,
  and benchmark records do not yet carry a mandatory session
  fingerprint tying them to host, flags and load. This is the
  methodological hole the AVX2 discrepancy fell through.
- Sustained-rate decay of the fast kernels (X-085, NEW) and the
  span-length crossover for kernel selection (X-083, NEW).
- The -mtune=znver3 scheduling variant of the v512 kernel
  (EXP-041 side finding): the census showed the standalone
  compress body's moves fall from 64 to 33 at the same 29 ALU
  operations. It was not benchmarked. This is a compiler
  scheduling question, distinct from the EXP-041 op-count
  question, and it is carried into the Stage 3 portfolio as
  EXP-044.

Open items and their cost models:

- Dispatch quality is a whole-system elapsed time question.
  EXP-041's control experiment is the warning: on this
  oversubscribed VM, session conditions move measured rates by
  more than small per-kernel differences, so dispatch decisions
  made from single sessions are noise. The governing model is
  elapsed time under contention, measured by EXP-017 or not
  measured at all.
- The C_THREADS global is a correctness-of-measurement defect,
  not a performance item: concurrent measurement sessions can
  change each other's settings, which contaminates exactly the
  evidence this section depends on.

## 11. Rejected items: is any reopening justified?

The mandate's rule: a REJECTED item stays rejected unless new
evidence or a changed condition can be named, and any such case
must be argued explicitly. Two candidates were examined as the
most plausible reopenings. Neither meets the bar.

Candidate 1: the 28-operation round form (Phase 001 H-8,
REJECTED by EXP-041). The argument for reopening would be that
EXP-041 tested gcc's code generation, and a different compiler
or scheduling pass might place the single-ternlog Maj on the
critical path differently. This fails the test on two grounds.
First, EXP-041 did not test one form: it tested six variants,
including the intrinsic-guaranteed 28-op forms, and all three
EXP-017 comparisons returned concordant nulls. Second, the
-mtune scheduling question that survives EXP-041 is a different
hypothesis (same operation count, different instruction
scheduling), already carried as NEW work; relabelling it a
reopening of H-8 would blur exactly the distinction the
registry exists to keep. H-8 stays REJECTED. The -mtune item
enters the portfolio on its own identity.

Candidate 2: heterogeneous worker pairs (EXP-021, ESTABLISHED
NEGATIVE). The argument for reopening would be that the host
fleet changed: the lab now alternates between an AMD host with
SHA-NI and an Intel host without it, so a mixed pool might
behave differently. This fails because EXP-021's negative is a
within-machine result: mixed backend workers on one capped
machine reproduced below the homogeneous pool, and the
mechanism (contention for about 2 effective CPUs) is unchanged
on either host. A cross-machine fleet is a different design
(EXP-035, roadmap F1 and F2), not a reopening of the
within-machine pair. EXP-021 stays REJECTED.

No other rejected item has a named change of evidence or
condition. In particular, EXP-011's unreproduced session figure
is an evidence limitation, not new evidence; EXP-024 design B
failed a predeclared criterion and stays failed; the EXP-019
carry-save price gate, the EXP-014 folding refutation, and the
EXP-016 delta refutations are proof-grade and have no new
counter-evidence. Conclusion: no reopening is justified, and
the portfolio in Stage 3 contains no reopened item.

## 12. Genuinely new or still-open questions

Each question below states why it is still open and what
evidence would close it. Settled results are not listed.

Q1. The H-033-02 residual cone question. Do 5-instruction
cones exist outside EXP-042's stated bounds (sum or Boolean
output produced by two or more instructions)? Still open
because the only instrument covering that generality, full-cone
CEGIS at L=5, timed out in EXP-033 (600 s) and EXP-042 (1,500 s
and 1,400 s per cone). Closed by: a completed solver run at
that generality returning SAT with a verified candidate, or
UNSAT; or a proof that the residual shapes reduce to the
closed ones.

Q2. The -mtune scheduling effect. Does -mtune=znver3 or znver4
scheduling of the v512 kernel change its measured rate, given
the census moves fall from 64 to 33 at equal 29 ALU operations?
Still open because EXP-041 censused but explicitly did not
benchmark this variant. Closed by: an EXP-017 campaign of the
tuned build against the production build, batch and search.

Q3. The AVX2 discrepancy. Why did EXP-032 measure the AVX2
batch at 1.409x [1.340, 1.480] and EXP-039 measure the
byte-identical kernel at 1.252x [1.185, 1.322], with
non-overlapping intervals? Still open because both records
stand and no controlled variable separates them (host state,
build path, session load and library layout are all
candidates). Closed by: a fingerprinted re-measurement campaign
that reproduces one figure under named conditions and
attributes the other, or shows the two condition sets that
produce each.

Q4. EXP-039 refusal on incapable hardware. Does the production
dispatch actually refuse the shani and avx2 tiers and fall back
correctly on the SHA-less Intel host and on an AVX2-only host?
Still open because the answer rests on probe construction, not
execution. Closed by: one make test-exp039 run on the Intel
host when it next rotates in, plus the equivalent forced-tier
run on any AVX2-only host that becomes available.

Q5. Design C against the current v512 search. EXP-024b verified
design C against the production search of its day; v512dual
then integrated, and the v512 search build itself is the
current fallback reference. Is design C still the fastest
single-batch search form? Still open because the baseline
moved after the measurement. Closed by: an EXP-017 re-measurement
of design C against today's v512 search, in the single-batch
scope only.

Q6. Category F at production difficulty, and for the solo and
pool pipelines. EXP-040 measured end-to-end cost only for the
GBT pipeline at regtest difficulty (plus an amplified variant).
Still open because no production-difficulty end-to-end figure
exists for any pipeline, and none at any difficulty for solo or
pool. Closed by: an amplified-difficulty campaign on the solo
and pool paths using the EXP-040 harness shape, reported as
category F with the amplification stated.

Q7. Multi-machine coordination. What are the coordination
overhead, real-network propagation latency, and cross-machine
scaling of the EXP-035 design? Still open because EXP-043
measured only in-process and loopback behaviour on this VM,
and the production coordinator is unbuilt. Closed by: the
roadmap F1 build, its fault campaign at the EXP-035 standard,
and a two-machine measurement. Fleet activation itself remains
an owner decision (F2) and is not part of the question.

Q8. An exact frontier for the pool path. Can the live pool
miner's unique coverage be stated as an interval union of the
EXP-038 kind rather than as counters? Still open because the
pool path never adopted the checkpoint machinery, and Stratum
job churn changes work identity outside the miner's control.
Closed by: a frontier design for the pool path that survives
job changes without false completion, plus an audit of its
accounting against the evidence log census.

Q9. The verifier throughput bound. At what candidate rate does
coordinator-side verify_candidate become the fleet bottleneck
(the EXP-030 matrix M27 budget)? Still open because only the
per-candidate latency (2.5 to 3.9 ms, EXP-040) is measured, not
throughput under load or its interaction with share density.
Closed by: a load measurement of the verifier at controlled
candidate rates, with the density assumptions stated.

Q10. The block-2 to outer-hash layout conversion. What does the
transposed-to-array digest conversion cost in batch mode, and
can the outer hash run in the transposed domain (Y-029, Y-005)?
Still open because the conversion has never been isolated from
the 125 rounds it sits between. Closed by: an instrumented
build that prices the conversion separately, followed by an
EXP-017 test of any transposed-domain outer form.

Q11. Port-model validity without counters. Can a vector port
model of these cores be validated at all on this VM, where
hardware counters return EPERM? Still open because every
scheduling claim in the programme (including EXP-041's
mechanism) rests on static reasoning plus EXP-017 outcomes.
Closed by: a prediction test: the model must forecast the
sign and rough size of a measured EXP-017 effect for a change
it did not fit, before the measurement is run.

Q12. Prefix sharing as a combination ingredient. EXP-013
measured cross-lane prefix sharing alone and its ratios
straddled 1.0; Phase 001 H-6 keeps the rate question open only
inside a combined design, and no combined design (for example
Y-098, prefix sharing inside the dual-batch walker) has been
built. Closed by: building the combined form and measuring it
under EXP-017 against v512dual.

Q13. The OP-1 umbrella question. Can any equivalent computation
graph evaluate SHA-256d with materially fewer primitive
operations than the conventional 125-round remainder? Still
open because every closure in the programme is piecewise
(EXP-020 within its vocabulary, EXP-027, EXP-033 and EXP-042
in named spaces), and the conventional accounting is not a
lower bound. Closed by: either a construction that beats the
remainder and verifies, or lower-bound proofs extended to the
residual spaces one by one, of which Q1 is the current
instance. This question is recorded for completeness; it is
not a plan.

Q14. Solo vardiff dynamics. The vardiff design is decided
(register R-12; EXP-030 matrix M10) and the solo share
difficulty is still fixed at 0.02 in the operative endpoint
config. Whether the decided controller holds a stable share
interval at production worker rates, without oscillation, is
unmeasured because no implementation exists. Closed by: the
implementation plus a regtest campaign measuring share-interval
error and adjustment behaviour across rate steps.

Q15. Session fingerprinting and benchmark drift. Why do
instruction-identical libraries disagree across session batches
on this VM by more than small effect sizes (EXP-041 control),
and can a mandatory session fingerprint (host, flags, load,
steal) explain the variance (X-068, X-069)? Still open because
benchmark records do not yet carry the fingerprint that would
let the question be answered from data. Closed by: fingerprint
capture on all new campaigns, then a variance attribution over
the accumulated records, including Q3's.

Total genuinely open questions: 15 (Q1 to Q15). Of these, Q13
is an umbrella recorded for completeness, Q7 and Q8 are bounded
by unbuilt infrastructure and an owner decision, and the
remaining 12 are closable with work on this VM or on the next
host rotation.
