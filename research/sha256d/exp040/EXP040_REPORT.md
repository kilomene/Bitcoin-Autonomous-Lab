# EXP-040 Report: category F end-to-end pipeline benchmark (Phase 002 step 2)

Status: COMPLETE 2026-11-15 (design in section 1 written
before any measurement; results in section 2, appended
after the runs).
Programme: NOVA SHA-X, Phase 002 step 2. This experiment
builds the category F harness whose absence the Master
Assignment audit recorded (BR-010) and the Hashrate
Measurement Specification states plainly in its section 2
("F: None. MISSING AS A MEASUREMENT") and section 12 of the
prohibition list ("Claiming any category F rate before an
F harness exists and has been run under this specification"
is prohibited). Until this report's results section exists,
no category F figure may be quoted from this programme.

Host for every measurement in this report: AMD EPYC 9D25
126-Core Processor, 4 vCPUs visible in the guest (about 2
effective CPUs per EXP-031). Contention state, stated per
the specification and never omitted: the live mainnet pool
miner (v512dual backend) and the pruned mainnet node are
running throughout. Every figure here is a
single-VM, contended, regtest-difficulty pipeline figure.
None of them is a hash rate, and none is comparable to a
category D or E rate except as pipeline context with the
category labels attached.

## 1. Design (written before the runs)

### 1.1 What category F is here

Category F (Hashrate Measurement Specification section 1)
is the end-to-end pipeline: template acquisition from a
node, block and coinbase construction, search, candidate
verification, and submission, timed as one pipeline. The
production path measured is the lab's GBT mining path:
mining/engine.py MiningEngine.mine_cycle against the local
regtest Bitcoin Core 28.1 node, with the production
ComputeEngine dispatch (CUDA, v512dual, v512, shani, avx2,
C, hashlib; on this host v512dual is selected), the EXP-025
repaired template cache enabled (the production default),
and the EXP-037 statistics wiring in its production default
state. mine_cycle is called unmodified. A timed run is one
mine_cycle call that ends in exactly one accepted block.

### 1.2 Stage attribution without touching production code

No production file is modified by this experiment. The
harness (research/sha256d/exp040/category_f.py) wraps the
objects it hands to its own MiningEngine instance, in its
own process, at the seams mine_cycle already uses:

- The RPC client is a delegating proxy. Its call() is
  timed per method: getblocktemplate is stage "gbt",
  submitblock is stage "submit", every other method is
  stage "rpc_other" (method names counted). The typed
  get_best_block_hash() is stage "confirm"; other typed
  wrappers are "rpc_other". with_timeout returns a proxy
  around the clone, so the longpoll path would be timed
  the same way (mine_cycle does not use it).
- prepare_template is replaced on the harness's engine
  instance only, by a wrapper that times the original
  call (stage "prepare") and wraps the returned
  PreparedTemplate.build so each extranonce step is timed
  (stage "construct"). The class method is untouched;
  the wrapper lives on the instance the harness created.
- The compute engine is a delegating proxy timing
  search_first_counted and search_first (stage "search").
  With difficulty amplification (scenario C) the proxy
  also substitutes the search target; see 1.4.
- A stack-based segment timer records (label, start, end)
  for every wrapped call. Stage totals are exclusive
  times (a segment minus the segments nested inside it),
  so nested RPC time inside prepare is counted once,
  under its own RPC label, never twice. "residual" is the
  cycle wall time minus all outermost segments: the
  engine's own loop bookkeeping, statistics recording,
  hit-path block assembly and its Python dsha256 for the
  block hash. The partition is checked per run: the sum
  of stage exclusive times plus residual equals the cycle
  wall time by construction, and the report prints the
  residual so nothing is hidden inside it.

Wrapper overhead is one perf_counter pair and a list
append per wrapped call. Search calls carry 65,536-hash
batches, RPC and construction calls are millisecond
scale; the wrapper cost is orders of magnitude below the
smallest stage it touches and is not corrected for.

### 1.3 Verification stage (EXP-036)

