# EXP-057 report: stratum aggregation tier

Date: 2026-11-17. Experiment: EXP-057, portfolio
NOVA-ER-0017, register R-27. Predeclaration:
PREDECLARATION.md in this directory, sha256
3cf0ed03b65e220092603e75b16b26a9ad741f57ca4f3590d87177b5e923c01a,
written before the campaign ran and pinned in every
driver. Raw record: RAW_RESULTS/
(campaign_20261117T100445Z.json,
overhead_20261117T100544Z.json,
gate6_20261117T100554Z.json, gates.log).

## Verdict: ALL GATES PASS

By the predeclaration's verdict mapping, EXP-057 is
COMPLETE. Classification: **PROVEN** for the tier
properties measured on this VM: share validation
differentials against EXP-036 verify_candidate in
full, identity spoofing and stale work injection at
the predeclared worker counts (2, 4 and 8 downstream
workers on 1 upstream connection) with exact
accounting and zero upstream submissions, restart
behaviour in full, overhead in form against the
EXP-043 baselines, and one regtest block produced
through the tier (a second followed in the regression
suite).

This is not a fleet claim. Fleet activation (roadmap
F2) stays owner-gated, no other machine was contacted,
and the UNVERIFIED register at the end of this report
stands in full.

## What was built

- mining/aggregation.py (new production component,
  beside mining/solo_server.py and
  mining/coordinator.py): an AggregationTier holding
  ONE upstream SoloServer (its job construction,
  validate_share header reconstruction and EXP-036
  pipeline are the production code, reused, not
  reimplemented) and fanning the workbase out to
  downstream workers, plus an AggregationTCPServer
  speaking Stratum V1 (subscribe, authorize, submit,
  suggest_difficulty) whose submissions route through
  the same single judgment path as in-process calls.
