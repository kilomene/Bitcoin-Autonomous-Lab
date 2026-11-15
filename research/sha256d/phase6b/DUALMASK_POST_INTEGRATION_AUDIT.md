# Post-Integration Audit: AVX-512 DualMask Production Backend (v512dual)

Date: 2026-11-14 (executed 2026-11-15T07:00Z to 07:05Z).
Auditor: independent post-integration audit (the auditor
did not write the integration). Subject: the production
integration recorded in PRODUCTION_INTEGRATION_LOG.md
Entry 1 (ComputeEngine backend "v512dual",
mining/cpu/bal_avx512_dual.c, mining/cpu/build.py,
gpu/engine.py selection, mining/mainnet_live.py status
line). Every claim below was re-derived by the auditor
from the tree, fresh scratch builds, fresh runs and
live reads. Nothing rests on the integration report's
word. The auditor did not stop or restart the miner or
the node at any point; the live deployment was verified
from the outside only.

Overall verdict: PASS WITH NOTES. No defect found
(no D- findings). Three notes (N-1 to N-3), all
cosmetic or observational. No correctness defect found;
nothing about the live backend is unsafe. The deployed
miner is running the audited code now.

## Area 1: kernel identity. PASS

Method: direct diff of mining/cpu/bal_avx512_dual.c
against research/sha256d/extreme_optimization/src/
avx512_mb_exp026_dual.c (77 diff lines), then a
normalised comparison (export renames mapped back,
comments and the include line stripped): the code is
identical. The only differences are exactly the
documented ones:

- The production header comment (longer, records the
  integration and the export mapping).
- The bal_search.h include path
  ("../../../../mining/cpu/bal_search.h" in research,
  "bal_search.h" in production).
- The three export renames: bal_vd_search2 from
  bal_v_e26d_search2, bal_vd_batch2 from bal_r_batch2,
  bal_vd_search2_exp018 from bal_r_search2 (plus two
  doc-comment mentions of the new names).

bal_vd_search2_exp018 is exported and not called by
the engine, as documented (source parity only).

## Area 2: build and instruction-set census. PASS

Method: fresh build in a scratch copy of the tree
(/tmp/audit-dual) using the production build.py.

- V512_FLAGS in build.py is exactly
  ["-mavx512f", "-mavx512bw"], applied to the dual
  translation unit only; the probe unit is compiled
  with no vector flags; no -march=native anywhere in
  the dual build path.
- The scratch-built libbal_v512dual.so is
  byte-identical to the production library in
  .local/cpu (sha256
  15e226145b9ff3bd62c9b0e52bb41090fab641e67b11f945f0866fcbd3a33d62
  for both).
- Objdump census of the fresh build: zero unambiguous
  AVX-512DQ, VBMI or IFMA mnemonics (no vpmullq,
  vpermi2/vpermt2 families, vpmultishiftqb,
  vpmadd52luq/huq, or vcvt*qq forms). vpternlogd
  appears 103 times and vpcmp 30 times, matching the
  integration record; vpternlogd is an AVX-512F
  instruction and is not a DQ/VBMI/IFMA form. The
  mnemonic census of the fresh build is identical to
  the shipped library's.

## Area 3: dispatch, D-1 guards, and the self-test race fix. PASS

Method: source read of gpu/engine.py _try_v512dual
and the search and tuning paths, plus the forced
fallback runs of Area 6.

- Dispatch order in ComputeEngine.__init__ is CUDA,
  then v512dual (requested "auto" or "v512dual"), then
  v512, then C. requested="c" pins C and
  requested="v512" pins the single-batch kernel; both
  were exercised live by the auditor's runs and by the
  integration suite (Area 8).
- _try_v512dual checks hasattr for bal_v512_supported
  before calling the probe, checks the probe result,
  then checks hasattr for bal_vd_batch2 and
  bal_vd_search2 and rejects the library as a whole,
  naming the missing entry points, BEFORE any argtypes
  assignment. build.py _smoke_v512dual follows the
  same pattern. The D-1 rule from the v512 audit is
  applied in both places.
