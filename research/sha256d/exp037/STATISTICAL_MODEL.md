# EXP-037: Mining Statistics and Probability Model

Date: 2026-11-15. Implements directive section 10 for the
Bitcoin Autonomous Lab. Production homes: the evidence census
in mining/autopilot.py (EvidenceCounter), the statistics
engine in mining/mining_statistics.py, and the probability
engine in mining/probability.py. Tests:
tests/test_exp037_statistics.py (Makefile target test-exp037).

## 1. The defect that opened this phase

Gap analysis component 16 recorded it and this phase measured
it on the production log before fixing: autopilot's
evidence_stats read only the last 2,000,000 bytes of
evidence/mainnet-live.jsonl. On 2026-11-15 the log was
2,289,561 bytes and held 247 accepted share_result events;
the tail-window count returned 222. Twenty-five accepted
shares were silently excluded from the number the operation
watches every five seconds, and the shortfall grows with
every byte the log adds. The heartbeat total was wrong by
construction, not by accident.

## 2. The evidence census, as fixed

EvidenceCounter (mining/autopilot.py) replaces the tail
window with an incremental whole-log census:

- First contact streams the log once from byte 0, in 1 MiB
  chunks, one line at a time. Memory is one chunk plus one
  partial line, independent of log size.
- The position is persisted after every advance to
  .local/evidence-count.json (atomic temp file plus
  os.replace): byte offset, accepted count, rejected count,
  share_result count, last event epoch, and a SHA-256
  fingerprint of the log's first up-to-8192 bytes.
- Later polls advance only over newly appended bytes, so the
  per-poll cost the autopilot pays (it polls every second)
  is one stat plus the bytes appended since the last poll.
- A partial final line is never consumed: the offset moves
  only past newline-terminated lines, so a writer caught
  mid-append is recounted once its line completes.
- Rotation and replacement: if the file shrinks below the
  recorded offset, or the head fingerprint no longer
  matches, the log is treated as a new file and recounted
  from zero. A missing log reads as zero. A corrupt state
  file falls back to a full recount.
- One replacement shape is undetectable by any offset scheme
  and is stated rather than hidden: a new file at least as
  large as the old offset whose first 8192 bytes are
  identical to the old file's would be mistaken for appends.
  No rotation in use here (rename and recreate, or truncate)
  produces that shape.

The fix takes effect in the live heartbeat at the autopilot's
next natural restart; nothing was restarted for this phase.
At that restart the reported shares_accepted_total will move
from the tail-window figure to the whole-log figure (247 at
the time of writing, and growing), which is the correct
number arriving, not an anomaly.

## 3. Categories: counted once, kept separate, never summed

MiningStatistics (mining/mining_statistics.py) holds the
directive section 10 categories and the EXP-035 section 7
accounting categories as independent integer counters, each
also broken down per worker and per backend. record()
refuses unknown categories and negative counts, so a new
category enters through the directive and the EXP-035 design
first, not by a typo at a call site.

