# Prompt 1 Report: Security Hardening, Evidence Integrity and Experiment Sandbox

Autonomous Mining Brain mandate, Prompt 1. Date: 2026-11-15.
Repository HEAD at start of work (recorded remote head):
18ff4eb070a066dec4424cf9cd4d8282fa9a38b3. Nothing was pushed
by this phase. The live mainnet miner, autopilot and node
were not restarted, signalled or modified; their pids
(autopilot 3745, miner 3758) were identical before and after
all work, with the heartbeat fresh throughout.

## Files inspected

- agent/intelligence/loop.py, experiments.py, permissions.py,
  audit.py, interface.py, __init__.py
- tests/test_agent_intelligence.py, tests/test_agent_operations.py
- docs/AGENT_CAPABILITIES.md, Makefile
- The mandate record (parent-verified defects and measured
  host isolation capabilities).

## Exact defects found (pre-change line numbers)

1. agent/intelligence/loop.py lines 90 to 100: _passed()
   accepted truthy values. A dict {"result": "false"} passed
   the integrate gate, because bool("false") is True and
   "false" != "fail". The gate also accepted independent
   verification as any dict whose "author" string merely
   differed from the implementation author: a self-authored
   claim of independence.
2. agent/intelligence/experiments.py run_command (original
   lines 147 to 207): subprocess.run with cwd inside the
   sandbox directory only. Full parent environment inherited,
   no CPU, memory, process, output or disk limits, and the
   timeout terminated only the direct child, so grandchildren
   survived as orphans. A working-directory restriction, not
   a sandbox.
3. Evidence had no integrity: assemble_evidence merged
   sandbox JSON booleans with no content hashing, no
   append-only chain, no source-commit binding and no
   artifact binding. Any process that could write the sandbox
   could manufacture a passing bundle.

## What was built

### A. Strict evidence schema (loop.py)

_passed() truthiness is gone. validate_evidence_record()
enforces, for every verification record (correctness,
differential, independent verification):

- passed is exactly Boolean True (type(x) is bool; the
  strings "false" and "true" and the integer 1 are refused).
- verifier_id is a non-empty string.
- artifact_sha256 is a 64-char lowercase hex string.
- source_commit is a non-empty string.
- verification_method is in the closed allowlist:
  differential_reference, independent_recompute,
  statistical_replication, chain_acceptance.
- timestamp is an ISO-8601 parseable string.

Missing fields fail closed. The EXP-017 verdict validation
rejects NaN and infinity anywhere (math.isfinite on the
pooled ratio and both CI bounds), rejects a CI whose lower
bound exceeds its upper bound or that is not entirely above
0, and requires sessions to be an int of at least 3 (bool
and string forms refused). validate_integrate_evidence still
returns the named missing/invalid items list. Bundle
binding: all records in a bundle must agree on
artifact_sha256 and source_commit, and must match the loop
record's expected binding when one is set (LoopRecord gained
optional artifact_sha256 and source_commit fields).

### B. Independent verifier service (agent/intelligence/verifier.py)

A separate process, run as
python3 -m agent.intelligence.verifier [--key PATH], taking
one JSON request on stdin and emitting one signed evidence
record on stdout. It holds an HMAC key at
.local/verifier/verifier.key (created on first use, mode
0600, never inside any sandbox, never printed). The verifier
independently recomputes the artifact file's SHA-256 itself;
for differential_reference it re-runs the declared
differential command itself inside the experimental sandbox
and checks declared test vectors against the hashlib
SHA-256d reference. The emitted record carries the strict
schema fields plus signature = HMAC-SHA256(key, canonical
JSON of the other fields). The loop gate verifies the
signature through a verify-only path that reads the same key
file (the gate is platform code, not experiment code; the
sandbox hides .local, so experiment code can never read the
key). A forged verifier_id, a record signed with a different
key, an unsigned record, and a record whose verifier_id
equals the implementation author are all refused with named
reasons. Unknown verification methods are refused by the
verifier before anything runs, with no record issued.

Honest scope: on a single host this separation is process
plus filesystem isolation. Experiment code cannot reach the
key; platform code can verify signatures. It is not a
multi-machine attestation service.

### C. Experimental sandbox (agent/intelligence/sandbox.py)

experiments.py run_command now executes only through
sandbox.run_sandboxed, using what this host measurably has:

- systemd-run --scope with CPUQuota, MemoryMax, TasksMax
  properties (transient scope per run).
- unshare --user --map-root-user --mount --net --pid --fork
  for user, mount, network and pid namespace isolation.
- Inside the mount namespace, a launcher: mounts made
  private; the experiment directory bind-mounted in as the
  only writable work location (staged under /mnt before /tmp
  and .local are covered); fresh tmpfs over /tmp, over the
  repository .local (which also hides the verifier key),
  over the lab secrets directory and over ~/.ssh; the
  repository bind-mounted read-only (recursive bind, so the
  credential-hiding submounts carry over; a plain bind was
  caught in testing silently re-exposing .local and was
  fixed). Production source stays visible for compilation
  but cannot be modified.
- Environment restricted to PATH, LANG, HOME and TMPDIR
  pointing at the sandbox work directory.
- Network namespace with no external interfaces and loopback
  down: no network by default.
- A python prelude applies rlimits (CPU, address space, file
  size, open files) as a second layer.
- The runner starts the tree in its own session; on timeout
  or a cap breach it kills the entire process group and
  stops the systemd scope. Termination reasons are recorded:
  exit, timeout, memory, cpu, tasks, output_cap, disk_cap.
- Output bytes and sandbox disk usage are capped by the
  runner monitor; concurrent experiments are capped at 2 by
  a semaphore.
- If isolation prerequisites are unavailable, execution is
  REFUSED with SandboxUnavailable. There is no unsandboxed
  fallback. The probe runs once and is cached. Probe result
  on this host: PASS (unshare namespaces and systemd-run
  scopes available).

