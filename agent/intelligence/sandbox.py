"""Experimental sandbox (Autonomous Mining Brain, Prompt 1,
items 1.2A and 1.3; filesystem isolation rebuilt after the
Prompt 1 independent audit, defect D-1).

The audit proved the first build's isolation covered only an
enumerated set of paths: sandboxed code running as uid 0
wrote to host /etc, /home and /usr/local/share and read
/etc/shadow, because the rest of the host filesystem simply
kept its normal mounts. This rebuild does not enumerate more
paths. It replaces the root filesystem.

Private root (the core mechanism). The launcher runs inside
unshare mount, network and pid namespaces. It builds a NEW
root on a tmpfs and pivot_root's into it, then detaches the
old root with umount2 MNT_DETACH (through the syscall
directly; util-linux umount cannot work there because it
consults /proc/self/mounts before procfs exists in the new
root). The new root contains ONLY:

- /usr bind-mounted read-only, with the host's merged-usr
  symlinks (/bin, /sbin, /lib, /lib32, /lib64, /libx32)
  recreated to match.
- /etc bind-mounted read-only (runtime configuration only).
- A FRESH procfs for the new pid namespace. It is mounted
  after the pivot and before the old root is detached (this
  kernel refuses a fresh procfs mount once no proc mount
  remains in the namespace; measured). A proc mount failure
  is FATAL (launcher exit 98); it is never ignored.
- A minimal /dev: a tmpfs carrying bind-mounted device files
  null, zero, full, random and urandom, a tmpfs /dev/shm and
  the conventional fd/stdin/stdout/stderr symlinks.
- A tmpfs /tmp (mode 1777).
- /source: a read-only snapshot copy of the repository (see
  below), with .local replaced by an empty directory.
- /work: the experiment directory, bind-mounted, the ONLY
  writable persistent location.

Nothing else from the host filesystem exists in the new
root: /home, /root, /var and every other host path are
absent, not overmounted, so there is nothing to enumerate
and nothing to forget.

Why /source is a snapshot copy, not a bind: the repository
tree is mode 770/660 root:root throughout, so a bind mount
is unreadable by the unprivileged payload uid. Overlayfs
mounts fail on this kernel (measured: wrong fs type), and
mount_setattr idmapped binds return EINVAL in this runtime
(measured). The launcher therefore copies the tree (77 MB,
about 1064 files, excluding .local) into the private root's
tmpfs, widens it to a+rX inside the copy only (host modes
are untouched), and remounts it read-only. The copy is a
snapshot taken at run start: host changes during a run do
not leak in, and the payload cannot modify the original.

Why there is no nested user namespace: one was built and
measured. With a nested userns (uid/gid maps written by a
parent stage process: inner 0 to host 0 for the launcher,
inner 65534 to host 65534 for the payload), every mount and
the pivot worked, but this kernel then refuses ALL fresh
procfs mounts from inside the nested namespace, in both
pre-pivot and post-pivot positions, because the inherited
runtime /proc carries locked masked submounts that are
foreign to the nested namespace (mount_too_revealing). The
identical build without the nested namespace mounts procfs
cleanly. A fresh procfs is a hard requirement (host process
visibility was half of defect D-1), so the nested namespace
is not used. This process already runs inside the runtime's
own user namespace, and the privilege drop is by setuid
inside the namespace to host uid 65534 (nobody), the
alternative the mandate text offers: the payload's file
access is as host uid 65534, never as root. The launcher
stage that performs the mounts runs as the namespace's
root; the payload never does.

Privilege drop and the work directory: the runner chowns
the experiment directory tree to 65534:65534 (without
following symlinks) before launch, so the payload can write
/work and nothing else, and its outputs stay readable by
the host agent (root). The python prelude applies the
rlimits, then setgroups([]), setgid(65534), setuid(65534),
then execs the command. Inside the payload, id reports
uid 65534; /etc/shadow is present through the read-only
/etc bind but unreadable (0640 root); writes to /etc,
/usr/local/share and /source fail with EROFS; host paths
such as /home simply do not exist.

What a payload CAN still see, stated plainly: the read-only
/usr runtime tree, the read-only /etc runtime configuration
(minus files its uid cannot read, such as /etc/shadow), the
read-only /source snapshot of the repository (its .local
empty), its own /work, and a /proc showing only processes
inside its own pid namespace.

Other layers, unchanged from the first build:

- systemd-run --scope requests cgroup limits (CPUQuota,
  MemoryMax, TasksMax). MEASURED HOST LIMITATION: on this
  VM the scope properties are accepted but do NOT enforce
  (a process allocated about 4 GB under MemoryMax=128M;
  this VM's processes live in a cgroup namespace rooted at
  0::/ and no scope sub-cgroups exist). Enforcement here
  comes from the prelude rlimits (RLIMIT_CPU, RLIMIT_AS,
  RLIMIT_FSIZE, RLIMIT_NOFILE) and a runner-side watchdog
  that polls the process tree's total RSS and task count
  every 0.2 s and kills the tree with the termination
  reason recorded. The scope properties stay applied for
  hosts with a normal cgroup hierarchy.
- The environment inside is a small allowlist: PATH, LANG,
  HOME=/work and TMPDIR=/tmp set by the launcher; the
  runner passes only PATH and the BAL_* control variables
  into systemd-run.
- The network namespace has no external interfaces and its
  loopback stays down: no network access by default.
- The runner starts the tree in its own session
  (start_new_session) and, on timeout or a cap breach,
  kills the entire process group and stops the systemd
  scope, so a timed-out tree leaves no orphans. Output and
  sandbox disk usage are capped by the runner monitor;
  concurrent experiments are capped by a semaphore.
- Run timeouts are measured from payload start, not from
  process spawn: building the private root (including the
  /source snapshot copy, roughly 13 to 20 s of wall time on
  this contended VM at about 0.5 s of CPU) must not consume
  the experiment's own budget. The launcher drops a start
  marker in /work immediately before exec'ing the payload;
  the runner latches the deadline from the marker's
  appearance, with a separate 300 s construction grace
  after which a run that never started is timed out too.

If the isolation prerequisites are unavailable (a required
tool missing, or the end-to-end probe fails), run_sandboxed
REFUSES with SandboxUnavailable. There is no unsandboxed
fallback. The probe runs the real launcher once with a
payload that prints its uid, requires exit 0 and uid 65534,
and caches the result.

gcc and python3 work inside the sandbox (verified by the
security suite: a C file compiles and runs, and a hashlib
SHA-256d differential matches the host reference).
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import uuid

_REPO_ROOT = os.path.abspath(os.path.join(
    os.path.dirname(__file__), "..", ".."))

# The payload never runs as root. It runs as this dedicated
# unprivileged host uid/gid (nobody/nogroup), reached by
# setuid inside the namespace after the launcher (which runs
# as the namespace root) has built the private root.
PAYLOAD_UID = 65534
PAYLOAD_GID = 65534

DEFAULT_MEMORY_MAX = "512M"
DEFAULT_CPU_QUOTA = "200%"
DEFAULT_TASKS_MAX = 256
DEFAULT_MAX_OUTPUT_BYTES = 8 << 20
DEFAULT_MAX_DISK_BYTES = 256 << 20
MAX_CONCURRENT = 2
# Name of the marker file the launcher drops in /work the
# moment the payload is about to start. The runner measures
# the run timeout from the payload's start, not from process
# spawn: sandbox construction (the /source snapshot copy)
# takes roughly 13 to 20 s of wall time on this contended
# VM and must not eat the experiment's own time budget.
START_MARKER = ".bal-payload-started"
# How long sandbox construction may take before payload
# start before the run is treated as timed out anyway.
SETUP_GRACE_S = 300

_semaphore = threading.Semaphore(MAX_CONCURRENT)
_probe_cache = None
_probe_lock = threading.Lock()


class SandboxUnavailable(Exception):
    """Isolation prerequisites are missing or the probe
    failed; execution is refused rather than degraded."""


_LAUNCHER = r"""
set -u
SBX="$1"; REPO="$2"; shift 2
[ "${1:-}" = "--" ] && shift
mount --make-rprivate / || exit 97
mount -t tmpfs tmpfs /mnt || exit 97
mkdir -p /mnt/newroot
mount -t tmpfs -o mode=755 tmpfs /mnt/newroot || exit 97
cd /mnt/newroot || exit 97
mkdir -p usr etc proc dev tmp source work oldroot
mount --rbind /usr usr || exit 97
mount -o remount,ro,bind usr || exit 97
for l in bin sbin lib lib32 lib64 libx32; do
  if [ -L "/$l" ]; then
    ln -s "$(readlink "/$l")" "$l" || exit 97
  elif [ -d "/$l" ]; then
    mkdir -p "$l"
    mount --rbind "/$l" "$l" || exit 97
    mount -o remount,ro,bind "$l" || exit 97
  fi
