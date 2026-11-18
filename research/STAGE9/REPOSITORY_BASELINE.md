# Stage 9 Repository Baseline

Stage: 9.1 (repository and experiment closure). Date: 2026-11-18.
Method: direct inspection of the local checkout at
~/workspace/bitcoin-autonomous-lab plus read-only GitHub API calls
(git refs and commits endpoints, connector surrogate credentials,
no writes). No file outside research/STAGE9/ was modified by this
audit. The live miner, autopilot, mainnet node, wallet and live
endpoint configuration were inspected read-only and not changed.
No benchmark or test suite was run in this stage.

## 1. Exact repository state

- Remote: https://github.com/kilomene/Bitcoin-Autonomous-Lab
  (public), default branch main.
- Remote HEAD at audit time: 883cf281be6c41617f27b8b44d1aa27e3c94df29
- HEAD parent: eca3a641311a98b3ed58065ad5f2ee23523475c5
- HEAD commit: dated 2026-11-18T02:36:38Z, message "Bitcoin
  Autonomous Lab: update
  research/sha256d/exp057/RAW_RESULTS/gate6_20261117T161245Z.json"
  (a single-file contents-API commit, the shape every commit in
  this repository has, because pushes go through the contents API,
  one file per commit).
- Remote tree at HEAD: 1,366 blobs (recursive tree fetch, not
  truncated).
- Last deliberate, audited push HEAD:
  11277e6f532a48844be5c9f33aa8ef6a755683c2 (NOVA-ER-0006, register
  R-30). It sits exactly 18 commits behind the current HEAD.
- The 18 intervening commits are churn, not development: every
  one is a single-file update of a runtime-generated path, namely
  research/sha256d/exp055/RAW_RESULTS gate5_state and gate6_state
  files and gate6 result JSONs (13 commits),
  research/sha256d/exp057/RAW_RESULTS gate5_snapshot.json and
  gate6 result JSONs (4 commits), and evidence/mainnet-live.jsonl
  (1 commit). They came from one accidental unscoped run of the
  push helper (~/workspace/bin/bal_github.py, invoked on a help
  probe) after the deliberate push. No production source file
  changed in any of the 18 commits. They are recorded here for
  what they are; nothing in Stage 9.1 depends on their content.
- The local checkout has no .git directory. There is no local
  branch, stash or index. "Working tree state" therefore means
  the file tree itself, compared by git blob sha against the
  remote tree (the same comparison the push tooling performs).
- Push view of the local tree (the bal_github local_files()
  definition: excludes .local, .git, __pycache__ directories and
  the bal-miner binary): 1,369 files, of which 3 are the new
  research/STAGE9/ files created by this stage. The remaining
  1,366 match the remote blob count exactly. Content differences
  against the remote are confined to the sanctioned churn set
  (evidence/mainnet-live.jsonl, exp055 and exp057 RAW_RESULTS
  runtime files, exp032/exp041/exp044 build artifacts,
  __pycache__), which the scoped push drivers exclude by design.
- Host at audit time: AMD EPYC 9D25, 4 vCPUs claimed (about 2
  effective), AVX-512F/BW/CD/DQ/VL/IFMA/VBMI, SHA-NI, AVX2.

## 2. Working-tree inventory

Inventory method: recursive file walk of the checkout.

- Files on disk, total: 18,021 (dominated by .local runtime data:
  node datadirs, built libraries, logs).
- Files excluding .local: 1,503.
- Files excluding .local and every __pycache__ directory: 1,367
  at inventory time, before this stage added its deliverables
  under research/STAGE9/.
- Push view by top-level directory (1,369 files including the 3
  new Stage 9 files): research 1,143; tests 55; mining 39;
  docs 28; agent 22; evidence 14; scripts 12; gpu 11;
  results 11; fpga 9; blockchain 7; asic 6; node 4; dashboard 3;
  root files 5 (.gitignore, CONTRIBUTING.md, LICENSE, Makefile,
  README.md).