In the GBT production path, in-path candidate judgement
is Core's own: submitblock's response plus the
best-chain check (that is the production design, recorded
in mining/engine.py; the EXP-036 verifier's counters are
deliberately not recorded on this path). Category F
nevertheless includes verification work (specification
section 1: "Verification work ... is on the critical
path of any found block and is part of category F"), so
the harness measures it on every accepted block: after
mine_cycle returns, the winning block is fetched raw
from the node, its first 80 bytes are passed to
mining/candidate_verify.verify_candidate under the
regtest proof-of-work limit (the EXP-036 exact verifier:
two independent SHA-256d implementations must agree, the
target is decoded with Core SetCompact semantics, the
comparison is exact integer only), and the call is
timed. Gate: the classification must be
"block_candidate" and the verifier's digest must equal
the block hash the node accepted. A run whose block
fails this gate, or whose mine_cycle does not end
accepted, is a FAILED run: retained in the raw record,
labelled, and excluded from the statistics (specification
section 6). The verify time is reported as its own
component per block, outside the cycle stage partition,
because in this path it is measured after submission;
in the solo and pool production paths the same verifier
runs before submission at the same per-candidate cost.

### 1.4 Difficulty control and the declared search space

Regtest's proof-of-work limit (bits 0x207fffff, target
about 2^255) admits roughly one hash in two, so at the
real regtest target the search stage of a block is a
handful of hashes and the end-to-end time is the
pipeline's fixed cost. That fixed cost per block is the
primary category F quantity this experiment exists to
measure, and scenarios A and B measure it at the real
target, unmodified.

The declared search space is the engine configuration,
identical for every run in a scenario: batch_size
65,536, extranonce_space (0, 64), so one cycle may walk
64 extranonce rounds of the full 2^32 nonce range. A run
consumes a measured prefix of that space; the backend's
own counted attempts (search_first_counted accounting,
never the requested batch size) are recorded per run.
Runs are comparable because the configuration, the
scenario setup and the acceptance rule are fixed.

Scenario C exists to measure the stage partition when
the search stage carries real mass. Its compute proxy
divides the search target by 2^24 before calling the
real backend, so the expected work per block is about
2^25 counted hashes. This is a harness-side difficulty
amplification, documented here and in the harness: the
production engine, its templates and its submission are
untouched, and every block found still meets the real
regtest target (the amplified target is a strict subset)
and is accepted by Core through the normal submitblock
plus best-chain verdict. Scenario C figures are labelled
"amplified-target variant" wherever they appear; they
are not the production configuration and are never
pooled with A or B.

### 1.5 Scenarios

- A, empty: mempool empty (asserted size 0 before each
  run), template carries the coinbase only.