done
mount --rbind /etc etc || exit 97
mount -o remount,ro,bind etc || exit 97
mount -t tmpfs -o mode=1777 tmpfs tmp || exit 97
mount -t tmpfs -o mode=755 tmpfs source || exit 97
for e in "$REPO"/* "$REPO"/.[!.]*; do
  [ -e "$e" ] || continue
  [ "$(basename "$e")" = ".local" ] && continue
  cp -a "$e" source/ || exit 97
done
mkdir -p source/.local
chmod -R a+rX source || exit 97
mount --bind source source || exit 97
mount -o remount,ro,bind source || exit 97
mount --bind "$SBX" work || exit 97
mount -t tmpfs -o mode=755 tmpfs dev || exit 97
for d in null zero full random urandom; do
  touch "dev/$d" || exit 97
  mount --bind "/dev/$d" "dev/$d" || exit 97
done
mkdir -p dev/shm
mount -t tmpfs -o mode=1777 tmpfs dev/shm || exit 97
ln -s /proc/self/fd dev/fd || exit 97
ln -s /proc/self/fd/0 dev/stdin || exit 97
ln -s /proc/self/fd/1 dev/stdout || exit 97
ln -s /proc/self/fd/2 dev/stderr || exit 97
cd /mnt/newroot || exit 97
pivot_root . oldroot || exit 99
cd / || exit 99
mount -t proc proc /proc || exit 98
python3 -c 'import ctypes,sys; libc=ctypes.CDLL("libc.so.6",use_errno=True); rc=libc.umount2(b"/oldroot",2); sys.exit(0 if rc==0 else 1)' || exit 99
rmdir /oldroot || exit 99
export HOME=/work TMPDIR=/tmp LANG=C.UTF-8
export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
cd /work || exit 99
: > .bal-payload-started || exit 99
exec python3 -c "$BAL_PRELUDE" "$@"
"""

_PRELUDE = (
    "import os, resource, sys\n"
    "resource.setrlimit(resource.RLIMIT_CPU, "
    "(int(os.environ['BAL_RLIMIT_CPU']), "
    "int(os.environ['BAL_RLIMIT_CPU']) + 1))\n"
    "resource.setrlimit(resource.RLIMIT_AS, "
    "(int(os.environ['BAL_RLIMIT_AS']), "
    "int(os.environ['BAL_RLIMIT_AS'])))\n"
    "resource.setrlimit(resource.RLIMIT_FSIZE, "
    "(int(os.environ['BAL_RLIMIT_FSIZE']), "
    "int(os.environ['BAL_RLIMIT_FSIZE'])))\n"
    "resource.setrlimit(resource.RLIMIT_NOFILE, (256, 256))\n"
    "os.setgroups([])\n"
    "os.setgid(int(os.environ['BAL_PAYLOAD_GID']))\n"
    "os.setuid(int(os.environ['BAL_PAYLOAD_UID']))\n"
    "os.execvp(sys.argv[1], sys.argv[1:])\n"
)


def _parse_memory(text):
    """Parse a systemd memory size like 512M or 128M to bytes."""
    text = str(text).strip()
    mult = 1
    if text and text[-1] in "KMGT":
        mult = {"K": 1 << 10, "M": 1 << 20,
                "G": 1 << 30, "T": 1 << 40}[text[-1]]
        text = text[:-1]
    return int(float(text) * mult)


def _chown_tree(path):
    """Chown a directory tree to the payload uid/gid without
    following symlinks, so the payload can write its work
    directory and nothing else. Best effort per entry (the
    host agent runs as root, so this succeeds here); the top
    directory is chowned first and matters most."""
    try:
        os.chown(path, PAYLOAD_UID, PAYLOAD_GID,
                 follow_symlinks=False)
    except OSError:
        pass
    for root, dirs, files in os.walk(path):
        for name in dirs + files:
            try:
                os.chown(os.path.join(root, name),
                         PAYLOAD_UID, PAYLOAD_GID,
                         follow_symlinks=False)
            except OSError:
                pass


def _build_command(sandbox_dir, argv, timeout_s, memory_max,
                   cpu_quota, tasks_max):
    """Assemble the (systemd-run command list, environment)
    that runs argv inside the private-root sandbox. Shared
    by the probe and by run_sandboxed so the probe measures
    exactly what production runs."""
    mem_bytes = _parse_memory(memory_max)
    unit = f"bal-sbx-{uuid.uuid4().hex[:12]}"
    env = {
        "PATH": "/usr/local/sbin:/usr/local/bin:/usr/sbin:"
                "/usr/bin:/sbin:/bin",
        "BAL_PRELUDE": _PRELUDE,
        "BAL_RLIMIT_CPU": str(max(1, int(timeout_s) + 5)),
        # Address-space cap: on this host the cgroup MemoryMax
        # does not enforce (see module docstring), so RLIMIT_AS
        # plus the runner watchdog are the enforcing layers.
        # The cap leaves headroom over the memory limit for
        # interpreter and toolchain virtual reservations.
        "BAL_RLIMIT_AS": str(mem_bytes * 4 + (512 << 20)),
        "BAL_RLIMIT_FSIZE": str(64 << 20),
        "BAL_PAYLOAD_UID": str(PAYLOAD_UID),
        "BAL_PAYLOAD_GID": str(PAYLOAD_GID),
    }
    inner = ["unshare", "--mount", "--net", "--pid", "--fork",
             "--", "/bin/bash", "-c", _LAUNCHER, "bal-launcher",
             sandbox_dir, _REPO_ROOT, "--"] + list(argv)
    cmd = ["systemd-run", "--scope", "--quiet", f"--unit={unit}",
           "-p", f"CPUQuota={cpu_quota}",
           "-p", f"MemoryMax={memory_max}",
           "-p", f"TasksMax={tasks_max}",
           "--"] + inner
    return cmd, env, unit


def probe_isolation():
    """Run the isolation probe once and cache the result.
    The probe runs the REAL launcher end to end with a
    payload that prints its uid, and requires exit 0 and the
    payload uid (65534): namespaces, private root, pivot,
    fresh procfs and the privilege drop are all exercised.
    Returns (ok, detail)."""
    global _probe_cache
    if _probe_cache is not None:
        return _probe_cache
    with _probe_lock:
        if _probe_cache is not None:
            return _probe_cache
        detail = []
        ok = True
        for tool in ("unshare", "systemd-run", "mount", "cp",
                     "pivot_root"):
            if shutil.which(tool) is None:
                ok = False
                detail.append(f"{tool} missing")
        if ok:
            probe_dir = tempfile.mkdtemp(
                prefix="bal-sbx-probe-")
            try:
                _chown_tree(probe_dir)
                cmd, env, _unit = _build_command(
                    probe_dir,
                    ["python3", "-c",
                     "import os; print(os.getuid())"],
                    timeout_s=30, memory_max="256M",
                    cpu_quota="200%", tasks_max=64)
                proc = subprocess.run(
                    cmd, capture_output=True, text=True,
                    timeout=300, env=env)
                got = proc.stdout.strip()
                if proc.returncode != 0:
                    ok = False
                    detail.append(
                        f"probe run exit {proc.returncode}: "
                        f"{proc.stderr.strip()[:200]}")
                elif got != str(PAYLOAD_UID):
                    ok = False
                    detail.append(
                        f"probe payload uid {got!r}, expected "
                        f"{PAYLOAD_UID}")
            except (OSError, subprocess.TimeoutExpired) as exc:
                ok = False
                detail.append(f"probe run failed: {exc}")
            finally:
                shutil.rmtree(probe_dir, ignore_errors=True)
        _probe_cache = (ok, "; ".join(detail) if detail
                        else "private-root sandbox probe "
                             "passed (namespaces, pivot_root, "
                             "fresh procfs, payload uid "
                             "65534)")
        return _probe_cache


_PAGE_SIZE = os.sysconf("SC_PAGE_SIZE")
# Processes the launcher itself contributes to the tree
# (systemd-run, unshare, bash, the python prelude) on top of
# the command's own tasks, allowed before the watchdog's
# task-count cap fires.
_LAUNCHER_TASK_SLACK = 8


def _tree_stats(root_pid):
    """(task_count, total_rss_bytes) of root_pid and all its
    descendants, from /proc. Processes that vanish mid-scan
    are skipped."""
    ppid = {}
    rss = {}
    for name in os.listdir("/proc"):
        if not name.isdigit():
            continue
        pid = int(name)
        try:
            with open(f"/proc/{pid}/stat", "rb") as f:
                parts = f.read().rsplit(b")", 1)[1].split()
            ppid[pid] = int(parts[1])
            rss[pid] = int(parts[21]) * _PAGE_SIZE
        except (OSError, ValueError, IndexError):
            continue
    children = {}
    for pid, parent in ppid.items():
        children.setdefault(parent, []).append(pid)
    count = 0
    total = 0
    stack = [root_pid]
    seen = set()
    while stack:
        pid = stack.pop()
        if pid in seen:
            continue
        seen.add(pid)
        count += 1
        total += rss.get(pid, 0)
        stack.extend(children.get(pid, []))
    return count, total


def _dir_size(path):
    total = 0
    for root, _dirs, files in os.walk(path):
        for name in files:
            try:
                total += os.path.getsize(os.path.join(root, name))
            except OSError:
                pass
    return total


def run_sandboxed(argv, sandbox_dir, timeout_s=120,
                  memory_max=DEFAULT_MEMORY_MAX,
                  cpu_quota=DEFAULT_CPU_QUOTA,
                  tasks_max=DEFAULT_TASKS_MAX,
                  max_output_bytes=DEFAULT_MAX_OUTPUT_BYTES,
                  max_disk_bytes=DEFAULT_MAX_DISK_BYTES):
    """Run argv (a list of strings, never a shell string)
    inside the experimental sandbox: a private root built by
    pivot_root (see the module docstring), cwd /work bound to
    sandbox_dir, payload running as host uid 65534. Returns a
    result dict:

        exit_code, timed_out, wall_s, stdout, stderr,
        termination_reason (exit, timeout, memory, cpu,
        tasks, output_cap, disk_cap, sandbox_error),
        limits (the limits applied).

    Raises SandboxUnavailable when isolation cannot be
    provided. Never falls back to unsandboxed execution.
    """
    ok, detail = probe_isolation()
    if not ok:
        raise SandboxUnavailable(
            f"experimental sandbox unavailable: {detail}; "
            "execution refused, no unsandboxed fallback")
    sandbox_dir = os.path.abspath(sandbox_dir)
    os.makedirs(sandbox_dir, exist_ok=True)
    _chown_tree(sandbox_dir)
    marker_path = os.path.join(sandbox_dir, START_MARKER)
    try:
        os.unlink(marker_path)
    except OSError:
        pass
    mem_bytes = _parse_memory(memory_max)
    cmd, env, unit = _build_command(
        sandbox_dir, argv, timeout_s, memory_max, cpu_quota,
        tasks_max)
    limits = {"memory_max": memory_max, "cpu_quota": cpu_quota,
              "tasks_max": tasks_max, "timeout_s": timeout_s,
              "max_output_bytes": max_output_bytes,
              "max_disk_bytes": max_disk_bytes,
              "isolation": "systemd-run scope (CPUQuota, "
                           "MemoryMax, TasksMax) + unshare "
                           "mount/net/pid namespaces + "
                           "private root via pivot_root "
                           "(read-only /usr and /etc, fresh "
                           "procfs, minimal /dev, tmpfs /tmp, "
                           "read-only /source snapshot with "
                           ".local empty, /work the only "
                           "writable location), payload uid "
                           "65534, restricted env, rlimits"}
    with _semaphore:
        t0 = time.perf_counter()
        proc = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            env=env, start_new_session=True)
        out_chunks, err_chunks = [], []
        sizes = {"out": 0, "err": 0}
        breach = {"reason": None}

        def reader(stream, chunks, key):
            while True:
                data = stream.read(65536)
                if not data:
                    return
                chunks.append(data)
                sizes[key] += len(data)
                if sizes[key] > max_output_bytes and \
                        breach["reason"] is None:
                    breach["reason"] = "output_cap"

        threads = [
            threading.Thread(target=reader, args=(
                proc.stdout, out_chunks, "out"), daemon=True),
            threading.Thread(target=reader, args=(
                proc.stderr, err_chunks, "err"), daemon=True)]
        for t in threads:
            t.start()
        timed_out = False
        started_at = None
        last_watchdog = 0.0
        while True:
            if proc.poll() is not None:
                break
            now = time.perf_counter()
            if breach["reason"] is not None:
                break
            if started_at is None and \
                    os.path.exists(marker_path):
                started_at = now
            if started_at is None:
                deadline = t0 + SETUP_GRACE_S + timeout_s
            else:
                deadline = started_at + timeout_s
            if now > deadline:
                timed_out = True
                breach["reason"] = "timeout"
                break
            if now - last_watchdog >= 0.2:
                last_watchdog = now
                if _dir_size(sandbox_dir) > max_disk_bytes:
                    breach["reason"] = "disk_cap"
                    break
                # Watchdog enforcement of the memory and task
                # caps: on this host the cgroup properties do
                # not enforce (module docstring), so the
                # runner measures the real process tree and
                # kills it when a cap is exceeded.
                tasks, tree_rss = _tree_stats(proc.pid)
                if tree_rss > mem_bytes:
                    breach["reason"] = "memory"
                    break
                if tasks > tasks_max + _LAUNCHER_TASK_SLACK:
                    breach["reason"] = "tasks"
                    break
            time.sleep(0.05)
        if breach["reason"] is not None and proc.poll() is None:
            _kill_tree(proc, unit)
        try:
            proc.wait(timeout=30)
        except subprocess.TimeoutExpired:
            _kill_tree(proc, unit)
            proc.wait(timeout=30)
        for t in threads:
            t.join(timeout=10)
        wall = time.perf_counter() - t0
        stdout = b"".join(out_chunks).decode("utf-8", "replace")
        stderr = b"".join(err_chunks).decode("utf-8", "replace")
        reason = breach["reason"]
        if reason is None:
            if proc.returncode == 0:
                reason = "exit"
            elif proc.returncode in (137, -9):
                reason = "memory"
            elif proc.returncode in (124,):
                reason = "timeout"
            else:
                reason = "exit"
        return {"exit_code": proc.returncode,
                "timed_out": timed_out,
                "wall_s": round(wall, 4),
                "stdout": stdout[:max_output_bytes],
                "stderr": stderr[:max_output_bytes],
                "termination_reason": reason,
                "limits": limits,
                "scope_unit": unit + ".scope"}


def _kill_tree(proc, unit):
    """Terminate the entire process tree: kill the process
    group, then stop the systemd scope so cgroup members the
    group kill missed are also terminated."""
    try:
        os.killpg(proc.pid, 9)
    except (ProcessLookupError, PermissionError, OSError):
        pass
    try:
        subprocess.run(["systemctl", "stop", unit + ".scope"],
                       capture_output=True, timeout=20)
    except (OSError, subprocess.TimeoutExpired):
        pass
