# Repository Reconciliation: NOVA SHA-X Extreme Research, Stage 0

Date: 2026-11-15. Method: direct source inspection of the local tree at
/home/hatch/workspace/bitcoin-autonomous-lab, plus a blob-sha diff against
the remote repository computed with the read-only local_files() and
remote_tree() helpers of the push tooling. No existing file was modified
by this audit. No benchmark was run. The live miner, autopilot and node
were not touched. Where this document disagrees with an earlier summary
or closing audit, the source and the diff are the authority.

## 1. Repository state

- Remote repository: kilomene/Bitcoin-Autonomous-Lab (public).
- Remote HEAD: 18ff4eb070a066dec4424cf9cd4d8282fa9a38b3 (Master Build push).
- Previous relevant commits:
  - 737e41c822b42bbb3abdaf775dc468cffaad9e3e (Master Assignment plus
    Phase 001 Genesis Engine, 79 files).
  - 3510daa47d426e7e235fe04cecce314eff8b376a (Phase 002, 145 files).
  - 18ff4eb070a066dec4424cf9cd4d8282fa9a38b3 (Master Build, 40 files).
- The local checkout has no .git directory. Pushes go through the
  contents API with blob-sha diffing.
- Branch: the remote default branch (main). There is no local branch
  concept; "uncommitted" means present locally and absent or different
  on the remote.

### 1.1 The exact uncommitted local delta

The blob-sha diff (971 comparable local files against 952 remote files,
0 remote-only files) shows 29 local files that differ from or are absent
on the remote:

Prompt 1 set (15 files, the Autonomous Mining Brain security work):

- MOD Makefile (adds test-agent-security; test-all is now 37 targets)
- MOD agent/intelligence/__init__.py
- MOD agent/intelligence/experiments.py
- MOD agent/intelligence/interface.py
- MOD agent/intelligence/loop.py
- MOD agent/intelligence/permissions.py
- NEW agent/intelligence/sandbox.py
- NEW agent/intelligence/verifier.py
- MOD docs/AGENT_CAPABILITIES.md
- MOD tests/test_agent_intelligence.py
- MOD tests/test_agent_operations.py
- NEW tests/test_agent_security.py
- NEW research/autonomous_brain/PROMPT1_SECURITY_AUDIT.md
- NEW research/autonomous_brain/PROMPT1_SECURITY_REAUDIT.md
- NEW research/autonomous_brain/PROMPT1_SECURITY_REPORT.md

Live churn (1 file):

- MOD evidence/mainnet-live.jsonl (the running miner's evidence log;
  it changes continuously and is excluded from push manifests by design)

Pre-existing binary artifacts (13 files, research build outputs that the
push filter excludes by extension; they predate the Master Build window):

- NEW research/sha256d/exp032/libbal_avx2.so
- NEW research/sha256d/exp032/libbal_h01.so
- NEW research/sha256d/exp032/libbal_v512fsearch.so
- NEW research/sha256d/exp041/src/libbal_e41alta.so
- NEW research/sha256d/exp041/src/libbal_e41altb.so
- NEW research/sha256d/exp041/src/libbal_e41altc.so
- NEW research/sha256d/exp041/src/libbal_e41base.so
- NEW research/sha256d/exp041/src/libbal_e41base_o2.so
- NEW research/sha256d/exp041/src/libbal_e41base_znver3.so
- NEW research/sha256d/exp041/src/libbal_e41tfull.so
- NEW research/sha256d/exp041/src/libbal_e41tfull_gate.so
- NEW research/sha256d/exp041/src/libbal_e41tmaj.so
- NEW research/sha256d/exp041/src/libbal_e41tmaj_gate.so

Nothing else differs. In particular, mining/, gpu/ (apart from the
artifacts above, which sit under research/), blockchain/, dashboard/,
scripts/, agent/autonomous.py and agent/interface.py are byte-identical
to remote HEAD 18ff4eb0.

## 2. Inventory

972 files on disk excluding .local/ and __pycache__/ (971 in the
comparable push set; the excluded file is the bal-miner binary at the
repo root). By top-level directory (excluding __pycache__):

