# Prompt 1 Independent Security Audit: Security Hardening, Evidence Integrity and Experiment Sandbox

Auditor: independent non-author agent (adversarial verification, own probes).
Date: 2026-11-15 (work executed 2026-11-16 02:10 to 02:21 UTC).
Build under audit: research/autonomous_brain/PROMPT1_SECURITY_REPORT.md.
Remote HEAD confirmed live before and during the audit:
18ff4eb070a066dec4424cf9cd4d8282fa9a38b3. Nothing was pushed.
Nothing was restarted by this audit (see section 8 for a VM
replacement event that interrupted the miner independently).

## Verdict: FAIL

One core acceptance property of Prompt 1 is refuted by direct
measurement: the experimental sandbox does NOT confine writes
(or reads) to the sandbox outside a small enumerated set of
paths. Sandboxed code, running as uid 0, wrote files onto the
real host filesystem at /etc, /usr/local/share and the user
home directory, and read /etc/shadow. Defect D-1 below gives
the exact reproduction. All other audited claims are confirmed
or corrected as itemised; the evidence gate, the verifier
signature scheme, the resource caps, the cgroup honesty, the
regression suites and production integrity all held under
independent probing. Prompt 2 production authority should not
proceed until D-1 is fixed and re-audited, per the mandate's
own completion requirement.

## Defect D-1 (critical): sandbox filesystem isolation covers only enumerated paths; the rest of the host filesystem is read/write

Location: agent/intelligence/sandbox.py, the _LAUNCHER script
(lines 97 to 116). The launcher overmounts only: the sandbox
work dir (bind to /mnt/work), /tmp (tmpfs), repo .local (tmpfs),
the lab secrets dir (tmpfs), ~/.ssh (tmpfs), and the repository
root (read-only recursive bind). Every other host path keeps
its normal host mount and normal host permissions. The agent
runs as root on this VM and unshare --map-root-user maps the
inner uid 0 to the host caller, so sandboxed code executes
with effective root-equivalent access to all uncovered paths.

Reproduction (auditor's own probe, via ExperimentRunner
run_command, python3 -c payloads, 2026-11-16 about 02:12 UTC):

- Write to /etc/audit-pwn from inside the sandbox: reported
  WROTE inside; the file existed ON THE HOST afterwards
  (6 bytes, content PWNED, root-owned).
- Writes to /home/hatch/audit-escape-home.txt, /etc/audit-pwn2
  and /usr/local/share/audit-pwn3.txt: all landed on the host.
- Write through a symlink created inside the sandbox pointing
  at /etc/audit-pwn4: landed on the host.
- Reads from inside the sandbox: /etc/shadow readable
  (486 bytes read), /home/hatch/MEMORY.md readable
  (67,711 bytes), /home/hatch/workspace/bin/bal_github.py
  readable. uid/euid inside the sandbox: 0/0.
- Host /proc is visible inside the sandbox: the launcher's
  proc mount (mount -t proc proc /proc, guarded by
  "2>/dev/null || true", so its failure is silent) does not
  take effect, and the auditor enumerated the host autopilot
  (pid 3745), miner (pid 3758) and bitcoind (pid 4270)
  cmdlines from inside the sandbox. Signalling those pids
  from inside failed (the pid namespace still isolates
  signals; kill returned No such process), so this sub-item
  is information disclosure, not process control.

All five host files created by this probe were deleted by the
auditor after capture; the host was left clean.

What DID hold in the same probes (the enumerated set):
production repo files are genuinely read-only (append to
mining/engine.py and to agent/intelligence/loop.py failed
with Errno 30 Read-only file system; engine.py SHA-256
identical before and after, f45feb51fdaaa8ba0385918757268ce
44ad61c040550057f25323eb8652862f7); writes to host /tmp paths
landed only in the namespace tmpfs (host path never appeared,
including through symlinks, because /tmp itself is covered);
the node bitcoin.conf, the lab wallet secrets file, the SSH
private key and config, and the verifier key all read as
blocked (FileNotFoundError under the tmpfs cover), directory
listings of .local, the secrets dir and ~/.ssh returned
empty, and target_path() refuses symlink and parent-traversal
escapes at the runner API level.

Why the author's suite missed it: tests/test_agent_security.py
item 6 exercises only a /tmp marker (a covered path) and item 9
only a repo file (a covered path). No test writes to an
uncovered absolute path.

Fix direction (for the builder, not applied by this audit):
build the sandbox on a private root (for example a tmpfs root
with pivot_root or an equivalent minimal bind set: /usr, /lib,
/bin and the work dir only), or bind-mount the whole of /
read-only before applying the writable work bind, overmount
/etc, /home and /usr/local as well, run the payload as a
mapped non-root uid, and make the /proc mount failure fatal
instead of "|| true". Then add acceptance tests that write to
/etc, the home directory and a sibling workspace path and
verify on the host that nothing appeared.

