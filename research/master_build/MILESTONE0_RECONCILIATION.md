# Milestone 0 Reconciliation: NOVA SHA-X Master Build Mandate

Date: 2026-11-15 (inspection executed 2026-11-15 PST, files read from the
working tree at /home/hatch/workspace/bitcoin-autonomous-lab).
Baseline: remote head 3510daa47d426e7e235fe04cecce314eff8b376a (Phase 002
push). The local checkout has no .git directory, so the HEAD is taken from
the push record, not from a local git read. Method: every claim below cites
a file path and, where useful, a function name or line number, read from
the actual source during this inspection. No existing file was modified.
No benchmark was run. The live miner, autopilot and node were not touched.

Concurrency note: while this inspection ran, a separate Milestone 1 build
created agent/intelligence/audit.py, agent/intelligence/memory.py and
agent/intelligence/permissions.py (all timestamped 2026-11-16 00:22 in the
working tree). Those three files are NOT part of the 3510daa4 baseline,
are not wired into agent/autonomous.py or agent/interface.py at the time
of reading, and were not audited here. Where they matter, they are flagged
as in-flight Milestone 1 work, not as existing capability.

Targets reminder (mandate section 1.1, unchanged): 500 GH/s minimum
objective, 140 TH/s larger objective. Verified live production rate on
this VM is in the 20 MH/s class (v512dual backend, category E
observations), so the measured gap to 500 GH/s remains roughly 24,000
such systems. No mainnet block has been found; balance 0 BTC; pool shares
are not blocks.

## (a) Implementation map (mandate section 2)

| Component | Existing implementation (exact paths, key functions) | Missing capability | Proposed action |
|---|---|---|---|
| Mining engine | mining/engine.py: MiningEngine (get_template line 550, wait_template line 553, prepare_template line 541, build_candidate line 562, build_candidate_uncached line 579, mine_cycle line 661, batch_count line 646); template layer TemplateFamily line 224, PreparedTemplate line 339, TemplateCache line 434, template_identity line 313. gpu/engine.py: ComputeEngine (dispatch in __init__ lines 890 to 965; search_first line 1815, search_first_counted line 1823, batch_search line 2352, benchmark_report line 2667). Kernels in mining/cpu/: bal_avx512_dual.c (v512dual), bal_avx512_mb.c (v512), bal_avx512_flags.c (flags batch), bal_avx2_mb.c (avx2), bal_shani_streams.c plus bal_shani_core.h (shani), bal_batch.c (C), bal_fallback_probe.c and bal_avx512_probe.c (flag-free CPUID probes), build.py. mining/pow_engine.py and mining/pow.py: PoW primitives. mining/solo_server.py: SoloServer (refresh_job line 228, validate_share line 302, submit_share line 351). | No BIP320 version rolling and no ntime rolling on any path (recorded gap, EXP-034). The GBT hit path does not call the EXP-036 verifier (see section c). No agent-facing control surface: batch size, extranonce space and backend pin are constructor arguments only. | Extend: keep every production file; expose controls through the Milestone 1 typed interface rather than editing engine internals. |
| Agent | agent/autonomous.py: AutonomousMiner (127 lines, whole file read). agent/interface.py: AgentInterface (177 lines, whole file read). | Everything in mandate section 4.1: no strategic, research, planning, optimisation or learning subsystem; no permissions; no audit trail beyond a BlockStore event kind; no task registry; no typed interface. See section (b) for the exact assessment. | Extend: build the Milestone 1 foundation under agent/ (the agent/intelligence/ package is already in flight concurrently); rewire AutonomousMiner through it. Do not replace autonomous.py. |
| Scheduler | mining/autopilot.py: Autopilot (start_child line 341, run line 406, heartbeat line 356, maybe_update line 375) is a process supervisor, not a work scheduler. gpu/engine.py: tune_c_threads line 234, tune_v512_threads line 276, tune_v512dual_threads line 324 (one-shot measured thread tuning at engine construction). agent/autonomous.py: _adjust_batch (batch size only). mining/engine.py: extranonce_space constructor argument (static range assignment). Research prototypes only: research/sha256d/exp035/lease_manager.py LeaseManager, research/sha256d/exp035/candidate_queue.py CandidateQueue, research/sha256d/phase6b/benchmarks/exp029_allocator.py. | No production work scheduler or coordinator exists. No resource registry. No lease-based assignment, no adaptive worker configuration, no work stealing in production. EXP-035's own INTEGRATION_DECISIONS.md records the decision: no production integration in that phase. | Extend in Milestones 4 and 5: productionise the EXP-035 lease design behind the agent interface; do not invent a second allocator (EXP-029 and EXP-035 already cover the design space). |
| Research system | research/sha256d/experiment_registry.md (1,498 lines) and research/sha256d/extreme_optimization/EXPERIMENT_REGISTRY.md (1,994 lines): the two narrative registries. research/sha256d/extreme_optimization/HYPOTHESIS_REGISTRY.md (X-001 to X-116) and HYPOTHESIS_REGISTRY_Y.md (Y-001 to Y-108). research/sha256d/exp033/HYPOTHESIS_REGISTRY.json (H-033-01 to H-033-14, the only machine-readable registry). Experiment trees research/sha256d/exp030 to exp043 plus phase6/ and phase6b/. EXP-017 harness: research/sha256d/phase6/benchmarks/exp017_paired_bench.py and exp017_analyze.py. | Registries are prose markdown: not queryable by an agent at runtime, two files with overlapping coverage, statuses embedded in paragraphs. No persistent structured research memory in the baseline (agent/intelligence/memory.py, in flight, parses these files; it did not exist at baseline). | Extend: Milestone 1 research memory parses the existing registries (as the in-flight memory.py does); never rewrite or renumber the registries. The seed register companion to this document (RESEARCH_OPPORTUNITY_REGISTER_SEED.md) maps them onto mandate section 17 statuses. |
| Optimisation engine | The experiment programme itself: registries above, kernels under research/sha256d/exp032/src, exp039 to exp043 trees, extreme_optimization/src and phase6/src. gpu/engine.py dispatch is the integration endpoint. | No optimisation loop exists in code. Experiments are designed, run and judged by agents and the owner ad hoc against the EXP-017 protocol; there is no experiment runner, no hypothesis-to-experiment workflow object, no automatic regression or rollback hook in the tree. | Extend in Milestone 3: implement the mandate section 5 cycle as a workflow over existing pieces (EXP-017 harness as the gate, registries as memory, ComputeEngine as the integration endpoint). |
| Verification | mining/candidate_verify.py: verify_candidate line 83, classify_submit_result line 144, verify_chain_acceptance line 171, pow_limit_for_chain line 70, meets_target line 76 (no float operations in the file; hashlib plus pure-Python agreement required). gpu/engine.py carries a second, unrelated verify_candidate at line 377 (per-nonce digest check inside the compute layer) plus _check_pairs line 2279 and _rescan_all_candidates line 2310. tests/: 33 Makefile test-all targets (count verified against Makefile line 107). | The GBT path (mining/engine.py mine_cycle) never calls mining/candidate_verify.py; its acceptance is submitblock plus best-chain equality, by the code's own comment. No single verification interface fronts all three paths (GBT, pool, solo). The name collision between the two verify_candidate functions invites wiring mistakes. | Extend: Milestone 1 interface names the verifier explicitly as mining.candidate_verify.verify_candidate; a Milestone 6 decision must either wire it into the GBT hit path or record the reliance on Core's verdict as the standing design. |
| Recovery | mining/autopilot.py Autopilot.run: child restart with backoff, hung-miner kill when evidence is stale beyond the owner-set window, heartbeat every 5 s. mining/work_checkpoint.py: WorkCheckpoint (resume line 90, record line 133), GBT path only, opt-in via MiningEngine checkpoint_path. mining/stratum_client.py: reader_loop line 392 reconnects on any drop, _reset_session line 375. scripts/solo_cutover.py: fire with automatic rollback to pool mode. Autopilot.maybe_update line 375: pull, smoke test, reset on failure (inert in this checkout: no .git, version reads "unknown"). | No checkpoint or resume exists for the Stratum pool path (job state is ephemeral by protocol; a restart re-authorizes and takes the current job, losing in-flight span position, which is acceptable for pool shares but is nowhere documented as a decision). No coordinator-level recovery in production (EXP-035 proof obligations P1 to P6 are prototype-level only). No agent-visible incident record: autopilot logs are text lines in .local/miner.out and the autopilot log. | Extend in Milestone 5: connect WorkCheckpoint and the EXP-035 lease recovery semantics to the agent; record the pool-path no-checkpoint decision explicitly. Reuse solo_cutover rollback shape for integration rollback. |
| Monitoring | mining/autopilot.py: heartbeat() line 356 writes .local/heartbeat.json; EvidenceCounter line 107 (whole-log incremental census, persisted offset in .local/evidence-count.json). mining/mainnet_live.py: .local/mainnet-status.txt refreshed in the status block, Evidence JSONL via mining/stratum_client.py Evidence line 160. mining/mining_statistics.py: MiningStatistics line 104, WindowedRate line 155, SafeRecorder line 211, FrontierAccountant line 242. dashboard/server.py gather_status line 80 and dashboard/status.py snapshot line 18. | Telemetry is file-based and per-process. MiningStatistics snapshots live only inside the process that owns them (the pool runner's snapshot rides its 10 s status event; the GBT engine's is observable only to its caller). No unified, agent-readable telemetry interface exists; the baseline agent reads none of it. | Extend in Milestone 2: one read-only telemetry surface over heartbeat, evidence census, status file and statistics snapshots. Do not add new counters; the EXP-037 categories already exist. |