- research/: 773 files (the bulk of the tree: experiment records, raw
  results, proofs, registries)
- tests/: 40 files (37 Python suites plus fixtures and 2 C harnesses)
- mining/: 30 files
- docs/: 28 files
- agent/: 18 files
- evidence/: 14 files
- scripts/: 12 files
- gpu/: 11 files
- results/: 11 files
- fpga/: 9 files
- blockchain/: 7 files
- asic/: 6 files
- node/: 4 files
- dashboard/: 3 files

Languages by extension: Python 229 (.py), C 47 (.c) plus 6 headers (.h),
CUDA 1 (.cu) plus 2 C++ (.cpp), Verilog 4 (.v) plus 2 compiled (.vvp),
shell 10 (.sh), systemd units 3 (.service), Markdown 208 (.md),
JSON 385 (.json, mostly raw results), JSONL 4 (.jsonl), text 12 (.txt),
logs 15 (.log), shared objects 30 (.so, build artifacts).

Research subdirectories under research/: architecture, autonomous_brain,
benchmarks, bitcoin_core, bitcoin_reverse_engineering, cpu_architecture,
cryptanalysis, experiments, formal_proofs, hashrate, master_build,
node_integration, nonce_search, phase001, phase_reports, probability,
proof_of_work, sha256d (with exp030 to exp043 subdirectories,
extreme_optimization, phase6, phase6b), and now EXTREME_RESEARCH.

## 3. Production mining call graph (traced in source)

### 3.1 Live pool mining path

Entry: mining/mainnet_live.py main() (line 126).

1. Worker name: --worker or mining.autopilot.default_worker() (the
   machine hostname, sanitised). Payout identity is
   address.worker on the lab wallet address.
2. Endpoint: mining.endpoint_config.resolve_endpoint() (environment,
   then .local/mining-endpoint.json, then public-pool.io:21496 default).
   Mode is "pool" in the staged config; mode "solo" points at the lab's
   own server and sets suggest_difficulty from the config.
3. Stratum: mining.stratum_client.StratumClient (connect, reader_loop
   thread, authorize wait 30 s, mining.notify job handling,
   mining.submit; optional on_share_result hook, default None).
4. Compute: gpu.engine.ComputeEngine() (see 3.2). The miner searches
   with engine.search_first_counted into the native search entry
   points, not through batch_search.
5. Candidate handling: on a hit, the header is re-verified exactly by
   mining.candidate_verify.verify_candidate (mainnet_live.py line 261)
   before submission; share results are recorded through the EXP-037
   statistics wiring (FrontierAccountant and SafeRecorder in
   mining/mining_statistics.py; client.on_share_result hook set at
   mainnet_live.py lines 195 to 200).
6. Evidence: JSONL events to evidence/mainnet-live.jsonl; periodic
   status events carry the separated statistics snapshot.

Supervision: mining/autopilot.py (499 lines). Single instance via
flock on .local/autopilot.lock; heartbeat to .local/heartbeat.json
every 5 s (HEARTBEAT_S); watchdog polls the miner child every 1 s;
hung window 300 s (STALE_S); crash backoff 1 s capped at 30 s; 24 h
session rotation; self-update check every 900 s (inert in this
checkout, no .git). EvidenceCounter (autopilot.py line 145) performs
the EXP-037 whole-log census with a persisted offset in
.local/evidence-count.json. On this VM the stack currently runs under
systemd units bal-autopilot.service and bal-bitcoind.service
(scripts/bal-autopilot.service, scripts/bal-bitcoind.service templates)
because shell-launched processes cannot write files in the current
runtime state; systemd-launched processes can.

### 3.2 ComputeEngine dispatch (gpu/engine.py, 2,818 lines)

ComputeEngine.__init__ (line 891) tries backends in this exact order,
each gated by a runtime probe and a hashlib self-test, cascading on
any failure:

1. CUDA (gpu/cuda shared library, context API bal_cuda_ctx_*). No GPU
   exists on this VM; never selected here.
2. v512dual: mining/cpu/bal_avx512_dual.c, library entry points
   bal_vd_batch2 and bal_vd_search2. Requires AVX-512F plus AVX-512BW
   via the flag-free probe mining/cpu/bal_avx512_probe.c and a
   256-nonce hashlib self-test.
