# EXP-051 independent audit (post-integration)

Auditor: independent agent, not the author. Date: 2026-11-16.
Host: AMD EPYC 9D25 126-Core Processor, contended VM
(load average about 7 to 12 during the audit). Scope:
mining/prefetch.py (new), the MiningEngine wiring in
mining/engine.py, the EXP-051 counters in
mining/mining_statistics.py, tests/test_exp051_prefetch.py,
the Gate 4 campaign record in research/sha256d/exp051/
RAW_RESULTS/, and the three experiment registries. Method:
line-by-line source read, a blob-verified diff against
remote HEAD b8b01ed3, the auditor's own adversarial probes
(four, none from the author's suite), the auditor's own
recomputation of the Gate 4 figures from the raw session
files, and the auditor's own runs of six suites.

## Verdict: PASS WITH NOTES. Defects: 0.

The change is cleared for the push step. The central claim
survives every attack the auditor could construct (section
2). All Gate 4 headline figures reproduce exactly from the
raw session files (section 5). The one author-reported
suite failure (test-engine) is confirmed environmental:
the suite passes on the auditor's rerun on a quiet chain
(section 6).

## 1. What was verified against primary sources

- Remote diff: mining/engine.py and
  mining/mining_statistics.py were fetched from remote
  commit b8b01ed3 through the contents API (blob SHAs
  verified) and diffed against the working tree. Every
  removed engine line reappears either re-indented inside
  the new TemplateCache lock or inside the restructured
  mine_cycle template resolution; every other change is a
  pure addition (imports, the lock, three constructor
  parameters with inert defaults, four new methods, the
  serve branch, the note_current call). The statistics
  diff is a docstring block, seven appended category
  names, and one error-message string. Nothing else in
  either file changed.
- mining/prefetch.py does not exist at b8b01ed3; it is a
  new file, as claimed.
- Live path isolation: mining/mainnet_live.py imports
  gpu.engine and mining.pow_engine only; a grep over
  mainnet_live.py, stratum_client.py and autopilot.py
  finds zero imports of mining.engine. The live pool
  miner cannot reach the changed code.

## 2. The central claim, attacked

Claim: a candidate prepared under template identity A is
never searched under identity B. The serve path
(PrefetchQueue.serve, mining/prefetch.py lines 113 to 154)
takes the newest queued entry, drops all older entries as
superseded, then (1) requires the entry's
previousblockhash to equal a freshly fetched best block
hash (any exception from the best-hash call is treated as
stale), and (2) recomputes the entry's layered EXP-025
identity from scratch via template_identity and requires
equality with the prepared identity (any exception is
treated as an identity drop). Both checks fail closed.
The auditor probed the surfaces the identity does not
cover and the races around the checks:

- Identity coverage: every field PreparedTemplate
  captures and build() consumes is inside the identity
  (tx set with txids, wtxids and fees; the default
  witness commitment string; height; coinbasevalue;
  coinbaseaux flags; the derived witness commitment;
  version; previousblockhash; bits; target; the family
  layer covers payout address, script, chain and halving
  interval). A grep over all production code finds
  exactly one write to a template field anywhere:
  prefetch.py line 152, the serve-time curtime refresh,
  which runs after both re-verifications and touches a
  field outside the identity by the declared EXP-025
  boundary.
- Extranonce space: a per-build input held by the engine,
  never part of the prepared work; the queue is per
  engine, so no cross-space serve exists. The EXP-038
  checkpoint keys on identity plus space plus curtime
  basis, unchanged.
- Mempool move (auditor probe P2): with the node's
  current template moved to A-prime (same tip, enlarged
  tx set), the queued A still serves, and the built
  candidate is exactly A's (coinbase plus A's one
  transaction, prevhash equal to the live tip). That is
  the claim operating as defined: the work is searched
  under A, internally consistent, on the live tip. H1's
  predeclaration defines a stale serve as an identity
  mismatch or a prevhash that is not the best block at
  serve time; a mempool refresh is neither.
- Tip race: a block landing between the serve-time tip
  check and the search leaves the cycle searching the
  previous tip's template. The synchronous path has the
  same window, larger (fetch, prepare, then search). The
  candidate stays internally consistent, and Core's
  submitblock plus best-chain verdict remains the final
  acceptance test, as before this change. Not a violation
  of the claim as predeclared.
