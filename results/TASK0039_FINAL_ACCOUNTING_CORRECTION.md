# Task 003.9: Final Mining Accounting Correction, Benchmark Accuracy and Release Sign-Off

Date: 2026-11-14. Repo: kilomene/Bitcoin-Autonomous-Lab (Phoenix
build, Bitcoin Core 28.1). Chain scope: regtest only for
integration; no mainnet work was done and the live mainnet
autopilot, miner and node services were never stopped or
altered (heartbeat fresh at the end of the work, 42 accepted
shares, miner state running).

## Commit examined

The local checkout has no .git directory, so the baseline was
established from the GitHub API: branch main, HEAD commit
21ab7ca52e96ddb4a1dcfcdc5e193d31a41b393b, committed
2026-11-14T09:49:15Z, message "Bitcoin Autonomous Lab: update
tests/test_task0038_abi.py". The repository is public. Before
any change, the local tree was compared against that commit's
recursive tree by blob SHA: identical except
evidence/mainnet-live.jsonl, the append-only evidence file of
the live mainnet miner running under separate owner orders.

Environment facts, rechecked live: no NVIDIA GPU exists on
this VM (zero /dev/nvidia nodes; CUDA runtime error 35), so
physical GPU execution and GPU performance are UNVERIFIED.
iverilog is absent, so RTL validation is UNVERIFIED
(test-rtl fails on that alone). nvcc 12.9.86 is present
repo-locally at .local/cuda129 (BAL_NVCC mechanism, restored
during Task 003.8).

## Phase 1: current-state trace (from the source, not the reports)

Every counter in gpu/engine.py and gpu/benchmark.py was traced
across the CPU, C, CUDA, overflow-recovery, verification and
rescan paths. Findings:

Where requested was counted as actual:

1. ComputeEngine.benchmark() accumulated `hashes += batch`,
   the REQUESTED batch size, and returned hashes / seconds.
   Any batch whose actual computations differed from the
   request (CUDA overflow recovery recomputes nonces) was
   misreported, and verification work was invisible. This is
   the headline defect of this task.
2. ComputeEngine.search_first_counted's "attempted" total on a
   verification rescan mixed native backend attempts and
   rescan attempts into one number with no field separating
   them (the split existed only inside the fallback event).

Where the CUDA invariant was over-generalized:

3. collect_candidates_complete's docstring stated "For every
   completed call the invariant device_hashes ==
   unique_coverage + researched_hashes holds" without scope.
   The driver is generic code; the identity is a property of
   its CUDA accounting (its only production caller is
   CudaContext), not of mining statistics in general.
4. The Task 003.8 report described last_search_stats.attempted
   as "the device_hashes analogue" for the CPU early-exit
   path, and described backend_hashes as "actual computations
   across backend and recovery". Both phrasings blur exactly
   the boundaries this task exists to fix. The report now
   carries an appended Task 003.9 scoping note (history not
   rewritten).

Where categories were mixed:

5. ComputeEngine.batch_search, all three paths: backend_hashes
   was count + rescan_attempted (C and generic paths) or
   device_hashes + rescan_attempted (CUDA path), folding
   trusted-rescan computations into the backend total while
   ALSO reporting them as verification_rescan_hashes: the same
   computations counted in two categories.
6. Independent candidate verification itself was counted
   nowhere: verify_candidate computations (one SHA-256d per
   presented candidate in _check_pairs, in the generic
   enumeration loop, and in the rescan's re-verification of
   each find) were invisible in every stats dict.

What was already correct and was not touched: the C library's
counted entry points (bal_c_search2/bal_c_batch2 report actual
per-worker attempts), MiningEngine's use of
search_first_counted attempts (Task 001/003.2), the driver's
internal split of unique vs researched work, and the
fail-closed rescan behavior itself (Tasks 003.4/003.8).

## Phase 2: accounting definitions (before and after)

Definitions now live in gpu/engine.py's module docstring and
govern every stats dict the module produces.