3. v512: mining/cpu/bal_avx512_mb.c, bal_v_batch2 and bal_v_search2.
4. shani: mining/cpu/bal_shani_streams.c plus bal_shani_core.h
   (EXP-039 tier, H-01 multi-stream at streams 4), bal_m_batch2 and
   its counted search entry. Gate: flag-free probe
   mining/cpu/bal_fallback_probe.c (__builtin_cpu_supports).
5. avx2: mining/cpu/bal_avx2_mb.c (EXP-039 tier), bal_a_batch2 and
   bal_a_search2.
6. C: mining/cpu/bal_batch.c, bal_c_batch and bal_c_search2.
7. Python hashlib fallback.

Pin semantics: a pinned request only cascades downward through its
own tier list; v512 and v512dual pins never enter the shani or avx2
tiers; the new EXP-039 tiers join "auto" and their own pins.

Flags batch path (EXP-022): after search selection, if the request is
auto, v512 or v512dual, _try_v512flags loads
mining/cpu/bal_avx512_flags.c (entry point bal_v_batchf2 only; the
library exports no search entry point). It serves batch_search
routing only (via _vf_batch_flagged) and never changes the search
backend. On any flags failure the materialised batch path is used.

Thread count: module-level C_THREADS global (gpu/engine.py lines 223
to 297), set by BAL_C_THREADS or by the tune_*_threads probe
functions. This shared mutable global is a known defect carried into
the Autonomous Mining Brain Prompt 4 scope.

Build: mining/cpu/build.py compiles each kernel translation unit
with restricted flags only (AVX-512: -mavx512f -mavx512bw; AVX2:
-mavx2; SHA-NI: -msha -mssse3; probes flag-free), never -march=native
for those units. See discrepancy D7 for the legacy exception.

### 3.3 GBT engine path (mining/engine.py, 831 lines)

MiningEngine (line 464): getblocktemplate via node RPC
(get_template, wait_template with longpoll), TemplateFamily and
PreparedTemplate construction, mine_cycle (line 661), submitblock,
and acceptance counted only when the submitted block equals the
best-chain tip (lines 756 to 770). The GBT cycle does NOT call
verify_candidate internally; exact verification on this path is
submitblock plus best-chain equality, with the EXP-036 verifier
available as an external wrap (demonstrated in Master Build
Milestone 6).

Template cache (EXP-025, integrated): TemplateCache (line 434),
bounded at 128 entries, keyed by the layered dsha256 identity built
in template_identity (line 313): family_key (payout address,
scriptPubKey, chain, halving interval), tx_key (transaction count
plus per-transaction (txid, wtxid, fee) in order plus the default
witness commitment string), coinbase_key, header_key. Default
use_template_cache=True; build_candidate_uncached (line 579) is the
preserved fallback; MiningEngine(use_template_cache=False) disables
the cache. Note N-2 boundary: the steps path holds the template by
reference without re-verification between steps; mintime and curtime
are read live per build and are deliberately outside the identity.

Extranonce space (EXP-034): MiningEngine extranonce_space=(first,
count), default (0, 64), validated at construction; out-of-range
spaces are refused.

Checkpointing (EXP-038): optional checkpoint_path (default None)
backed by mining/work_checkpoint.py; the frontier (extranonce,
nonce) advances only after a batch returns without a hit.
agent/autonomous.py is the only production caller that enables it
(.local/work-checkpoint.json).

Statistics (EXP-037): optional statistics parameter (default off);
a FrontierAccountant records searches, candidates and submission
outcomes into separated counters; snapshot() has no combined total.

### 3.4 Solo path

mining/solo_server.py (635 lines): SoloServer serves Stratum jobs
built from the node GBT. refresh_job (line 228) locates the
extranonce split in the STRIPPED coinbase (line 270,
stripped.index(marker); the EXP-034 fix for the witness-commitment
offset defect). validate_share and submit_share (lines 302, 351)
route candidates through verify_candidate, classify_submit_result
and verify_chain_acceptance from mining/candidate_verify.py.
mining/solo_mainnet.py is the solo runner; scripts/solo_cutover.py
(check, fire, rollback, status) owns the armed pool-to-solo switch,
guarded by .local/solo-cutover.json; scripts/bal-solo.service is
installed at fire time. Share difficulty is fixed (0.02 in the
staged endpoint config); vardiff (register row R-12) is a decided
design with no production implementation.

