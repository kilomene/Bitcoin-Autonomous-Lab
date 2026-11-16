# EXP-049 (NOVA-ER-0009, register R-35): offline benchmark mode in the production binary

Date: 2026-11-16. Host for every measurement in this report:
AMD EPYC 9D25 126-Core Processor (guest: 4 logical CPUs,
about 2 effective CPUs per EXP-031), recorded from
/proc/cpuinfo at run time. Status at writing: the mode is
built and Gates 1, 2, 3 and 5 are executed; the Gate 4
campaign design and its agreement criterion are predeclared
in section 6 before the campaign runs, and the campaign
results are appended in section 7 after the run. Nothing in
this experiment was pushed; an independent audit gate
applies to this production change before any push.

## 1. Research question and hypothesis

Portfolio NOVA-ER-0009: can the production search path run
a fixed bench work unit with no network and no submission
path compiled into the mode, reporting the category E rate
and the host profile in one command? Motivation: the lab's
hosts alternate (AMD EPYC 9D25, Intel Xeon Platinum
8321HC) and every VM replacement lands on a host with no
one-command profile. The Master Build scheduler measures
through the real search path (262,144 hashes per repetition)
but is an agent-layer tool with no fixed bench work unit in
the production command surface.

Hypothesis: a fixed work unit through
search_first_counted reproduces the research harness's
category E figures within session noise, making the mode a
trustworthy profiling surface.

## 2. Design: the surface, and why it is shaped this way

The mode is a dedicated entry module,
mining/bench_mode.py, invoked as:

    python3 mining/bench_mode.py [--repetitions N]
                                 [--count N] [--json]
                                 [--output PATH]

It imports only the Python standard library plus
gpu.engine (the production compute seam); gpu.engine itself
imports only ctypes, hashlib, os and time. The mode's code
path therefore contains no endpoint resolution, no Stratum
client, no share handling and no chain interface: there is
nothing in the process that could connect anywhere or
present a candidate to anyone. The safety property is a
build property of the import graph, not a runtime flag. The
mode never reads .local/mining-endpoint.json, never opens a
socket, and writes nothing except an optional caller-named
JSON report file.

Why not a flag on mining/mainnet_live.py: mainnet_live
imports the Stratum client and the endpoint configuration
at module level, so a flag inside it would run with the
full submission path imported into the process and the
structural property would be false. The dedicated module
keeps the property true by construction. Cost of the
choice: the small backend label/reason mapping is
reimplemented in miniature inside bench_mode.py (mirroring
mainnet_live.py's backend_reason helper, the Stage 6 D9
fix) rather than imported; the duplication is deliberate
and recorded here.

The change is additive only: no existing production file's
behaviour changes (gpu/engine.py and mining/mainnet_live.py
are untouched; the Makefile gains one test target), and
nothing imports bench_mode. Rollback is deleting one file
and one Makefile target.

Fixed bench work unit: ComputeEngine.search_first_counted
over a pinned 80-byte header, bytes(range(80)), at target 1
from nonce 0 over a fixed count (default 262,144), median
of repetitions (default 5). The header, target and count
are byte-identical to the scheduler's R-35 work unit
(BENCH_HEADER, BENCH_TARGET, WORKLOAD_HASHES in
agent/intelligence/scheduler.py), restated as local
constants so the mode imports nothing from the agent layer;
the figures are therefore directly comparable to the
harness's. Target 1 is met by a real digest with
probability about 2^-256, so the scan covers the full range
in practice; the engine's returned attempted count is the
authority for work done, and the rate is attempted hashes
over wall time measured around the call, the scheduler's
own convention. The reported rate is labelled category E
(complete production search) everywhere it appears.

Report contents per invocation: host profile (hostname,
OS, CPU model from /proc/cpuinfo, logical CPUs, the CPU
flags the production dispatch keys on, cgroup cpu.max when
present, load average), backend selected with its reason,
thread count, the self-check result (section 3), the
median category E rate with every run's attempted count and
wall time, total counted hashes, and an effective-CPU
estimate by the EXP-031 scaling-ratio method (median
2-thread rate over median 1-thread rate on explicit-thread
engines, labelled an estimate, not a core count).

## 3. Gates 1 and 2: correctness

The mode self-checks on every invocation, before any rate
is reported, on the mode's own engine:

- Batch digests: the production batch path over a
  1,024-nonce span at full target must enumerate the whole
  span, and every returned digest must equal the hashlib
  double SHA-256 of the header with that nonce, byte for
  byte. Result on this host: 1,024 verified, 0 mismatched.
