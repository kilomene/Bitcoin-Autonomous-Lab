# EXP-057 independent audit: stratum aggregation tier

Auditor: independent (not the author). Date: 2026-11-17.
Host: AMD EPYC 9D25. Stated remote HEAD at dispatch:
10bdda4e09c4567e989acc62d916a375185fe463 (see note N-8:
the live remote advanced past it during this audit).
Predeclaration sha256 verified on disk:
3cf0ed03b65e220092603e75b16b26a9ad741f57ca4f3590d87177b5e923c01a,
matching the value pinned in the campaign, Gate 6 and
test drivers. Worker counts 2, 4, 8 predeclared and used.

## Verdict: PASS WITH NOTES, 2 defects

Every predeclared gate holds under independent re-run
and recomputation, and no spoofed submission was
accepted on any surface I could reach. Two defects
were found outside the campaign scripts, both in
lifecycle handling around the audited paths: a TCP
re-authorization orphans the previous session (D-1,
identity lifecycle; must be fixed before any
deployment of the tier), and the operator submission
path discards a pending candidate when re-verification
or submission fails (D-2, fail-closed, lossy). Neither
defect changes any gate result as predeclared, and
neither lets an unauthenticated or unverified share
through. Details and the full attack log follow.

## 1. Identity attacks (auditor's own, beyond the author's 7)

Storage and compare discipline, verified by inspection
and by dumping live state: the tier stores only the
SHA-256 hex of each enrollment token and of the
operator token; a snapshot of a live tier contains the
hashes and no plaintext token (checked for both a
worker token and the operator token). Token comparison
is hmac.compare_digest on the two fixed-length hex
digests, on both constant-time paths that exist:
open_session and operator_submit_pending (2 call sites,
no other comparison form in the module).

Attacks tried, all rejected unless stated:

- Case and encoding tricks against open_session:
  lowercased worker id, lowercased token, trailing
  space in worker id, leading space in token, fleet id
  in wrong case, fleet id with trailing space, empty
  worker id, empty token against a real enrollment,
  None token against a real enrollment, a Cyrillic
  homoglyph worker id, a worker id with an embedded
  NUL byte, and another worker's token. Every one
  raised IdentityError; zero sessions were issued.
- Cross-worker share misuse in-process: a share on
  worker w2's session claiming worker w1 was an
  identity rejection; a share on w1's own session was
  judged as w1 under w1's extranonce1.
- TCP stratum surface: submit before authorize refused
  (error 25); authorize as w1 with w2's token refused
  (error 24, connection closed); a legitimately
  authorized w1 connection submitting a share claiming
  w2 refused as a hijack claim, and the same connection
  could still submit as w1 afterwards (the session
  binding did not move). The session id is never
  transmitted on the wire and the handler binds the
  session to its own connection, so a session id cannot
  be presented over TCP at all.
- Extranonce1: three sessions (two for one worker, one
  for another) received three distinct extranonce1
  values; closing a session did not free its value for
  reuse (the sequence is monotonic); open_session has
  no extranonce parameter, so a worker cannot choose
  or fixate its slot. After a snapshot restore, the
  sequence continued (old session S1, restored tier
  issued S2 with a fresh extranonce1): no reassignment
  or collision across the restart epoch.
- Enrollment races: 16 threads enrolling the same
  worker id concurrently produced exactly one success
  and 15 ValueError refusals; a later re-enrollment
  attempt was also refused. Enrollment is atomic under
  the tier lock.
- Session fixation: session ids are tier-assigned and
  cannot be chosen by a worker (note N-1 on their
  predictability).
- Post-restart (epoch) reuse: a pre-restart session id
  submitted after restore was an identity rejection
  (see section 5).

One attack succeeded, and it is defect D-1 below: a
second mining.authorize on an already authorized TCP
connection orphans the first session.

## Defect D-1: TCP re-authorization orphans the previous session (identity lifecycle)

_AggHandler._run assigns self._session_id on each
successful mining.authorize without closing any
previous session, and _AggHandler.handle closes only
the final session id on disconnect. Reproduced live
against AggregationTCPServer on loopback: authorize
as tcp-w1 (session S2 in the probe tier), re-authorize
as tcp-w2 on the same connection (S3), disconnect with
a full close of the client file and socket: S3 was
closed, S2 remained in tier.sessions, and S2 still
judged a share in-process, credited to tcp-w1, after
its connection was gone. The single-authorize control
case cleaned up correctly (no sessions remained after
disconnect).