- Selection requires the 256-nonce batch self-test
  against hashlib (digest by digest) and the
  dual-shape search self-test: a 64-nonce counted
  search at ONE thread crossing both batches and the
  32-lane boundary, an all-meet leg (first nonce, exact
  digest) and a target-1 miss leg (rc 0, attempted
  exactly 64). The single-thread choice and its reason
  (the counted context publishes the first winner
  across spans, so a multi-span all-meet probe would
  be a race) are documented in the code at the site.
- Race-shape probe of the rest of the new code path:
  tune_v512dual_threads probes with target 1 (a clean
  miss), so no winner is ever published there;
  _vd_batch_flagged enumerates the full range and has
  no first-winner semantics; the build smoke search
  runs 2 threads over a span containing exactly one
  DIFF1 candidate (the genesis nonce) and checks
  accounting plausibility, not a raced value; the
  production counted search itself accepts any valid
  winner and verifies it with verify_candidate before
  use, so winner nondeterminism among multiple valid
  candidates is semantically harmless there. No other
  instance of the race shape was found.

## Area 4: fresh differentials through the production API. PASS

Method: the auditor's own script (not the integration
suite), driving ComputeEngine.batch_search with the
auto-selected v512dual backend, target 2^256-1,
comparing every returned digest against hashlib
(cpu_digest), with candidate hashes converted from
display order.

- 121,400 fresh randomised differentials, 0
  mismatches. Includes batch sizes 15/16/17/31/32/33/
  63/64/65 at start 0 and as spans ending exactly at
  2^32, plus randomised bulk spans.
- The integration suite's claimed 197,616
  differentials were reproduced by running
  make test-avx512dual (Area 8): 0 mismatches there
  too, including the same boundary sizes and 2^32-end
  spans, and candidate-set equivalence at density 0
  and about 2^-12 against an independent recount.

## Area 5: counted accounting contract. PASS

Method: the auditor's own dual-walker simulation,
written from the kernel's documented contract
(partition into per-thread contiguous spans; dual
groups of 32 lanes while at least 17 nonces remain in
a span, then one single group of 16), compared against
search_first_counted results and last_search_stats.

- Miss spans (target 1) at counts 1, 5, 16, 17, 31,
  32, 33, 64, 100, 1000 and 65536: attempted equals
  the count exactly, backend_hashes equals the
  simulation exactly at every size, unique_coverage
  equals the count. Verified at C_THREADS 4 and 8
  (the tuner selected different values across runs;
  the predictions matched in both regimes).
- Hit span (genesis, DIFF1): nonce 2083236893 found
  with the exact hashlib digest, attempted 4503,
  backend_hashes 4608 (a whole number of 16-lane
  groups, not below attempted).
- Bad-candidate behaviour is by construction: the
  v512dual branch of search_first_counted verifies
  the candidate with verify_candidate and, on failure,
  calls the same _recover_bad_candidate fail-closed
  CPU rescan as the v512 branch, marking the backend
  "cpu-rescan" and voiding unique_coverage with a
  note. (Source-verified; a bad candidate cannot be
  produced by the correct kernel on demand.)

## Area 6: forced fallback. PASS

Method: the auditor's own ComputeEngine constructions
with vd_lib_path redirected, in scratch only, each
followed by a genesis search that must still succeed.

- Absent library: lands on v512, reason records the
  missing path.
- Probe-failure library (auditor-compiled stub,
  bal_v512_supported returns 0): lands on v512, reason
  records the CPUID dispatch failure.
- Incomplete library, the D-1 shape (auditor-compiled
  stub: probe returns 1, bal_vd_batch2 present,
  bal_vd_search2 missing): rejected as a whole with
  bal_vd_search2 named; lands on v512, no exception.
- The v512 library offered as the dual library (probe
  present and passing, both dual symbols missing):
  rejected as a whole with both names; lands on v512.
- Dual build failure (corrupted source in the scratch
  copy): build_v512dual returns ok False and lib None
  without raising; the engine treats that state as
  "not built" (the absent-library case above).
- In all four engine cases the engine kept mining
  correctly (genesis nonce found through the fallback
  backend). No case raised.

## Area 7: fresh regtest block. PASS

Method: the auditor's own run through the production
path (MiningEngine over ComputeEngine auto-selected
v512dual, production template, assembly and
submission), regtest node already at tip 909.

- Block accepted by Core at height 910, hash
  22fad4bcda202fd12e91664240e7f9ca1726b2b7f0db18a8c324fec2fef233a8,
  best-block hash matches, height advanced by exactly
  one. This is beyond the integration's claimed
  heights 830 and 877, both of which are consistent
  with the chain history below 909.