- Queue race: serve snapshots and clears the queue under
  its lock, then verifies outside it. An entry enqueued
  during verification simply waits for the next
  transition and is verified then. No path serves
  unverified work. Auditor probe P3 (16 threads,
  concurrent TemplateCache.get, enqueue and serve):
  no deadlock, no exceptions, served plus starved equals
  the 1,000 serve calls exactly, cache identity_checks
  equals hits plus prepares exactly, queue bound held.
- Cache and family locks: TemplateCache.get holds its
  lock across the check-then-store sequence (statements
  identical to the pre-change body); construction under
  the lock performs no RPC and never re-enters the cache,
  and cache_family uses a separate lock acquired before,
  never inside, the cache lock. No lock-ordering cycle
  exists. EXP-025 cache semantics are unchanged for
  single-threaded callers (test-template-cache passes,
  section 6).
- Time fields: see notes N-1 and N-2. Both effects are
  confined to the header time, remain consensus-valid or
  fail visibly at Core, and neither moves a candidate
  across identities.

No stale serve was found by the author's adversarial
suite, by the campaign, or by the auditor's probes.

## 3. Disabled default

With use_prefetch=False the constructor builds no queue
and no feed, mine_cycle's serve branch is skipped by
_prefetch_usable(), the steps-path prepare condition
reduces to the historical one, and the note_current call
is behind `if self.use_prefetch`. The remote diff
(section 1) shows the disabled flow is statement-for-
statement the historical flow. The author's suite pins
it (no queue, all seven counters zero, candidates
byte-identical to the enabled engine's); the auditor's
test-mining and test-template-cache runs exercise the
disabled path through the production engine and pass.

## 4. Counters

The seven categories (prefetch_enqueued, prefetch_served,
prefetch_starved, prefetch_dropped_identity,
prefetch_dropped_stale, prefetch_dropped_superseded,
prefetch_dropped_overflow) are appended to the EXP-037
CATEGORIES tuple as their own block; snapshot() is
untouched and still has no combined total; record()
still rejects unknown categories. In serve(), exactly
one of prefetch_served / prefetch_starved is recorded
per call on every path (empty queue, stale newest,
identity mismatch, success), which the auditor verified
by reading every return and empirically in probe P3.
The campaign accounting closes exactly: enqueued 62
equals served 42 plus superseded 16 plus 4 entries still
queued at session ends; starved 6 equals the six session
warm-up cycles, each session file's warmup block showing
starved 1 and served 0. One precision note is recorded
as N-3.

## 5. Gate 4 recomputation (auditor's own analysis)

The auditor recomputed everything from the 12 session
JSONs in RAW_RESULTS/, ignoring the author's analysis
code and analysis.json:

- Scenario B (loaded): synchronous median non-search
  overhead 389.7 ms, prefetch 167.3 ms; reduction 0.5706
  (57.1 percent), against the predeclared 15 percent
  margin. Matches the report.
- Scenario A (empty): 102.3 ms vs 91.7 ms, reported by
  the author without a verdict, correctly: no margin was
  predeclared for A.
- Served fraction: 42 of 42 timed prefetch runs
  queue-served (24 of 24 in A, 18 of 18 in B); H3's
  loaded served fraction is 1.0 and the served B runs'
  (gbt + prepare) median is 0.0 ms. Matches.
- Failed runs: 0 of 84; every run's record shows an
  accepted block with the EXP-036 verifier's
  block_candidate classification.
- Counter sums across the six prefetch session files
  reproduce the campaign totals exactly (section 4).
- Predeclaration integrity: sha256 of
  research/sha256d/exp051/PREDECLARATION.md is
  23db3912749fcbd185f20dc583e89131338a868419ea39066b997f
  0002b8aa07, identical to the value recorded in every
  campaign session manifest and quoted in the report.
  The 15 percent H2 margin, H1's zero-stale-serve hard
  gate and H3's attribution rule are all in that file,
  written as criteria, not fitted after the fact (the
  EXP-049 audit lesson is applied: the predeclaration is
  its own preserved file).
- Shakedown honesty: the two pre-amendment session files
  are preserved under RAW_RESULTS/shakedown/ and excluded
  from the analysis; the mempool contamination (575
  transactions, 75 foreign) and the harness amendment
  (mine until the mempool is empty before each scenario
  setup) are disclosed in the report and visible in the
  harness code (clear_mempool with a dated comment and a
  hard assert). One narrative imprecision is recorded as
  N-4.
- Stage labelling: the auditor confirmed in the EXP-040
  harness source that get_best_block_hash is booked under
  the "confirm" stage, so the report's reading note (the
  prefetch arm's confirm median carries the serve tip
  check; the headline wall-minus-search figure is
  unaffected) is accurate.

