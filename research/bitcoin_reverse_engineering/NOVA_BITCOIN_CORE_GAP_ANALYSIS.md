# NOVA Bitcoin Core Gap Analysis

NOVA SHA-X Master Assignment, deliverable 15. Date: 2026-11-15.

NOVA measured against Bitcoin Core, function by function: what NOVA
implements that Core never had, what Core has that NOVA lacks or
leaves unwired, and the documentation debt the Phase A audit
recorded. Sources: research/bitcoin_reverse_engineering/
NOVA_REPOSITORY_AUDIT.md (the Phase A truth baseline, verified
against production source), research/bitcoin_core/ (the pinned
v28.1 source audit set, commit
32efe850438ef22e2de39e562af557872a402c31), the wave A to C
deliverables of this assignment, and research/phase001/
COMPARATIVE_NOVA_REPORT.md.

Status vocabulary: PRESENT (in production, verified), PROTOTYPE
(proven in research, not integrated), ABSENT (does not exist),
UNWIRED (exists in production code but no live path calls it).

## 1. Function-by-function comparison

| Function | Bitcoin Core v28.1 | NOVA | Gap direction |
|---|---|---|---|
| Header hashing | Generic single-stream CSHA256 via HashWriter; no midstate API; SHA256D64 multi-way machinery used only by the Merkle tree (merkle.cpp:56) | Multi-buffer kernels with cached midstate (v512dual, v512, C batch), CPUID-probed dispatch, hashlib floor | NOVA ahead: Core has no mining hash path at all |
| Midstate / reusable header state | Absent in both eras (v0.1.3 recomputed chunk 1 per candidate; v28.1 has no facility) | Present since the C midstate backend; the conventional 67-of-192 prefix is cached per template | NOVA only |
| Production search | None. The only in-tree nonce loop is the regtest GenerateBlock utility, single-threaded, generic path | Live production search (ComputeEngine counted search entries; mainnet_live on public-pool.io; MiningEngine on GBT; solo server path) | NOVA only |
| Target decoding and judgement | arith_uint256 SetCompact with fNegative/fOverflow reporting; rejection owned by CheckProofOfWork (pow.cpp:137 to 154); integer hash <= target, equality accepted | mining/candidate_verify.py implements the modern rule set exactly (EXP-036): dual recomputation (hashlib plus pure Python), negative/overflow/zero/over-limit rejection, integer comparison | Parity, by deliberate implementation; NOVA also carries a simple second decoder (mining/pow.py) used only for bookkeeping, never for a submission decision |
| Template construction | BlockAssembler behind interfaces::Mining; GBT with RPC-layer cache (rebuild on new tip or mempool change older than 5 s); server coinbase is height push plus OP_0 | MiningEngine consumes GBT and builds its own coinbase (BIP34 height, "/BAL/" marker, engine extranonce, witness commitment); EXP-025 template cache under a layered cryptographic identity; solo server builds jobs from its own node | Different division of labour by design; NOVA's cache and identity machinery have no Core analogue |
| Extranonce ownership | Entirely client-side; no IncrementExtraNonce exists in v28.1; OP_0 is the fossil space | Engine-owned, with opt-in extranonce_space windows (EXP-034, default (0, 64) byte-identical to historical behaviour) | Parity of ownership; NOVA adds partitioning machinery Core never needed |
| Candidate verification | CheckBlock / CheckBlockHeader / CheckProofOfWork inside ProcessNewBlock | Pre-submission verify_candidate plus classify_submit_result plus verify_chain_acceptance (acceptance requires chain confirmation, never the submitblock return alone) | NOVA ahead on the client side: Core's null return is not best-chain proof, and NOVA's client rule encodes exactly that |
| Submission | submitblock with BIP22 strings; ProcessNewBlock, AcceptBlock, ConnectBlock; chain selection by nChainWork | GBT path (inline tip-equality check, equivalent standard, code not shared with candidate_verify), solo path (full EXP-036 routing), pool path (verify before submit, job-generation freshness guard) | Parity of standard; one consistency note (unshared GBT check) recorded in the audit |
| Work distribution | None (single node, external miners are independent) | EXP-035 lease manager, coordinator and candidate queue: PROTOTYPE, proven in-process (60 of 60 campaign trials, exact disjoint coverage under deaths, restarts and steals); multi-machine overhead, latency and scaling UNVERIFIED; fleet not activated | NOVA design ahead; production absent (section 3) |
| Search-space dimensions | Nonce only inside Core's regtest utility; extranonce is the client's | Nonce plus engine extranonce live; version rolling and ntime rolling ABSENT on every production path (EXP-034 finding) | Gap on NOVA's side (section 3) |
| Mining statistics | None (RPC estimates only: getnetworkhashps is a chain-derived estimate, not miner telemetry) | mining/mining_statistics.py with separated, never-summed counters (EXP-037): correct and tested, but UNWIRED: record() has no live caller; live accounting is reconstructed from the evidence log by the autopilot's EvidenceCounter | Module ahead of Core; wiring gap on NOVA's side |
| Probability model | None | mining/probability.py (expected hashes, expected seconds, probability over time, days helper): present but incomplete against BR-011: no median or percentile outputs, no exact-target form, no N-trial form, no period helpers beyond days; the full model and the seven-function specification now exist in research/probability/BITCOIN_MINING_PROBABILITY_MODEL.md | Specification ahead; implementation gap on NOVA's side |
| Restart honesty | Not applicable to Core's design (no resumable search) | mining/work_checkpoint.py (EXP-038): exact (extranonce, nonce) frontier keyed by layered identity plus extranonce space plus curtime basis; frontier advances only after a hitless batch; opt-in, live caller is agent/autonomous.py | NOVA only |
| Template freshness signalling | GBT longpoll (wait on tip / mempool notifications) | MiningEngine.wait_template implements the longpoll but has NO production caller; the GBT path polls per cycle; Stratum paths key on prevhash and job generation | Gap on NOVA's side: implemented, unwired |
| Stratum | Not part of Core at all | Both ends implemented: solo server (job refresh with IBD refusal, share validation through candidate_verify) and pool client (job validation, duplicate and stale-echo guards); V1 only; Stratum V2 ABSENT | NOVA only for V1; V2 gap recorded |
| Node operation | Core is the node | NOVA runs its own pruned mainnet Core (prune=550) under .local/mainnet, still in initial block download at the time of writing; solo cutover staged and armed, not fired; live mining still on the external pool | In progress by design; the cutover watcher owns the transition |

