# Test Report: Master Build

Date: 2026-11-15. Full-suite run for the Master Build Mandate
deliverables. Complete raw output:
research/master_build/TEST_ALL_RUN_2026-11-15.txt (the file
contains the make test-all run, a continuation section explained
below, and the single permitted rerun, each clearly delimited).

## Host and conditions

- CPU, from /proc/cpuinfo: AMD EPYC 9D25 126-Core Processor (the
  AMD host of the alternating pair; the lab's other host is an
  Intel Xeon Platinum 8321HC).
- 4 logical CPUs visible; about 2 effective CPUs by the EXP-031
  characterisation. About 7,934 MB RAM.
- The live mainnet miner, autopilot and pruned mainnet node ran
  throughout, as they always do on this VM; every figure here is
  a contended-VM result.
- The regtest node was used only by the test suites themselves,
  exactly as the suites already do.

## How the run went, stated exactly

`make test-all` was run once, sequentially, with output captured
to the file above. Make runs its 36 prerequisites in Makefile
order and stops at the first failing one. The run passed 11
targets, reached test-rtl, which failed for the known
environmental reason (iverilog absent, see below), and make
halted with exit 2. The remaining 24 targets were then run
individually, sequentially, in Makefile order, appended to the
same capture file under a continuation header, so that every one
of the 36 targets has a recorded result from today. One target
(test-task0039) failed its first run and was rerun once, as
permitted, to separate flake from defect; both outcomes are
recorded below and in the capture file.

## Per-target results

| # | Target | Result | Banner or failure, transcribed |
|---|---|---|---|
| 1 | test | PASSED | ALL TESTS PASSED |
| 2 | test-regtest | PASSED | ALL REGTEST TESTS PASSED |
| 3 | test-engine | PASSED | ALL INTELLIGENCE ENGINE TESTS PASSED |
| 4 | test-pow | PASSED | ALL POW ENGINE TESTS PASSED |
| 5 | test-gpu | PASSED | ALL GPU COMPUTE TESTS PASSED |
| 6 | test-gpu-correction | PASSED | ALL GPU CORRECTION TESTS PASSED |
| 7 | test-mining | PASSED | ALL MINING ENGINE TESTS PASSED |
| 8 | test-adversarial | PASSED | ALL ADVERSARIAL TESTS PASSED |
| 9 | test-deepening | PASSED | ALL DEEPENING TESTS PASSED |
| 10 | test-cpu | PASSED | ALL CPU ASPECT TESTS PASSED |
| 11 | test-cpu-correction | PASSED | ALL CPU CORRECTION TESTS PASSED |
| 12 | test-rtl | FAILED (environmental) | AssertionError: /bin/sh: 1: iverilog: not found |
| 13 | test-solo | PASSED | ALL SOLO SERVER TESTS PASSED |
| 14 | test-solo-cutover | PASSED | ALL SOLO CUTOVER TESTS PASSED |
| 15 | test-research | PASSED | ALL RESEARCH TESTS PASSED |
| 16 | test-autopilot | PASSED | ALL AUTOPILOT TESTS PASSED |
| 17 | test-judgement | PASSED | ALL JUDGEMENT TESTS PASSED |
| 18 | test-installer | PASSED | ALL INSTALLER TESTS PASSED |
| 19 | test-task003 | PASSED | ALL TASK 003 CORRECTION TESTS PASSED (regtest block at height 1473) |
| 20 | test-task0038 | PASSED | ALL TASK 003.8 TESTS PASSED (regtest block at height 1474) |
| 21 | test-task0039 | FAILED first run, PASSED on rerun | See failure notes |
| 22 | test-avx512 | PASSED | ALL AVX512 INTEGRATION TESTS PASSED |
| 23 | test-avx512dual | PASSED | ALL AVX512 DUAL INTEGRATION TESTS PASSED |
| 24 | test-mainnet-live | PASSED | ALL MAINNET LIVE ACCOUNTING TESTS PASSED |
| 25 | test-template-cache | PASSED | ALL TEMPLATE CACHE TESTS PASSED |
| 26 | test-avx512flags | PASSED | ALL AVX512 FLAGS INTEGRATION TESTS PASSED |
| 27 | test-exp036 | PASSED | ALL EXP-036 VERIFICATION TESTS PASSED |
| 28 | test-exp034 | PASSED | ALL EXP-034 JOB AND TEMPLATE TESTS PASSED |
| 29 | test-exp037 | PASSED | ALL EXP-037 STATISTICS TESTS PASSED |
| 30 | test-exp038 | PASSED | ALL EXP-038 CHECKPOINT TESTS PASSED |
| 31 | test-probability | PASSED | ALL PROBABILITY PERCENTILE TESTS PASSED (73 checks) |
| 32 | test-exp039 | PASSED | EXP-039 fallback integration suite: ALL PASSED |
| 33 | test-exp040 | PASSED | ALL EXP-040 CATEGORY F TESTS PASSED |
| 34 | test-agent-intelligence | PASSED | ALL AGENT INTELLIGENCE TESTS PASSED (86 checks) |
| 35 | test-agent-awareness | PASSED | ALL AGENT AWARENESS TESTS PASSED (51 checks) |
| 36 | test-agent-operations | PASSED | ALL AGENT OPERATIONS TESTS PASSED (10306 checks) |

Total: 35 of 36 targets pass. The single failing target is
environmental.

## Failure notes

test-rtl (target 12): FAILED, environmental. The suite shells
out to iverilog, which is absent on this VM (it disappears on VM
replacements and has not been reinstalled). Exact failure, from
the capture: the RTL test's assertion tripped on the subprocess
output "/bin/sh: 1: iverilog: not found", and make reported
"Makefile:42: test-rtl Error 1". This is the standing environment
failure recorded across the programme; it is not a code defect
and no RTL code changed in this build. It is also the reason
make halted: the remaining targets were completed by the
continuation described above.

test-task0039 (target 21): FAILED on its first run today, PASSED
in full on the single permitted rerun. First-run failure, from
the capture: tests/test_task0039_accounting.py,
test_early_exit_accounting, line 290: `assert attempted <
100000 // 10, attempted` raised AssertionError with attempted =
11149, that is, the early-exit search attempted 11,149 hashes
against a threshold of 10,000 (10 percent of the 100,000
requested). Every earlier check in the suite had passed,
including the other accounting exactness checks. The rerun
passed the whole suite (banner: ALL TASK 003.9 TESTS PASSED,
regtest block at height 1492), including the same early-exit
check, which there reports the attempted count as far below the
100,000 requested. Verdict: a borderline, contention-sensitive
threshold in a pre-existing suite (the first run executed while
the continuation loop and the live miner were loading the same
capped guest), not a defect in the new agent layer and not a
defect introduced by this build; no code was changed in this
task, per its rules. The threshold margin (11,149 against
10,000) is recorded here so a future owner of that suite can
decide whether the assertion wants a wider bound.

No other target failed. In particular, all three new agent-layer
suites passed, so no defect in the new agent layer appeared in
this run.

## One transcription note

The Milestone 2 report records the awareness suite as 50 checks;
today's run prints 51 checks for test-agent-awareness. The suite
gained a check at some point after that report was written (or
the earlier count was taken before a final check was added);
the discrepancy is in the milestone report's count, not in
today's banner, which is transcribed above as printed.
