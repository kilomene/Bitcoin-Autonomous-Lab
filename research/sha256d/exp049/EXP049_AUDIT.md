# EXP-049 independent audit (NOVA-ER-0009, register R-35)

Auditor: independent agent, not the EXP-049 author.
Date: 2026-11-16. Host: AMD EPYC 9D25 126-Core Processor
(guest: 4 logical CPUs), the same host as the author's runs.
Scope: the production change mining/bench_mode.py, its
suite tests/test_exp049_bench_mode.py, one Makefile target,
the Gate 4 campaign record, and the three registry updates.
Every claim below was re-derived from primary sources by
the auditor; the author's report was treated as a claim
list, not as evidence.

## Verdict: PASS WITH NOTES. Defects: 0.

The production change is additive, structurally incapable
of network or submission behaviour, correct against
hashlib, and its Gate 4 agreement verdict follows from the
raw campaign data under the predeclared criterion. It may
proceed to the push step. Six notes follow; none blocks
the push, and N-4 names the one formality still open.

## 1. Structural safety: CONFIRMED independently

Auditor's own AST analysis of mining/bench_mode.py (not
the author's test): imports are exactly argparse,
contextlib, hashlib, json, os, statistics, struct, sys,
time, plus gpu.engine. gpu/engine.py itself imports only
ctypes, hashlib, os and time. No banned identifier (socket,
StratumClient, submit, submitblock, connect, endpoint,
getblocktemplate, urllib, and peers) appears in the AST.

Auditor's own fresh-interpreter closure check: after
importing mining.bench_mode, sys.modules contains no
stratum, endpoint, solo, mainnet, autopilot, socket,
urllib or agent module; the socket module is not loaded
at all.

Auditor's own runtime check: a full bench run executed
with socket.socket, socket.create_connection,
socket.getaddrinfo and socket.gethostbyname all replaced
by raisers completed with exit 0 and reported a rate.
The endpoint configuration file .local/mining-endpoint.json
had sha256 d741cde3c6224406f46f3bae138fb174eb1d780725bc
b94baff4e14a8670c7d3 before and after the run, byte
identical: the mode neither reads nor writes it. From the
source, the mode's only file inputs are /proc/cpuinfo,
the cgroup cpu.max files, and the engine's native
libraries; its only write is the caller-named --output
file. The author's strace record (RAW_RESULTS/
strace_network.txt) contains only thread-exit lines and
zero connect/sendto/recvfrom lines, consistent with the
above.

## 2. Live path untouched: CONFIRMED by remote blob comparison

Git blob SHAs compared against remote commit aa4c8917
(the pre-EXP-049 remote state), fetched through the
bal_github helper's read-only API path:

- gpu/engine.py: remote bb9f57902ba23eaf6546575e48a0afd
  39681a054, local identical. MATCH.
- mining/mainnet_live.py: remote 5caa30f75301f50e5a7d76
  c1db2d68d0076434a2, local identical. MATCH.
- mining/bench_mode.py: absent at aa4c8917 (new file, as
  expected).
- Makefile: differs, and the full diff against aa4c8917
  is exactly the test-exp049 target block plus appending
  test-exp049 to test-all. test-all now names 41 targets
  (counted by the auditor), as the author claimed.

Remote HEAD moved during the audit (aa4c8917 to
63383833) because the parallel EXP-047/EXP-048 research
push landed; gpu/engine.py and mining/mainnet_live.py
carry the same blob SHAs at the new HEAD, so that push
did not touch them either. A repo-wide grep confirms
nothing outside the EXP-049 test and research files
references bench_mode: no production module imports it.

## 3. Correctness gates: CONFIRMED with auditor's own code

- make test-exp049, run by the auditor: ALL 20 EXP-049
  BENCH MODE CHECKS PASSED.
- Auditor's own script through the production
  ComputeEngine, using none of bench_mode's code:
  batch_search over the 1,024-nonce span returned 1,024
  candidates and all 1,024 digests matched an independent
  hashlib double SHA-256, byte for byte.
  search_first_counted over the genesis span returned
  nonce 2083236893; its digest equals the genesis block
  hash, equals the hashlib reference digest, and meets
  the genesis target.