- Genesis candidate: a search over the 1,000-nonce span
  containing the genesis nonce at the genesis target must
  agree with a hashlib scan of the same span on whether a
  hit exists, and the returned candidate's digest must be
  the genesis block hash and meet the genesis target.
  Result: found by both, nonce 2083236893, digest matches,
  target met.
- Work-unit accounting: at target 1 the search attempts
  exactly the fixed span count (262,144), confirming the
  counted-hashes authority.

A failed self-check exits nonzero (status 2) and no rate is
presented as trustworthy. The suite
tests/test_exp049_bench_mode.py re-runs all of this: 20
checks, all passed (section 8).

## 4. Gate 3: the mode cannot submit or connect

Four independent demonstrations, all on the real mode:

1. AST scan (in the test suite): bench_mode.py's imports
   are only the standard library plus gpu.engine, and no
   network, endpoint or submission identifier (socket,
   StratumClient, submit, submitblock, connect, endpoint,
   getblocktemplate, and peers) appears anywhere in its
   AST.
2. Import closure (in the test suite): a fresh interpreter
   that imports mining.bench_mode has no mining.stratum_
   client, mining.endpoint_config, mining.solo_server,
   mining.mainnet_live, mining.autopilot, socket or urllib
   in sys.modules.
3. Socket-blocked run (in the test suite): a full bench
   run under a wrapper that replaces socket.socket,
   socket.create_connection, socket.getaddrinfo and
   socket.gethostbyname with raisers completes with exit 0
   and reports a rate, with BAL_POOL_HOST pointed at an
   invalid host for good measure. Any connection attempt
   would have raised.
4. Traced run: strace -f -e trace=network over a full run
   recorded zero network syscalls (the trace file holds
   only thread-exit lines). RAW_RESULTS/strace_network.txt.

The endpoint configuration file's sha256 was identical
before and after every run in the suite: the mode does not
read it, let alone write it.

## 5. Gate 5: no configuration needed

The test suite runs the mode as a subprocess with an empty
environment (PATH only) from a foreign working directory
with an empty home: it completes, reports the host CPU
model and a category E rate. The mode's only file inputs
are /proc/cpuinfo, the cgroup cpu.max file when present,
and the production native libraries under .local/cpu (build
artifacts, not configuration). A literal fresh VM
replacement could not be staged inside this experiment;
the clean-environment run is the simulation, and the first
real post-replacement run is listed as unverified in
section 9.

## 6. Gate 4: comparison campaign, design and predeclared criterion

Predeclared at 2026-11-16, before any campaign run. The
campaign script (exp049_campaign.py) carries this same
text, and its manifest records this report file's sha256
at campaign start so the ordering is checkable.

- Arms: MODE = bench_mode.measure_once on a ComputeEngine()
  constructed exactly as production constructs it (auto
  dispatch, no arguments). HARNESS = Scheduler._measure for
  the tier the mode's engine selected, at the mode engine's
  resolved thread count, repetitions=1.
- Work unit per measurement, both arms: the fixed R-35
  unit (header bytes(range(80)), target 1, start 0, count
  262,144) through search_first_counted; rate = attempted /
  wall around the call.
- Sessions: 3. Pairs per session: 20. Within each pair the
  two arms run back to back in randomized AB/BA order
  (per-session seeded RNG, seeds recorded). Benchmarks run
  strictly one at a time. Host load is recorded (load
  average at each session start), not controlled; the live
  miner runs throughout, as it does for every measurement
  in this programme.
- Statistic: paired log ratio ln(mode rate / harness rate)
  per pair; per-session and pooled mean with a percentile
  bootstrap 95% CI (10,000 resamples of the pairs, seed
  1049).
- AGREEMENT CRITERION: the hypothesis is VERIFIED if the
  pooled bootstrap 95% CI of the mean paired log ratio
  contains 0. If the pooled CI excludes 0, the verdict is
  DISAGREEMENT beyond session noise and the portfolio
  entry's failure criterion is met. Per-session CIs are
  reported either way.

## 7. Gate 4: campaign results

Run 2026-11-16T17:24:54Z to 17:25:02Z, exactly as
predeclared (the manifest's report sha256 at campaign
start, 43f639293c79a93da448e42086940adfc224866ffcab641e
45a46f6aeb189fc4, is the hash of this file with sections
1 to 6 complete and this section empty). The mode engine
selected v512dual and auto-tuned to 4 threads; the harness
arm measured the same tier at the same thread count. 60
pairs, 0 discarded. Conditions were extreme contention:
load average 16.5, 16.5 and 15.9 at the three session
starts (the live miner plus other programme work on the
same guest). Pairing is the defence: both arms in a pair
ran back to back under the same conditions.