| Metric | Meaning (Task 003.9) | Applies to | Excludes |
|---|---|---|---|
| requested_hashes | Computations the caller asked for (nonce-range size) | all paths | n/a: a request is not work |
| unique_coverage | Distinct nonces actually covered; full range size on completed enumerations; distinct nonces examined before stopping on early-exit paths; None with a note when the exact number is not measurable (post-rescan union, legacy uncounted library) | all paths | repeats of any kind |
| backend_hashes | Actual computations performed by the selected mining backend itself | CPU, C, CUDA | verification and rescan work, always |
| device_hashes | Actual computations performed by a CUDA device | CUDA only; exactly 0 when no device executed work | all CPU and C work |
| researched_hashes | Extra backend computations repeating already-covered work (CUDA overflow recovery) | CUDA path (subset of device_hashes and of backend_hashes there) | first-pass work |
| overflow_splits | Range subdivisions caused by candidate-buffer overflow | CUDA recovery driver | n/a |
| verification_hashes | Actual computations by the independent verification and recovery layer: one per candidate presented for verification, plus every trusted-rescan computation (enumeration digests and per-find re-verifications) | all paths | backend mining work |
| candidate_count | Candidates the backend presented for independent verification | all paths | candidates the rescan found (those are recounted set members, reported in the candidate list) |

Before (Task 003.8): backend_hashes mixed backend and rescan
work; verification computations were uncounted; the only
total was that mixture; the CUDA identity was stated without
scope; the CPU early-exit stats carried no standard fields.

After (Task 003.9): every computation is counted in exactly
one category. Identities, each scoped:
- CUDA driver paths: device_hashes == unique_coverage +
  researched_hashes, and backend_hashes == device_hashes.
- CPU and C paths: device_hashes == 0, and backend_hashes +
  verification_hashes == total actual computations (the
  legacy "hashes" key carries exactly that total).
- Early-exit C path: backend_hashes is the counted native
  attempts; unique_coverage equals it when no rescan
  intervened; after a rescan, unique_coverage is None with
  an explanatory note, because the exact union of the
  backend's scattered examined set and the rescan's prefix
  is not measurable. Nothing is invented.

Implementation notes: _check_pairs now also returns the
number of verification computations it actually performed
(pairs rejected by the cheap range/duplicate checks cost no
hash and are not counted); _rescan_all_candidates now also
returns its total verification computations (enumeration
plus per-find re-verifications); batch_search was
re-accounted on all three paths; search_first_counted stats
gained the standard fields; the CUDA recovery driver gained
backend_hashes and requested_hashes alongside its existing
fields (identical totals there, since it wraps one backend)
and its invariant is now scoped in its docstring.
verification_rescan_hashes is retained as the rescan
enumeration count for older callers.

Two assertions in tests/test_task0038_abi.py encoded the
superseded Task 003.8 mixed definition (backend_hashes ==
count + count after a rescan) and were corrected to the
Task 003.9 split (backend_hashes == count), with added
assertions on verification_hashes and on the total. This is
the definition change the task ordered, not a weakening:
the same totals are asserted exactly, now in the right
fields. No other existing test was changed.

## Phase 3: the benchmark fix

ComputeEngine.benchmark() did `hashes += batch` per batch.
It now delegates to the new ComputeEngine.benchmark_report(),
which accumulates the actual per-batch statistics returned
by batch_search: elapsed seconds (sum of the per-batch
monotonic seconds), requested_hashes, unique_coverage and
coverage_per_second, backend_hashes and hashrate (actual
backend computations per second), device_hashes and
device_hashes_per_second (0 with an explicit note when no
CUDA device executed work), verification_hashes with its
share of total work, researched_hashes with their share of
backend work, overflow_splits and candidate_count, plus the
backend name and per-run detail. Overflow recovery is
therefore visible in benchmark output, never folded silently
into a single rate. benchmark() keeps its historical float
contract (the dashboard, the autonomous agent and
mining/cpu/miner.py consume a float) but the float is now
the actual backend rate; it raises RuntimeError when a batch
fails instead of returning a clean-looking rate over partial
work, while benchmark_report() returns the failed report
with partial totals marked by batches_completed <
batches_requested. gpu/benchmark.py was aligned: per-run
verification and requested fields, and totals for backend,
device, verification and coverage with stated definitions.

Before-and-after example (the headline regression test,
deterministic): a stub backend whose batch of 1024 requested
nonces actually computes 5120 hashes (overflow recovery
repeats), 2.0 seconds elapsed.
- Before: benchmark reported 1024 / 2.0 = 512.0 H/s.
- After: benchmark reports 5120 / 2.0 = 2560.0 H/s actual
  backend computations, with coverage 512.0 per second,
  device rate 2560.0 per second, researched share 0.8 and
  15 overflow splits all reported separately.
