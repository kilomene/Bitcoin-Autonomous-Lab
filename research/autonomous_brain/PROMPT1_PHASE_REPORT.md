# Prompt 1 Phase Report: Security, Evidence and Experiment Isolation

Directive 4 (NOVA SHA-X Autonomous Mining Brain), Prompt 1, Critical.
Phase status: COMPLETE. Independent audit FAIL, defect fixed,
independent re-audit PASS WITH NOTES, owed regression rerun
completed clean. This report closes the phase.

## HEAD

Remote main HEAD at phase start and at the time of writing:
18ff4eb070a066dec4424cf9cd4d8282fa9a38b3. This report ships in
the phase push together with the full Prompt 1 file set, the
D1 documentation fix, and the Stage 0 reconciliation artifacts
of the Extreme Research mandate.

## Files inspected

- agent/intelligence/loop.py, experiments.py, permissions.py,
  audit.py, interface.py, __init__.py (Master Build agent layer)
- tests/test_agent_intelligence.py, tests/test_agent_operations.py
- docs/AGENT_CAPABILITIES.md, Makefile
- The mandate record, including the parent pre-change
  verification of the defects in the shipped Master Build code.

## Files created

- agent/intelligence/verifier.py: independent verifier service,
  runnable as a module, JSON request on stdin, signed record on
  stdout.
- agent/intelligence/sandbox.py: operating-system level
  experimental sandbox (rewritten once after audit defect D-1).
- tests/test_agent_security.py: adversarial suite for the phase.
- research/autonomous_brain/PROMPT1_SECURITY_REPORT.md: build
  report, with an appended dated FIX section.
- research/autonomous_brain/PROMPT1_SECURITY_AUDIT.md: first
  independent audit (auditor-authored, verdict FAIL).
- research/autonomous_brain/PROMPT1_SECURITY_REAUDIT.md:
  independent re-audit of the fix (auditor-authored, verdict
  PASS WITH NOTES).
- research/autonomous_brain/PROMPT1_PHASE_REPORT.md: this report.

## Files modified

- agent/intelligence/loop.py: strict evidence schema replaces
  truthiness checks; HMAC signature verification at the
  integrate gate; bundle artifact and source-commit binding
  with optional expected binding; EXP-017 statistical
  validation rejects NaN, infinite values, inverted confidence
  intervals and non-integer session counts.
- agent/intelligence/experiments.py: run_command rewired
  through the sandbox; strict evidence assembly; append-only
  hash-chained evidence ledger under
  .local/agent-evidence/<experiment_id>.jsonl with
  CURRENT_SOURCE_COMMIT (18ff4eb0) bound into every record;
  HMAC-signed ledger anchor added by the fix.
- agent/intelligence/permissions.py: every ActionSpec carries
  a kind (operational for L1 and L2, experimental for L3) and
  shell=False; assert_no_shell_payload guard added.
- agent/intelligence/interface.py: payload guard applied on
  inspect_status.
- agent/intelligence/__init__.py: Agent wires the verifier key
  path (.local/verifier/verifier.key) into the loop.
- tests/test_agent_intelligence.py and
  tests/test_agent_operations.py: fixtures migrated to strict
  signed evidence records and the real verifier service. The
  gate was not weakened to make the fixtures pass.
- Makefile: test-agent-security target added; test-all now
  has 37 targets.
- docs/AGENT_CAPABILITIES.md: dated correction of the
  evidence-trust limitation that Prompt 1 removed.
- README.md and docs/EVIDENCE.md: D1 documentation drift
  fixed at phase close-out (test-all count 36 corrected to
  37 in four places, counted from the Makefile itself).

## Components reused

- The Master Build agent/intelligence package as shipped:
  permission registry, append-only audit log, optimisation
  loop state machine, ExperimentRunner, MiningInterface and
  the Agent facade. Prompt 1 hardened these in place; it
  built no parallel structure.
- hashlib as the trusted SHA-256d differential reference
  inside the verifier.
- Host isolation primitives measured before building:
  systemd-run scopes, unshare namespaces, pivot_root,
  rlimits, and a runner-side watchdog.
- The repository push helper (bal_github.py) and the
  scoped-driver push pattern used by every previous phase.

## Security changes

1. Strict evidence schema. An evidence item passes only as a
   dict with passed exactly Boolean True (the string "true",
   the integer 1 and bare truthy values are refused),
   verifier_id a non-empty string, artifact_sha256 a 64
   character lowercase hex string, source_commit a non-empty
   string, verification_method in a closed allowlist
   (differential_reference, independent_recompute,
   statistical_replication, chain_acceptance) and an
   ISO-8601 parseable timestamp. Missing fields fail closed.
   The pre-fix gate accepted {"result": "false"} as a pass.
