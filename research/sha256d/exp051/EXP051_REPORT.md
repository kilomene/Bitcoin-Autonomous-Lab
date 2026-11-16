# EXP-051: prepared-work prefetch queue (NOVA-ER-0011, register R-33)

Date: 2026-11-16. Host: AMD EPYC 9D25 126-Core Processor
(4 vCPUs visible, about 2 effective per EXP-031), under
heavy contention throughout (load average 9 to 16; an
EXP-050 audit was running suites concurrently for part of
the work). All figures are contended single-VM figures.

**Verdict: the mechanism is VERIFIED at regtest
difficulty.** The predeclared hypothesis holds: at loaded
regtest difficulty the queue removed 57.1 percent of the
median non-search overhead per block (predeclared margin:
15 percent), with 18 of 18 loaded prefetch runs
queue-served, the removable stages at 0.0 ms median on the
critical path of served runs, and ZERO stale serves
anywhere: not in the adversarial suite, not in 84 campaign
runs. At mainnet difficulty the effect is claimed nil and
nothing is measured there (see the unverified register).

## 1. Design

New module mining/prefetch.py, wired into
MiningEngine.mine_cycle (mining/engine.py) behind an
opt-in flag, in the EXP-025 / EXP-034 style:

- `MiningEngine(..., use_prefetch=False, prefetch_depth=2,
  prefetch_fetcher=None)`. Default off: no queue is
  constructed, no feed thread exists, mine_cycle resolves
  its template synchronously exactly as before. The
  disabled path is the rollback surface, and it is pinned
  by test (no queue, no counters, byte-identical
  candidates).
- PrefetchQueue: bounded (default 2 entries), newest at
  the right. Overflow evicts the oldest entry, counted.
  Duplicate identities are refused at enqueue.
- PrefetchFeed: a daemon thread that longpolls the node
  from the current template's longpollid (the engine's own
  wait_template by default; an injected fetcher otherwise),
  prepares each genuinely new template through the engine's
  own prepare_template (the EXP-025 cache, so a returning
  identity is a cache hit), and enqueues it unless it is
  the work already being mined or already queued. Feed
  errors back off and retry; the feed never raises into
  the mining thread.
- Serve rule (PrefetchQueue.serve, called once per
  mine_cycle on the steps fast path only): take the
  newest entry; drop every older entry as superseded;
  then re-verify the newest before serving:
  (1) its previousblockhash must still equal the node's
  best block hash, else it is dropped as stale;
  (2) its layered identity, recomputed from scratch at
  serve time (the EXP-025 serving rule), must equal the
  identity it was prepared under, else it is dropped as
  an identity drop. A tip that cannot be verified at all
  is treated as stale. Any failure records one
  prefetch_starved for the transition and mine_cycle falls
  through to the synchronous fetch and prepare: the queue
  can only remove work from the critical path, never
  change what work is done. A candidate prepared under
  identity A is therefore never searched under identity B.
- Time boundary: mintime and curtime are not in the
  EXP-025 identity. At serve time the entry's curtime is
  refreshed to the current time, exactly what a fresh GBT
  response would carry; build() clamps it against mintime
  per build as the uncached path does.
