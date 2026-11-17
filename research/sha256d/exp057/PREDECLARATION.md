# EXP-057 predeclaration (written before the campaign runs)

Written: 2026-11-17, before any EXP-057 campaign, overhead
or regtest measurement was taken. This file's sha256 is
pinned in the campaign and Gate 6 drivers and in the test
suite. EXP-057 is portfolio NOVA-ER-0017 (register R-27):
a stratum-speaking aggregation tier. It is built strictly
after EXP-055 (NOVA-ER-0015) because worker identity and
leases are F1 semantics; the identity model here inherits
the EXP-035 and EXP-055 fleet checks (fleet id binding,
per-worker registration, rejection of foreign fleets) and
not ckpool's open pool trust model.

## Question and hypothesis

Can a stratum-speaking aggregation tier hold few upstream
connections, fan workbases out to fleet workers, validate
every share through EXP-036 verify_candidate, and keep
per-worker accounting through EXP-037, without becoming a
trust hole?

Portfolio hypothesis: the solo server's job and validation
machinery generalises to the aggregation role; the
genuinely new work is fleet identity.

## Design fixed here

- The tier is a new production component,
  mining/aggregation.py, beside mining/solo_server.py and
  mining/coordinator.py. It wraps one SoloServer instance
  as its workbase and validation engine (job construction,
  validate_share header reconstruction, and the EXP-036
  pipeline are the production code, not a reimplementation)
  and fans the resulting workbase out to downstream
  stratum workers. Upstream connection count in every
  measurement here: exactly 1 (the tier's one SoloServer
  facing the node). Downstream worker counts are
  predeclared below.