### 3.5 Candidate verification (EXP-036, integrated)

mining/candidate_verify.py (203 lines): verify_candidate requires
hashlib and pure-Python agreement, then pow_engine.check_pow
(integer verdict, Core SetCompact semantics). There are no float
operations in the file. classify_submit_result treats a solo
submitblock None as processed, not accepted; acceptance requires
verify_chain_acceptance (best-chain confirmation). Both the pool
path (mainnet_live.py) and the solo path (solo_server.py) route
candidates through verify_candidate. target_for_difficulty exists
in both mining/mainnet_live.py and mining/stratum_client.py and is
a pool share criterion only, never a consensus test.

### 3.6 Bitcoin Core integration points

- node/node_manager.py: bitcoind lifecycle for the regtest node
  (setup, start, stop, status) against the pinned Core 28.1
  binaries.
- node/rpc_client.py and node/peer_node.py: RPC transport and the
  second peered regtest node.
- mining/engine.py: GBT, submitblock, best-chain reads.
- mining/solo_server.py: GBT plus submitblock through the same RPC
  seam.
- The pruned mainnet node (datadir .local/mainnet, RPC 8332) is read
  by the agent awareness layer (getblockchaininfo only) and by the
  solo cutover preconditions.
- blockchain/ (store.py BlockStore on SQLite WAL, analysis.py,
  monitor.py, service.py, transactions.py, watch.py): the
  Blockchain Intelligence Engine, fed by Core RPC.

### 3.7 Block-template, transaction and Merkle construction

In mining/engine.py: build_coinbase (line 119) constructs the
coinbase with height, value and extranonce; strip_witness,
txid_of and wtxid_of (lines 75 to 117) handle segwit separation;
PreparedTemplate.root_with_coinbase (line 375) recomputes the
Merkle root per extranonce from the cached branch structure, which
is the EXP-025 amortisation point; the witness commitment comes
from the template's default_witness_commitment. In
mining/solo_server.py: attach_witness (line 67) and merkle_branch
(line 87) build the served job's coinbase parts and branch.

## 4. Agent intelligence architecture (agent/intelligence/)

Fourteen modules plus __main__:

- permissions.py (269 lines): Level IntEnum L1, L2, L3; the
  ACTION_REGISTRY holds 22 ActionSpecs (verified live in this
  audit: 11 L1 operational, 8 L2 operational, 3 L3 experimental).
  Every spec carries a kind and shell=False (Prompt 1). Unknown
  operations are refused; L3 is contained to the sandbox root.
- audit.py (105 lines): append-only JSONL audit log, one os.write
  per record on an O_APPEND descriptor; failures counted, never
  raised.
- memory.py (316 lines): ResearchMemory parses the two markdown
  registries plus the EXP-033 JSON into 98 indexed entries
  (verified live in this audit: EXPERIMENTAL 46, REJECTED 19,
  PROVEN 32, UNDER_INVESTIGATION 1, INTEGRATED 0; 0 unparsed, 0
  missing sources). See discrepancy D6.
- planning.py (230 lines): TaskRegistry with the mandate task
  fields, a transition map, a dependency gate, and a done gate
  that refuses until required evidence is supplied. Persisted by
  temp file plus os.replace.
- interface.py (488 lines): typed dataclass requests and
  responses; MiningInterface with inspect_status, inspect_machine,
  inspect_backends, verify_candidate_op, estimate_probability,
  select_backend, checkpoint_status, and start_mining/stop_mining
  as L2 specs executed only through an injectable controller
  whose default raises NotImplementedError. Prompt 1 added the
  shell-payload guard (assert_no_shell_payload) on this surface.
- strategy.py (141 lines): TARGET_MIN_HS = 500e9 and
  TARGET_LARGE_HS = 140e12 constants; gap_report;
  next_investigations excluding REJECTED and INTEGRATED entries;
  bottleneck_summary with cited source files.