Impact, stated precisely: over the current TCP
surface the orphaned id cannot be presented (the
protocol never carries session ids), so no external
spoofed accept was demonstrated. The gap is real
regardless: sessions accumulate without bound on
repeated authorize, a session outlives the connection
and the disconnect that should have ended it, and the
orphaned id remains a live bearer credential for any
in-process caller (see N-1). For a component whose
whole claim is exact session lifecycle, this must be
fixed before deployment: close the previous session
on re-authorize (or refuse a second authorize on one
connection), with a regression test in the suite.

## 2. Submission authority

The tier cannot submit upstream on its own, verified
three ways. (a) Code: the only submitter call site is
operator_submit_pending; submit_share and the stale
path queue candidates and never call it. (b) Campaign
recomputation and my own variant (section 4): the
counting spy was never called and upstream_submissions
stayed 0 while candidates and shares flowed. (c) My
own authority probes on a fresh tier: operator submit
with an empty queue raised and submitted nothing;
with no submitter configured it refused; with no
operator token configured it refused; with a wrong
operator token it refused and retained the candidate.

Re-verification before submission is real: I planted
a tampered candidate (an all-zero 80-byte header,
labelled planted) behind a correct operator token and
a counting submitter; operator_submit_pending raised
on re-verification (zero-target), the submitter was
never called, and upstream_submissions stayed 0.
Nothing unverified can be submitted through the sole
path, as the report claims.

## Defect D-2: operator_submit_pending discards the candidate on failure (fail-closed, lossy)

operator_submit_pending pops the pending candidate
before the job lookup, the EXP-036 re-verification and
the submitter call. Any failure after the pop (failed
re-verification, proven in my probe above: the planted
candidate was gone afterwards; a candidate whose job
has left the bounded history; a submitter exception)
permanently discards a candidate that may have been a
genuine verified block. The failure direction is safe
(nothing unverified is ever submitted), but a real
block candidate can be silently lost on a transient
failure. Fix: peek, re-verify, submit, and remove only
on success (or requeue on failure), with the behaviour
pinned by a test.

## 3. Gate 2 differentials, auditor's fresh seeds

I reran a differential subset with a fresh seed the
author did not use (424242): 750 unique entries (600
random, 50 bad extranonce2 size, 50 ntime before
mintime, 50 ntime too far in the future) plus 20
unknown-job submissions. The tier's verdict equalled
the direct verify_candidate verdict, mapped through
the tier's stated mapping, on 750 of 750 (tally by
direct verdict: 558 below_target, 42 share, 150
invalid); every unknown-job submission was classified
unknown_job and rejected. The accounting identity held
afterwards. This matches the campaign of record
(3,240 of 3,240, plus 60 unknown-job entries counted
apart, which I recomputed from the campaign JSON).

## 4. Accounting exactness

assert_accounting_identity is real, not decorative.
Direct tampering is caught: adding 1 to the global
accepted counter made the assert fail, and recording
an extra per-worker pool_shares_submitted in the
EXP-037 statistics made it fail again (both restored
afterwards). Organic divergence attempts stayed exact:
a duplicate share, the same share tuple presented by
a different worker (correctly not a duplicate: the
extranonce1 differs, so the header differs), a stale
share after a workbase refresh, and a submission on a
closed session (identity rejection, never entering
pool accounting) left the global identity and the
per-worker reconciliation exact, and the EXP-037
pool_shares_submitted total equalled the sum of the
six tier categories at every step.

Gate 3 tallies recomputed from
campaign_20261117T100445Z.json: at 2, 4 and 8 workers
the harness tallies equal the report table exactly,
the authenticated submission totals are 25, 49 and 97
(each the sum of its six categories and equal to the
recorded EXP-037 pool_shares_submitted), identity
rejections are 7 at each count, and the driver's spy
assertion (upstream submissions 0) is in the code path
that produced the file. My own Gate 3 variant at 4
workers with a fresh seed (777) reproduced the shape
independently: 7 identity rejections, 49 authenticated
submissions, exact accounting (the accepted versus
below_target split moved with the seed, 2 and 38,
which is the predeclared share-target luck, not a
discrepancy).

## 5. Gate 5 snapshot and restore

The planted-candidate disclosure is honest. The
campaign driver labels the record in code
(verify_reason planted-for-persistence-test, with a
comment stating it exercises persistence mechanics
only), the report discloses it in the Gate 5 section
and again in the judgment calls, and the preserved
record in RAW_RESULTS/gate5_snapshot.json carries the
same planted label and an all-zero header that could
not be mistaken for a verified candidate. Gate 6
covers the real candidate (section 6).

