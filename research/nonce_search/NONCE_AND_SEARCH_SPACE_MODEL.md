# Nonce and Search Space Model

NOVA SHA-X Master Assignment, work package BR-007 (nonce and
search space). The complete formal model of the space a Bitcoin
miner searches: its dimensions, how each dimension is owned and
partitioned, how coverage and duplication are accounted so that
duplicated work never counts as unique coverage, and what a
restart may and may not claim. The degenerate original case
(v0.1.3, one thread, one variable) is included as the base point
the modern model generalizes.

Sources: research/phase001/NONCE_SEARCH_ANALYSIS.md (the v0.1.3
search as a formal object, with executable checks);
research/sha256d/exp034/JOB_TEMPLATE_ENGINE.md (NOVA's
extranonce_space and the freshness and rolling findings);
research/sha256d/exp035/WORK_DISTRIBUTION_DESIGN.md (the
multi-dimensional space, leases, and accounting rules);
research/sha256d/exp037/STATISTICAL_MODEL.md and
mining/mining_statistics.py (the separated counters);
research/sha256d/exp038/AUTONOMOUS_OPERATIONS.md (the checkpoint
frontier semantics). Header mechanics are in
research/bitcoin_reverse_engineering/BLOCK_HEADER_SERIALIZATION_
SPECIFICATION.md section 5.

## 1. The space

A template fixes every header byte except the mutable fields. A
**candidate** is one fully determined 80-byte header. The search
space of a job is the Cartesian product of its declared mutable
dimensions:

```
space(job) = (extranonce2 value) x (version variant) x (ntime value)
             x nonce range [0, 2^32)
```

One combination of (extranonce2, version, ntime) is a **slice**;
a slice contains 2^32 candidates, one per nonce. Dimensions, one
by one:

### 1.1 The nonce (per-slice variable)

