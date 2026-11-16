# EXP-045: AVX2 batch discrepancy resolution (NOVA-ER-0002)

Experiment: EXP-045 (portfolio identity NOVA-ER-0002).
Date: 2026-11-16. Host: AMD EPYC 9D25 126-Core Processor
(guest, hostname htch-runtime; 4 vCPUs visible, about 2
effective CPUs per EXP-031). Standing condition of every
measurement: the live miner (v512dual backend,
autopilot-supervised, pid 2691 throughout, restarts 0,
shares accepted 471 at campaign start and 472 at the
end), the pruned mainnet node in initial block download,
and other agents' work were running throughout and were
never paused, restarted or reconfigured. Load average
(1 minute) at session starts ranged from 3.4 to 18.7
across the campaign, the heaviest sustained mix of the
three campaigns discussed here. Research only: no
production file was modified.

## The discrepancy

EXP-032 measured the AVX2 multi-buffer kernel's batch
rate at pooled 1.409x [1.340, 1.480] against production
C (EXP-017 protocol, 3 sessions). EXP-039 measured the
same kernel, integrated as the production tier
mining/cpu/bal_avx2_mb.c, at pooled 1.252x [1.185, 1.322]
against production C under the same protocol. The
intervals do not overlap. The EXP-039 audit (note N-2)
recomputed the EXP-039 figure from its raw files,
confirmed the discrepancy is real, and left it
unresolved. EXP-039's own report attributed the
difference to session conditions without isolating the
cause. This experiment was designed to isolate it.

## Verdict (three-tier language)

CAUSE IDENTIFIED, by measurement: the discrepancy is a
session-conditions effect on the AVX2 arm, not a
kernel, build, harness or baseline difference. Every
candidate factor that differs between the two campaigns
was crossed in a single 2x2 campaign plus a head-to-head,
and each measured null or near-null:

- Library provenance (research-built .so vs
  production-built .so): head-to-head pooled 0.976x
  [0.930, 1.025], NOT SIGNIFICANT, sessions disagreeing
  in sign. The compiled kernel code is
  instruction-identical between the two libraries
  (section 2).
- Harness path (direct ctypes vs the production
  ComputeEngine.batch_search seam): the ratio moves by
  +1.0% (production library) and +2.3% (research
  library) between harnesses, inside noise, and in the
  direction opposite to the historical gap.
- C baseline drift: refuted at the file level. Both
  campaigns' session manifests record the identical
  libbal_batch.so sha256
  (8794238ce48c561dfb338c5524dace6cecd500497a9e4523cb8855fb3aa036f9),
  and the file on disk today is still those bytes.

What does move the number is when the sessions run. The
AVX2 arm's absolute throughput is highly variable
between sessions in every campaign (session medians
0.64M to 2.57M H/s across all 18 AVX2-vs-C sessions on
record, a 4.0x spread), while the C arm is comparatively
stable (0.84M to 1.07M across the two historical
campaigns). A ratio with a stable denominator and a
high-variance numerator inherits the numerator's
variance: per-session raw ratios span 1.06 to 2.45
across campaigns. The pooled EXP-017 estimate is
therefore a draw from a condition-dependent distribution
on this oversubscribed guest, and the two campaigns
sampled different parts of it. EXP-045, crossing all
factors under the heaviest load mix of the three
campaigns, lands at 1.274x to 1.315x in all four cells,
between the two historical figures.

Both historical verdicts stand unchanged: AVX2 batch is
a VERIFIED IMPROVEMENT over production C (every session
and pooled CI above 1.0 in EXP-032, EXP-039 and every
EXP-045 cell). What changes is the interpretation of
the point estimates: 1.409x is the ratio under EXP-032's
session mix, 1.252x under EXP-039's, and 1.27x to 1.32x
under EXP-045's. None of them is a condition-free
constant of the kernel, and on this guest none exists
at the precision the two original intervals implied.

## 1. Design (stated before the runs)