## 6. Suites (auditor's own runs, one at a time)

- make test-exp051: ALL PASSED, including the Gate 6
  real-node section (a queue-served block accepted by
  Core and EXP-036 verified; served 1, starved 1,
  enqueued 2 in that section).
- make test-exp034: PASSED (21 checks; blocks at heights
  2358 and 2359 accepted with matching coinbase values).
- make test-exp036: PASSED (12 checks).
- make test-template-cache: PASSED (block at height 2361
  through the production steps fast path).
- make test-exp037: PASSED.
- make test-mining: PASSED (production MiningEngine
  suite, the disabled-default path).
- make test-engine (the author's reported failure):
  PASSED on the auditor's rerun. Before running it the
  auditor confirmed the shared regtest chain was quiet
  (height 2361 unchanged over 45 seconds); the suite
  then synced 2,362 blocks to tip 2,361, satisfying the
  exact assertion that failed for the author
  (store.block_count() == tip + 1), and completed every
  section. The attribution is verified, not taken on
  trust: (a) the suite imports only blockchain.* and
  node.* (plus stdlib), nothing in this change's import
  graph; (b) its step 1 reads the tip AFTER sync_once()
  returns and asserts the store holds tip + 1 blocks, so
  any block landing around the sync leaves the store
  short by exactly the number of blocks that landed,
  which matches all three reported failure tuples
  (store, tip) of (2158, 2162), (2165, 2169) and
  (2331, 2333), shortfalls of 5, 5 and 3; (c) the shared
  chain is demonstrably mined by concurrent suites: the
  auditor's own six suite runs in this audit mined
  blocks at heights 2358 to 2367, and during the author's
  window an EXP-050 audit was running suites against the
  same node. Verdict on this item: environment
  interference on a shared chain, not a defect in this
  change, and not a defect in the suite's own logic
  beyond its known sensitivity to a moving tip.

Full test-all (42 targets) was not run by the auditor;
see the unverified register.

## 7. Registries

- Both markdown registries carry an EXP-051 record that
  agrees with the report on every figure (389.7 vs
  167.3 ms, 57.1 percent, served 42, starved 6,
  superseded 16, zero stale serves) and each ends with
  "Next unreserved ID: EXP-052."
- The Stage 0 JSON registry parses at 102 entries. The
  EXP-051 entry's status is PROVEN and its text agrees
  with the report. Entry-by-entry comparison against
  remote b8b01ed3: all 100 prior entries are present;
  the only prior entry whose content differs is R-26,
  and its delta is exactly EXP-050's own status update
  (NEW to INTEGRATED with its measured result and
  evidence), which belongs to the EXP-050 work, not to
  EXP-051. EXP-051 added exactly one entry and altered
  no prior entry.

## 8. Scans

27 files (all EXP-051 created or edited files: the three
production files, the test suite, the Makefile, the full
exp051 research tree including RAW_RESULTS, and the three
registries) were byte-scanned: U+2014 count 0; secret
patterns (PEM private keys, xprv, WIF-shaped strings,
rpcpassword assignments, GitHub token shapes, AWS key
shapes) 0 hits of any kind.

## 9. Live stack

Never restarted or signalled. Census from
evidence/mainnet-live.jsonl (full count): 614 accepted /
8 rejected before the audit, 617 accepted / 8 rejected
after; the +3 are the live miner's own pool shares during
the audit window. Balance 0 BTC, no block, as before.

## Notes

- N-1 (curtime refresh, cache-hit case; auditor probe
  P1): serve() refreshes the curtime of the QUEUED dict,
  but mine_cycle builds from the PreparedTemplate's own
  stored dict. When the queued entry is a TemplateCache
  hit, the prepared entry was constructed from an earlier
  dict of the same identity, and the built header then
  carries that earlier dict's curtime (clamped per build)
  rather than the refreshed value. The report's sentence
  that the served template's curtime is refreshed to
  exactly what a fresh GBT response would carry is
  therefore imprecise for the cache-hit case. The
  behaviour is safe: the tip is verified unchanged, so
  mintime (a function of the tip) is the same, and the
  header time lands inside [mintime + 1, now], consensus
  valid. No identity impact; the same aliasing exists on
  the pre-EXP-051 synchronous steps path (EXP-025 audit
  note N-2 recorded the by-reference shape). Recommend
  the report wording be corrected at the next touch, or
  the refresh applied to the prepared entry's dict as
  well.
- N-2 (mintime is the one uncovered build input;
  auditor probe P4): an in-process holder of the queued
  dict who rewrote its mintime after prepare would pass
  the identity check (mintime is outside the identity by
  design) and move build()'s clamp floor, hence the
  header time. The effect is confined to the time field;
  an absurd value yields a block Core rejects under its
  time rules (fail-visible, never a silently wrong
  candidate), and no production code writes mintime (the
  only template-field write in the tree is the serve-time
  curtime refresh). A node cannot mutate a dict it has
  already returned; the exposure requires a trusted
  in-process holder, the same trust boundary the EXP-025
  steps path already carries. Recorded for precision,
  not as a defect.
- N-3 (starvation counter granularity): prefetch_starved
  is recorded per mine_cycle serve attempt with no valid
  prepared work, which equals template transitions in the
  engine's own loop shapes and in the campaign (exactly
  the six warm-ups). A caller that re-enters mine_cycle
  repeatedly on an unchanged tip with an empty queue
  records one starved per entry. The predeclaration's
  wording ("transitions") and the implementation agree
  for every caller in the tree; the distinction is
  recorded so the counter is not over-read later.