32 bits, header bytes 76 to 79. Every slice has the full range
[0, 2^32) available in the modern model. The nonce is the only
dimension that changes per candidate in a running search; all
other dimensions change per slice, at a cost (a new coinbase, a
new merkle root, or a new midstate, per the serialization
specification's mutation table).

### 1.2 The extranonce (client-owned, always)

The extranonce is not a header field. It is miner-chosen bytes in
the coinbase scriptSig; changing it changes the coinbase txid,
hence the merkle root, hence every candidate in the slice. Two
ownership facts, both verified against source:

- The node never owns it. Bitcoin Core v28.1 contains no
  IncrementExtraNonce anywhere; its server-side coinbase scriptSig
  is exactly the BIP34 height push plus OP_0, and getblocktemplate
  hands the client coinbaseaux (flags the client must include),
  coinbasevalue, and the witness commitment, leaving the rest of
  the scriptSig to the client (Core audit; mining call graph
  section 5).
- In v0.1.3 it was equally client-side and even more minimal: a
  local CBigNum counter inside BitcoinMiner, pushed after nBits
  in the scriptSig, pre-incremented once per template, never
  persisted or shared (section 5 below).

On Stratum paths the extranonce splits into extranonce1 (assigned
by the server per connection) and extranonce2 (rolled by the
miner). On NOVA's GBT path it is the engine's own coinbase
counter, partitioned by EXP-034's opt-in
MiningEngine(extranonce_space=(first, count)), default (0, 64)
(the historical behaviour, byte-identical when unused);
out-of-range spaces beyond the 32-bit extranonce are refused at
construction, and disjoint configured spaces provably build
disjoint candidate sets whose union is the default set (EXP-034
test C4).

### 1.3 ntime (the timestamp dimension)

A job declares an explicit ntime list: the template's ntime plus
permitted forward steps. The bounds are consensus bounds, not
preferences: each value must exceed the median time past of the
previous 11 blocks and stay within the allowed future window
(network-adjusted time plus 2 hours); a pool's rules may narrow
the window further, and the template manager owns computing the
permitted list (EXP-035 design, section 2). Each ntime value is a
separate slice coordinate: coverage under one ntime says nothing
about coverage under another.

### 1.4 Version (the BIP320 dimension)

Version rolling varies the general-purpose bits of the template's
version (BIP320 mask 0x1fffe000), preserving the template's BIP9
signalling bits. The job declaration enumerates the permitted
variant list explicitly; variants outside the mask are not part
of the space and are never leased or searched (EXP-035 design,
section 2). Each variant has its own midstate (version is a
chunk-1 word), so this dimension multiplies template-side
precomputation as well as space.

### 1.5 What is not a dimension

hashPrevBlock and nBits are never dimensions: they are fixed by
the chain position and the retarget rule, and changing either is
a new job, not a roll (serialization specification, section 5).
The transaction set likewise enters only through template
replacement, which declares a new job with a new generation
rather than mutating the old space (EXP-035 design, section 3).
Expanding any real dimension declares more space; it never
redefines work already counted.

## 2. Work identity and partitioning

A job's identity is (job_id, generation), where generation is
the monotonically increasing EXP-034 job generation identifier; a
bare job_id or a bare worker slot is never an identity (the
reference firmwares' recycled slot registries can misattribute a
late result to the wrong job, EXP-030 Phase A matrix finding W3;
the generation tag is NOVA's correction). Jobs are immutable once
declared.

Partitioning for distributed work (EXP-035 design): the
extranonce2 dimension is partitioned by worker, Qaxe style
(matrix M06):

```
extranonce2 = (slot << 25) | counter
```

7 bits of worker slot (up to 128 workers) and 25 bits of
per-slot counter. A worker is bound to one slot per job and can
only lease slices inside its own slot, so the coinbase dimension
is disjoint across workers by construction, not by trust. Within
a slot, work is assigned in leases: a lease names its slice
coordinates (slot, counter, extranonce2, version, ntime) and a
nonce sub-range [lo, hi), carries a unique lease_id and a fencing
token from one monotonically increasing coordinator counter, and
has a deadline. Work stealing is a coordinator act that shrinks
the victim's chunk and rotates its fencing token BEFORE the tail
is leased to the thief, so the partition is disjoint at every
instant, not merely eventually.

## 3. Coverage and duplication accounting (the never-summed rules)

The accounting exists to make one fraud impossible: counting the
same candidate twice as if it were two units of unique work. The
rules, from EXP-035 section 7 and EXP-037, implemented as
separated counters in mining/mining_statistics.py:

1. **Unique coverage** counts completed chunk sizes only: a
   position enters unique coverage when a lease completes and its
   chunk is credited, never when it is merely examined.
2. **Actual computations** counts every reported examination,
   including repeats. It is a cost figure, not a coverage figure.
3. **Repeated computations** (the statistics module's
   repeated_work) counts examinations of already-examined
   positions, booked at re-lease time. The vocabulary equivalence
   between EXP-035's "repeated computations" and the module's
   repeated_work is recorded in the module itself so the two
   documents cannot drift apart silently.
4. **Duplicate deliveries** and **stale reports** count rejected
   coordinator reports (completion of an already-completed lease;
   reports from a non-holder or with a dead fencing token). A
   duplicate candidate is detected on the full header identity
   (job_id, generation, extranonce2, version, ntime, nonce),
   counted, and never verified twice.
5. The identity **unique + pending + leased == declared** holds
   at every instant for the current job (EXP-035).
6. **The categories are never summed.** Backend hashes, unique
   headers, unique nonces, unique coverage, actual computations,
   verification hashes and the rest overlap by construction (a
   verification hash is a real hash computation; a repeated
   examination is a real nonce position), so any grand total
   double-counts. MiningStatistics.snapshot() therefore returns
   each category separately and deliberately has no combined
   total, and this model adopts the same rule for its own
   language: a coverage claim names its category, always.
7. Rates are derived from counters, never estimated from shares:
   share counts say how lucky a search was, never how much work
   it did (EXP-037, counter-first rule). A candidate-construction
   rate (for example the EXP-025 cache's measured construction
   speedups) is not a hash rate and never enters a coverage
   statement.

A coverage claim is well-formed only in the shape: "the union of
completed chunks equals X positions of job (id, generation)'s
declared slice set, with the job's variant and ntime lists on
record." Anything shorter is not a coverage claim this programme
recognizes.

## 4. Restart honesty (checkpoint frontier semantics)

The rule, from the EXP-030 directive and EXP-038: a restarted
process must not falsely claim unfinished work was completed.
EXP-038 implements it for the GBT path in
mining/work_checkpoint.py with an exact frontier:

- Positions are (extranonce, nonce) pairs in the lexicographic
  order MiningEngine.mine_cycle walks them. The record holds a
  frontier (fe, fn): every position with extranonce below fe was
  examined over its full nonce range, and in round fe every nonce
  below fn was examined. Because the walk is strictly ordered,
  one frontier is an exact description of completed coverage for
  a template, not an estimate.
- **The frontier advances only after a batch's search returns
  without a hit.** A batch that produces a hit never advances it:
  that batch was partly examined, the cycle ends there, and a
  later cycle on the same template rescans that one batch. The
  rescan is repeated work and is accounted as such (section 3),
  never silently absorbed into coverage.
- Resume requires ALL THREE of: the template's EXP-025 layered
  identity, the engine's extranonce space, and the template's
  curtime basis. The identity deliberately excludes time fields
  (the EXP-025 rule) while header time is a per-build input, so
  the time basis is matched separately: a resumed scan never
  claims coverage recorded under a different time basis. Any
  mismatch, a corrupt record, or a frontier outside the space
  starts the cycle fresh, with the reason carried in the cycle
  result.
- A space recorded complete is not rescanned under the same
  identity: the cycle returns "nonce space exhausted" with zero
  hashes rather than repeating finished work.
- Writes are atomic (sibling temp file, fsync, os.replace), so a
  crash mid-write leaves the old record or the new one, never a
  torn file. The auditor's 24-configuration randomised restart
  campaign (EXP-037/038 audit) showed resumed coverage pairwise
  disjoint and union-complete against the uninterrupted walk.
- Scope boundary: the checkpoint serves the GBT path. The Stratum
  pool path's separation is the pool-assigned extranonce1 per
  connection and its job state belongs to the pool session, so a
  restarted pool miner starts a new session whose separation the
  pool provides; claiming a local position there would be false
  precision. Coordinator-level progress in the distributed model
  belongs to the EXP-035 lease manager's recorded positions, not
  to this checkpoint.

## 5. The degenerate case: the v0.1.3 original search

The original search is this model with every dimension collapsed
except the nonce, executed by one thread (Phase 001 Deliverable
13, mechanics from src/main.cpp lines 2183 to 2362):

- Space per template: nonce values {1, ..., 0xffffffff}, exactly
  2^32 - 1 = 4,294,967,295 candidates. **Nonce 0 is never hashed**:
  the loop starts at 1 (line 2297) and the post-increment wrap to
  0 is the termination signal (lines 2347 to 2348), never a
  candidate. Any coverage statement about the original search
  that says 2^32 per template is wrong by one, and the model's
  executable checks pin the count three ways (direct identity,
  gate-count identity, and a width-reduced executable model at 8
  and 12 bits: 255 and 4,095 candidates, nonce 0 never hashed).
- Traversal: strictly increasing, no gaps, no repeats inside one
  template. Housekeeping runs every 262,144 increments (mask
  0x3ffff, line 2344): exactly 16,384 gates per full traversal,
  checking in order shutdown, wrap, tip change, mempool change
  with template age over 60 seconds, generation flag, and
  otherwise refreshing nTime. Staleness is therefore polled in
  hash units (up to 262,144 hashes late), a bound whose wall-clock
  meaning shrinks as machines get faster.
- Extranonce: the local CBigNum of section 1.2, pre-incremented
  per rebuild (line 2212), so a run's total coverage is
  (2^32 - 1) x (distinct templates built), with the qualification
  that templates also differ by tip and transaction set when those
  trigger the rebuild. The counter is arbitrary precision; its
  practical bound is the coinbase scriptSig length rule.
- Duplicates: none at the header level. Every reachable rebuild
  path changes at least one non-nonce header input (extranonce,
  tip, transaction set, or a fresh coinbase key on restart), so
  the same 80-byte header is never hashed twice by the program
  (proven over the enumerated rebuild paths, with one stated
  assumption: a fresh CKey produces a different public key, the
  single point where the argument rests on probability rather
  than code structure). The original's redundancy is instead
  INSIDE each candidate: the template-constant chunk-1
  compression (64 of 192 rounds) is recomputed per candidate,
  which is repeated computation in this model's accounting, not
  duplicate coverage. The 0.1.3 search has perfect coverage
  hygiene and poor round economy, simultaneously.
- The nTime refresh creates a diagonal band, not a rectangle: the
  gate refreshes nTime mid-template and the scan continues from
  the current nonce, so for each nTime epoch only a segment of
  the nonce range is covered under that nTime. Coverage claims
  for the original must be stated per (template, nTime epoch).
- No resumption: a stopped miner restarts its template's scan
  from nonce 1 under a new extranonce, losing the partial scan,
  safe only because the new template's headers are all distinct.
  Section 4's frontier is the modern correction of exactly this.

At the genesis target, the probability model gives a 63.2 percent
success chance per full original template space (1 - (1 - p)^(2^32
- 1) with p from the exact target; the 2^32-trial anchor
0.6321149454 is computed in the probability model's script), so
exhaustion without success, and the extranonce rebuild, were
routine events in the original architecture, not edge cases.

## 6. Production status against this model

Stated from the EXP-034/035 records and the Phase A audit, so the
model does not describe a system that does not exist:

- Implemented and live: the nonce dimension on all paths; the
  engine extranonce rounds with opt-in extranonce_space (GBT
  path); the Stratum extranonce1/extranonce2 pair (pool and solo
  paths); the EXP-038 checkpoint frontier (GBT path, enabled by
  agent/autonomous.py); the separated statistics counters
  (EXP-037 module; note the audit's finding that its record() has
  no live caller in the miner yet, so live accounting is still
  reconstructed from the evidence log, not from the module).
- Designed and proven as a research prototype, NOT integrated:
  the EXP-035 lease manager, coordinator and candidate queue,
  including the (slot << 25) | counter partition, fencing, and
  the section 3 accounting at coordinator level. Its randomised
  campaign (60 of 60 trials, exact disjoint coverage under deaths,
  restarts and steals) is a prototype result on one VM;
  multi-machine overhead, propagation latency and linear scaling
  are UNVERIFIED, and the fleet agents were not activated.
- Absent from production: version rolling and miner-side ntime
  rolling on every path (EXP-034). The dimensions exist in this
  model and in the EXP-035 design; no production code searches
  them, and no coverage claim may include them until it does.

## 7. Reproduction

- Original search: research/phase001/RAW_RESULTS/
  phase001_verification.py sections 6 and 7 (candidate count,
  gate count, width-reduced loop model).
- Partition and accounting design proofs: research/sha256d/
  exp035/PROOFS/ and TESTS/test_exp035_campaign.py with its
  RAW_RESULTS campaign output.
- Checkpoint semantics: tests/test_exp038_checkpoint.py and the
  EXP-037/038 audit report (research/sha256d/exp038/).