- Fleet identity, the genuinely new work, inheriting
  EXP-035 and EXP-055 checks and not ckpool's open
  pool trust model: a worker exists only if the
  operator enrolled it (worker_id plus an enrollment
  token; only the token's SHA-256 hash is stored,
  compared in constant time); opening a session
  requires the fleet id to match, the worker to be
  enrolled and the token to match; a session binds
  exactly one worker to exactly one tier-assigned
  extranonce1 (the worker never chooses it, and every
  share is judged under the session's extranonce1);
  a share whose claimed worker differs from its
  session's worker is an identity rejection; sessions
  never survive a tier restart (the epoch bumps,
  workers re-authenticate).
- Submission authority stays OUT of the tier: the
  tier validates and accounts only. A verified block
  candidate is queued as a pending candidate and is
  never submitted by the tier on its own authority.
  The single submission path is
  operator_submit_pending: it requires the operator
  token and an explicitly configured upstream
  submitter, refuses with either missing, and
  re-verifies the candidate through EXP-036
  immediately before submitting, so nothing
  unverified can be submitted even there.
- Accounting is the EXP-037 separated statistics
  (MiningStatistics) plus the tier-local disjoint
  categories fixed in the predeclaration (accepted,
  below_target, invalid, stale, duplicate,
  unknown_job; identity failures counted only as
  identity_rejected and never entering
  pool_shares_submitted). assert_accounting_identity
  checks the predeclared identity globally and per
  worker against the EXP-037 snapshot.
- research/sha256d/exp057/: exp057_campaign.py
  (Gates 2, 3, 5), exp057_overhead.py (Gate 4),
  exp057_gate6.py (Gate 6).
- tests/test_exp057_aggregation.py behind a new
  Makefile target test-exp057; test-all becomes 47.
  Suite result: 9 checks, ALL PASSED. Neighbouring
  suites re-run after the build, one at a time:
  test-solo ALL PASSED, test-exp055 23 checks ALL
  PASSED. Production miner, autopilot, solo server,
  endpoint config and live stack untouched; the tier
  is additive and not deploying it is the rollback.

## Gate 2: share validation differentials

Randomised corpus against a synthetic workbase built
by the production SoloServer machinery (nBits at the
difficulty-1 target): 3,240 entries (3,000 random
submissions plus 240 constructed invalid entries:
80 bad extranonce2 size, 80 ntime before the template
mintime, 80 ntime too far in the future), plus 60
unknown-job entries counted apart. The tier's verdict
agreed with the direct verify_candidate verdict on
every entry: 3,240 of 3,240. Corpus tally by direct
verdict: 2,823 below_target, 177 share, 240 invalid.
Zero disagreements; the predeclared failure criterion
(any single disagreement) did not occur.

## Gate 3: identity spoofing and stale work injection

At each predeclared worker count (2, 4, 8 workers on
1 upstream connection), enrolled workers submitted a
fixed script (10 submissions each, one replayed
duplicate each, one stale submission each after a
workbase refresh) while the campaign injected seven
identity attacks: an unenrolled worker, a wrong
fleet id, a wrong token, a token belonging to another
worker, a session hijack claim (a share on one
worker's session claiming another worker's name), a
submission on a never-issued session, and a
submission on a closed session. Results:

| workers | authenticated submissions | accepted | below_target | duplicate | stale | unknown_job | identity rejected | upstream submissions |
|---|---|---|---|---|---|---|---|---|
| 2 | 25 | 0 | 20 | 2 | 2 | 1 | 7 | 0 |
| 4 | 49 | 0 | 40 | 4 | 4 | 1 | 7 | 0 |
| 8 | 97 | 5 | 75 | 8 | 8 | 1 | 7 | 0 |

Every spoof was rejected (7 of 7 at each count), zero
spoofed submissions were accepted, the harness tally
equalled the tier counters exactly at each count, and
the accounting identity held globally and per worker
(assert_accounting_identity). The upstream submitter
was a counting spy: it was never called, and
upstream_submissions stayed 0 throughout, as
predeclared. The portfolio failure criterion (any
identity or accounting gap) did not occur. The
accepted counts are share-target luck on random
nonces at the synthetic share difficulty (about 1 in
16 expected; 0, 0 and 5 observed), not a rate claim.

## Gate 4: overhead, in form against EXP-043 baselines

All figures are this VM (AMD EPYC 9D25, live miner and
node running), medians of 3 sessions, 300 submissions
per session:

| path | median |
|---|---|
| tier authenticated submit, in-process | 19.0 us |
| direct SoloServer submit (the wrapped path) | 12.3 us |
| tier stratum submit round trip, TCP loopback | 61.1 us |

Session medians: tier in-process 19.2, 12.4, 19.0 us;
direct 12.3, 7.9, 12.3 us; TCP 61.1, 50.7, 79.1 us.
Read against EXP-043: its prototype manager calls
cost 1 to 5 microseconds in-process and its loopback
wire shim floor was about 33 to 55 microseconds per
round trip at 1 worker. The tier's in-process submit
is the direct solo path plus session lookup, dedup
and accounting (about 1.5x the direct path here), and
its TCP round trip sits at the same order as the
EXP-043 shim floor. verify_candidate runs only on
candidate hits on both paths, as in production. No
scaling claim beyond this VM is made.

## Gate 5: restart behaviour

With 12 submissions accounted (1 accepted, 11
below_target) and a pending candidate planted for the
persistence check (labelled in the driver: it
exercises the persistence mechanics only; Gate 6
produces the real verified candidate), the tier was
snapshotted to a real state file and a new tier
restored from it. Required behaviour all held: the
epoch bumped 0 to 1; the pre-restart session was dead
(a submission on it was an identity rejection); the
accounting categories were preserved exactly; the
planted pending candidate survived; the dedup set
survived (a replayed share in a fresh session was
still a duplicate); and fresh work in the new session
was accounted, with the accounting identity holding
after the restart.

## Gate 6: regtest block through the tier

A downstream worker (gate6-w1) connected over TCP
stratum, authorized with its enrollment token, and
mined the tier's workbase with the production
ComputeEngine; a spoofed authorize with a wrong token
was refused before any mining. The winning share was
accepted by the tier as a verified block candidate
and queued: the chain tip provably did not move
(2,374 before and after the share), and
upstream_submissions stayed 0. A wrong operator token
was refused. Only then did the explicit operator
action (operator token plus the explicitly wired
SoloServer submitter) submit: height 2,375, hash
00000017d0df0340f2197b2eb1038090a4636cc718c83b2707d9d40bde1ebd6d,
submitblock accepted, verify_chain_acceptance
reported tip, height advanced exactly 2,374 to 2,375,
and the accounting identity held. The regression
suite re-ran Gate 6 end to end and produced the next
block the same way: height 2,376, hash
0000004076ca4ac71430b7e56fb9f5dd6c3731e575fadced73c6522693903e95.

## Judgment calls

- The tier's stratum extranonce1 is issued at
  authorize time (a mining.set_extranonce notice),
  not at subscribe time, because the extranonce1 is
  bound to the authenticated identity and identity
  does not exist until authorize. This is stated in
  the code and is the one deliberate deviation from
  the solo server's subscribe-time extranonce1.
- Gate 5's pending-candidate persistence is exercised
  with a planted record, labelled in the driver,
  because a real verified block candidate cannot be
  produced on the synthetic difficulty-1 workbase on
  demand; the persistence code path is identical, and
  Gate 6 produces and submits the real candidate on
  regtest through the same queue.
- Gate 3's legitimate-traffic accepted counts are
  left as observed (0, 0, 5): the campaign asserts
  accounting exactness, not a share rate, and no
  session was rerun to make the numbers prettier.
- The synthetic Gate 2 and 3 workbase uses a FakeRPC
  template source so the corpus is reproducible; the
  job construction, header reconstruction and
  verification under test are the production
  SoloServer and EXP-036 code, and Gate 6 runs the
  same tier against the real regtest node.

## Files

- mining/aggregation.py (new).
- research/sha256d/exp057/: PREDECLARATION.md,
  EXP057_REPORT.md, exp057_campaign.py,
  exp057_overhead.py, exp057_gate6.py, RAW_RESULTS/
  (campaign, overhead and gate6 JSONs of record,
  gates.log, gate5_snapshot.json as runtime state).
- tests/test_exp057_aggregation.py (new); Makefile
  (test-exp057 target; test-all 47).
- The three registries (EXP-057 entry; next
  unreserved ID EXP-058; EXP-052 stays reserved for
  NOVA-ER-0012 and EXP-056 for NOVA-ER-0016).

An independent audit is owed before any push, and it
should be adversarial on identity, as this is a new
trusted component on the share path. This build was
not pushed.

## UNVERIFIED register (stands in full)

- Multi-machine operation: UNVERIFIED. No other
  machine was contacted, activated or measured.
- Real-network latency and behaviour: UNVERIFIED.
  Loopback figures are this-VM figures.
- Real upstream pool behaviour (the tier facing a
  real third-party pool instead of the lab's own node
  and SoloServer machinery): UNVERIFIED and not
  attempted.
- Cross-machine scaling, real fleet behaviour, clock
  skew across machines, partial network failure:
  UNVERIFIED.
- Live deployment of the tier in the production
  mining path: UNVERIFIED and not attempted.
  Deployment and fleet activation are separate
  owner-gated steps (roadmap F2).
- Other hosts: UNVERIFIED. All measurement is the
  AMD EPYC 9D25 host.

## Defect-fix addendum (2026-11-17)

The independent audit (EXP057_AUDIT.md, PASS WITH
NOTES) found two defects outside the campaign scripts.
Both are fixed in mining/aggregation.py, with
regression tests in tests/test_exp057_aggregation.py.
Host: AMD EPYC 9D25. This addendum changes no
predeclaration, campaign result, gate verdict or
registry status; EXP-057 stays PROVEN.

- D-1 (identity lifecycle): a second mining.authorize
  on one TCP connection orphaned the previous session,
  which stayed in tier.sessions and could still judge
  shares in-process after disconnect. Fix, in
  _AggHandler._run: on a successful re-authorize the
  previous session is closed before the new session id
  is bound to the connection (closing the previous
  session was chosen over refusing a second authorize,
  the audit's first suggestion). Regression test
  regression_d1_reauthorize_closes_previous reproduces
  the audit scenario exactly: authorize as tcp-w1,
  re-authorize as tcp-w2 on the same connection,
  disconnect; it asserts the first session is closed at
  re-authorize, the orphaned session id raises
  IdentityError in-process, and tier.sessions is empty
  after disconnect (3 checks).
- D-2 (fail-closed, lossy): operator_submit_pending
  popped the pending candidate before the job lookup,
  the EXP-036 re-verification and the submitter call,
  so any failure permanently discarded a possibly
  genuine verified candidate. Fix, in
  AggregationTier.operator_submit_pending: peek at the
  candidate, re-verify, submit, and remove exactly
  that candidate (by identity) only after the
  submitter returns; a failed job lookup, a failed
  re-verification or a submitter exception retains it
  in the queue. Regression test
  regression_d2_failed_submit_retains_candidate
  asserts retention after a real re-verification
  failure (planted all-zero header, submitter never
  called), retention after a submitter exception, and
  removal only on a successful submit (3 checks; the
  exception and success paths patch verify_candidate
  at the module boundary for the queue test only,
  because the synthetic workbase cannot produce a
  network-target header on demand).

Verification, suites run one at a time on
2026-11-17: make test-exp057, 15 checks, ALL PASSED
(the 9 pre-audit checks plus the 6 new regression
checks; its Gate 6 produced regtest block height
2382); make test-solo, ALL SOLO SERVER TESTS PASSED
(block height 2383); make test-exp055, 23 checks, ALL
PASSED (Gate 6 block height 2384). Nothing was
pushed, and no live path was touched: the fixes are
confined to mining/aggregation.py, its regression
suite and this addendum.
