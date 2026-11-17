# EXP-052 predeclaration (written before the campaign runs)

Written: 2026-11-17, before any EXP-052 measurement was
taken. This file's sha256 is pinned in the campaign
driver, the analyzer and the test suite. EXP-052 is
portfolio NOVA-ER-0012 (register R-23): bake-off
hardening into production dispatch. It follows EXP-058
in the Stage 9 execution sequence; the EXP-052 identity
was reserved for this entry throughout Stage 9.

## Question and hypothesis

Can the advisory scheduler bake-off be hardened into a
production dispatch input that picks the empirically
fastest backend tier per host, with a minimum margin
over the static order, re-runs on host change, and
falls back to the static order on any doubt, without
ever picking a worse tier outside noise?

Portfolio hypothesis: with an EXP-017-shaped median
protocol and a margin set above the measured noise
floor, the hardened bake-off never underperforms the
static order beyond noise across host rotations.

Scope limit fixed here: the portfolio entry completes
only after at least one rotation of each host kind, or
with an explicit partial verdict. This campaign runs
on the current host only (AMD EPYC 9D25, confirmed
from /proc/cpuinfo at build start). The verdict of
this campaign is therefore at most PARTIAL: everything
definable and measurable on this host, with the
cross-host portion (an Intel Xeon Platinum 8321HC
rotation, and a second AMD rotation) recorded as
outstanding. Full completion is not claimed under any
outcome of this campaign.

## Existing evidence (recorded, cited)

- The Milestone 4 advisory bake-off
  (agent/intelligence/scheduler.py, design R-23 with
  the R-35 real-search-path instrument) exists and ran
  live once: shani was the nominal winner over v512 by
  0.8 percent, inside contention noise. It picks the
  argmax of medians of 3 repetitions with no margin
  rule, no significance test and no doubt semantics
  beyond a cache keyed by CPU model plus flags hash.
  That is precisely the gap this entry hardens.
- EXP-031 (research/sha256d/exp031/
  CPU_VM_CHARACTERIZATION.md): run-to-run variance at
  fixed configuration is large (the 2-thread rate
  differed by about 20 percent between runs 30 seconds
  apart); steal 1.4 to 2.7 percent and insensitive to
  thread count; saturation at about 2 effective CPUs
  against 4 claimed vCPUs; baseline guest busy 61 to
  64 percent with the live stack running. Unpaired
  comparisons on this VM are meaningless at the
  percent level, which is why the protocol below is
  paired and interleaved.
- EXP-017 (experiment registry, adopted as the
  programme integration decision rule by owner
  decision 2026-11-14): 3 or more sessions, paired
  65,536-hash blocks, randomised AB/BA order, adjusted
  bootstrap CI entirely above 0 in every session and
  pooled, plus full correctness gates. EXP-054's
  analyzer is the reference implementation of the
  statistic: paired log-ratio, OLS adjustment on the
  steal-difference, runnable-load-difference and order
  covariates, 10,000-resample pairs bootstrap,
  deterministic sha256-derived seeds (never the salted
  built-in hash; the EXP-053 seed lesson).
- EXP-049 (mining/bench_mode.py): the fixed bench work
  unit (80-byte header bytes(range(80)), target 1) and
  the per-engine correctness self-check (1,024-nonce
  batch digests against hashlib byte for byte, plus
  the genesis-span search agreement) that Gate 4
  re-runs per tier.
- NOVA-ER-0002's attribution work and EXP-045:
  session-conditions effects on this VM are real and
  are handled here by pairing, covariates and the
  control comparison, not by assumption.

## Sizing probe (disclosed, pre-predeclaration)