## (b) Agent capability assessment: what the existing agent actually does

Files read line by line: agent/autonomous.py (127 lines) and
agent/interface.py (177 lines). These are the only two agent modules at
baseline.

### agent/autonomous.py: AutonomousMiner

Construction (__init__): takes an RPC client, a payout address, an
optional BlockStore, an optional ComputeEngine, and allow_mainnet=False.
It builds one MiningEngine with checkpoint_path=WORK_CHECKPOINT_PATH
(.local/work-checkpoint.json, the EXP-038 wiring). Nothing else is
configured. There are no parameters for backend choice, worker count,
threads, or strategy.

The complete behaviour is run_cycles(cycles=3, max_batches_per_cycle=400),
a fixed loop:

1. _guard_chain(): reads rpc.get_blockchain_info()["chain"] and raises
   unless the caller passed allow_mainnet=True for a main chain. This is
   a safety gate, not a decision.
2. bench = self.compute.benchmark(): the ComputeEngine measures itself.
   _decide("backend-selected", ...) then LOGS the backend the engine's
   own CPUID dispatch already chose, with its fallback reason and the
   measured rate. The agent does not select the backend; it records a
   selection made inside gpu/engine.py. The word "decision" in the code
   is a log label: _decide(kind, detail) appends {"kind", "detail", "ts"}
   to self.decisions and writes a BlockStore event of kind
   "agent_decision". That is the entirety of the decision machinery.
3. For each cycle: result = self.engine.mine_cycle(...). Any exception is
   caught, converted into a failure result dict, and recorded as a
   "mining_error" event; the loop continues. Every result is persisted
   via store.record_mining_cycle(result).
4. _decide("cycle-accepted" / "cycle-failed", ...): again a log of an
   outcome the engine produced, not a choice.
5. _adjust_batch(stats): the one genuine adaptive rule in the file. If
   the measured per-batch time is below TARGET_BATCH_SECONDS / 2 (0.125 s)
   and batch_size is below MAX_BATCH (2^20), double it; if above
   TARGET_BATCH_SECONDS * 2 (0.5 s) and above MIN_BATCH (4096), halve it.
   Fixed thresholds, fixed factors, no memory across cycles beyond the
   current value, no consideration of backend, template, or chain state.

State it reads: the chain name (guard), the compute benchmark scalar,
each cycle result dict, and store.mining_summary() once at the end.
State it writes: BlockStore mining cycles and events, the in-memory
decisions list, engine.batch_size, and (through the engine) the EXP-038
checkpoint file.

Actions it can take, exhaustively: run mine_cycle a caller-chosen number
of times, and change MiningEngine.batch_size within [4096, 2^20].

What it cannot do (no code path exists): start, stop, or even observe
the live mainnet miner, the autopilot, or the solo server (it imports
none of mining/mainnet_live.py, mining/stratum_client.py,
mining/autopilot.py, mining/solo_server.py); choose or pin a backend;
change thread counts; allocate extranonce or nonce ranges to workers;
refresh or reject a job; verify a candidate itself; submit anything
except through MiningEngine.mine_cycle; run or design an experiment;
read the experiment or hypothesis registries; plan beyond the fixed
loop; learn across restarts (decisions list is per-process; only
BlockStore rows and the checkpoint persist, and nothing reads the
decisions back); enforce permissions (there is no permission concept;
any caller with an RPC object gets full mine_cycle authority, gated
only by the mainnet flag).