- N-4 (shakedown narrative): the report says the first
  campaign attempt "completed scenario A" before dying at
  the first B setup; the preserved shakedown files are
  two partial scenario A session-0 files (2 and 3 runs).
  The disclosure itself is honest (files preserved,
  excluded, contamination stated, amendment visible in
  code); only the sentence overstates how far the first
  attempt got.
- N-5 (feed dedupe staleness): PrefetchFeed.run captures
  the current identity before its longpoll fetch and
  dedupes the answer against that capture. If the engine
  advances to new work during the fetch and the answer is
  that same new work, it is enqueued despite being the
  work now mined; the next transition then re-serves the
  same identity (both checks pass legitimately) and the
  engine re-searches it. That is duplicated work of the
  same shape the synchronous path produces after a budget
  exhaustion, never a wrong-identity serve. An efficiency
  nit only.
- N-6 (test-all): as with the EXP-049 and EXP-050
  audits, the auditor ran the change-surface suites
  rather than all 42 targets under load; a full test-all
  on this tree state remains outstanding.

## UNVERIFIED register

- Mainnet difficulty effect of the queue (claimed nil by
  the hypothesis, unmeasured; nothing in the report or
  this audit is a mainnet figure).
- The solo server seam (mining/solo_server.py
  JobRefresher): not wired, by the scope boundary the
  predeclaration declared in advance; the auditor
  confirms solo_server.py does not consume MiningEngine.
- Solo difficulty through this engine as a deployment
  shape, separately from the regtest GBT path measured
  here.
- Other hosts: the Intel Xeon 8321HC rotation has not run
  this mechanism; all figures are the AMD EPYC 9D25 host
  under contention.
- Long-run feed behaviour over days, including node
  restarts mid-longpoll; exercised only over campaign
  and audit hours.
- Full make test-all (42 targets) on this tree state.
- The live mainnet stack with prefetch enabled: the flag
  is off there by default and the pool path does not
  import the module (section 1); enablement on any live
  path is a separate gated decision.
