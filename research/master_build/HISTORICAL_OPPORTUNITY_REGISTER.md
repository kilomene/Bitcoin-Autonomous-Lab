# Historical Opportunity Register: Master Build Mandate, Section 3

Date: 2026-11-15. Companion to HISTORICAL_MINER_RESEARCH.md
(same directory), which holds the per-repository evidence
for every row below.

Method: one row per concrete transferable idea found in the
studied sources. Every row was cross-checked against the
existing NOVA research record: the experiment registry
(EXP-000 to EXP-043), the Phase 001 genesis study, the
EXP-030 Phase A reference matrix (rows M01 to M34), and the
production code state after Phase 002. An idea NOVA has
already implemented, tested, decided or rejected is marked
ALREADY COVERED with its reference, so the register's NEW
rows are only ideas with no prior NOVA treatment. Statuses
for NEW rows are all NEW: no decision is invented here.

NOVA component names below use the repository's real
modules: gpu/engine.py (ComputeEngine dispatch),
mining/engine.py (GBT template engine), mining/solo_server.py,
mining/stratum_client.py, mining/mainnet_live.py,
mining/autopilot.py, mining/candidate_verify.py,
mining/mining_statistics.py, mining/work_checkpoint.py,
agent/interface.py, agent/autonomous.py.

## Register