| Category | What increments it | Counted today by |
|---|---|---|
| backend_hashes | hash computations a backend actually performed, dummy lanes included where the backend computes them | ComputeEngine Task 003.9 stats per call |
| unique_headers | distinct headers hashed | ComputeEngine accounting (unique_coverage of headers) |
| unique_nonces | distinct nonce positions examined | ComputeEngine unique_coverage; EXP-038 checkpoint frontier on the GBT path |
| leases_completed | leases reported complete and credited | EXP-035 lease manager (design and prototype; no production leases yet) |
| leases_abandoned | leases reclaimed unfinished (expiry, death, restart, steal residue) | EXP-035 lease manager (same status) |
| repeated_work | examinations of already-examined positions (EXP-035's "repeated computations": one counter, two source documents) | EXP-035 accounting at re-lease; visible across restarts via the EXP-038 checkpoint note |
| candidates | candidate results a backend presented | ComputeEngine candidate_count |
| verification_hashes | hash computations spent re-verifying candidates | ComputeEngine verification_hashes; EXP-036 verifier |
| valid_candidates | candidates that passed exact verification | EXP-036 verify_candidate on the solo and pool paths |
| pool_shares_submitted | shares sent to the pool | Stratum client submit path |
| pool_shares_accepted | share_result events with accepted true | Evidence census over the whole log (section 2) |
| pool_shares_rejected | share_result events with accepted false | Evidence census over the whole log |
| network_target_candidates | verified candidates meeting the network target | EXP-036 verifier classification |
| blocks_submitted | blocks handed to submitblock | GBT engine and solo server submission paths |
| blocks_accepted | submissions verified in the best chain afterwards | EXP-036 chain verification |
| blocks_rejected | submissions refused or never confirmed in chain | EXP-036 classification and chain verification |
| unique_coverage | completed chunk sizes only, in positions (EXP-035) | EXP-035 lease manager |
| actual_computations | every reported examination, repeats included (EXP-035) | EXP-035 lease manager |
| duplicate_deliveries | completion reports for already-completed leases (EXP-035) | EXP-035 lease manager |
| stale_reports | reports carrying dead fencing tokens (EXP-035) | EXP-035 lease manager |

The categories overlap by construction: a verification hash
is a real hash computation, a repeated examination is a real
nonce position, an accepted block was first a valid
candidate and a network-target candidate. Any total built by
adding categories double-counts, so snapshot() returns each
category as its own number and has no combined-total field.
That absence is deliberate and is pinned by a test.

## 4. Counter-first telemetry (M11, M28)

The rule adopted from both reference firmwares: hashrate and
error rates come from counters the workers themselves
increment in the search loop, windowed by a reader that
never estimates from shares. A share count measures luck;
a hash counter measures work. WindowedRate
(mining/mining_statistics.py) derives rates from cumulative
counter samples only: rate over a window is the counter
delta divided by the true span between the bracketing
samples. Per-worker and per-backend breakdowns are recorded
at the same time as totals (M28), because an aggregate that
hides one sick worker is how a fleet loses a machine
silently.

## 5. Probability engine

mining/probability.py adopts the orphaned
research/probability.py formulas into production reach,
unchanged in substance and cross-checked against the
research originals in tests:

- expected_hashes(D) = D * 2^32
- expected_seconds(R, D) = (D * 2^32) / R
- prob_at_least_one(R, D, t) = 1 - exp(-R * t / (D * 2^32))

Anchors pinned in tests: expected_hashes(1) = 2^32 exactly;
expected_seconds(2^32, 1) = 1.0; probability at one expected
time is 1 - exp(-1) = 0.6321205588285577.

Labelling: these outputs are THEORETICAL, exact for an ideal
uniform hash function given their inputs. The inputs are
where measurement lives: network difficulty from the node's
template, hashrate from counters (section 4). Expected time,
probability over a period, best share difficulty, network
difficulty and actual block discovery are five separate
quantities; this engine computes the first two from the
fourth and a measured rate, and says nothing about the third
or fifth. A high-difficulty share is not a block, and a
probability is not a schedule.

## 6. Measured, estimated, theoretical: the current surface

| Number | Source | Label |
|---|---|---|
| heartbeat shares_accepted_total | whole-log evidence census (after next autopilot restart) | measured |
| heartbeat evidence_age_s | last event epoch from the same census | measured |
| ComputeEngine per-call stats | backend counters | measured |
| solo server stats() | server-side per-worker counters | measured |
| mainnet_live status rate | counted hashes over elapsed session time: a session cumulative average, not a windowed rate | measured inputs, session-average presentation |
| mainnet_live best difficulty | in-memory best-share statistic, lost on restart | measured, volatile |
| probability outputs | section 5 formulas | theoretical given measured inputs |
| fleet scaling figures (24,000 systems to 500 GH/s) | gap model arithmetic on a measured single-system rate | theoretical |

## 7. What remains unbuilt or unmeasured

Stated plainly, so this phase is not overread:

- MiningStatistics is a production module with pinned
  accounting rules, but the live paths (mainnet_live,
  autopilot heartbeat, solo server) still emit their own
  counters; wiring record() calls into those paths is
  follow-on work, not done here. The one live number this
  phase changed is the heartbeat share census, through
  EvidenceCounter.
- No windowed per-backend or per-worker rate series runs on
  the live path yet. WindowedRate exists and is tested; the
  status events still carry the session cumulative average
  labelled in section 6.
- The directive's latency series (verification latency,
  template construction latency, job distribution latency,
  submission latency, worker recovery time) are not yet
  measured anywhere. No numbers are claimed for them.
- M10 (adaptive solo share difficulty toward a target share
  interval, with hysteresis) is dispositioned as a design
  note in the EXP-038 operations document; it is not
  implemented. The solo share difficulty remains the
  configured constant (0.02 in the staged endpoint config).
- Lease categories have no production producer until
  EXP-035's design is built; their counters exist so the
  accounting vocabulary is fixed before the producer lands.

## 8. Tests

tests/test_exp037_statistics.py proves: the whole-log census
on a synthetic log of 2.3 MB with accepted shares inside the
old window's dropped region (old algorithm shown
undercounting the same bytes), incremental append without
double counting, partial-line handling, offset persistence
across counter instances, rotation, truncation, corrupt
state, missing log, the evidence_stats contract, a
brute-force equality check against the real production log,
category separation and refusal rules, windowed rates from
synthetic counter samples, and the probability anchors plus
identity with the research originals.