My own restore probe (fresh snapshot, fresh tier):
epoch bumped 0 to 1; the pre-restart session was dead
(identity rejection on submit); the session and
extranonce sequences continued without reuse; a
replayed pre-restart share in a fresh session was
still a duplicate (dedup set survived); the planted
pending candidate survived with its label intact; the
snapshot file contains token hashes only, no
plaintext; the accounting identity held after restore.
A second restore from the same snapshot also landed
at epoch 1, as the design states.

## 6. Gate 6 regtest block, verified on chain

Block 2375 exists on the lab regtest chain with hash
00000017d0df0340f2197b2eb1038090a4636cc718c83b2707d9d40bde1ebd6d
(getblockhash 2375 returned exactly that hash during
this audit; getblockheader showed height 2375 with
confirmations). The gate6 JSON of record
(gate6_20261117T100554Z.json) records tip_before 2374
and tip_after 2375 with chain_status tip and
upstream_submissions 1: the tip did not move while
the candidate queued (the driver asserts the count
before and after the winning share, with the tier's
upstream count at 0) and moved exactly +1 on the
operator action. The regression-form JSON
(gate6_20261117T100655Z.json) shows the same shape for
block 2376, and my suite re-run added block 2379 the
same way, again +1 with the tip unmoved while queued.

## 7. Safety and production diff

Nothing in the live paths imports the tier: a search
over mining/ found aggregation referenced only by
mining/aggregation.py itself. The live endpoint config
(.local/mining-endpoint.json) still carries its
2026-11-14 mtime; mining/solo_server.py,
mining/mainnet_live.py, mining/endpoint_config.py and
mining/autopilot.py are byte-identical to the stated
HEAD (see the diff below). All test and campaign
traffic was loopback (127.0.0.1) or in-process.

Blob-level diff of the whole local tree against the
tree of 10bdda4e (1,253 entries, not truncated), with
the standing exclusions (evidence/mainnet-live.jsonl,
bal-miner, the .so/.o artifacts under exp032, exp041
and exp044): differences are exactly the allowed set
(mining/aggregation.py, research/sha256d/exp057/ in
full, tests/test_exp057_aggregation.py, Makefile, and
the three registries) plus the EXP-055 runtime state
files listed in note N-8. No production code outside
the allowed set differs.

## 8. Suites (run one at a time, in this order)

- make test-exp057: 9 checks, ALL PASSED (including a
  fresh Gate 6 block at height 2379 through the tier).
- make test-solo: ALL SOLO SERVER TESTS PASSED.
- make test-exp055: 23 checks, ALL PASSED.

No shared-regtest contamination was observed; the
three suites advanced the shared chain sequentially
(heights 2379, 2380, 2381) without interference.

## 9. Registries, Makefile, scans

- JSON registry (research/EXTREME_RESEARCH/
  EXPERIMENT_REGISTRY.json): 106 entries; EXP-057 is
  present with status PROVEN; the last entries run
  EXP-050, EXP-051, EXP-053, EXP-054, EXP-055, EXP-057.
- The two markdown registries: the EXP-057 append is
  byte-identical between them (compared from the
  EXP-057 record heading to end of file), and each
  closes with next unreserved ID EXP-058, with EXP-052
  reserved for NOVA-ER-0012 and EXP-056 for
  NOVA-ER-0016, as required.
- Makefile: test-all lists 47 targets, ending with
  test-exp057; the test-exp057 target runs the suite
  above.
- U+2014 count over the EXP-057 set, aggregation.py,
  the test file, the Makefile and the registries: 0.
- Secret scan over the same set (key material,
  credential patterns): 0 hits. No token or credential
  value appears in any audited file; campaign files
  use the synthetic tokens of the experiment itself.

## Notes

- N-1: Session ids are sequential and predictable
  (S1, S2, ...), and in the in-process API the session
  id alone is the bearer credential for submit_share
  (possession of a live id judged a share in my probe,
  credited to its bound worker). The TCP surface
  mitigates this today (ids are never transmitted and
  sessions are bound to connections), but combined
  with D-1 a leaked id stays usable after disconnect.
  Any future transport must treat the id as a secret
  or replace it with an unguessable value.
