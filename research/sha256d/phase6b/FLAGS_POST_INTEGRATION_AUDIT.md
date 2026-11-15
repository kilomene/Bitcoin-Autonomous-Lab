# EXP-022 Flags Batch Post-Integration Audit

Independent post-integration audit of the EXP-022
(Y-084) flags batch adoption for the engine batch
consumers (PRODUCTION_INTEGRATION_LOG.md Entry 3).
The auditor is not the integration author. Every
number below is the auditor's own work, produced
with the auditor's own harnesses (fresh seeds), not
a re-statement of the author's gate numbers, except
where a suite run is explicitly identified as the
author's suite being re-run as a check.

Date: 2026-11-15. Host: AMD EPYC 9D25 guest (the
Phase 6B host), live miner running throughout.

## Verdict: PASS WITH NOTES, zero defects

## 1. Provenance

- The production translation unit
  mining/cpu/bal_avx512_flags.c (484 lines) was
  compared against the research original
  research/sha256d/extreme_optimization/src/
  avx512_mb_flags.c (688 lines) by the auditor:
  after stripping the header comment and include
  lines from both, every substantial paragraph of
  the production body (20 of 20) appears verbatim
  in the research original. The retained code is
  byte-identical to the research source, as
  claimed.
- The production library .local/cpu/
  libbal_v512flags.so exports exactly
  bal_v_batchf2 plus the probe symbols
  bal_v512_supported and bal_v512_feature_bits
  (and the bal_search.h failure-hook data symbols).
  No search entry point exists in the library.
  The strings v_group and bal_v_batch2 /
  bal_v_search2 appear in the production source
  only inside comments; there is no v_meets or
  v_group code in the file.
- The preserved fallback is unchanged:
  mining/cpu/bal_avx512_mb.c carries a modification
  time of 2026-11-14 15:05, a full day before the
  flags integration (2026-11-15 08:45), and its
  integration suite passes (section 5). The
  research file's bal_v_batch2 and bal_v_search2
  sections were not copied into the flags TU.

## 2. Selection safety

- The probe (mining/cpu/bal_avx512_probe.c,
  compiled with no vector flags) requires exactly
  __builtin_cpu_supports("avx512f") and
  __builtin_cpu_supports("avx512bw"); the build
  compiles the kernel TU with exactly
  V512_FLAGS = -mavx512f -mavx512bw (build.py
  line 85), never -march=native.
- gpu/engine.py _try_v512flags: the library is
  loaded, the probe is called first, and the
  hasattr check on bal_v_batchf2 precedes the only
  argtypes assignment for that symbol. The same
  discipline holds in build.py _smoke_v512flags
  (hasattr before argtypes for both symbols).
- The engine self-test is genuine: a 256-nonce
  batch at target 2^255 whose flagged pairs and
  digests must equal a hashlib recount exactly,
  with exact accounting (256, 256), followed by a
  pure-mode call (digests NULL) whose flag bits
  must equal the extract-mode candidate set. The
  build smoke test independently checks the
  all-ones target (every flag bit set, every digest
  equal to hashlib), a difficulty-1 target bit for
  bit against hashlib, exact accounting, and pure
  mode bit equality.
- Pins verified by construction in the auditor's
  harness: requested="c" selects backend c with no
  flags path; requested="cpu" selects the Python
  backend with no flags path; requested="v512"
  keeps the v512 search backend and routes its
  batch through flags with an exact candidate set.

## 3. Auditor's own differentials

Auditor harness, fresh seed 20261115, independent
hashlib recount of every nonce, three-way
comparison (flags path, preserved v512dual batch,
hashlib) on candidate sets and on the digests of
flagged lanes:

- Density 1 (target 2^256 - 1): 24 trials of
  2,048 nonces, 49,152 digests byte-identical
  three ways.
- Density about 2^-8: 4 trials of 16,384 nonces.
- Density about 2^-16: 2 trials of 65,536 nonces.
- Boundaries: sizes 15, 16, 17, 31, 32, 33, 63,
  64, 65 at starts 0, 12345 and NONCE_SPACE minus
  count (spans ending exactly at 2^32), density 1,
  byte-exact.
- Density 0 (target 1) through batch_search:
  empty candidate set, batch_path "flags".
- Total: 246,768 nonces recounted, 0 mismatches.
  On every call the flags ABI's (attempted,
  backend) counts equalled the preserved dual
  batch ABI's counts exactly, with attempted equal
  to the requested count.
- Target equality and minus-one: a nonce whose
  digest equals the target is flagged, and is not
  flagged at target minus one, both through the
  direct flags call and through batch_search.

## 4. Auditor's forced fallbacks

The auditor built three stub libraries of his own
(probe-only, probe-returns-0, kernel-returns-minus-1)
and used a nonexistent path for the absent case:

- Incomplete library (probe present, bal_v_batchf2
  missing): rejected with the missing entry point
  named; batch_search served by the materialised
  batch, candidate set exact, batch_path reported
  "materialised".
