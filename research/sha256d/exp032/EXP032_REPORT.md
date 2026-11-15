# EXP-032: CPU Execution Engine, Production Search-Path Investigation

Experiment: EXP-032 (EXP-030 programme, Phase D).
Date: 2026-11-15. Host: AMD EPYC 9D25 126-Core Processor
(guest, hostname htch-runtime; full AVX-512 set, AVX2,
SHA-NI, BMI2, ADX, GFNI, VAES all present in the guest
flags). Standing condition of every measurement: the live
miner (v512dual backend, autopilot-supervised), the
pruned mainnet node in initial block download, and a
second agent's correctness work were running throughout
and were never paused or restarted. Load averages of 7 to
9.7 on 4 claimed vCPUs (about 2 effective CPUs per
EXP-031) were observed during the runs. Absolute rates
below are therefore contended-VM rates measured alongside
production, not idle-machine figures; the verdicts rest on
the paired ratios, which is what the EXP-017 design and
its covariate adjustment exist for.

Scope per the directive (section 5 of the record): AVX2
and AVX-512 multi-buffer, SHA-NI, runtime detection and
dispatch, candidate masks and early-exit search, whether
the EXP-022 flags approach can improve the real
production search path and not merely the batch API, and
benchmarks of complete production search (candidate
extraction and verification included), never an isolated
kernel equated with a faster miner. Research only:
nothing in this experiment changes any production file,
and nothing here is integrated.

Targets stand at full height: 500 GH/s minimum system
objective, 140 TH/s larger objective. Nothing measured
here is called success against those targets; every
result is intermediate, and the gap statement is in
section 9.

## Verdict summary (three-tier labels)

Batch scope (counted batch entry points, EXP-017
protocol, 3 sessions each, 2 threads):

| Comparison | Pooled adjusted ratio | 95% CI | Label |
|---|---|---|---|
| AVX2 MB batch vs production C batch | 1.409x | [1.340, 1.480] | VERIFIED IMPROVEMENT |
| SHA-NI H-01 4-stream batch vs production C batch | 2.861x | [2.671, 3.089] | VERIFIED IMPROVEMENT |
| SHA-NI H-01 4-stream batch vs v512dual batch | 0.726x | [0.672, 0.783] | significantly slower (every session) |
| AVX2 MB batch vs v512dual batch | 0.371x | [0.340, 0.403] | significantly slower (every session) |
| production SHA-NI intrin batch vs production C batch | 0.517x | [0.497, 0.536] | ESTABLISHED NEGATIVE |

Search scope (complete production search calls, the
headline scope; see section 3 for what each arm calls):

| Comparison | Pooled adjusted ratio | 95% CI | Label |
|---|---|---|---|
| production v512dual search vs production C search | 6.781x | [6.154, 7.467] | VERIFIED (baseline confirmation) |
| production v512dual search vs flags batch_search used as search | 2.565x | [2.320, 2.836] | VERIFIED: native search wins |
| flags-form search entry vs production v512 search | 0.967x | [0.885, 1.059] | NOT SIGNIFICANT: no improvement |
| flags-form search entry vs production v512dual search | 0.493x | [0.448, 0.543] | significantly slower (every session) |
| AVX2 search vs production v512dual search | 0.134x | [0.122, 0.147] | significantly slower (every session) |
| SHA-NI H-01 4-stream search vs production v512dual search | 0.349x | [0.315, 0.385] | significantly slower (every session) |

Headline answers, one line each:

1. AVX2 multi-buffer works, is exact, and beats the
   production C fallback by a verified 1.409x in batch
   scope on this host. On an AVX-512 host it is not
   competitive with the AVX-512 backends (0.371x of
   v512dual batch, 0.134x of v512dual search). Its value
   is portability, as a fallback for AVX2-only hosts.
