# Solo vardiff prototype: design (NOVA-ER-0004, register R-12)

Status: research prototype. Experimental implementation and
verification only. NO production code is modified by this work
and nothing here is integrated. The prototype lives entirely
under research/vardiff/ and imports the production solo server
(mining/solo_server.py) unchanged.

## 1. What this is

Register row R-12 (portfolio entry NOVA-ER-0004, EXP-030 matrix
row M10) records vardiff as a DECIDED design whose production
implementation is still open: adapt the solo server's share
difficulty toward a target share interval, with hysteresis (a
grace period) on increases, so the solo leg produces a stable
share flow for accounting at any worker rate instead of a flood
at low difficulty or silence at high difficulty.

Today the solo server serves ONE fixed difficulty to every
connection: SoloServer.share_difficulty, with the share target
computed once in the constructor as int(diff1 / difficulty).
This prototype implements the decided controller around that
server, per connection, without editing it.

Precedents studied in the historical register and followed
here in shape: ckpool's stratifier vardiff and the Bitaxe
difficulty controller (matrix M10: adapt to a target share
interval, grace period on increases).

## 2. Discrepancy D10 (documented, NOT fixed here)

Stage 0 reconciliation recorded a latent inconsistency: the
operative staged endpoint config serves share difficulty 0.02
(mining/endpoint_config.py, SOLO_SHARE_DIFFICULTY = 0.02,
consumed by mining/solo_mainnet.py), while the SoloServer
constructor default is 0.01 (mining/solo_server.py). The
running mainnet solo leg, when the armed cutover fires, gets
0.02 because the runner always passes the config value; the
0.01 default only bites a caller who constructs SoloServer
without arguments. This prototype does not change either
value. Its own declared initial difficulty is 0.02, matching
the operative config, and the Stage 6 integration path in
section 9 closes D10 by making the endpoint config the single
source and deleting the divergent default's authority.

## 3. Architecture

research/vardiff/vardiff.py contains three pieces:

1. VarDiffController: the pure control law. No I/O, no
   sockets, no production imports. Time is supplied by the
   caller on every event, so the law is deterministically
   testable under a simulated clock.

2. VarDiffSoloServer(SoloServer): subclasses the production
   server. It adds per-connection difficulty state keyed by
   extranonce1 (the per-connection value the production
   server already issues at subscribe), a bounded history of
   superseded jobs, an adjustment log, and stale/duplicate
   accounting. With vardiff_enabled=False it is a pinned
   constant-difficulty server whose submit_share delegates to
   the production method verbatim (the rollback surface, and
   the differential-test baseline).

3. VarDiffTCPServer + _VarDiffHandler: mirrors the production
   SoloTCPServer/_Handler pair (which hardcode each other, so
   a handler variant cannot be injected without a copy). The
   differences are exactly: connection registration at
   connect, the connection's own difficulty in the subscribe
   set_difficulty message, a set_difficulty notice after any
   submit that changed the connection's difficulty, a
   per-client set_difficulty ahead of each broadcast notify,
   and connection teardown at disconnect.

## 4. The control law (declared constants)

All values are constructor parameters of VarDiffController;
the defaults below are the prototype's declared operating
point, and every test run records the values it used.

- target_interval: 15.0 s. The declared target: one accepted
  share per connection per 15 s on average.
- initial difficulty: 0.02 (matches the operative endpoint
  config; see D10).
- floor: 0.002. ceiling: 1.0. Difficulty never leaves
  [floor, ceiling].
- Interval estimate: exponential moving average of accepted
  share intervals, alpha 0.35, seeded by the first interval.
- Deadband: no adjustment while the EMA sits inside
  [target / 1.25, target x 1.25] (at the 15 s target, the
  band is 12 s to 18.75 s). The band is what "holds the
  share interval" means in the portfolio success criterion:
  inside it the controller is deliberately silent, so the
  settled state does not hunt around the target. Adjustments
  aim back at the centre (the factor is computed against
  the target itself, not the band edge).
