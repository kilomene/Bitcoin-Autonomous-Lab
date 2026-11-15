# EXP-030 Phase B: NOVA Repository Audit and Gap Analysis

Date: 2026-11-15. Scope: the current NOVA codebase and research
tree of the Bitcoin Autonomous Lab, audited against the EXP-030
programme directive (owner directive 2026-11-15; record at
~/workspace/goals/bitcoin-autonomous-lab-private-bitcoin-mining-lab/files/EXP030_DIRECTIVE_RECORD.md,
sections 4 to 12).

Method: every claim below was read from the tree itself on
2026-11-15: the production code under mining/, gpu/, dashboard/,
scripts/, agent/, blockchain/ and node/; the research trees under
research/sha256d/ (phase6, phase6b, extreme_optimization, tools);
the docs under docs/; the evidence log evidence/mainnet-live.jsonl;
and the test surface (Makefile, 26 test targets). No benchmarks
were run (Phase C owns measurement). Nothing was restarted and no
production code was changed. Where a component's state could not
be settled from the code, this document says so instead of
guessing.

Status vocabulary:

- EXISTS: a production implementation exists and is exercised by
  a live or tested production path. Gaps may still be named.
- PARTIAL: real production code covers part of the requirement;
  the named remainder is missing.
- MISSING: no production implementation. Where a research
  prototype exists, it is named and never counted as production.

Headline result: of the directive's 20 required logical
components, 2 are EXISTS, 15 are PARTIAL, and 3 are MISSING in
production (Work Lease Manager, Distributed Agent Coordinator,
Candidate Queue). The MISSING three all have their substance in
exactly one place: the EXP-029 research design and allocator
prototype, which no production code imports. The strongest
existing assets are the ComputeEngine accounting vocabulary
(Task 003.9), the EXP-025 template cache, the EXP-017 measurement
stack, and the MiningEngine acceptance rule. The weakest point,
relative to the mission definition (discover, verify, construct
and submit a valid block), is that the only path that can
assemble a mainnet block today, the solo server, applies a
weaker submission acceptance standard than the regtest engine
path and never verifies acceptance against chain state.

## 1. Per-component table