On 2026-11-17, before this file was written, a sizing
probe ran ONE 65,536-hash block and ONE 262,144-hash
block per requested tier at 2 threads (wall times
only, no comparative verdict drawn; single blocks are
noisy and none is cited as evidence anywhere).
Resolved backends: auto to v512dual, v512dual to
v512dual, v512 to v512, shani to shani, avx2 to avx2,
c to c, cuda to cpu (no CUDA device on this host),
hashlib to cpu (the engine's pure-Python tier).
Slowest single 65,536 block: about 0.29 s (the cpu
fallback). These figures fix only the pair count
below: at 150 pairs per comparison per session, the
worst comparison costs about 90 s of measurement and
a full session about 4 minutes.

## C_THREADS dependency (portfolio-named, verified)

The portfolio entry requires the C_THREADS
shared-global defect to be fixed or worked around
before concurrent measurement is trusted. Verified
from the code at build start, not re-fixed: Stage 7
removed the gpu.engine module global; the thread
count is instance-scoped (ComputeEngine.c_threads,
gpu/engine.py, with DEFAULT_C_THREADS an immutable
constant read once from the BAL_C_THREADS environment
value at import). The scheduler's measurement path
passes the count through the ComputeEngine
constructor on a throwaway instance per (tier,
thread count) pair, and this campaign's driver does
the same. No shared state is set or restored anywhere
in the measurement path.

## Design fixed here

- New additive component mining/bakeoff_dispatch.py:
  host fingerprinting (CPU model, sha256 of the
  sorted flags string, logical CPUs, from
  /proc/cpuinfo, standard library only), the EXP-017
  protocol runner, the decision rule, the verdict
  cache (write, read, strict validation), and the
  dispatch resolver. The agent-layer advisory
  scheduler is unchanged.
- The dispatch seam: mining/mainnet_live.py builds
  its ComputeEngine through the resolver ONLY when
  the operator enabled the bake-off section of the
  endpoint config. The section is added to
  mining/endpoint_config.py in the EXP-050 pattern
  (BAKEOFF_DEFAULTS, enabled False, merged over the
  config file). Disabled (the default, and the live
  config's state): the resolver is never called, no
  cache is read, and the engine is constructed
  exactly as today (requested "auto", the static
  order cuda, v512dual, v512, shani, avx2, c,
  hashlib). Enabling the switch is an operator
  decision and is NOT done in this experiment.
- Dispatch never measures. Measurement happens only
  in the bake-off runner (the campaign driver here,
  or an operator-run invocation later). On host
  change the fingerprint mismatch voids the cached
  verdict (static fallback) and a fresh runner
  invocation produces the new host's cache: that is
  the re-run on host change.
- Tier set: the static order's requested values
  [cuda, v512dual, v512, shani, avx2, c, hashlib].
  A requested value is eligible on a host iff the
  engine it constructs reports the backend the value
  denotes (cuda to cuda, v512dual to v512dual, v512
  to v512, shani to shani, avx2 to avx2, c to c,
  hashlib to cpu, the engine's name for its
  pure-Python tier). Ineligible tiers are recorded
  with the resolved backend and excluded, never
  worked around. The static pick is the requested
  value denoting the backend that requested "auto"
  resolves to (v512dual on this host, per the sizing
  probe; the campaign re-derives it, it is not
  assumed).

## Decision rule (the deliverable, stated before any run)

- Protocol: 3 sessions. Per session, per comparison,
  150 paired blocks of 65,536 hashes through
  ComputeEngine.search_first_counted (header
  bytes(range(80)), target 1, nonce 0, engines
  constructed per tier with threads=2 explicit).
  Pair order randomised AB or BA per pair from the
  session's deterministic seed. The attempted count
  is asserted equal to 65,536 on every counted call;
  a violation voids the pair and is recorded.
  Steal and runnable-load covariates are sampled
  around every counted call (the EXP-017 form:
  second steal sample minus first steal sample).
- Comparisons: every eligible challenger against the
  static pick, plus the control (static pick against
  itself).
- Statistic: the EXP-017 statistic as implemented by
  EXP-054's analyzer. Per-pair log ratio of rates
  (challenger over static), OLS adjustment on the
  steal-difference, runnable-difference and order
  covariates, 10,000-resample pairs bootstrap,
  deterministic seeds derived from sha256 of
  "EXP-052:<comparison>:<session>" (and ":pooled"),
  adjusted 95 percent CIs per session and pooled.
- Margin: 5 percent (log bound log(1.05)). Basis:
  the one live advisory margin was 0.8 percent and
  inside noise; the paired design exists to cancel
  the roughly 20 percent unpaired run variance
  EXP-031 recorded; EXP-054 resolved a 0.16 percent
  effect at 30,000 pairs per session, so 150 pairs
  per session resolves percent-level effects and
  5 percent sits above this protocol's noise floor
  with room, while any true gap below 5 percent is
  not worth a non-static dispatch risk.
- Displacement: a challenger displaces the static
  pick iff its adjusted CI lower bound exceeds
  log(1.05) in EVERY session AND pooled, AND the
  control pooled adjusted CI lies entirely within
  plus or minus log(1.05) (the resolution check: if
  the control cannot resolve 5 percent in this
  campaign, nobody is certified), AND the challenger
  passed the Gate 4 correctness gates. If several
  challengers qualify, the one with the highest
  pooled adjusted point estimate is the winner. In
  every other case the verdict is STATIC (the static
  order stands for this host).
- Cache: written only by the runner, atomically.
  Fields: schema version, protocol id
  "exp052-bakeoff-v1", fingerprint, static pick,
  verdict winner (a requested value, or null for
  STATIC), margin, per-tier summaries (eligibility,
  resolved backend, median rates), campaign id,
  timestamp. The resolver validates strictly: exact
  schema and types, protocol id match, fingerprint
  equality with the current host, winner in the
  denotation set, cached margin at least the
  predeclared 0.05, cache age at most max_age_s
  (default 604,800 s, 7 days), every numeric field
  finite. Any failure is doubt and resolves to the
  static order with the reason recorded.

## Gates, fixed in advance (Gates 1, 2 and 6 do not apply)

- Gate 3 (adversarial, offline, synthetic caches and
  stubbed probes; every case must fall back to the
  static order or refuse, none may raise out of the
  resolver): (1) cache file missing; (2) cache not
  JSON; (3) cache JSON with missing keys or wrong
  types; (4) fingerprint mismatch in CPU model; (5)
  fingerprint mismatch in flags hash; (6) stale cache
  (age beyond max_age_s); (7) winner naming an
  unknown tier; (8) non-finite numbers in the cache
  (NaN or infinity tokens, or strings in numeric
  fields); (9) cached margin below the predeclared
  margin, or protocol id mismatch; (10) probe
  failure: engine construction raising for every
  tier during a runner invocation yields a doubt
  record and no cache write, and a pre-existing valid
  cache is left untouched; (11) switch disabled with
  a valid winner cache present: the resolver returns
  "auto" and never reads the cache; (12) verdict
  STATIC in a valid cache: the resolver returns
  "auto" with the static-confirmed reason.
- Gate 4 (the campaign of record): the protocol
  above, run against the live host alongside the
  live mining stack (contention recorded per pair;
  the paired design and the covariates are the
  answer to it, and no quiet window is claimed).
  Correctness gates re-run per tier before
  measurement: the EXP-049 self-check on each tier's
  engine (1,024 batch digests against hashlib, 0
  mismatches required; genesis-span search agreement
  required). A challenger failing correctness is
  excluded and recorded; the static pick failing
  correctness is a Gate 4 failure. Session
  integrity: each (session, comparison) unit is
  written atomically on completion; a unit with a
  complete file is never repeated and the driver
  discloses skips; an interrupted unit leaves no
  file and is re-run whole. Campaign wall budget:
  3,600 s of measurement; sessions run strictly one
  at a time, never in parallel.
- Gate 5 (dispatch seam trial, isolated instances
  only): in a temporary directory, with explicit
  config dicts and cache paths, never the live
  config: (a) the real campaign cache with the
  switch on resolves to the campaign verdict, and a
  ComputeEngine constructed with the resolved
  requested value reports the expected backend;
  (b) a restricted-tier protocol run (tiers v512 and
  shani only, static pick v512, 1 session, 40 pairs,
  the same runner code and the same margin rule)
  produces a genuine cache in the isolated
  directory; the resolver with the switch on returns
  its winner and the constructed engine's backend
  matches; (c) that cache corrupted resolves to
  static; (d) that cache with a tampered fingerprint
  resolves to static; (e) the switch off with that
  winner cache present resolves to "auto". The live
  endpoint config file's sha256 is recorded before
  and after the whole experiment and must be
  identical.

## Verdict mapping, predeclared

- Gate 3 all pass AND Gate 4 campaign completes
  (3 sessions, every comparison, correctness gates
  passing for the static pick) AND Gate 5 all pass:
  EXP-052 is PARTIAL COMPLETE for this host,
  classification PROMISING HYPOTHESIS (the portfolio
  hypothesis is cross-rotation and stays unproven),
  registry status UNDER_INVESTIGATION. The on-host
  properties are proven at gate level as measured:
  the protocol ran, the fallback is sound against
  the Gate 3 cases, the seam honours a valid verdict
  and falls back on doubt, and this host's verdict
  (winner or STATIC) is whatever the decision rule
  produced. A certified winner does NOT complete
  the entry and does NOT enable the switch.
- Any Gate 3 case failing to fall back, any Gate 5
  seam failure, or the static pick failing Gate 4
  correctness: EXP-052 is ESTABLISHED NEGATIVE for
  this design, registry status REJECTED, the feature
  stays advisory (the switch stays off; the code
  stays default-off), and the failure is recorded.
- The campaign cannot complete inside the wall
  budget (for example repeated VM replacement):
  INCONCLUSIVE, registry status UNDER_INVESTIGATION,
  completed sessions recorded, the remainder
  outstanding with the cross-host portion.

## Hard lines and scope

- No other machine is contacted. Fleet activation is
  owner-gated and is not performed.
- The live miner, autopilot, solo server and node
  are untouched: no process is signalled, no live
  config is read by any driver except the endpoint
  config's sha256 fingerprint for the Gate 5
  integrity record, and .local/mining-endpoint.json
  is never written. The campaign measures with its
  own throwaway ComputeEngine instances beside
  production, the EXP-031 load-probe pattern.
- Exact SHA-256d only; the measurement workload uses
  the production engine at target 1 (full scans), so
  no share validation path is exercised; where
  validation would apply, EXP-036 is the only route.
- Production files change only by addition, plus the
  two declared seam edits: mining/bakeoff_dispatch.py
  is new; mining/endpoint_config.py gains the
  bake-off defaults and accessor (additive, in the
  EXP-050 pattern); mining/mainnet_live.py gains one
  conditional block that is inert while the switch
  is off; the Makefile and the three registries gain
  the EXP-052 entries.
- Host: AMD EPYC 9D25 (confirmed from /proc/cpuinfo
  at build start). No GPU exists and none is
  claimed. Results on other hosts are UNVERIFIED.

## UNVERIFIED register (predeclared, stands regardless of outcome)

- Behaviour across host rotations (an Intel Xeon
  Platinum 8321HC rotation, a second AMD rotation):
  UNVERIFIED and outstanding; the portfolio entry
  completes only there or stays partial.
- Live enablement of the dispatch switch, and any
  effect of a bake-off pick on the live mining rate:
  UNVERIFIED, not attempted; enablement is an owner
  decision.
- The pick on any host other than this one:
  UNVERIFIED. The cache is fingerprint-keyed and
  voids itself elsewhere by design, but that the
  protocol picks correctly on an unseen host is the
  cross-rotation claim and is unproven.
- Long-horizon cache behaviour (staleness inside the
  7-day bound while the host's contention profile
  drifts): UNVERIFIED; the bound is a design value,
  not a measurement.
- Behaviour under real fleet conditions (multiple
  machines): UNVERIFIED; no other machine is
  contacted.