2. SHA-NI, in the H-01 multi-stream form with the
   MSG1/MSG2 schedule, beats the production C batch by a
   verified 2.861x and reaches 0.726x of the v512dual
   batch on an AVX-512 host, using only SHA-NI and SSSE3.
   It is the strongest verified fallback for hosts that
   carry SHA-NI but not AVX-512. The production
   single-stream intrinsics kernel (bal_sha_intrin.c,
   scalar schedule) is an established negative at 0.517x
   of the C batch, which uses OpenSSL's MSG-schedule
   SHA-NI code: the schedule machinery, not the round
   instructions, is what makes SHA-NI fast.
3. The EXP-022 flags approach does NOT improve the real
   production search path. Measured three ways in
   section 6: searching through the flags batch is 2.565x
   slower than the native search entry; a dedicated
   flags-form search entry is statistically
   indistinguishable from the production single-batch
   search it would replace (pooled 0.967x, CI straddling
   1, sessions disagreeing in sign, any gain bounded at
   about 1.06x); and it reaches only 0.493x of the
   production DualMask search. The batch-scope flags win
   (1.441x production figure) does not transfer to
   search scope. No integration is recommended.

## 1. What was built

All code is research code under research/sha256d/exp032/.
Builds use restricted flag sets, never -march=native
(build.sh): the AVX2 library is built with -mavx2 only,
the SHA-NI library with -msha -mssse3, the flags-search
library with the production restricted set -mavx512f
-mavx512bw.

- src/avx2_mb.c: new AVX2 8-lane multi-buffer SHA-256d
  kernel, a lane-width port of the production
  bal_avx512_mb.c with its structure, template handling
  and Task 003.9 accounting preserved (attempted counts
  real nonces; backend counts lane computations including
  dummy lanes of partial groups, ceil(span/8)*8 per
  span). Exports bal_a_batch2 and bal_a_search2 with the
  counted ABI shape of the production kernels. AVX2
  rotations expand to shift pairs plus OR (3 ops where
  VPROLD spends 1), which is the structural reason it
  trails the AVX-512 kernels per core here.
- src/h01_multistream.c and src/shani_core.h: the Stage 5
  H-01 multi-stream SHA-NI kernel (EXP-003) and its H-02
  core, copied byte-identically from
  research/sha256d/experiments/h02_shani/ (sha256 of the
  copy and the original both
  d2794662de9fefc063dc7a525895f3e99fc06762e6b46b0713b35cef43327322;
  the relative include of mining/cpu/bal_search.h
  resolves unchanged at this depth). NS independent nonce
  streams (1, 2 or 4) advance in lockstep inside one
  worker so the SHA256RNDS2 latency chains overlap; the
  message schedule runs entirely on SHA256MSG1/MSG2.
  Exports bal_m_batch2 and bal_m_search2 with a streams
  parameter.
- src/avx512_flags_search.c: a byte copy of the
  production mining/cpu/bal_avx512_flags.c (production
  source sha256
  8bc647bcdbff11fed9b94c797b28a7e117e8093da50d251f81bbe10203a37366)
  plus one added entry, bal_v_searchf2: an early-exit
  search that walks the same 16-lane groups as the flags
  batch, takes the vf_group meets mask per group with
  extraction enabled, publishes the lowest flagged lane
  through the shared BalSearchCtx, and stops. The
  production file is untouched.
- exp032_gates.py: correctness gates (section 2).
- exp032_paired_bench.py: the EXP-017 protocol driver
  (section 3). exp032_analyze.py: the verdict statistic,
  computed by importing the EXP-017 analyzer's own code
  (phase6/benchmarks/exp017_analyze.py) so the statistic
  is literally the predeclared one, pointed at the
  EXP-032 session files.
- exp032_probe.py: supplementary median-rate probe
  (section 8), outside the protocol, no verdict rests on
  it.

## 2. Correctness gates (all pass before any benchmark)