- Decreases (interval above target, miner too slow for the
  current difficulty): applied on the share event itself, no
  hysteresis. New difficulty = old x clamp(ema / target, 1,
  max_down_factor) inverted, i.e. divided by a factor of at
  most max_down_factor = 2.0 per adjustment.
- Increases (interval below target, shares arriving too
  fast): hysteresis on increases, per the decided design.
  An increase requires up_confirmations = 2 consecutive
  accepted-share evaluations with ema below target AND at
  least up_hysteresis_s = 30 s since the last increase.
  Each increase multiplies difficulty by at most
  max_up_factor = 1.5.
- Adjustment events: ONLY accepted-share events and job
  changes. Nothing adjusts on a timer, on a rejected share,
  or mid-job (see section 5).
- Idle decay: on a job change, if the connection's last
  accepted share (or its connect time, if it has never
  submitted) is older than decay_after_s = 60 s, difficulty
  steps down by decay_factor = 2.0 toward the floor, one
  step per job change. Declared window: from the initial
  0.02, the floor 0.002 is reached in at most 4 decay steps
  (0.02, 0.01, 0.005, 0.0025, 0.002) once the idle threshold
  has passed, i.e. after 60 s idle plus up to 4 job changes.
  Job changes are guaranteed by the production JobRefresher
  cadence (tip moves and a 120 s maximum job age), so a
  silent client decays to the floor without any timer in
  this prototype.
- Flooding: a client submitting faster than the target
  interval drives difficulty up by at most 1.5x per
  confirmed adjustment until the ceiling clamps it; clamp
  events are logged (once per distinct bound state, not per
  share).
- Reconnect: a new connection is a new extranonce1 and a new
  controller state at the initial difficulty. Nothing carries
  over.

## 5. Judging rules (exactness, EXP-036 separation)

- Difficulty is a share criterion only. It never enters
  candidate judging: block candidacy is decided solely by
  mining/candidate_verify.py's exact integer test against
  the job's network target, exactly as in production. This
  is the separation the portfolio entry names as the design's
  one mathematical obligation, and Gate 3 tests it directly
  (a share between the share target and the network target
  follows the identical path at every difficulty).
- A share is judged against the difficulty in force for the
  job it answers. When a job is issued (refresh or
  subscribe), the server snapshots each live connection's
  current difficulty against that job_id. Later adjustments
  never rewrite a snapshot, so an adjustment can never
  invalidate work already issued: in-flight work is always
  judged by the target it was issued under, and the new
  difficulty takes effect from the next job, which is also
  when the client is told (set_difficulty accompanies the
  broadcast notify and any post-submit notice).
- The share target is computed with the production formula,
  int(diff1 / difficulty), integer-exact and identical to
  mining/stratum_client.target_for_difficulty. Acceptance is
  the exact integer comparison value <= target
  (candidate_verify.meets_target semantics; equality meets).
- Stale shares: the production server forgets superseded
  jobs (a share for one is "unknown job"). The prototype
  retains the last 8 superseded jobs and classifies shares
  against them explicitly: a stale share is validated
  against its own job and its own snapshot, is NEVER counted
  as an accepted share, and is counted in the stale category.
  If it meets the network target it is still a genuine block
  candidate: it goes through the identical EXP-036 exact
  verification and submitblock pipeline, is recorded in
  blocks_found with stale=True, and counts as accepted only
  on chain confirmation, exactly like a current-job
  candidate. If it meets only its job's share target it is
  recorded stale-valid. Otherwise stale-low. A share for a
  job the server never issued (or has evicted) keeps the
  production verdict "unknown job".
- Duplicates: a repeated (job_id, extranonce2, ntime, nonce)
  tuple from the same connection is classified "duplicate"
  and counted in its own category. It is never counted as an
  accepted share, never as unique work, and never triggers
  an adjustment. (Production has no duplicate detection;
  this is an intentional, documented divergence of the
  vardiff accounting layer, active only in vardiff mode. In
  pinned mode the prototype is production-identical,
  duplicates included.)
