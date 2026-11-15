# EXP-035: Distributed CPU Agent Architecture

## Work Distribution Design: Work Lease Manager, Distributed
## Agent Coordinator, Candidate Queue

Status: DESIGN plus research prototype, controlled local
testing complete. Nothing in this document is integrated
into production, and no fleet agent has been activated.
Directive basis: EXP-030 directive record section 8
(EXP-035), section 12 components 8, 10 and 11. Inputs:
EXP-029 (proven allocator core), the EXP-030 Phase B gap
analysis (all three components MISSING in production),
and the Phase A translation matrix rows M04, M06, M12,
M13, M14, M15, M26, M27, M31, M34.

## 1. What is missing today, and what this design adds

Production today has no leases, no coordinator and no
candidate queue. Each agent mines its own checkout; the
only separation between two GBT-path engines with the
same payout address is convention, and both would step
extranonces from 0 over identical coinbases and perform
identical header work (gap analysis, component 10).
Candidates are handled synchronously inline, so a crash
between discovery and submission loses a candidate
without a trace (component 11). There are no work-state
checkpoints, so a restart restarts coverage from nonce 0
and extranonce2 0, and the repeated work is neither
prevented nor accounted (component 19).

This design adds three components:

- **Work Lease Manager** (component 8): owns the declared
  search space of one job, partitions it into chunks,
  issues exclusive leases with identities, fencing tokens
  and deadlines, tracks progress positions, and accounts
  unique, actual and repeated work separately.
- **Distributed Agent Coordinator** (component 10): owns
  the worker registry, fleet identity checks, heartbeat
  and telemetry timeouts, failure detection, reclaim and
  reassignment, stealing, stale-job cancellation, and
  the persistent coordinator state. One coordinator is
  the single point of exact verification and submission
  (matrix M13): workers report candidates, the
  coordinator re-verifies, only the coordinator submits.
- **Candidate Queue** (component 11): a persistent,
  deduplicating buffer between candidate discovery and
  the EXP-036 Exact Candidate Verifier, so no candidate
  can be lost silently between a worker finding it and
  the verifier judging it.

## 2. The search space: leases are not nonce division

Dividing the 32-bit nonce range does not exhaust mining,
and this design never models it that way (directive
section 8, matrix M34). A job's declared search space is
a set of **slices**. One slice is the Cartesian factor:

    (extranonce2 value) x (version variant) x (ntime value)
    x nonce range [0, 2^32)

- **Extranonce2** is partitioned by worker, Qaxe style
  (matrix M06): `extranonce2 = (slot << 25) | counter`,
  7 bits of worker slot (up to 128 workers) and 25 bits
  of per-slot counter. Each distinct counter value gives
  a distinct coinbase, hence a distinct merkle root,
  hence a fresh nonce space. A worker is bound to one
  slot per job and can only lease slices inside its own
  slot, so the coinbase dimension is disjoint across
  workers by construction, not by trust.
- **Version rolling** uses only permitted variants: the
  BIP320 version mask applied to the template's version,
  enumerated as an explicit variant list in the job
  declaration. Variants outside the mask are not part of
  the space and are never leased.
- **Timestamp rolling** uses an explicit ntime list per
  job: the template's ntime plus permitted forward steps
  within consensus and pool rules (ntime must exceed the
  median time past and stay within the allowed future
  window; the template manager, EXP-034, owns computing
  the permitted list). The lease manager treats the list
  as opaque declared values.