exp032_gates.py, record RAW_RESULTS/gates_20261115T094026Z.json
(the earlier gates_20261115T093955Z.json run failed only
the planted-target cases because the gate itself planted
a 2^-16-density target where it intended an easy one;
the kernels were exonerated by the same run's batch and
cross-check gates, the gate was fixed to a 2^-8 density,
and the rerun passes everything; both records are
preserved).

Batch digests verified byte-identical against hashlib
(genesis header, random headers, odd counts, thread
counts 1, 2 and 4, flag agreement against the hashlib
meets decision at three densities, and a range ending
exactly at 2^32):

- AVX2 batch: 274,925 digests.
- SHA-NI H-01 batch, streams 1 / 2 / 4: 322,890 /
  225,235 / 232,580 digests.
- Production SHA-NI intrin batch: 302,580 digests.
- Total: 1,358,210 digest verifications, zero mismatches.

Search gates (genesis nonce found with the exact genesis
digest; planted-target hits returned with digests
verified against hashlib; no-hit ranges return 0 with
attempted exactly equal to the range size): pass for the
AVX2 search, H-01 search at streams 1 and 4, the
production intrin search, and the flags-form search.
Cross-check: on 8 random ranges the flags-form search
agrees with the production flags batch (no flag bit set
implies search returns 0; a returned nonce always has
its flag bit set and a hashlib-exact digest).

## 3. Method

Protocol: the adopted EXP-017 rule, unchanged. Paired
65,536-hash blocks, randomised AB or BA order per pair,
steal and runnable-load covariates sampled around every
counted call, 100 to 120 pairs per session, 3 sessions
per comparison, verdicts from the adjusted statistic
(paired log-ratio, OLS on the steal-difference,
runnable-load-difference and order covariates, pairs
bootstrap CI) computed by the EXP-017 analyzer code. A
VERIFIED IMPROVEMENT requires the adjusted CI entirely
above 0 in every session and pooled. 33 sessions, 3,920
pairs, about 514 million timed hashes in total. Every
timed call asserts attempted == 65,536. Sessions are
append-only under RAW_RESULTS/sessions/; the analysis is
RAW_RESULTS/analysis_20261115T100744Z.json.

Batch scope arms call the counted batch entries
(bal_c_batch2, bal_vd_batch2, bal_a_batch2,
bal_m_batch2, bal_i_batch2) over the genesis header at
the difficulty-1 target, exactly as the EXP-017 driver
measures them, 2 threads.

Search scope arms measure complete production search
over a no-hit range (target 1, so every arm scans the
full 65,536 nonces and finds nothing; mining's common
case, and the only case where rates are comparable
without hit-position luck):

- prod_dual_search, prod_v512_search, prod_c_search:
  ComputeEngine.search_first_counted on real
  ComputeEngine instances pinned by requested backend,
  so dispatch, the native call, candidate verification
  machinery and the engine's accounting all run.
- prod_flags_batchsearch: ComputeEngine.batch_search on
  the auto engine (v512dual selected, flags batch
  selected); the driver asserts stats batch_path is
  "flags", unique_coverage == count and zero candidates
  on every call. This is the flags path used as a search
  strategy, end to end through the production engine.
- avx2_search, shani_m4_search, fsearch: the research
  kernels' native search entries called through the same
  ctypes pattern the engine's native branches use. These
  are research wrappers, not production dispatch, and
  are labelled as such wherever quoted.

## 4. The production search path, as it actually is

From gpu/engine.py (read in full for this experiment):

- search_first_counted dispatches by backend:
  v512dual to bal_vd_search2, v512 to bal_v_search2, C
  to bal_c_search2, each a native early-exit entry with
  counted accounting and a Python verify_candidate
  recheck of any hit (with a trusted rescan if a
  candidate ever failed verification). Anything else
  falls back to batch_search (full enumeration).
- batch_search routes an AVX-512 backend's enumeration
  through the flags entry bal_v_batchf2 when the flags
  library is selected (batch_path "flags" in stats),
  falling through to the selected backend's preserved
  digest-materialising batch on any flags failure. The
  C backend's batch does not use flags.