- Probe-failure library: rejected at the CPUID
  step; same exact materialised service.
- Absent library: rejected as not built; same.
- Kernel returning -1: rejected at the self-test;
  same.
- Runtime failure after selection (a selected
  engine whose flags library handle was swapped
  for the failing stub): batch_search fell through
  to the materialised batch for that call, exact
  candidate set, batch_path "materialised".
- want_all: the preserved dual wrapper with
  want_all=True returned all 1,000 digests of a
  1,000-nonce batch, every one byte-identical to
  hashlib. No caller needing full digests can
  receive flags-shaped partial output through that
  wrapper, and batch_search never calls the flags
  entry for want_all purposes.

## 5. Search non-interference and template cache

- make test-avx512flags (the author's suite, re-run
  by the auditor as a check): ALL PASS, including
  its 491,520 differentials and a regtest block at
  height 1021 in that run.
- make test-avx512: ALL PASS (regtest height 1023
  in that run). make test-avx512dual: ALL PASS
  (regtest height 1024). Search dispatch and
  behaviour are unchanged.
- Template cache: mining/engine.py carries a
  modification time of 2026-11-15 07:43 UTC, the
  cache integration window, predating the flags
  work (08:45); make test-template-cache passes
  unchanged (regtest height 1022 in that run). The
  flags integration did not touch the EXP-025
  cache.

## 6. Auditor's regtest block

The auditor mined a fresh regtest block through
the production ComputeEngine (auto engine, v512dual
search, MiningEngine.mine_cycle), accepted by Core
as best block: height 1025, hash
50a5470ffd2726c91a4d87b0defc4160779c355195756424d644c83ef8867cfb.
The block's header was then re-enumerated through
batch_search with batch_path "flags" proven in the
returned stats: the block nonce (12501) came back
among 26,166 verified candidates, each
independently verified with hashlib.

## 7. Benchmark spot-check (batch scope only)

One EXP-017 session from the author's driver
(exp022f_paired_bench.py, comparison
flagsx_vs_production_d0, 120 pairs, 65,536-hash
blocks, 2 threads, density about 0), run alone:
session 20261115T091030Z, auditor's own bootstrap
over the recorded per-pair log ratios gives ratio
1.285, 95 percent CI [1.029, 1.603], pairs won
63.3 percent. The interval lies entirely above 1
and overlaps the author's pooled figure of 1.441x
[1.261, 1.645] (the auditor's point estimate sits
inside the author's pooled interval). Verdict:
consistent with the claimed pooled figure, in
direction, significance and magnitude, at batch
scope. The session ran under audit-time contention
(the live miner plus the auditor's own suites), so
a point estimate below the pooled figure is
expected and is not a discrepancy. The session
record is preserved alongside the author's in
benchmarks/exp022f/.

## 8. Live state

Nothing was restarted by the integration or by
this audit. At audit close: heartbeat fresh
(2026-11-15T09:11:02Z), autopilot pid 3136, miner
pid 3140, restarts 0, backend v512dual, endpoint
still pool mode. The evidence log (the primary
source) records 237 accepted shares and rising;
the heartbeat counter reads 221 and lags the log,
the known counter behaviour, not a share loss.

## 9. Hygiene

- Long dash (U+2014) byte scan: zero in all six
  changed files and zero across the whole tree
  excluding .local (652 files scanned).
- Secrets scan by value, in memory only: the node
  RPC password and both wallet private-key fields
  (private_key_hex, private_key_wif) are absent
  from the tree. CLEAN. (The wallet's public
  address and descriptive strings appear in the
  tree, public by design, as in every prior audit.)

## Defects

None.

## Notes

- N-1: the flags library also exports the probe
  symbols and the bal_search.h failure-hook data
  symbols. This matches the v512 and v512dual
  library pattern and is how the engine probes
  safely; it is not additional kernel surface.
- N-2: in batch_search, a flags call that returns
  pairs which then fail CPU verification is
  handled by the pre-existing fail-closed rescan
  labelled with the search backend's name (for
  example "native AVX-512 DualMask batch") rather
  than a flags-specific label. The rescan itself
  is correct and complete; only the event label
  names the backend family, not the batch path
  that served. Cosmetic.
- N-3: the auditor did not re-run the full
  26-target suite; the targets run are listed in
  section 5. The author's full-suite result (25 of
  26, only the pre-existing test-rtl iverilog
  failure) stands as the integration record, and
  every target the auditor did run passed on its
  first run, with no contention flake observed.
- N-4: an auditor-side analyze invocation was
  started against the author's benchmark records
  and terminated once it had reproduced the pooled
  figures in its output; it wrote no files before
  termination and no benchmark was run in parallel
  with it.
- N-5: the auditor's first append of this audit's
  pointer to the integration log landed after
  Entry 2's identical audit-pending text instead
  of Entry 3's; it was removed from Entry 2 and
  re-appended to Entry 3 in the same session, and
  the final state of both entries was verified by
  reading them back. No other content changed.