## 2. What NOVA implements that Core never had

Consolidated, with tiers:

1. **Midstate multi-buffer search kernels** (v512dual DualMask,
   VERIFIED IMPROVEMENT pooled 1.718x over the v512 search,
   EXP-026; v512, VERIFIED 3.55x over production C in batch scope,
   EXP-017; the complete production search at 6.781x over C search,
   EXP-032). Core's fastest header-hash path is a generic
   single-stream CSHA256; the SHA256D64 machinery exists in Core
   but serves the Merkle tree only.
2. **Exact candidate verification with chain confirmation** as a
   client discipline (EXP-036, audit PASS WITH NOTES, zero
   defects): dual-implementation recomputation, modern SetCompact
   rejection semantics, and acceptance decided from chain state.
   This closed a real defect class (submitblock None treated as
   success) that the pre-EXP-036 solo path carried.
3. **A template cache with a layered cryptographic identity**
   (EXP-025 repaired design, integrated): family, transaction,
   coinbase and header keys combined under dsha256, identity
   computed only after a full validation pass, with a preserved
   uncached fallback. The audit verified the fingerprint complete
   over the construction's actual dependency set.
4. **A distributed work allocator design with proofs** (EXP-035):
   leases with fencing tokens, the Qaxe-style extranonce2 partition
   (slot << 25) | counter, a candidate queue, and never-summed
   accounting, proven in-process over 60 of 60 randomised campaign
   trials (609,280 declared positions, union-complete and pairwise
   disjoint under injected deaths, restarts and steals). PROTOTYPE
   tier: the design is proven; the production system does not exist.