| # | Component | Status | Evidence files | Gap | Closed by |
|---|-----------|--------|---------------|-----|-----------|
| 1 | CPU Capability Detector | PARTIAL | mining/cpu/bal_avx512_probe.c (flag-free CPUID probe, production); gpu/engine.py (_try_v512, _try_v512dual, _try_v512flags selection); research/sha256d/phase6b/benchmarks/exp028_probe.c and exp028_dispatch.py (16-bit feature mask, research only); research/sha256d/tools/probe_machine.py | Production dispatch probes exactly two features (AVX-512F, AVX-512BW). The wider EXP-028 mask (AVX2, SHA, BMI, ADX, AES and the AVX-512 subsets) exists only as a research artifact and is not wired into production. There is no persisted capability record that dispatch and experiments share; each selection path calls its own probe inline. No ARM detection anywhere. | EXP-031 (record), EXP-032 (consumption) |
| 2 | Resource and VM Profiler | PARTIAL | research/sha256d/tools/probe_machine.py; research/sha256d/tools/machine_probe_2026-11-14.json; covariate sampling in research/sha256d/phase6/benchmarks/exp017_paired_bench.py (sample_env: steal jiffies, load, runnable) | The probe is a one-shot research script, not a maintained profiler. It reads model name, flags, cpu0 cache map, MemTotal, MHz samples, load1 and a single-stream copy bandwidth. Nothing in the tree reads cgroup quota or period, CPU affinity or allowed sets, or hypervisor identity (grep over production and probe code returns no hits). Physical topology is not measured: probe_machine.py embeds a literal topology_note string describing this VM, so on any other host it would print this host's facts. Steal time exists only as a benchmark covariate, never as a standing measurement. No repeatable resource-characterisation benchmark exists as a tool. Unknown values are not reported as unknown; several are hardcoded notes. | EXP-031 |
| 3 | SHA-256d Kernel Registry | PARTIAL | Kernels: mining/cpu/bal_batch.c, bal_avx512_mb.c, bal_avx512_dual.c, bal_avx512_flags.c, bal_sha_intrin.c, bal_avx512_probe.c, bal_miner.c, gpu/cuda/engine.cu; builders and smoke tests: mining/cpu/build.py; dispatch: gpu/engine.py ComputeEngine.__init__ and _try_* methods; describe() in gpu/engine.py | Kernels exist as separate translation units with per-kernel builders, but there is no registry: no single place records a kernel's feature requirements, entry points, accounting contract and provenance. Adding a kernel means editing gpu/engine.py in several places. The SHA-NI kernel (bal_sha_intrin.c) is built but never dispatched by the production engine; it serves only the CPU-aspect tests via mining/cpu/miner.py. No AVX2 kernel exists anywhere (grep for avx2 in mining/cpu and gpu/engine.py returns nothing). | EXP-032 |
| 4 | CPU Mining Execution Engine | EXISTS | gpu/engine.py (ComputeEngine: search_first, search_first_counted, batch_search, Task 003.9 accounting, thread auto-tuners tune_c_threads, tune_v512_threads, tune_v512dual_threads); mining/engine.py MiningEngine.mine_cycle; mining/mainnet_live.py search loop; gpu/benchmark.py | The engine is real, dispatched (CUDA, v512dual, v512 plus flags batch, C, hashlib) and carries exact accounting. Named gaps: no AVX2 backend; the flags shape serves the batch API only, so whether it can improve the real search path is exactly the open Phase D question; there is no standing whole-miner benchmark harness for the full Stratum loop (gpu/benchmark.py measures the batch layer with correct discipline, and mainnet_live self-reports a cumulative average rate). The production CPU engine living in gpu/engine.py is an organisational hazard recorded in section 4. | EXP-032 |
| 5 | Header and Midstate Builder | PARTIAL | mining/engine.py (build_coinbase, header assembly in build_candidate_uncached and PreparedTemplate.build); mining/pow.py (dsha256, target_from_nbits, merkle_root, coinbase_subsidy); mining/cpu/bal_batch.c (midstate-optimised C kernel: first compression computed once per header); mining/stratum_client.py build_header; mining/solo_server.py validate_share header assembly; research/sha256d/header_and_midstate_analysis.md | No distinct component or shared interface. Header construction is implemented independently in at least four places (engine, solo server, Stratum client, and the PreparedTemplate path) with different conventions, including the client's prevhash wordswap modes. Midstate reuse exists inside the C kernel and as cached merkle levels in the template cache, but no midstate object is shared between template construction and the AVX-512 kernels, which consume full 80-byte headers. | EXP-032, EXP-034 |
| 6 | Template Manager | PARTIAL | mining/engine.py (get_template, wait_template GBT longpoll, TemplateCache); mining/solo_server.py (JobRefresher: tip tracking, 120 s max age, node gating via check_node); mining/stratum_client.py (job_generation freshness guards, duplicate and stale-echo rejection) | Three work sources (direct GBT, GBT via the solo server, pool Stratum) each manage templates their own way. There is no unified manager, no shared job generation identifier (solo uses a hex sequence, Stratum uses the pool's string, GBT has none), no invalidation or cancellation abstraction (freshness is per-consumer: a generation counter in the client, wholesale jobs-dict replacement in the server, a fresh fetch per cycle in MiningEngine), and no persistent job records anywhere: templates are never written to disk, and the solo server's job table is memory-only. | EXP-034 |
| 7 | Coinbase and Merkle Builder | EXISTS | mining/engine.py (build_coinbase: BIP34 height push, BIP141 witness commitment, subsidy plus fees validation; strip_witness, txid_of, wtxid_of); mining/pow.py merkle_root; PreparedTemplate cached merkle levels in mining/engine.py; mining/solo_server.py (merkle_branch, attach_witness); tests/test_mining_engine.py, tests/test_template_cache.py | Construction is correct, validated against Core templates, and adversarially tested through the EXP-025 cache gates. The gap is duplication, not correctness: the solo server re-implements branch and witness handling as inverse operations of the engine's functions instead of sharing one module, so the two implementations can drift independently. | EXP-034 (consolidation) |
| 8 | Work Lease Manager | MISSING (production); research prototype exists | research/sha256d/phase6b/benchmarks/exp029_allocator.py (RangeAllocator: lease, progress, complete, fail_worker, steal, snapshot, restore, heartbeat, stale_workers, accounting); research/sha256d/phase6b/benchmarks/exp029_tests.py; research/sha256d/phase6b/EXP029_DISTRIBUTED_EXECUTION.md | No production code leases work. mining/mainnet_live.py scans nonce spans linearly per job with an in-memory extranonce2 counter; MiningEngine.mine_cycle walks extranonce rounds 0 to 63 and the nonce space directly. There are no lease identities, no expiry, no progress positions and no reassignment in any production path. The allocator is imported by nothing outside its own tests. | EXP-035 |
| 9 | Worker Supervisor | PARTIAL | mining/autopilot.py (heartbeat every 5 s, watchdog 1 s poll, 300 s hung window on evidence staleness, exponential backoff capped at 30 s, 24 h session rotation, flock single instance, self-update with smoke test and rollback); scripts/autopilot.sh; scripts/bal-autopilot.service, bal-bitcoind.service, bal-solo.service; scripts/solo_cutover.py (solo service supervision at cutover) | The autopilot supervises exactly one process shape, the pool miner child. There is no per-worker state model (identity, failure state, restart state, last completed work position) beyond pid, uptime and restart count in the heartbeat. The solo server is supervised by a systemd unit plus the cutover script, not by the autopilot; the MiningEngine and agent path has no supervisor at all. The outer keeper that restarts the autopilot itself is a goal-owned cron living outside this repository, so the repo alone does not contain the full supervision story it depends on. | EXP-038, EXP-035 |
| 10 | Distributed Agent Coordinator | MISSING (production); design exists | research/sha256d/phase6b/EXP029_DISTRIBUTED_EXECUTION.md (seven mechanisms specified: allocation, dynamic pull, stealing, duplicate prevention, template propagation, failure recovery, telemetry); research/sha256d/phase6b/benchmarks/exp029_allocator.py | No coordinator process, worker registry, or inter-instance protocol exists in production. The only multi-machine mechanism is convention: each agent runs its own checkout and derives a unique Stratum worker name from its hostname (mining/autopilot.py default_worker). Nothing prevents two GBT-path engines with the same payout address and template from performing identical header work, because both step extranonces from 0 over identical coinbases; on the pool path the per-connection extranonce1 is the only separation, and it is the pool's doing, not NOVA's. | EXP-035 |
| 11 | Candidate Queue | MISSING | No queue construct exists in production code (grep for Queue across mining/, gpu/, agent/, scripts/ returns no candidate queue; candidates are handled synchronously) | Candidates flow inline: ComputeEngine returns a hit, the caller verifies it on the spot (gpu/engine.py _check_pairs and _rescan_all_candidates; the confirmation block in mining/mainnet_live.py), and the solo server validates and submits inside its connection handler thread. There is no buffering, no backpressure, no ordering, and no persisted candidate record: a candidate exists as an evidence-log line only after confirmation, so a crash between discovery and submission loses it without a trace (see component 20). | EXP-036 |
| 12 | Exact Candidate Verifier | PARTIAL | gpu/engine.py (verify_candidate, cpu_digest: every backend candidate is re-verified on CPU; fail-closed rescan on a bad candidate); mining/pow_engine.py (check_pow: independent from-spec verifier with Core-style reason codes negative-target, overflow-target, zero-target, target-above-limit, high-hash); mining/pow.py block_work_ok; mining/mainnet_live.py candidate confirmation block | Verification exists in three separate implementations with three different standards, and the strictest one is not on any production path: pow_engine.check_pow is called only by tests and scripts/milestone_003_006.py. mining/pow.py block_work_ok omits the negative, overflow and above-limit checks. The live path verifies inline (hashlib recompute equals backend digest, value versus target, template freshness), which is sound for shares, but its pool target is derived by float division (target_for_difficulty and difficulty_of in mining/mainnet_live.py), not by exact integer semantics; the network-target leg does use the exact target_from_nbits, so the live check is mixed, not uniformly exact. The directive's twelve-step pipeline (immutable job recovery, header reconstruction, exact target decode, full block construction, local validation, submission, response recording, chain-state acceptance verification) is implemented as one pipeline nowhere. | EXP-036 |
| 13 | Full Block Constructor | PARTIAL | mining/engine.py MiningEngine.mine_cycle (header plus body assembly on a hit); mining/solo_server.py submit_share (header, varint, witness-reattached coinbase, template transactions) | Two independent implementations, no shared component. The flagship live path cannot construct a block at all: mining/mainnet_live.py holds no transaction set, so a network-target hit there is logged as is_block_candidate and submitted as a pool share, correctly for a pool, but it means block construction exists only on the GBT engine path and the solo server path. | EXP-036, EXP-034 |
| 14 | Bitcoin Core Submission Adapter | PARTIAL | mining/engine.py mine_cycle (submitblock; a block counts only when submitblock returns None AND getbestblockhash equals the block hash); mining/solo_server.py submit_share (submitblock with exception capture and a recorded result); node/rpc_client.py (BitcoinRPC); scripts/solo_cutover.py (post-flip verification) | The two Core paths apply different acceptance standards. The engine path verifies acceptance against chain state; the solo server path, the one that would submit a real mainnet block, sets ok purely from submitblock returning None and never checks the best chain or block index afterwards. No shared adapter exists, and submitblock reason strings (duplicate, stale, invalid) are recorded verbatim but never classified or acted on. The engine path's stronger rule is exercised only on regtest. | EXP-036 |
| 15 | Stratum V1/V2 Adapter | PARTIAL | V1 client: mining/stratum_client.py (subscribe, authorize, notify, set_difficulty, set_extranonce, submit; validate_job; reconnecting reader_loop); V1 server: mining/solo_server.py; endpoint switching: mining/endpoint_config.py | Stratum V1 exists on both sides. Stratum V2 is entirely absent (no SV2 code anywhere in the tree). Even within V1 there is no version rolling and no miner-side timestamp rolling: submit sends the job's version and ntime verbatim (mining/stratum_client.py submit), and the only production search-space expansion is extranonce2 stepping (mainnet_live) and extranonce rounds (MiningEngine). Client and runner are fused; there is no adapter interface separating protocol handling from mining logic. | EXP-034, EXP-036 |
| 16 | Statistics Engine | PARTIAL | gpu/engine.py Task 003.9 accounting definitions (requested_hashes, unique_coverage, backend_hashes, device_hashes, researched_hashes, verification_hashes, candidate_count) in every stats dict; evidence/mainnet-live.jsonl (append-only; event census on 2026-11-15: job 4601, template_validated 3343, status 1873, submit 248, share_result 248, candidate_confirmed 212, candidate_rejected 2, backend_selected 12); mining/autopilot.py heartbeat; mining/solo_server.py stats() per-worker counters; blockchain/store.py mining_cycles and mining_summary (agent path only); gpu/benchmark.py | There is no statistics engine as a component, only per-path counters that share a vocabulary. Of the directive's fifteen tracked categories, several exist in exactly one path (verification hashes only in ComputeEngine stats; repeated work only in CUDA overflow accounting and the research allocator) and some exist nowhere (completed and abandoned leases, job distribution latency, submission latency, worker recovery time, template construction latency as a series). Hashrate is a cumulative session average in status events, not windowed or sustained series; per-backend rates over time are not kept; best difficulty is an in-memory variable in mainnet_live and is lost on restart. Concrete defect: autopilot.evidence_stats counts accepted shares by reading only the last 2,000,000 bytes of evidence/mainnet-live.jsonl, and the log is already 2,185,778 bytes, so the heartbeat's shares_accepted_total is a tail-window count that silently excludes early accepted shares and will drift further from the lifetime total as the log grows. | EXP-037 |
| 17 | Mathematical Research Engine | PARTIAL | research/sha256d/mathematical_foundations.md, boolean_equivalence.md, message_schedule_research.md, header_and_midstate_analysis.md, round_optimization.md, automated_discovery.md; research/sha256d/phase6/MATHEMATICAL_DISCOVERIES.md and COMPUTATION_GRAPH_RESEARCH.md; research/sha256d/phase6/src/discovery_harness.py, exp020_round_search.py, exp027_vocab_search.py, nonce_dependency.py; proofs under research/sha256d/extreme_optimization/proofs, phase6/proofs, phase6b/proofs; mining/pow_engine.py PureSHA256 (independent reference implementation) | The research base is deep (EXP-016 dependency derivation, EXP-020 vocabulary optimum at 28 ops, EXP-027 closures with z3 proofs) but it is a library of per-phase snapshots, not a living engine: several documents are superseded by later phases without saying so in place, and there is no machine-readable hypothesis registry. HYPOTHESIS_REGISTRY.json does not exist anywhere in the tree; both hypothesis registries are Markdown (see component 18). The one explicitly open space, non-sharing cross-round restructuring (EXP-027), has a stated blocker (search-space size) but no bounded method yet. | EXP-033 |
| 18 | Benchmark and Experiment Registry | PARTIAL | research/sha256d/phase6/benchmarks/exp017_paired_bench.py and exp017_analyze.py (paired 65,536-hash blocks, randomised AB/BA order, steal and load covariates, OLS adjustment, pairs bootstrap, append-only session files); per-experiment drivers under phase6/benchmarks and phase6b/benchmarks; registries: research/sha256d/extreme_optimization/EXPERIMENT_REGISTRY.md and research/sha256d/experiment_registry.md; hypothesis registries: extreme_optimization/HYPOTHESIS_REGISTRY.md (X-001 to X-116) and HYPOTHESIS_REGISTRY_Y.md (Y-001 to Y-108); ranking: research/sha256d/phase6/src/rank_hypotheses.py and phase6/HYPOTHESIS_RANKING.md | The EXP-017 stack is a genuine, reused measurement standard, and the adopted integration decision rule rests on it. The registry layer is weaker: two Markdown experiment registry files are maintained in parallel and have diverged before (EXP-025 was appended to the lowercase file while the uppercase file still marked it reserved; EXP-026 realigned them), each paired-bench driver is a per-experiment copy rather than one harness with pluggable arms, and there is no EXPERIMENT_MANIFEST.json or any machine-readable registry, so the directive's section 13 quality requirements cannot be checked mechanically. | EXP-032, EXP-033, EXP-037 |
| 19 | Persistent State Manager | PARTIAL | blockchain/store.py BlockStore (SQLite: blocks, transactions, sync_status, chain_events, mining_cycles; used by the agent and dashboard on the regtest intelligence path); .local JSON state (heartbeat.json, mining-endpoint.json, mainnet/node-config.json, solo cutover marker, solo-status.json written by mining/solo_mainnet.py); evidence/*.jsonl append-only logs | State is scattered across three unrelated mechanisms (SQLite for one path, JSON files for operations, memory for everything else) with no manager and no common schema. The decisive gap: there are no work-state checkpoints anywhere. No record exists of in-progress search ranges, so any restart restarts coverage from nonce 0 and extranonce2 0 for the current job, and repeated work across restarts is neither prevented nor accounted (grep for checkpoint in production code returns nothing). MiningEngine cycle results are persisted after the fact by the agent path only; the live mainnet path persists nothing but its evidence log. | EXP-038, EXP-035 |
| 20 | Autonomous Recovery Controller | PARTIAL | mining/autopilot.py (watchdog, hung-miner kill, backoff, session rotation, self-update with smoke test and rollback); mining/stratum_client.py reader_loop (reconnect with session reset, one-second retry); mining/solo_server.py JobRefresher (refuses work while the node is not ready, resumes when it is); scripts/solo_cutover.py (preconditions, live smoke test, share verification, automatic rollback); systemd units in scripts/ | Recovery is per-process improvisation, not a controller with a policy. There is no startup self-test on the live path beyond backend selection self-tests (no end-to-end node, template and payout check before mining resumes); no candidate recovery (a confirmed candidate lives in process memory and one evidence line; a crash before submission loses it); no resource-exhaustion handling (the evidence log grows without bound and nothing watches disk or memory); and no rule anywhere that a restarted process must reconcile unfinished work, which is currently satisfied only by absence: the miner starts a new session and claims nothing about the old one, rather than by an explicit checkpoint-and-resume or checkpoint-and-abandon record. The autopilot's self-update is inert in this checkout (there is no .git directory, _git returns None, maybe_update exits silently, heartbeat version reads "unknown"). | EXP-038 |

Counts: EXISTS 2 (components 4 and 7), PARTIAL 15 (1, 2, 3, 5,
6, 9, 12, 13, 14, 15, 16, 17, 18, 19, 20), MISSING 3 (8, 10, 11).
Of the three MISSING components, two (8 and 10) have a proven
research core in EXP-029 that production never imports; one
(11, Candidate Queue) has no implementation anywhere in the
tree, research included.

## 2. Per-experiment readiness: EXP-031 to EXP-038

### EXP-031: CPU and virtual machine intelligence

Builds on: probe_machine.py and its 2026-11-14 snapshot (model,
flags, cache map, memory, MHz samples, load, one bandwidth
figure); the EXP-028 research probe (exp028_probe.c: a 16-bit
instruction-feature mask, verified against cpuinfo on this host);
the EXP-017 driver's covariate sampling (steal fraction and
runnable load are already computed correctly there, per paired
call). Greenfield: cgroup quota and period reading, affinity and
allowed-CPU-set reporting, hypervisor identification, measured
(not hardcoded) topology, thermal and throttling signals where
exposed, performance-counter availability, a repeatable
resource-characterisation benchmark maintained as a tool, an
unknown-means-unknown reporting discipline, and a persisted
capability record that EXP-032 dispatch can consume. Readiness:
the experiment is mostly new construction on top of two research
scripts; nothing in production blocks it, and nothing in
production currently depends on its output.

### EXP-032: CPU execution engine

Builds on: the production ComputeEngine with five dispatched
backends and exact accounting; the EXP-024 and EXP-024b mask
search records (design C verified at pooled 1.398x in search
scope as a single-batch form; DualMask already integrated from
EXP-026); the EXP-022 flags batch (integrated, batch scope only);
the EXP-028 dispatch specification (exp028_dispatch.py) which
already writes down the intended cross-architecture order,
including avx2-mb and shani-streams slots marked SPECIFIED,
UNVERIFIED. Greenfield: an AVX2 multi-buffer kernel (no AVX2
code exists in production today); a production SHA-NI search
backend (the streams kernel is research-only, and this VM's AMD
host has SHA-NI while the earlier Intel host did not, so
probe-first dispatch is mandatory, not optional); the kernel
registry refactor (component 3); a whole-miner benchmark that
measures search plus candidate extraction plus verification
end to end, as the directive requires, instead of kernel-only
rates; and the explicit investigation of whether the flags
approach improves the real search path, which Phase 6B
deliberately left open when it integrated flags for batch only.
Readiness: highest of the eight; the baseline, the measurement
stack and the decision rule all exist and are proven.

### EXP-033: Mathematical investigation

Builds on: the exact computation derivation and its corrections
(the 125-round figure is a conventional remainder, not a lower
bound; research/sha256d/phase6 records), EXP-016 nonce
dependency results (affinity dies at S_8; W20 is the first fully
nonlinear schedule word), the EXP-020 vocabulary optimum (28
vector ops per steady-state round within the searched
vocabulary, with an SMT lower bound in that vocabulary), the
EXP-027 closures (GFNI, shuffle rotations, carry-save beyond
the schedule, state representations, addition networks, each
closed with proofs at a stated scope), the z3 proof artifacts
under the three proofs directories, and the discovery harness
(phase6/src/discovery_harness.py, seed-validated by reproducing
EXP-012). Greenfield: the living mathematical notebook as a
maintained artefact rather than per-phase snapshots; the
machine-readable hypothesis registry (directive section 6
requires it; today both registries are Markdown); and a bounded
method for the one open space, non-sharing cross-round graph
restructuring, whose blocker is search-space size. Readiness:
the prior results are strong and unusually well evidenced; the
experiment's work is form (notebook, registry) plus one hard
open problem, and it should not re-open closed spaces without
new vocabulary evidence.

### EXP-034: Job and template engine

Builds on: MiningEngine (GBT acquisition, longpoll, candidate
construction), the EXP-025 repaired template cache (integrated
2026-11-15, independently audited PASS WITH NOTES, zero
defects; the adversarial standard this section demands is the
one it was integrated under), the solo server's job model (the
full template is retained server-side, which is what makes its
block reconstruction possible), and the Stratum client's job
validation and freshness guards. Greenfield: a
protocol-independent job model in which a job carries everything
needed to reconstruct and verify a candidate later (today the
three job representations are a GBT dict, a Stratum job dict
and a solo job dict, and only the solo one retains the full
template); persistent job records; job generation identifiers
shared across paths; template invalidation and cancellation as
defined operations rather than side effects; safe job
replacement semantics; and a version-rolling and
timestamp-rolling policy, which does not exist anywhere in
production today (see component 15). Readiness: the correctness
core (construction plus cache identity) is proven; the work is
unification and persistence, not new cryptography.

### EXP-035: Distributed CPU agent architecture

Builds on: EXP-029 in full: the design document's seven
mechanisms, the RangeAllocator prototype with its accounting
separations (unique coverage, actual computations, repeated
computations, verification computations, candidate submissions
kept distinct), the 120-trial randomised campaign proving exact
disjoint coverage under death, duplicate, steal and restart
injections, the measured local overhead record (labelled
prototype-only), and an end-to-end regtest block through the
allocator plus production ComputeEngine (height 829). Also the
default_worker hostname convention, which already gives every
agent a distinct Stratum identity. Greenfield: everything
networked and persistent: a coordinator process, a worker
protocol (the allocator is in-process only), lease transport
and expiry over a network, template propagation to real
workers, coordination overhead measurement on real links,
search-space expansion beyond the nonce (per-worker extranonce
space, merkle-root variation, permitted version rolling,
timestamp policy) with the directive's rule that duplicated
work never counts as unique coverage, and the coordinator-side
persistent state (the allocator's snapshot and restore exist,
but leases deliberately do not survive a restart in the
prototype, which a production design must confront). Directive
boundary, restated: design and controlled testing only; the
roughly 25 agents are not activated at this stage. Readiness:
the testable core is proven, which de-risks the design; the
engineering is entirely ahead.

### EXP-036: Exact candidate verification and block submission

Builds on: pow_engine.check_pow (the strict verifier, currently
test-only), MiningEngine's acceptance rule (submitblock None
plus best-block equality, the strongest acceptance semantics in
the tree), the solo server's submission path (full block
assembly from the retained template, submitblock exception
capture so a failed submission cannot lose the candidate
record), mainnet_live's confirmation block (independent hashlib
recompute, pool target and network target checks, freshness
check), and node/rpc_client.py. Greenfield: the twelve-step
pipeline as a distinct, testable stage that every path routes
through; a Bitcoin Core submission adapter that classifies
submitblock responses (accepted, duplicate, stale, invalid) and
verifies acceptance against chain state on the solo path, where
that verification is missing today (component 14); exact-integer
target handling on the live path, replacing the float-derived
pool target for any network-target decision (component 12); a
shared full-block constructor (component 13); and Stratum-side
handling that distinguishes an ordinary accepted share from a
network-target block candidate in the submission record itself,
not only in a log field. Readiness: every individual mechanism
exists somewhere in the tree; the experiment is assembly,
unification and hardening, and it is the cheapest of the eight
relative to its mission weight.

### EXP-037: Mining statistics and probability engine

Builds on: the Task 003.9 accounting vocabulary in gpu/engine.py
(the single best foundation any of these experiments has: the
category separations the directive demands are already defined
and enforced inside ComputeEngine stats); the append-only
evidence JSONL with a rich event set; research/probability.py,
which already implements exactly the directive's formulas
(expected hashes D times 2^32, expected time, and
P = 1 - exp(-R t / (D times 2^32))) but is orphaned: no
production code imports it, and it is referenced only by
README tables and a prose mention in mining/testnet4_attempt.py;
research/statistics.py (the lab's own hash-structure studies,
a different subject from operational statistics); the solo
server's per-worker counters; and the EXP-017 covariate and
bootstrap machinery for uncertainty. Greenfield: a statistics
engine as a component: one store joining the fifteen directive
categories across all paths, windowed and sustained hashrate
series, per-worker and per-backend series, the latency family
(verification, template construction, job distribution,
submission, worker recovery), result labelling (measured,
estimated, theoretical, simulated, unverified) enforced at the
reporting layer, live probability reporting wired to measured
rate and current network difficulty, and a fix for the
heartbeat tail-window share count named in component 16.
Readiness: vocabulary and formulas exist; the store, the series
and the wiring do not.

### EXP-038: Autonomous mining operations

Builds on: the autopilot (watchdog, hung detection, backoff,
session rotation, single-instance lock), the Stratum client's
reconnect loop, the solo JobRefresher's readiness gating, the
solo cutover script (preconditions, smoke test, verification,
automatic rollback: the most complete recovery sequence in the
repo), the systemd units, and the external keeper cron.
Greenfield: a startup self-test that runs before mining resumes
(node reachable and on the right chain, template obtainable,
payout valid, backend self-tests passed, evidence writable);
candidate recovery across restarts (with components 11 and 19);
work-state checkpoints that make restart semantics explicit
(resume, or abandon with the abandonment accounted, never a
silent restart-from-zero presented as continuity); resource
exhaustion guards (evidence growth, disk, memory); and a single
recovery policy document that the autopilot, the solo runner
and the cutover script all implement instead of each inventing
its own. Readiness: the pieces work in production today; the
experiment is consolidation plus the checkpoint and candidate
recovery mechanisms, which are genuinely new.

## 3. Top gaps, ranked by mission impact

1. **The block path is the least verified path (EXP-036).**
   The mission's success criterion is a discovered, verified,
   constructed and submitted block. The pool path cannot
   construct a block (component 13); the solo path can, but it
   accepts submission success from submitblock's return value
   alone, never verifies chain acceptance afterwards, validates
   shares with inline code rather than the strict verifier, and
   sits next to a live path whose pool target is float-derived
   (components 12 and 14). Every other path in the lab is held
   to a higher standard than the one that matters most. This is
   also the cheapest top gap to close: all mechanisms exist.

2. **No leases, no coordinator: scale has no substrate
   (EXP-035).** The gap model (research/sha256d/phase6b/
   PERFORMANCE_GAP_MODEL.md) puts 500 GH/s at roughly 24,000
   live-system equivalents at the observed DualMask rate.
   Nothing in production can divide work between two machines
   without risking identical header work (component 10), count
   unique coverage across them, or recover a dead worker's
   range. EXP-029 proved the allocator core in research; until
   EXP-035 builds on it, additional machines add heat, not
   coordinated coverage.

3. **No work-state checkpoints: restarts silently repeat work
   and lose candidates (EXP-038, EXP-037).** Coverage
   accounting is exact inside a process (Task 003.9) and
   meaningless across restarts: a restarted miner rescans from
   zero, a discovered candidate in memory vanishes, and no
   record separates repeated from unique work at the system
   level (components 11, 19, 20). On a VM that is replaced
   regularly, this is not an edge case; it is the normal case.

4. **Statistics are fragmented, and one headline number is
   already wrong by construction (EXP-037).** The heartbeat's
   accepted-share total counts only the last 2,000,000 bytes of
   a 2,185,778-byte evidence log (component 16), so the number
   the operation watches every five seconds excludes early
   shares and drifts further with every session. Windowed
   rates, per-backend series and all latencies are absent, so
   programme decisions rest on session averages and log archaeology.

5. **The programme cannot state what its own machine is
   (EXP-031).** Production dispatch knows two CPU features.
   Quota, affinity, steal and contention are unmeasured outside
   benchmark covariates, and the one probe that reports machine
   facts hardcodes this VM's topology as a string. Phase 6B's
   own lesson was that measurement variance on a contended
   guest is the binding constraint; EXP-031 is what turns that
   lesson into instrumentation. Every rate the programme quotes
   inherits this unknown until then.

6. **Portability is one host deep (EXP-032).** The verified
   kernel set covers AVX-512F+BW hosts. On anything else,
   production falls back to the C OpenSSL batch: the SHA-NI
   kernel exists but is not dispatched, and AVX2, the widest
   modern x86 coverage, has no kernel at all. The EXP-028
   dispatch specification already names the intended order;
   the kernels behind two of its slots do not exist.

7. **Three job models, no job identity (EXP-034).** GBT,
   Stratum and solo jobs share no identifier, no persistence
   and no invalidation semantics. EXP-035 leases and EXP-036
   immutable job recovery both presuppose a job that can be
   named, stored and reconstructed; that object does not exist
   yet, so EXP-034 is on the critical path of both.

8. **Registries are prose, in duplicate (EXP-032, EXP-033,
   EXP-037).** Two Markdown experiment registries with a
   recorded divergence incident, Markdown hypothesis registries,
   no manifest. The directive's quality requirements (section
   13 of the record) cannot be enforced or even checked
   mechanically until the registry layer is machine-readable.

## 4. Contradictions: what the tree says versus what it does

Findings where documents or code comments assert behaviour the
current tree does not have. Each was verified against the code
or the data on 2026-11-15.

1. **docs/ARCHITECTURE.md says mainnet is paused.** Decision 2
   states that all experiments run on regtest and that the
   Stratum code is "preserved under mining/ but paused by owner
   instruction", and the module map calls stratum_client.py a
   "paused mainnet experiment". The lab has mined live on
   mainnet since 2026-11-13; mining/mainnet_live.py is the
   flagship path and the autopilot supervises it. The
   architecture document describes a lab that stopped existing
   two days after it was written.

2. **evidence/SUMMARY.md denies the lab's own E3 evidence.** It
   states "No share has been accepted by a pool yet, so no E3
   claim is made anywhere in this repository." The evidence log
   in the same directory records 248 share_result events and
   the first pool-accepted share at 2026-11-13 18:59:51 UTC is
   documented in README.md and docs/EVIDENCE.md. The summary
   was never regenerated after the longrun session it describes.

3. **Rate figures in docs and README predate two integrations.**
   docs/HARDWARE.md gives the CPU aspect at "about 6.6M H/s end
   to end on this VM"; README's status section is dated
   2026-11-13 with a 5.18 MH/s live rate, and its 2026-11-14
   update covers the v512 integration but not DualMask (live
   sessions observed at 20.6M H/s after integration), the
   EXP-025 template cache, or the flags batch. A reader of the
   repo's front documents underestimates the production engine
   by roughly a factor of three.

4. **mining/mainnet_live.py describes a dispatch that no longer
   exists.** Its docstring says the ComputeEngine is "AVX-512
   multi-buffer where the CPUID probe confirms it, otherwise
   the C midstate batch". The actual order is CUDA, v512dual,
   v512, C, hashlib, with the flags batch inside batch_search.
   The file's own backend_selected evidence events contradict
   its header.

5. **The dashboard watches the wrong chain and denies itself.**
   dashboard/server.py titles itself a live dashboard for a
   "regtest node" and builds the default regtest RPC client; it
   displays nothing about the mainnet mining that is the lab's
   live operation. dashboard/status.py says Task 001 keeps a
   CLI snapshot "rather than shipping an untested web server",
   in the same package that ships dashboard/server.py.

6. **probe_machine.py reports this VM's facts as literals.** The
   topology_note and contention_note in
   research/sha256d/tools/probe_machine.py are hardcoded
   strings ("KVM guest; lscpu reports 4 cores x 1 thread",
   "capped near 1.5 effective CPUs"). The probe's purpose is to
   measure the machine it runs on; on any other host it would
   print this host's description. This is the exact failure
   mode EXP-031's unknown-as-unknown rule exists to prevent.

7. **The autopilot's self-update is presented as live and is
   inert here.** mining/autopilot.py documents self-update with
   smoke test and rollback as an operating feature. This
   checkout has no .git directory, so _git returns None,
   maybe_update returns silently on every check, and the
   heartbeat reports version "unknown". The feature is real
   code that cannot execute in the deployment it supervises.

8. **solo_server.py overstates its validator.** Its docstring
   says shares are "validated with the lab's own PoW engine".
   Validation is inline double SHA-256 from mining/pow.py;
   mining/pow_engine.py, the lab's strict from-specification
   PoW engine with Core-style reason codes, is called only by
   tests and scripts/milestone_003_006.py, never by any
   production path.

9. **Both experiment registries still point at EXP-030 as the
   next unreserved ID.** research/sha256d/experiment_registry.md
   (final line) and research/sha256d/extreme_optimization/
   EXPERIMENT_REGISTRY.md (final addendum) both state the next
   unreserved ID remains EXP-030. The 2026-11-15 directive
   reserves EXP-030 to EXP-038 and makes EXP-039 next. This is
   a known in-flight inconsistency (Phase A owns the registry
   update), recorded here so it is not mistaken for a settled
   state.

10. **A compiled binary sits at the repository root.**
    bal-miner is an ELF executable of the legacy C miner
    (mining/cpu/bal_miner.c command-line tool: bench, search,
    ranges), committed at the top level of the tree. No
    production path invokes it (production builds its libraries
    from source via mining/cpu/build.py into .local/cpu), and
    no document at the root explains its provenance or that it
    is a legacy artifact. It invites exactly the confusion the
    lab's evidence discipline exists to avoid.

11. **The production CPU engine lives in gpu/.** gpu/engine.py
    is the CPU mining execution engine for every live path;
    the GPU aspect proper is gpu/cuda. Documents that describe
    gpu/ as the GPU aspect (docs/HARDWARE.md, docs/ARCHITECTURE.md
    module map) mislead any new reader, human or agent, about
    where the production engine is. Organisational, but it has
    already cost audit time in this programme.

## 5. Audit limits

- This audit read production code, research code and docs; it
  ran no benchmarks and executed no test suite (Phase B scope).
  Statements about what code does are from reading it, not from
  running it, except where an existing test or audit record is
  cited.
- The keeper cron that supervises the autopilot, and the solo
  cutover watcher cron, live outside this repository (goal-owned
  scheduling). They are assessed here only as far as the repo
  itself reveals them, which is partially: scripts/solo_cutover.py
  is in the tree, the keeper's body is not.
- .local contents were inventoried by name only; no credential
  values were read.
- Phase A (reference repository audit) is running concurrently;
  nothing in this document depends on its findings, and the
  translation matrix may reprioritise the gaps in section 3
  when it lands.