- The live miner's search path is the native one:
  mainnet_live drives search_first_counted on the
  v512dual backend. batch_search serves the engine's
  batch consumers (Task 003.9 accounting callers,
  diagnostics, want_all wrappers), not the live search.

So "the real search path" for the flags question is the
native early-exit search entries, and the flags approach
could only improve it in one of two ways: by replacing
the enumeration inside a search (tested by the
batch_search-as-search arm), or by giving a search entry
the flags form (tested by bal_v_searchf2 against both
production search entries it could conceivably displace).

## 5. Results in detail

Session medians are H/s at 2 threads on the contended
guest; ratios are the pooled adjusted figures of the
verdict table (per-session values in the analysis JSON).

### 5.1 AVX2 multi-buffer

Batch medians: AVX2 0.85M to 2.07M against C 0.84M to
0.91M in the paired sessions; pooled 1.409x
[1.340, 1.480], significant in every session.
VERIFIED IMPROVEMENT over the production C batch.

Against v512dual batch (medians 3.87M to 5.99M): pooled
0.371x [0.340, 0.403], significantly slower in every
session. In search scope against the production dual
search (medians 9.11M to 11.79M; AVX2 search medians
0.79M to 0.84M): pooled 0.134x [0.122, 0.147]. The
8-lane width and the 3-op rotations cost exactly what
the instruction census predicts against a 16-lane
VPROLD kernel on the same silicon.

Dispatch consequence: the EXP-028 specified order gains
a measured AVX2 slot. On a host with AVX2 but neither
AVX-512 nor SHA-NI, this kernel is the best verified
fallback over C (1.409x batch). Rates on a non-AVX-512
host are UNVERIFIED: this host's AVX2 units are Zen 4
units that also execute AVX-512, and per-core AVX2
throughput on a genuinely AVX2-only part may differ.
Correctness is host-independent (differentials are
exact); the ratio is this host's.

### 5.2 SHA-NI

Three SHA-NI forms were measured, and they are not
interchangeable:

- H-01 multi-stream (MSG schedule, streams interleaved):
  batch medians 2.31M to 3.92M at streams 4, pooled
  2.861x [2.671, 3.089] over the C batch, significant in
  every session. VERIFIED IMPROVEMENT. Against v512dual
  batch: pooled 0.726x [0.672, 0.783]. In search scope
  against the dual search (m4 search medians 2.77M to
  3.89M): pooled 0.349x [0.315, 0.385]. The batch-to-
  search drop against dual is expected: the dual search
  compares in opmask and extracts only on a hit group,
  while H-01's search materialises each wave's digests
  and compares scalar, and the engine-side dual arm also
  benefits from its dual-batch wave structure.
- H-02 single-stream core (the base of H-01, Stage 5):
  not re-benchmarked as a separate arm here; its
  historical 1-thread median of 3.30M H/s was measured
  on a quieter host state and is not reproduced as a
  claim. The streams probe (section 8) shows the
  stream-count ordering on today's contended guest.
- Production bal_sha_intrin.c (single stream, scalar
  schedule, snapshot after round 1): batch medians
  0.36M to 0.46M against C 0.69M to 0.73M, pooled 0.517x
  [0.497, 0.536], significantly slower in every session.
  ESTABLISHED NEGATIVE as a batch backend. The C batch
  it loses to runs OpenSSL's SHA256_Transform, which on
  this CPU is SHA-NI code with the MSG schedule: the
  difference between the two SHA-NI kernels is the
  schedule machinery and the snapshot depth, not the
  round instructions. This confirms the gap analysis
  finding from the other side: the intrin kernel is
  built but never dispatched, and dispatching it as it
  stands would halve the fallback rate.