Factors, one at a time, full crossing:

- Harness DIRECT: counted batch entries called via
  ctypes with caller-allocated buffers outside the timed
  region. This is the exact call shape of both
  historical batch drivers (exp032_paired_bench.py and
  exp039_paired_bench.py batch arms are the same code;
  EXP-039's ComputeEngine seam carried its search arms,
  not its batch arms, a point the historical record
  states imprecisely and this report corrects).
- Harness SEAM: production ComputeEngine.batch_search
  on engines pinned by requested=, wall-clock around the
  whole engine call (dispatch, buffer allocation, flag
  scan, candidate check, stats assembly included), as in
  production use.
- Library RESEARCH: research/sha256d/exp032/libbal_avx2.so,
  the .so EXP-032 measured (sha256 91d0a1b8...).
- Library PROD: .local/cpu/libbal_avx2.so, the .so
  EXP-039 measured (sha256 81a6ca18...).
- Comparator: production C (bal_c_batch2 direct;
  ComputeEngine "c" batch_search in the seam), measured
  inside every cell.
- Fifth comparison: direct head-to-head, production
  library vs research library, C removed from the pair,
  isolating provenance alone.

Protocol for every comparison: EXP-017, unchanged. 3
sessions, 120 paired 65,536-hash blocks per session,
randomised AB or BA order per pair, steal and
runnable-load covariates sampled around every counted
call, attempted == 65,536 asserted on every call,
verdicts from the adjusted statistic computed by the
imported exp017_analyze code (exp045_analyze.py).
Threads pinned to 2 in both harnesses (direct arms pass
threads=2; the seam ran with BAL_C_THREADS=2, the
engine's documented override, asserted in the driver).
Sessions ran strictly one at a time. Total: 15
sessions, 1,800 pairs, about 236 million timed hashes.

One documented harness construction: the research
library exports no CPUID probe symbol, so production
dispatch (gpu/engine.py _try_avx2) would refuse it. The
seam research-library arm builds a ComputeEngine pinned
to avx2 through normal dispatch, then replaces the
engine's loaded library object with a ctypes handle on
the research library, bal_a_batch2 argtypes set exactly
as _try_avx2 sets them. Only the library object differs;
all engine machinery that runs is production code.

Discard rule, declared in advance: a session whose data
shows a contention-spike corruption signature (an arm
median collapsed relative to its sibling sessions, or a
failed coverage assertion) is discarded and rerun, and
the discard recorded. Outcome: no session met the
criterion. All 15 sessions completed 120 of 120 pairs
with coverage assertions passing; the highest-load
session (load1 17.25, head-to-head session 3) produced
arm medians (0.883M / 0.983M) in line with its siblings.
Zero discards.

## 2. Forensic findings (before any timing)

1. The C comparator never changed. EXP-032 and EXP-039
   session manifests record the identical production C
   source sha256 (c0feb989...) and binary sha256
   (8794238c...). Both files on disk today still hash to
   those values, as do the two AVX2 libraries (each
   byte-identical to the file its campaign measured).
   Baseline drift (candidate c) is refuted.
2. The kernel sources differ only in comments. A
   comment-stripped diff of exp032/src/avx2_mb.c against
   mining/cpu/bal_avx2_mb.c shows exactly one differing
   line: the opening comment line.
3. The compiled kernel code is instruction-identical.
   Full disassembly comparison (RAW_RESULTS/
   disasm_comparison.md, with both objdump outputs
   preserved): bal_a_batch2 (41 instructions) and
   a_worker (44) are identical after address
   normalisation; a_compress8 (163), a_run (718) and
   the hot function a_walk.constprop.0 (2,380) have
   identical instruction sequences, counts, registers
   and immediates, differing only in RIP-relative
   constant-pool displacements. The build difference is
   real but shallow: the research build compiles one
   translation unit (gcc -O3 -mavx2 -shared -fPIC); the
   production build compiles the kernel TU separately
   with the same -O3 -mavx2 flags and links in the
   flag-free probe TU, so the libraries differ in file
   layout and in the extra probe symbols, not in kernel
   code. Placement even favours the production build
   naively: its hot function sits at a 64-byte boundary
   (0x2640) against the research build's 32 mod 64
   (0x1560).
4. The historical session data already showed the
   mechanism's signature. Per-session absolute medians:
   EXP-032 AVX2 0.99M / 1.44M / 2.07M against C 0.84M /
   0.87M / 0.91M; EXP-039 AVX2 1.03M / 1.12M / 2.57M
   against C 0.87M / 1.02M / 1.07M. In both campaigns
   the C arm moves by about 1.25x across sessions while
   the AVX2 arm moves by 2.1x to 2.5x, including single
   sessions with raw ratios of 2.41 and 2.45 that the
   covariate adjustment pulls back. The pooled figures
   1.409x and 1.252x are two draws from that spread.

## 3. Correctness gates (all pass before any timing)

exp045_gates.py, record RAW_RESULTS/
gates_20261116T064831Z.json. Every arm path passed a
hashlib differential through its own harness: direct C
131,072 digests; direct AVX2 (each library) 196,608
(genesis plus a random header); seam C 131,072; seam
AVX2 (each library) 131,072, the seam differentials
running at the all-ones target through batch_search so
every digest was materialised, engine-verified and
compared byte for byte. Total 917,504 digests, zero
mismatches.

## 4. Results

Adjusted pooled ratios (EXP-017 statistic; per-session
values in RAW_RESULTS/analysis_20261116T070343Z.json):

| Cell | Sessions (adjusted) | Pooled |
|---|---|---|
| direct, production lib vs C | 1.313, 1.176, 1.348 | 1.274x [1.222, 1.328] |
| direct, research lib vs C | 1.341, 1.220, 1.299 | 1.286x [1.233, 1.345] |
| seam, production lib vs C | 1.329, 1.161, 1.378 | 1.287x [1.236, 1.340] |
| seam, research lib vs C | 1.240, 1.446, 1.273 | 1.315x [1.261, 1.374] |
| direct head-to-head, prod vs research | 0.934, 0.869, 1.147 | 0.976x [0.930, 1.025] NS |

Every AVX2-vs-C cell is significant in every session
and pooled: the VERIFIED IMPROVEMENT verdict is
reproduced four more times, once per cell.

Reading the table by factor:

- Library: the two direct cells differ by 0.9%, the
  two seam cells by 2.2%, and the head-to-head (the
  cleanest isolation, 360 pairs of nothing but the two
  libraries) gives 0.976x with CI [0.930, 1.025]: the
  production build is at most about 7% slower or 2.5%
  faster than the research build, point estimate 2.4%
  slower, sessions disagreeing in sign. Provenance
  cannot account for a 12.5% gap.
- Harness: for the production library, direct 1.274x
  vs seam 1.287x; for the research library, direct
  1.286x vs seam 1.315x. The seam costs both arms
  absolute rate (seam C medians 0.58M to 0.71M against
  direct 0.69M to 0.78M; seam AVX2 0.64M to 0.77M
  against direct 0.74M to 0.90M, the engine's per-call
  buffer allocation, flag scan and stats work), but it
  costs them roughly proportionally, so the ratio is
  preserved. The seam is exonerated, and as a by-product
  the production path's batch ratio is now measured
  directly: about 1.29x to 1.32x under these conditions.
- Conditions: EXP-045's cells were measured under load1
  at session starts from 3.4 to 18.7 (5-minute averages
  9 to 13, against EXP-032's recorded 6 to 9.7 and
  EXP-039's runnable queue about 12), and all four
  cells cluster at 1.27x to 1.32x, below EXP-032's
  1.409x and at or above EXP-039's 1.252x. Even
  today's replication of the EXP-039 cell (direct,
  production library) does not reproduce EXP-032's
  interval: its CI [1.222, 1.328] misses EXP-032's
  lower bound of 1.340 by 0.012. Three campaigns, three
  pooled values, with every within-campaign factor
  measured at 3% or less: the between-campaign spread
  is the conditions.

Mechanism, stated at the strength the evidence
supports: on a guest with about 2 effective CPUs, the
2-thread AVX2 multi-buffer kernel needs both of its
threads scheduled together and competes for vector
execution resources with the live miner's AVX-512 work;
its throughput therefore swings with the co-runner mix
far more than the C kernel's does (the C kernel is
OpenSSL SHA-NI code with a shallower scheduling
footprint). The EXP-017 covariates (steal and runnable
queue sampled around each call) capture part of this,
which is why the adjusted pooled figures are as close
as they are, but the residual condition-dependence is
about 10%: larger than any code or harness factor in
the system. This is consistent with EXP-041's control
finding that cross-session layout comparisons on this
VM disagreed with themselves by far more than the
effect under test. Hardware performance counters,
which could refine the mechanism further, are not
accessible on this VM (EXP-031: perf_event_open returns
EPERM), so the mechanism is established by factor
elimination plus the variance structure, not by counter
evidence, and is labelled accordingly.