- Auditor's own mode runs: output shape confirmed (host
  profile, backend with reason, self-check line, the
  category E label, counted hashes). Counted hashes equal
  repetitions x 262,144 exactly (262,144 at 1 repetition;
  524,288 at 2). RAW_RESULTS/mode_profile.json records
  the same identity for the author's run.

## 4. Gate 4 campaign: verdict CONFIRMED by recomputation

The auditor recomputed everything from
RAW_RESULTS/campaign_sessions.json with independent code.
Stored per-pair log_ratio values match recomputation from
the raw mode and harness rates to 1e-9 on every pair.
Per-session mean log ratios: +0.2267, +0.2135, +0.0942,
identical to the report. Pooled mean log ratio +0.1781
(ratio 1.195), identical. The auditor's own percentile
bootstrap (10,000 resamples, auditor seed 7 in place of
the author's 1049) gives CI95 [-0.0625, +0.4235] against
the author's [-0.0615, +0.4175]; both contain 0, as does
every per-session CI. Under the predeclared criterion
(pooled CI contains 0), AGREEMENT VERIFIED follows.

Honest width, stated as the report states it: in ratio
terms the pooled CI bounds any systematic mode-versus-
harness difference only to roughly -6 percent to +53
percent. The point estimates were positive in all three
sessions and remain unexplained; the data under load
average about 16 cannot resolve anything tighter.

Predeclaration evidence: the campaign manifest
(campaign_sessions.json) records report_sha256_at_start
= 43f639293c79a93da448e42086940adfc224866ffcab641e45a
46f6aeb189fc4, exactly the value the report prints, and
started/finished timestamps 2026-11-16T17:24:54Z to
17:25:02Z matching the report. The agreement criterion
text is embedded verbatim in exp049_campaign.py's header
(lines 8 and 35 to 36), and that script necessarily
predates the sessions file it produced. See note N-1
for the one part the auditor could not re-derive.

## 5. Registries: CONFIRMED

- research/sha256d/experiment_registry.md and
  research/sha256d/extreme_optimization/
  EXPERIMENT_REGISTRY.md each carry an EXP-049 record
  whose figures (pooled +0.178, CI [-0.062, +0.418],
  census 602/8 to 604/8, suite list) agree with the
  report, and each ends with "Next unreserved ID:
  EXP-050."
- research/EXTREME_RESEARCH/EXPERIMENT_REGISTRY.json
  parses; 100 entries; exactly one EXP-049 entry, status
  PROVEN. Entry-by-entry comparison against the same
  file at remote aa4c8917 (97 entries): zero prior
  entries missing, zero prior entries changed; the only
  additions are EXP-047, EXP-048 and EXP-049.

## 6. Suites re-run by the auditor, one at a time

- make test-exp049: PASSED (20 of 20).
- make test-gpu: ALL GPU COMPUTE TESTS PASSED.
- make test-mainnet-live: ALL MAINNET LIVE ACCOUNTING
  TESTS PASSED (including the Stage 6 D9 backend-reason
  checks).
- make test-engine: ALL INTELLIGENCE ENGINE TESTS PASSED.

Full test-all (41 targets) was NOT run by the auditor;
see note N-4.

## 7. Scans

Byte scan by the auditor of all 13 EXP-049 created or
edited files (module, test, Makefile, report, campaign
script, 5 RAW_RESULTS files, both markdown registries,
the JSON registry): U+2014 count 0 in every file. Secret
patterns (xprv/xpub, key headers, WIF-shaped strings,
password/token assignments, RPC credential keys): zero
hits. The single pattern hit anywhere is the word
"mnemonics" at research/sha256d/extreme_optimization/
EXPERIMENT_REGISTRY.md line 1560, in the historical
phrase "vector mnemonics, mask 0xffff agreeing with",
about instruction mnemonics in a pre-EXP-049 record,
roughly 800 lines above the appended EXP-049 record.
Benign and pre-existing, exactly as the author reported.

## 8. Live stack

Never restarted, signalled or reconfigured by the
auditor. Full-log census of evidence/mainnet-live.jsonl:
604 accepted / 8 rejected before the audit, 606 accepted
/ 8 rejected after; the +2 are the live miner's own pool
shares during the audit window. Balance remains 0 BTC;
no block found; the mission success criterion is not met
and nothing in this audit changes that.

## Notes

- N-1 (evidence strength, Gate 4 predeclaration): no
  prefix of the delivered EXP049_REPORT.md hashes to
  the manifest's report_sha256_at_start, so the exact
  pre-campaign report bytes cannot be re-derived from
  what was delivered (the results sections were written
  into the file after the run, and not as a pure append
  at a prefix boundary the auditor could find). The
  predeclaration therefore rests on the campaign
  script's own header text, the manifest's recorded sha
  matching the report's printed value, and consistent
  timestamps and mtimes. That is adequate evidence, but
  it is weaker than a re-derivable hash, and future
  campaigns should preserve the pre-campaign report as a
  separate file so the sha can be checked byte for byte.
- N-2 (effective-CPU estimate is contention-sensitive):
  the scaling-ratio estimate printed by the mode was
  0.50 in the author's recorded profile (2-thread rate
  below the 1-thread rate), 0.84 in one auditor run and
  1.60 in another, all on this host, against EXP-031's
  standing estimate of about 2. The figure is labelled
  an estimate with its method everywhere it appears and
  no claim in the report depends on a specific value,
  but a single run's figure under load can fall below 1
  and should not be quoted as a host constant.