- Rejected shares (below target, malformed, bad ntime)
  follow production exactly and never trigger adjustments.

## 6. Accounting (EXP-037 / EXP-038 rules preserved)

- Every adjustment appends one record to the server's
  adjustment log: timestamp, connection (extranonce1 hex),
  worker name when known, reason, old difficulty, new
  difficulty, the EMA interval that drove it, and a clamped
  flag when a bound limited the move. The log is a chain:
  each record's old equals the previous record's new for
  that connection. The test suite verifies completeness by
  replaying it.
- Share accounting keeps the production counters
  (shares_accepted, shares_rejected, per-worker accepted /
  rejected / blocks / block_candidates) and adds two
  disjoint categories, shares_stale and shares_duplicate,
  mirrored per worker. For any connection:
  submissions = accepted + rejected + stale + duplicate.
  No category is ever folded into another, and no combined
  "total work" figure is produced (the EXP-037 rule).
- Vardiff changes share granularity only. It assigns no
  nonce ranges, advances no frontier, and makes no coverage
  claim: mining/work_checkpoint.py's EXP-038 frontier rules
  (frontier advances only after a batch returns without a
  hit; coverage is exact positions examined) are untouched
  because the solo Stratum path's work separation is the
  server-issued job plus client-chosen extranonce2/nonce,
  exactly as before. A share, at any difficulty, is evidence
  about one position, never about a range.
- Repeated submissions are the duplicate category above:
  counted, never treated as unique work (the EXP-038 /
  mining_statistics separation of repeated_work and
  duplicate_deliveries from unique coverage, applied to
  share accounting).

## 7. Cost

The controller is O(1) per accepted share (one EMA update,
a few comparisons) and O(connections) per job refresh.
EXP-043 measured the in-process coordination verbs this
sits beside at 0.77 us (candidate submit) to a few us; the
vardiff additions are of that order and make no rate claim.
No performance benchmark is part of this task (Gate 4 does
not apply to NOVA-ER-0004: no hash rate is claimed).

## 8. Failure behaviour summary

- Silent client: decays to the floor per section 4.
- Flooding client: rises to the ceiling and clamps, logged.
- Disconnect/reconnect: fresh state at initial difficulty.
- Node not ready: inherited unchanged. refresh_job still
  raises SoloNotReady / ChainMismatch and the handler still
  refuses the subscription rather than serve unbacked work.
- Controller misconfiguration (floor > initial, initial >
  ceiling, non-positive targets) is refused at construction.

## 9. Stage 6 integration path (for the later, separate task)

This prototype is the evidence base, not the integration.
The exact path a later Stage 6 would take, in order:

1. Port VarDiffController into mining/solo_server.py as an
   optional SoloServer component: SoloServer gains a
   vardiff=None parameter; when None, behaviour is today's
   fixed difficulty bit for bit (the rollback surface).
2. Move per-connection state, snapshots, job history, stale
   and duplicate accounting into the server alongside the
   existing workers table; parameterise SoloTCPServer's
   handler class so _VarDiffHandler's three deltas
   (registration, per-connection set_difficulty, notice on
   adjustment) land in the production handler.
3. Close D10 in the same change: the endpoint config becomes
   the single source of the initial difficulty; the
   SoloServer constructor default is removed or aligned to
   read the same config, so no divergent default survives.
4. Configuration through mining/endpoint_config.py: target
   interval, floor, ceiling, hysteresis, decay, alongside
   SOLO_SHARE_DIFFICULTY (which becomes the initial value).
5. Gates before the armed cutover may use it: Gate 2
   differential against the pinned server on a scripted
   stream (this prototype's suite, ported to tests/), Gate 3
   adversarial (oscillation injection, rate steps, stale and
   duplicate floods), Gate 5 (server start, refresh, recovery
   with vardiff live), Gate 6 (regtest blocks accepted at
   adapted difficulties), then an independent audit per the
   standing post-integration rule. Rollback at every point:
   vardiff=None restores today's behaviour exactly, and the
   endpoint config is the rollback surface.