## 5. What is now the defensible statement of the rate

- The AVX2 multi-buffer batch beats production C on
  this host: VERIFIED IMPROVEMENT, reproduced in three
  campaigns and in all four EXP-045 cells.
- The ratio is condition-dependent. The defensible
  range across all campaigns to date is about 1.25x to
  1.41x; the best current single estimate, from the
  campaign that crossed every factor, is 1.27x to 1.32x
  under load with the live miner running. Quoting
  either historical point estimate without its session
  conditions repeats the error this experiment closes.
- The production dispatch consequence of EXP-039 is
  unchanged: on an AVX2-only host the tier is worth
  having at any figure in that range. Behaviour on a
  genuinely AVX2-only host remains UNVERIFIED (no such
  host is available; this host's AVX2 units are Zen 4
  units that also execute AVX-512), exactly as EXP-032
  and EXP-039 recorded.

## 6. Limitations

- EXP-045 is one campaign on one day on one host. Its
  factor isolations are strong (same-day crossing), but
  its absolute pooled values are themselves draws from
  the same condition distribution; the 1.27x to 1.32x
  band is a statement about this campaign's conditions,
  not a new constant.
- Load average at session start is a weak proxy for the
  contention mix inside a session (correlation of raw
  ratio with load1 across all 18 sessions is -0.36,
  and -0.10 within EXP-045); the report rests the
  conditions conclusion on the factor crossing and the
  arm-variance structure, not on that correlation.
- The seam research-library cell uses the documented
  library-object substitution of section 1; the timed
  path is production code throughout, but the cell is a
  measurement construction, not a supported production
  configuration.
- Nothing here re-opens EXP-039's UNVERIFIED item
  (tier refusal on the SHA-less Intel host and on an
  AVX2-only host); that still awaits the Intel host
  rotation (portfolio NOVA-ER-0001).

## 7. Artifacts

- EXP045_REPORT.md (this file).
- exp045_gates.py; RAW_RESULTS/gates_20261116T064831Z.json
  (917,504 digests, all pass).
- exp045_paired_bench.py; 15 session files under
  RAW_RESULTS/sessions/ (each with host, library and
  source sha256 manifest, build commands, load at start
  and end, miner heartbeat snapshots, coverage
  assertion).
- exp045_analyze.py; RAW_RESULTS/
  analysis_20261116T070343Z.json.
- RAW_RESULTS/disasm_comparison.md;
  RAW_RESULTS/disasm_research_lib.txt;
  RAW_RESULTS/disasm_production_lib.txt.
- Discards: none (section 1).
- No production file was modified; the live miner,
  autopilot and node were never touched (miner pid
  2691, restarts 0, before and after).