### agent/interface.py: AgentInterface

A read-only question layer over Bitcoin Core RPC plus one regtest
action. Methods: latest_block_hash, latest_blocks, analyze_block
(blockchain/analysis.py BlockAnalyzer), block_tx_count,
network_difficulty, mempool_status and inspect_transaction
(blockchain/transactions.py TxInspector), has_new_block and sync_status
(blockchain/service.py MonitorService), node_status, current_height,
latest_block, get_block, and generate_blocks (regtest only, raises on
any other chain, uses generatetoaddress through a wallet RPC). The CLI
in main() dispatches 14 subcommands. It has no mining-engine contact at
all: it never imports mining/engine.py, gpu/engine.py, or
agent/autonomous.py. AutonomousMiner never imports it. The two modules
are disconnected.

### Verdict

The existing "agent" is a deterministic supervisory script: one fixed
mining loop, one hard-coded batch-size adaptation rule, one chain safety
gate, and an event log whose entries are labelled decisions. It makes no
strategic, research, planning, or optimisation decisions, holds no
model of the mining operation beyond the last cycle result, and has no
authority over the live mining path. Everything mandate section 4 asks
for must be built; what exists to build on is the engine wiring
(MiningEngine plus EXP-038 checkpoint), the BlockStore event sink, and
a clean read-only RPC question layer.

## (c) Execution path audit

### GBT path (regtest and solo-style direct mining)

Entry: agent/autonomous.py run_cycles, or any caller of
MiningEngine.mine_cycle (mining/engine.py line 661).

1. Job acquisition: get_template() line 550 issues getblocktemplate
   with segwit rules. wait_template() line 553 is the longpoll variant;
   mine_cycle itself calls get_template once per cycle.
2. Template preparation: with the cache enabled (default),
   prepare_template() line 541 runs TemplateCache.get, which recomputes
   the EXP-025 layered identity (template_identity line 313: family_key,
   tx_key, coinbase_key, header_key) with the uncached path's own
   validations before serving a PreparedTemplate. The fallback
   build_candidate_uncached() line 579 re-parses every template
   transaction, recomputes txid and wtxid and raises TemplateError on
   mismatch, checks coinbasevalue equals subsidy (chain halving
   interval: 150 regtest, 210000 otherwise) plus fees, and checks the
   BIP141 witness commitment against default_witness_commitment.
3. Checkpoint resume (EXP-038): if checkpoint_path was given,
   WorkCheckpoint.resume(identity, extranonce_space, curtime) returns
   fresh, resume, or exhausted; exhausted returns immediately with
   reason "nonce space exhausted".
4. Search: for each extranonce round in extranonce_space (default
   (0, 64)), PreparedTemplate.build(extranonce) produces header and
   body; batches of batch_count(batch_size, start) go to
   ComputeEngine.search_first_counted (gpu/engine.py line 1823), which
   returns the hit and the exact attempted count. FrontierAccountant
   .record_search runs per batch (EXP-037 wiring, engine.py line 750
   area). After every hitless batch, WorkCheckpoint.record advances
   the frontier; a hit batch never advances it, so unfinished work is
   never recorded as completed.
5. Candidate handling and submission: on a hit, the nonce is spliced
   into the header, the block is header plus body, and acceptance is
   decided by Core: submitblock is called, and accepted is true only
   when submitblock returns None AND rpc.get_best_block_hash() equals
   the block hash. Statistics record blocks_submitted and then
   blocks_accepted or blocks_rejected. mining/candidate_verify.py is
   NOT called on this path; the code comments state this is deliberate
   (Core's submitblock and best-chain verdict are this path's
   verification), and the ComputeEngine layer separately validates
   candidate digests internally (gpu/engine.py verify_candidate line
   377, _check_pairs line 2279, _rescan_all_candidates line 2310).

### Live pool path (the path actually mining mainnet)

Supervision: mining/autopilot.py main() builds the miner command
(mining/mainnet_live.py with duration and worker arguments) and
Autopilot.run() line 406 supervises it: 1 s poll, restart with backoff
on exit, kill when the evidence log is stale beyond the hung window,
heartbeat every 5 s carrying the EvidenceCounter census.

Runner: mining/mainnet_live.py main() line 126.

1. Endpoint: mining/endpoint_config.py resolve_endpoint picks CLI
   arguments, environment, .local/mining-endpoint.json (mode "pool" is
   public-pool.io, mode "solo" is the lab solo server), or the
   public-pool default.
2. Job acquisition: StratumClient (mining/stratum_client.py line 177)
   connects, subscribes, authorizes; reader_loop() line 392 runs in a
   thread; _handle() line 254 processes mining.notify into a job dict
   after validate_job() line 61, rejects duplicates (same job_id,
   prevhash, ntime) and stale echoes (ntime regression for the same
   tip), and bumps job_generation on every accepted template so the
   freshest template always supersedes. mining.set_difficulty and
   mining.set_extranonce update session state.
3. Search: the main loop takes (job, generation, difficulty) under the
   client lock, increments a local extranonce2 counter, builds the
   header with build_header() line 118, derives the share target with
   target_for_difficulty() line 58 (float-derived; the docstring states
   it is a pool share criterion only, never a consensus test), and
   scans in spans sized to about one second of the measured probe
   rate, abandoning the span walk the moment job_generation changes.
   Attempts are counted exactly by call_attempts() line 67 from
   engine.last_search_stats, and recorded through
   FrontierAccountant.record_search (mainnet_live.py line 239 area).
4. Candidate verification (EXP-036): on a hit, the header is rebuilt
   at the winning nonce and verify_candidate (mining/candidate_verify
   .py line 83) must confirm: hashlib and pure-Python digests agree
   with each other and with the backend digest, the header target is
   legal under POW_LIMIT_MAINNET, the exact integer share comparison
   passes, and the template is still the freshest generation.
   record_candidate_event() line 90 writes the separated counters
   (candidates, verification_hashes = 2, valid_candidates,
   network_target_candidates).
5. Submission: confirmed candidates go to StratumClient.submit()
   line 361 (mining.submit with user, job_id, extranonce2, ntime,
   nonce). The pool's verdict returns through _handle: a share_result
   evidence event, plus the on_share_result hook (default None, line
   203; invoked guarded at lines 347 to 357) feeding
   record_share_result() in the runner. A candidate that meets the
   network target is still submitted as a share: on this solo-style
   pool the pool constructs and submits the block. There is no local
   submitblock on the pool path, and no block has been found to date.

