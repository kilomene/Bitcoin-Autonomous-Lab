# Prompt 1 Independent Security Re-Audit: D-1 Fix Verification

Auditor: independent non-author agent (adversarial verification,
own probes through the real ExperimentRunner.run_command).
Date: 2026-11-15 PST (work executed 2026-11-16 02:52 to 03:06 UTC).
Build under re-audit: the post-audit fix recorded in
research/autonomous_brain/PROMPT1_SECURITY_REPORT.md, section
"FIX (post-audit)": private root via pivot_root, payload uid
65534, fresh procfs, HMAC-signed ledger anchor, timeout measured
from payload start.
Remote HEAD confirmed live by read-only diff:
18ff4eb070a066dec4424cf9cd4d8282fa9a38b3. Nothing was pushed.
Nothing was restarted by this audit.

## Verdict: PASS WITH NOTES

Every D-1 escape from the first audit is refused by the rebuilt
sandbox under my own probes, verified from the host side. The
new surfaces the fix introduces (the /source snapshot, the
fresh /proc, the uid drop, the device set, the ledger anchor)
were probed independently and hold. The ledger anchor detects
every tamper case I applied. The timeout change is measured
correct. Production integrity holds.

The notes are about the regression suites and the environment,
not about the fix: my run of make test-agent-security failed at
one check under concurrency I introduced (section 5), and from
about 03:02 UTC a VM-wide exec write block (every file write
from exec, bash, dd and Python alike, denied with EPERM)
prevented clean sequential reruns of the operations and
awareness suites. At the same minute the lab miner stack
(autopilot, miner, bitcoind) disappeared from the host process
table; no audit action signals host processes (probe 1 proves
the payload cannot even see them), and the keeper is expected
to restore them. A clean sequential rerun of
test-agent-security, test-agent-operations and
test-agent-awareness is required once exec writes recover, to
close the regression item formally.

## Probe 1: the first audit's exact escapes, replayed: CONFIRMED (all refused)

Method: one payload through ExperimentRunner.run_command
(re-audit probe A, experiment exp-20261116T025239Z-f3a7a2,
random suffix 22429f1af4), markers verified from the host side
afterwards, then removed.

Writes (payload result, host-side result):
- /etc/reaudit-22429f1af4: blocked inside (OSError, errno 30
  EROFS); host file absent afterwards.
- /home/hatch/reaudit-22429f1af4: blocked inside
  (FileNotFoundError, errno 2; the path does not exist in the
  private root); host file absent.
- /usr/local/share/reaudit-22429f1af4: blocked inside (errno
  30 EROFS, via the read-only /usr bind); host file absent.
- Append to /etc/hostname: blocked inside (PermissionError,
  errno 13); host /etc/hostname SHA-256 identical before and
  after (e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca4959
  91b7852b855, the empty file on this host).
- Write through an in-sandbox symlink to /etc
  (esc-link/reaudit-22429f1af4): blocked inside (errno 30).
- Write via /work/../etc traversal: blocked inside (errno 30).

Reads (all blocked inside):
- /etc/shadow: PermissionError (errno 13). The file exists
  through the read-only /etc bind but is unreadable by uid
  65534, as the fix describes.
- Host-only marker planted by me at
  /home/hatch/workspace/reaudit-hostonly-22429f1af4.txt:
  FileNotFoundError by the host absolute path, via
  /proc/self/root plus the host path, via /proc/1/root plus
  the host path, and via .. traversal from both /work and
  /source (5 path constructions, all errno 2).
- Verifier key: FileNotFoundError by the host path
  (.local/verifier/verifier.key), via /source/.local, via
  /proc/self/root, via /proc/1/root, and via .. traversal
  from /work and from /source (6 constructions, all errno 2).
- Node .local/mainnet/bitcoin.conf: FileNotFoundError by the
  same 6 constructions (all errno 2).
- /proc/1/root/etc/shadow and /proc/self/root/etc/shadow:
  PermissionError (errno 13); the proc root links resolve to
  the private root, not the host.

Host side after the run: none of the three marker files
exists, /etc/hostname byte-identical, the planted host-only
marker untouched (removed by me after verification).

## Probe 2: new angles introduced by the fix

### 2a. The /source snapshot: CONFIRMED clean