- Top-level structure: agent/ (agent control), asic/ (pre-layout
  package), blockchain/ (chain analysis), dashboard/, docs/,
  evidence/, fpga/ (RTL), gpu/ (compute engine and CUDA),
  mining/ (production mining), node/ (node management),
  research/ (all research programmes), results/, scripts/,
  tests/, plus the bal-miner binary at the root (a build output,
  excluded from pushes).

## 3. Production mining call graph

Entry points and supervision (all verified in current source):

1. mining/autopilot.py (571 lines) is the supervisor. It takes a
   single-instance flock on .local/autopilot.lock (a second
   starter is refused and the refusal is incident-coded 2004),
   spawns the miner child as a subprocess
   ([sys.executable, mining/mainnet_live.py, ...], start_child,
   incident 1003), writes .local/heartbeat.json every 5 s
   (heartbeat includes incident_counts from the R-30 ledger),
   polls on a 1 s watchdog, kills and relaunches a miner whose
   evidence goes stale past the 300 s hung window (incident
   1002), relaunches an exited miner under backoff (incident
   1001), honours the operator stop file (incident 2003), and
   runs the self-update check (incidents 3001 to 3004; inert on
   this checkout because there is no .git). Incident emission is
   additive and defensive: mining/incident_codes.py is imported
   under a guard and a missing registry degrades to plain logs.
2. mining/mainnet_live.py is the live miner. Startup order in
   main(): resolve the worker name (mining.autopilot
   default_worker), resolve the endpoint via
   mining/endpoint_config.resolve_endpoint (mode from
   .local/mining-endpoint.json, currently pool), build the
   endpoint health policy object only if the config enables it
   (mining/endpoint_health.EndpointHealthPolicy, shipped default
   enabled=false), then the bake-off step: only if the bakeoff
   config section is enabled (shipped default enabled=false, and
   the live config carries no bakeoff section) it calls
   mining/bakeoff_dispatch.resolve_requested and logs the result;
   then it constructs gpu.engine.ComputeEngine(requested=...).
   The search loop receives stratum jobs, reconstructs the
   header, calls mining.candidate_verify.verify_candidate
   (EXP-036) on every hit before any submission, records through
   mining/mining_statistics (FrontierAccountant and the EXP-037
   counters, which also key the 4001 to 4003 incident codes),
   and submits shares through the stratum client.
3. gpu/engine.py ComputeEngine is the hash kernel dispatch. The
   documented and implemented tier order is: cuda (compiled
   gpu/cuda/engine.cu library, only when present and passing its
   candidate-path self-test; no GPU exists on this host, so this
   tier never selects here), v512dual (AVX-512 DualMask,
   mining/cpu/bal_avx512_dual.c, EXP-026), v512 (AVX-512 16-way
   multi-buffer, mining/cpu/bal_avx512_mb.c), shani (SHA-NI
   multi-stream, mining/cpu/bal_shani_streams.c on the H-02 core,
   EXP-039), avx2 (AVX2 8-way multi-buffer,
   mining/cpu/bal_avx2_mb.c, EXP-039), C (the production C batch
   backend, mining/cpu/bal_miner.c lineage), hashlib (pure
   Python fallback and correctness reference). Every native tier
   is gated by a CPUID probe and a hashlib digest self-test; any
   failure degrades loudly to the next tier. The EXP-022 flags
   batch (mining/cpu/bal_avx512_flags.c) hangs off the AVX-512
   tiers for the batch path only; it is not a search tier.
4. GBT path: mining/engine.py MiningEngine obtains work with
   getblocktemplate (longpoll via wait_template), builds
   candidates through the EXP-025 layered template cache
   (TemplateFamily, PreparedTemplate, template_identity;
   identity recomputed from scratch on every serve), steps
   extranonces inside the EXP-034 job space, checkpoints exact
   completed work through mining/work_checkpoint.py (EXP-038,
   GBT path only), and searches through the same ComputeEngine.
   mining/prefetch.py (EXP-051) is imported here as an opt-in
   feed (use_prefetch, default off).