5. **Mining statistics and probability modules** (EXP-037):
   separated counters with no combined total by construction, and
   difficulty-form probability functions pinned to anchors and
   cross-checked against exact rational arithmetic.
6. **Restart-honest checkpointing** (EXP-038): an exact frontier
   that structurally cannot record unfinished work as completed,
   proven over a 24-configuration randomised restart campaign.
7. **A supervision stack Core never needed:** the autopilot
   (heartbeat, watchdog, crash backoff, session rotation), the
   outer keeper, the EvidenceCounter that fixed the heartbeat share
   census (full-log count; 248 accepted at the EXP-037 audit census
   and growing since), and the solo cutover state machine with
   automatic rollback.

## 3. What Core has that NOVA lacks or leaves unwired

Each item with its work package and its honest status:

1. **Production coordinator, lease manager and candidate queue**
   (BR-015, BR-007). EXP-035 is a research prototype; no production
   code assigns extranonce_space windows, holds leases, or queues
   candidates. A found candidate is submitted synchronously on
   every path. ABSENT in production.
2. **Stratum V2** (BR-012). NOVA speaks Stratum V1 only, both ends.
   ABSENT.
3. **Version rolling (BIP320) and timestamp rolling** (BR-007).
   Absent on every path (EXP-034): the per-template search space is
   nonce times the extranonce window only. ABSENT.
4. **A longpoll caller** (BR-012). wait_template is implemented and
   correct; nothing in production calls it. UNWIRED.
5. **Live statistics wiring** (BR-011, BR-016).
   mining_statistics.record() has no production caller; live
   accounting is reconstructed from the evidence log. UNWIRED.
6. **Probability percentile outputs** (BR-011). The model now
   specifies median and 90th/95th/99th percentile times, the
   exact-target form, the N-trial form and period helpers, with
   seven functions specified to signature level
   (BITCOIN_MINING_PROBABILITY_MODEL.md section 8). The module does
   not implement them. ABSENT in code, specified in research.
7. **A category F end-to-end benchmark** (BR-010). End-to-end
   correctness is proven by regtest tests and live operation; no
   timed end-to-end pipeline measurement exists anywhere.
   ABSENT as a measurement.
8. **Dispatch tiers for non-AVX-512 hosts** (BR-008, BR-016).
   EXP-032 verified an AVX2 multi-buffer kernel (1.409x over C,
   batch) and the SHA-NI streams-4 kernel (2.861x over C, batch);
   neither is dispatched. The production SHA-NI translation unit is
   the older single-stream form EXP-032 measured at 0.517x
   (ESTABLISHED NEGATIVE), and ComputeEngine does not dispatch it.
   Hosts without AVX-512F+BW fall back to C or hashlib, exactly as
   before EXP-032. VERIFIED in research, ABSENT in production.
9. **A shared acceptance check on the GBT path** (BR-012).
   MiningEngine's inline tip-equality check is equivalent to
   verify_chain_acceptance but not shared code; no reorg re-check
   follows an accepted block on any path. Consistency gap, recorded
   by the audit as a note, not a defect.
10. **VM intelligence consumption** (BR-009). EXP-031 characterised
    the VM (about 2 effective CPUs under a 61 to 64 percent busy
    baseline); no production code consumes capacity intelligence.
    Dispatch is pure CPUID. A defensible design, recorded because
    the directive's environment picture is a point sample, not a
    standing mechanism.

## 4. Documentation gaps: the 11 contradictions