- Counters (mining/mining_statistics.py, EXP-051
  provenance block): prefetch_enqueued, prefetch_served,
  prefetch_starved (the starvation counter: transitions
  where no valid prepared work was ready, including a
  cold engine's first cycle), prefetch_dropped_identity,
  prefetch_dropped_stale, prefetch_dropped_superseded,
  prefetch_dropped_overflow. All are separated EXP-037
  categories; snapshot() still has no combined total and
  no counter is ever summed with another.
- Concurrency hardening in mining/engine.py:
  TemplateCache.get is lock-guarded and TemplateFamily
  construction is lock-guarded, because the feed thread
  prepares while the mining thread prepares. Semantics
  for single-threaded callers are unchanged (the
  template cache suite passes).
- Scope boundary, declared in the predeclaration: the
  solo server (mining/solo_server.py) does not consume
  MiningEngine; it has its own JobRefresher thread that
  pre-builds the next job server-side. Wiring this queue
  into that seam would be a redesign of a different
  interface, so EXP-051 covers the GBT engine path and
  declares the solo server seam out of scope rather than
  forcing it. The GBT path is the path the autonomous
  agent and the Stage 8 demonstration mine through.

## 2. Predeclaration

research/sha256d/exp051/PREDECLARATION.md was written
before any measurement (2026-11-16T18:09Z); its sha256,
23db3912749fcbd185f20dc583e89131338a868419ea39066b997f
0002b8aa07, is recorded in every campaign session
manifest. Criteria: H1 zero stale serves (hard gate);
H2 loaded-scenario median non-search overhead per block
at least 15 percent below the synchronous arm; H3 at
least half of loaded prefetch runs queue-served with the
(gbt + prepare) critical-path stage median under 5 ms in
served runs. Non-search overhead is the EXP-040
definition: cycle wall minus the search stage, in
milliseconds, never a hash rate.

## 3. Gate 3: adversarial (production suite)

tests/test_exp051_prefetch.py (make test-exp051), all
passing:

- Queue unit gates: serve, starve-on-empty, stale-tip
  drop, unverifiable-tip drop (best-hash call raising),
  identity confusion twice (an in-place version mutation
  that changes the identity without a validation error,
  and a coinbasevalue mutation that makes recomputation
  raise), superseded drops, overflow eviction with the
  bound held, duplicate refusal, curtime refresh.
- Feed gates: dedupe against the current identity and
  against queued identities.
- Engine gates on an in-process fake node through the
  real mine_cycle: cold start starves exactly once, the
  feed fills, the second cycle is queue-served and its
  block builds on the first block's hash; the identity
  confusion attack at engine level (the queued template
  mutated after prepare is dropped, never searched, the
  cycle falls back and is accepted); the stale-tip attack
  (feed stopped so only stale work is queued, an external
  block lands, the work is dropped and the cycle mines
  the live tip); rapid successive tip changes (three
  external blocks: no stale serve, served + starved
  accounts for every transition).
- Disabled default: no queue, all seven counters zero,
  candidates byte-identical to the enabled engine's.

**Stale-serve finding: none.** No adversarial test found
a stale serve; no design fix was needed. The two
re-verifications at serve time are the whole defence and
both are exercised above.

## 4. Gates 1 and 2 (inherited, re-run, not re-derived)

- make test-exp034 (EXP-034 job/template gates): PASSED.
  One earlier run failed with a bare AssertionError while
  external blocks were landing on the shared chain (its
  B-section asserts exact heights and coinbase values);
  the direct rerun and the make rerun both passed in
  full.
- make test-exp036 (EXP-036 verification gates): PASSED.
- make test-template-cache (EXP-025 cache gates, covers
  the TemplateCache lock): PASSED.
- make test-exp037 (EXP-037 statistics, covers the new
  categories): PASSED.
- make test-mining (production MiningEngine suite):
  PASSED.
- make test-exp040 (EXP-040 harness gates): PASSED.

make test-engine (tests/test_intelligence_engine.py, the
blockchain intelligence suite; it imports only
blockchain.* and node.*, nothing EXP-051 touched) FAILED
three times, always at its step-1 assertion
store.block_count() == tip + 1 after a multi-minute full
sync: (2158, 2162), (2165, 2169), (2331, 2333). The
regtest tip was directly observed advancing about one
block per 25 seconds while none of this work's processes
were mining (a concurrent audit's suites mine on the
same shared node), and any block landing between the
sync and the assertion breaks it. This is recorded as
environment interference on a shared chain, not as a
defect in this change; the suite is outside the change's
import graph and passed in earlier full test-all runs on
a quieter chain (Stage 8 audit: 39 of 40).

## 5. Gate 4: category F before/after (EXP-040 harness shape)

Harness: research/sha256d/exp051/category_f_prefetch.py,
reusing the EXP-040 harness's timers, proxies, mempool
loader and verifier. Arms differ only in the engine's
use_prefetch flag. The feed runs on its own RPC
connection through the engine's prefetch_fetcher seam
(production default is the engine's wait_template), and
prepare instrumentation is thread-aware (feed-thread
prepares are accumulated separately, never written into
the mining thread's segment stack). 3 sessions per arm
per scenario, arms interleaved by session index; A
(empty) 8 runs per session, B (loaded, 500 transactions)
6 runs per session; 84 timed runs, 0 failed, every run
one Core-accepted block passing the EXP-036 verifier.

Disclosed harness amendment: the first campaign attempt
completed scenario A, then died at the first B setup
because the shared regtest mempool held 575 transactions
(75 foreign). The harness setup now mines blocks until
the mempool is empty before each scenario setup, so the
scenario definitions (empty; exactly the loader's 500)
hold exactly as the EXP-040 asserts intend. The two
pre-amendment smoke sessions are preserved under
RAW_RESULTS/shakedown/ and are not in the analysis.

Median non-search overhead per block (ms):

| scenario | sync | prefetch | change |
|---|---|---|---|
| A empty (24 runs each) | 102.3 | 91.7 | -10.4% |
| B loaded (18 runs each) | 389.7 | 167.3 | -57.1% |

Stage medians (ms), loaded scenario B:

| stage | sync | prefetch |
|---|---|---|
| gbt | 77.7 | 0.0 |
| prepare | 111.8 | 0.0 |
| serve (exclusive) | 0.0 | 0.1 |
| construct | 0.1 | 0.0 |
| submit | 171.3 | 105.0 |
| confirm | 6.5 | 72.7 |

Reading notes, stated plainly:

- Absolute levels are far above EXP-040's (GBT 38.0 ms,
  prepare 19.7 ms, overhead 206.3 ms) because this
  campaign ran under load average 9 to 16 with a
  concurrent audit; the comparison that carries the
  verdict is arm against arm inside the same window,
  interleaved by session.
- In the prefetch arm the serve's tip check is a
  get_best_block_hash call, which the EXP-040 TimingRPC
  convention books under the "confirm" label: the arm's
  confirm median (72.7 ms) includes one extra RPC call
  per served run, and the "serve" stage's exclusive
  median (0.1 ms) is the identity recomputation plus
  queue work only. The headline overhead (wall minus
  search) is unaffected by stage labelling.
- Scenario A had no predeclared margin and none is
  claimed: at empty difficulty the removable stages are
  only about 7 ms of the sync arm's overhead, both arms'
  medians are dominated by submit/confirm variance under
  contention (maxima about 3.1 to 3.4 s in both arms),
  and the -10.4 percent median difference is reported as
  an observation, not a verdict.

Campaign prefetch counters (all prefetch sessions):
enqueued 62, served 42, starved 6, dropped_identity 0,
dropped_stale 0, dropped_superseded 16,
dropped_overflow 0. Served 42 is exactly the 42 timed
prefetch runs (24 A + 18 B): every timed prefetch run
was queue-served. Starved 6 is exactly the 6 session
warm-up cycles (cold queue each session), as the
predeclaration scopes the counter. Superseded 16 is the
feed outrunning the cycle boundary (mempool reloads and
tip changes queue a newer template before the older one
is reached); it is the queue doing its job, and each
superseded entry is counted, never silently discarded.

Verdicts against the predeclaration:

- H1 (zero stale serves): PASS. 0 failed runs in the
  campaign, every block EXP-036 verified, and the
  adversarial suite (section 3) is the primary evidence.
- H2 (loaded overhead reduction at least 15 percent):
  PASS at 57.1 percent.
- H3 (attribution): PASS. Served fraction in B is 1.0
  (18 of 18); the (gbt + prepare) median in served B
  runs is 0.0 ms, under the 5 ms bound.

## 6. Gates 5 and 6

Gate 5: the queued path runs inside the production
MiningEngine.mine_cycle with its shape unmodified: the
serve attempt is one branch at template resolution, the
search, accounting, checkpoint and submission code below
it is untouched, and result dicts are unchanged in shape.
The production suite's engine gates and the campaign
both run exactly this path.

Gate 6: regtest blocks through the queued path accepted
by Core: the production suite's real-node section mined
a queue-served block on the live regtest node (served 1,
starved 1, enqueued 2 at that point), confirmed it as
the best block, and passed it through the EXP-036 exact
verifier; the campaign added 42 more queue-served
accepted blocks (heights in the session files), every
one EXP-036 verified by the harness.

## 7. Live stack

The live mainnet miner (mining/mainnet_live.py, pool
path) does not import mining/engine.py and was never
restarted or signalled. Share census from
evidence/mainnet-live.jsonl (full count): 614 accepted /
8 rejected before, 614 accepted / 8 rejected after (no
share happened to be accepted inside this work's window;
the count is reported as counted, not smoothed).

## 8. UNVERIFIED register

- Mainnet difficulty: the effect is claimed nil by the
  hypothesis (prepare cost amortised over an astronomical
  search) and is UNMEASURED; nothing in this report is a
  mainnet figure.
- The solo server seam (mining/solo_server.py
  JobRefresher): not wired, by the declared scope
  boundary in section 1; it already pre-builds jobs
  server-side by its own design.
- Solo difficulty through this engine: the queued path
  is verified at regtest difficulty on the GBT path; a
  solo server deployment consuming MiningEngine was not
  separately measured.
- Other hosts: all measurements are the AMD EPYC 9D25
  host under contention; the Intel host rotation has not
  run this mechanism.
- Long-run feed behaviour (days of longpoll cycling,
  node restarts mid-longpoll) is exercised only over
  this campaign's hours, not soaked.
- make test-engine (intelligence suite) on a quiet
  chain: environment-blocked during this work, per
  section 4.

## 9. Files

- mining/prefetch.py (new): PrefetchQueue, PrefetchFeed.
- mining/engine.py: opt-in constructor parameters,
  mine_cycle serve branch and feed noting, close_prefetch,
  TemplateCache and TemplateFamily locks.
- mining/mining_statistics.py: seven EXP-051 categories
  with provenance.
- tests/test_exp051_prefetch.py (new) and Makefile
  (test-exp051, appended to test-all; 42 targets).
- research/sha256d/exp051/: PREDECLARATION.md, this
  report, category_f_prefetch.py, exp051_analyze.py,
  RAW_RESULTS/ (12 campaign session files, analysis.json,
  2 shakedown sessions).

An independent post-integration audit is owed before any
push, per the standing rule.