- loop.py (433 lines): the 15-state optimisation loop (observe to
  monitor, plus rolled_back and failed). Prompt 1 replaced the
  loose _passed() truthiness check with a strict evidence schema
  (passed exactly Boolean True, verifier_id, artifact_sha256,
  source_commit, verification_method from a closed allowlist,
  ISO-8601 timestamp) plus HMAC signature verification against
  the verifier service key, bundle artifact and commit binding,
  and EXP-017 validation that rejects NaN, infinity, inverted CI,
  non-integer sessions and ci_low at or below 0.
- awareness.py (804 lines): live mining awareness (heartbeat,
  EvidenceCounter census, miner status file, evidence tail,
  bounded read-only getblockchaininfo, endpoint mode), rate
  observation over a real window, degradation checks with named
  evidence, coverage report, observe_cycle writing to the audit
  log and the standing L1 task.
- experiments.py (604 lines): ExperimentRunner. Prompt 1 rewired
  run_command through sandbox.py, added strict evidence assembly
  and the append-only hash-chained evidence ledger under
  .local/agent-evidence/ with verify_ledger() and an HMAC-signed
  anchor file; CURRENT_SOURCE_COMMIT is bound into every record
  (currently 18ff4eb070a066dec4424cf9cd4d8282fa9a38b3).
- sandbox.py (605 lines, NEW in Prompt 1): the experiment sandbox.
  systemd-run scope plus unshare mount, net and pid namespaces; a
  new root built on tmpfs and pivot_root; only /usr and /etc bound
  read-only, a fresh procfs (mount failure is fatal), a minimal
  /dev, a tmpfs /tmp, a read-only /source snapshot of the repo
  with an empty .local, and /work as the only writable persistent
  location. Payload runs as uid/gid 65534 after rlimits are
  applied. A runner-side watchdog polls tree RSS and task count
  every 0.2 s because cgroup limits do not enforce on this VM
  (measured: about 4 GB allocated under MemoryMax=128M).
- verifier.py (257 lines, NEW in Prompt 1): the independent
  verifier service, a separate process
  (python3 -m agent.intelligence.verifier) that recomputes the
  artifact SHA-256 itself, re-runs declared differential commands
  inside the sandbox, checks vectors against the hashlib SHA-256d
  reference, and emits the strict evidence record signed with
  HMAC-SHA256. Key at .local/verifier/verifier.key, mode 0600.
- scheduler.py (357 lines): MachineProfile, effective-CPU probe,
  and bake_off() measuring every eligible tier through the real
  ComputeEngine search path (category E), winner cached to
  .local/agent-scheduler.json. Advisory only: it changes no
  production dispatch. Its _measure sets and restores the
  gpu.engine C_THREADS global (known defect, Prompt 4 scope).
- resources.py (334 lines): exact local ResourceRegistry
  (register_worker, assign with overlap refusal inside a job
  identity and extranonce space, complete only when
  batches_completed equals batches_total, reassign preserving
  the completed frontier, unique_coverage as interval union).
  Single-machine only; no wire protocol.
- __init__.py (105 lines): the Agent facade wiring checker,
  memory, registry, interface, loop, awareness, runner,
  scheduler and resources; grants L3 with the sandbox root at
  .local/agent-experiments; Prompt 1 wires verifier_key_path
  into the loop.
- __main__.py (55 lines): CLI with status and awareness
  subcommands.

Outside the package: agent/autonomous.py (127 lines) is the older
deterministic supervisory miner (fixed mine_cycle loop, one
hard-coded batch-size rule); it is the only production caller of
the EXP-038 checkpoint. agent/interface.py (177 lines) is a
separate read-only RPC question layer that AutonomousMiner never
calls.

## 5. Test suites, benchmarks, build