End-to-end through the real recovery driver (flooding stub):
2 batches requested 2048 in total, actual device
computations 10240 after 30 overflow splits, researched
8192, identity 10240 == 2048 + 8192 exact.

## Tests executed and results

New suite tests/test_task0039_accounting.py (Makefile target
test-task0039; test-all now has 20 targets): ALL PASSED.
Sections: CUDA stub without overflow (all fields exact,
verification equals candidate count); CUDA stub with forced
overflow (device 8864 = unique 1024 + researched 7840, 220
splits, backend == device, 512 candidates cost exactly 512
verification hashes); multiple splits on an all-match range
(31 splits, device 384 = 64 + 320); CPU fallback (backend
2000, device 0, CUDA identity explicitly shown NOT to hold,
verification 1021 separate); native C batch (backend 2000,
device 0, one verification hash per presented candidate);
full-range coverage at an odd count (unique == requested ==
4097); early-exit counted accounting (genesis hit:
backend_hashes == counted attempts, far below 100000
requested, exactly 1 verification hash; miss: exactly 30000
backend, 0 verification); early-exit rescan accounting
(backend 6, verification 1 + rescan attempts, coverage
honestly None with note); fail-closed batch split (backend
2000, verification 3022 = 1 + 2000 + 1021, total identity
exact); the headline benchmark test above; benchmark
overflow integration; CPU benchmark has no device component;
zero-work and failed-batch benchmarks; fresh regtest block.

Existing suites rerun after the changes:
- tests/test_task003_corrections.py: PASS (including its
  sanitizer sections and its own fresh regtest block).
- tests/test_task0038_abi.py: PASS (including host ABI
  validation, sanitizers, compiled-library ABI checks, and
  its own fresh regtest block).
- Full suite: 20 targets, 19 PASS, 1 FAIL. The single
  failure is test-rtl, solely because iverilog is not
  installed on this VM ("iverilog: not found"), the same
  pre-existing environment failure as in Tasks 002, 003 and
  003.8; the target was not hidden or weakened. (A single
  make test-all invocation plus per-target reruns were used
  to tally all 20; every target's own PASS line was
  observed.)

Compilers and sanitizers: no C or C++ files were changed in
this task (the correction is Python accounting plus tests
and docs). The host validation builds inside the Task 003
and 003.8 suites compile with strict warnings and ran clean
under ASan and UBSan, and under TSan (setarch -R) for the
CPU libraries, miner, mutex harness and CUDA host checks, in
this session's runs. nvcc 12.9.86 remains available
repo-locally; no CUDA source changed, so no new device-side
compilation result is claimed beyond the suites' rebuilds.

## Benchmark measurements (this VM)

All numbers are from this shared, capped VM (about 1.5
CPUs) with the live mainnet miner and node running; run to
run variance is wide and no performance improvement is
claimed by this task. Host numbers are never GPU
measurements; the harness labels them itself.

- Native C backend, ComputeEngine.benchmark_report, 3
  batches of 65536 at target 2^240: requested = unique =
  backend 196608, device 0, verification 12 (12 candidates
  presented), elapsed 0.1965 s, backend rate about
  1,000,000 per second; a separate benchmark() call measured
  about 1,173,000 per second.
- Python CPU backend, same shape: elapsed 1.4028 s, backend
  rate about 140,000 per second; benchmark() about 167,000
  per second on a separate call.
- gpu/benchmark.py harness (C fallback, 3 batches of
  65536): median backend rate about 745,000 per second,
  totals backend 196608, device 0, verification 12, unique
  196608, label "NOT a GPU measurement: fallback backend
  executed the work".
- CUDA device rates: none exist. UNVERIFIED (no GPU).

## Regtest evidence (this task)

Fresh block mined after the changes through
mining/engine.py with the native CPU backend
(ComputeEngine backend "c"): height 592, hash
40d4406a1c90ba1dff878dc25866622e983832cd7ea018708a7e333528689b32,
submitblock returned null, and the node's best block equals
the block hash (asserted in tests/test_task0039_accounting.py).
The make test-task0039 rerun mined a further accepted block
at height 629, hash
086c1399f6d39a86b933ff09a26172c46c6f258e046a1fd8eb0c6dd6523df5a3,
under the same assertions.