Claims corrected by D-1: the report's statements that the
experiment directory is "the only writable work location" and
acceptance item 6 ("an experiment cannot write outside its
sandbox") are REFUTED in their general form. They hold only
for the enumerated paths.

## 1. Evidence gate strictness: CONFIRMED

Auditor's own probe (/tmp/audit_probe1.py) against
agent.intelligence.loop.validate_integrate_evidence, with the
independent record obtained through the real verifier process
(verifier.request_verification spawning
python3 -m agent.intelligence.verifier) over an artifact the
auditor created (SHA-256 c6cfbb0a740058093042a48438d2cc1f6fc
60dc843d3db092b300713ae19465c). The fully valid bundle passed
(missing list empty). Every one of the following was refused
with the named reason:

- {"result": "false"} as the correctness item.
- passed = "true" (string), passed = 1 (int), the bare Boolean
  True as a record, the string "true" as a record, the int 1
  as a record, passed = False.
- EXP-017 verdict: NaN pooled ratio, +inf pooled ratio, +inf
  CI bound, -inf CI bound, NaN CI bound, inverted CI
  (0.58 low, 0.24 high), ci_low = 0, pooled_ratio = 1.0.
- sessions = 2, sessions = 3.0 (float), sessions = "3"
  (string), sessions = True (bool).
- Unknown verification_method ("self_attestation").
- Missing artifact_sha256; uppercase artifact hash; 63-char
  and 65-char artifact hashes.
- Non-ISO timestamps ("not-a-date", "2026-13-45T99:99:99Z").

26 of 26 refusal cases refused; the valid bundle and a
restored valid bundle both passed. One design observation,
matching the report's own description: only the independent
verification record is signature-checked; correctness and
differential records are schema-validated but unsigned, so
their strength rests on bundle binding to the signed record's
artifact and commit. Recorded as a note, not a defect.

## 2. Forgery and self-verification: CONFIRMED

Auditor's probe (/tmp/audit_probe2.py), same genuine signed
record as section 1:

- Record signed with a DIFFERENT key (auditor-generated key
  file): refused, "signature invalid or missing".
- Genuine record mutated one field at a time, each refused:
  passed (to False), artifact_sha256 (to a different valid
  hash, with the rest of the bundle re-aligned so only the
  signature could fail), source_commit, verifier_id,
  timestamp, verification_method (to another allowlisted
  method), detail, signature itself (to zeroes), signature
  deleted, and an extra field appended after signing.
- Self-verification: a record whose verifier_id equals the
  implementation author is refused with "independent
  verification by an author other than the implementation
  author", BOTH when signed with the real verifier key and
  when signed with another key (the author check fires before
  the signature check in loop.py). The implementation author
  cannot self-verify through this gate.
- The verifier service itself refuses an unknown method with
  an unsigned error record, and signs a passed=False record
  for a wrong differential test vector, which the gate then
  refuses.

## 3. Sandbox escapes (auditor's own attempts): MIXED, see D-1

- (a) Secret reads: CONFIRMED blocked for the enumerated
  credential paths (bitcoin.conf, lab wallet file, SSH key
  and config, verifier key; listings empty). REFUTED for
  non-enumerated paths: /etc/shadow and other host files are
  readable (part of D-1).
- (b) Writes: CONFIRMED blocked for repo files and host /tmp
  (namespace tmpfs), including through symlinks created
  inside the sandbox and a symlink pre-planted on the host
  inside the sandbox dir. REFUTED for uncovered paths
  (/etc, home, /usr/local/share, symlink to /etc): D-1.
- (c) Environment leakage: CONFIRMED. A marker variable
  (AUDIT_MARKER_SECRET) set in the parent environment was
  absent inside the sandbox. The inside environment contains
  only the allowlist plus BAL_* rlimit variables and a
  systemd INVOCATION_ID; no secret material.
- (d) Network: CONFIRMED blocked, stronger than claimed. TCP
  connects to 1.1.1.1:53, 8.8.8.8:53 and 93.184.216.34:80 all
  failed (Errno 101 Network unreachable), DNS resolution
  failed, and even loopback to 127.0.0.1:8332 failed (loopback
  is down in the namespace).
- (e) Detached grandchild: CONFIRMED contained. A parent that
  spawned a setsid (start_new_session) grandchild writing
  heartbeats every 0.2 s was timed out at 3 s; heartbeat count
  was identical immediately after and 2 s later (12 and 12).
  The pid namespace plus scope stop contains even a fully
  detached grandchild on this host; no escape found here.
- (f) Hogs: CONFIRMED with one nuance. Memory hog under a
  128M cap: killed with reason "memory" in 1.30 s. Task hog
  with 60 small sleep children under tasks_max=16 and a 4G
  memory cap: killed with reason "tasks" in 0.85 s. A fork
  hog using full Python children under default caps tripped
  "memory" before "tasks" (each Python child carries real
  RSS; whichever cap trips first is the recorded reason).
  Termination reasons are recorded in every case.
- (g) Refusal when isolation is unavailable: CONFIRMED two
  ways. The author's mechanism is the cached probe result
  (sandbox._probe_cache); forcing it to (False, ...) makes
  run_command raise SandboxUnavailable and nothing runs.
  Independently, in a fresh subprocess with PATH set to a
  nonexistent directory, probe_isolation() returned
  (False, "unshare missing; systemd-run missing; mount
  missing") and run_sandboxed raised SandboxUnavailable.
  There is no unsandboxed fallback.

## 4. Cgroup claim: CONFIRMED

The author's statement that systemd scope MemoryMax and
TasksMax do not enforce on this VM is independently
reproduced:

- /proc/self/cgroup reads exactly "0::/" and
  /sys/fs/cgroup/system.slice does not exist.
- Raw systemd-run scope with MemoryMax=128M: a Python process
  allocated and touched the full 4 GB in 256 MB steps and
  exited 0.
- Raw systemd-run scope with TasksMax=6: 20 sleep processes
  spawned and lived.
- RLIMIT_CPU: the mechanism fires on this kernel. Inside the
  sandbox, a child run under a self-imposed RLIMIT_CPU of 2 s
  died by signal 24 (SIGXCPU, returncode -24). Precision
  note: in the shipped wiring the prelude sets RLIMIT_CPU to
  timeout_s + 5, so for a plain CPU hog through run_command
  the runner's wall-clock timeout fires first and the recorded
  reason is "timeout" (the author's own test 11b records
  exactly that). RLIMIT_CPU is a backstop, not the observed
  killer on that path. The report's enforcement summary
  (rlimits plus the 0.2 s watchdog) is accurate; the sandbox
  docstring phrase "RLIMIT_CPU killed by the kernel" is true
  of the mechanism but not of the run_command path.

## 5. Evidence ledger: CONFIRMED with one correction

Auditor's probes (/tmp/audit_ledger.py, /tmp/audit_ledger2.py)
through ExperimentRunner on a fresh experiment:

- Ledger lives at .local/agent-evidence/<id>.jsonl (under the
  agent local_dir), outside the writable sandbox. Creation
  and run records carry CURRENT_SOURCE_COMMIT
  (18ff4eb070a066dec4424cf9cd4d8282fa9a38b3, matching remote
  HEAD), compiler version (gcc 13.3.0), machine profile
  (AMD EPYC 9D25), execution config, raw output hashes and
  sandbox file hashes. verify_ledger passes on the genuine
  ledger.
- Detected tampering: editing one hash character, editing a
  kind field, a single byte flip mid-file, reordering two
  lines, deleting a MIDDLE line, truncating a line
  mid-content (invalid JSON), and appending a forged line.
- NOT detected: deleting whole TAIL records. A 3-record
  ledger truncated to its first 2 records verifies as
  "2 records, chain intact", and a 2-record ledger truncated
  to 1 likewise passes. A hash chain without an external
  anchor or expected count cannot detect tail rollback. The
  report's unqualified claim that verify_ledger "reports
  tampering, truncation or reordering" is therefore
  CORRECTED: truncation of the final records is undetectable
  by this verifier. Severity is bounded by the threat model
  (the ledger sits in .local, which the sandbox hides; the
  writer would need host platform access), but the claim as
  written overstates the guarantee. A fix would anchor the
  chain head externally (for example in the audit log).

## 6. Operational / experimental separation: CONFIRMED

- Runtime check: ACTION_REGISTRY holds 22 specs; every spec
  carries kind and shell; shell is False for all 22; the 11
  L1 and 8 L2 specs are kind=operational, the 3 L3 specs are
  kind=experimental.
- Payload guard: assert_no_shell_payload refuses each of
  command, argv, shell, code, script, cmd, exec, executable
  and args, in both dict and attribute-object payload forms,
  and MiningInterface.inspect_status refuses a dict payload
  carrying a command field. Request dataclasses reject extra
  fields with TypeError. Observation only: the guard is
  case-sensitive ("Command" is not refused), but no interface
  method consumes payload fields, so no execution path is
  reachable through it.
- Subprocess reachability (grep of agent/intelligence/):
  subprocess appears only in sandbox.py (the experimental
  runner, its probe and scope stop), verifier.py (spawning
  the verifier process) and experiments.py (a fixed
  gcc --version metadata call). interface.py, permissions.py,
  loop.py, awareness.py, planning.py, memory.py, strategy.py,
  resources.py and scheduler.py contain no subprocess use and
  no shell=True, os.system or os.popen exists anywhere in the
  package. No operational spec reaches subprocess.

## 7. Regression (auditor's own runs, sequential): CONFIRMED with a one-check reporting discrepancy

- make test-agent-security: ALL AGENT SECURITY TESTS PASSED
  (91 checks). Matches the report.
- make test-agent-intelligence: ALL AGENT INTELLIGENCE TESTS
  PASSED (86 checks). Matches the report.
- make test-agent-awareness: ALL AGENT AWARENESS TESTS PASSED
  (50 checks) in two separate auditor runs. The Prompt 1
  report states 51 checks. The suite passes; the count in
  the report is one higher than what the suite prints on
  this host. Minor reporting discrepancy, recorded here.
- make test-agent-operations: ALL AGENT OPERATIONS TESTS
  PASSED (10,309 checks, including the 240-trial resources
  campaign). Matches the report.
- Makefile: test-all depends on exactly 37 targets (counted
  from the Makefile itself). CONFIRMED.

## 8. Production integrity: CONFIRMED, with the miner interruption explained

- Tree diff using bal_github.py read-only machinery
  (local_files() content compared via blob_sha() against
  remote_tree(); remote HEAD re-fetched as
  18ff4eb070a066dec4424cf9cd4d8282fa9a38b3): 27 differing
  paths. 13 are exactly the Prompt 1 authorised set (created:
  agent/intelligence/sandbox.py, agent/intelligence/
  verifier.py, tests/test_agent_security.py,
  research/autonomous_brain/PROMPT1_SECURITY_REPORT.md;
  modified: agent/intelligence/loop.py, experiments.py,
  permissions.py, interface.py, __init__.py,
  tests/test_agent_intelligence.py,
  tests/test_agent_operations.py, Makefile,
  docs/AGENT_CAPABILITIES.md). 1 is live evidence churn
  (evidence/mainnet-live.jsonl). The remaining 13 are .so
  build artifacts under research/sha256d/exp032/ and
  research/sha256d/exp041/src/ whose mtimes (2026-11-15
  09:37 UTC and 20:49 to 21:11 UTC) predate both the Prompt 1
  build window (file mtimes 2026-11-16 02:06 to 02:08 UTC)
  and this audit; they are pre-existing non-reproducible
  local build artifacts, the same class the Master Build
  closing audit recorded as note N-1, and are not Prompt 1
  changes. No other differences. Nothing outside the
  authorised set is attributable to Prompt 1.
- Zero U+2014 in all 13 Prompt 1 files (byte scan, 0
  occurrences in each).
- Miner and autopilot: at audit start (02:10 UTC) and
  through every sandbox and regression run, autopilot pid
  3745 and miner pid 3758 were alive, heartbeat fresh,
  shares 428 accepted. At about 02:14:46 UTC the VM itself
  was replaced (uptime 3 minutes at 02:17:46 UTC, systemd
  units absent, the known non-durable-unit pattern); the
  last pre-replacement heartbeat (02:14:30 UTC) still showed
  pids 3745/3758 running with restarts 0. The keeper restored
  service on its own: by 02:20:22 UTC autopilot pid 4111 and
  miner pid 4114 were running with shares still 428. This
  audit restarted, signalled and modified nothing; the
  interruption was the VM replacement, not the audit and not
  the Prompt 1 build (whose own pid evidence covers its
  window and is consistent with what the auditor observed).

## Summary of check outcomes

1. Evidence gate strictness: CONFIRMED.
2. Forgery and self-verification: CONFIRMED.
3. Sandbox escapes: REFUTED in part (defect D-1, filesystem
   coverage); network, environment, detached-tree, hog and
   refusal items CONFIRMED.
4. Cgroup non-enforcement claim: CONFIRMED (independently
   reproduced); RLIMIT_CPU mechanism CONFIRMED as backstop.
5. Evidence ledger: CONFIRMED except tail-truncation
   detection, which is REFUTED (claim corrected above).
6. Separation: CONFIRMED.
7. Regression: CONFIRMED (awareness count 50 measured vs 51
   reported, suite passing).
8. Production integrity: CONFIRMED; miner interruption was a
   VM replacement, keeper-restored, not auditor-caused.

Required before Prompt 2: fix D-1 (full filesystem
confinement, non-root mapped uid, fatal /proc mount failure)
and re-audit items 3 and 6. Recommended: anchor the evidence
ledger chain head externally so tail truncation is
detectable, and correct the awareness check count in the
Prompt 1 report.
