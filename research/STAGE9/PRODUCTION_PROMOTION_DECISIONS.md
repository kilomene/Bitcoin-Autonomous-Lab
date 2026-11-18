# Stage 9 Production Promotion Decisions

Stage: 9.2 (production promotion decisions and outstanding
defect resolution). Date: 2026-11-18. Repository:
kilomene/Bitcoin-Autonomous-Lab. Remote HEAD at the Stage 9.1
baseline: 883cf281be6c41617f27b8b44d1aa27e3c94df29 (see
REPOSITORY_BASELINE.md). Last deliberate, audited push:
11277e6f532a48844be5c9f33aa8ef6a755683c2.

Inputs: REPOSITORY_BASELINE.md, EXPERIMENT_CLOSURE_LEDGER.json
(109 records), EXPERIMENT_CLOSURE_REPORT.md (discrepancies
D-01 to D-10). Every promotion class below was decided from
current source, not from the ledger alone: imports and calls
were traced from the three live entry points
(mining/autopilot.py, mining/mainnet_live.py) and the agent
control path (agent/autonomous.py, agent/intelligence/
controller.py), through mining/engine.py, mining/solo_server.py,
mining/stratum_client.py and gpu/engine.py.

Scope discipline for this stage: no production code was
modified. No live process, node, wallet or endpoint
configuration was touched. Nothing was pushed. Live enablement
of bakeoff dispatch, endpoint health failover, prefetch,
aggregation, PID control and the coordinator remains an owner
decision and none of it was enabled here.

## 1. The production paths, as traced

There are three distinct execution paths in the current tree,
and a record can be integrated into one without being live on
another. Promotion decisions below name the path.

- Live pool path (what is mining now): mining/autopilot.py
  supervises mining/mainnet_live.py, which builds a
  StratumClient to public-pool.io (endpoint mode "pool" in
  .local/mining-endpoint.json, keys verified: mode, pool, solo,
  payout_address; no bakeoff or pool_health section present),
  constructs gpu.engine.ComputeEngine, searches with
  engine.search_first (mining/mainnet_live.py line 324), and
  verifies every hit with mining/candidate_verify.
  verify_candidate before submission.
- GBT and agent path: mining/engine.py MiningEngine (GBT
  longpoll, TemplateCache, WorkCheckpoint, optional prefetch).
  Its production constructors in the tree are
  agent/autonomous.py (line 48, the regtest-era autonomous
  miner), mining/testnet4_attempt.py (line 69, stood down) and
  mining/cpu/miner.py (line 133). Only the agent path is
  live-relevant: mining/cpu/miner.py is imported by nothing
  live (it is mentioned only in a gpu/engine.py comment), so
  the live path conclusion is unchanged.
  mining/mainnet_live.py never imports mining.engine.
  mining/solo_server.py imports three helpers from
  mining.engine (address_script_pubkey, build_coinbase,
  strip_witness) at two deferred import sites (lines 536 and
  574), so part of that module is on the solo path.
- Solo path (built, not live while mode is "pool"):
  mining/solo_mainnet.py constructs SoloServer, optionally with
  a VarDiffController, and mining/solo_server.py validates
  shares and submits blocks through candidate_verify.