Payload enumeration (probe B, exp-20261116T025408Z-ae2602):
/source top level is the repository tree (agent, asic,
blockchain, dashboard, docs, evidence, fpga, gpu, mining,
node, research, results, scripts, tests, plus root files);
1,065 files in total. /source/.local lists EMPTY ([]), as
designed. /source is not writable (errno 30 EROFS on a write
attempt); known repo files (README.md, mining/engine.py,
Makefile) are readable, which is the snapshot's purpose.
Name scan for secret-shaped paths found only
mining/wallet_gen.py (the public key-generation script) and
its __pycache__ entry; no verifier key, wallet file or
bitcoin.conf path exists in the snapshot.
Secret-value scan: on the host I loaded the RPC password
from .local/mainnet/bitcoin.conf and the private key hex and
WIF from the lab wallet file, took a 16-character middle
substring of each (values never printed anywhere in this
audit), passed the substrings to the payload in a file under
/work, and the payload byte-searched every file under
/source for each substring. Result for all three fragments:
NOT FOUND, no path reported. The fragment file was deleted
by the payload and confirmed gone from the host side.

### 2b. /proc: CONFIRMED

The payload's /proc contains exactly one numeric entry: its
own pid (1 in its pid namespace; the payload is the namespace
init). Its cmdline is the payload itself. The host miner pid
(4114) and autopilot pid (4111) are not visible
(os.path.exists returns False for both). No host cmdline is
enumerable. /proc/self/root resolves to / and lists only the
private root entries (bin, dev, etc, lib, lib32, lib64,
libx32, proc, sbin, source, tmp, usr, work). /proc/mounts has
19 lines and contains no /home entry and no secrets path.

### 2c. Payload identity: CONFIRMED

os.getuid/geteuid/getgid/getegid all report 65534; id(1)
prints uid=65534(nobody) gid=65534(nogroup). /proc/self/status
shows Uid and Gid 65534 across all four fields, CapEff
0000000000000000, NoNewPrivs 1. os.setuid(0) is refused
(PermissionError, errno 1); os.setgid(0) is refused the same
way. Note N-2 below records the CapBnd value precisely.

### 2d. Inherited file descriptors: CONFIRMED