- Fleet identity (the new work): a worker exists only if
  the operator enrolled it (worker_id plus an enrollment
  token; the tier stores only the token's SHA-256 hash).
  Opening a session requires the fleet id to match, the
  worker to be enrolled, and the token to match under a
  constant-time compare. A session binds exactly one
  worker to exactly one tier-assigned extranonce1; the
  worker never chooses its extranonce1, and every share
  is judged under the session's extranonce1. Sessions do
  not survive a tier restart (the epoch bumps and workers
  re-authenticate), inheriting the EXP-055 restart rule.
- Submission authority stays OUT of the tier: the tier
  validates and accounts only. A verified block candidate
  is queued as a pending candidate and is NEVER submitted
  by the tier on its own authority. The single submission
  path is an explicit operator action
  (operator_submit_pending) requiring the operator token
  and an explicitly configured upstream submitter; with
  no submitter configured the call refuses. The fault
  campaign asserts the upstream submission count is zero
  throughout, including while verified block candidates
  sit queued.
- Accounting is EXP-037 separated accounting
  (mining/mining_statistics.py MiningStatistics) plus a
  tier-local disjoint category set. Definitions, fixed
  here so Gate 3 exactness is decidable: an authenticated
  submission increments exactly one of accepted,
  below_target, invalid, stale, duplicate, unknown_job;
  pool_shares_submitted in the EXP-037 snapshot equals
  the sum of those six; identity failures increment only
  identity_rejected and never enter pool_shares_submitted;
  stale and duplicate also increment the EXP-037
  stale_reports and duplicate_deliveries counters;
  verify_candidate calls increment verification_hashes;
  verified shares and block candidates increment
  valid_candidates; block candidates increment
  network_target_candidates and candidates;
  blocks_submitted, blocks_accepted and blocks_rejected
  move only inside operator_submit_pending. Per-worker
  EXP-037 breakdowns must reconcile exactly with the
  tier-local per-worker counters.
- Rollback: the tier is additive. Nothing in the live
  mining paths imports it; workers return to direct
  endpoints by configuration. The live miner, autopilot,
  solo server and endpoint config are untouched.

## Predeclared worker counts

Fan-out points, fixed in advance: 2, 4 and 8 downstream
workers on 1 upstream connection. Gate 3 runs its exact
accounting scenario at each of the three counts. Gate 6
runs 2 workers over TCP stratum on regtest.

## Gates, fixed in advance (Gate 1 does not apply)

- Gate 2 (share validation differentials, in full): a
  randomised corpus of share submissions (valid shares,
  below-target submissions, and invalid submissions:
  bad extranonce2 size, ntime before the template
  mintime, ntime too far in the future, unknown job)
  against a synthetic regtest-shaped workbase whose
  nBits is the difficulty-1 target, so block candidacy
  is decidable but rare. For every corpus entry the
  tier's verdict (accepted or not, and its category)
  must equal the verdict obtained by calling
  verify_candidate directly on the header the tier
  reconstructed (the EXP-036 classification mapped
  through the tier's stated mapping: block_candidate
  and share accept; below_target and invalid reject).
  Corpus size predeclared: at least 3,000 entries, of
  which at least 200 are constructed invalid entries.
  Any single disagreement is a Gate 2 failure.
- Gate 3 (identity spoofing and stale work injection,
  in full): at each predeclared worker count (2, 4, 8),
  enrolled workers submit a fixed script of valid and
  invalid shares while the campaign injects: an
  unenrolled worker, a wrong fleet id, a wrong token, a
  token belonging to another worker, a session hijack
  (one worker presenting another worker's session id),
  a replayed duplicate share, a share for a superseded
  job after a workbase refresh (stale injection), a
  share for an unknown job, and a share submitted after
  its session was closed. Success requires: every
  spoof rejected, zero spoofed submissions accepted,
  exact accounting (the identity in the design section
  holds globally and per worker), and zero upstream
  submissions for the whole campaign. FAILURE
  CRITERION, predeclared (portfolio): any identity or
  accounting gap in the campaign is a failure of the
  whole experiment; it is recorded honestly, not edited
  away.
- Gate 4 (overhead, in form against EXP-043 baselines):
  per-share cost of the tier's authenticated submit
  path in-process, and the stratum submit round trip
  over TCP loopback, medians of 3 sessions, reported
  beside the EXP-043 loopback figures (wire shim floor
  about 33 to 55 microseconds per round trip at 1
  worker; prototype manager calls 1 to 5 microseconds).
  No scaling claim beyond this VM is permitted.
- Gate 5 (restart behaviour, in full): with shares
  accounted and a verified candidate pending, the tier
  is snapshotted to a real state file and a new tier is
  restored from it. Required: the epoch bumps; every
  pre-restart session is dead (submissions on it are
  identity rejections); accounting counters, the dedup
  set (a replayed share is still a duplicate) and the
  pending candidate survive exactly; a fresh session
  can submit and be accounted after the restart.
- Gate 6 (regtest blocks through the tier): a fresh
  regtest block whose winning share was submitted by a
  downstream worker to the tier over TCP stratum,
  validated by the tier through verify_candidate
  (regtest limit), queued with the chain tip provably
  unmoved, and then submitted only by the explicit
  operator action; the block counts only when the node
  holds it on its active chain
  (verify_chain_acceptance) and the height advanced by
  exactly one.

## Verdict mapping, predeclared

- ALL GATES PASS: EXP-057 is COMPLETE, classification
  PROVEN for the tier properties measured on this VM
  (validation differentials, identity and accounting
  exactness at 2, 4 and 8 workers, restart behaviour,
  one regtest block through the tier), with overhead
  recorded in Gate 4 form. This is not a fleet claim:
  fleet activation (roadmap F2) stays owner-gated, no
  other machine was contacted, and the UNVERIFIED
  register below stands in full.
- ANY GATE FAILS, including any single identity or
  accounting gap at Gate 3: EXP-057 is recorded as
  FAILED with the failing gate and evidence, and the
  tier is not proposed for any deployment. A defect
  found and fixed during the build, before the
  campaign of record runs, is ordinary build work and
  is recorded in the report's judgment calls; a defect
  found by a gate is a gate failure unless the gate's
  own text above says otherwise.

## Hard lines and scope

- No other machine is contacted; workers are loopback
  and in-process on this VM only. Fleet activation is
  owner-gated (roadmap F2) and is not performed.
- Submission authority stays out of the tier in every
  live path: the only submission call is the explicit
  operator action, exercised in this experiment only
  inside Gate 6 on regtest.
- Exact SHA-256d only; no consensus property is
  touched; Gate 6 runs on regtest only.
- Production files are untouched except by addition:
  mining/aggregation.py is new, and the Makefile and
  the three registries gain the EXP-057 entries.
- Host: AMD EPYC 9D25 (confirmed from /proc/cpuinfo at
  build start). No GPU exists and none is claimed.
  Results on other hosts are UNVERIFIED.

## UNVERIFIED register (predeclared, stands regardless of outcome)

- Multi-machine operation: UNVERIFIED. No other machine
  is contacted, activated or measured.
- Real-network latency and behaviour: UNVERIFIED.
  Loopback figures are this-VM figures.
- Real upstream pool behaviour (the tier facing a real
  third-party pool instead of the lab's own node and
  SoloServer machinery): UNVERIFIED and not attempted.
- Cross-machine scaling, real fleet behaviour, clock
  skew across machines, partial network failure:
  UNVERIFIED.
- Live deployment of the tier in the production mining
  path: UNVERIFIED and not attempted; deployment and
  fleet activation are separate owner-gated steps.
- Other hosts: UNVERIFIED. All measurement is the
  AMD EPYC 9D25 host.
