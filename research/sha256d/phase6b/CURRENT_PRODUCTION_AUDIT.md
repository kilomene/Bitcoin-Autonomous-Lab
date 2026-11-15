# Phase 6B, Assignment A: Current Production Audit

Date of record: 2026-11-14. Audit executed:
2026-11-15, about 04:30 to 04:40 UTC, against the live
local tree at /home/hatch/workspace/bitcoin-autonomous-lab
and the public remote
https://github.com/kilomene/Bitcoin-Autonomous-Lab.
Auditor: Phase 6B Assignment A (repository audit). The
auditor edited no production code, stopped nothing, and
restarted nothing. The live mainnet autopilot, miner
and node were inspected read-only through their state
files and log tails.

Method: direct source reads of every file named in the
directive section 3, blob-SHA comparison of the full
local tree against the remote recursive tree (read-only
use of the push helper's machinery, no push performed),
function-level diffs for kernel identity claims, the
experiment registry read in full (EXP-000 to EXP-023),
the Phase 6 records, and one cheap test target
(section 9). Anything not executed by this audit is
labelled as recorded, not re-verified.

Overall verdict: the production state matches its
records. Backend, dispatch, build and accounting all
reproduce from source. No new production correctness
defect was found. Four new findings, all documentation
or tooling grade, are numbered B6-A1 to B6-A4 in
section 8. Nothing found blocks EXP-024.

## 0. Audit host record

Recorded at audit time from /proc/cpuinfo and uname:

- Host CPU: AMD EPYC 9D25 126-Core Processor (guest:
  4 vCPUs, family 26, model 17), 1497.749 MHz as
  reported, KVM guest on kernel 7.0.0-44-generic,
  hostname htch-runtime.
- Flags present, the ones this programme depends on:
  sha_ni YES, avx512f YES, avx512bw YES, avx512dq YES,
  avx512vl YES, avx512vbmi YES, avx512_vbmi2 YES,
  avx512ifma YES, avx512_vnni YES, gfni YES, vaes YES,
  avx2 YES, bmi1/bmi2 YES, adx YES.
- Toolchain: gcc 13.3.0, Python 3.12.3, OpenSSL 3.0.13.
  iverilog ABSENT (which returns nothing), which is
  the standing cause of the test-rtl failure.
- Host variability warning, standing: VM replacements
  have previously landed this guest on an Intel Xeon
  Platinum 8321HC host with AVX-512F/BW/VL/VNNI but NO
  SHA extensions and NO VBMI. Every future session
  manifest must record its own host; no session may
  assume this section's flags.

## 1. Item 1: current production commit (tree equivalence)

The local checkout has no .git directory (verified:
ls .git returns "No such file or directory"), so the
commit of record is the remote head, bound to the
local tree by blob comparison:

- Remote: kilomene/Bitcoin-Autonomous-Lab, public
  (private: False), default branch main.
- Remote head commit at audit time:
  2bc63b49a16b15d899d4eab85379f9b957015dcf
  (head commit message: "Bitcoin Autonomous Lab:
  update research/sha256d/research_findings.md", the
  helper's per-file contents-API style; the API did
  not return a committer date for this read).
- Comparison (read-only; the helper's local_files and
  remote_tree functions with git blob SHAs): 408 local
  entries, 408 remote entries. Exactly one path
  differs: evidence/mainnet-live.jsonl, the live
  evidence log the running miner appends to
  continuously. Zero remote-only paths.
- Verdict: local tree equals remote tree except the
  live evidence log. That divergence is expected
  runtime behaviour, not a discrepancy. The Phase 6B
  files created by this assignment are local-only
  until the parent pushes them; they are listed in
  section 10.
- Tooling caveat: see finding B6-A1. The helper's own
  VERIFY step would not, by itself, prove the
  research/ part of this equivalence.

## 2. Item 2: current production backend

- Backend name: "v512", the AVX-512 16-way
  multi-buffer kernel, source
  mining/cpu/bal_avx512_mb.c (397 lines), built into
  .local/cpu/libbal_v512.so (present at audit time,
  alongside libbal_batch.so and libbal_intrin.so).
- Live confirmation at audit time:
  .local/mainnet-status.txt reads "compute backend:
  v512 (native impl: avx512-mb; AVX-512 MB: selected:
  CPUID probe confirms AVX-512F and AVX-512BW and the
  batch reproduces hashlib digests)".
- Fallback chain: CUDA (never selected here, no GPU),
  then v512, then the OpenSSL C backend
  (mining/cpu/bal_batch.c into libbal_batch.so), then
  the Python hashlib enumeration. Requesting "c"
  explicitly selects the C backend alone (verified in
  source, gpu/engine.py ComputeEngine.__init__ and
  _try_v512 gating, and by the post-integration
  audit's live check).
- Kernel identity: diff of mining/cpu/bal_avx512_mb.c
  against research/sha256d/extreme_optimization/src/
  avx512_mb.c shows exactly two differences: the
  production header comment block (production file
  lines 4 to 15) and the bal_search.h include path
  ("bal_search.h" vs the research relative path).
  The claim in both file headers is accurate.

## 3. Item 3: actual runtime dispatch path

End to end, from source:

1. mining/mainnet_live.py main() constructs
   gpu.engine.ComputeEngine with defaults
   (requested="auto").
2. ComputeEngine.__init__ (gpu/engine.py, class at
   line 720) tries, in order: _try_cuda (only for
   requested auto/cuda/cuda-only), then _try_v512
   (only for auto/v512), then _try_c (for auto/c/v512
   when neither CUDA nor v512 selected).
   requested="cuda-only" with no CUDA raises.
3. _try_v512 (line 838) performs, in order: file
   existence check on .local/cpu/libbal_v512.so;
   ctypes load (loading executes no kernel code; the
   library has no constructor, per the post-integration
   audit's object inspection); hasattr check for
   bal_v512_supported; the probe call; on a negative
   probe, rejection with the feature-bits reason; on a
   positive probe, a completeness check that both
   bal_v_batch2 and bal_v_search2 exist (the D-1 fix,
   present in the current source as the "missing" list
   check before any argtypes assignment); argtypes
   assignment; then a 256-nonce self-test batch over
   header bytes(range(80)) whose every digest must
   equal cpu_digest (hashlib double SHA-256,
   gpu/engine.py line 202). Any failure leaves the
   backend unselected with v512_reason recorded and
   falls through to C.
4. The probe itself (mining/cpu/bal_avx512_probe.c,
   41 lines) is compiled with no vector flags and
   answers __builtin_cpu_supports("avx512f") and
   ("avx512bw"), which also implies the OS zmm state
   check. Required feature set: AVX-512F plus
   AVX-512BW, exactly. No DQ, VL, VBMI, VBMI2 or IFMA
   is required or used (objdump census in the
   post-integration audit, Area 2).
5. After selection, __init__ calls tune_v512_threads
   (or tune_c_threads for C): a one-time measured
   thread-count probe over the real counted search,
   setting the module C_THREADS and LAST_PROBE_RATE,
   unless BAL_C_THREADS is set in the environment.
6. Build path (mining/cpu/build.py): build() compiles
   bal_batch.c with -O3 -march=native into
   libbal_batch.so and smoke-tests it (genesis digests
   plus the counted search re-finding nonce
   2083236893) before reporting ok; build_v512()
   compiles bal_avx512_mb.c as its own translation
   unit with the restricted flags V512_FLAGS =
   ["-mavx512f", "-mavx512bw"] (never -march=native),
   compiles bal_avx512_probe.c with no vector flags,
   links both into libbal_v512.so, and smoke-tests
   through _smoke_v512 (probe first; batch digests;
   genesis search; wave accounting checks). A v512
   build failure is loud and never fails the C build.
   build_intrin() is experimental only and never a
   production selection. The string march=native
   appears only in the pre-existing _compile path for
   the C and intrinsics libraries.

## 4. Item 4: actual live-miner search path (the digest trace)

This section is the EXP-024 section 4.1 trace. It is
reproduced in EXP024_MASK_SEARCH.md.

Call chain: mining/mainnet_live.py scan loop calls
engine.search_first(header, target, nonce, span) per
span (span sized to about one second of the probe
rate, 2^20 to 2^24 nonces). search_first
(gpu/engine.py line 988) is a thin wrapper over
search_first_counted (line 996), which on the v512
backend:

1. Validates header length, target range and the
   nonce interval (start, count within 2^32).
2. Calls libbal_v512.so bal_v_search2(header, start,
   count, C_THREADS, target_le, out_nonce, out_digest,
   out_attempted, out_backend) once per span.
3. Inside bal_v_search2 (mining/cpu/bal_avx512_mb.c
   line 380): argument and range validation
   (bal_validate_range in bal_search.h: count at
   least 1, start and count each at most 2^32, sum at
   most 2^32; return -1 bad args, -2 range crossing);
   BalSearchCtx initialisation (fallible; -4 on mutex
   init failure); v_run; publish-failure check (-3);
   on a hit, copies ctx.found_nonce and
   ctx.found_digest to the outputs and returns 1,
   else 0.
4. Inside v_run / v_walk / v_group: v_template_init
   computes the block-1 midstate once, scalar
   (v_compress_scalar over header bytes 0 to 63), and
   extracts block-2 words w0, w1, w2 (header bytes 64
   to 75). The range is partitioned by bal_partition
   into at most C_THREADS contiguous disjoint spans;
   each worker walks its span in 16-lane groups.
   Per group, v_group: lane nonces are start+off+lane;
   the nonce is byte-swapped by _mm512_shuffle_epi8
   (the AVX-512BW instruction) into schedule word W3;
   block-2 compression runs over the transposed state
   (v_compress16, 64 rounds, vector schedule); the
   inner digest state is materialised through an
   inn[8][16] staging array; the outer compression
   runs from the SHA-256 initial state; the final
   state is stored through a dg[8][16] staging array
   and every valid lane's 32-byte digest is written
   out byte by byte into a stack array dig[16][32].
   Dummy lanes of a partial final group are computed
   (backend count includes them) but never stored and
   never counted as coverage.
5. Comparison, search mode: back in v_walk, each
   valid lane's materialised digest is compared
   SCALAR, byte by byte from byte 31 down, by
   v_meets(dig[l], target). On a meet, the worker
   calls bal_ctx_publish: under the winner mutex, the
   first publisher's nonce and digest are copied into
   the context and the atomic stop flag is raised;
   other workers observe the flag at their next group
   boundary and stop. There is no vector comparison
   anywhere in the production search path today, and
   no early termination inside a group: a started
   16-lane group always completes all three
   compressions and the full digest materialisation
   for all 16 lanes.
6. Accounting, search mode: per span, attempted sums
   the real nonces of every completed group (wave
   semantics: a group containing the winner counts
   all its real nonces); backend sums 16 per group
   including dummy lanes. v_run sums the span slots
   after joining all workers. Back in Python,
   search_first_counted records last_search_stats
   (attempted, backend_hashes, unique_coverage equal
   to attempted, candidate_count 1 on a hit,
   verification_hashes 1 on a hit), and verifies the
   candidate: verify_candidate (line 207) recomputes
   cpu_digest (hashlib) for the winning nonce, demands
   byte equality with the kernel digest, and demands
   the value meet the target. A verification failure
   is never a silent miss: _recover_bad_candidate
   rescans the whole span with hashlib, records a
   fallback event, and reclassifies the work as
   verification hashes with unique_coverage None.
7. Batch mode (batch_search, used by verification and
   statistics consumers, not by the live scan):
   _v_batch_flagged calls bal_v_batch2, which runs
   the same v_group materialisation for the full
   range, copies every digest into the caller's
   hashes buffer and writes a per-nonce flag byte
   from the same scalar v_meets. Python then locates
   flagged pairs by scanning the flag bytes. The
   batch epilogue (staging stores, per-lane byte
   extraction of all 16 digests per group, the
   32-byte per-hash output copy, the scalar per-lane
   compare) is exactly the cost EXP-022 measured at
   roughly half the batch call at sparse densities.
8. Submission path: mainnet_live.py, on a hit,
   rebuilds the header for the winning nonce through
   stratum_client.build_header, recomputes the digest
   with hashlib independently, rechecks it against
   the pool target and the network target from the
   job nbits, checks the job generation is still
   fresh, and only then submits. A mask, flag or
   kernel claim is never treated as proof of a valid
   share or block anywhere in this chain.

Where each digest lives, summary: generated in
registers (transposed zmm state) inside v_compress16;
materialised through inn[8][16] (inner) and dg[8][16]
(outer) stack staging; stored per lane into dig[16][32]
on the worker stack (search and batch) or, in batch
mode only, copied again into the ctypes hashes buffer;
compared scalar by v_meets in v_walk (both modes);
extracted, search mode, as the single winning digest
copied through BalSearchCtx.found_digest to the
ctypes out_digest; verified twice in Python
(verify_candidate inside the engine, hashlib
recompute inside mainnet_live.py).

Error propagation: kernel return codes -1, -2, -3,
-4 surface as RuntimeError in search_first_counted
for any rc outside (0, 1); bal_ctx_publish failures
raise the publish_error flag checked after the join;
pthread_create failure for a span runs that span
synchronously in the calling thread (bal_search.h
design); allocation failure inside the kernel search
path does not exist (all buffers are stack or caller
owned); the flags research kernel adds -5 for its
scratch allocation failure (research only).

## 5. Item 5: available experimental kernels (inventory)

Research tree, research/sha256d/extreme_optimization/
src/, each with counted batch and search entry points
unless noted. All are research only; none is wired
into production except avx512_mb.c, whose production
copy is item 2.

| File | Entry points | Experiment | State |
|---|---|---|---|
| avx512_mb.c | bal_v_batch2, bal_v_search2 | EXP-007 | Research original of production v512 |
| avx512_mb_flags.c | bal_v_batchf2 (new), plus bal_v_batch2, bal_v_search2 identical to the EXP-007 paths (verified by function diff in this audit) | EXP-022 | Flags batch VERIFIED in batch scope; no search entry point exists for the flags form |
| avx512_mb_reg.c | bal_r_batch2, bal_r_search2 | EXP-018 | Register-resident dual batch; not significant |
| avx512_mb2.c | bal_w_batch2, bal_w_search2 | EXP-011 | Dual-batch interleave; unreproduced |
| avx512_mb_exp020.c | bal_p6_batch2, bal_p6_search2 | EXP-020 | Single-ternlog Maj variant P6C-007; not significant |
| avx512_mb_tern.c | bal_t_batch2, bal_t_search2 | EXP-012 | Explicit ternlog forms; parity |
| avx512_mb_share.c | bal_x_batch2, bal_x_search2 | EXP-013 | Cross-lane prefix sharing; inconclusive |
| avx512_mb_kw.c | bal_k_batch2, bal_k_search2 | EXP-014 | K+W folding; rejected |
| bitslice32.c | bal_z_batch2, bal_z_search2 | EXP-015 | Bitsliced 32-lane; rejected (about 0.03x of MB) |
| h01_geo.c | bal_m_batch2, bal_m_batch2m, bal_m_search2, bal_m_search2m | EXP-005 | SHA-NI streams geometry; streams=4 strided is the EXP-017 second contender |
| h01_hsf.c | bal_m_batch2m family | EXP-006 | Hand-scheduled variant; rejected |
| h01_phase.c | bal_p_batch2, bal_p_search2 | EXP-008 | Phase pipelining; rejected |
| freq_gate.c | (gate program) | EXP-007 X-041 | AVX-512 frequency gate |

Earlier kernels: experiments/h02_shani/ (H-02 SHA-NI
kernel and H-01 multistream, EXP-002 and EXP-003).
Production-side libraries: mining/cpu/bal_batch.c
(C, production fallback), mining/cpu/bal_sha_intrin.c
(experimental intrinsics, never production),
mining/cpu/bal_miner.c (standalone bal-miner binary),
gpu/cuda/ (CUDA engine; compiles, cannot execute
here, no GPU).

Phase 6 tooling: phase6/benchmarks/exp017_paired_
bench.py and exp017_analyze.py (the adopted statistic),
exp018 to exp023 paired benches, gates and analyses;
phase6/src/discovery_harness.py, nonce_dependency.py,
exp020_round_search.py, rank_hypotheses.py.

## 6. Item 6: current benchmark baseline (recorded, not re-run)

The audit ran no benchmarks. Recorded baseline, with
evidence files:

- EXP-000 trusted baseline (production C, pre-v512):
  medians 1T 1,314,704 H/s, 2T 1,627,792, 4T
  2,512,762 (4T spread 82.6 percent, disqualified as a
  planning figure); intrinsics about 0.52x production;
  Python hashlib 304,444 H/s. Evidence:
  research/sha256d/experiments/exp000_baseline.json;
  registry EXP-000.
- EXP-017 decision measurements (the adopted rule):
  MB vs production pooled 3.55x (adjusted CI 3.17x to
  3.97x), significant in every session, pairs won
  81.5 percent; streams=4 strided vs production pooled
  2.80x (CI 2.53x to 3.09x), pairs won 79.8 percent;
  equal-pair controls null in all sessions. Absolute
  arm medians in those sessions: MB 6.19 to 6.64 MH/s,
  production 0.81 to 0.99 MH/s, at 2 threads under IBD
  contention. Evidence: phase6/benchmarks/exp017/
  (12 session files) and analysis_20261114T145128Z.json.
- EXP-007: MB combined-session 2T median 6.53 MH/s
  (the figure the Phase 6 target model carried).
- Live system at audit time: miner session rate
  11,145,244 H/s in .local/mainnet-status.txt
  (2026-11-15T04:34Z), status events 11.08 to 11.28
  MH/s; session rates are exact-attempt based since
  the N-1 fix and reflect the auto-tuned thread count
  of the running session, not the 2-thread benchmark
  configuration. Label: measured live observation,
  not a benchmark.
- EXP-022 (batch scope only): flags vs production
  batch pooled 1.82x at candidate density about 0
  (2T), 1.59x at 2^-8, 1.33x at density 1, pure flags
  1.89x, 1T 1.83x; every session significant.
  Evidence: phase6/benchmarks/exp022/ (15 sessions,
  gates_20261114T190507Z.json,
  analysis_20261114T192558Z.json).
- EXP-023 (construction, not hash rate): steps at 500
  transactions pooled 18.49x, job families 22.06x,
  churn control 0.97x null. Evidence:
  phase6/benchmarks/exp023/ (12 sessions, gates,
  audit, four analyses).

## 7. Items 7 and 8: latest correctness and regtest evidence

Correctness, latest of record:

- Integration gates through the production path:
  196,608 differentials, 0 mismatches
  (tests/test_avx512_integration.py; recorded in the
  Phase 6 final report addendum and re-run by the
  post-integration auditor, whose own independent
  probes added 131,072 differentials, 0 mismatches,
  plus template, boundary and target-equality gates).
- EXP-022 gates: 154,316 density-1 differentials,
  candidate-set parity at four densities and three
  thread counts, accounting parity on 32 (count,
  threads) pairs (benchmarks/exp022/
  gates_20261114T190507Z.json).
- EXP-023 gates: 1,320 randomised byte-identity cases
  against build_candidate, snapshot completions equal
  to hashlib on 200 headers, merkle spine equality at
  47 leaf counts (benchmarks/exp023/
  gates_20261114T194015Z.json).
- D-1 regression gate test_incomplete_library_fallback
  and the N-1 gate tests/test_mainnet_live_
  accounting.py are part of make test-all. This audit
  re-ran the N-1 target only (section 9): PASS.

Regtest, latest of record (all through production
paths, accepted by Bitcoin Core 28.1):

- Heights 630 and 700: integration verification,
  v512 backend.
- Height 701: post-integration auditor's re-run of
  the integration suite. Height 702: the auditor's
  own fresh block, hash
  7aa935cd59b84fb816ff814c2c844f49db26d80ca97d374e9ba11b359d320886.
  Height 703: D-1 fix verification run.
- Height 763, hash
  0000001325090ccf3e4108a2d2a3ca7832f91607d1259c1e970ee0940ec4a2de:
  solo server end-to-end in its current form
  (docs/SOLO_CUTOVER.md lines 16 and 222;
  research_findings.md). Recorded; not re-derived by
  this audit.
- No fresher regtest evidence exists in the tree
  after 2026-11-14. Any Phase 6B integration will
  need its own fresh block under the integration
  rules; none is claimed here.

Live mining evidence at audit time (read-only):
heartbeat fresh (ts 2026-11-15T04:34:05Z at first
read), autopilot pid 2394, miner pid 2397, state
running, shares_accepted_total 185, endpoint mode
pool (public-pool.io:21496), balance 0 BTC (solo-style
pool; no block found, none claimed). Node debug.log
tail shows UpdateTip advancing (height 428,513 at
04:35:39Z), still in initial block download toward
about 975,900 headers; the solo cutover remains
correctly unfired (endpoint config mode "pool"; the
cutover marker file is absent, see B6-A3).

## 8. Item 9: outstanding defects and findings

Standing, known before this audit:

- K-1: test-rtl fails because iverilog is absent from
  this VM (environment). Pre-existing; never hidden.
- K-2: GPU gates UNVERIFIED (Tasks 002, 003, 003.8:
  device performance, device verification, GPU
  regtest acceptance). No GPU exists on this VM
  (zero /dev/nvidia* nodes). Closing them needs one
  run on a machine with a supported NVIDIA GPU.
- K-3: FPGA and ASIC records are simulation and
  pre-layout only; no board, bitstream, PDK or
  silicon measurement exists.
- K-4: EXP-011 session A raw JSON was overwritten
  before archiving (found by the Phase 6 first
  assignment). Its 8.27 MH/s figure survives as
  transcription only and is excluded from the gap
  model.
- K-5: two integration recommendations await owner
  decisions and are NOT integrated: EXP-022 flags
  output shape for batch consumers; EXP-023 Y-077
  data-level caching in mining/engine.py (the second
  is additionally gated by EXP-025 in this phase).
- K-6: post-integration audit notes D-1, N-1, N-2
  are all RESOLVED in source, verified in this audit:
  D-1 guards present in gpu/engine.py _try_v512
  (missing entry-point check before argtypes) and in
  build.py _smoke_v512 (hasattr checks for both entry
  points); N-1 fixed by call_attempts in
  mining/mainnet_live.py accumulating
  last_search_stats["attempted"], never the requested
  span; N-2 docstring now describes the runtime
  dispatched backend. The fixes take effect in the
  live miner on natural restarts, as recorded in the
  audit addenda; the currently running miner (pid
  2397) already shows exact-attempt session rates.

New findings of this audit (numbered B6-A):

- B6-A1 (tooling, moderate for Phase 6B pushes):
  the push helper /home/hatch/workspace/bin/
  bal_github.py defines MANAGED_PREFIXES (lines 12 to
  14) as node/, blockchain/, mining/, gpu/, agent/,
  dashboard/, tests/, docs/, scripts/, results/ and
  evidence/, plus five managed root files. The
  prefixes research/, fpga/ and asic/ are NOT
  managed. Consequences: the helper's guarded
  deletion step never deletes a remote file under
  research/ that vanished locally, and its VERIFY
  step (extra_managed) never flags a remote-only file
  under research/. Pushes of changed research files
  DO happen (the put loop covers the whole local
  tree), so content updates land; what is unproven by
  the helper's own verify is the absence of stale
  remote-only research files. This audit's comparison
  covered all 408 paths directly and found zero
  remote-only paths, so the current tree is verified
  clean by the audit method. Recommendation for the
  parent push of this phase: extend the comparison
  to the full tree (as done here) or add research/
  to the managed prefixes before relying on the
  helper's VERIFY line for Phase 6B files.
- B6-A2 (documentation, cosmetic): the
  POST_INTEGRATION_AUDIT.md addenda undercount the
  test suite by one target in both places. The D-1
  addendum reports "20 of 21 targets pass" and the
  N-1 addendum "21 of 22", each naming test-rtl as
  the only failure. The Makefile test-all target has
  23 prerequisites today (counted in this audit from
  the Makefile and from make -n test-all, 23 python
  test invocations), and it had 22 before
  test-mainnet-live was added by the N-1 pass
  itself. With one failure, the consistent figures
  are 21 of 22 (D-1 era) and 22 of 23 (N-1 era, and
  today). No verdict changes: the pass/fail substance
  (only test-rtl fails, on the missing iverilog) is
  unaffected. Recorded so future citations use the
  right totals.
- B6-A3 (documentation, cosmetic): staging
  descriptions of the solo cutover speak of a marker
  file at .local/solo-cutover.json; at audit time
  that file does not exist, and neither does
  .local/solo-status.json. This is consistent with
  the mechanism (scripts/solo_cutover.py read_json
  defaults to an armed marker when the file is
  absent; the status file is written by the solo
  server, which has never started), and the endpoint
  config correctly reads mode "pool". No action
  needed; the record is corrected here so a missing
  marker is never misread as a fault.
- B6-A4 (documentation, cosmetic): the gpu/engine.py
  module docstring (line 25 area) describes the cpu
  fallback as "(this machine also has the C SHA-NI
  engine in mining/cpu for the Stratum path)". The
  live Stratum path does not use a SHA-NI engine:
  mainnet_live.py searches through ComputeEngine
  (v512 here), and the SHA-NI kernels are research
  artifacts in the research tree and experiments/.
  No code impact found; the sentence is stale.

No other discrepancies between documents and source
were found in the files named by the directive. In
particular: the flags file's claim that its
bal_v_batch2 and bal_v_search2 paths are identical to
the EXP-007 kernel was verified by function-level
diff in this audit (v_compress16, v_compress_scalar,
v_group and the whole span-walker-to-EOF region are
byte-identical to avx512_mb.c); the registry's
EXP-017 to EXP-023 entries match their raw session
files in count and location; the Phase 6 final
report carries addenda for EXP-017 through EXP-023
and for the integration.

## 9. Cheap verification run by this audit

Run: make test-mainnet-live
(tests/test_mainnet_live_accounting.py), 2026-11-15
about 04:37 UTC, duration about 1.2 seconds of test
output. Result: ALL MAINNET LIVE ACCOUNTING TESTS
PASSED. Detail from the run: the v512 auto-tune probe
measured 6,743,112 H/s during the test (a tuning
probe under live contention, recorded here as a test
environment note, not a benchmark); early-exit
counter advanced by exactly 16 on v512 and exactly 4
on C over a 100,000 nonce span; full miss advanced by
exactly 30,000; the no-stats fallback counted a hit
as start..winner (51) and a miss as 0. The live
miner heartbeat was re-read after the run: fresh,
miner pid 2397 still running, shares 185. The test
did not disturb the miner.

Not run, deliberately: make test-all (23 targets,
includes regtest node work and the full integration
suite; too long and too contending for an audit that
must not disturb live mining) and all benchmarks
(the baseline of record is section 6; re-benchmarking
is EXP-024's job under the EXP-017 protocol).

## 10. Item 10: experiment status table, EXP-000 to EXP-023

Source: the experiment registry, read in full by this
audit. Status words are the registry's own verdicts,
compressed; the registry entry governs.

| ID | Subject | Status |
|---|---|---|
| EXP-000 | Trusted baseline | Complete; accepted as baseline |
| EXP-001 | Compiler and flag sweep | Complete; REJECTED (no variant beat production) |
| EXP-002 | H-02 direct SHA-NI kernel | Complete; proven research kernel, not integrated |
| EXP-003 | H-01 multi-stream interleave | Complete; direction supported, integration declined under the old rule |
| EXP-004 | X-067 decision re-run | Complete; integration REJECTED (criterion failed) |
| EXP-005 | Stream geometry sweep | Complete; accepted as geometry map (streams=4 strided best) |
| EXP-006 | Hand-scheduled schedule-first | Complete; REJECTED as champion |
| EXP-007 | AVX-512 16-way multi-buffer | Complete; fastest medians; later integrated as v512 under the EXP-017 rule (see EXP-017) |
| EXP-008 | Cross-nonce phase pipelining | Complete; REJECTED on this core |
| EXP-009 | Pipeline and interaction study | Complete; accepted measurements |
| EXP-010 | Part A decision closure | Complete; criterion failed a third time under the old rule; rule later replaced by owner adoption of EXP-017 |
| EXP-011 | Dual-batch interleaved MB | Complete; NOT accepted, PROMISING HYPOTHESIS (unreproduced; raw session A lost, K-4) |
| EXP-012 | VPTERNLOGD Boolean cones | Complete; formal closure (Ch 0xCA, Maj 0xE8, XOR3 0x96, minima proven); performance hypothesis REJECTED (parity, compiler already applied it) |
| EXP-013 | Cross-lane prefix sharing | Complete; inconclusive (effect below noise floor); retained as ingredient |
| EXP-014 | K+W constant folding | Complete; REJECTED |
| EXP-015 | Bitsliced 32-lane | Complete; REJECTED by measurement (about 0.03x of MB) |
| EXP-016 | Nonce dependency derivation | Complete; derivation adopted; Y-065 and Y-075 REFUTED as work reductions (proof grade) |
| EXP-017 | Measurement stack | Complete; adopted as the decision rule by owner decision; MB and streams=4 both significant vs production; integration of MB executed (VERIFIED IMPROVEMENT) |
| EXP-018 | Register-resident dual batch (Y-023) | Complete; residency achieved, gain not significant; PROMISING HYPOTHESIS; not integrated |
| EXP-019 | Carry-save schedule pricing (Y-002, Y-001) | Complete; Y-001 and Y-002 REJECTED, established negatives; no kernel built (price gate) |
| EXP-020 | Automated full-round rewriting (Y-014, Y-015) | Complete; round closed at 28 vector ops within the searched vocabulary with matching lower bound; variant P6C-007 not significant, not integrated |
| EXP-021 | Heterogeneous worker pair (Y-097) | Complete; established negative (mixed pool below homogeneous MB at 2 and 4 threads); not integrated |
| EXP-022 | Flags-only MB batch (Y-084) | Complete; VERIFIED IMPROVEMENT in batch scope only; NOT integrated; owner decision pending (K-5) |
| EXP-023 | Midstate amortisation family (Y-076, Y-077, Y-079) | Complete; Y-076 REJECTED as specified; Y-077 VERIFIED at data level, prototype only, NOT integrated, owner decision pending and EXP-025 gate applies; Y-079 VERIFIED TABLE |

Pending at phase open: EXP-024 to EXP-029, reserved
by this assignment (registry addendum appended
2026-11-14), all NOT STARTED. Their Phase 6B files
are the stubs in this directory.

Files created by this assignment (local until the
parent pushes): the 15 documents listed in
PHASE6B_MASTER_PLAN.md section 7, all under
research/sha256d/phase6b/, plus the registry
reservation addendum in
research/sha256d/extreme_optimization/
EXPERIMENT_REGISTRY.md. No production file, no
historical evidence file and no existing registry
entry was edited.

## 11. What blocks EXP-024

Nothing found blocks EXP-024. Two facts shape its
design and are recorded here so they are not
rediscovered mid-run:

1. There is no flags search entry point anywhere:
   avx512_mb_flags.c exports bal_v_batchf2 (batch
   only) alongside the unchanged production search;
   libbal_v512.so exports only bal_v_batch2 and
   bal_v_search2; gpu/engine.py has no binding for a
   flags or mask search form. EXP-024 must design
   and build the search form (directive designs A to
   E), it cannot merely rewire an existing one.
2. The production search's avoidable cost is
   precisely located (section 4, steps 5 and 7):
   full digest materialisation for all 16 lanes of
   every group plus scalar per-lane comparison, in
   both modes. The batch epilogue that EXP-022
   removed does not exist in search mode in the same
   shape, so EXP-024's effect size is an open
   measurement question, not an extrapolation of
   1.82x. Its predeclared criterion (EXP024_MASK_
   SEARCH.md) is written accordingly.