Makefile test-all lists 37 targets in the local (uncommitted)
Makefile: test, test-regtest, test-engine, test-pow, test-gpu,
test-gpu-correction, test-mining, test-adversarial, test-deepening,
test-cpu, test-cpu-correction, test-rtl, test-solo,
test-solo-cutover, test-research, test-autopilot, test-judgement,
test-installer, test-task003, test-task0038, test-task0039,
test-avx512, test-avx512dual, test-mainnet-live,
test-template-cache, test-avx512flags, test-exp036, test-exp034,
test-exp037, test-exp038, test-probability, test-exp039,
test-exp040, test-agent-intelligence, test-agent-awareness,
test-agent-operations, test-agent-security. At remote HEAD the
count is 36 (no test-agent-security). Standing environment
failures: test-rtl (iverilog absent after VM replacements);
on the SHA-less Intel host, test-cpu-correction and test-task003
also SIGILL. The last full run on record (Master Build) was
35 of 36 passing, with test-task0039 passing on its single
permitted rerun after a borderline contention threshold failure.

Benchmark programs: gpu/benchmark.py; research harness drivers
under research/sha256d/exp032, exp039, exp040 (category_f.py),
exp041, exp043; the EXP-017 protocol implementation used across
the programme (paired 65,536-hash blocks, randomised AB/BA order,
adjusted bootstrap CI). Makefile bench target runs the legacy
bal-miner bench. There is no category A harness and, before
EXP-040, there was no category F benchmark; EXP-040 closed the
category F gap for the GBT pipeline only.

Build configuration: Makefile (gcc, the legacy bal-miner target
uses -O3 -march=native for mining/cpu/bal_miner.c, a standalone
binary, not a production library); mining/cpu/build.py for the
production shared libraries (restricted flags, see 3.2);
gpu/cuda/build.py for the CUDA library. No CI configuration
exists in the tree; the standing discipline is local build and
test, then a single push.

## 6. Claims this audit could NOT confirm, or that disagree with the source

D1. Test count drift (local only). README.md (lines 55, 221, 227)
and docs/EVIDENCE.md (line 5) state make test-all has 36 targets.
The current local Makefile lists 37, because the unpushed Prompt 1
change added test-agent-security without updating README or
EVIDENCE. At remote HEAD 18ff4eb0 the documents and the Makefile
agree at 36. The drift exists only in the uncommitted state and
will ship if the Prompt 1 set is pushed as-is.

D2. Stale registry reservation block.
research/sha256d/extreme_optimization/EXPERIMENT_REGISTRY.md, in
its EXP-030 to EXP-038 reservation block, still states that
EXP-030 is IN PROGRESS with only Phase A executed, that EXP-031
to EXP-038 are RESERVED and not started, and that the next
unreserved ID is EXP-041. Later records in the same file record
EXP-031 to EXP-038 complete and the next unreserved ID as
EXP-044. The reservation block was never updated; a reader of
that block alone gets a false state.

D3. Stale Phase 001 hypothesis table.
research/phase001/MATHEMATICAL_OPTIMIZATION_HYPOTHESES.md lists
H-8 as "Open as engineering" and H-9 as "Open as integration
decision". Phase 002 closed H-8 as an ESTABLISHED NULL (EXP-041:
the 28-op forms are not significantly faster) and EXP-024b
verified H-9's design C as a certified single-batch fallback
(still not integrated). The Phase 001 table predates Phase 002
and was not updated.

D4. EXP-011 has no surviving raw evidence. The registry records
that the raw session A JSON behind the EXP-011 dual-batch figure
(8,267,078 H/s in one session) was overwritten. The figure is
transcription only, was never reproduced, and is excluded from
the verified rate table in research/hashrate/. Any citation of
it as a measured result overstates the evidence.

D5. Two verified records disagree on the AVX2 rate. EXP-032
measured the AVX2 multi-buffer batch at pooled 1.409x
[1.340, 1.480] against production C; EXP-039 measured the
byte-identical kernel at pooled 1.252x [1.185, 1.322] under the
same EXP-017 protocol. The confidence intervals do not overlap.
Both records stand; the discrepancy is unresolved (recorded as
EXP-039 audit note N-2) and changes no verdict, but the two
numbers cannot both describe the same conditions.