Dispatch consequence: for a host with SHA-NI but no
AVX-512, H-01 at streams 4 is the strongest verified
fallback (2.861x over the C batch in batch scope). That
host class is real (SHA-NI shipped on many parts that
never received AVX-512) but no such host is available
here, so the on-host ratio is this host's and the
cross-host claim is UNVERIFIED beyond correctness.

### 5.3 Complete production search baseline

Production dual search against production C search,
both end to end through ComputeEngine.search_first_counted:
medians 8.24M to 14.78M against 0.82M to 1.03M, pooled
6.781x [6.154, 7.467], significant in every session.
This is the current production search path's verified
standing on this VM under today's contention, and the
reference every candidate in this experiment had to
beat. None did.

## 6. The flags question, answered three ways

Question (directive section 5): can the EXP-022 flags
approach improve the real production search path, not
merely the batch API?

(a) Flags enumeration as the search: production
batch_search on the flags path against production dual
search, same no-hit ranges, same engine. Flags
batch_search medians 2.28M to 5.04M; dual search medians
5.81M to 13.72M in those sessions; pooled ratio for
dual over flags 2.565x [2.320, 2.836], significant in
every session. Searching through the flags batch is
significantly SLOWER than the native search entry: it
enumerates the whole range into flag bits and candidate
pairs and pays the Python-side pair checking, where the
native entry compares in-kernel and stops at group
granularity. VERIFIED for the native search.

(b) A flags-form search entry against the single-batch
production search: bal_v_searchf2 (section 1) against
ComputeEngine's v512 search (bal_v_search2). Medians:
fsearch 4.77M to 6.67M, v512 search 4.48M to 7.76M.
Pooled 0.967x [0.885, 1.059]; the three sessions
disagree in sign (one marginally positive, one
significantly negative, one straddling). NOT
SIGNIFICANT: no improvement is established, and the
pooled interval bounds any gain at about 1.06x while
the point estimate sits below 1. The batch-scope flags
advantage does not transfer to search scope. The
mechanism is consistent with where the batch win comes
from: in batch scope the flags form avoids writing
32 digest bytes per hash into a caller's buffer and
extracting every lane; in search scope the materialised
digests live in a 512-byte stack array that stays in L1
and is compared immediately, so there is no large
traffic to save, and the 8-word opmask compare with its
mask bookkeeping costs about what the saved extraction
returns.

(c) The same entry against the production default:
bal_v_searchf2 against dual search, pooled 0.493x
[0.448, 0.543], significantly slower in every session.
DualMask is itself the mask-compare idea carried into a
dual-batch search (EXP-024 into EXP-026), so on the
default path the flags principle is already present in
a stronger form.

Conclusion: no flags integration into the search path
is recommended. The flags batch keeps its verified
batch-scope role for the batch consumers, unchanged.
EXP-024's search-path investigation is continued and
closed for the single-batch form by (b): the remaining
mask-search headroom on this host is inside the
DualMask structure, not in a flags variant of the
single-batch kernel.

## 7. Runtime detection and dispatch findings

- Production dispatch probes exactly AVX-512F and
  AVX-512BW (gap analysis component 1). EXP-032 adds two
  measured slots to the EXP-028 specified order:
  shani-streams (H-01, streams 4) for SHA-NI hosts
  without AVX-512, and avx2-mb for AVX2 hosts without
  either. Both kernels are built with restricted flag
  sets and are safe to probe-first dispatch in the
  established style (flag-free CPUID probe, completeness
  check before any call, hashlib self-test), but neither
  is integrated by this experiment; integration is a
  separate step with its own gates and independent
  audit, and is recommended only if a target host class
  without AVX-512 becomes a real deployment prospect.
- The SHA-NI probe matters in both directions: this AMD
  guest has SHA-NI, the earlier Intel guest did not.
  Any future dispatch that assumes SHA-NI from the
  vendor string alone would fault on such a host; the
  probe-first rule already in production covers it.
