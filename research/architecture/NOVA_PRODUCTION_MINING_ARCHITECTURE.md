# NOVA Production Mining Architecture

NOVA SHA-X Master Assignment, deliverable 16 (work packages BR-016,
integrated production engine, with BR-012 and BR-015). Date:
2026-11-15.

This document describes the production mining system as it actually
is today, verified against source by the Phase A audit
(research/bitcoin_reverse_engineering/NOVA_REPOSITORY_AUDIT.md) and
the wave A to C deliverables, and then the target architecture the
Master Assignment's phases point to, with every gap between the two
named and tied to its work package.

Status vocabulary: LIVE (running in production), INTEGRATED
(in production code, exercised by callers), PRESENT-UNWIRED (in
production code, no live caller), PROTOTYPE (research only),
ABSENT.

## 1. The system at a glance

Four running or staged paths share one dispatch core and one
verification stage:

- The **live pool path** mines mainnet on public-pool.io today.
  It is the only path producing evidence: pool-accepted shares
  (evidence level E3; 248 accepted at the EXP-037 full-log census,
  the count growing since), zero blocks, balance 0 BTC.
- The **engine path** (MiningEngine over getblocktemplate) mines
  against a node directly; it is the path the autonomous agent
  drives and the path the template cache, extranonce space and
  checkpointing serve.
- The **solo path** (own solo server fed by our own node) is built,
  audited, and staged: the cutover is armed and has not fired,
  because our pruned mainnet node is still in initial block
  download.
- The **research path** (EXP-035 coordinator prototype, EXP-032
  undispatched tiers) is proven where it claims to be proven and
  is not part of production.

The programme's success criterion, stated here because every
architecture claim is subordinate to it: a real, independently
verified, submitted and accepted mainnet block. **NOT MET.** No
block has been found, the balance is 0 BTC, and pool shares are
not blocks.

## 2. The live pool path (LIVE)

Components, in data order:

1. **mining/mainnet_live.py**, the runner. Constructs a
   ComputeEngine with defaults, takes jobs from the pool through
   the Stratum client, and searches with
   engine.search_first(header, target, nonce, span) (line 185).
2. **mining/stratum_client.py**, the pool client. build_header
   assembles the 80-byte header (wordswap prevhash mode); incoming
   jobs pass validate_job plus duplicate and stale-echo guards
   before they can supersede current work; every accepted job
   bumps job_generation, which the runner checks before
   submitting, so a hit on a stale generation is never submitted.
3. **Verification before submission.** Every search hit is
   reconstructed into a full header and passed through
   mining/candidate_verify.py verify_candidate with the mainnet
   pow limit and the pool share target; submission happens only
   when the backend digest matches both recomputations (hashlib
   and pure Python), the header target is legal, the exact integer
   share comparison passes, and the job generation is still the
   freshest. Block candidacy in the evidence log comes from
   meets_network_target alone.
4. **mining/autopilot.py**, the supervisor. Single-instance flock;
   heartbeat to .local/heartbeat.json every 5 s; watchdog polls the
   miner child every 1 s with a 300 s hung window; crash backoff
   1 s capped at 30 s; 24 h session rotation; self-update check
   every 900 s (inert in this checkout, which has no .git). Its
   EvidenceCounter streams the whole evidence log once and then
   advances incrementally, persisting offset, counts and a head
   fingerprint atomically; it replaced the tail-window counter
   that under-reported the share census (EXP-037).
5. **The outer keeper** (goal cron outside the repo): restarts the
   autopilot if it is truly down and restarts the node if its RPC
   stops answering; it owns recovery from the VM replacements this
   environment undergoes roughly every two hours.

Worker identity: every entry point defaults its worker to the
machine hostname (this VM mines as htch-runtime); the payout
address is the lab wallet bc1q528egeqsvv8aa382j43edxskqw6x7zxc2xpcf3.

## 3. The dispatch core (INTEGRATED)

gpu/engine.py ComputeEngine is the single dispatch point for every
path. Selection order for the search backend (lines 862 to 897):

1. **CUDA**, only if requested and only if library load, device
   presence and a CPU-reverified production self-test all pass.
   No GPU device exists on any lab host; CUDA has never been
   selected and no GPU rate exists.
2. **v512dual** (mining/cpu/bal_avx512_dual.c): the DualMask
   kernel, VERIFIED IMPROVEMENT (EXP-026, pooled 1.718x over the
   v512 search), selected on AVX-512F+BW hosts.