2. Independent verifier service. The Agent spawns the
   verifier as a separate process. The verifier recomputes
   the artifact SHA-256 itself, re-runs any declared
   differential command itself inside the sandbox, checks
   test vectors against the hashlib SHA-256d reference, and
   emits the strict record plus an HMAC-SHA256 signature over
   the canonical JSON of the other fields. The key lives at
   .local/verifier/verifier.key, created on first use, mode
   0600, never printed. Self-verification is refused by the
   author check before signature validation.
3. Experimental sandbox. Experiment commands run as argv
   lists, never shell strings, inside a private root built
   on tmpfs and entered by pivot_root: only a read-only /usr
   bind, a read-only /etc bind, a fresh procfs for the new
   pid namespace (mount failure is fatal), a minimal /dev, a
   tmpfs /tmp, a read-only /source snapshot of the repository
   with an empty .local, and the experiment directory at
   /work as the only writable persistent location. The
   payload runs as uid and gid 65534 after setgroups,
   setgid and setuid, with rlimits applied first. Network is
   fully blocked, the environment is scrubbed, and a
   runner-side watchdog polling every 0.2 s enforces the
   memory and task caps that cgroups cannot enforce on this
   VM. Timeout deadlines latch from payload start, with a
   separate construction grace, and termination takes the
   whole process tree.
4. Ledger anchor. Every ledger append atomically rewrites
   .local/agent-evidence/<id>.anchor.json with the
   experiment id, record count and last record hash,
   HMAC-signed with the verifier key. verify_ledger requires
   the anchor to exist, be correctly signed, and agree on
   count and head hash. Tail truncation, which the first
   audit showed was undetected, is now detected; pre-fix
   ledgers without an anchor fail verification, intended
   fail-closed behaviour.
5. Operational and experimental separation. All 22
   ActionSpecs carry kind and shell=False (19 operational,
   3 experimental at audit time). Shell-shaped payloads are
   refused through the MiningInterface in dict and object
   forms.

## Capabilities gained

- The integrate gate can no longer be passed by
  self-authored, unsigned, malformed or statistically
  invalid evidence.
- Experiment code executes with operating-system level
  confinement: it cannot write host paths, read host secrets,
  see host processes, reach the network, or survive its
  timeout as a detached grandchild.
- Experiment evidence is tamper-evident end to end: hash
  chain inside the ledger, signed external anchor outside
  it, artifact hash and source commit bound into every
  record and every verifier signature.
- The phase produced a reusable adversarial suite
  (tests/test_agent_security.py) that pins every acceptance
  item individually.

## Operations actually connected

None to production. Prompt 1 deliberately grants no
production authority: the MiningInterface start and stop
operations still raise NotImplementedError without an
injected controller, exactly as shipped in the Master Build.
The connections made are internal to the agent layer: the
Agent loop calls the verifier service as a subprocess, and
ExperimentRunner.run_command routes through the sandbox.
The live miner, autopilot and node were never touched by
this phase; both audits verified process identity before
and after their runs.

## Experiments run

No mining or performance experiments. Prompt 1 ran only
security acceptance probes: the build suite, the first
audit's escape attempts (which produced defect D-1), the
fix smoke tests (gcc compile and run inside the sandbox, a
hashlib SHA-256d differential inside the sandbox matching
the host reference byte for byte), and the re-audit's replay
of every first-audit escape plus new angles (17 read path
constructions, mount and nested unshare attempts, ledger
tamper cases, timeout measurement).

## Test results

Build end, sequential: test-agent-security 91 checks ALL
PASSED; test-agent-intelligence 86 PASSED;
test-agent-awareness 51 PASSED; test-agent-operations
10,309 PASSED.

After the D-1 fix, sequential: test-agent-security 112
checks ALL PASSED; test-agent-intelligence 86 PASSED;
test-agent-operations 10,309 PASSED; test-agent-awareness
PASSED at the conditional count (below).

Owed clean rerun (the re-audit's own rerun was destroyed by
the VM-wide exec write block that began about 03:02 UTC on
2026-11-16; see audit results). Completed clean and
sequential on AMD EPYC 9D25 after the block cleared:
test-agent-security 112 checks ALL PASSED (312 s);
test-agent-operations 10,309 checks ALL PASSED (70 s,
including the 240-trial resources campaign);
test-agent-awareness 50 checks ALL PASSED (32 s). The
awareness count is 50 rather than 51 because the node RPC
timed out during that run, the standing
initial-block-download under load pattern on this VM, so
the conditional blocks <= headers check did not run; the
suite has 49 unconditional checks plus one for heartbeat
age (ran) plus that one conditional check. test-agent-
intelligence passed 86 checks in the build and both audit
runs and was not part of the owed rerun.

## Audit results