| # | Idea | Source repo and file | NOVA component | Expected value | Risk | Status |
|---|---|---|---|---|---|---|
| R-01 | Compute the chunk-1 midstate once per template and reuse it for every nonce | jgarzik/cpuminer, cpu-miner.c (server-supplied midstate); pooler/cpuminer, sha2.c sha256_transform | mining/engine.py, gpu/engine.py | Removes 64 of 192 rounds per candidate | None; exact identity | ALREADY COVERED: Phase 001 H-1; production since the first C backend; re-verified EXP-023, EXP-025 |
| R-02 | Precompute the nonce-independent prefix of chunk 2 (rounds 0 to 2) once per template | pooler/cpuminer, sha2.c sha256d_prehash | gpu/engine.py kernels | Removes the remaining reusable rounds; the 67 of 192 ceiling | None; exact identity | ALREADY COVERED: registry H-03; EXP-023 family; in production kernels |
| R-03 | Pre-extend the message schedule for nonce-independent words | pooler/cpuminer, sha2.c sha256d_preextend | gpu/engine.py kernels | Avoids recomputing fixed schedule words per nonce | None; exact identity | ALREADY COVERED: EXP-016 (W18 is the first nonce-dependent expanded word); production |
| R-04 | Multi-way interleaved batch hashing (4-way SSE2, 8-way AVX2 forms) | jgarzik/cpuminer, sha256_4way.c; pooler/cpuminer, sha2.c scanhash_sha256d_8way | gpu/engine.py | The whole SIMD throughput ladder | None | ALREADY COVERED: EXP-011, EXP-026 (DualMask integrated), EXP-032, EXP-039 (AVX2 tier integrated) |
| R-05 | Cheap first-word screen, then an exact full 256-bit target test as the only authority | pooler/cpuminer, sha2.c (Htarg screen) and util.c fulltest | mining/candidate_verify.py | Screening saves work; exactness is never delegated to the screen | A screen treated as authority would be a consensus bug | ALREADY COVERED: EXP-036 (verify_candidate, integer only, no float anywhere in the file); screens exist in production search masks, EXP-024, EXP-026 |
| R-06 | Return candidate nonces only from the search device, never bulk digests | m0mchil/poclbm, phatk.cl search kernel output discipline | gpu/engine.py search path | Cuts result data movement to near zero | None | ALREADY COVERED: registry H-04; EXP-024 and EXP-026 mask search integrated as v512dual |
| R-07 | Runtime CPU feature probing with per-tier backends behind one scan interface | jgarzik/cpuminer, cpu-miner.c backend selection; pooler/cpuminer, sha256_use_4way and sha256_use_8way | gpu/engine.py | One engine, correct kernel on every host | Executing an unsupported instruction is a hard crash | ALREADY COVERED: EXP-028, EXP-039 (flag-free probe, dispatch order CUDA, v512dual, v512, shani, avx2, C, hashlib) |
| R-08 | Long-poll work refresh with per-thread restart flags so stale work is abandoned inside a span | jgarzik/cpuminer, cpu-miner.c restart_threads; pooler/cpuminer, GBT longpoll handling | mining/mainnet_live.py, mining/autopilot.py | Fresh templates reach search threads in seconds | Restart storms on a flapping endpoint | ALREADY COVERED: production GBT longpoll monitoring; autopilot watchdog at 1 s poll |
| R-09 | Hand workers explicit nonce ranges (base plus size) cut from a work unit, ranges dying with their unit | jedi95/Phoenix-Miner, WorkQueue.py NonceRange, getRangeFromUnit, isRangeStale | mining/engine.py, coordinator design | Deterministic, disjoint distribution | Ranges without completion accounting falsely claim coverage | ALREADY COVERED and strengthened: EXP-029 allocator proofs; EXP-035 leases; EXP-038 crash-honest frontiers |
| R-10 | Fixed registry of immutable jobs, cloned on read, results resolved to jobs by id | Bitaxe firmware via EXP-030 matrix M04, M05 | mining/engine.py job model | Kills job mutation races and stale result attribution | Slot recycling ambiguity in the original | ALREADY COVERED: EXP-030 M04, M05 decisions; EXP-034 job and template engine (generation-tagged identity) |
| R-11 | Partition extranonce2 by worker id bits plus a per-worker counter | Qaxe firmware via EXP-030 matrix M06 | coordinator design | Disjoint coinbase space by construction | Partition exhaustion at extreme worker counts | ALREADY COVERED: EXP-035 work distribution design (slot shifted left 25, 25-bit counter) |
| R-12 | Adapt share difficulty toward a target share interval, with hysteresis on increases | Bitaxe firmware via EXP-030 matrix M10; ckpool, src/stratifier.c vardiff | mining/solo_server.py | Stable share flow for accounting at any hashrate | Oscillation without hysteresis; difficulty is not a consensus value and must stay out of candidate judging | ALREADY COVERED as a decided design (M10, EXP-037 statistics); production state: solo share difficulty is still fixed at 0.02, implementation remains open and is tracked here so it is not lost |
| R-13 | Coordinator re-verifies every worker candidate exactly before submission; workers never submit directly | Qaxe firmware via EXP-030 matrix M13; ckpool, src/stratifier.c share validation | mining/candidate_verify.py | One verified submission path for the whole fleet | Verifier throughput bounds fleet size (matrix M27 budgeting) | ALREADY COVERED: EXP-036 verification component; EXP-035 coordinator design |
| R-14 | Suppress duplicate candidates and shares keyed by full work identity | Qaxe firmware via EXP-030 matrix M12; luke-jr/bfgminer, miner.c stratum_share table | mining/mining_statistics.py, coordinator design | Duplicated work never counts as coverage | A too-small dedup window admits duplicates | ALREADY COVERED: EXP-035 duplicate detection and accounting (892 injected duplicates all detected in its campaign) |
| R-15 | Treat version rolling, extranonce and nonce as one combined, exactly accounted search space | Bitaxe hardware note via EXP-030 matrix M34; ckolivas/cgminer, work rolls (roll-ntime lineage) | mining/engine.py, coordinator design | Correct coverage claims across all rolling dimensions | Double counting one dimension against another | ALREADY COVERED: EXP-034 and EXP-035 combined space design; EXP-038 frontier keys include extranonce space |
| R-16 | Detect stale work and refuse to submit stale shares by default | ckolivas/cgminer, cgminer.c stale_work, opt_submit_stale | mining/stratum_client.py, mining/solo_server.py | No wasted submissions; honest accounting | Over-eager staleness discards valid near-tip work | ALREADY COVERED: EXP-034 template identity; EXP-036 submit classification; solo cutover verification counts server-side |
| R-17 | Stage non-clean job updates and swap at a search boundary instead of tearing live work | Bitaxe firmware via EXP-030 matrix M16; ckolivas/cgminer work expiry discipline | mining/engine.py | No torn reads of job state mid-search | Staging delays urgent clean jobs if misapplied | ALREADY COVERED: EXP-025 cache identity discipline; EXP-034 safe job replacement |
| R-18 | Per-worker counters (hashes, candidates, errors) in fixed time windows as the only hashrate source | Bitaxe firmware via EXP-030 matrix M11; Canaan Avalon farm-manager status reports | mining/mining_statistics.py | Honest, luck-independent telemetry | Counter overhead in the hot loop if done naively | ALREADY COVERED: EXP-037 (EvidenceCounter, separated statistics, no combined total) |
| R-19 | Backend self-test against known vectors at selection and at worker start; refuse on failure | Bitaxe firmware via EXP-030 matrix M32; BFGMiner ZTEX capability readback via libztex.c | gpu/engine.py | A broken backend never mines silently | Self-test bugs could refuse a good backend | ALREADY COVERED: production hashlib self-test at dispatch (256-nonce check); EXP-039 D-1 guarded probes; EXP-028 simulated capability profiles |
| R-20 | Separate supervisor that never mines and a miner that never supervises itself | Qaxe supervisor MCU via EXP-030 matrix M20; ckolivas/cgminer watchdog thread | mining/autopilot.py plus the keeper cron | Supervision survives miner death | Supervisor complexity | ALREADY COVERED: autopilot plus keeper layering, proven live by repeated keeper restarts |
| R-21 | Support Stratum V2 with Noise encryption for external pools, and model precomputed-root jobs as a distinct job type | Bitaxe firmware via EXP-030 matrix M23, M24; stratum-mining/stratum, sv2 subprotocols | mining/stratum_client.py, mining/engine.py job model | Protocol currency; correct caching for both job types | Real implementation cost; no current NOVA need (own solo server is V1) | ALREADY COVERED as investigated and sequenced (M23 Investigate, M24 Adapt); not implemented, by recorded decision |
| R-22 | Pipeline the compression function so independent nonce lanes hide round latency | fpgaminer/Open-Source-FPGA-Bitcoin-Miner, src/sha256_transform.v | gpu/engine.py kernels | The SIMD interleave strategy itself | None at the concept level | ALREADY COVERED as the software analogue: EXP-003 multi-stream, EXP-011 and EXP-026 interleaved multi-buffer; the hardware mechanism itself is non-transferable |
| R-23 | Startup measured bake-off: benchmark every correctness-passing backend on the actual host at first start, cache the winner in the host capability profile, fall back to the static dispatch order on any doubt | luke-jr/bfgminer, driver-cpu.c and README.CPU (--algo auto and fastauto) | gpu/engine.py dispatch; EXP-031 capability profiles | Picks the empirically fastest tier on hosts the lab has never seen, including the alternating AMD and Intel VMs of EXP-031; closes the EXP-039 note N-1 refusal gap empirically instead of by construction | Benchmark noise on a contended VM could pick a worse tier; mitigate with EXP-017-shaped medians, a minimum margin over the static choice, and re-runs on host change | NEW |
| R-24 | Per-operation privilege enforcement on the agent control interface: every operation carries a privilege class (read, operate, administer) enforced at the transport, modelled on a proven command table | ckolivas/cgminer, api.c command table (mutating commands flagged privileged: restart, quit, switchpool, enablepool, save, hotplug) | agent/interface.py | Turns the mandate's authority levels from convention into mechanism; the Antbleed history (report section 3.13) is the counterexample of an unprivileged control surface | Over-broad privilege classes could block legitimate recovery actions; classes must be designed with the recovery paths first | NEW |
| R-25 | Quota-based allocation across multiple template and endpoint sources, quotas forward-looking, a dead source's quota dropped until it recovers, all-zero quotas falling back to failover | ckolivas/cgminer, miner.h enum pool_strategy (POOL_LOADBALANCE, POOL_BALANCE), README quota semantics | mining/endpoint_config.py, coordinator design | Lets a future fleet split work between its own solo server and external pools by policy instead of a binary switch | Quota bugs could starve the solo leg or double-assign space; needs EXP-035 lease integration, never a replacement for it | NEW |
| R-26 | Endpoint health policy as a named object: ordered endpoints, N consecutive errors before failover, a timed failback retry of the primary | m0mchil/poclbm, poclbm.py options (tolerance, failback) and Switch.py | mining/mainnet_live.py, mining/autopilot.py | The pool leg survives endpoint failure and recovery without operator action; policy is inspectable and tunable by the agent | Failback flapping on a marginal endpoint; needs damping counts, which the source's tolerance parameter already models | NEW |
| R-27 | A stratum-speaking aggregation tier between fleet workers and upstream endpoints: one process holds few upstream connections, fans workbases out, validates shares, and keeps per-worker accounting | ckpool, src/ckpool.c proxy and passthrough modes, src/stratifier.c, src/connector.c; luke-jr/bfgminer stratum server mode | new component beside mining/solo_server.py | Fleet scale without one upstream connection per worker; a single point where EXP-036 verification and EXP-037 accounting attach to stratum traffic | A new trusted component; must inherit EXP-035 fleet identity checks, not ckpool's open pool trust model | NEW |
| R-28 | Push-based template supply from the node via Bitcoin Core's multiprocess mining IPC, with GBT retained as fallback | ckpool, README-SOLOMINING.md and src/generator.c (IPC preferred, GBT fallback) | mining/engine.py template source | Templates arrive on new-block events with no polling or longpoll latency; matches Core's own direction | Requires a Core version and build change (multiprocess bitcoin-node, Core 32 era) while NOVA pins bitcoind 28.1; a node upgrade is an owner-level infrastructure decision, so this row is gated, not scheduled | NEW |
| R-29 | Stratum V2 job declaration client: the miner proposes its own self-built template to the pool for approval | stratum-mining/stratum, sv2/subprotocols job-declaration | mining/stratum_client.py (future SV2 work) | Template sovereignty on external pools; the pool cannot silently censor transactions from NOVA-built templates | Depends on R-21's SV2 base and on pools that support declaration; identity handling for proposed templates must extend the EXP-025 fingerprint | NEW |
| R-30 | Stable numeric incident code registry: every detected fault, recovery action and backend refusal carries a durable code from a registry file, keyed into statistics and audit | MicroBT Whatsminer public error-code documentation (documentation-sourced only; no source exists to study, report section 3.19) | mining/mining_statistics.py, mining/autopilot.py incident records | Agent reasoning and post-incident audit can key on codes instead of free text; recurring fault classes become countable | A badly designed taxonomy ossifies; codes must be append-only and coarse at first | NEW |
| R-31 | Signed release chain for fleet software: versioned builds, a signing key, a feed of signed manifests, staged rollout with refusal on signature failure | Braiins OS via fork mirror DavHau/braiins-os, bb.py, keys/, build-release.sh, upgrade/ | mining/autopilot.py self-update path | The fleet gains a verifiable update mechanism; today the autopilot self-update is inert on this VM and there is no fleet update story at all | Key management is a security-critical design task; a bad rollout bricks workers, so staging and rollback must be designed before any signing | NEW |
| R-32 | PID closed-loop control for worker count and span size, driven by a measured error signal (steal time or share interval error), replacing step changes | Braiins braiins/bmminer, fancontrol.c PID loop (hardware target, software shape) | mining/autopilot.py, adaptive scheduler (mandate milestone 4) | Smooth adaptation on contended VMs instead of throttle and collapse cycles; matrix M21 flagged ramping as Investigate but no controller was designed | A mis-tuned loop oscillates; needs EXP-031 signal data and conservative gains, with the step policy retained as fallback | NEW |
| R-33 | Prepared-work prefetch queue between the template engine and the search threads, with a starvation counter, so a template change never leaves search threads idle | ckolivas/cgminer staged work queue (cgminer.c); jedi95/Phoenix-Miner, WorkQueue.py fetchRange staging | mining/engine.py, gpu/engine.py seam | Removes template-transition bubbles from the production path; EXP-040 measured per-stage costs but no prefetch mechanism was built | Prefetched work ages; the queue must key every entry to template identity and drop on change (EXP-025 discipline) | NEW |
| R-34 | Hotplug-style worker attach and detach on a running coordinator: a worker joins, is capability-checked and leased work, or drains and leaves, without coordinator restart | ckolivas/cgminer, api.c hotplug command and device hotplug handling | coordinator design (EXP-035 follow-on) | Fleet membership becomes an operation, not a deployment event; matches how VM workers actually appear and disappear | Drain semantics must never falsely complete work; EXP-038 frontier rules govern the leaving path | NEW |
| R-35 | A first-class offline benchmark mode in the production binary: run the real search path against a fixed bench work unit with no network, report the category E rate and the host profile | tpruvot/ccminer, ccminer.cpp --benchmark mode (opt_benchmark) | gpu/engine.py command line surface | After every VM replacement the new host is profiled in one command through the production path, feeding R-23 and EXP-031 profiles; today benchmarks live only in research harnesses | A benchmark mode must never be confusable with mining; fixed work unit, no submission path compiled into the mode | NEW |