Per-session results (medians in H/s; log ratios are
ln(mode / harness)):

- Session 0: mode median 8,390,617; harness median
  5,292,287; mean log ratio +0.2267, CI95 [-0.1392,
  +0.5938].
- Session 1: mode median 14,689,320; harness median
  10,319,431; mean log ratio +0.2135, CI95 [-0.2984,
  +0.7266].
- Session 2: mode median 9,317,612; harness median
  7,622,357; mean log ratio +0.0942, CI95 [-0.2568,
  +0.4331].
- Pooled: mean log ratio +0.1781 (ratio 1.195), CI95
  [-0.0615, +0.4175].

Verdict under the predeclared criterion: AGREEMENT
VERIFIED. The pooled CI contains 0, as does every
per-session CI, so the hypothesis (the mode reproduces
the harness's category E figures within session noise)
stands. The honest width of that statement matters: the
mode arm's point estimate ran above the harness arm's in
all three sessions (about +10 to +25 percent), and the
pooled CI bounds any systematic difference only to
roughly -6 percent to +52 percent. Under this contention
the data cannot resolve a difference smaller than that,
and no tighter agreement is claimed. No mechanism for a
mode-arm advantage is known: both arms call the same
library through the same engine API at the same tier and
thread count, order was randomized per pair, and the rate
convention is identical (attempted over wall around the
call). The residual positive point estimates are recorded
as an observation, not explained away and not promoted to
a claim.

Raw record: RAW_RESULTS/campaign_sessions.json (every
run), RAW_RESULTS/campaign_analysis.json (the statistics),
RAW_RESULTS/mode_profile.json and mode_run_text.txt (one
full mode invocation), RAW_RESULTS/strace_network.txt
(section 4).

## 8. Test suites

Run one at a time on this host, after the change:

- make test-exp049: 20 checks, ALL PASSED (sections 3
  to 5 above are its gates).
- make test-gpu: ALL GPU COMPUTE TESTS PASSED (engine on
  v512dual, CUDA absent with reason recorded, as expected
  on this host).
- make test-mainnet-live: ALL MAINNET LIVE ACCOUNTING
  TESTS PASSED (includes the D9 backend-reason checks
  against the real describe() output).
- make test-engine: ALL INTELLIGENCE ENGINE TESTS PASSED.

Full test-all was not run for this entry; the three
suites above are the ones the change surface touches
(new module, one Makefile target), and the independent
audit gate before any push is the place for the full run.

Live-stack safety: the live mainnet stack was never
restarted or signalled. Share census from a full count of
evidence/mainnet-live.jsonl: 602 accepted / 8 rejected
before the work, 604 accepted / 8 rejected after it; the
+2 accepted are the live miner's own shares during the
window (the mode submits nothing, by construction and by
the section 4 evidence).

## 9. Verdict and UNVERIFIED

Verdict: EXP-049 COMPLETE. The production binary surface
now has an offline benchmark mode whose no-network,
no-submission property is structural and multiply
demonstrated (Gate 3), whose digests and candidate are
verified against hashlib (Gates 1 and 2), which runs with
no configuration (Gate 5), and whose category E figure
agrees with the research harness within session noise
under the predeclared paired criterion (Gate 4). The mode
is a trustworthy profiling surface on this host, at the
agreement width section 7 states.

UNVERIFIED, stated plainly:

- The other host type: the Intel Xeon Platinum 8321HC
  (no SHA extensions, no VBMI) has not run the mode. The
  mode is host-agnostic by construction (auto dispatch,
  CPUID probes), but its Intel figures, and the tier it
  selects there, are unmeasured until a rotation.
- A literal fresh VM replacement: Gate 5 was a
  clean-environment simulation, not a replacement. The
  first real post-replacement run is still to be observed.
- Agreement tighter than the section 7 CI width: under
  quieter conditions the paired campaign would resolve a
  smaller difference; that run has not been done, and the
  consistent positive point estimates are unexplained.
- CUDA hosts: no GPU exists here; the mode's CUDA branch
  is the production engine's own dispatch, unexercised by
  this experiment.
- The mode under the Prompt 1 OS sandbox: not run; the
  Gate 3 evidence above was gathered on the host directly
  (AST, import closure, socket rigging, strace).

Next unreserved experiment ID: EXP-050.
