# EXP-048 Report: category F end-to-end measurement of the solo and pool pipelines (portfolio NOVA-ER-0008)

Status: COMPLETE 2026-11-16 (design in section 1 written
before the campaign; two shakedown amendments recorded in
section 1.7; results in section 2).
Programme: NOVA SHA-X, Directive 5 Stage 9 (portfolio
NOVA-ER-0008). This experiment extends the EXP-040 category
F harness (research/sha256d/exp040/, which measured the GBT
pipeline only, at regtest difficulty) to the lab's two
Stratum pipelines, closing the standing gap Stage 0
recorded: no end-to-end figure at any difficulty for the
solo or pool pipelines, and nothing at production
difficulty for any pipeline.

Host for every measurement in this report: AMD EPYC 9D25
126-Core Processor, 4 vCPUs visible in the guest (about 2
effective CPUs per EXP-031). Contention state, stated per
the Hashrate Measurement Specification and never omitted:
the live mainnet pool miner (v512dual backend) and the
pruned mainnet node ran throughout; session manifests
record load averages at session start (1-minute load
between about 9 and 16 across the campaign). The live
miner's share census moved 589 accepted / 8 rejected
before the campaign to 600 / 8 after it; the harness never
touched, signalled, or reconfigured the live stack. Every
figure here is a single-VM, contended, regtest figure.
None of them is a hash rate. Category F figures are time
per block and overhead milliseconds, per the Gate 4
category F form.

## 1. Design (written before the campaign)

### 1.1 Question and hypothesis

Question (portfolio NOVA-ER-0008): what is the end-to-end
cost per block of the solo and pool pipelines at
production difficulty, and what is their non-search
overhead in absolute milliseconds?

Hypothesis (from the portfolio entry): the transferable
overhead figures (milliseconds per block) for solo and
pool will be of the same order as the GBT pipeline's, with
the solo path's share handling at adapted difficulty the
largest single stage; the amplified method transfers
without modification of production code.