From NOVA_REPOSITORY_AUDIT.md section 13 (items 1 to 11; the
audit's item 12 records docs/EVIDENCE.md as not a contradiction).
Severity is this analysis's assignment: HIGH means a reader trusting
the document misunderstands what the production system is or what
the evidence shows; MEDIUM means a material fact is wrong or stale;
LOW means omission or over-broad wording with the correct record
nearby.

| # | Document and claim | Source truth | Severity |
|---|---|---|---|
| 1 | README testing section: "make test-all runs 15 suites" | Makefile test-all lists 30 targets; audit ran them individually: 27 of 30 cold, 29 of 30 with the regtest wallet loaded, test-rtl blocked on absent iverilog | MEDIUM |
| 2 | README CPU aspect: production miner described as a C batch engine through OpenSSL's SHA-NI path, with a 2026-11-14 update naming v512 | Production backend is v512dual (DualMask); README never mentions v512dual, the template cache, candidate_verify, or EXP-030 | HIGH |
| 3 | README: "End to end engine rate 6,617,558 H/s" | The figure is a category D batch_search measurement from the C-backend era; labelling it end to end presents D as E/F | HIGH |
| 4 | README status at a glance: worker shown as bc1q528egeqsvv8aa382j43edxskqw6x7zxc2xpcf3.bal1 | Since 2026-11-14 every entry point defaults its worker to the machine hostname (this VM mines as htch-runtime); the README's own status log records the change, so the file contradicts itself | MEDIUM |
| 5 | README repository map: "research/: statistics and probability engine" | research/ holds the whole SHA-X programme (registries, exp030 to exp038 trees) plus the probability and statistics originals | LOW |
| 6 | docs/ARCHITECTURE.md decision 2: "mainnet paused", Stratum code "paused by owner instruction" | Mainnet pool mining has been live and owner-ordered since 2026-11-13; the solo cutover is armed. The oldest standing contradiction in the tree, already recorded by the EXP-030 Phase B gap analysis and still unfixed | HIGH |
| 7 | docs/ARCHITECTURE.md module map: "gpu/: research gate, no implementation"; mining/ described as four Task-era files; bal_miner.c called "the SHA-NI CPU engine" | gpu/engine.py IS the production ComputeEngine hosting every CPU backend; mining/ holds the GBT engine, solo server, autopilot, candidate verifier, statistics, probability and checkpoint modules; the production kernels are the bal_avx512*.c and bal_batch.c units | HIGH |
| 8 | docs/ARCHITECTURE.md: "The repo stays private until the owner resolves that in one message" | The repository is public; the owner flipped it on 2026-11-13 and the audit's push verification recorded private: false | MEDIUM |
| 9 | evidence/SUMMARY.md: "Evidence level reached: E2... No share has been accepted by a pool yet" | The same directory's evidence/mainnet-live.jsonl contains the pool-accepted shares (first 2026-11-13 18:59:51 UTC; 248 accepted at the EXP-037 census); README and docs/EVIDENCE.md both record E3 | HIGH |
| 10 | docs/MINING_ENGINE.md: describes the midstate C backend as the engine's advance | No mention of the AVX-512 backends, DualMask, the flags batch, the template cache or candidate verification; a Task 003-era document presented without a date boundary | MEDIUM |
| 11 | PRODUCTION_INTEGRATION_LOG.md Entry 3 consumer trace for batch_search | Reads broader than the current call graph: the dashboard and agent reach batch_search only through ComputeEngine.benchmark(), for a benchmark figure; neither mines through it. The entry's scope claim itself (batch consumers only) is exact | LOW |

None of the 11 touches production correctness; all 11 touch what a
reader believes about the system, which is what Phase A existed to
prevent. They remain unfixed at the time of writing and are carried
as documentation debt into the next phase's scope (MASTER_RESEARCH_
FINDINGS.md section 7).

## 5. Net assessment

- On the mining engine itself, NOVA is strictly ahead of anything
  Core contains: Core has no production miner to be behind with.
  The comparison that matters is not NOVA versus Core's miner; it
  is NOVA versus the complete system the Master Assignment
  specifies, and against that specification the gaps are items 1 to
  10 of section 3: distribution, rolling, wiring, dispatch tiers,
  and one missing benchmark category.
- On consensus fidelity, NOVA is at parity by construction and by
  audit: the verifier implements the modern rejection semantics,
  templates are validated field by field before use, and acceptance
  is decided from chain state.
- On documentation, NOVA is behind its own code by roughly two
  backend generations and one evidence level. The code and the
  research record are trustworthy; the front-door documents are
  not, yet.