- N-3 (Gate 4 width): the agreement verdict is a
  statement at the CI width in section 4 (roughly -6 to
  +53 percent in ratio terms), not a tight equivalence.
  The report says this plainly; any future citation of
  EXP-049 must carry the width with it.
- N-4 (test-all not run): with load average about 16
  from concurrent programme work, a 41-target run would
  mix genuine results with contention artifacts, and two
  targets carry documented environment failures on this
  VM (test-rtl: iverilog absent; test-autopilot: the
  empty-lock skip precondition while the live stack is
  up). The auditor ran the four suites covering the
  change surface instead. A full test-all for this tree
  state remains outstanding since the Stage 8 audit run
  (39 of 40 there) and should be picked up in a quieter
  window; it is not a defect in this change.
- N-5 (duplicated label mapping): bench_mode.py
  reimplements mainnet_live.py's backend label/reason
  mapping in miniature, deliberately, to keep the
  structural property. The mirror-image of Stage 6 audit
  note N-2 applies: a future new engine backend must
  extend BOTH mappings in the same change, or the bench
  mode will mislabel it "pure Python" (a display defect
  only; rates and digests are unaffected).
- N-6 (thread probe variance): the engine's auto-tune
  resolved 2, 4 and 8 threads across runs on this host
  during the audit window. This is inherited production
  probe behaviour under contention, not introduced by
  the mode; the gates prove digests and counted hashes
  are unaffected, only rates move.

## UNVERIFIED register (auditor concurs with the author's list, plus N-4)

- The Intel Xeon Platinum 8321HC host: the mode has not
  run there; its tier selection and figures on that host
  are unmeasured until a rotation.
- A literal fresh VM replacement run of the mode: Gate 5
  was a clean-environment simulation.
- CUDA hosts: no GPU exists here; the CUDA branch is the
  production engine's own dispatch, unexercised.
- The mode under the Prompt 1 OS sandbox: not run.
- Gate 4 agreement tighter than the section 4 CI width
  under quiet conditions: not measured.
- Full test-all (41 targets) on this tree state: not run
  by author or auditor (note N-4).

## Bottom line

EXP-049's claims survive independent verification on
every point the auditor could re-derive, and the single
point that could not be re-derived byte for byte (N-1)
is corroborated by two independent artifacts. Defects:
0. Verdict: PASS WITH NOTES. The change is cleared for
the push step, with N-4's test-all formality carried as
an open item for a quieter window.