D6. The research memory cannot see INTEGRATED status. Verified
live in this audit: ResearchMemory indexes 98 entries with 0
INTEGRATED (EXPERIMENTAL 46, PROVEN 32, REJECTED 19,
UNDER_INVESTIGATION 1), because integration facts live in
narrative addenda rather than verdict lines the parser reads.
Documents describing strategy.next_investigations as excluding
already-integrated work by status therefore describe behaviour
the code cannot deliver today: integrated work parses as PROVEN
or EXPERIMENTAL and can be re-proposed. The gap is disclosed in
the Master Build records; it is still present in current source
and is Prompt 3 scope in the Autonomous Mining Brain mandate.

D7. The "never -march=native" build claim has a legacy exception.
mining/cpu/build.py compiles the AVX-512, AVX2, SHA-NI and probe
units with restricted flags, but its shared legacy _compile
helper (line 151) still builds the older C batch library and the
SHA-NI intrin library with -march=native. Blanket statements
that production libraries are never built with -march=native
are inaccurate for those two legacy libraries (also recorded as
EXP-039 audit note N-3).

D8. The awareness suite has no fixed check count.
research/master_build/MILESTONE2_LIVE_AWARENESS.md reports the
suite as 50 checks; the Master Build full-suite run printed 51.
The count is 50 or 51 depending on whether the node RPC answers
during the run (one check is conditional on a live
getblockchaininfo). Any flat count quoted for this suite is
imprecise; the Prompt 1 report carries a dated correction, the
Milestone 2 document itself still says 50.

D9. Cosmetic mislabel in the live miner's backend line.
mining/mainnet_live.py (lines about 175 to 183) labels the
backend reason "AVX-512 MB" and reads desc["v512_reason"] for
every backend that is not v512dual, including shani, avx2 and C.
On a host where a fallback tier is selected, the session log
line would misname the reason source. It does not affect
selection or accounting; it is a logging defect found by
inspection. Status: FIXED 2026-11-16 (Stage 6, item 1): the
session line now takes its label and reason from a
backend_reason helper that reads the selected backend's own
probe record; see research/sha256d/phase6b/
PRODUCTION_INTEGRATION_LOG.md, Entry 4.

D10. Solo share difficulty is stated two ways. The SoloServer
constructor default in mining/solo_server.py is
share_difficulty=0.01 (line 107), while the staged endpoint
config and register row R-12 describe the fixed solo share
difficulty as 0.02. The running solo leg takes its value from
the endpoint config, so 0.02 is the operative figure; the
constructor default is a latent inconsistency, not the live
value. Status: FIXED 2026-11-16 (Stage 6, item 2): the
constructor default is removed; with no explicit difficulty
and no vardiff controller, SoloServer now resolves its share
difficulty from the endpoint config
(mining/endpoint_config.py, SOLO_SHARE_DIFFICULTY = 0.02),
which is the single source; see research/sha256d/phase6b/
PRODUCTION_INTEGRATION_LOG.md, Entry 5.

## 7. Standing limitations recorded by this audit

- No mainnet block has been found. Balance 0 BTC. The success
  criterion (a real, independently verified, submitted and
  accepted mainnet block) is not met. Pool shares (446 accepted,
  8 rejected at the last census available to this audit) are
  evidence of correct work, not of block discovery.
- The targets stand at full height: 500 GH/s minimum and
  140 TH/s long-term. The best verified live rate basis is about
  20 to 25 MH/s on this VM, a gap of roughly four orders of
  magnitude to the minimum target (about 20,000 to 24,000 such
  systems at the live basis).
- Multi-machine coordination overhead, real-network propagation
  latency, cross-machine scaling, the production wire protocol
  and the persistent coordinator remain UNVERIFIED or unbuilt
  (EXP-043 closed only the in-process and loopback parts).
- EXP-039 tier refusal on the SHA-less Intel host and on an
  AVX2-only host is established by probe construction, not by
  execution on that hardware.
- Category F end-to-end cost is measured only for the GBT
  pipeline at regtest difficulty; the solo and pool pipelines'
  full end-to-end cost is unmeasured.
- The Prompt 1 file set is uncommitted and unpushed, and its
  final clean sequential suite rerun (test-agent-security,
  test-agent-operations, test-agent-awareness) is still owed:
  the re-audit's own rerun was destroyed by the runtime write
  fault, not by a code failure.