- **Merkle-root changes** enter the space through the
  extranonce2 counter (each counter value rebuilds the
  coinbase and the merkle root, EXP-034's job engine)
  and through template replacement, which declares a new
  job with a new generation rather than mutating the old
  space.

Coverage claims are made only over a declared space:
"the fleet covered X" means the union of completed
chunks equals a named job's declared slice set, with the
job's variant and ntime lists on record. Expanding any
dimension declares more space; it never redefines work
already counted.

## 3. Jobs and generations

A job declaration carries: job_id, a monotonically
increasing **generation** (the EXP-034 job generation
identifier), the template identity, the slice dimensions
of section 2, the nonce count and the chunk size.
Declaring a new job supersedes the old one: outstanding
leases of the old generation die immediately, and any
late report against them is rejected as STALE by token
(section 5). This is the generation tag the matrix (M04)
requires on top of the reference firmwares' slot
registries, whose recycled slots can misattribute a late
result to the wrong job (weakness W3). NOVA job identity
is (job_id, generation); a bare slot or job_id is never
an identity.

Jobs are immutable once declared (M05): consumers hold
copies or references to a job record, never the registry
entry, and reconstruction of any candidate's exact header
from its job record is the EXP-034/036 contract.

## 4. The worker registry

The coordinator keeps a persistent registry of workers:

- **Identity**: a unique worker id (the existing
  hostname-derived Stratum identity is the seed of it)
  plus the fleet identity it must present on
  registration. A registration presenting a foreign fleet
  identity is rejected and logged (M14, the Qaxe CAN
  master's foreign-fleet check). Foreign work is never
  leased and foreign candidates are never queued.
- **Record per worker**: registered_at, last heartbeat,
  last lease time, slot binding per job, restart count,
  failure state, and last completed work position (the
  highest completed chunk identity per job), which is
  what a recovering coordinator or a re-registering
  worker reconciles against.
- **Liveness**: workers heartbeat to the coordinator;
  the telemetry timeout is of the 10 second class (M14).
  A worker past the timeout is stale: its leases are
  reclaimed (section 6) and it must re-register before
  leasing again.
- **Starvation**: a worker that holds no lease for
  longer than the starvation window must re-register
  before it can lease again (M15, the Qaxe slave's
  re-registration rule). Re-registration restarts its
  starvation clock. This prevents a worker that lost
  contact from silently mining stale work when it comes
  back: its old leases are gone and its old tokens dead.
- **Failure domains** (M26): each worker is its own
  failure domain, and each VM is a failure domain above
  its workers. A fault in one worker reclaims only that
  worker's leases; nothing in the design lets one
  worker's fault silently include another's work.

## 5. Leases: identity, fencing, lifecycle

A lease is the unit of exclusive work assignment:

    lease = { lease_id, fencing_token, epoch, worker_id,
              job_id, generation, slice coordinates
              (slot, counter, extranonce2, version, ntime),
              nonce lo, nonce hi, issued_at, deadline,
              state }

- **lease_id** is unique per issuance, forever.
- **fencing_token** comes from one monotonically
  increasing coordinator counter. Every issuance,
  including a re-lease of a reclaimed chunk and both
  products of a steal, carries a fresh token. Progress
  and completion reports must present the lease's current
  token. A report with a token that is not current, from
  a lease that is no longer active, or from before a
  coordinator restart (epoch mismatch), is rejected as
  STALE and counted. A report with the current token but
  the wrong worker identity is rejected as NOT_HOLDER
  and counted. A report naming a completed lease is
  DUPLICATE (section 7).
- **Lifecycle**: pending chunk, leased (active),
  completed, or reclaimed (back to pending). A chunk is
  in exactly one state at any instant, and is leased to
  at most one worker at any instant. This is the EXP-029
  partition invariant, kept.
- **Progress**: workers report cumulative examined
  counts per lease. Progress is the only basis for
  steal decisions and for repeated-work accounting; it
  never creates coverage. Only completion creates
  coverage, and only for the chunk's full current size.
- **Deadline**: every lease has one (a TTL from
  issuance). A lease past its deadline is reclaimable
  even if its worker is heartbeating, which bounds the
  damage of a worker that is alive but stuck.

## 6. Expiry, reclaim, death and restart

Four events return a leased chunk to pending, all
through one reclaim path:

1. **Worker death** (detected by heartbeat timeout, or
   reported by the Worker Supervisor, EXP-038).
2. **Lease expiry** (deadline passed).
3. **Worker restart notice**: the supervisor knows when
   a worker process restarts, so the coordinator
   reclaims immediately rather than waiting for the
   timeout. The restarted worker must re-register; it
   holds no valid token for its pre-restart leases.
4. **Coordinator restart**: leases never survive it.
   The coordinator restores completed coverage,
   accounting and the token counter from its snapshot,
   bumps its epoch, and reclaims every outstanding
   lease. Workers re-register (M15) and lease afresh.

On every reclaim, the chunk's reported progress is moved
into its examined_before count. When the chunk is
re-leased, that count is added to repeated computations
and the re-examination adds to actual computations.
Unique coverage is untouched by reclaim: it grows only
on completion. This is exactly the EXP-029 accounting
rule, and it is what makes restart honesty work:

- **A restarted process cannot falsely claim unfinished
  work was completed.** Its pre-restart completion claim
  carries a dead token (reclaimed lease, or old epoch),
  and is rejected as STALE. Its unfinished work was never
  credited: completion is the only crediting event, and
  it never happened. If the worker genuinely completed a
  chunk before crashing but the acknowledgement was lost,
  the replayed completion from the same lease, if the
  lease is still the completed record, returns DUPLICATE
  (idempotent, section 7); if the lease was reclaimed in
  between, the chunk will simply be re-examined and
  completed by whoever leases it, and the first worker's
  examinations are accounted as repeated work. Coverage
  is never double-credited in either branch.

## 7. Duplicate detection and accounting

Duplicate work is detected at three levels, and never
counts as unique coverage at any of them:

- **Lease level**: completion of an already-completed
  lease returns DUPLICATE and increments
  duplicate_deliveries. Progress or completion from a
  non-holder or with a dead token is rejected and
  counted (NOT_HOLDER, STALE, UNKNOWN_LEASE).
- **Candidate level**: the Candidate Queue deduplicates
  on the full header identity (job_id, generation,
  extranonce2, version, ntime, nonce), replacing the
  Qaxe 32-entry (nonce, version) ring (M12, W2). A
  duplicate candidate is counted and never verified
  twice.
- **Accounting level** (EXP-037 categories, kept
  separate forever): unique coverage (completed chunk
  sizes only), actual computations (every reported
  examination, including repeats), repeated computations
  (examinations of already-examined positions, booked at
  re-lease time), duplicate deliveries, stale reports,
  completed leases, abandoned (reclaimed) leases. The
  identity `unique + pending + leased == declared`
  holds at every instant for the current job.

**Work stealing** is the one legitimate transfer: when
a worker is idle and another's lease has a large
unreported tail, the coordinator splits the tail. The
victim's chunk shrinks FIRST and its fencing token
rotates (its old token dies), then the tail is leased to
the thief under a fresh lease. The partition is disjoint
at every instant, and the victim cannot report progress
past its new boundary with its old token. Stealing is a
coordinator act, never a worker act: a worker that tries
to complete or report against a lease it does not hold
is rejected (above), which the tests exercise as the
illegitimate "steal attempt".

## 8. The Candidate Queue and the flow into EXP-036

Flow: worker search finds a header meeting its share
criterion, worker sends a candidate record to the
coordinator, the coordinator's Candidate Queue accepts
and journals it, the queue drains FIFO into the EXP-036
Exact Candidate Verifier, and the verifier's verdict
drives the EXP-036 submission pipeline. Workers never
submit to a node or a pool directly (M13).

Candidate record: the full header identity of section 7
plus the complete header fields needed for EXP-036
step 1 to 3 reconstruction (job_id and generation, so
the immutable job can be recovered; extranonce2, version,
ntime, nonce, merkle root or the coinbase identity the
job record resolves), the reporting worker and lease ids,
and the worker's claimed digest (advisory only; the
verifier recomputes).

Queue rules:

- **Persist before acknowledge**: a record is appended
  to the queue's append-only journal before the worker
  is told it was accepted. After a coordinator crash,
  recovery replays the journal: submitted-but-unverified
  records are pending again; verified records are marked
  seen, so a resubmission is a duplicate, never a second
  verification. This closes the gap-analysis defect that
  a candidate today exists only as an evidence-log line
  after confirmation.
- **Deduplicate on submit** (full header identity).
- **Generation check at drain**: a candidate whose job
  generation is no longer current is dropped as stale
  and never reaches the verifier; its template is no
  longer the work the chain wants.
- **Lease state does not decide verification**: validity
  is a property of the header, not of the lease. A
  candidate found under a lease that was later reclaimed
  is still verified once, and attributed
  from_reclaimed_lease so the accounting shows where it
  came from. What the lease decides is coverage credit,
  never candidate judgement.
- **Backpressure and budget** (M27): the verifier's
  throughput bounds the fleet. The queue is bounded; if
  it fills, workers keep searching (candidates are rare
  and the queue drains at verifier speed), and the
  coordinator sheds load by pausing new leases rather
  than by dropping queued candidates. The production
  sizing of the bound is an EXP-037 measurement task,
  not a number this design invents.

## 9. Wire format and persistence (design only)

Not built in this phase; specified so the production
build has no open choices:

- Coordinator-worker messages are length-prefixed
  frames with a total length and a payload checksum,
  adopting the Qaxe multiframe fragmentation discipline
  while adding the integrity fields it lacks (M31, W7).
  A frame that fails its checksum is discarded and
  counted, never absorbed.
- Every message carries (worker_id, job generation,
  lease_id, fencing_token) as applicable, so any stale
  or misrouted message is rejected by the same token
  rules as the in-process prototype.
- Coordinator persistence is an append-only journal of
  registry, declaration, lease, reclaim, completion and
  candidate events, plus periodic snapshots in the
  EXP-029 snapshot format extended with the token
  counter, epoch and registry. Restore follows section 6
  rule 4 exactly.
- Transport, authentication of the fleet channel, and
  deployment shape are production decisions for the
  integration phase; this design fixes the semantics
  they must preserve, not the bytes beyond the frame
  rule above.

## 10. Disjointness proof obligations

The design is only as good as these obligations, each of
which is discharged by the controlled tests of this
phase (TESTS/test_exp035_campaign.py) against the
research prototype (lease_manager.py, candidate_queue.py):

- **P1 (exact union)**: when a job finishes, the union
  of completed intervals equals the declared space
  exactly, per slice and in total. No gaps.
- **P2 (pairwise disjoint)**: completed intervals are
  pairwise disjoint; the per-slice chunk partition tiles
  its nonce range with no gap and no overlap at every
  assertion instant, including across steals, reclaims
  and restores.
- **P3 (duplicates never credited)**: duplicate, stale
  and not-holder reports are counted in their own
  counters and contribute nothing to unique coverage,
  which equals the declared total exactly at completion
  despite thousands of injected duplicates and replays.
- **P4 (accounting identity)**: unique + pending +
  leased == declared at completion, with pending and
  leased zero; actual >= unique always; repeated work is
  visible in its own counter whenever reclaims with
  progress occurred.
- **P5 (restart honesty)**: after worker restart,
  worker death, lease expiry and coordinator restart,
  no pre-event completion claim is credited (all return
  STALE), and the affected work is either completed
  later by a live lease or remains pending, never
  silently covered.
- **P6 (candidate integrity)**: the verifier is invoked
  exactly once per unique candidate identity; duplicates
  and stale-generation records never reach it; journal
  recovery preserves both properties across a crash.

## 11. Controlled testing on this VM (summary)

Simulated workers (separate state objects in one
process, plus the manager) ran against the prototype.
No fleet agent was contacted, no production code was
touched, no mining kernel was benchmarked. The full
record is in RAW_RESULTS/.

- 10 targeted tests, all PASS: foreign-fleet rejection;
  duplicate completion idempotence; restart replay never
  credited (with repeated-work accounting of exactly the
  32 re-examined positions); lease expiry reclaim;
  coordinator restart killing all pre-restart tokens
  (job then completed exactly, 64 repeated); steal with
  victim token rotation (old token STALE, wrong-identity
  attempt NOT_HOLDER, both halves completed exactly
  once); starved-worker re-registration; search-space
  declaration arithmetic (4 slots x 2 counters x 2
  versions x 2 ntimes = 32 slices, extranonce2 values
  pairwise disjoint and equal to (slot << 25)|counter);
  candidate queue semantics; candidate queue journal
  recovery.
- Randomised campaign, 60 trials, all PASS: 609,280
  declared positions completed exactly in aggregate,
  under 2,167 injected worker deaths, 1,564 worker
  restarts, 801 coordinator restarts, 806 lease
  expiries, 694 legitimate steals and 6,708 reclaims,
  with 3,190 zombie restart replays (all STALE), 2,088
  duplicate completion deliveries and 739 not-holder
  attempts rejected and counted, and 257,020 repeated
  computations accounted separately from the 609,280
  unique coverage. Candidate submissions inside the
  campaign: every duplicate detected, verifier invoked
  once per unique candidate.

## 12. What remains UNVERIFIED

Stated plainly, with no numbers, because none were
measured:

- **Multi-machine overhead**: all testing was
  in-process on one VM. Coordinator-worker round trips
  over a real network, frame costs and journal fsync
  costs are unmeasured.
- **Propagation latency**: template and lease
  distribution latency to real remote workers, and
  candidate return latency, are unmeasured. EXP-029
  measured only local prototype overhead and this phase
  adds nothing to it.
- **Linear scaling**: nothing here shows the fleet
  scales linearly, or to what worker count the
  coordinator and the EXP-036 verifier sustain. The
  verifier-budget concern (M27) is a design rule, not a
  measurement.
- **Real fleet behaviour**: the roughly 25 agents were
  not activated, contacted or measured. Their hosts,
  clocks and failure modes are unknown to this design's
  evidence.
- **The wire protocol and persistent coordinator** of
  section 9 are specified, not built or tested.
- **Clock behaviour**: the prototype uses an explicit
  simulated clock. Production deadlines ride on real
  clocks across machines; skew handling is a production
  build concern, mitigated by making deadlines
  coordinator-side (the coordinator's clock is the only
  one that decides expiry), but untested here.

## 13. Production integration path (future, gated)

Not part of this phase. In order: (1) promote the lease
manager and queue into a coordinator service with the
section 9 journal and frames; (2) wire the EXP-034 job
engine as the declaration source and the EXP-036
verifier as the queue's drain; (3) single-VM multi-
process controlled run (several worker processes, one
coordinator, one regtest node), with a regtest block
found through a leased slice and verified through the
queue as the acceptance gate, in the EXP-029 criterion
style; (4) only then, a measured overhead study at
increasing worker counts before any fleet activation
decision, which remains the owner's.