## Counts

- Total rows: 35.
- ALREADY COVERED: 22 (R-01 to R-22), each with its
  experiment, matrix or production reference.
- NEW: 13 (R-23 to R-35), none previously treated in the
  NOVA record.

## Reading notes

- The NEW rows cluster entirely in the operations layer:
  selection, control privilege, allocation, resilience,
  aggregation, template supply, incident taxonomy, updates,
  adaptive control, queueing, membership and profiling.
  No new hash-path mechanism was found anywhere in the
  studied sources; the report's synthesis section states
  this as a completeness signal with its boundary (closed
  ASIC firmware could not be searched).
- Two NEW rows are gated on decisions outside the research
  programme: R-28 needs a Bitcoin Core version decision;
  R-29 needs R-21's SV2 base plus pool support. Both are
  registered so the gates are visible, not as work items.
- R-12 is the one ALREADY COVERED row whose production
  implementation is still open (solo share difficulty is
  fixed at 0.02 today). It is marked covered because the
  design decision exists (matrix M10, EXP-037); the row
  stays visible here so the implementation gap is not lost.
- Excluded deliberately: sgminer's pluggable hash algorithm
  registry (report section 3.15). The mandate fixes exact
  SHA-256d; a multi-algorithm registry is out of scope and
  is recorded as an exclusion, not a row.