Solo variant of the same client path: with endpoint mode "solo",
mining/solo_mainnet.py runs the server side: SoloServer
(mining/solo_server.py) builds jobs from its own node's
getblocktemplate in refresh_job() line 228 (including the EXP-034
stripped-coinbase offset fix), serves them over Stratum V1, and in
submit_share() line 351 verifies each share with verify_candidate()
line 374, classifies block candidates, submits real blocks with
submitblock, and confirms acceptance with verify_chain_acceptance()
line 422. JobRefresher line 451 keeps jobs tip-following.

## (d) Experiment and integration status map (EXP-000 to EXP-043)

Sources: research/sha256d/experiment_registry.md,
research/sha256d/extreme_optimization/EXPERIMENT_REGISTRY.md, and the
production tree as read in this inspection. Statuses: INTEGRATED means
production code in the tree carries the result (files named);
RESEARCH-ONLY means the result stands in the research tree with no
production change; REJECTED means an established negative or a failed
predeclared criterion; PROVEN means a proof or verified measurement
with no code integration implied.

| EXP | Status | Evidence / production files |
|---|---|---|
| EXP-000 | Baseline (reference, not an optimisation) | Trusted baseline adopted; production C batch 1T median 1,314,704 H/s. Harness in research/sha256d/experiments/. |
| EXP-001 | REJECTED | All compiler flag variants rejected; production flags unchanged. |
| EXP-002 | RESEARCH-ONLY | H-02 SHA-NI kernel stayed in the research tree at decision time. Its lineage reaches production only through EXP-032 and EXP-039 (shani tier). |
| EXP-003 | RESEARCH-ONLY at the time | H-01 multi-stream: decision criterion not met in 2026-11-14 sessions; the streams form was later integrated via EXP-032/EXP-039. |
| EXP-004 | RESEARCH-ONLY (criterion failed) | X-067 re-run failed the beyond-spread criterion a second time; not integrated. |
| EXP-005 | RESEARCH-ONLY | Geometry sweep (streams 3, 6, strided); informs the streams-4 choice of the production shani tier. |
| EXP-006 | REJECTED | Schedule-first hand scheduling: spill ops cut, throughput not improved. Negative result. |
| EXP-007 | INTEGRATED | AVX-512 16-way MB kernel; integrated as backend v512 under the EXP-017 adoption record: mining/cpu/bal_avx512_mb.c, gpu/engine.py _try_v512. |
| EXP-008 | REJECTED | Cross-nonce phase pipelining: phase premium not supported on this core. |
| EXP-009 | RESEARCH-ONLY (measurement) | Priced candidate construction (X-059): one validateaddress plus one getblockchaininfo per build_candidate call; the measurement that motivated EXP-023. |
| EXP-010 | RESEARCH-ONLY (closure) | Part A decision closure: criterion failed a third time under the old rule; no integration. Superseded as a method by EXP-017. |
| EXP-011 | RESEARCH-ONLY | Dual-batch interleaved MB: one strong session (8,267,078 H/s) never reproduced; raw session A overwritten; excluded from the verified rate table by rule. Ancestor shape of EXP-018 and EXP-026 C2. |
| EXP-012 | PROVEN (formal closure) | VPTERNLOGD cones closed: Ch 0xCA, Maj 0xE8, XOR3 0x96; classic op counts minimal. No code change needed; the compiler already emits the forms. |
| EXP-013 | RESEARCH-ONLY | Cross-lane prefix sharing: correct, ratios straddle 1.0, below the noise floor; not integrated. |
| EXP-014 | REJECTED | K+W folding: no gain as implemented. |
| EXP-015 | REJECTED | Bitsliced SHA-256d at about 0.03x of MB16. |
| EXP-016 | PROVEN | Nonce dependency derivation adopted as programme reference: W18 delta is sigma0(nonce), W19 delta is the nonce, W20 onward nonlinear. Y-065 and Y-075 REFUTED. No production change. |
| EXP-017 | INTEGRATED (methodology) | The paired measurement stack and decision rule, adopted by owner decision 2026-11-14; every later integration verdict uses it. Tooling: research/sha256d/phase6/benchmarks/exp017_paired_bench.py, exp017_analyze.py. |
| EXP-018 | RESEARCH-ONLY | Y-023 register-resident dual-batch: residency achieved, rate not significant (PROMISING tier). Ingredient of EXP-026 C2; not integrated as its own kernel. |
| EXP-019 | REJECTED | Y-001/Y-002 carry-save schedule rejected at the price gate (a software 3:2 compressor costs 3 instructions, not 2). |
| EXP-020 | PROVEN | Full round closed at 28 vector ops per steady-state round within the searched vocabulary, with a matching SMT lower bound. The P6C-007 one-op-gap variant measured not significant; not integrated (see EXP-041). |
| EXP-021 | REJECTED | Heterogeneous worker pair: ESTABLISHED NEGATIVE under makespan and continuous-assignment accounting. |
| EXP-022 | INTEGRATED (batch scope only) | Flags batch verified 1.82x at density 0 in batch scope; adopted later by owner decision (option B): mining/cpu/bal_avx512_flags.c (bal_v_batchf2), gpu/engine.py _try_v512flags and _vf_batch_flagged, reached only from batch_search routing. The flags library exports no search entry point; it is not in the live search path. |
| EXP-023 | MIXED | Y-076 REJECTED as specified. Y-077 VERIFIED at the data level (became EXP-025). Y-079 VERIFIED TABLE. |
| EXP-024 | RESEARCH-ONLY | Design B (predeclared primary) failed the every-session criterion (pooled 1.169x, 1 of 3 sessions). Design E span scan: established negative for search. |
| EXP-024b | RESEARCH-ONLY (verified, deliberately not integrated) | Design C mask search VERIFIED: pooled 1.398x [1.242, 1.578], every session significant. Certified single-batch fallback form; production kept the dual-batch form. |
| EXP-025 | INTEGRATED | Template cache correctness and layered identity repair: mining/engine.py TemplateCache, PreparedTemplate, template_identity (family_key, tx_key, coinbase_key, header_key); build_candidate_uncached preserved as fallback. Steps500 pooled 23.02x is a candidate-construction rate, never a hash rate. |
| EXP-026 | INTEGRATED (C2) / REJECTED (C1) | C2 DualMask VERIFIED (pooled 1.718x vs production search) and integrated as backend v512dual: mining/cpu/bal_avx512_dual.c, gpu/engine.py _try_v512dual. C1 TernMask: ESTABLISHED NEGATIVE. C3/C4/C5 killed at the cost model. |
| EXP-027 | RESEARCH-ONLY (negative) | Track B characterised search: GFNI forms, shuffle rotations, rotated/byte-swapped state, carry-save beyond the schedule, addition networks, IFMA accumulation all closed with proofs at stated scopes. One sub-space left open (non-sharing cross-round restructuring), closed by EXP-033 and EXP-042. |
| EXP-028 | RESEARCH-ONLY (specification) | AVX-512 F+BW family verified on two hosts; dispatch specification partly realised by EXP-039. ARMv8 SHA2 and NEON parts remain SPECIFIED, UNVERIFIED. |
| EXP-029 | RESEARCH-ONLY (prototype) | Distributed allocator testable core proven (120 randomised trials, exact disjoint coverage); prototype at research/sha256d/phase6b/benchmarks/exp029_allocator.py. Not integrated. Multi-machine behaviour UNVERIFIED at that point (see EXP-043 for what closed). |
| EXP-030 | RESEARCH-ONLY (programme umbrella) | Repository audit and reference matrix (research/sha256d/exp030/): 53 findings, 34 matrix rows. No production code. |
| EXP-031 | RESEARCH-ONLY | CPU/VM characterisation: the guest delivers about 2 effective CPUs (estimates 1.87 to 2.04); perf counters blocked (EPERM). research/sha256d/exp031/. |
| EXP-032 | RESEARCH-ONLY at completion; kernels INTEGRATED via EXP-039 | AVX2 MB batch 1.409x and SHA-NI streams-4 batch 2.861x vs C, both VERIFIED; production bal_sha_intrin.c batch ESTABLISHED NEGATIVE (0.517x); flags on the real search path answered NEGATIVE three ways. |
| EXP-033 | RESEARCH-ONLY (mathematics) | Cross-round restructuring closed at stated bounds (ESTABLISHED NEGATIVE); Sigma0/Sigma1 minima proven exactly 4 over V; W18/W19 identities verified; W20 linearity refuted; outer precomputation negative. One shape left unrefuted (E2, H-033-05), closed by EXP-042. |
| EXP-034 | INTEGRATED | Job/template engine: mining/engine.py extranonce_space (opt-in, default (0, 64) byte-identical to history); mining/solo_server.py stripped-coinbase extranonce offset fix (real defect: segwit marker shifted the split 2 bytes). Version and ntime rolling recorded as absent (gap carried to section h). |
| EXP-035 | RESEARCH-ONLY (prototypes, by its own decision record) | Work distribution design plus lease_manager.py and candidate_queue.py prototypes in research/sha256d/exp035/; randomised campaign exact under fault injection. INTEGRATION_DECISIONS.md: no production integration this phase. Wire protocol and persistent coordinator specified, not built. |
| EXP-036 | INTEGRATED | Exact candidate verification: mining/candidate_verify.py (new production module), wired into mining/mainnet_live.py and mining/solo_server.py. Solo submitblock None no longer treated as success; acceptance requires chain confirmation (verify_chain_acceptance). |
| EXP-037 | INTEGRATED | Statistics and probability: mining/autopilot.py EvidenceCounter; mining/mining_statistics.py (separated counters, snapshot has no combined total); mining/probability.py (adopted formulas, exact-rational cross-checks). Percentile functions added in Phase 002 step 4. |
| EXP-038 | INTEGRATED | Work checkpointing: mining/work_checkpoint.py; MiningEngine opt-in checkpoint_path (default None, historical behaviour); agent/autonomous.py is the only production caller that enables it. |
| EXP-039 | INTEGRATED | Fallback tier dispatch: gpu/engine.py order CUDA, v512dual, v512, shani, avx2, C, hashlib; mining/cpu/bal_avx2_mb.c, bal_shani_streams.c, bal_shani_core.h, bal_fallback_probe.c; mining/cpu/build.py restricted flags. Batch and search both served per tier; AVX2 batch 1.252x, shani batch 2.812x, avx2 search 1.300x, shani search 2.887x vs C, all VERIFIED under EXP-017. |
| EXP-040 | RESEARCH-ONLY (benchmark) | Category F end-to-end GBT pipeline timing: harness research/sha256d/exp040/category_f.py against the unmodified production engine; non-search overhead about 44 ms per block empty, about 206 ms with 500 transactions. No production change. |
| EXP-041 | RESEARCH-ONLY (ESTABLISHED NULL) | The 29 vs 28 op codegen gap: the 28-op intrinsic forms (tmaj, tfull) are not significant under EXP-017; the production DualMask search body already emits 28. No integration; production untouched. |
| EXP-042 | RESEARCH-ONLY (ESTABLISHED NEGATIVE at stated bounds) | E2 (H-033-05) refuted for both cones by decomposition synthesis (z3 UNSAT); full-cone CEGIS at L=5 inconclusive and reported as such. H-033-02 remains open only in residual generality (shapes outside the stated bounds). |
| EXP-043 | RESEARCH-ONLY (measurement) | EXP-035 coordination overhead on this VM only: in-process verbs cheap and mostly flat; prototype defects found (unpruned lease table, snapshot deepcopy); 128-worker fault trial capped and failed, recorded as a failed run. Loopback shim measured; production wire protocol still unbuilt. |