/proc/self/fd inside the payload lists only 0, 1 and 2, all
pipes (the runner's captured stdout/stderr/stdin). A fourth
entry (3) appeared in the directory listing itself and its
readlink failed with FileNotFoundError: it is the transient
descriptor of the payload's own listdir call, already closed,
not a host file. No host file is open in the payload.

### 2e. /dev: CONFIRMED

/dev contains exactly: fd, full, null, random, shm, stderr,
stdin, stdout, urandom, zero. No sda, vda, tty, tty0, ptmx,
mem or kmem exists; opening /dev/tty fails (errno 2).

### 2f. Breakout via mount or unshare from inside: CONFIRMED refused

mount -t tmpfs on a fresh directory fails (exit 32, "must be
superuser to use mount"). A nested unshare --mount --pid
--fork fails (exit 1, "unshare: unshare failed: Operation
not permitted"). The payload therefore cannot create a
nested namespace at all on this host; the question of what a
nested namespace could see does not arise. The payload's own
/proc/mounts shows no host mounts (see 2b).

## Probe 3: ledger anchor: CONFIRMED

Method: fresh experiment through the real runner (probe C),
two sandboxed runs, giving a 3-record ledger (created plus 2
runs) with its anchor. Genuine state: verify_ledger returns
True, "3 records, chain intact, anchor verified".
On the live files, with backup and restore between cases:
- Truncate ledger to 2 records: detected. verify_ledger
  returns False, "anchor expects 3 records but the ledger
  holds 2: tail records added or removed".
- Truncate ledger to 0 records: detected. False, "ledger is
  empty" (the empty check fires before the anchor check;
  fails closed either way, note N-4).
- Delete the anchor (the pre-fix ledger shape, chain only):
  detected, fails closed. False, "evidence anchor missing:
  tail truncation cannot be ruled out". Pre-fix ledgers are
  therefore rejected as documented in the fix section.
- Forge an anchor with a wrong key (correct experiment id,
  correct record count, correct head hash, signed with a
  different key generated for this probe): detected. False,
  "evidence anchor signature invalid or missing".
- Edit the anchor record_count to 99 without re-signing:
  detected. False, "evidence anchor signature invalid or
  missing".
- After restore: the genuine ledger verifies True again.

## Probe 4: timeout integrity after the construction-grace change: CONFIRMED

Probe D, two runs through the real runner:
- Case 1 (timeout_s=5, payload records its own start epoch
  then sleeps 60 s): result timed_out True, termination
  reason "timeout", exit code -9. The payload's lifetime,
  measured from its own recorded start epoch to the
  run_command return, is 5.02 s: the deadline is the payload
  deadline, not the 300 s construction grace. The payload
  never reached its post-sleep write (no finished file). For
  scale: payload start came 43.59 s after the run_command
  call in this fresh process (about 21 s of isolation probe
  plus about 22 s of private-root construction), and none of
  that consumed the 5 s budget (note N-5).
- Case 2 (timeout_s=5, payload spawns a setsid grandchild
  writing heartbeats every 0.2 s, then sleeps): timed_out
  True, reason "timeout". Heartbeat count in the sandbox was
  23 immediately after the kill and still 23 two seconds
  later; pgrep on the host finds no surviving process. The
  detached grandchild is fully contained and the termination
  reason is recorded in both cases.

## Probe 5: regression suites: PARTIAL (environment-obstructed)

Run by me, sequentially, from the repository root:
- make test-agent-intelligence: ALL AGENT INTELLIGENCE
  TESTS PASSED (86 checks). Observed directly in a foreground
  run.
- make test-agent-security: FAILED in my run. The buffered
  process log (authoritative; an earlier completion delivery
  for the same session that reported a pass was superseded
  by it) shows: AssertionError: ledger experiment run
  succeeds (in test_refusals_and_ledger), make Error 1. Two
  qualifications, stated plainly: (a) the run overlapped with
  my own read-only diff computation and the intelligence
  suite, so sandbox runs executed under concurrency I
  introduced, contrary to the one-at-a-time discipline;
  (b) the failing check is the exit code of a plain sandboxed
  print run, and the same run_command path succeeded in all
  8 of my direct probe runs in the same window, including
  two ledger-probe runs minutes before. I do not attribute
  this failure to the fix, and I do not erase it: it is an
  unresolved suite failure under concurrency, and the suite
  must be rerun clean.
- make test-agent-operations: my first attempt failed with
  PermissionError (Errno 1) partway. Two further clean
  sequential attempts (by a second agent in a separate exec
  environment, at my request) failed identically at startup:
  tempfile.mkdtemp in main() raises FileNotFoundError, "No
  usable temporary directory found", before any check runs.
- make test-agent-awareness: two clean sequential attempts
  (same second agent) failed identically at
  tempfile.mkdtemp in main(), before any check and before
  any node RPC read. No awareness count (50 or 51) could be
  observed in this audit, and whether the node RPC answered
  during a suite run is therefore unobserved; the node
  itself was mid-IBD and its processes later disappeared
  (section 6).

Root cause of the mkdtemp failures, measured independently
in two exec environments: from about 03:02 UTC every file
WRITE issued from exec is denied with EPERM, on every path
(/tmp, /var/tmp, the workspace, the home directory), for
bash redirection (printf), dd, and Python os.write alike.
File creation succeeds (a 0-byte placeholder appears) and
the write itself is refused, which is exactly the operation
tempfile's usability probe performs, so every suite that
opens with mkdtemp dies at startup. Reads and the file-tool
channel are unaffected. This is a runtime environment
failure, not a property of the code under audit. Required
follow-up: one clean sequential run of test-agent-security,
test-agent-operations and test-agent-awareness once exec
writes recover; expected counts from the fix report are
security 112, operations 10309, awareness 50 or 51 depending
on node RPC reachability.

## Probe 6: production integrity: CONFIRMED, with an environment event

Read-only diff using bal_github.py local_files(),
remote_tree() and blob_sha() against remote HEAD
18ff4eb070a066dec4424cf9cd4d8282fa9a38b3 (local 970 files,
remote 952): 28 differing paths, all accounted for:
- 14 in the Prompt 1 authorised set including the fix files:
  Makefile, agent/intelligence/__init__.py, experiments.py
  (fix mtime 02:35 UTC), interface.py, loop.py,
  permissions.py, sandbox.py (fix mtime 02:43 UTC),
  verifier.py, docs/AGENT_CAPABILITIES.md,
  tests/test_agent_intelligence.py,
  tests/test_agent_operations.py, tests/test_agent_security.py
  (fix mtime 02:39 UTC),
  research/autonomous_brain/PROMPT1_SECURITY_REPORT.md
  (fix section appended, mtime 02:49 UTC), and
  research/autonomous_brain/PROMPT1_SECURITY_AUDIT.md (the
  first audit's own report).
- 1 live evidence churn: evidence/mainnet-live.jsonl.
- 13 pre-existing .so build artifacts under
  research/sha256d/exp032/ (3) and research/sha256d/exp041/
  src/ (10), mtimes 2026-11-15 09:37 and 20:49 to 21:11 UTC,
  predating the Prompt 1 build window; the same class the
  first audit and the Master Build closing audit recorded.
No other differences. Zero U+2014 (byte scan) in all 14
authorised files.

Miner and autopilot: before the audit (02:51 UTC) autopilot
pid 4111, miner pid 4114, bitcoind pid 2850, heartbeat fresh,
miner running, 436 shares accepted. At audit end (03:05 UTC)
none of the three processes exists on the host and the
heartbeat is stale at 03:01:52 UTC (4111/4114, 438 shares).
The disappearance coincides with the onset of the exec write
block (about 03:02 UTC) and with the security suite's ledger
run failure (about 03:01 UTC). This audit restarted,
signalled and modified nothing: probe 1 proves the sandboxed
payload cannot see or signal host processes, and the only
host-side termination in my code path is the sandbox runner
stopping its own bal-sbx scopes. Other host services from
the same boot (02:14 UTC) survived, so this was not a VM
reboot. I record the event as an environment incident during
the audit window, not an audit effect; per instructions I
restarted nothing, and the keeper cron is the mechanism
expected to restore the stack.

## Notes

- N-1 (blocking follow-up, environmental): the regression
  item is not formally closed. test-agent-security needs one
  clean sequential rerun (my run failed at one check under
  self-introduced concurrency), and test-agent-operations
  and test-agent-awareness need one clean run each once the
  exec write block lifts; both currently die at mkdtemp
  before any check, in two independent exec environments.
- N-2: inside the payload, CapBnd reads 000001ffffb7cfff
  (a full bounding set) while CapEff is 0, the uid is 65534
  and NoNewPrivs is 1. No capability is effective, setuid
  back to 0 is refused, and file access is governed by the
  uid and the read-only mounts, so this is not an escape;
  it is recorded because the fix's claim rests on the uid
  drop, and the bounding set is wider than the payload
  needs. A future hardening could also drop the bounding
  set in the prelude.
- N-3: the append attempt on /etc/hostname returned EACCES
  (13) rather than the EROFS (30) returned by the /etc write
  attempts. Both are refusals and the host file is
  byte-identical; the difference is immaterial.
- N-4: truncation of the ledger to 0 records is detected by
  the empty-ledger check in verify_ledger rather than by
  the anchor comparison. The outcome (fail closed) is the
  required one.
- N-5: sandbox startup cost is large on this contended VM:
  in a fresh process the isolation probe plus private-root
  construction put payload start about 43 s after the
  run_command call in probe D (about 22 s of construction
  alone in probe A, wall 26.6 s end to end). Timeouts are
  correctly measured from payload start, so this is a
  latency cost, not a correctness issue.

## Summary of check outcomes

1. First-audit escapes replayed (writes, symlink write,
   reads by 17 path constructions): CONFIRMED, all refused,
   host side clean.
2a. /source snapshot secret scan: CONFIRMED, no secret
    material; .local in the snapshot empty; read-only.
2b. /proc isolation: CONFIRMED, only the payload's own pid
    namespace; proc roots resolve to the private root.
2c. Payload uid 65534, no setuid or capability regain:
    CONFIRMED.
2d. Inherited descriptors: CONFIRMED, stdio pipes only.
2e. /dev minimal set: CONFIRMED.
2f. Mount and nested unshare from inside: CONFIRMED refused.
3. Ledger anchor (genuine, truncate to 2, truncate to 0,
   anchor deleted, wrong-key forge, count edit): CONFIRMED,
   every tamper detected; pre-fix ledgers fail closed.
4. Timeout integrity (payload deadline 5.02 s measured;
   setsid grandchild contained; reasons recorded):
   CONFIRMED.
5. Regression: intelligence 86 PASSED (CONFIRMED); security
   FAILED at one check under self-introduced concurrency
   (recorded, rerun required); operations and awareness
   obstructed by a measured VM-wide exec write block before
   any check could run (environmental; rerun required).
6. Production integrity: CONFIRMED (28 diffs, all in the
   authorised set plus live churn plus pre-existing .so
   artifacts; zero U+2014). Miner stack disappearance at
   about 03:01 UTC recorded as an environment incident; this
   audit restarted nothing.

The D-1 fix itself is verified: defect D-1 does not
reproduce in any form I could construct, and the two
corrections from the first audit (ledger tail truncation,
awareness count) are resolved on the evidence above (the
anchor) and documented in the fix report (the count), with
the awareness count itself unobservable in this window for
the environmental reason in probe 5. Prompt 2 may proceed
on the strength of the sandbox, verifier and ledger
evidence; the regression rerun in note N-1 should be
completed and recorded as soon as the environment permits.