Modules imported by nothing on any live path (verified by
import scan of mining/*.py, agent/*.py, agent/intelligence/*.py
and gpu/*.py): mining/coordinator.py (EXP-055),
mining/aggregation.py (EXP-057), mining/pid_control.py
(EXP-058). mining/bench_mode.py (EXP-049) is imported only by
its own test and run standalone as a module.

## 2. Promotion classes: counts

| Promotion class | Count |
| --- | --- |
| ADD TO PRODUCTION | 28 |
| KEEP AS RESEARCH | 41 |
| KEEP DISABLED / EXPERIMENTAL | 18 |
| DO NOT ADD | 15 |
| DEFER | 7 |
| Total | 109 |

ADD TO PRODUCTION means: already invoked by a production path
in current source and stays; no new enablement is proposed by
this stage. For records whose scope is narrower than the live
pool path, the table says so in the row.

## 3. Flagged INTEGRATED records: code present, not live as claimed

These are the Stage 9.1 D-07 findings, verified again in
current source for this stage. None is a reason to remove code;
each is a reason the registry word INTEGRATED must not be read
as live effect.

- F-1, R-26 and EXP-050 (endpoint health policy,
  mining/endpoint_health.py): genuinely wired.
  mining/mainnet_live.py builds EndpointHealthPolicy only when
  pool_health_config reports enabled (POOL_HEALTH_DEFAULTS
  enabled False in mining/endpoint_config.py), and
  mining/stratum_client.py policy hooks (_policy_note_error,
  _policy_note_success, _maybe_failback, _probe_endpoint) all
  no-op while client.endpoint_policy is None. The live config
  carries no pool_health section, so the policy object is never
  constructed at runtime. True state: integrated code,
  default-off, zero live effect. Class: KEEP DISABLED /
  EXPERIMENTAL (enablement is an owner decision, and a real
  second endpoint does not exist yet). Note the ledger pair is
  internally inconsistent: R-26 is INTEGRATED while EXP-050,
  the experiment that built the same code, is
  PROVEN_NOT_INTEGRATED. Section 6 proposes the repair.
- F-2, EXP-051 and R-33 (prefetch, mining/prefetch.py):
  mining/engine.py imports PrefetchFeed and PrefetchQueue at
  top level (line 26) but constructs them only when
  use_prefetch is true (MiningEngine constructor, default
  False; _prefetch_usable also requires the template cache).
  No production constructor passes use_prefetch=True. True
  state: opt-in hook on the GBT path only, never enabled, and
  the GBT path itself is not the live pool path. Class: KEEP
  DISABLED / EXPERIMENTAL.
- F-3, EXP-052 and R-23 (bakeoff dispatch,
  mining/bakeoff_dispatch.py): mining/mainnet_live.py consults
  resolve_requested only under bakeoff_cfg["enabled"]
  (lines 253 to 265); BAKEOFF_DEFAULTS enabled False; the live
  config has no bakeoff section; no cache file exists at
  .local/bakeoff-dispatch.json (checked). True state: seam
  present, resolver never consulted live. Class: KEEP DISABLED
  / EXPERIMENTAL. Full reconciliation in section 5.1.
- F-4, R-12 (vardiff, mining/solo_server.py VarDiffController):
  mining/solo_mainnet.py constructs the controller only when
  solo_vardiff_config reports enabled (SOLO_VARDIFF_DEFAULTS
  enabled False, lines 107 to 126 of solo_mainnet.py);
  SoloServer defaults vardiff=None, the fixed-difficulty path.
  The solo server is itself not the live path while the
  endpoint mode is pool. True state: integrated code on a
  non-live path, behind a default-off switch. Class: KEEP
  DISABLED / EXPERIMENTAL.
- F-5, EXP-022 (AVX-512 flags batch, gpu/engine.py
  _try_v512flags and _vf_batch_flagged): the flags entry is
  selected at ComputeEngine construction (line 996) but serves
  only batch_search (routing at lines 2429 to 2442). The live
  pool miner searches with search_first (mainnet_live.py line
  324), which never routes to the flags entry, and EXP-032
  measured the flags form in the search entry at 0.967x, not
  significant. True state: live code, batch scope only, no live
  pool search effect. Class: ADD TO PRODUCTION with that scope
  recorded; the 1.441x pooled figure is a batch figure and must
  never be quoted as a search-path gain.
- F-6, the MiningEngine family (EXP-025, EXP-034,
  EXP-030-PHASE-E, EXP-038, PHASE001-H-1, PHASE001-H-5, R-08,
  R-10): integrated into mining/engine.py, which the live pool
  miner does not import (see section 1). These records are
  live on the GBT and agent path and in tests, not on the live
  pool path. Two partial exceptions: EXP-034, because
  solo_server imports build_coinbase and strip_witness from
  mining.engine; and EXP-037, whose statistics module is
  imported directly by mainnet_live.py and is live on the pool
  path in its own right. EXP-038 is narrower still: the
  WorkCheckpoint is constructed only when a checkpoint_path is
  passed, and the only production caller that passes one is
  agent/autonomous.py (line 50). Class for the family: ADD TO
  PRODUCTION, with the path scope stated per row.
- F-7, R-13 (coordinator re-verifies every candidate): the
  principle is live, the named architecture is not. What the
  live paths actually invoke is mining/candidate_verify.
  verify_candidate (EXP-036) inside mainnet_live.py and
  solo_server.py; workers never submit directly on those paths
  by construction. mining/coordinator.py, the module the
  register wording points at, is imported by nothing live.
  Class: ADD TO PRODUCTION as a principle embodied by EXP-036,
  with the coordinator itself decided under EXP-055.

## 4. Promotion decision table (all 109 ledger records)

| ID | Ledger disposition | Promotion class | Evidence basis (production call path) |
| --- | --- | --- | --- |
| EXP-000 | PROVEN_NOT_INTEGRATED | KEEP AS RESEARCH | Result stands as recorded (Production C batch 1 thread median 1,314,704 H/s); no import of its module from the live entry points in current source, so no production effect. |
| EXP-001 | REJECTED | DO NOT ADD | Negative finding preserved with its evidence; production path unchanged by it. All variants rejected |
| EXP-002 | PROVEN_NOT_INTEGRATED | KEEP AS RESEARCH | Result stands as recorded (Accepted as a proven research kernel; the MSG schedule alone is worth about 2.6x over the scalar schedule. Not integrated as built); no import of its module from the live entry points in current source, so no production effect. |
| EXP-003 | PROVEN_NOT_INTEGRATED | KEEP AS RESEARCH | Result stands as recorded (Hypothesis supported; H-01 streams-4 1-thread median 3.30M H/s. The streams-4 form was later integrated as the shani tier through ); no import of its module from the live entry points in current source, so no production effect. |
| EXP-004 | REJECTED | DO NOT ADD | Negative finding preserved with its evidence; production path unchanged by it. The integration was rejected, not the kernel |
| EXP-005 | PROVEN_NOT_INTEGRATED | KEEP AS RESEARCH | Result stands as recorded (Accepted as the family geometry map used by later stream work); no import of its module from the live entry points in current source, so no production effect. |
| EXP-006 | REJECTED | DO NOT ADD | Negative finding preserved with its evidence; production path unchanged by it. Rejected as champion; retained as evidence |
| EXP-007 | PROVEN_NOT_INTEGRATED | KEEP AS RESEARCH | Result stands as recorded (Accepted as the family fastest measured kernel of its phase; ancestor of the production v512 backend); no import of its module from the live entry points in current source, so no production effect. |
| EXP-008 | REJECTED | DO NOT ADD | Negative finding preserved with its evidence; production path unchanged by it. Rejected on this core |
| EXP-009 | PROVEN_NOT_INTEGRATED | KEEP AS RESEARCH | Result stands as recorded (Measurements stand; X-059 closed by this study); no import of its module from the live entry points in current source, so no production effect. |
| EXP-010 | REJECTED | DO NOT ADD | Negative finding preserved with its evidence; production path unchanged by it. Neither candidate passed; no integration resulted from this run |
| EXP-011 | EXPERIMENTAL | KEEP DISABLED / EXPERIMENTAL | Research-stage variant with no production module on a live path; not invoked by mining/autopilot.py, mining/mainnet_live.py or agent/autonomous.py in current source. |
| EXP-012 | PROVEN_NOT_INTEGRATED | KEEP AS RESEARCH | Result stands as recorded (Closed formally: Ch = 0xCA, Maj = 0xE8, XOR3 = 0x96; classic op counts proven minimal within the searched vocabulary); no import of its module from the live entry points in current source, so no production effect. |
| EXP-013 | UNDER_INVESTIGATION | KEEP AS RESEARCH | Investigation open; no production module invoked by a live path; conclusion not yet supported by the recorded evidence. |
| EXP-014 | REJECTED | DO NOT ADD | Negative finding preserved with its evidence; production path unchanged by it. Rejected as implemented; the agent loop still refuses re-proposal citing this entry |
| EXP-015 | REJECTED | DO NOT ADD | Negative finding preserved with its evidence; production path unchanged by it. Rejected by measurement at about 0.03x of MB16 |
| EXP-016 | PROVEN_NOT_INTEGRATED | KEEP AS RESEARCH | Result stands as recorded (W18 delta is exactly sigma0(nonce), XOR-linear; W19 delta is exactly the nonce; W20 onward fully nonlinear and the first word with); no import of its module from the live entry points in current source, so no production effect. |
| EXP-017 | PROVEN_NOT_INTEGRATED | KEEP AS RESEARCH | Result stands as recorded (Protocol adopted as the programme integration decision rule by owner decision 2026-11-14: 3+ sessions, paired 65,536-hash blocks, ); no import of its module from the live entry points in current source, so no production effect. |
| EXP-018 | EXPERIMENTAL | KEEP DISABLED / EXPERIMENTAL | Research-stage variant with no production module on a live path; not invoked by mining/autopilot.py, mining/mainnet_live.py or agent/autonomous.py in current source. |
| EXP-019 | REJECTED | DO NOT ADD | Negative finding preserved with its evidence; production path unchanged by it. Rejected at the price gate: a software 3:2 compressor costs 3 instructions, not 2 |
| EXP-020 | PROVEN_NOT_INTEGRATED | KEEP AS RESEARCH | Result stands as recorded (The full round is closed at its vocabulary optimum: 28 vector ops per steady-state round, with an SMT lower bound of 28 within the); no import of its module from the live entry points in current source, so no production effect. |
| EXP-021 | REJECTED | DO NOT ADD | Negative finding preserved with its evidence; production path unchanged by it. Established negative |
| EXP-022 | INTEGRATED | ADD TO PRODUCTION | gpu/engine.py selects the flags entry at construction (line 996) and routes only batch_search to it (lines 2429 to 2442); live pool search uses search_first, so scope is batch only (flag F-5). Pooled 1.441x is a batch figure. |
| EXP-023 | EXPERIMENTAL | KEEP DISABLED / EXPERIMENTAL | Research-stage variant with no production module on a live path; not invoked by mining/autopilot.py, mining/mainnet_live.py or agent/autonomous.py in current source. |
| EXP-024 | EXPERIMENTAL | KEEP DISABLED / EXPERIMENTAL | Research-stage variant with no production module on a live path; not invoked by mining/autopilot.py, mining/mainnet_live.py or agent/autonomous.py in current source. |
| EXP-024b | PROVEN_NOT_INTEGRATED | KEEP AS RESEARCH | Result stands as recorded (Pooled 1.398x [1.242, 1.578], significant in every session and pooled; control null; B/C interleave 1.011x null. Verified improvem); no import of its module from the live entry points in current source, so no production effect. |
| EXP-025 | INTEGRATED | ADD TO PRODUCTION | mining/engine.py TemplateCache and template_identity, invoked by MiningEngine on the GBT and agent path; live pool miner does not import mining.engine (flag F-6). |
| EXP-026 | INTEGRATED | ADD TO PRODUCTION | gpu/engine.py v512dual tier, first CPU tier in the dispatch order; constructed by mainnet_live.py via ComputeEngine on the live pool path. Pooled 1.718x vs v512 search under EXP-017. |
| EXP-027 | PROVEN_NOT_INTEGRATED | KEEP AS RESEARCH | Result stands as recorded (Characterised search, negative result: every named sub-space closed with proofs at stated scopes; census 0 nontrivial subterms sha); no import of its module from the live entry points in current source, so no production effect. |
| EXP-028 | PROVEN_NOT_INTEGRATED | KEEP AS RESEARCH | Result stands as recorded (AVX-512 F+BW family verified on two hosts (AMD EPYC 9D25 and Intel Xeon Platinum 8321HC); flag-free probe and dispatch specificati); no import of its module from the live entry points in current source, so no production effect. |
| EXP-029 | PROVEN_NOT_INTEGRATED | KEEP AS RESEARCH | Result stands as recorded (Testable core proven: 120 randomised trials with death, duplicate, steal and restart injections; completed intervals union exactly); no import of its module from the live entry points in current source, so no production effect. |
| EXP-030 | PROVEN_NOT_INTEGRATED | KEEP AS RESEARCH | Result stands as recorded (All phases A to H completed, audited and pushed at head 018221a9 with a final report answering all 16 section-16 questions; succes); no import of its module from the live entry points in current source, so no production effect. |
| EXP-031 | PROVEN_NOT_INTEGRATED | KEEP AS RESEARCH | Result stands as recorded (The guest delivers about 2 effective CPUs (estimates 1.87 to 2.04); production ComputeEngine on v512dual: 1T 5.19M/5.50M H/s, 2T 9); no import of its module from the live entry points in current source, so no production effect. |
| EXP-032 | PROVEN_NOT_INTEGRATED | KEEP AS RESEARCH | Result stands as recorded (AVX2 MB batch pooled 1.409x [1.340, 1.480] verified; SHA-NI H-01 streams-4 batch pooled 2.861x [2.671, 3.089] verified; production); no import of its module from the live entry points in current source, so no production effect. |
| EXP-033 | PROVEN_NOT_INTEGRATED | KEEP AS RESEARCH | Result stands as recorded (E-graph equality saturation found no cheaper graph for the two-round round function (soundness 380,520 enode evaluations, 0 mismat); no import of its module from the live entry points in current source, so no production effect. |
| EXP-034 | INTEGRATED | ADD TO PRODUCTION | mining/engine.py job and template construction on the GBT path, plus three helpers (address_script_pubkey, build_coinbase, strip_witness) imported by mining/solo_server.py at two deferred import sites (lines 536, 574); the witness coinbase defect fix is in solo_server.py line 270. |
| EXP-035 | EXPERIMENTAL | KEEP DISABLED / EXPERIMENTAL | Lease-based distribution design; built form is EXP-055 (mining/coordinator.py), not wired live. Design stays experimental pending multi-machine proof. |
| EXP-036 | INTEGRATED | ADD TO PRODUCTION | mining/candidate_verify.py verify_candidate imported and called by mining/mainnet_live.py (line 349) and mining/solo_server.py before any submission; integer-only verdict, chain confirmation required. Live on both submission paths. |
| EXP-037 | INTEGRATED | ADD TO PRODUCTION | mining/mining_statistics.py and mining/probability.py imported by mining/mainnet_live.py, mining/autopilot.py and mining/engine.py; separated counters, no combined total. Live on the pool path. |
| EXP-038 | INTEGRATED | ADD TO PRODUCTION | mining/work_checkpoint.py constructed by MiningEngine only when checkpoint_path is passed; the only production caller passing one is agent/autonomous.py (line 50). GBT path only, no pool frontier (flag F-6). |
| EXP-039 | INTEGRATED | ADD TO PRODUCTION | gpu/engine.py dispatch tiers (cuda, v512dual, v512, shani, avx2, C, hashlib) with CPUID probes and hashlib self-tests; the live engine construction path. Intel refusal check still host-gated (section 7). |
| EXP-040 | PROVEN_NOT_INTEGRATED | KEEP AS RESEARCH | Result stands as recorded (Harness times the unmodified MiningEngine.mine_cycle against regtest Core: 63 timed runs, 3 sessions per scenario, 0 failures, eve); no import of its module from the live entry points in current source, so no production effect. |
| EXP-041 | REJECTED | DO NOT ADD | Negative finding preserved with its evidence; production path unchanged by it. Established null. Only the explicit VPTERNLOGD intrinsic forms reach 28 ops (tmaj, tfull); source forms and flag variants stay at 29 (rejected as rout |
| EXP-042 | REJECTED | DO NOT ADD | Negative finding preserved with its evidence; production path unchanged by it. Refuted at precisely stated bounds: decomposition synthesis UNSAT at iteration 0 for both cones (a-cone Sigma0 through Maj, 540.3 s; e-cone Sigma1 thr |
| EXP-043 | PROVEN_NOT_INTEGRATED | KEEP AS RESEARCH | Result stands as recorded (In-process medians: heartbeat 220 ns; registration 0.73 us; lease grant 3.1 to 4.7 us; candidate submit 0.77 us; journalled submit); no import of its module from the live entry points in current source, so no production effect. |
| EXP-030-PHASE-A | PROVEN_NOT_INTEGRATED | KEEP AS RESEARCH | Result stands as recorded (Complete: REPOSITORY_AUDIT.md (663 lines, 53 findings) and REFERENCE_TO_NOVA_MATRIX.md (34 rows M01 to M34) at exact upstream comm); no import of its module from the live entry points in current source, so no production effect. |
| EXP-030-PHASE-B | PROVEN_NOT_INTEGRATED | KEEP AS RESEARCH | Result stands as recorded (Complete: of 20 components, EXISTS 2, PARTIAL 15, MISSING 3 (Work Lease Manager, Distributed Agent Coordinator, Candidate Queue); ); no import of its module from the live entry points in current source, so no production effect. |
| EXP-030-PHASE-C | PROVEN_NOT_INTEGRATED | KEEP AS RESEARCH | Result stands as recorded (See EXP-031: about 2 effective CPUs delivered by a 4-vCPU guest); no import of its module from the live entry points in current source, so no production effect. |
| EXP-030-PHASE-D | PROVEN_NOT_INTEGRATED | KEEP AS RESEARCH | Result stands as recorded (See EXP-032: AVX2 and SHA-NI tiers verified; flags closed negative on the search path); no import of its module from the live entry points in current source, so no production effect. |
| EXP-030-PHASE-E | INTEGRATED | ADD TO PRODUCTION | Phase record for EXP-034; same evidence and scope as EXP-034. |
| EXP-030-PHASE-F | INTEGRATED | ADD TO PRODUCTION | Phase record for EXP-036; same evidence and scope as EXP-036. |
| EXP-030-PHASE-G | EXPERIMENTAL | KEEP DISABLED / EXPERIMENTAL | Phase record for EXP-035; same evidence and state. |
| EXP-030-PHASE-H | PROVEN_NOT_INTEGRATED | KEEP AS RESEARCH | Result stands as recorded (See EXP-033: restructuring space closed at stated bounds; E2 left open and later closed by EXP-042); no import of its module from the live entry points in current source, so no production effect. |
| PHASE001-H-1 | INTEGRATED | ADD TO PRODUCTION | Chunk-1 midstate computed once per template inside the C kernels and mining/engine.py template preparation; same mechanism as R-01. |
| PHASE001-H-2 | PROVEN_NOT_INTEGRATED | KEEP AS RESEARCH | Result stands as recorded (Statistical observation, closed: the reversals are an artifact of the 0.1.3 API shape, explained by the EXP-027 C3 boundary princi); no import of its module from the live entry points in current source, so no production effect. |
| PHASE001-H-3 | PROVEN_NOT_INTEGRATED | KEEP AS RESEARCH | Result stands as recorded (Proven identity, closed; its measurable form was not significant (EXP-018); distinct from the rotated-domain form refuted by EXP-0); no import of its module from the live entry points in current source, so no production effect. |
| PHASE001-H-4 | PROVEN_NOT_INTEGRATED | KEEP AS RESEARCH | Result stands as recorded (Proven identity, closed; per-engine content decided by EXP-027 C4 and EXP-032); no import of its module from the live entry points in current source, so no production effect. |
| PHASE001-H-5 | INTEGRATED | ADD TO PRODUCTION | Padding precomputation for fixed-length header blocks in mining/engine.py and the kernel batch setup on the GBT path. |
| PHASE001-H-6 | UNDER_INVESTIGATION | KEEP AS RESEARCH | Investigation open; no production module invoked by a live path; conclusion not yet supported by the recorded evidence. |
| PHASE001-H-7 | REJECTED | DO NOT ADD | Negative finding preserved with its evidence; production path unchanged by it. Closed, refuted by EXP-014 |
| PHASE001-H-8 | REJECTED | DO NOT ADD | Negative finding preserved with its evidence; production path unchanged by it. Closed by EXP-041 as an established null: the 28-op intrinsic forms are not significantly faster on this VM; not integrated |
| PHASE001-H-9 | PROVEN_NOT_INTEGRATED | KEEP AS RESEARCH | Result stands as recorded (Verified improvement at pooled 1.398x [1.242, 1.578] (EXP-024b); certified single-batch fallback form; not integrated, superseded ); no import of its module from the live entry points in current source, so no production effect. |
| R-01 | INTEGRATED | ADD TO PRODUCTION | Midstate reuse embodied in the production kernels (bal_miner.c lineage and the AVX-512 kernels) and mining/engine.py; no separate module, the mechanism itself is the production behaviour. |
| R-02 | INTEGRATED | ADD TO PRODUCTION | Nonce-independent chunk-2 prefix (rounds 0 to 2) precomputed per template in the kernel batch setup and MiningEngine preparation; embodied mechanism, no separate module. |
| R-03 | INTEGRATED | ADD TO PRODUCTION | Message schedule pre-extension for nonce-independent words in the kernel batch setup; embodied mechanism, no separate module. |
| R-04 | INTEGRATED | ADD TO PRODUCTION | Multi-way interleaving is the production kernel geometry itself: 16-way v512 and v512dual, 8-way AVX2, 4-stream SHA-NI in gpu/engine.py tiers. |
| R-05 | INTEGRATED | ADD TO PRODUCTION | Cheap screen with exact authority: kernel flagged batches screen in-mask, and every flagged hit is re-verified exactly (gpu/engine.py _check_pairs, then candidate_verify on submission paths). |
| R-06 | INTEGRATED | ADD TO PRODUCTION | ComputeEngine search returns candidate (nonce, digest) pairs only; bulk digests are never returned to callers on the production search entries. |
| R-07 | INTEGRATED | ADD TO PRODUCTION | gpu/engine.py runtime CPUID probing with per-tier backends behind the single ComputeEngine scan interface; live at every engine construction. |
| R-08 | INTEGRATED | ADD TO PRODUCTION | GBT longpoll with restart semantics in mining/engine.py (wait_template) and mining/prefetch-adjacent refresh; GBT and agent path scope, not the stratum pool path (flag F-6). |
| R-09 | PROVEN_NOT_INTEGRATED | KEEP AS RESEARCH | Result stands as recorded (Already covered and strengthened: EXP-029 allocator proofs, EXP-035 leases, EXP-038 crash-honest frontiers; the production coordin); no import of its module from the live entry points in current source, so no production effect. |
| R-10 | INTEGRATED | ADD TO PRODUCTION | Immutable template and job records in mining/engine.py TemplateCache (identity recomputed from scratch on every serve); GBT path scope (flag F-6). |
| R-11 | PROVEN_NOT_INTEGRATED | KEEP AS RESEARCH | Result stands as recorded (Already covered as design: EXP-035 work distribution (slot shifted left 25, 25-bit counter); production coordinator not built); no import of its module from the live entry points in current source, so no production effect. |
| R-12 | INTEGRATED | KEEP DISABLED / EXPERIMENTAL | VarDiffController in mining/solo_server.py, constructed by mining/solo_mainnet.py only when the vardiff section is enabled (default False); solo path is not live in pool mode (flag F-4). |
| R-13 | INTEGRATED | ADD TO PRODUCTION | Principle live via EXP-036 verify_candidate on both submission paths; the coordinator module the wording implies is not imported live (flag F-7). Coordinator itself decided under EXP-055. |
| R-14 | PROVEN_NOT_INTEGRATED | KEEP AS RESEARCH | Result stands as recorded (Already covered: EXP-035 duplicate detection (892 injected duplicates all detected in its campaign) and EXP-037 accounting separat); no import of its module from the live entry points in current source, so no production effect. |
| R-15 | PROVEN_NOT_INTEGRATED | KEEP AS RESEARCH | Result stands as recorded (Already covered as design and accounting: EXP-034 and EXP-035 combined space; EXP-038 frontier keys include the extranonce space. ); no import of its module from the live entry points in current source, so no production effect. |
| R-16 | INTEGRATED | ADD TO PRODUCTION | Stale-work handling live: mining/stratum_client.py rejects stale template echoes (lines 296 to 310) and autopilot kills a miner on stale evidence (incident 1002). |
| R-17 | INTEGRATED | ADD TO PRODUCTION | Non-clean stratum job updates are staged by mining/stratum_client.py (clean_jobs flag parsed at line 290) and taken up at the search boundary in mainnet_live.py rather than tearing the running span. |
| R-18 | INTEGRATED | ADD TO PRODUCTION | Per-worker separated counters in mining/mining_statistics.py with WindowedRate as the rate source; imported by the live miner and autopilot. |
| R-19 | INTEGRATED | ADD TO PRODUCTION | Every gpu/engine.py tier is gated by a CPUID probe plus a hashlib digest self-test at selection; failure degrades loudly to the next tier with the reason recorded. |
| R-20 | INTEGRATED | ADD TO PRODUCTION | mining/autopilot.py supervises and never mines; mining/mainnet_live.py mines and never supervises itself. Live separation, incident-coded (R-30). |
| R-21 | DEFERRED | DEFER | Registered proposal, no execution recorded under this id; outside the immediate CPU-first objective or gated on an external dependency. |
| R-22 | PROVEN_NOT_INTEGRATED | KEEP AS RESEARCH | Result stands as recorded (Already covered as the software analogue: EXP-003 multi-stream, EXP-011 and EXP-026 interleaved multi-buffer; the hardware mechani); no import of its module from the live entry points in current source, so no production effect. |
| R-23 | UNDER_INVESTIGATION | KEEP DISABLED / EXPERIMENTAL | Register row for EXP-052; same seam and same state (flag F-3). |
| R-24 | DEFERRED | DEFER | Registered proposal, no execution recorded under this id; outside the immediate CPU-first objective or gated on an external dependency. |
| R-25 | DEFERRED | DEFER | Registered proposal, no execution recorded under this id; outside the immediate CPU-first objective or gated on an external dependency. |
| R-26 | INTEGRATED | KEEP DISABLED / EXPERIMENTAL | EndpointHealthPolicy wired in mainnet_live.py and stratum_client.py but constructed only when enabled; shipped and live config both default off, policy is None at runtime (flag F-1). |
| R-27 | PROVEN_NOT_INTEGRATED | KEEP DISABLED / EXPERIMENTAL | Register row for EXP-057; same module and same state. |
| R-28 | DEFERRED | DEFER | Registered proposal, no execution recorded under this id; outside the immediate CPU-first objective or gated on an external dependency. |
| R-29 | DEFERRED | DEFER | Registered proposal, no execution recorded under this id; outside the immediate CPU-first objective or gated on an external dependency. |
| R-30 | INTEGRATED | ADD TO PRODUCTION | mining/incident_codes.py and incident_registry.json (20 codes); emission live in mining/autopilot.py (1001 to 1003, 2001 to 2004, 3001 to 3004) and mining/mining_statistics.py (4001 to 4003); heartbeat publishes incident_counts, verified live at the baseline. |
| R-31 | DEFERRED | DEFER | Registered proposal, no execution recorded under this id; outside the immediate CPU-first objective or gated on an external dependency. |
| R-32 | EXPERIMENTAL | KEEP DISABLED / EXPERIMENTAL | Register row for EXP-058; same module and same state. |
| R-33 | PROVEN_NOT_INTEGRATED | KEEP DISABLED / EXPERIMENTAL | Register row for EXP-051; same code and same opt-in state (flag F-2). |
| R-34 | DEFERRED | DEFER | Registered proposal, no execution recorded under this id; outside the immediate CPU-first objective or gated on an external dependency. |
| R-35 | PROVEN_NOT_INTEGRATED | KEEP AS RESEARCH | Result stands as recorded (New; not started. Partial analogue: the Master Build scheduler bake-off measures through the production search path but is an agen); no import of its module from the live entry points in current source, so no production effect. |
| EXP-047 | PROVEN_NOT_INTEGRATED | KEEP AS RESEARCH | Backend agreement verification at fuzzing scale (46,150,110 comparisons); a verification result over the production backends, not a code addition. Search semantics question stays an owner decision (section 7). |
| EXP-048 | PROVEN_NOT_INTEGRATED | KEEP AS RESEARCH | Harness-side overhead measurement (solo 97.0 ms empty and 152.4 ms loaded medians; pool 55.9 and 210.7 ms against a local stub); not real public-pool.io end to end, no production code resulted. |
| EXP-049 | PROVEN_NOT_INTEGRATED | KEEP AS RESEARCH | mining/bench_mode.py is imported only by tests/test_exp049_bench_mode.py and run standalone; no production entry point imports it. Offline tooling, agreement with the live path verified (pooled ratio 1.195). |
| EXP-050 | PROVEN_NOT_INTEGRATED | KEEP DISABLED / EXPERIMENTAL | The experiment behind R-26; same code, same default-off state (flag F-1). Ledger pair inconsistency with R-26 noted in section 6. |
| EXP-051 | PROVEN_NOT_INTEGRATED | KEEP DISABLED / EXPERIMENTAL | PrefetchFeed and PrefetchQueue in mining/prefetch.py, hooked into MiningEngine behind use_prefetch (default False); no production caller enables it (flag F-2). |
| EXP-053 | REJECTED | DO NOT ADD | ESTABLISHED NEGATIVE at predeclared resolution (pooled log ratio -0.0017); production walker unchanged. Bench driver defect D-1 must be fixed before any reuse (section 7). |
| EXP-054 | REJECTED | DO NOT ADD | Flat granularity curve confirmed, production G = 1 stands; displacement ESTABLISHED NEGATIVE (G=2 +0.0016, G=4 -0.0521, G=8 -0.1505). Production walker unchanged. |
| EXP-055 | PROVEN_NOT_INTEGRATED | KEEP DISABLED / EXPERIMENTAL | mining/coordinator.py (CoordinatorCore, CoordinatorServer) is imported by nothing live; protocol-level proof only, one VM, loopback (section 5.3). Fleet activation is owner-gated. |
| EXP-057 | PROVEN_NOT_INTEGRATED | KEEP DISABLED / EXPERIMENTAL | mining/aggregation.py AggregationTier is imported by nothing live; loopback proof only, D-1 and D-2 fixed in source (section 5.5). Deployment is owner-gated. |
| EXP-058 | EXPERIMENTAL | KEEP DISABLED / EXPERIMENTAL | mining/pid_control.py AdaptiveWorkController is imported by nothing live and ships disabled; step_up scale-up leg is an established negative for the interval-only signal (section 5.6). |
| EXP-056 | INCONCLUSIVE | KEEP AS RESEARCH | Z3 CEGIS campaign under research/sha256d/exp056; solver budget exhausted, no SAT construction, 7 of 56 profiles per cone closed UNSAT. A budget result, not an impossibility proof (section 5.4). |
| EXP-052 | UNDER_INVESTIGATION | KEEP DISABLED / EXPERIMENTAL | mining/bakeoff_dispatch.py resolver seam in mainnet_live.py (lines 253 to 265) behind the bakeoff section (default off); no cache file planted; one AMD campaign, STATIC by dominance (section 5.1). |

Reading rule for the table: ADD TO PRODUCTION asserts
invocation in current source on the path named in the basis;
it is not a new enablement. KEEP DISABLED / EXPERIMENTAL
asserts the code or design exists but is either behind a
default-off switch, on a non-live path, or missing a gate
(multi-machine proof, owner approval, or a new experiment).
DO NOT ADD preserves a rejected result and its evidence;
nothing is deleted. DEFER keeps a registered proposal with
no execution under its id.

## 5. A4 findings reconciliation

Each item is closed against current source, or carried as an
open item with its owner or next step named.

### 5.1 EXP-052 adaptive backend dispatch (register R-23): CLOSED as verified, enablement OPEN (owner)

Source: mining/bakeoff_dispatch.py (sha256
fc211512d3097781413e2bfb7b11210664eb347335573c1c6f59ba7656993c10
at the baseline).

- Resolver robustness, re-read line by line for this stage:
  resolve_requested (line 522) returns "auto" on every doubt
  path: non-mapping config (guarded dict conversion), switch
  disabled, non-numeric or non-positive or non-finite max_age_s
  and margin (each coerced under try and checked with
  math.isfinite), and any read_cache failure. It never measures
  and never constructs an engine.
- Wrong-type handling (audit D-1 fix, present): validate_cache
  coerces now under try (TypeError, ValueError) and returns
  doubt; read_cache rejects a non-path cache_path by type
  before opening; the fingerprint argument is converted with
  dict(fingerprint) under try inside validate_cache, so a
  wrong-typed fingerprint yields doubt, not an exception.
  One residual gap is recorded as defect DEF-9.2-1 in
  section 7 (the host_fingerprint() call at line 566 to 567
  sits outside a guard, and the caller in mainnet_live.py has
  no wrapper); as written today host_fingerprint cannot raise
  in practice, so the never-raises contract holds, but the
  seam is not defended at both ends.
- Cache winner cross-check (audit D-2 fix, present):
  validate_cache rejects a winner with no tier row, a winner
  whose tier row is not eligible, and a winner whose tier row
  resolved_backend differs from DENOTED_BACKEND[winner]. It
  also enforces the exact cache key set, schema and protocol
  identity, fingerprint equality, timestamp sanity (future
  beyond 300 s rejected, staleness against max_age_s), the
  predeclared margin floor, finite tier rates, and a known
  static_pick and winner.
- Static fallback: "auto" is the gpu/engine.py static tier
  order, exactly current behaviour. With the switch off the
  cache is never read (mainnet_live.py lines 253 to 265).
- Host fingerprinting: host_fingerprint (line 105) keys on CPU
  model, a hash of the sorted instruction flags, and logical
  CPU count from /proc/cpuinfo; any mismatch voids the cache.
- Cross-host evidence: none. The single campaign (AMD EPYC
  9D25, flags hash 51d3e983ddf6ac93) resolved STATIC by
  dominance: pooled adjusted log ratios against v512dual from
  -0.6264 (v512) to -3.9732 (hashlib), 450 pairs per
  comparison, zero voided. The disclosed qualification stands:
  the control pooled CI [-0.1101, +0.1452] is wider than plus
  or minus log(1.05), so no challenger could have been
  certified at the 5 percent margin in that campaign.
- Live enablement: NOT enabled (flag F-3). Remaining work is
  host-gated, not code-gated: an Intel Xeon Platinum 8321HC
  rotation, a second AMD rotation, a measured-winner Gate 5
  (both genuine campaigns produced STATIC; the winner path is
  verified only through synthetic caches and decide() units),
  and any future 5 percent certification campaign needs its
  own predeclaration with a pair count sized from this
  control. Enablement itself is an owner decision.

### 5.2 EXP-053 and EXP-054: CLOSED, negatives preserved

No reopening. EXP-053 (prefix sharing in the dual-batch
walker) is an ESTABLISHED NEGATIVE at its predeclared
resolution (pooled -0.0017), class DO NOT ADD. EXP-054
(interleave granularity) confirmed the flat curve; production
G = 1 stands and the displacement hypothesis is an ESTABLISHED
NEGATIVE, class DO NOT ADD. Neither was re-measured in this
stage (no benchmarks run). Reopening either requires a new
mathematical hypothesis stated in advance, per the Stage 9
brief; none was presented. The EXP-053 bench driver defect
D-1 is carried in section 7 as a fix-before-reuse item.

### 5.3 EXP-055 coordinator: CLOSED as source-verified, multi-machine OPEN

Source: mining/coordinator.py (1,224 lines at the baseline),
re-read for this stage.

- Lease ownership: CoordinatorCore issues leases with unique
  sequential ids, a per-lease fencing token and an epoch.
  _check_report (line 497) rejects a wrong token or stale
  epoch as STALE and a non-holder as NOT_HOLDER.
- Fencing: completed lease ids are kept in _completed_ids and
  reclaimed or superseded ids in _dead_ids (lines 264 to 267);
  lease_info (line 484) answers for live and tombstoned ids;
  duplicate delivery against a completed id and reports
  against dead ids are counted separately, never silently
  accepted.
- Recovery: CoordinatorServer journals operations with fsync
  per entry and writes atomic snapshots; on restart it loads
  the snapshot, replays the journal tail, recovers candidate
  state from the candidate journal, then apply_restart_rule
  (line 712) bumps the epoch and reclaims every outstanding
  lease, so no lease survives a coordinator restart and
  workers must re-register.
- Duplicate prevention: slices and chunks are partitioned
  under the invariant unique + pending + leased == declared,
  asserted by assert_partition_invariant (line 773);
  CandidateQueue deduplicates by full candidate identity and
  journals before acknowledging.
- Real multi-machine limitations, stated plainly: every
  measurement behind this module is one VM, in-process or
  loopback. Multi-machine coordination, real network latency,
  cross-machine scaling, clock skew across machines, partial
  network failure, and live deployment beside the production
  miner are all UNVERIFIED. Simulated or loopback workers are
  not evidence of distributed scaling. The module is imported
  by nothing live. Class: KEEP DISABLED / EXPERIMENTAL. Fleet
  activation remains an owner decision and is the next step
  gate, together with a genuine two-machine test.

### 5.4 EXP-056 symbolic synthesis: CLOSED, INCONCLUSIVE retained

The classification stays INCONCLUSIVE. The campaign exhausted
its predeclared budget (6,519.3 s of 6,600 s): Stage A
full-space queries unknown at 1,500 s for both cones, Stage B
closed 7 of 56 op-kind profiles per cone as UNSAT and
exhausted 12 per cone, no SAT construction found. A solver
timeout is a budget result, not a proof of impossibility, and
nothing in this stage upgrades it. Still open per cone: 5
profiles unknown at 240 s, 44 profiles never queried, the
full-space question above 1,500 s per query, and Stage C
(encoding B), never run. If the campaign resumes, the audit
D-1 correction is owed first: re-run the control against the
corrected predeclared plant (the shipped control plant had
selectors (6, 5) and ADD(i2, i1) where the predeclaration
specified (7, 5) and ADD(i3, i1), so the control proved
SAT-capability against an easier target; its equivalence for
that easier target is verified). Drivers resume from
checkpoint at profile 12; no completed query is to be
repeated. H-033-02 stays UNPROVEN BREAKTHROUGH, narrowed.
Class: KEEP AS RESEARCH.

### 5.5 EXP-057 stratum aggregation: CLOSED as source re-audited, deployment OPEN (owner)

Source: mining/aggregation.py (718 lines at the baseline),
re-read line by line for this stage against its audit.

- Authentication and session lifecycle: a worker exists only
  if the operator enrolled it; enroll_worker (line 123) stores
  a token hash, never the token. open_session (line 174)
  raises IdentityError on a foreign fleet id, an unenrolled
  worker, or a token hash mismatch. Each session binds exactly
  one worker to exactly one tier-assigned extranonce1; the
  worker never chooses it, so a share cannot be credited to
  another worker's slot.
- D-1 (session orphaning) fix, present: in _AggHandler._run,
  a re-authorize on one connection captures the previous
  session id, binds the new session, then closes the previous
  one, and connection teardown closes the connection's final
  session. No session is left bound to a dead connection.
- Candidate persistence: snapshot and restore persist workers,
  counters, the duplicate seen-set, pending candidates and the
  upstream submission count; on restore the session table is
  deliberately emptied (sessions never survive a tier restart;
  workers re-authenticate).
- Retry safety and D-2 (lossy candidate pop) fix, present:
  operator_submit_pending (line 421) is the only submission
  path in the module. It requires the operator token, refuses
  when no submitter is configured, re-verifies the stored
  header through candidate_verify.verify_candidate before
  submitting, and removes the candidate from the queue only
  after the submitter returns, deleting by identity. On any
  failure the candidate stays queued.
- Submission authority: the tier never submits on its own
  authority. Workers cannot submit upstream at all; the sole
  path is the explicit operator call through the configured
  submitter callable.
- Accounting: per-worker and global counters reconcile through
  assert_accounting_identity against the EXP-037 statistics;
  duplicates are keyed on (worker, job, extranonce2, ntime,
  nonce) and counted, not silently dropped.
- Limitations: loopback only; no real upstream pool, no
  multi-machine operation, no live deployment. Imported by
  nothing live. Class: KEEP DISABLED / EXPERIMENTAL.
  Deployment remains an owner decision.

### 5.6 EXP-058 PID controller: CLOSED with the missed requirement preserved; observability proposal below (not implemented)

Source: mining/pid_control.py (529 lines at the baseline).
The missed scale-up requirement is preserved exactly: the
controller's only signal is the span completion interval. The
inner span loop (velocity form) drives log2(span); the outer
worker loop (absolute form) reads span saturation. When
intervals are already at target there is no error signal that
distinguishes "correctly loaded" from "capacity to spare", so
an interval-only cascade structurally cannot see spare
capacity, and the step_up scale-up leg is an ESTABLISHED
NEGATIVE for this signal (register R-32). make_work_controller
(line 506) builds the interval-only cascade and nothing else.
The module ships disabled, is imported by nothing live, and
Gate 5 actuated a side workload only; any hash-rate effect is
UNVERIFIED by design. Class: KEEP DISABLED / EXPERIMENTAL.

Proposal (design only, NOT implemented in this stage): a
bounded canary probe with a direct spare-capacity signal.

1. Signal: per-worker unique hash rate from the EXP-037
   WindowedRate counters, plus effective CPU capacity from
   the EXP-031 host characterisation as a feedforward ceiling.
   Neither requires new telemetry plumbing; both already exist
   in the tree.
2. Probe: when the interval error has stayed inside the
   deadband for M consecutive control intervals (suggested
   M = 20, to be fixed by predeclaration), the controller runs
   exactly one bounded probe: one extra worker for exactly one
   span at the current span size. The probe is the only way
   the controller may propose a scale-up.
3. Decision: the scale-up is adopted only if, over the probe
   span, the completion interval degrades by less than a
   predeclared bound (suggested 5 percent) AND total unique
   hashes completed rises by at least the probe worker's
   expected share minus the same bound. Otherwise the probe
   worker is withdrawn and the retry backoff doubles
   (exponential, capped), so probing cannot oscillate.
4. Safety: a probe never runs while a template is stale, a
   worker is unhealthy, or the host is above a predeclared
   load ceiling; candidate verification and accounting are
   never throttled by the controller.
5. Evidence bar: the mechanism gets its own experiment id and
   an EXP-017-shaped predeclaration (paired sessions,
   production search path, adjusted CI) before any promotion
   discussion. Until then EXP-058 stays exactly as it is.

### 5.7 NOVA-ER-0006 incident registry (register R-30): CLOSED at current HEAD, three items OPEN

- Registry: mining/incident_registry.json holds exactly 20
  append-only codes in 5 classes (1001 to 1003, 2001 to 2005,
  3001 to 3004, 4001 to 4003, 5001 to 5005), registry id
  bal-incident-codes/1. mining/incident_codes.py validates
  entries and enforces the append-only rule
  (check_append_only); the rule is pinned by
  tests/test_incident_codes.py.
- Emission verified in current source: mining/autopilot.py
  emits 1001, 1002, 1003, 2001, 2002, 2003, 2004 and 3001 to
  3004 through log_incident, with the heartbeat publishing
  incident_counts; mining/mining_statistics.py keys 4001 to
  4003 in record() and exposes record_incident and
  incident_snapshot, with snapshot() deliberately unchanged.
  Emission is defensive: the autopilot imports incident_codes
  under a guard and runs uncoded if the registry is missing.
- Audit scope reconciled: the independent audit
  (research/EXTREME_RESEARCH/NOVA_ER_0006_AUDIT.md, PASS WITH
  NOTES, 0 defects) was scoped to the change set against
  remote HEAD 6528aae0, before the push at 11277e6f. The three
  audited files are byte-identical at the current HEAD
  (sha256 table in REPOSITORY_BASELINE.md), so the verdict
  carries to this HEAD for those files.
- Live proof: heartbeats after the integration carry
  incident_counts (for example {1003: 1, 2001: 1} on the
  running instance at the Stage 9.1 baseline). The item that
  was UNVERIFIED at build time is verified.
- Still UNVERIFIED, carried open: (a) keeper-side mapping for
  2005 SUPERVISOR_LOST: the keeper is not repo code, so no
  repo change can close this; next step is a keeper-side
  mapping note owned by whoever maintains the keeper.
  (b) The 3001 to 3004 self-update path end to end: the code
  sites exist in maybe_update, but the path has never fired on
  this VM (the checkout has no .git, so it is inert here);
  next step is a forced update drill on an isolated checkout
  with a .git remote, in Stage 9.3 or later. (c) Emission
  wiring at the 5xxx producers: codes 5001, 5002, 5004 and
  5005 are assigned and replay-mapped over 165 real log lines
  with zero unmapped, but the producers (miner evidence
  events) are not wired to emit codes by this change, and 5003
  has no instance in the operational evidence corpus; next
  step is a small, separately audited wiring change if the
  owner wants coded 5xxx records.
- Class: ADD TO PRODUCTION (already live for the wired codes).

### 5.8 Stage 8: CLOSED as a historical result, not a current-HEAD claim

The Stage 8 audit (research/EXTREME_RESEARCH/STAGE8_AUDIT.md,
PASS WITH NOTES, 0 defects) verified four regtest blocks at
heights 1787 to 1790 on the best chain and an isolated agent
instance's evidence log, against remote HEAD
78a061e5385e86b953801af51b49bf5d57d72243, with Stage 8 itself
local and unpushed at audit time. That verdict is about that
commit and that isolated instance. The current HEAD is
883cf281; the Stage 8 code has since been pushed and
test-stage8 is one of the 51 test-all prerequisites, but no
Stage 8 demonstration was re-run in Stage 9.1 or 9.2, and
nothing here upgrades the historical verdict into a
current-HEAD claim. The known Stage 8 run-1 finding (the
production GBT path lacks the 10 s status publisher the demo
miner needed) remains open and is carried in section 7.
Stage 9.5 owns any fresh autonomous regtest demonstration.

## 6. Registry staleness repair proposal (D-01 to D-04, plus D-06 and the R-26 pair)

Proposal only. The authoritative registry
(research/EXTREME_RESEARCH/EXPERIMENT_REGISTRY.json, generated
2026-11-15 against HEAD 18ff4eb0 plus a local delta) was NOT
edited in this stage. The parent should apply these as one
separate, small, tested change (regenerate the derived
registry with agent.intelligence.integrations.write_registry,
re-run test-agent-intelligence, and verify the derived set
still matches the authoritative INTEGRATED set).

Exact status updates proposed:

| Row | Current registry status | Proposed status | Basis |
| --- | --- | --- | --- |
| R-23 | NEW | UNDER_INVESTIGATION | Executed as EXP-052; partial completion on one host, rotations outstanding (D-01). |
| R-27 | NEW | PROVEN | Executed as EXP-057; protocol-level proof, not integrated (D-01). |
| R-32 | NEW | EXPERIMENTAL | Executed as EXP-058; ships disabled, scale-up leg negative (D-01). |
| R-33 | NEW | PROVEN | Executed as EXP-051; opt-in hook integrated in MiningEngine but the row's own result is the measured prefetch behaviour (D-01). If the parent prefers to mark code presence, INTEGRATED with the enablement annotation below is the alternative; PROVEN is the conservative choice. |
| R-35 | NEW | PROVEN | Executed as EXP-049; bench mode built and verified, not on a production path (D-01). |

D-02 (registry basis is old): in the same change, update the
registry framing text and basis HEAD from 18ff4eb0 to the HEAD
current at the time of the repair, and rewrite R-23's open
question, which was written before EXP-052 ran, to point at
the EXP-052 report and its outstanding rotations.

D-03 (EXP-030 self-note): replace the reservation-block
wording for EXP-030 to EXP-038 (still written as RESERVED in
the EXP-030 entry) with the executed status, referencing the
EXP-030-PHASE-A to H records, which already carry the real
statuses.

D-04 (Phase 001 table): correct the Phase 001 status table so
H-8 reads REJECTED (the EXP-041 result; the registry already
says REJECTED and the ledger follows it), and update H-9's
wording to reference EXP-024b (PROVEN) and its supersession
by EXP-026 as the integration candidate.

D-06 (R-30 stale note): update the R-30 entry's sentence that
live records carry codes only after the next natural autopilot
restart; that restart has happened and heartbeats carry
incident_counts now.

Enablement annotation (new, proposed): add an optional
enablement field to INTEGRATED rows with three values,
live, default-off, and path-scoped, and set it in the same
repair: R-26 default-off; R-12 default-off and path-scoped
(solo); EXP-022 path-scoped (batch); EXP-025, EXP-034,
EXP-038, PHASE001-H-1, PHASE001-H-5, R-08, R-10 path-scoped
(GBT and agent path). This is the smallest change that stops
the D-07 misreading from recurring, and it also harmonises
the EXP-050 (PROVEN) and R-26 (INTEGRATED) pair: the pair is
then one experiment record plus one register record over the
same code, with the register row carrying the enablement
state.

## 7. Defects found during tracing

No production code was changed in this stage. Each item lists
file, line evidence, impact and a proposed small fix.

- DEF-9.2-1 (minor, robustness, bakeoff seam):
  mining/bakeoff_dispatch.py, resolve_requested lines 566 to
  567: the host_fingerprint() call sits outside any guard, and
  mining/mainnet_live.py lines 253 to 265 call
  resolve_requested with no try wrapper. Impact: the module's
  documented contract is "the resolver never raises"; today
  host_fingerprint cannot raise in practice (its only file
  read is OSError-guarded), so the contract holds, but any
  future fingerprint change that can raise would propagate
  into miner startup once the switch is enabled. Proposed fix:
  wrap the fingerprint resolution in resolve_requested in a
  try that returns the doubt verdict, and add the regression
  case to tests/test_exp052_bakeoff_dispatch.py. Apply before
  any enablement, not now.
- DEF-9.2-2 (minor, coupling, GBT engine):
  mining/engine.py line 26 imports PrefetchFeed and
  PrefetchQueue unconditionally at module top level, although
  the feature is opt-in (use_prefetch default False) and the
  objects are only constructed under that flag (lines 566 to
  568). Impact: a broken mining/prefetch.py would break
  MiningEngine import for every caller, including callers that
  never enable prefetch. Proposed fix: move the import inside
  the use_prefetch branch. Cosmetic today (prefetch imports
  cleanly), listed for completeness.
- DEF-9.2-3 (known, research driver, fix before reuse):
  the EXP-053 bench driver defect D-1 recorded in its report
  and carried by the closure ledger. Impact: none on
  production (the driver is research-only and the EXP-053
  verdict does not depend on the defective path), but the
  driver must not be reused until fixed. Proposed fix: fix in
  the exp053 driver under its own change if the driver is ever
  reused; no action while EXP-053 stays closed.
- DEF-9.2-4 (open finding, GBT path): the Stage 8 run-1
  finding stands: the production GBT path in mining/engine.py
  lacks the 10 s status publisher the Stage 8 demo miner
  needed. Impact: observability gap on the GBT path only; the
  live pool path has its own evidence and heartbeat. Proposed
  fix: Stage 9.4 or 9.5 scope, a small publisher in
  MiningEngine mirroring the demo's, with a test.
- DEF-9.2-5 (measurement integrity, not code): D-05 from the
  closure report: EXP-032 and EXP-039 measured the
  byte-identical AVX2 kernel at 1.409x and 1.252x with
  non-overlapping confidence intervals. Impact: none on the
  live pick (v512dual dominates on this host class), but the
  conflict is unresolved and any future AVX2-host decision
  would rest on it. Proposed next step: one paired re-measure
  under the EXP-017 protocol on an AVX2 host, owned by
  Stage 9.7.
- Not defects, recorded to prevent misreading: the
  MiningController select_backend and refresh_job operations
  in agent/intelligence/controller.py (lines 485 and 535)
  return honest "unsupported" refusals, because backend
  selection lives in mainnet_live.py construction and job
  supply is push-driven inside the miner. That is correct
  behaviour, not a gap to patch over. The autopilot
  self-update path (3001 to 3004) being inert on a checkout
  with no .git is likewise by design.

## 8. Open items carried forward

1. EXP-052: Intel Xeon Platinum 8321HC rotation and second
   AMD rotation (host-gated); measured-winner Gate 5; any
   5 percent certification campaign needs its own
   predeclaration. Enablement: owner decision.
2. EXP-050 and R-26: live enablement needs a real second
   endpoint and an owner decision.
3. EXP-051 and R-33: live enablement on the GBT path is an
   owner decision; mainnet difficulty effect UNVERIFIED.
4. EXP-055: genuine multi-machine test (independent machines,
   real latency, disconnections, restarts, clock skew) before
   any fleet claim. Fleet activation: owner decision.
5. EXP-057: real upstream and multi-machine test before any
   deployment. Deployment: owner decision.
6. EXP-058: the canary-probe observability design in
   section 5.6 needs its own predeclaration and experiment
   before implementation is promoted.
7. EXP-056: corrected-plant control re-run owed if the
   campaign resumes; resume from checkpoint profile 12.
8. NOVA-ER-0006: keeper-side 2005 mapping (keeper is not repo
   code); 3001 to 3004 end-to-end update drill on an isolated
   checkout; 5xxx producer wiring as a separate audited change
   if wanted.
9. EXP-047: owner decision on search semantics (accept
   first-publisher-wins as documented production semantics, or
   pay for a minimum reduction in the search context).
10. EXP-039: tier refusal check on the SHA-less Intel host and
    an AVX2-only host remains host-gated (probe construction
    only so far).
11. Registry repair in section 6: parent to apply as a
    separate small tested change.
12. D-10: no CI configuration exists in the repository; the
    test record is the local Makefile suite. Stage 9.3 owns
    the current-HEAD test audit and the CI decision.
13. Success criterion unchanged and unmet: no mainnet block
    has been found; pool shares are not blocks. The 500 GH/s
    minimum objective and the 140 TH/s aspirational objective
    stand at full height.

## Corrections (2026-11-18)

Two documentation defects found by the independent audit in
research/STAGE9/STAGE9_2_AUDIT.md (verdict PASS WITH NOTES,
Defects 1 and 2) are corrected in place above. No promotion
class, count or id changed.

- Defect 1: section 1 previously named only two MiningEngine
  constructors. It now names all three (agent/autonomous.py
  line 48, mining/testnet4_attempt.py line 69 and
  mining/cpu/miner.py line 133) and states plainly that only
  the agent path is live-relevant and mining/cpu/miner.py is
  imported by nothing live. The live path conclusion is
  unchanged.
- Defect 2: section 1 and the EXP-034 row previously said
  mining/solo_server.py imports two helpers from
  mining.engine. Both now say three helpers
  (address_script_pubkey, build_coinbase, strip_witness) at
  two deferred import sites (lines 536 and 574).

## Registry repair applied (2026-11-18)

The section 6 registry staleness repair has been applied to
research/EXTREME_RESEARCH/EXPERIMENT_REGISTRY.json as one
separate, tested change, including the enablement annotation.
The annotation is encoded as a single composite string field
named enablement, joining the applicable values and scope in
this section's phrasing: R-26 "default-off"; R-12
"default-off, path-scoped (solo)"; EXP-022 "path-scoped
(batch)"; EXP-025, EXP-034, EXP-038, PHASE001-H-1,
PHASE001-H-5, R-08 and R-10 "path-scoped (GBT and agent
path)". No other record or field changed. Registry sha256
after the repair:
c333c8ef59c81a4b18ddad84674429eca7d84cd3ed27e039af8cddb07cb85f24.
The derived registry was regenerated with
agent.intelligence.integrations.write_registry and is
byte-identical to before (the generator does not carry the
enablement field); the Stage 9.1 ledger validator still reads
VALID at 109 entries and test-agent-intelligence passes
against the repaired registry.