Next unreserved experiment ID in both registries: EXP-044.

### Open UNVERIFIED register (carried from Phase 002, still open)

1. EXP-039 tier refusal on the SHA-less Intel Xeon 8321HC and on an
   AVX2-only host: established by probe construction and forced-fallback
   gates, never executed on that hardware. Closing action: one
   make test-exp039 run when the Intel host next hosts the lab.
2. AVX2 batch discrepancy: EXP-039 pooled 1.252x [1.185, 1.322] vs
   EXP-032 pooled 1.409x [1.340, 1.480] for byte-identical kernels;
   non-overlapping intervals, unresolved conditions discrepancy, no
   verdict changes.
3. Category F at production difficulty, on any other host, and the
   solo/pool pipelines' full end-to-end cost (EXP-040 measured regtest
   GBT only; the amplified variant is not production difficulty).
4. Multi-machine coordination overhead, real-network propagation
   latency, cross-machine linear scaling, the production wire protocol
   and persistent-coordinator behaviour (EXP-043 closed only the
   in-process and loopback parts, on this VM).
5. The EXP-041 -mtune=znver3 scheduling variant (compress body moves
   64 to 33 at the same 29 ALU ops): unbenchmarked; would need its own
   experiment ID (next free: EXP-044).

Also standing: EXP-028's ARMv8 SHA2 and NEON dispatch parts (specified,
unverified, no rates quoted), and H-033-02's residual generality
(5-instruction cones outside EXP-042's stated bounds), covered only by
an inconclusive full-cone CEGIS.

## (e) Duplicate implementations and unfinished integrations

Duplicates, with evidence:

1. Two functions named verify_candidate with different signatures and
   purposes: gpu/engine.py line 377 (verify_candidate(header, target,
   nonce, digest), the compute layer's per-nonce digest check) and
   mining/candidate_verify.py line 83 (verify_candidate(header,
   pow_limit, share_target=None), the EXP-036 exact verifier). Any
   future agent wiring that imports the wrong one fails silently at
   the type level only if arguments mismatch; the names invite the
   error. Recommendation: the Milestone 1 interface refers to the
   EXP-036 verifier by full module path everywhere.
2. target_for_difficulty is implemented twice: mining/mainnet_live.py
   line 58 and mining/stratum_client.py line 43. Both derive the float
   share target from DIFF1_TARGET; the solo server and the pool client
   each carry their own copy of the surrounding difficulty plumbing
   (difficulty_of exists only in mainnet_live.py).
3. Two PoW primitive modules with overlapping scope: mining/pow.py
   (dsha256, target_from_nbits, merkle helpers; the Task 001/002 era
   module used by the intelligence side and known-block tests) and
   mining/pow_engine.py (the verified production module the mining
   paths use, including check_pow with Core SetCompact semantics).
   docs/ARCHITECTURE.md lists both without stating which is
   authoritative for what. No consolidation has been done.
4. A complete legacy mining path survives alongside ComputeEngine:
   mining/cpu/miner.py (CpuMiner class line 115, verify_c_library,
   benchmark, tune_threads) driving mining/cpu/bal_miner.c and
   bal_sha_intrin.c. Repository-wide import search during this
   inspection found CpuMiner referenced only by
   tests/test_cpu_aspect.py and by a comment in gpu/engine.py line
   2772. No production entry point uses it. It is kept test coverage,
   not a live path, but nothing in the tree says so.
5. Coinbase, merkle and header construction are implemented three
   times, once per protocol: mining/engine.py build_candidate_uncached
   (GBT, merkle_root from mining/pow_engine.py), mining/stratum_client
   .py build_header line 118 (pool Stratum, branch folding inline),
   mining/solo_server.py refresh_job plus its own merkle_branch line
   87 (server side). Partly forced by the protocols (Stratum serves
   coinbase parts, GBT serves full templates), but the merkle and
   coinbase logic is genuinely re-implemented per path, and the
   EXP-034 offset defect lived in exactly one of the three copies.
6. Designed separations that are NOT duplicates, recorded so nobody
   "fixes" them: stratum_client.Evidence (append-only JSONL writer)
   vs autopilot.EvidenceCounter (incremental census reader of the same
   log); MiningStatistics in-process session counters vs the
   EvidenceCounter lifetime census (documented scopes in
   mainnet_live.py record_share_result); MiningEngine's
   build_candidate_uncached as the preserved differential reference
   for the EXP-025 cache.

Unfinished integrations:

1. EXP-024b design C: VERIFIED and deliberately not integrated;
   production kept v512dual. It remains the certified single-batch
   fallback form in the research tree only. Closing it needs an owner
   decision, not more measurement.
2. EXP-028 dispatch specification: the AVX2 and SHA-NI parts were
   realised by EXP-039; the ARMv8 SHA2 and NEON parts exist only as
   specification. No ARM host exists here; status UNVERIFIED.
3. EXP-029 allocator and EXP-035 LeaseManager/CandidateQueue: proven
   prototypes with no production integration, by EXP-035's own
   decision record. The production wire protocol and a persistent
   coordinator are specified in research/sha256d/exp035/
   WORK_DISTRIBUTION_DESIGN.md and not built anywhere.
4. EXP-022 flags: integrated for batch consumers only. A flags-form
   search entry was built in research by EXP-032 and measured not
   significant; no production search integration exists or is pending.
5. Solo cutover: staged and armed (scripts/solo_cutover.py, endpoint
   config mode "pool"), not fired; the pruned mainnet node is still in
   initial block download. Operational state, not an integration
   defect, but the solo path's production exercise on mainnet remains
   UNVERIFIED until it fires.
6. Autopilot self-update (maybe_update) is inert in this checkout:
   the tree has no .git directory, so _git returns None, the version
   reads "unknown", and no update can ever be detected. Documented
   behaviour for this deployment shape (push happens through the
   contents-API helper, not git), recorded here so the agent layer
   does not mistake it for a live update channel.
7. agent/intelligence/ (audit.py, memory.py, permissions.py): created
   by the concurrent Milestone 1 build during this inspection; at
   reading time nothing in agent/autonomous.py or agent/interface.py
   imports it. Unfinished by definition until the Milestone 1 wiring
   lands and is tested.

## (f) Doc-vs-code differences found in THIS inspection

The Phase 002 corrections wave fixed 11 known contradictions. The
following remain, each checked against source during this inspection:

1. docs/ARCHITECTURE.md, module map, gpu/ entry: the dispatch chain is
   given as "CUDA when a real device passes the self-test, then
   v512dual, v512, the C batch backend, then Python hashlib". The
   shani and avx2 tiers added by EXP-039 are missing. Source:
   gpu/engine.py ComputeEngine.__init__ lines 922 to 941 (CUDA,
   v512dual, v512, shani, avx2, C, then the hashlib floor in the
   search layer). README.md line 109 and docs/MINING_ENGINE.md's
   sibling text in README carry the correct order; ARCHITECTURE.md
   does not.
2. docs/MINING_ENGINE.md, "Update, 2026-11-15" section: the same
   omission. It states the dispatch order as "CUDA, v512dual, v512,
   the C batch backend, then Python hashlib", with no shani or avx2.
   The document's own dating note says the update records the current
   state, so this is current-state text that is one integration
   behind.
3. docs/ARCHITECTURE.md, module map, mining/ entry: the kernel list
   names bal_avx512_dual.c, bal_avx512_mb.c, bal_avx512_flags.c,
   bal_batch.c, bal_miner.c and bal_sha_intrin.c, but omits
   bal_avx2_mb.c, bal_shani_streams.c, bal_shani_core.h,
   bal_fallback_probe.c and bal_avx512_probe.c, and the module list
   omits mining/endpoint_config.py entirely (the module that decides
   pool vs solo for the live runner). All five kernel files exist in
   mining/cpu/ and are wired by mining/cpu/build.py.
4. docs/ARCHITECTURE.md, module map, agent/ entry: describes only
   interface.py ("structured JSON answers from live RPC data,
   including Regtest block generation"). agent/autonomous.py, the
   AutonomousMiner that the rest of the documentation calls the agent,
   is not mentioned.
5. docs/ARCHITECTURE.md, module map, dashboard/ entry: "status.py, a
   JSON snapshot CLI that a future web dashboard will poll". A web
   dashboard already exists: dashboard/server.py (gather_status line
   80, Handler line 116, main line 134) serves it. The doc understates
   shipped code.
6. docs/ARCHITECTURE.md, decision 3, present tense: "The CPU miner
   engine remains C with OpenSSL for SHA-NI speed." Production search
   has run the AVX-512 v512dual kernel since the EXP-026 integration;
   the C/OpenSSL path is a fallback tier in gpu/engine.py dispatch.
   The decision text is historical in origin but is not marked as
   superseded, unlike decision 2, which the corrections wave updated
   with exactly such a marker.
7. docs/MINING_ENGINE.md, "How a cycle works", step 5: "Every
   candidate is re-verified on the CPU before submission." For the
   GBT cycle the document describes, mining/engine.py mine_cycle does
   not call mining/candidate_verify.py; the hit path splices the
   nonce, calls submitblock, and judges by best-chain equality (the
   code comments say this is deliberate). CPU-side digest checking
   does happen inside gpu/engine.py's search internals, but the
   EXP-036 exact verifier the document's own 2026-11-15 update names
   is not on this path. The sentence overstates the GBT path's
   verification as written.
8. README.md, repository map, research/ entry: "the exp030 to exp038
   trees". The tree now also contains exp039, exp040, exp041, exp042
   and exp043 directories (all present under research/sha256d/), plus
   research/master_build/ as of this milestone. The map is one phase
   behind.
9. README.md, "Status at a glance (2026-11-13)" and the Live mining
   status table: session-1 figures (5.18 MH/s average, suite peak
   6.62 MH/s) remain the front-page numbers. The dated updates deeper
   in the file record the v512dual integration, so the file is not
   self-contradictory, but the at-a-glance table was never refreshed
   and a reader who stops there gets a two-day-old, roughly 4x low
   picture of the live rate. Recorded as staleness, not falsehood.
10. README.md line 53 and line 225, and docs/EVIDENCE.md line 5:
    "make test-all (33 targets, all must print PASSED)". The count 33
    is correct (verified against Makefile line 107 in this
    inspection). The "all must print PASSED" clause is not true of
    this VM as shipped: test-rtl fails because iverilog is absent
    after VM replacements, a standing environment failure recorded
    across the programme. The docs do not carry that caveat at the
    point of the claim.

No other differences were found in the three documents against the
code paths read for this reconciliation. Items NOT re-checked in this
pass (UNVERIFIED here): docs/AUTOPILOT.md, docs/SOLO_CUTOVER.md,
docs/CUDA.md, docs/HARDWARE.md and results/ were outside the assigned
check set.

## (g) Reusable components inventory for Milestones 1 to 5

Each entry: path, what it is, and what the agent layer should reuse
rather than rebuild.

| Component | Path | Reuse directive |
|---|---|---|
| Autopilot supervisor | mining/autopilot.py (Autopilot, EvidenceCounter, default_worker, evidence_stats) | Milestone 2 telemetry and Milestone 5 recovery build on its heartbeat and census; the agent must not grow a second supervisor. Start/stop authority, when granted, acts through the autopilot's own mechanisms (stop file, child lifecycle), never by killing processes directly. |
| EvidenceCounter | mining/autopilot.py line 107 | The lifetime share census. Any agent-reported share total comes from here or from the evidence log itself, never from a process-local counter. |
| MiningStatistics plus SafeRecorder plus FrontierAccountant | mining/mining_statistics.py lines 104, 211, 242 | The EXP-037 separated accounting vocabulary (backend_hashes, unique coverage, repeated work, candidates, verification, submissions) with failure isolation. Milestone 2 exposes snapshots; Milestone 3 records experiment outcomes in the same categories. snapshot() deliberately has no combined total; keep it that way. |
| WorkCheckpoint | mining/work_checkpoint.py (resume line 90, record line 133) | The only production frontier record. Milestone 5 connects the agent to it; do not design a second checkpoint format. Its identity already includes the EXP-025 layered identity plus extranonce space plus curtime basis. |
| Candidate verifier | mining/candidate_verify.py (verify_candidate, classify_submit_result, verify_chain_acceptance) | The single exact-verification authority for pool and solo paths. Milestone 1 interface exposes it by full module path; Milestone 6 uses verify_chain_acceptance for the acceptance leg. |
| Probability module | mining/probability.py (expected_hashes, expected_seconds, prob_at_least_one, quantile_seconds, median_seconds, percentile_seconds, prob_at_least_one_exact, expected_hashes_exact, prob_within_period, PERIOD_SECONDS) | All agent statements about odds, expected waits and target gaps (mandate section 16 reporting) compute through here, including the exact-target forms. The two 63.2 percent anchors are different numbers and are pinned separately in tests; keep them separate in agent output too. |
| EXP-035 lease manager prototype | research/sha256d/exp035/lease_manager.py (LeaseManager: register_worker, heartbeat, declare_job, lease, progress, complete, expire, steal, snapshot, restore, accounting, assert_partition_invariant) | The Milestone 5 productionisation source. Its fencing tokens, lease_ids and restart honesty (leases never survive a coordinator restart) are the design; EXP-043's findings (prune the lease table, bound snapshot cost) are the known fixes to carry in. |
| EXP-035 candidate queue prototype | research/sha256d/exp035/candidate_queue.py (CandidateQueue: submit, drain, recover, journal) | The deduplication and journalled candidate hand-off for Milestone 5; 892 duplicate submissions were detected by this design in the EXP-035 campaign. |
| EXP-029 allocator | research/sha256d/phase6b/benchmarks/exp029_allocator.py | The earlier disjoint-range allocator proof (120 randomised trials). Read before touching EXP-035 code: EXP-035 supersedes it as the design of record, but its trial corpus is reusable test evidence. |
| Blockchain Intelligence Engine | blockchain/store.py (BlockStore: record_event, record_mining_cycle, mining_summary), blockchain/monitor.py (ChainMonitor), blockchain/analysis.py (BlockAnalyzer), blockchain/transactions.py (TxInspector), blockchain/service.py (MonitorService) | The agent's existing persistence and chain-question layer. BlockStore is where AutonomousMiner already writes decisions and cycles; Milestone 1 memory and audit should extend this store's conventions (SQLite, WAL) rather than invent a parallel database. Analysis and monitor classes back agent/interface.py today. |
| ComputeEngine dispatch | gpu/engine.py (ComputeEngine, benchmark, benchmark_report, describe) | Backend selection, eligibility probing and measured tuning already exist and are CPUID-safe. Milestone 4 reads eligibility and rates from here; it must not re-probe or re-tune. |
| EXP-017 measurement stack | research/sha256d/phase6/benchmarks/exp017_paired_bench.py, exp017_analyze.py | The integration gate for Milestone 3, verbatim. No second benchmarking statistic. |
| Endpoint configuration | mining/endpoint_config.py (load_config, set_mode, resolve_endpoint) | The pool/solo switch the cutover owns. The agent reads mode from here; it never edits the config (the cutover script owns flips). |
| Solo cutover machinery | scripts/solo_cutover.py (check, fire, rollback, status) | The template for controlled production transitions with automatic rollback; Milestone 3 integration steps should follow its shape. |
| Solo server | mining/solo_server.py (SoloServer, JobRefresher, SoloTCPServer) | A complete second job source and verifier consumer. Milestone 6's end-to-end demonstration can run against it on regtest without new server code. |
| Machine characterisation | research/sha256d/exp031/CPU_VM_CHARACTERIZATION.md plus exp031/tools | Milestone 4's machine-discovery baseline: about 2 effective CPUs behind 4 visible vCPUs, perf counters blocked. The scheduler design starts from these measured facts. |

## (h) Highest-priority missing functionality, ranked

Ranking basis: what unblocks the mandate's acceptance criteria
(section 15) earliest, at lowest risk to the live operation.

1. **A typed agent-to-mining-engine interface with permissions and an
   audit trail (Milestone 1 core).** Today the agent's only interface
   is direct object construction, and authority is all-or-nothing.
   Files: agent/intelligence/ package (in flight concurrently:
   permissions.py, audit.py, memory.py already exist as of this
   inspection; the interface and task modules do not yet). Modify:
   agent/autonomous.py (route every action through the permission
   checker and audit log), agent/interface.py (no change needed for
   reads; it is already read-only). New tests:
   tests/test_agent_intelligence.py (or the concurrent build's chosen
   name).
2. **Live mining awareness (Milestone 2).** The agent cannot see the
   system it is meant to direct: heartbeat, evidence census, pool job
   state, backend, unique coverage and share outcomes are all
   invisible to agent/. Files to create: a telemetry reader module
   under agent/intelligence/ that reads mining/autopilot.py's
   heartbeat and EvidenceCounter outputs, .local/mainnet-status.txt,
   and MiningStatistics snapshots. No production mining file needs
   modification; the data already exists.
3. **Persistent, queryable research memory (Milestone 1).** The
   programme's findings live in two prose registries totalling about
   3,500 lines plus per-experiment trees. The in-flight
   agent/intelligence/memory.py parses them; it must be finished,
   tested against the registries as they stand (including the
   EXP-033 JSON registry), and wired so hypothesis lookup by ID and
   by status is one call. Companion seed:
   research/master_build/RESEARCH_OPPORTUNITY_REGISTER_SEED.md.
4. **A task registry and planning layer (Milestone 1).** No file in
   the baseline represents a task with objective, dependencies,
   evidence requirements, budget and completion state (mandate
   section 4.1 C). Files to create: the planning/task module under
   agent/intelligence/, persisted through blockchain/store.py
   conventions.
5. **Strategic state tracking (Milestone 1/2).** Nothing in the tree
   computes the mandate section 16 report (verified throughput vs
   500 GH/s and 140 TH/s, gap, best next optimisation) from live
   data. Files to create: a strategy module under agent/intelligence/
   consuming mining/probability.py and the telemetry from item 2.
6. **The autonomous optimisation loop (Milestone 3).** The 17-step
   cycle exists only as programme practice. Files to create: an
   experiment workflow module under agent/intelligence/ driving the
   EXP-017 harness and the registries; no production mining file is
   modified by the loop except through the integration gate.
7. **Adaptive CPU scheduler and resource registry (Milestones 4/5).**
   Productionise research/sha256d/exp035/lease_manager.py and
   candidate_queue.py into a production module (new file, location
   for Milestone 5 to settle, mining/ or agent/intelligence/), carry
   in EXP-043's two fixes (lease-table pruning, bounded snapshots),
   and connect mining/work_checkpoint.py frontiers to lease
   accounting. Prerequisite: item 1's permissions, so range
   allocation is a Level 2 controlled operation.
8. **GBT-path verification decision (Milestone 6, small).** Either
   wire mining/candidate_verify.py into mining/engine.py's hit path
   or record the reliance on Core's submitblock plus best-chain
   verdict as the standing, audited design. One of the two must be
   written down; today the divergence is visible only in a code
   comment and is misstated in docs/MINING_ENGINE.md step 5 (see
   section f, item 7).

Explicitly NOT missing and not to be rebuilt: backend kernels and
dispatch (EXP-039 state is complete for this hardware class), the
template cache (EXP-025), exact verification for pool and solo
(EXP-036), statistics categories (EXP-037), GBT checkpointing
(EXP-038), the solo server, and the cutover machinery.

## Method and limits of this reconciliation

Read in full: agent/autonomous.py, agent/interface.py,
mining/mainnet_live.py, mining/engine.py (MiningEngine and mine_cycle
in full; template layer by function), docs/ARCHITECTURE.md,
docs/MINING_ENGINE.md, README.md, both experiment registries
(EXP-024 to EXP-043 records in full; EXP-000 to EXP-023 records in
full or in their registry summaries), the EXP-033 hypothesis JSON,
the Phase 001 hypothesis summary table. Read by structure and key
sections: gpu/engine.py (dispatch and entry points), mining/autopilot
.py, mining/stratum_client.py, mining/candidate_verify.py,
mining/solo_server.py, mining/mining_statistics.py,
mining/work_checkpoint.py, mining/probability.py, the EXP-035
prototypes. Anything not read is not claimed. The Makefile test-all
count (33) was verified by direct count of Makefile line 107. No
tests were run in this milestone, per instructions.