3. **v512** (bal_avx512_mb.c): the preserved AVX-512 multi-buffer
   fallback, VERIFIED 3.55x over production C in batch scope
   (EXP-017).
4. **C** (bal_batch.c): the OpenSSL midstate batch backend.
5. **Python hashlib** (backend "cpu"): the floor, and the
   verification authority for every backend's self-test.

Selection discipline: the library file must exist; the flag-free
CPUID probe (bal_avx512_probe.c, compiled with no vector flags)
must exist, checked with hasattr BEFORE any argtypes assignment
(the audit D-1 rule, mandatory in every integration since); the
counted entry points must all be present as a completeness list;
then a self-test batch must reproduce hashlib digests exactly. Any
failure leaves the backend unselected with the reason recorded.
Thread tuning probes counts with the real counted search and keeps
the measured peak. The AVX-512 translation units are built with
the restricted flags -mavx512f -mavx512bw, never -march=native, so
the same binaries run on both lab host shapes (AMD EPYC 9D25 with
SHA-NI; Intel Xeon Platinum 8321HC without).

The live search path itself: search_first wraps
search_first_counted (line 1459), which dispatches on the selected
backend to the native counted search entries only (bal_vd_search2,
bal_v_search2, bal_c_search2, or the batch_search fallback on the
cpu backend). The EXP-022 flags library (bal_avx512_flags.c,
exporting only bal_v_batchf2 plus probe symbols) is selected
independently for batch enumeration and is reachable only through
batch_search via _vf_batch_flagged; it has no search entry point
and no presence in the search path (audit section 3, verified
again in INDEPENDENT_VALIDATION_REPORT.md).

Verified but NOT dispatched: the EXP-032 AVX2 multi-buffer kernel
(1.409x over C, batch) and the EXP-032 SHA-NI streams-4 kernel
(2.861x over C, batch), and EXP-024b design C mask search (1.398x,
search scope). All three exist only in research code.

## 4. The engine path (INTEGRATED)

mining/engine.py MiningEngine, over node/rpc_client.py to a Core
node:

- **Templates.** get_template calls getblocktemplate with rules
  ["segwit"]; wait_template implements the GBT longpoll and is
  PRESENT-UNWIRED (no production caller; the agent calls
  get_template fresh each cycle).
- **Construction.** build_coinbase and the candidate builders
  implement BIP34 height, the "/BAL/" marker, the engine
  extranonce, coinbaseaux flags, and the BIP141 witness commitment
  when any transaction has a witness. Template transactions are
  re-parsed; txids and wtxids are recomputed and a mismatch rejects
  the template; coinbasevalue must equal subsidy plus fees.
- **The EXP-025 template cache** (INTEGRATED): a layered identity
  (family, transaction, coinbase and header keys under dsha256),
  computed only after the full validation pass, bounded at 128
  entries with FIFO eviction, never serving silently on mismatch,
  with build_candidate_uncached preserved as the fallback and
  differential reference. Its measured gains are
  candidate-construction rates (steps500 pooled 23.02x), never hash
  rates.
- **Search.** mine_cycle steps extranonce rounds (opt-in
  extranonce_space, EXP-034, default (0, 64)) and searches batches
  through search_first_counted; total_hashes accumulates the
  backend's reported attempted count, never the requested size.
- **Submission.** A hit is assembled into a full block and
  submitted with submitblock, counted accepted only when
  submitblock returns None AND the node's best block hash equals
  the block hash: the same acceptance standard as
  candidate_verify.verify_chain_acceptance, applied inline (the
  code is not shared; a consistency note, not a defect).
- **Checkpoints.** mining/work_checkpoint.py (EXP-038) is opt-in
  via checkpoint_path; its only production caller is
  agent/autonomous.py. The frontier advances only after a batch
  returns without a hit.
- **Statistics.** mining/mining_statistics.py is PRESENT-UNWIRED:
  no live path calls record(). mining/probability.py is live but
  partial (no percentile outputs; see the gap analysis, section 3
  item 6).

## 5. The solo path (INTEGRATED, staged)

- **mining/solo_server.py.** refresh_job builds the coinbase with
  the engine's builder and an 8-byte extranonce placeholder and
  serves the STRIPPED coinbase split as coinb1 and coinb2; the
  split offset is located in the stripped bytes (lines 262 to 270),
  the EXP-034 fix for the defect that would have served corrupted
  coinbases on effectively every mainnet template had the cutover
  fired first. validate_share rebuilds the exact block and routes
  the header through verify_candidate; a network-target candidate
  is submitted and recorded accepted only when
  verify_chain_acceptance confirms tip or in-chain. JobRefresher
  polls the node every 2 s and refuses to serve during initial
  block download, on the wrong chain, or when the node is
  unreachable.