First independent audit (non-author agent): verdict FAIL.
One critical defect, D-1: the original sandbox overmounted
only enumerated paths, left the rest of the host filesystem
mounted with host permissions, and ran the payload as uid
0. The auditor proved writes to /etc, /home/hatch and
/usr/local/share (host-side marker files, all verified
present, then deleted; host left clean), reads of
/etc/shadow and host files, and host /proc visibility. The
author's suite had missed the escape because its write
tests exercised only covered paths. Everything else was
confirmed: evidence gate strictness (26 of 26 refusals,
plus a valid bundle passing only with a genuine verifier
HMAC record), forgery and self-verification refusal,
network and environment isolation, detached-grandchild
containment, hog kills, probe-failure refusal with no
fallback, the cgroup non-enforcement claim (independently
reproduced), operational and experimental separation, and
production integrity. One correction: ledger tail
truncation was NOT detected.

Fix: sandbox rebuilt on a private pivot_root with the
payload at uid 65534, fatal procfs mount failure, and the
HMAC-signed ledger anchor. Two kernel orderings measured
and load-bearing: procfs mounts after the pivot but before
the old-root detach, and the detach uses the raw umount2
syscall. A nested user namespace was built first and
rejected on measurement: this kernel refuses fresh procfs
mounts from inside it because the inherited runtime /proc
carries locked masked submounts; the payload instead runs
inside the runtime's own user namespace, so uid 65534 is a
real unprivileged host uid.

Independent re-audit (non-author agent): verdict PASS WITH
NOTES. Every first-audit escape replayed through the real
run_command and refused, verified host-side; /source byte
scanned for fragments of the RPC password, wallet private
key and WIF with no hits; /proc confined to the payload's
own namespace; payload CapEff 0 and NoNewPrivs 1; ledger
anchor tamper cases all detected; a 5 s payload deadline
measured 5.02 s of payload lifetime. Notes: N-1, the
regression rerun was still owed (the auditor's security
run failed at one check under self-introduced concurrency,
and the write block then killed the operations and
awareness runs before any check); discharged by the clean
rerun recorded above. N-2, CapBnd inside the payload is a
full bounding set while CapEff is 0; no capability is
effective and setuid back to 0 is refused, recorded for
precision. N-3, one append refusal returned EACCES rather
than EROFS; immaterial. N-4, ledger truncation to zero
records is caught by the empty-ledger check rather than
the anchor comparison; still fails closed. N-5, sandbox
construction cost under contention (carried into
limitations).

## Performance measurements

None claimed by Prompt 1. The phase changed no production
code path, ran no benchmark, and measured no hash rate.
The only timings recorded are test wall times (above) and
the sandbox construction latency (limitations, below).

## Limitations

- Cgroup limits do not enforce on this VM, measured twice
  (build and first audit): about 4 GB allocated under
  MemoryMax=128M and 20 tasks run under TasksMax=6, because
  this VM's processes sit in a cgroup namespace with no
  scope sub-cgroups. Sandbox memory and task enforcement
  therefore rests on rlimits plus the 0.2 s watchdog;
  CPUQuota enforcement could not be confirmed or refuted
  under this VM's contention and is not claimed. The scope
  properties remain applied for hosts with a normal
  hierarchy.
- Sandbox construction costs tens of seconds per run under
  contention (the re-audit measured about 43 s of
  construction and probe overhead on one contended run;
  the build measured 13 to 20 s). Deadlines are measured
  from payload start, so this is latency, not correctness.
- The payload can still see the read-only /usr runtime
  tree, the read-only /etc runtime configuration (files
  unreadable by uid 65534, such as /etc/shadow, stay
  unreadable), the read-only /source snapshot with an empty
  .local, its own /work, and a /proc containing only its
  own pid namespace.
- Single-host HMAC separation: the verifier's independence
  rests on process separation plus the sandbox hiding the
  key. Platform code outside the sandbox can read the key,
  because it must verify signatures. The threat model
  covered is experiment code inside the sandbox, which is
  the boundary this phase specifies.
- The watchdog polls every 0.2 s, so a very fast
  allocation spike can overshoot the memory cap briefly
  before the kill; RLIMIT_AS bounds the worst case.
- Prompt 1 grants no production authority. There is still
  no production MiningController; start and stop are not
  wired to the autopilot. That is Prompts 2 onward, now
  Stages 6 to 9 of the Extreme Research mandate.

## Remaining work

Prompt 1 itself has no remaining items: the audit defect
is fixed and re-audited, the owed rerun is complete, the
D1 documentation drift is fixed, and this report and the
phase file set are pushed with two-way verification.
Standing items outside this phase: the EXP-039 tier
refusal check on a SHA-less host (unexecuted, probe
construction only), and the CapBnd tightening noted by
the re-audit as optional future hardening.

## Next phase

Prompt 2: operational control and the production sandbox.
Build the real MiningController by extending
mining/autopilot.py (never a competing controller), with
typed inspect, start, stop, restart, select_backend,
adjust_workers, refresh_job, checkpoint, recover and
status operations that invoke real production operations
and verify their results, behind the permission tiers and
pre-action safety checks the mandate specifies. Under the
Extreme Research mandate this work sits in Stages 6 to 9;
Prompt 1's sandbox, verifier and ledger are the isolation
and evidence layer those stages build on.