- The integration suite run (Area 8) mined a further
  block at height 911 through the same path.

## Area 8: changed tests and suite targets. PASS

- The four extended known-backend enumerations are
  present as claimed: tests/test_gpu_compute.py,
  tests/test_gpu_correction.py, tests/test_deepening.py
  and tests/test_cpu_aspect.py each include "v512dual"
  in their accepted backend sets.
- tests/test_avx512_integration.py pins
  requested="v512" where it gates the single-batch
  backend itself (dispatch test and fallback tests),
  with the reason documented at the site.
- make test-avx512dual: ALL PASSED (dispatch,
  forced fallbacks, 197,616 differentials, candidate
  sets, search gates, regtest block at height 911).
- make test-mainnet-live (the N-1 accounting tests):
  ALL PASSED.
- The integration's full-suite claim (23 of 24,
  test-rtl failing on absent iverilog) was not
  re-run end to end by this audit; the two targets
  most affected by the integration were re-run and
  pass, and test-rtl does not touch this code path.

## Area 9: live deployment, verified from the outside. PASS

Method: reads only (.local/mainnet-status.txt,
.local/heartbeat.json, evidence/mainnet-live.jsonl).
Nothing was restarted.

- Status file: "compute backend: v512dual (native
  impl: avx512-dual; AVX-512 DualMask: selected:
  CPUID probe confirms AVX-512F and AVX-512BW, the
  batch reproduces hashlib digests, and the
  dual-shape search self-test passes)".
- Session rate observed by the auditor: 20.63M H/s
  (status at t=735s of the session) and 20.65M H/s in
  the evidence log status events, against the
  integration record's 21.4 to 21.5M H/s readings and
  the prior v512 session's 9.7 to 10.3M H/s. Live
  readings under contention; the verified figure
  remains the EXP-026 kernel-scope 1.718x.
- Evidence log: 205 accepted share_result events in
  total (counted by the auditor). The first share of
  the v512dual session is the accepted share_result
  at 2026-11-15T06:57:29Z, after the v512dual
  backend_selected event at 2026-11-15T06:48:04Z,
  exactly as the integration record states.
- Heartbeat fresh at every read; at the final read
  (2026-11-15T07:04:25Z) autopilot pid 3190, miner
  pid 30455, state running, restarts 2,
  shares_accepted_total 205 (see N-3).

## Area 10: hygiene. PASS

- Em dash scan (byte-wise, U+2014) over all twelve
  files the integration changed, including this
  log's entry: zero occurrences.
- Secret scan over the same files: no RPC credentials,
  private keys or password material. Node RPC
  credentials exist only in .local/mainnet/
  bitcoin.conf (mode 0600), which is local-only state
  outside the repository tree and was not touched by
  the integration.

## Notes

- N-1 (cosmetic, log completeness): the evidence log
  carries two v512dual backend_selected events. The
  first, at 2026-11-15T06:46:17Z, has no
  v512dual_reason field; the second, at
  2026-11-15T06:48:04Z, carries the full reason. This
  is consistent with the status-line fix landing
  mid-deployment (the first event was written by the
  pre-fix binary). No action needed; recorded so the
  gap in the log is explained.
- N-2 (observation, inherited pattern): the thread
  auto-tuner is nondeterministic under contention.
  Across the auditor's runs it selected 4 and 8
  threads with probe rates between about 9.6M and
  39.2M H/s. This mirrors the pre-existing v512
  tuner, and accounting stayed exact in both regimes
  (Area 5). No action proposed.
- N-3 (cosmetic, known lag): at the auditor's first
  heartbeat read the shares_accepted_total read 204
  while the evidence log already held 205 accepted
  shares; by the final read the heartbeat had caught
  up to 205. The evidence log is the primary source,
  as the integration record states.

## Close confirmation

The auditor restarted nothing. At the close of the
audit the miner is still running on v512dual
(heartbeat 2026-11-15T07:04:25Z, miner pid 30455,
state running), the node was never touched, and the
only files this audit created are this document and
the one-line pointer in PRODUCTION_INTEGRATION_LOG.md.
Scratch work lived in /tmp and was left there.