- **mining/solo_mainnet.py** behind scripts/bal-solo.service
  (Restart=always), installed at fire time.
- **scripts/solo_cutover.py** (check, fire, rollback, status),
  guarded by the marker .local/solo-cutover.json (absent: the
  armed default). Fire verifies preconditions, smoke-tests live
  Stratum, flips .local/mining-endpoint.json from "pool" to
  "solo", restarts the miner child through the autopilot, and
  requires at least 3 server-side accepted shares; post-flip
  failures roll back to the pool automatically. The
  bal-solo-cutover watcher cron runs the check every 15 minutes
  and has returned NOT_READY on every check so far, correctly.

## 6. The node (LIVE, syncing)

Our own pruned mainnet Core 28.1: datadir .local/mainnet,
prune=550, RPC on 127.0.0.1, 8 outbound peers pinned after the
2026-11-14 permission-card incident. It is in initial block
download (about 446,000 of about 976,000 headers at the last
recorded check on 2026-11-15, still syncing; no completion ETA is
promised anywhere in this programme). Until it syncs, the solo
path cannot fire and live mining stays on the pool. A second
peered regtest node serves the test suites.

## 7. The target architecture, and every gap to it

The Master Assignment's phases point to a system with the same
paths, closed at the following points. Each gap names its current
state and its work package.

| # | Gap | Current state | Work package |
|---|---|---|---|
| G1 | Production coordinator, lease manager, candidate queue | EXP-035 PROTOTYPE, proven in-process; multi-machine overhead, latency and scaling UNVERIFIED; fleet activation is the owner's decision and has not been given | BR-015, BR-007 |
| G2 | Category F end-to-end benchmark | ABSENT as a measurement; F is validated by regtest tests and live operation, never timed | BR-010 |
| G3 | Dispatch tiers for non-AVX-512 hosts | EXP-032 AVX2 and SHA-NI streams kernels VERIFIED in research, ABSENT in production; non-AVX-512 hosts fall back to C or hashlib | BR-008, BR-016 |
| G4 | Live statistics wiring | mining_statistics PRESENT-UNWIRED (no record() caller) | BR-011, BR-016 |
| G5 | Probability percentile and exact forms | Specified to signature level in the probability model (seven functions); ABSENT in mining/probability.py | BR-011 |
| G6 | Version rolling (BIP320) and ntime rolling | ABSENT on every path | BR-007 |
| G7 | Longpoll in production | wait_template PRESENT-UNWIRED | BR-012 |
| G8 | Stratum V2 | ABSENT (V1 only, both ends) | BR-012 |
| G9 | Shared acceptance code on the GBT path; reorg re-check after acceptance | Inline equivalent check; no reorg re-check anywhere | BR-012 |
| G10 | Design C single-batch mask search | VERIFIED in research (1.398x); integration is an owner decision, not taken | BR-008, BR-016 |
| G11 | The 29 versus 28 op codegen gap | Known residual; the one-op candidate measured 1.051x NOT SIGNIFICANT and was not integrated | BR-008, BR-013 |
| G12 | E2 (Sigma-through-Maj/Ch cone) | UNPROVEN BREAKTHROUGH; attack INCONCLUSIVE; ceiling about 2 ops per round | BR-013, BR-014 |
| G13 | Documentation debt | 11 contradictions from the Phase A audit unfixed (gap analysis section 4) | BR-001, BR-017 |
| G14 | Node sync and solo cutover | In progress by design; watcher armed; fires only on READY | BR-012 |

Target state, in one paragraph: the pool path remains as the
fallback it already is; the solo path fires when the node syncs
and becomes the primary mainnet path under the same verification
stage; the engine path gains its longpoll caller, live statistics
and complete probability outputs; dispatch gains the two verified
fallback tiers under the full gate set; a category F harness makes
the whole pipeline measurable; and if, and only if, the owner
decides fleet activation on measured overheads, the EXP-035 design
becomes a production coordinator with the candidate queue between
search and submission. None of this changes the honest arithmetic:
at the measured rates, 500 GH/s is about 24,272 systems on the live
basis and about 33,800 VMs on the contended benchmark basis, and
140 TH/s is about 6.8 million and about 9.5 million respectively
(research/cpu_architecture/VM_RESOURCE_CAPACITY_REPORT.md
section 9). The architecture work closes correctness, wiring and
measurement gaps; it does not close the throughput gap, and no
document in this programme claims otherwise.