- Register pressure notes: the AVX2 kernel keeps 8
  state vectors, 16 schedule vectors and the round
  temporaries in 16 ymm registers; the compiler spills
  schedule vectors to the stack ring by design (the
  W[16] ring is stack-resident, as in the AVX-512
  original). H-01 at streams 4 keeps 4 stream states
  (8 xmm) plus 4 message vectors (4 xmm) live; streams
  beyond 4 were not available in the H-01 design and
  were not attempted.

## 8. Supplementary probe (not protocol, no verdicts)

exp032_probe.py, RAW_RESULTS/probe_20261115T094912Z.json:
medians of 9 counted batch calls per configuration.
Contention during the probe was extreme (repeat spreads
of 5x to 10x inside single configurations), so these
medians are context only: C batch 0.67M (1 thread) and
0.69M (2); intrin 0.26M and 0.35M; v512dual batch 9.08M
(1 thread) and 4.81M (2, a contention artefact, the
paired sessions are the reliable dual figures); AVX2
0.89M, 0.90M and 0.96M at 1, 2 and 4 threads; H-01 at
1 thread 0.71M (streams 1), 0.70M (2), 0.80M (4); at
2 threads 1.03M (1), 3.16M (2), 0.87M (4). The H-01
2-thread stream ordering is not stable under this
contention and is not claimed; the protocol comparisons
used streams 4 throughout, per the H-01 design point.

## 9. Gap to the targets

The best complete-search rate observed in this
experiment is the production dual search at session
medians of 8.2M to 14.8M H/s (2 threads, contended,
alongside the live miner itself). At 14.8M H/s, 500 GH/s
is about 33,800 such VMs and 140 TH/s about 9.5 million;
at the programme's earlier live observation of 20.6M H/s
the figures are about 24,000 and about 6.8 million
(Phase 6B basis, unchanged). EXP-032 narrows no part of
that gap on AVX-512 hosts: its verified gains are
fallback gains for other host classes (AVX2 1.409x,
SHA-NI streams 2.861x, both over the C fallback), and
its search-path investigation closes a question rather
than opening a rate. The binding constraints remain the
ones EXP-020 and EXP-027 established: the full round at
its vocabulary optimum and the closed representation
spaces, plus this VM's roughly 2 effective CPUs.

## 10. Integration decisions

- AVX2 MB kernel: NOT INTEGRATED. Candidate for a
  future dispatch slot (avx2-mb) if a non-AVX-512,
  non-SHA-NI host becomes a deployment prospect.
- SHA-NI H-01 streams kernel: NOT INTEGRATED. Candidate
  for a future dispatch slot (shani-streams) for
  SHA-NI-without-AVX-512 hosts; the strongest verified
  fallback measured in this programme for that class.
- Flags-form search entry bal_v_searchf2: REJECTED for
  integration (section 6). The research source stays in
  this tree as the record of the test.
- Production bal_sha_intrin.c: no change recommended to
  production (it is not dispatched); the established
  negative is recorded so a future dispatch proposal for
  it starts from the measurement, not the assumption.
- No production file was modified by EXP-032. The live
  miner, autopilot and node were never restarted.

## 11. Artifacts

- EXP032_REPORT.md (this file).
- src/avx2_mb.c, src/h01_multistream.c, src/shani_core.h,
  src/avx512_flags_search.c; build.sh; libbal_avx2.so,
  libbal_h01.so, libbal_v512fsearch.so.
- exp032_gates.py with RAW_RESULTS/gates_20261115T093955Z.json
  (first run, gate-density defect, preserved) and
  RAW_RESULTS/gates_20261115T094026Z.json (all pass).
- exp032_paired_bench.py; 33 session files under
  RAW_RESULTS/sessions/; exp032_analyze.py;
  RAW_RESULTS/analysis_20261115T100744Z.json.
- exp032_probe.py; RAW_RESULTS/probe_20261115T094912Z.json.
- Every session file carries the host (AMD EPYC 9D25),
  source and binary sha256 manifests, build commands,
  environment covariates and the coverage assertion.