## Physical GPU status

UNVERIFIED. No NVIDIA GPU exists on this VM (zero
/dev/nvidia nodes, CUDA runtime error 35). No GPU execution,
GPU performance, or GPU regtest acceptance is claimed; all
CUDA-path evidence comes from stubs implementing the device
primitive's bounded semantics over real digests, and from
the host-compiled shared source, exactly as in Tasks 002,
003 and 003.8.

## RTL validation status

UNVERIFIED. iverilog is not installed on this VM; test-rtl
fails on that absence alone, unchanged from previous tasks.

## Files changed

- gpu/engine.py: accounting definitions in the module
  docstring; collect_candidates_complete scoped invariant
  plus backend_hashes and requested_hashes fields;
  CudaContext.search info gains backend_hashes,
  verification_hashes, requested_hashes; _check_pairs counts
  verification computations; _rescan_all_candidates returns
  verification computations; batch_search re-accounted on
  the C, CUDA and generic paths; search_first_counted stats
  gained the standard fields; benchmark() fixed and
  benchmark_report() added.
- gpu/benchmark.py: verification and requested fields per
  run; backend, device, verification and coverage totals;
  definitions aligned to Task 003.9.
- tests/test_task0039_accounting.py: new suite.
- tests/test_task0038_abi.py: two backend_hashes assertions
  corrected to the Task 003.9 definition with added
  verification_hashes assertions; docstring scope note.
- Makefile: test-task0039 target; test-all now 20 targets.
- docs/CUDA.md: Task 003.9 accounting note.
- results/TASK0038_CUDA_ABI_HARDENING.md: appended Task
  003.9 scoping note.
- results/TASK0039_FINAL_ACCOUNTING_CORRECTION.md: this
  report.
- evidence/regtest/task0039-accounting.json:
  machine-readable evidence.

No SHA-256, nonce-search, consensus, CPU, or CUDA kernel
code was changed; SHA-256d correctness evidence is the
passing differential suites listed above.

## Acceptance conditions

1. CUDA accounting invariants are correctly scoped: PASS
   (scoped in the module docstring, the driver docstring,
   docs/CUDA.md and the 003.8 report addendum; tests assert
   the identity on CUDA paths and its non-application, with
   device_hashes == 0, on CPU and C paths).
2. CPU, C and CUDA statistics have unambiguous meanings:
   PASS (definitions table above, implemented identically
   across batch_search, search_first_counted, the recovery
   driver and both benchmark surfaces).
3. Legacy benchmark counts actual computations: PASS
   (headline regression test: 5120 actual, not 1024
   requested; benchmark() and benchmark_report() both
   accumulate returned stats).
4. Overflow recovery cannot distort benchmark reporting:
   PASS (device, researched and splits are separate fields;
   flooding-stub integration test shows 10240 actual vs
   2048 requested inside a benchmark run).
5. Regression tests prove these behaviors: PASS (new
   suite, all sections, listed above).
6. Existing SHA-256d correctness is preserved: PASS (no
   hash code changed; differential and known-block suites
   pass in the full run).
7. Existing nonce coverage and candidate-verification
   guarantees remain intact: PASS (fail-closed behavior
   unchanged; the 003, 003.8 and 003.9 suites assert exact
   coverage and exact candidate sets, including after
   verification failures).
8. No previous passing functionality is broken: PASS
   (19 of 20 targets pass; the only failure, test-rtl on
   absent iverilog, predates this task and is
   environmental).

## Remaining limitations

- Physical GPU execution, GPU performance and GPU regtest
  acceptance remain UNVERIFIED until the repo runs on a
  machine with a supported NVIDIA GPU; the accounting code
  paths are exercised here only through device-semantics
  stubs and the host build.
- RTL validation remains UNVERIFIED while iverilog is
  absent from this VM.
- On the early-exit path after a verification rescan,
  unique_coverage is reported as unavailable (None with a
  note) rather than estimated; the exact union of the
  backend's examined set and the rescan's prefix is not
  measurable from the counted interfaces.
- The legacy uncounted C search entry point (bal_c_search,
  used only if bal_c_search2 is absent) reports the range
  size as an upper bound, flagged counted=False, as before.
- Benchmark rates on this VM vary widely under the live
  mainnet load; they are reported as measured, with no
  improvement claimed.