Candidate submission paths:

- Pool (live): mining/stratum_client.py StratumClient
  (subscribe, authorize, notify handling, build_header,
  submit(job, extranonce2, nonce)); the client also carries the
  EXP-050 policy hooks (_policy_note_error, _policy_note_success,
  _maybe_failback, _probe_endpoint) which are inert while the
  policy is disabled. A share is submitted only after
  verify_candidate accepts the reconstructed header against
  POW_LIMIT_MAINNET and the share target; pool shares, network
  target candidates and accepted blocks are separate counters
  (EXP-037).
- Solo: mining/solo_server.py SoloServer (1,222 lines) serves
  stratum to local workers against the lab node, validates every
  share, and submits blocks through _submit_block;
  mining/solo_mainnet.py is its mainnet driver.
  mining/candidate_verify.py (verify_candidate,
  classify_submit_result, verify_chain_acceptance) is the single
  exact verifier: integer-only target comparison, full SHA-256d
  recomputation, and chain-membership confirmation after
  submission. The solo server is not the live path while the
  endpoint mode is pool.

Modules built but NOT on any live call path (verified by import
scan of mining/*.py, agent/*.py, agent/intelligence/*.py and
gpu/*.py at audit time): mining/coordinator.py (EXP-055),
mining/aggregation.py (EXP-057), mining/pid_control.py
(EXP-058). Nothing in the live tree imports them.

## 4. Agent control path

- agent/autonomous.py: AutonomousMiner (127 lines), a regtest-era
  autonomous miner that decides through a permission-gated
  interface over node RPC (agent/interface.py AgentInterface:
  chain inspection, block analysis, generate_blocks on regtest).
- agent/intelligence/ is the Directive 4 brain package:
  controller.py MiningController (703 lines) is the operational
  controller over the live stack (inspect, status, start, stop,
  restart, checkpoint, classify_fault, recover; its
  select_backend and refresh_job operations are honest refusals,
  recorded as unsupported, because backend selection lives in
  mainnet_live.py construction and job supply is push-driven
  inside the miner). loop.py OptimisationLoop is the research
  loop with evidence validation and an independent verifier
  signature gate before integration. Supporting modules:
  awareness.py, planning.py, strategy.py, experiments.py,
  integrations.py (writes the derived integration registry),
  permissions.py, sandbox.py, verifier.py, audit.py, memory.py,
  modes.py, resources.py, scheduler.py, interface.py.
- The keeper that restarts the autopilot and the node from
  outside the repository is not repo code; its incident class
  (2005) is registry-only in mining/incident_registry.json.

## 5. Node configurations

Mainnet (live):

- Bitcoin Core 28.1, binaries at
  ~/workspace/bitcoin-core-dist/bitcoin-core-28.1/bin/ (outside
  the repo). Datadir .local/mainnet inside the checkout.
- .local/mainnet/bitcoin.conf (mode 600): server=1, prune=550,
  rpcport=8332, rpcbind=127.0.0.1, rpcallowip=127.0.0.1,
  maxconnections=12, listen=0, plus a fixed set of connect=
  peers. Credential values are not printed here; they live in
  that file and in .local/mainnet/node-config.json (mode 600,
  keys rpc_user, rpc_password, rpc_port 8332, chain main).
- State at audit start (context, read-only): node in initial
  block download at about height 470,267 of 976,342 headers,
  progress about 0.1495, pruned. The node was restarted on owner
  order shortly before this audit (pid 24493 at audit start).

Regtest (isolated, not live):

- node/node_manager.py manages a regtest node with datadir
  .local/regtest, RPC port 18443, config generated into
  .local/regtest/data/bitcoin.conf with a [regtest] section;
  credentials in .local/regtest/node-config.json.
- node/peer_node.py manages a second peered regtest node at
  .local/regtest2. scripts/regtest.sh is the start, stop and
  status wrapper. Stage 8 used an additional isolated instance
  under .local/stage8.

Live endpoint configuration:

- .local/mining-endpoint.json (mode 600): mode "pool", pool
  public-pool.io:21496, solo 127.0.0.1:3333 with share
  difficulty 0.02, payout address
  bc1q528egeqsvv8aa382j43edxskqw6x7zxc2xpcf3. Untouched by this
  audit. mining/endpoint_config.py holds the shipped defaults:
  SOLO_SHARE_DIFFICULTY 0.02, and the vardiff, pool-health,
  prefetch-adjacent and bakeoff sections all default to
  enabled=false.

Live stack at audit start (context only): autopilot pid 2306,
miner pid 2309, shares accepted total 1,040 (heartbeat at
2026-11-18T02:40:02Z, incident_counts {1003: 1, 2001: 1}).
No mainnet block has been found; balance 0 BTC.

## 6. Test inventory and CI status

- The Makefile defines 57 targets. Test entry points: 52 (the
  plain test target, 50 named test-* suites, and the test-all
  aggregator). test-all aggregates 51 prerequisites (test plus
  the 50 named suites); every prerequisite is a defined target.
- The 50 named suites: test-regtest, test-engine, test-pow,
  test-gpu, test-gpu-correction, test-mining, test-adversarial,
  test-deepening, test-cpu, test-cpu-correction, test-rtl,
  test-solo, test-solo-vardiff, test-solo-cutover, test-research,
  test-autopilot, test-judgement, test-installer, test-task003,
  test-task0038, test-task0039, test-avx512, test-avx512dual,
  test-mainnet-live, test-template-cache, test-avx512flags,
  test-exp034, test-exp036, test-exp037, test-exp038,
  test-exp039, test-exp040, test-exp049, test-exp050,
  test-exp051, test-exp052, test-exp053, test-exp054,
  test-exp055, test-exp056, test-exp057, test-exp058,
  test-probability, test-agent-intelligence,
  test-agent-awareness, test-agent-operations,
  test-agent-security, test-agent-controller, test-stage8,
  test-incident-codes.
- Other targets: bal-miner, cuda-build, cuda-diag, bench,
  node-status, clean.
- CI: there is no .github directory and no CI configuration in
  the repository. The test record is the Makefile suite run on
  this VM. The most recent full run on record (2026-11-17,
  pre-Stage 9) executed all then-current targets sequentially:
  48 pass, 1 environment failure (test-rtl, iverilog not
  installed). That record refers to HEAD 11277e6f-era source;
  Stage 9.3 re-runs the suite at the current HEAD.

## 7. Source file hashes (sha256, verified at audit time)

Parent-supplied hashes were re-computed against the live files;
all nine matched exactly. The table extends the list to the
remaining production modules named in the Stage 9 brief.

| File | sha256 |
| --- | --- |
| mining/mainnet_live.py | c8071ce1286c2bc3350afb05a624fd6fd2b16cb1f17808a86cbe922072e3218c |
| mining/autopilot.py | 3cfafc209f4c4e8a965fe6247c05529df45efcf10687fcdeef7a147e3c1ac60a |
| mining/endpoint_config.py | c08010747aeed251df2b6ec498b21530be7facd269a5b79d76948c42a006a405 |
| mining/bakeoff_dispatch.py | fc211512d3097781413e2bfb7b11210664eb347335573c1c6f59ba7656993c10 |
| mining/coordinator.py | b4215980cac03f0e11a772887cc08a6db37ca46df8032e481175940bae032eff |
| mining/aggregation.py | 1951a657b1be1968b484514a0defa70e4c10ce93ccc46beb0f0369b74d67c603 |
| mining/pid_control.py | cfdcdd845a6a4bdfb1e9e2619bf4369376dd803ca45fe5eb7b754a4a1c51ed22 |
| mining/incident_codes.py | 5382f95ed7f22a54edebab0439a0942d751c02cb1ccf409b174861d75f2ff6bd |
| gpu/engine.py | bfe605cbb155b59f6b9857e7643348a0a6504160197a663c86d5859911365d46 |
| mining/candidate_verify.py | 35467c952cc43c06702746362025949e8c2d799d34a007c0f4f0ad56bad6a328 |
| mining/solo_server.py | b094832ab614689f6d272271d1458210e2bb4cadbe342241c564506a74bc608a |
| mining/work_checkpoint.py | cece67007c2bb043434c0d08665b39ac2c1fbfd6d1d1066ff850fd27efb43566 |
| mining/endpoint_health.py | 0c6e9101f8ea493fb34f98d4b92b573fd3a128fbd7ba1357f5c2a08bb72d6842 |
| mining/prefetch.py | 0e1ccd2ddf70baa3eb8c7e1c9380c655f5d2de50d8450a61632567305e30a9a5 |
| mining/bench_mode.py | 890ead06abd827b2309be160793be4dc3c66b7f4736cad71f90cd32cd9347594 |
| mining/mining_statistics.py | 5c3ee14b4f74b79137d1f7b342667b7b8699371afcc86705165f147288f1e27a |
| mining/probability.py | b3ba63d57e0f73a4ca2a7ff3059a9ec6f1f736d146dea1ef7f430c861f002db8 |
| mining/stratum_client.py | 334d4c28549d9645af2ebeaded62c23a76bed8e657a67de1a8ce6e04fab6590b |
| mining/engine.py | ec5f5687453c94d842cd274c054d13aa723296f46f05edfbc02b2b53f8331a5f |
| agent/autonomous.py | f7a841baab2da1ebf9d533c02973420aec17ecd5c867cbe5b8d0fb2d0d6340ae |
| agent/intelligence/controller.py | 984d08246ac8373d114a57222336597a9c005aa8a5f1ec4e569077c737a9ed76 |

## 8. Which reports and audits refer to earlier commits

Every report in the repository predates the current HEAD; the
table samples the load-bearing ones and states the HEAD basis
each one records for itself. A report is evidence about the
commit it names, not about 883cf281.

| Document | Recorded basis |
| --- | --- |
| research/EXTREME_RESEARCH/EXPERIMENT_REGISTRY.json | Generated 2026-11-15; basis: remote HEAD 18ff4eb070a066dec4424cf9cd4d8282fa9a38b3 plus the uncommitted Prompt 1 local delta |
| research/EXTREME_RESEARCH/REPOSITORY_RECONCILIATION.md | Remote HEAD 18ff4eb0 (Stage 0, 2026-11-15) |
| research/EXTREME_RESEARCH/STAGE6_VARDIFF_AUDIT.md | Remote tree at HEAD 3ebbaeb216bc1260cfca22c63b9af60d780a971e |
| research/EXTREME_RESEARCH/STAGE7_AUDIT.md | Audited locally against an unpushed tree; remote HEAD in its brief: d412f14f |
| research/EXTREME_RESEARCH/STAGE8_AUDIT.md | Remote HEAD throughout: 78a061e5385e86b953801af51b49bf5d57d72243; Stage 8 itself local and unpushed at audit time |
| research/EXTREME_RESEARCH/NOVA_ER_0006_AUDIT.md | Working tree audited against the pushed tree at remote HEAD 6528aae071fff74922f2d4a2b3b98e48ed440697 |
| research/sha256d/exp052/EXP052_REPORT.md | Campaign on the pre-push working tree; pushed at 6528aae0 |
| research/sha256d/exp056/EXP056_REPORT.md | Campaign on the pre-push working tree; pushed at e18528c8 |
| research/sha256d/exp057 and exp058 reports | Working-tree campaigns; pushed at 5ec7914d and 413608dd respectively |

The Stage 9.1 ledger and closure report in this directory are
the first reconciliation written against HEAD 883cf281.