"Production difficulty" is made precise for a Stratum
pipeline: the searched target is the SHARE target, and
the production configuration sets it at difficulty 0.02
(mining/endpoint_config.py SOLO_SHARE_DIFFICULTY, the
armed cutover's setting; the pool stub sets the same).
The network target on regtest (bits 0x207fffff, about
2^255) admits about one hash in two, so every share at
difficulty 0.02 also meets the network target, and a run
that ends in a submitted share ends in a block. Nothing
here measures mainnet's network difficulty; what
transfers to production is the overhead in milliseconds
and the stage costs, exactly as EXP-040 established for
the GBT pipeline.

### 1.2 The pipelines as measured

- Solo: the production SoloServer (mining/solo_server.py)
  in-process, served by the production SoloTCPServer on
  localhost, fed by the regtest node. Vardiff DISABLED
  (vardiff=None, the production configuration and the
  armed cutover's configuration) for scenarios A/B/C.
  Scenario D passes a VarDiffController built from the
  production default parameters (endpoint_config
  SOLO_VARDIFF_DEFAULTS, initial 0.02), harness-side
  construction only, and is labelled separately.
- Pool: a local pool-protocol stub built in the harness
  (research/sha256d/exp048/category_f_stratum.py). It
  does the work a real pool does for a block: builds jobs
  from getblocktemplate with the production coinbase
  builder and merkle branch helpers, serves Stratum V1,
  judges shares against its share target, runs every
  target-meeting candidate through the EXP-036 exact
  verifier, assembles and submits network-target blocks,
  and counts a block only on chain confirmation. It is
  not a production component; multi-worker pool
  infrastructure, payout accounting, and pool-side
  vardiff are outside its scope by design. The harness
  never connects to public-pool.io.
- Client (both pipelines): a loop with the
  mining/mainnet_live.py shape over the production
  StratumClient and ComputeEngine: poll (job, generation,
  difficulty) under the client lock; build the header per
  extranonce2 round (build_header, wordswap); scan
  ~1-second spans with search_first, sized from the
  probe rate exactly as mainnet_live sizes them; account
  attempts with mainnet_live's own call_attempts; confirm
  every candidate through verify_candidate (EXP-036)
  before submitting; block candidacy from the verifier
  alone. The one chain-appropriate substitution is the
  proof-of-work limit constant (POW_LIMIT_REGTEST here;
  mainnet_live uses POW_LIMIT_MAINNET).

No production file is modified. The failure criterion was
predeclared: if a pipeline could not be instrumented
without production changes, that boundary would be
reported rather than crossed. It was not hit.

### 1.3 The timed run

A timed run starts when the harness begins it (after
scenario setup, which is never inside a timed run, the
EXP-040 discipline) and ends when the run's block is
confirmed as the node's best block hash. A run counts
only if it ends in exactly one Core-accepted block (Gate
6 in harness scope) and the block's header passes the
EXP-036 gate in the client loop before submission.
Failed runs are retained in the raw record, labelled, and
excluded from statistics (specification section 6).

Stage attribution is two nested views, labelled as such
(the pipelines are two processes' worth of threads, not
EXP-040's single cycle):

- Client view (partitions the run wall time): job_wait
  (supply latency of the fresh job for the new tip: the
  previous block's post-block refresh and broadcast may
  still be in flight when the run begins; the push-based
  analogue of EXP-040's in-cycle GBT fetch), construct
  (build_header per extranonce2 round and per candidate),
  search (the compute proxy's search_first time),
  verify_client (the EXP-036 confirmation of candidates),
  submit_send (the client.submit call), verdict_wait
  (from submit until the server's verdict arrives; for a
  block share the server responds only after its own
  validation, verification, block submission, and chain
  confirmation, so this stage CONTAINS the server view),
  confirm (the harness's own best-block-hash poll until
  equality), residual (wall minus the above: loop
  bookkeeping and reader-thread processing; median under
  1.5 ms in every scenario).
- Server view (decomposes verdict_wait; exclusive times
  on the server's handler thread, so totals nest inside
  the submit handling, not beside it): submit_total's
  own remainder, validate (solo: validate_share, which
  recomputes the full merkle root over the job's
  transactions; stub: header rebuild and fast compare),
  verify (the server-side EXP-036 verify_candidate),
  assemble (stub only; the solo server's assembly is
  inside its submit path and its RPC time is what is
  timed), gbt (getblocktemplate calls: post-block
  refreshes in-run, and for scenario B the setup window's
  refreshes, recorded separately as setup stages), submit
  (the submitblock RPC), chain (chain-state reads:
  check_node and verify_chain_acceptance), rpc_other.

Instrumentation is wrapping in this process only: a
thread-aware segment timer; a delegating RPC proxy on
each server's node client; the solo instance's
submit_share / validate_share / refresh_job methods and
the solo_server module's verify_candidate binding
wrapped; a delegating compute proxy on the client engine
(search timing, and scenario C amplification, section
1.4). Wrapper cost is one perf_counter pair and a list
append per wrapped call, orders of magnitude below the
smallest stage it touches, and is not corrected for.

### 1.4 Difficulty and amplification

At difficulty 0.02 the expected search work per block is
0.02 x 2^32 = 85,899,346 hashes (the share target is the
searched target; the first share found is the block, per
section 1.1). Scenarios A and B therefore already carry
real search mass, unlike EXP-040's real-target scenarios
(a handful of hashes).

Scenario C exists, as in EXP-040, to measure the stage
partition when search carries still more mass. EXP-040
divided the searched (network) target by 2^24. Here the
searched target is the share target; dividing it by 2^24
would make the expected work per block 0.02 x 2^32 x
2^24 = 2^50.4 hashes, not measurable in any feasible
campaign. The compute proxy therefore divides the search
target by 2^2 (factor 4, stated wherever the figures
appear), giving an expected ~3.4e8 counted hashes per
block, about 20x the search mass of EXP-040's scenario C.
Produced blocks still meet the real regtest target and
pass the EXP-036 gate; the client's own verification
always uses the unamplified share target.

Counted hashes are the production accounting: the
backend's last_search_stats attempted, via call_attempts,
the identical definition the live miner uses and EXP-040
used. A probe run for this report (RAW_RESULTS/
probe_search_accounting.json) establishes what that
accounting is on the AVX-512 backends: it is the parallel
search's own count of work examined until it stopped, NOT
a positional census. On a controlled header (target
2^232, hashlib positional first hit at nonce 812,061),
v512dual returned a real hit at nonce 17,335,985 with
3,943,360 counted attempts; over [0, 2^24) the resumed
AVX-512 searches returned only the later of the two real
hits, where the C backend returned both in order. The
AVX-512 search reports the first hit in its parallel
scan's completion order, and the production loop's
resume-at-hit+1 pattern (mirrored by this harness) does
not rescan the span's earlier part. This is the
production search's real behaviour, measured as-is; it
means counted hashes on hit-terminated spans run below
positional expectation, which is why scenario C's counted
medians (section 2.4) sit at about 2.0 to 2.3x scenario
A's rather than the 4x positional factor. On a full-span
miss the counted attempts equal the span exactly
(verified: 16,777,216 of 2^24).

### 1.5 Scenarios

- A, empty: mempool empty (asserted size 0 before each
  run), template carries the coinbase only.
- B, loaded: mempool loaded with 500 simple transactions
  by the EXP-040 loader before each run (asserted size
  500, and the served template asserted to carry 500
  transactions before the run starts), so the template
  carries 501 transactions. Reload is setup: recorded,
  never in a timed run.
- C, amplified: empty mempool, search target divided by
  2^2 in the compute proxy (section 1.4).
- D, solo only, separately labelled: vardiff ENABLED
  with the production default parameters, empty mempool,
  otherwise identical to A. Two sessions of 5 runs.

Each primary scenario runs 3 sessions per pipeline. A
session builds a fresh server, client, ComputeEngine, and
payout address, runs one untimed warm-up block that must
end accepted, then the timed runs: 8 per session for A
and B, 5 for C. Sessions ran strictly sequentially;
nothing else was benchmarked in parallel.

### 1.6 Statistics

Per pipeline and scenario: per-stage and end-to-end
medians with min, max, and interquartile range across the
scenario's timed runs (sessions pooled only after
per-session medians are printed; the per-session numbers
stay in the raw files and in this report's table). The
headline transferable quantity is the non-search overhead
in milliseconds per block: per run, cycle wall minus the
search stage, reported as median and as a fraction of
wall. Because the search time per block is geometrically
distributed (a memoryless lottery at fixed difficulty),
end-to-end medians carry that distribution's full spread
and loaded-versus-empty end-to-end ratios are expected to
be uninformative; the loaded-versus-empty comparison is
therefore made on the template-supply cost (setup-window
GBT plus in-run refresh GBT plus client construction),
with a bootstrap confidence interval over runs (10,000
resamples, fixed seed). This is a measured comparison,
not an EXP-017 protocol verdict, and no VERIFIED
IMPROVEMENT language attaches to it.

### 1.7 Shakedown amendments (before any campaign run)

Shakedown sessions (retained under RAW_RESULTS/ with the
shakedown_ prefix, excluded from statistics) forced two
design corrections, both recorded here:

1. Run start. The first design started the cycle clock
   at the previous block's confirmation, which put
   scenario B's reload (seconds of setup) inside the
   timed window. Corrected to the EXP-040 discipline:
   setup is never in a timed run; the run starts when the
   harness begins it after setup, and the setup window's
   server stages are recorded separately per run.
2. Template caching. An immediate refresh after a
   mempool load can serve Core's cached template (v28.1
   rebuilds getblocktemplate on a tip move or when the
   mempool change is about 5 s old). Scenario B setup
   therefore polls the refresh until the served template
   carries the 500 transactions (observed waits 2 to 3 s),
   and asserts the count before every run.

Log noise, disclosed: at solo session teardown the
production SoloTCPServer's handler thread prints a
socketserver ConnectionResetError traceback when the
client socket closes. It occurs after the session file
is written, affects no measurement, and is the
production server's default error handling, which this
experiment does not modify.

## 2. Results (measured 2026-11-16, this host, contended)

Campaign as designed: solo A/B 3 sessions of 8 runs, solo
C 3 of 5, solo D 2 of 5, pool A/B 3 of 8, pool C 3 of 5,
strictly sequential. Session files:
RAW_RESULTS/session_<pipeline>_<scenario>_<index>_<stamp>
.json (20 files; five shakedown_ files retained and
excluded). Timed runs: 136. Failed runs: 0. Every timed
run ended in exactly one block accepted by Core
(best-chain equality) whose header had passed the
EXP-036 gate in the client loop. Timed-run heights: solo
A 1936 to 1961, C 1963 to 1979, B 1983 to 2008, D 2010
to 2020, pool A 2022 to 2047, C 2049 to 2065, B 2067 to
2092 (warm-up blocks interleave; the raw files are
authoritative). Backend selected by the production probe
in every session: v512dual.

### 2.1 End-to-end per accepted block (category F)

Medians across the scenario's timed runs; per-session
medians in brackets.

| Scenario | Median s/block | Min | Max | IQR | Blocks/hour (aggregate) |
|---|---|---|---|---|---|
| solo A empty | 5.280 [4.38, 6.46, 5.04] | 0.695 | 17.819 | [3.070, 6.952] | 588 |
| solo B loaded (501 tx) | 6.046 [4.87, 6.22, 6.75] | 0.811 | 25.526 | [3.713, 11.295] | 452 |
| solo C amplified (x4 target division) | 15.334 [47.94, 13.98, 10.24] | 1.331 | 102.709 | [10.839, 45.715] | 114 |
| solo D vardiff on (labelled) | 4.651 [2.62, 6.29] | 0.161 | 21.773 | [2.790, 12.393] | 479 |
| pool A empty | 5.068 [5.00, 9.44, 4.34] | 0.345 | 18.332 | [2.429, 10.661] | 511 |
| pool B loaded (501 tx) | 4.087 [9.47, 3.32, 1.10] | 0.040 | 13.202 | [1.516, 9.650] | 643 |
| pool C amplified (x4 target division) | 8.829 [25.88, 8.83, 8.82] | 0.295 | 75.944 | [2.291, 42.453] | 143 |

These end-to-end times are dominated by the geometric
search at difficulty 0.02 (expected 8.59e7 hashes per
block; counted medians 6.0e7 to 8.2e7 in A/B/D), so their
spread is the lottery's spread, and loaded-versus-empty
end-to-end ratios are uninformative by construction
(solo 1.14x, CI [0.68, 2.25]; pool 0.81x, CI [0.34,
2.07]; both intervals span 1, as designed for in section
1.6). They are NOT comparable to EXP-040's end-to-end
figures (0.065 s empty, 0.215 s loaded, 3.299 s
amplified): the GBT pipeline at the real regtest target
searches a handful of hashes per block, while the
Stratum pipelines at the production share difficulty
search ~8.6e7. The comparable quantities across
pipelines are the overhead milliseconds and stage costs
below. The first C session of each pipeline ran under
the campaign's heaviest contention (its session medians,
47.94 s solo and 25.88 s pool, sit far above the other
two sessions); pooling is the honest summary and the
per-session figures stay printed.

### 2.2 Client stage breakdown (median ms per block)

| Stage | solo A | solo B | solo C | solo D | pool A | pool B | pool C |
|---|---|---|---|---|---|---|---|
| Job wait | 2.94 | 0.01 | 2.11 | 4.01 | 0.01 | 1.05 | 0.01 |
| Construct (headers) | 0.09 | 0.11 | 0.08 | 0.08 | 0.09 | 0.11 | 0.08 |
| Search (counted backend) | 5,198.7 | 5,838.1 | 15,282.2 | 4,560.3 | 5,046.2 | 3,902.8 | 8,804.7 |
| Verify (client EXP-036) | 1.81 | 5.37 | 3.76 | 3.50 | 2.42 | 2.65 | 1.84 |
| Submit send | 1.89 | 3.00 | 3.71 | 2.62 | 3.05 | 5.73 | 7.72 |
| Verdict wait | 58.34 | 114.14 | 89.45 | 77.72 | 23.02 | 163.84 | 76.94 |
| Confirm (best-hash poll) | 2.38 | 2.88 | 4.29 | 1.56 | 2.78 | 2.34 | 1.94 |
| Residual | 0.69 | 0.51 | 1.41 | 0.56 | 0.60 | 0.46 | 0.69 |

Client-side header construction is a tenth of a
millisecond per block even for the 501-transaction
template (the client folds a 9-entry merkle branch; it
never rebuilds the block). The client EXP-036
confirmation costs 1.8 to 5.4 ms per candidate,
consistent with EXP-040's 2.5 to 3.9 ms measured on the
GBT path.

### 2.3 Server stage breakdown (median ms per block)

Exclusive times on the server's handler thread; the
submit-path rows nest inside the verdict wait above.

| Stage | solo A | solo B | solo C | solo D | pool A | pool B | pool C |
|---|---|---|---|---|---|---|---|
| Validate share | 0.06 | 0.86 | 0.05 | 0.06 | 0.06 | 0.07 | 0.05 |
| Verify (server EXP-036) | 2.07 | 3.92 | 2.52 | 2.76 | 2.07 | 2.57 | 1.85 |
| Assemble block (stub only) | n/a | n/a | n/a | n/a | 0.02 | 0.53 | 0.02 |
| Submitblock RPC | 22.43 | 103.45 | 73.26 | 35.86 | 20.07 | 165.02 | 45.26 |
| Chain reads | 9.13 | 13.74 | 24.03 | 11.12 | 1.70 | 4.04 | 1.68 |
| GBT, post-block refresh (in-run) | 0.64 | 0.00 | 4.31 | 4.02 | 3.42 | 2.22 | 2.38 |
| GBT, loaded template (setup window) | n/a | 66.49 | n/a | n/a | n/a | 64.85 | n/a |

Reading of the server columns:

- Share judging itself is cheap in both pipelines:
  validate plus the EXP-036 verify is about 2.1 to
  4.8 ms per submitted share. The solo server's
  validate rises from 0.06 ms (empty) to 0.86 ms
  (loaded) because validate_share recomputes the full
  merkle root over the job's 501 transactions for every
  share; the stub validates by branch folding (0.07 ms
  loaded), the real-pool shape. At the production share
  cadence (one share per ~7 s at the lab's rate, per the
  endpoint config's own estimate) even the solo figure
  is negligible server load; it is recorded because it
  is the one per-share cost that grows with template
  size on the solo path.
- The dominant server cost of a block is node-side:
  submitblock validation (20 to 165 ms; the loaded
  block costs the node the most in both pipelines),
  plus the chain-confirmation reads. This is the same
  shape EXP-040 found on the GBT path (submit 13.6 ms
  empty, 99.9 ms loaded).
- The loaded template's GBT build costs about 65 to
  66 ms in both pipelines' setup windows (the figure
  includes the cache-poll refreshes of section 1.7; a
  single uncached build is bounded by it). EXP-040's
  in-cycle GBT fetch for the loaded template was
  38 ms; the two figures measure the same node work
  through different windows.

### 2.4 The non-search overhead (headline)

Per run, cycle wall minus the search stage:

| Scenario | Median overhead | Median fraction | Counted hashes/block (median) |
|---|---|---|---|
| solo A empty | 97.0 ms | 0.0184 | 7.56e7 |
| solo B loaded | 152.4 ms | 0.0283 | 8.17e7 |
| solo C amplified | 115.6 ms | 0.0054 | 1.74e8 |
| solo D vardiff on | 89.3 ms | 0.0180 | 5.96e7 |
| pool A empty | 55.9 ms | 0.0103 | 6.73e7 |
| pool B loaded | 210.7 ms | 0.0521 | 6.17e7 |
| pool C amplified | 97.7 ms | 0.0096 | 1.37e8 |
| GBT A empty (EXP-040) | 43.5 ms | 0.930 | 32 |
| GBT B loaded (EXP-040) | 206.3 ms | 0.992 | n/a |
| GBT C amplified (EXP-040) | 49.5 ms | 0.015 | 1.68e7 |

The transferable result: all three production pipelines
carry a fixed cost of roughly 50 to 210 ms per block on
this contended VM, empty to 501-transaction templates,
and in every pipeline the largest part of it is the
server/pool-side submit path ending in node-side
submitblock validation. The Stratum overheads sit at
search fractions of 0.5 to 5 percent because their
search stage already carries production-difficulty mass;
the GBT real-target fractions near 1 are the same fixed
cost measured against a near-zero search. Scenario C
shows the overhead does not grow with search mass
(solo 115.6 ms at 1.74e8 counted hashes vs 97.0 ms at
7.56e7; pool 97.7 ms vs 55.9 ms). Derived arithmetic,
labelled as such (the EXP-040 form): at any difficulty
where the search stage takes T seconds per block, the
overhead fraction is approximately
overhead / (overhead + T) with the overheads above; no
new measurement is claimed by that formula. For the
armed solo cutover this puts the server's operating cost
at about 0.1 to 0.2 s of pipeline time per block plus
about 2 to 5 ms of server CPU per share at difficulty
0.02, against search times that are minutes at pool
difficulty 1 and years at mainnet difficulty on this
hardware.

Template supply, loaded versus empty (measured
comparison, bootstrap 95 percent CI over runs; not an
EXP-017 verdict): solo 3.00 ms empty vs 66.67 ms loaded,
ratio 22.3x, CI [5.59, 42.9]; pool 3.68 ms vs 69.16 ms,
ratio 18.8x, CI [11.2, 29.1]. The Stratum path pays the
loaded-template cost once per job on the server; the
GBT path additionally pays per-template identity work
in prepare (EXP-040's prepare-plus-construct ratio was
147x), which has no Stratum analogue because the client
never rebuilds the template.

### 2.5 Scenario D: vardiff enabled (separately labelled)

Two sessions of 5 runs, all accepted, heights 2010 to
2020. The vardiff machinery ran end to end on the
production server: per-connection state, EMA interval
tracking (3.57 s and 10.56 s at the two sessions' ends),
per-job difficulty snapshots, and exactly one logged
adjustment per session (0.02 to 0.03, an increase at the
1.5x maximum up factor, after the required confirmations
and hysteresis). No stale or duplicate shares occurred
(the single client never produces them). Overhead
89.3 ms vs scenario A's 97.0 ms: at this scale the
vardiff layer adds no measurable overhead. This is a
short-session observation, not a vardiff stability
result: the rate-stepped stability campaign and
two-client interference remain unverified (section 3).

### 2.6 Hypothesis verdict

- "Overheads of the same order as the GBT pipeline":
  SUPPORTED. Solo 97.0 / 152.4 ms and pool 55.9 /
  210.7 ms (empty / loaded) against GBT's 43.5 /
  206.3 ms, same band, same dominant component
  (node-side submission).
- "The solo path's share handling the largest single
  stage": SUPPORTED in the broad sense, REFUTED in the
  narrow sense. Everything the server does with a
  submitted block share, inside the client's verdict
  wait (58 to 114 ms solo), is the largest single
  overhead component in both pipelines. But the share
  JUDGING steps themselves (validate plus EXP-036
  verify) are only about 2 to 5 ms of it; the mass is
  the submitblock RPC and chain confirmation that
  follow. Any future optimisation aimed at "share
  handling" should aim at the submission leg, not the
  judging leg.
- "The amplified method transfers without modification
  of production code": SUPPORTED, with the one stated
  adaptation: the amplification factor is 2^2 on the
  share target rather than 2^24 on the network target,
  for the arithmetic reason derived in section 1.4.
  Zero production files were changed; every block
  passed the EXP-036 gate and Core acceptance.

## 3. What this does and does not establish

Established: category F figures now exist for all three
production pipelines on this host. The solo pipeline
(the armed cutover's path) and the pool pipeline (via a
local stub) both carry roughly 50 to 210 ms of
non-search overhead per block, dominated by node-side
submission; share judging costs single-digit
milliseconds per share in both; the vardiff layer's
overhead is below this measurement's resolution; the
EXP-040 harness method (wrapping only, amplification in
the compute proxy, Gate 6 on every run) transfers to
both Stratum pipelines with zero production changes.
The benchmark category map (BR-010) is complete for all
three pipelines.

Not established: anything at mainnet network difficulty
(the searched target here is the production SHARE
difficulty on regtest; the transferable quantities are
the overhead milliseconds, per section 1.1); the real
public-pool.io pipeline end to end (network latency and
pool-side internals are not measurable from here, and
the harness never connected to it; the pool figures are
the production client path against a local stub doing a
real pool's per-block work); anything on another host;
multi-client behaviour of either server; vardiff
behaviour beyond 6-share sessions (no stale or duplicate
traffic, one adjustment per session, no rate-stepped
stability campaign); the solo server's behaviour under
the mainnet node's IBD-era refusal paths (the regtest
node is never in IBD). No hash rate is claimed anywhere
in this experiment.

Suites run after the campaign, one at a time, all
passing: make test-exp040 (ALL EXP-040 CATEGORY F TESTS
PASSED), make test-solo (ALL SOLO SERVER TESTS PASSED),
make test-solo-vardiff (59/59 checks, ALL SOLO VARDIFF
TESTS PASSED). The harness touches no production code;
the suites cover the production paths it wraps.

## 4. Files

- category_f_stratum.py: the harness (this directory).
- exp048_analyze.py: the analysis over RAW_RESULTS.
- RAW_RESULTS/session_*.json: the 20 campaign sessions.
- RAW_RESULTS/shakedown_*.json: retained shakedowns.
- RAW_RESULTS/client_evidence_*.jsonl: the production
  StratumClient's own evidence logs, one per session.
- RAW_RESULTS/probe_search_accounting.json: the
  counted-attempts accounting probe (section 1.4).
- RAW_RESULTS/analysis.json: the aggregated record this
  report quotes.