- B, loaded: mempool loaded with 500 simple
  one-input one-output wallet transactions before each
  run (asserted size 500), so the template carries 501
  transactions. The loader spends confirmed UTXOs only
  (no unconfirmed chains, so mempool ancestor limits do
  not bind). All 500 transactions pay a single offline
  key, generated per harness process and held only in
  memory: the lab wallet funds that key's address with
  one sendtoaddress, an offline-built split transaction
  creates the 500 confirmed UTXOs, and each reload's
  transactions are constructed and signed in-process
  (BIP143, via the cryptography library's secp256k1) and
  broadcast in submitpackage chunks. This shape is
  forced by measurement, not preference: on this host a
  wallet getnewaddress costs about 2 to 4 s and a wallet
  sign about 1.4 s per call (even batched, even from a
  fresh wallet), so a wallet-driven reload of 500
  transactions would spend many minutes of setup per
  run; the first shakedown, wallet-driven from the
  shared lab wallet, measured 40 to 55 s of setup per
  40-transaction reload. Reload time is scenario setup:
  recorded in the session file, never inside a timed
  run, and the shakedown session files are retained
  under a shakedown_ prefix.
- C, amplified: empty mempool, search target divided by
  2^24 in the compute proxy (see 1.4), engine budget
  raised (max_batches 100,000, deadline 900 s) so the
  amplified search is never budget-cut.

Each scenario runs 3 sessions. A session builds one
fresh MiningEngine (fresh payout address), runs one
untimed warm-up cycle that must end accepted (it pays
the one-time TemplateFamily construction and backend
warm-up; production engines are long-lived, so this cost
is amortised in production and excluded here, and its
exclusion is stated), then the timed runs: 8 per session
for A and B, 5 per session for C. Sessions run strictly
sequentially; nothing else is benchmarked in parallel.

### 1.6 Statistics

Per scenario: per-stage and end-to-end medians with min,
max and interquartile range across that scenario's timed
runs (sessions pooled only after per-session medians are
printed; all sessions share host, configuration and
contention class, so pooling runs is the honest summary,
and the per-session numbers stay in the raw files and in
this report's table). Headline quantities:

- end-to-end seconds per accepted block (median), and
  blocks per hour derived from the aggregate (total runs
  divided by total timed seconds, the robust form);
- the measured non-search overhead fraction: per run,
  (cycle wall time minus search stage time) divided by
  cycle wall time, reported as median and range. At the
  real regtest target this fraction is expected to be
  near 1 by construction (the target admits about one
  hash in two); the transferable quantity is the
  overhead in milliseconds per block, printed alongside.
  Scenario C gives the same fraction when search carries
  about 2^25 hashes per block.
- hashes examined per accepted block (backend counted).
- loaded versus empty: ratio of medians for end-to-end
  time and for prepare plus construct time, with a
  bootstrap confidence interval over runs (10,000
  resamples, fixed seed). This is a measured comparison,
  not an EXP-017 protocol verdict: the two arms are
  different templates by design, not paired work blocks,
  and no VERIFIED IMPROVEMENT language attaches to it.

### 1.7 What is excluded, and why

- Mempool reload and funding (scenario setup, recorded
  separately).
- The warm-up cycle per session (see 1.5).
- Node startup and wallet loading (the regtest node is
  long-lived infrastructure, like production).
- The EXP-036 verify call's own time is excluded from
  the cycle stage partition (it is measured after the
  cycle in this path) and reported as a per-block
  component; see 1.3.
- Nothing is excluded from the raw record: failed runs,
  warm-up results and setup times are all in the session
  files.

## 2. Results (measured 2026-11-15, this host, contended)

Campaign as designed: scenario A 3 sessions of 8 runs,
scenario C 3 sessions of 5 runs, scenario B 3 sessions of
8 runs, strictly sequential. Session files:
RAW_RESULTS/session_A_0..2, session_C_0..2,
session_B_0..2 (full names in RAW_RESULTS/analysis.json);
three shakedown files (shakedown_ prefix) are retained
and excluded. Timed runs: 63. Failed runs: 0. Every timed
run ended in exactly one block accepted by Core through
submitblock plus best-chain confirmation, and every
accepted block's header passed the EXP-036 exact
verifier (classification "block_candidate", digest equal
to the accepted block hash). Accepted timed-run heights:
A 1345 to 1370, C 1372 to 1388, B 1392 to 1417 (warm-up
blocks interleave; the raw files are authoritative).
Backend selected by the production probe in every
session: v512dual.

### 2.1 End-to-end per accepted block (category F)

Medians across the scenario's timed runs; per-session
medians in brackets.

| Scenario | Median s/block | Min | Max | IQR | Blocks/hour |
|---|---|---|---|---|---|
| A empty, real target | 0.065 [0.043, 0.156, 0.040] | 0.009 | 5.980 | [0.019, 0.154] | 55,300 by median; 6,586 aggregate |
| B loaded (501 tx), real target | 0.215 [0.215, 0.206, 0.213] | 0.104 | 0.400 | [0.166, 0.289] | 16,768 by median; 16,152 aggregate |
| C empty, amplified target (variant) | 3.299 [3.124, 3.713, 3.299] | 0.274 | 16.129 | [2.647, 4.094] | 1,091 by median; 773 aggregate |

Blocks/hour is printed two ways because they answer
different questions: "by median" is 3600 divided by the
median run; "aggregate" is runs times 3600 divided by
total timed seconds, the literal rate over the campaign
window. Scenario A's aggregate is dragged far below its
median form by one run whose submitblock stage stalled
for 5.97 s under contention (that run is retained and is
A's max in every column). These are regtest-difficulty
pipeline rates on a contended VM. They are not hash
rates, not production-difficulty rates, and not
comparable to category D or E figures.

### 2.2 Stage breakdown (median ms per block)

| Stage | A empty | B loaded | C amplified |
|---|---|---|---|
| GBT fetch (node) | 3.03 | 37.99 | 3.80 |
| Prepare (template identity, EXP-025 cache) | 0.10 | 19.69 | 0.10 |
| Construct (extranonce steps) | 0.03 | 0.13 | 0.03 |
| Search (counted backend) | 2.36 | 1.88 | 3,244.38 |
| Submit (submitblock, node) | 13.58 | 99.91 | 16.39 |
| Confirm (best-block check) | 4.80 | 4.07 | 4.46 |
| Other RPC | 0.00 | 0.00 | 0.00 |
| Residual (engine bookkeeping) | 0.21 | 0.70 | 14.92 |
| EXP-036 verify (per block, post-cycle) | 3.87 | 2.53 | 2.57 |

Reading of the loaded column: loading 500 transactions
into the template costs about 38 ms of node-side GBT
work, about 20 ms of prepare (the EXP-025 layered
identity hashes every template transaction; the steps
themselves stay at 0.13 ms because the prepared entry is
reused across extranonce rounds, which is the cache
doing exactly its job), and about 100 ms of node-side
submitblock validation. The engine's own residual stays
under 1 ms.

Scenario C's residual (median 14.9 ms, max 68 ms) is
larger than A/B because it is spread over about 257
batches per block: per-batch loop bookkeeping and
statistics recording, roughly 0.06 ms per batch. It is
engine overhead inside the cycle but outside the wrapped
seams, and it is reported, not hidden.

### 2.3 The non-search overhead fraction (headline)

Per run, (cycle wall minus search stage) divided by
cycle wall:

| Scenario | Median fraction | Range | Median overhead |
|---|---|---|---|
| A empty, real target | 0.930 | [0.200, 1.000] | 43.5 ms/block |
| B loaded, real target | 0.992 | [0.576, 0.998] | 206.3 ms/block |
| C amplified (about 2^25 hashes/block) | 0.015 | [0.007, 0.062] | 49.5 ms/block |

As designed, the real-target fractions are near 1: at
regtest difficulty the search is a handful of hashes
(median counted hashes per block 32, the backend's
group-atomic accounting of an expected about 2), so the
end-to-end time IS the pipeline's fixed cost. The
transferable measurements are the overhead milliseconds:
about 44 ms per block for an empty template and about
206 ms for a 501-transaction template on this contended
VM, consistent between scenarios A and C (43.5 vs
49.5 ms on the same empty template). Scenario C shows
the same fixed cost amortised over real search work:
at about 16.8M counted hashes per block (median) the
overhead fraction falls to about 1.5 percent. Derived
arithmetic, labelled as such: at any difficulty where
the search stage takes T seconds per block, the
overhead fraction is approximately
overhead / (overhead + T) with the overheads above; no
new measurement is claimed by that formula.

### 2.4 Loaded versus empty (measured comparison)

Ratio of medians, loaded over empty, bootstrap 95
percent CI over runs (10,000 resamples; not an EXP-017
verdict, see section 1.6):

- End-to-end time: 3.30x, CI [2.02, 10.61]. The interval
  is wide because scenario A's runs are noisy under
  contention (its session medians span 40 to 156 ms).
- Prepare plus construct: 147x, CI [110, 178]. The
  construction-side cost of a 501-transaction template
  is about two orders of magnitude the coinbase-only
  cost, and it sits in prepare (identity), not in the
  per-extranonce steps.

### 2.5 Setup costs (recorded, never in a timed run)

Loader funding (one payment, split, confirmations):
2.9 s once per harness process. Mempool reload of 500
transactions: 4.4 to 8.7 s in shakedown, similar through
the campaign (per-session values in the session files
under setup.loader). Warm-up cycles: all accepted.

### 2.6 What this does and does not establish

Established: the category F harness exists, runs the
unmodified production GBT pipeline, and has measured
its end-to-end cost per accepted block and its stage
partition on this host, closing the BR-010 gap. The
pipeline's fixed cost per block is tens of milliseconds
(empty) to about two hundred milliseconds (500
transactions) under live contention, and it is dominated
by node-side stages (GBT, submitblock validation), not
by the engine.

Not established: anything at production difficulty
(regtest's target admits about one hash in two; scenario
C is an amplified variant, not production), anything on
another host, anything about the solo or pool production
paths' end-to-end cost (their per-candidate EXP-036
verification cost is measured here at about 2.5 to
3.9 ms per candidate; their full pipelines are not
timed by this experiment), and any rate in H/s. The
functional suite is tests/test_exp040_category_f.py
(make test-exp040, wired into test-all).

## 3. Files

- category_f.py: the harness (this directory).
- exp040_analyze.py: the analysis over RAW_RESULTS.
- RAW_RESULTS/session_*.json: the campaign sessions.
- RAW_RESULTS/shakedown_*.json: retained shakedowns.
- RAW_RESULTS/analysis.json: the aggregated record this
  report quotes.
- tests/test_exp040_category_f.py: the functional gate.