- N-2: enroll_worker accepts an empty token: a worker
  enrolled with the empty string can open a session
  with token None or empty (both hash to the empty
  token's digest). This is an operator-error edge, not
  a spoof of a properly enrolled worker, but enrollment
  should refuse empty or short tokens. Relatedly, the
  stored hashes are unsalted SHA-256, so a leaked
  snapshot file exposes weak tokens to fast offline
  guessing; enrollment tokens must be high-entropy.
- N-3: Type confusion at the in-process boundary:
  open_session with an int or bytes token raises
  AttributeError (from _hash_token) instead of
  IdentityError, and is not counted as an identity
  rejection. The TCP layer coerces parameters to str,
  so the stratum surface is unaffected; the in-process
  API should still fail in its own exception type.
- N-4: open_session error messages distinguish foreign
  fleet, unenrolled worker and token mismatch, and the
  fleet and enrollment checks run before the token
  compare, so a prober learns which stage failed. No
  accept path results; recorded as an information
  disclosure note for a future networked deployment.
- N-5: The dedup key is (worker, job, extranonce2,
  ntime, nonce) and does not include the session or
  extranonce1: the same tuple replayed by the same
  worker under a new session (new extranonce1, hence
  a different header) is classified duplicate, and an
  invalid submission consumes its dedup slot before
  validation. Both directions fail closed (rejection),
  accounting stays exact, and no accept results.
- N-6: In the stale path, a verified network-target
  hit records candidates and network_target_candidates
  but not valid_candidates, where the current-job path
  records all three. The predeclared accounting
  identity (pool sums, globally and per worker) is
  unaffected and the assert does not cover this
  EXP-037 category; recorded for vocabulary exactness.
- N-7: The TCP handler lets socketserver print a
  traceback (BrokenPipeError, ConnectionResetError)
  when a client disconnects abruptly. Session cleanup
  still ran in the single-authorize case; cosmetic.
- N-8: Two tree-state observations. (a) The local tree
  differs from 10bdda4e in EXP-055 runtime state files
  (RAW_RESULTS/gate5_state/ and gate6_state/ journals
  and snapshots, plus a new gate6 record at
  20261117T100719Z): these are regenerated every time
  the EXP-055 suite runs (the author's neighbour runs
  before this audit, and my own test-exp055 run during
  it, which added a further gate6 record). They are
  evidence-state churn, not code, and a scoped EXP-057
  push must exclude them. (b) The live remote HEAD
  moved past 10bdda4e during this audit (per-file
  commits, for example 083ea0d9 at 2026-11-17T10:15Z
  updating an EXP-055 gate5 state file): push activity
  was in flight concurrently, so the diff in section 7
  is stated against the dispatched HEAD 10bdda4e, as
  instructed. The parent should confirm the final push
  set explicitly.
- N-9: Gate 4 overhead was checked in form only: the
  overhead JSON's session medians reproduce the
  report's figures (tier in-process 19.0 us, direct
  12.3 us, TCP 61.1 us) and sit at the EXP-043 orders.
  I did not re-measure timing on this shared-CPU VM;
  no verdict rests on the exact figures.

## UNVERIFIED register (auditor's own)

- Multi-machine operation, real-network behaviour,
  clock skew and partial failure: UNVERIFIED (inherited
  from the predeclaration; nothing in this audit
  contacted another machine).
- The tier facing a real third-party upstream pool:
  UNVERIFIED and not attempted.
- Live deployment of the tier in the production mining
  path, and fleet activation: UNVERIFIED and not
  attempted; both stay owner-gated.
- Other hosts, including Intel: UNVERIFIED. All work
  here is the AMD EPYC 9D25 host.
- Gate 4 exact timing figures: not independently
  re-measured (N-9).
- Behaviour under sustained concurrent TCP load
  (many simultaneous connections racing submits and
  refreshes): probed only at small scale in-process
  (enrollment race, section 1); a dedicated contention
  campaign is UNVERIFIED.
- The D-1 fix and any regression test for it:
  UNVERIFIED, not yet written; this audit does not
  modify production code.

## Bottom line

The predeclared claims survive adversarial checking:
identity held against every spoof I could construct
on the surfaces the campaign defines, accounting is
exact and the identity assert has teeth, submission
authority is genuinely outside the tier, and a real
regtest block flowed through it. PASS WITH NOTES,
2 defects (D-1 session orphaning on re-authorize,
D-2 lossy operator submission pop), 9 notes. D-1
should be fixed, with a regression test, before the
tier is deployed anywhere; whether it also blocks
the push of this research record is the parent's
call, since no gate as predeclared is affected.