Measured host limitation, stated plainly: the systemd scope
cgroup properties are accepted on this VM (systemctl show
reports them) but do NOT enforce. A test process allocated
about 4 GB under MemoryMax=128M, and 20 tasks ran under
TasksMax=6. This VM's processes live in a cgroup namespace
rooted at 0::/ and no scope sub-cgroups exist under
/sys/fs/cgroup. Enforcement on this host therefore comes
from the layers that demonstrably work here: RLIMIT_CPU and
RLIMIT_AS in the prelude (the address-space limit stopped
the first memory hog), plus a runner-side watchdog that
polls the process tree's total RSS and task count every
0.2 s and kills the tree with the reason recorded (the
memory hog is now killed in about 1.2 s with reason
"memory"; a task hog with reason "tasks"). The scope
properties remain applied: on a host with a normal cgroup
hierarchy they enforce as an additional layer. CPUQuota
enforcement could not be confirmed or refuted by
measurement on this contended VM (a no-quota control hog
received less CPU than a quota'd one across runs), so no
claim is made for it here; CPU-bound work is bounded by the
runtime timeout and RLIMIT_CPU.

gcc and python3 work inside the sandbox (verified: a trivial
C file compiles and runs; the toolchain in /usr stays
visible).

### D. Operational sandbox separation (permissions.py)

ActionSpec gained kind and shell fields. Every L1/L2 spec is
kind=operational with shell=False; every L3 spec is
kind=experimental and still requires a sandbox path inside
the checker's sandbox root. A new guard,
assert_no_shell_payload, refuses any command-like payload
fields (command, argv, shell, code, script, cmd, exec,
executable, args) attached to an operation, and
MiningInterface.inspect_status applies it to its request.
Typed request dataclasses reject extra fields at
construction. The real production controller remains Prompt
2 work and is not claimed here.

### E. Immutable evidence ledger (experiments.py)

Each experiment gets an append-only ledger at
.local/agent-evidence/<experiment_id>.jsonl, OUTSIDE the
writable sandbox. Creation, every run, every evidence
assembly and every gate decision append a record carrying:
experiment_id, kind, timestamps, source_commit (the recorded
HEAD 18ff4eb070a066dec4424cf9cd4d8282fa9a38b3), compiler and
version (gcc --version captured), machine profile (CPU model
from /proc/cpuinfo), execution configuration (the sandbox
limits), raw output file hashes, source and artifact file
hashes of the sandbox contents, the verifier record when
present, the final decision and the integration status, plus
prev_hash and record_hash forming a hash chain.
verify_ledger(experiment_id) recomputes the chain and
reports tampering, truncation or reordering. Earlier records
are never overwritten by this code.

## Acceptance tests (tests/test_agent_security.py, 91 checks, all passed)

1. {"result": "false"} cannot pass: PASS. The gate names
   the correctness item invalid.
2. "true" string and int 1 cannot substitute for Boolean
   True: PASS, both refused; a bare True is also refused as
   not a verification record.
3. NaN and infinity rejected, inverted CI rejected: PASS;
   also fewer than 3 sessions and string sessions refused.
4. Forged verifier identity rejected: PASS. Also rejected: a
   record signed with a different key, an unsigned record,
   and verifier_id equal to the author.
5. Evidence bound to a different source commit or artifact
   rejected: PASS, both as bundle disagreement and against
   the loop record's expected binding.
6. Sandbox cannot write outside itself: PASS. A write to a
   host /tmp marker landed only in the namespace tmpfs; the
   host path never appeared.
7. Sandbox cannot read production secrets: PASS. The node
   bitcoin.conf, the lab wallet secrets file and the SSH
   private key all raised OSError inside the sandbox.
8. No network by default: PASS. TCP connects to 1.1.1.1:53
   and 8.8.8.8:53 both failed (network unreachable).
9. Sandbox cannot modify production files: PASS. Appending
   to mining/engine.py failed with a read-only filesystem
   error and the file's SHA-256 was identical before and
   after.
10. Timed-out process tree terminated: PASS. A parent that
    spawned a heartbeat-writing child was timed out at 3 s;
    the child's heartbeats stopped and no process carrying
    the child marker survived.
11. CPU and memory limits enforced: PASS. The memory hog
    was killed by the watchdog with reason "memory" in about
    1.2 s of wall time under a 128M cap; a CPU hog ran only
    to its time budget with reason "timeout" recorded. (See
    the cgroup limitation above: enforcement here is rlimits
    plus the watchdog, not the scope properties.)
12. A failed security check refuses execution: PASS. A
    tampered ledger is detected by verify_ledger; the
    verifier refuses an unknown method and issues no record;
    with the isolation probe forced to fail, run_command
    raises SandboxUnavailable and nothing runs.
13. Sandbox failures do not terminate the production miner:
    PASS. Autopilot pid 3745 and miner pid 3758 were
    identical before and after the whole suite, miner state
    running.

Existing suites, re-run after the changes (sequentially):
test_agent_intelligence 86 checks PASSED;
test_agent_awareness 51 checks PASSED;
test_agent_operations 10309 checks PASSED (includes the
240-trial resources campaign). The strict schema required
migrating the evidence fixtures in the intelligence and
operations suites from loose booleans and author strings to
strict verification records with genuinely signed
independent records (the operations suite obtains its signed
record from the real verifier service over a real artifact);
the gate was not weakened to accommodate them.

## Files created

- agent/intelligence/verifier.py (verifier service, signing
  and verification, runnable as a module)
- agent/intelligence/sandbox.py (experimental sandbox)
- tests/test_agent_security.py (91 checks)
- research/autonomous_brain/PROMPT1_SECURITY_REPORT.md
  (this report)

## Files modified

- agent/intelligence/loop.py (strict evidence schema,
  signature verification at the gate, expected binding)
- agent/intelligence/experiments.py (sandboxed run_command,
  strict evidence assembly, hash-chained evidence ledger)
- agent/intelligence/permissions.py (kind and shell on every
  spec, assert_no_shell_payload)
- agent/intelligence/interface.py (payload guard on
  inspect_status)
- agent/intelligence/__init__.py (verifier key path wiring)
- tests/test_agent_intelligence.py (fixture migration)
- tests/test_agent_operations.py (fixture migration to
  strict records and the real verifier service)
- Makefile (test-agent-security target, added to test-all;
  test-all now has 37 targets)
- docs/AGENT_CAPABILITIES.md (dated correction of the
  evidence-trust limitation)

## Limitations

- Single-host HMAC separation: the verifier's independence
  rests on process separation plus the sandbox hiding the
  key file. Platform code outside the sandbox can read the
  key (it must, to verify). A process with unrestricted host
  access could forge records; the threat model covered here
  is experiment code inside the sandbox, which is the
  boundary Prompt 1 specifies.
- Cgroup limits via systemd scopes do not enforce on this
  VM (measured, above). Memory and task caps are enforced by
  rlimits and the runner watchdog; CPU quota enforcement is
  unproven on this host and is not claimed.
- The watchdog polls every 0.2 s, so a very fast allocation
  spike can overshoot the memory cap briefly before the
  kill; RLIMIT_AS bounds the worst case.
- The verifier's differential_reference path runs the
  declared command inside the same experimental sandbox;
  commands are argv lists from the requesting platform code,
  never from inside an experiment.
- The operational sandbox is only half built, by design of
  the mandate order: typed separation and payload refusal
  are in place, but no production MiningController exists
  yet (Prompt 2). Start and stop still raise
  NotImplementedError without an injected controller.
- An independent security audit by a non-author agent has
  not yet been run on this phase; per the mandate, Prompt 2
  production authority should not proceed until it passes.

## FIX (post-audit), 2026-11-15 PST (executed 2026-11-16 UTC)

The independent audit (research/autonomous_brain/
PROMPT1_SECURITY_AUDIT.md) returned FAIL on one critical
defect and two corrections. All three are addressed here.
This section supersedes section C's filesystem-isolation
claims and section E's unqualified truncation claim; the
original text above is left unchanged as the record of
what was first built.

### D-1 (critical): sandbox filesystem isolation rebuilt as a private root

The audited build overmounted only enumerated paths; the
rest of the host filesystem kept its normal mounts, and
sandboxed code ran as uid 0. The auditor wrote to host
/etc, /home/hatch and /usr/local/share (including through
a symlink), read /etc/shadow, and enumerated host processes
through the inherited /proc (the launcher's proc mount
failed silently under "|| true").

The rebuild does not enumerate more paths. The launcher
(agent/intelligence/sandbox.py) now runs in unshare mount,
network and pid namespaces, builds a NEW root filesystem
on a tmpfs, pivot_root's into it, mounts a fresh procfs
for the new pid namespace (failure is fatal, launcher exit
98, never ignored), and detaches the old root with the
umount2 syscall (MNT_DETACH; util-linux umount cannot work
at that point because it consults /proc/self/mounts before
procfs exists in the new root). The new root contains
only: /usr bind-mounted read-only with the host's
merged-usr symlinks recreated; /etc bind-mounted
read-only; the fresh procfs; a minimal /dev (tmpfs with
the null, zero, full, random and urandom device files
bound in, a tmpfs /dev/shm, fd/stdin/stdout/stderr
symlinks); a tmpfs /tmp; /source (below); and /work, the
experiment directory and the only writable persistent
location. /home, /root, /var and every other host path are
absent, not overmounted.

Two ordering facts were measured on this kernel and are
load-bearing: the fresh procfs must be mounted after the
pivot but BEFORE the old root is detached (once no proc
mount remains in the namespace, this kernel refuses a new
one), and the detach must use the raw syscall (above).

Privilege drop. The payload never runs as root. The
runner chowns the experiment directory tree to 65534:65534
(the nobody/nogroup ids, without following symlinks)
before launch, and the python prelude applies rlimits,
then setgroups([]), setgid(65534), setuid(65534), then
execs. Inside the payload, id reports uid 65534; writes to
/etc, /usr/local/share and /source fail with EROFS;
writes to host paths such as /home/hatch fail because the
paths do not exist; /etc/shadow is present through the
read-only /etc bind but unreadable by uid 65534 (0640
root); /proc shows only the payload's own pid namespace.

A nested user namespace was built and measured first, and
rejected on evidence: with uid/gid maps written by a
parent stage process (inner 0 to host 0 for the launcher
stage, inner 65534 to host 65534 for the payload), every
mount and the pivot worked, but this kernel then refuses
ALL fresh procfs mounts from inside the nested namespace,
in both pre-pivot and post-pivot positions, because the
inherited runtime /proc carries locked masked submounts
foreign to the nested namespace. The identical build
without the nested namespace mounts procfs cleanly. A
fresh procfs is a hard requirement (host process
visibility was half of D-1), so the nested namespace is
not used; this process already runs inside the runtime's
own user namespace, and the drop is by setuid to host uid
65534, the alternative the mandate text offers.

/source. The repository tree is mode 770/660 root:root
throughout, so a plain bind is unreadable by uid 65534.
Overlayfs mounts fail on this kernel (measured) and
mount_setattr idmapped binds return EINVAL in this
runtime (measured). The launcher therefore copies the
repository (77 MB, about 1064 files, excluding .local)
into the private root's tmpfs, widens the COPY to a+rX
(host modes untouched), creates an empty .local in the
copy, and remounts it read-only at /source: a snapshot at
run start, readable by the payload, unwritable (EROFS),
and immune to host changes during the run.

Timeout semantics. Building the private root costs
roughly 13 to 20 s of wall time on this contended VM
(about 0.5 s of CPU; the rest is per-file wait). Run
timeouts are therefore now measured from payload start:
the launcher drops a start marker in /work immediately
before exec'ing the payload, the runner latches the
deadline from the marker's appearance, and a separate
300 s construction grace bounds setup. Termination
reasons, the watchdog, rlimits, the systemd scope attempt,
the process-group plus scope termination, output and disk
caps, the concurrent-experiment semaphore and
probe-failure refusal (SandboxUnavailable, no fallback)
are unchanged; the probe now runs the real launcher end
to end and requires the payload to print uid 65534.

What a payload can still see, stated plainly: the
read-only /usr runtime tree, the read-only /etc runtime
configuration (minus files its uid cannot read, such as
/etc/shadow), the read-only /source snapshot (its .local
empty), its own /work, and a /proc showing only its own
pid namespace.

Regression tests (tests/test_agent_security.py, new
function test_sandbox_escape_paths): the auditor's exact
attacks are now permanent tests. Writes to /etc/<marker>,
/home/hatch/<marker>, /usr/local/share/<marker>,
/etc/hostname and through an in-sandbox symlink to /etc;
reads of /etc/shadow, a host-only marker file planted at
a random path outside the sandbox, the verifier key (by
host path and via /source/.local) and the host MEMORY.md;
host miner pid visibility and host cmdline enumeration in
/proc; payload uid by os.getuid and by id -u. Every marker
is verified absent or unchanged from the HOST side after
the run. A python3 hashlib SHA-256d differential inside
the sandbox was added to test_sandbox_isolation alongside
the existing gcc compile-and-run smoke test.

Results: make test-agent-security: ALL AGENT SECURITY
TESTS PASSED (112 checks, up from 91). make
test-agent-intelligence: 86 checks PASSED. make
test-agent-operations: 10309 checks PASSED. make
test-agent-awareness: PASSED (count is environment-
conditional; see the correction note below). The miner
and autopilot were not restarted or signalled; the
security suite's item 13 pid-identity check passed.

### Ledger tail truncation: external anchor added

The auditor showed a bare hash chain cannot detect
deletion of whole TAIL records (a 3-record ledger cut to
2 verified as intact). experiments.py now maintains an
external anchor: on every append, _update_anchor
atomically (temp file plus os.replace) rewrites
.local/agent-evidence/<experiment_id>.anchor.json with
the experiment id, the record count and the last record
hash, HMAC-signed with the verifier key (the same signing
helpers as the verifier service; the anchor lives in
.local, which experiment code cannot reach at all).
verify_ledger now additionally requires the anchor to
exist, to carry a valid signature and matching experiment
id, and to agree with the ledger on count and head hash;
a missing or forged anchor fails closed. New tests
(test_ledger_anchor): a genuine 3-record ledger verifies;
cutting it to 2 records and to 0 records are both
detected via the anchor; editing the anchor's count
(invalidating its signature) is rejected. Note:
ledgers written before this fix have no anchor and now
fail verification with "evidence anchor missing"; that is
the intended fail-closed behaviour for pre-anchor records.

### Correction note (2026-11-15 PST): awareness check count

The regression section above states test_agent_awareness
passed with 51 checks. The auditor measured 50 in two
runs. Both numbers are real executions of the same suite:
test_live_smoke in tests/test_agent_awareness.py contains
two environment-conditional checks on top of 49
unconditional ones: one runs only when the heartbeat age
is present in the snapshot (essentially always), and one
(blocks <= headers) runs only when the node RPC answers.
Under the node's standing initial-block-download load the
RPC read intermittently times out at its bound, and the
check is skipped for that run. In the fix author's own
runs on 2026-11-15 PST the suite printed 51 with the RPC
answering and, later the same day, 50 with the log line
"RPC getblockchaininfo attempt 1/1 failed: timed out".
The honest statement is: the suite passes; its printed
count is 50 or 51 depending on node RPC reachability at
run time. The unqualified "51 checks" above should have
said so.
