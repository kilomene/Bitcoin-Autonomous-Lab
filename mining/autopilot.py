#!/usr/bin/env python3
"""BAL Autopilot: the keep-alive supervisor for mainnet mining.

One process to run. It owns the miner the way a heart owns a
rhythm:

- HEARTBEAT: writes .local/heartbeat.json every HEARTBEAT_S
  seconds with miner liveness, evidence-log freshness, accepted
  share count and restart count.
- WATCHDOG: polls the miner child every POLL_S seconds. If the
  child exits for any reason (crash, clean end of its session
  timer, host kill), the autopilot relaunches it within seconds.
  If the child lives but its evidence log goes stale past
  STALE_S (no new job event, the miner is hung), the watchdog
  kills and relaunches it. Restarts back off exponentially to a
  cap so a broken config cannot fork-bomb the host.
- SESSION ROTATION: the miner is run in bounded sessions
  (default 24 h). The moment one ends, the next begins. Mining
  is therefore continuous until the autopilot itself is stopped.
- SINGLE INSTANCE: an flock on .local/autopilot.lock guarantees
  one autopilot per checkout. A second starter exits politely.
- INCIDENT CODES: every fault, recovery action and
  refusal this supervisor records carries a stable
  numeric code from the append-only registry in
  mining/incident_registry.json (NOVA-ER-0006, register
  R-30): the log line gains a "[code] " prefix and the
  incident is counted in a code-keyed ledger published
  in the heartbeat as incident_counts, so post-incident
  audit keys on codes instead of free text. The
  registry can never kill supervision: an unresolvable
  code degrades to the plain line and the counting is
  failure-isolated (the SafeRecorder contract).
- SELF-UPDATE: every UPDATE_CHECK_S (default 900 s, 15 minutes)
  it compares HEAD with origin/main. On a new version it pulls
  fast-forward only, runs the PoW engine smoke test, and only
  then restarts the miner onto the new code. If the smoke test
  fails it resets to the previous HEAD and keeps the old code
  mining. Enabled by default by scripts/autopilot.sh and the
  systemd unit; disable with BAL_AUTO_UPDATE=0 or by omitting
  --auto-update when running the module directly.

Sensitivity profile (owner-specified): heartbeat every 5 s,
watchdog crash detection on a 1 s poll, hung-miner window 300 s
(5 minutes), update check every 15 minutes.

Stop: SIGTERM or SIGINT to the autopilot, or `touch
.local/autopilot.stop` (checked every poll). Status:
.local/heartbeat.json and `python3 mining/autopilot.py --status`.

All thresholds are constants at the top of this file and can be
overridden by environment variables BAL_AP_POLL_S, BAL_AP_STALE_S,
BAL_AP_HEARTBEAT_S, BAL_AP_UPDATE_CHECK_S.
"""

import fcntl
import json
import os
import re
import signal
import socket
import subprocess
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(
    os.path.abspath(__file__)), ".."))
try:
    from mining import incident_codes as _incident_codes
    from mining.mining_statistics import (
        SafeRecorder as _SafeRecorder)
except Exception:
    # Incident coding is an annotation layer, never a
    # precondition for supervision: if the package
    # cannot be imported, the autopilot runs uncoded.
    _incident_codes = None
    _SafeRecorder = None

ROOT = os.path.join(os.path.dirname(__file__), "..")
LOCAL = os.path.join(ROOT, ".local")
HB_PATH = os.path.join(LOCAL, "heartbeat.json")
LOCK_PATH = os.path.join(LOCAL, "autopilot.lock")
STOP_PATH = os.path.join(LOCAL, "autopilot.stop")
LOG_PATH = os.path.join(LOCAL, "autopilot.log")
EVIDENCE = os.path.join(ROOT, "evidence", "mainnet-live.jsonl")
COUNT_STATE_PATH = os.path.join(LOCAL, "evidence-count.json")


def default_worker():
    """Worker name for this machine when none is given: the
    sanitized hostname, so a team of agents mining into one
    payout address never collide on a single shared name like
    bal1. Stratum worker names travel as address.worker, so the
    name is kept to lowercase letters, digits and dashes."""
    host = socket.gethostname() or "bal"
    name = re.sub(r"[^a-z0-9-]+", "-", host.lower()).strip("-")
    return (name or "bal")[:24]

POLL_S = float(os.environ.get("BAL_AP_POLL_S", "1"))
STALE_S = float(os.environ.get("BAL_AP_STALE_S", "300"))
HEARTBEAT_S = float(os.environ.get("BAL_AP_HEARTBEAT_S", "5"))
UPDATE_CHECK_S = float(os.environ.get("BAL_AP_UPDATE_CHECK_S", "900"))
BACKOFF_START_S = 1.0
BACKOFF_CAP_S = 30.0  # no resting: a dead miner is back within 30 s worst case
MIN_HEALTHY_S = 60.0  # a child living this long resets backoff


def log(msg):
    line = f"{time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())} autopilot: {msg}"
    print(line, flush=True)
    try:
        with open(LOG_PATH, "a") as f:
            f.write(line + "\n")
    except OSError:
        pass


_INCIDENTS = _SafeRecorder() if _SafeRecorder is not None \
    else None


def log_incident(code, msg):
    """log() with the incident code for msg keyed and
    prefixed (NOVA-ER-0006, register R-30): the line
    gains a "[code] " token resolved against
    mining/incident_registry.json, and the incident is
    counted in the process incident ledger, which
    heartbeat() publishes as incident_counts. Removing
    the token restores the prior line byte-for-byte.
    Supervision can never be killed by the registry: if
    the code cannot be resolved the plain line is
    logged instead, and the counting goes through
    SafeRecorder, which swallows and counts its own
    failures (a refused code is one of them)."""
    prefix = ""
    if _incident_codes is not None:
        try:
            prefix = _incident_codes.prefix(code)
        except Exception:
            prefix = ""
    log(prefix + msg)
    if _INCIDENTS is not None:
        _INCIDENTS.record_incident(code)


_HEAD_FP_BYTES = 8192
_READ_CHUNK = 1 << 20


def _ts_epoch(ts):
    """Epoch seconds for an evidence timestamp, 0.0 if unusable."""
    try:
        import calendar
        return float(calendar.timegm(
            time.strptime(ts[:19], "%Y-%m-%dT%H:%M:%S")))
    except (ValueError, TypeError):
        return 0.0


class EvidenceCounter:
    """Incremental census of the append-only evidence log.

    EXP-037 fix. The previous implementation read only the last
    2,000,000 bytes of evidence/mainnet-live.jsonl, so once the
    log grew past that window the heartbeat's accepted-share
    total silently excluded early shares and drifted further
    from the lifetime total with every session (measured
    2026-11-15: full log 247 accepted, tail-window count 222).

    This counter streams the log exactly once from byte 0 and
    then advances incrementally over newly appended bytes only.
    Its position (byte offset, counts, last event epoch, and a
    SHA-256 fingerprint of the file's first bytes) is persisted
    atomically to a state file after every advance, so a
    restarted autopilot resumes where the last one stopped
    instead of rescanning, and steady-state cost per poll is
    one stat plus reading only the bytes appended since the
    previous poll. Memory use is one read chunk plus one
    partial line, independent of log size.

    Rotation and replacement handling: if the file shrinks
    below the recorded offset, or its first bytes no longer
    match the recorded fingerprint, the log is treated as a
    new file and recounted from byte 0. A partial final line
    (a writer caught mid-append) is never consumed: the offset
    advances only past complete newline-terminated lines, and
    the partial line is recounted once it is completed. A
    missing log resets the census to zero. A corrupt or
    unreadable state file falls back to a full recount. One
    replacement shape is undetectable by construction and is
    documented rather than hidden: a new file that is at least
    as large as the old offset and whose first _HEAD_FP_BYTES
    bytes are identical to the old file's would be mistaken
    for appends; no rotation scheme in use here (rename and
    recreate, or truncate) produces that shape.
    """

    def __init__(self, path=EVIDENCE, state_path=COUNT_STATE_PATH):
        self.path = path
        self.state_path = state_path
        self.accepted = 0
        self.rejected = 0
        self.share_results = 0
        self.last_epoch = 0.0
        self.offset = 0
        self._head_len = 0
        self._head_sha = None
        self._loaded = False

    def _reset(self):
        self.accepted = 0
        self.rejected = 0
        self.share_results = 0
        self.last_epoch = 0.0
        self.offset = 0
        self._head_len = 0
        self._head_sha = None

    def _load_state(self):
        self._loaded = True
        try:
            with open(self.state_path) as f:
                st = json.load(f)
            self.accepted = int(st["accepted"])
            self.rejected = int(st.get("rejected", 0))
            self.share_results = int(st.get("share_results", 0))
            self.last_epoch = float(st.get("last_epoch", 0.0))
            self.offset = int(st["offset"])
            self._head_len = int(st.get("head_len", 0))
            self._head_sha = st.get("head_sha")
        except (OSError, ValueError, KeyError, TypeError):
            self._reset()

    def _save_state(self):
        st = {
            "version": 1,
            "accepted": self.accepted,
            "rejected": self.rejected,
            "share_results": self.share_results,
            "last_epoch": self.last_epoch,
            "offset": self.offset,
            "head_len": self._head_len,
            "head_sha": self._head_sha,
        }
        try:
            os.makedirs(os.path.dirname(self.state_path) or ".",
                        exist_ok=True)
            tmp = self.state_path + ".tmp"
            with open(tmp, "w") as f:
                json.dump(st, f)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, self.state_path)
        except OSError:
            pass

    def _process_line(self, raw):
        try:
            ev = json.loads(raw.decode("utf-8", "replace"))
        except ValueError:
            return
        if not isinstance(ev, dict):
            return
        if ev.get("event") == "share_result":
            self.share_results += 1
            if ev.get("accepted"):
                self.accepted += 1
            else:
                self.rejected += 1
        ts = ev.get("ts")
        if ts:
            epoch = _ts_epoch(ts)
            if epoch > self.last_epoch:
                self.last_epoch = epoch

    def _scan_from_offset(self, f):
        """Consume complete lines from self.offset onward and
        advance the offset past them. Returns bytes consumed."""
        f.seek(self.offset)
        pending = b""
        consumed = 0
        while True:
            chunk = f.read(_READ_CHUNK)
            if not chunk:
                break
            parts = (pending + chunk).split(b"\n")
            pending = parts.pop()
            for raw in parts:
                consumed += len(raw) + 1
                self._process_line(raw)
        self.offset += consumed
        return consumed

    def update(self):
        """Advance over any new log bytes. Returns
        (accepted_shares, last_event_epoch) over the WHOLE log,
        the same contract the old tail-window code claimed."""
        import hashlib
        if not self._loaded:
            self._load_state()
        try:
            size = os.path.getsize(self.path)
        except OSError:
            self._reset()
            self._save_state()
            return self.accepted, self.last_epoch
        rescan = False
        if size < self.offset:
            rescan = True
        elif self._head_sha is not None and self._head_len > 0:
            try:
                with open(self.path, "rb") as f:
                    head = f.read(self._head_len)
            except OSError:
                head = b""
            if hashlib.sha256(head).hexdigest() != self._head_sha:
                rescan = True
        if rescan:
            keep_epoch = 0.0
            self._reset()
            self.last_epoch = keep_epoch
        changed = rescan
        try:
            with open(self.path, "rb") as f:
                if self._scan_from_offset(f) > 0:
                    changed = True
                head_len = min(size, _HEAD_FP_BYTES)
                if rescan or head_len != self._head_len:
                    f.seek(0)
                    head = f.read(head_len)
                    self._head_len = len(head)
                    self._head_sha = hashlib.sha256(
                        head).hexdigest()
                    changed = True
        except OSError:
            pass
        if changed:
            self._save_state()
        return self.accepted, self.last_epoch


_default_counter = None


def evidence_stats(path=None, state_path=None):
    """(accepted_shares, last_event_epoch) from the evidence
    log, counted over the whole log via EvidenceCounter. With
    no arguments, uses the production paths and a shared
    counter so repeated polls stay incremental."""
    global _default_counter
    if path is None and state_path is None:
        if _default_counter is None:
            _default_counter = EvidenceCounter()
        return _default_counter.update()
    counter = EvidenceCounter(
        path or EVIDENCE,
        state_path or ((path or EVIDENCE) + ".count.json"))
    return counter.update()


def acquire_lock():
    os.makedirs(LOCAL, exist_ok=True)
    fh = open(LOCK_PATH, "w")
    try:
        fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        return None
    fh.write(str(os.getpid()))
    fh.flush()
    return fh


class Autopilot:
    def __init__(self, miner_cmd, auto_update=False):
        self.miner_cmd = miner_cmd
        self.auto_update = auto_update
        self.child = None
        self.child_started = 0.0
        self.restarts = 0
        self.backoff = BACKOFF_START_S
        self.stop_flag = False
        self.last_update_check = 0.0
        self.last_hb = 0.0
        self.version = self._git("rev-parse", "--short", "HEAD") or "unknown"

    def _git(self, *args):
        try:
            out = subprocess.run(["git", "-C", ROOT] + list(args),
                                 capture_output=True, text=True, timeout=60)
            return out.stdout.strip() if out.returncode == 0 else None
        except Exception:
            return None

    def start_child(self):
        out = open(os.path.join(LOCAL, "miner.out"), "a")
        self.child = subprocess.Popen(self.miner_cmd, cwd=ROOT,
                                      stdout=out, stderr=subprocess.STDOUT)
        self.child_started = time.time()
        log_incident(1003, f"miner started pid={self.child.pid} "
                           f"cmd={' '.join(self.miner_cmd)}")

    def child_state(self):
        if self.child is None:
            return "down"
        rc = self.child.poll()
        if rc is None:
            return "running"
        return f"exited rc={rc}"

    def heartbeat(self):
        accepted, last_ev = evidence_stats()
        state = {
            "ts": time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
            "autopilot_pid": os.getpid(),
            "version": self.version,
            "miner_pid": self.child.pid if self.child else None,
            "miner_state": self.child_state(),
            "miner_uptime_s": round(time.time() - self.child_started, 1)
            if self.child and self.child_state() == "running" else 0,
            "restarts": self.restarts,
            "shares_accepted_total": accepted,
            "evidence_age_s": round(time.time() - last_ev, 1) if last_ev else None,
        }
        if _INCIDENTS is not None:
            state["incident_counts"] = _INCIDENTS \
                .incident_snapshot()["totals"]
        tmp = HB_PATH + ".tmp"
        with open(tmp, "w") as f:
            json.dump(state, f, indent=2)
        os.replace(tmp, HB_PATH)

    def maybe_update(self):
        if not self.auto_update:
            return
        now = time.time()
        if now - self.last_update_check < UPDATE_CHECK_S:
            return
        self.last_update_check = now
        remote = self._git("ls-remote", "origin", "main")
        local = self._git("rev-parse", "HEAD")
        if not remote or not local:
            return
        remote_sha = remote.split()[0]
        if remote_sha == local:
            return
        log_incident(3001, f"update available {local[:8]} -> "
                           f"{remote_sha[:8]}; pulling")
        old = local
        if self._git("pull", "--ff-only", "origin", "main") is None:
            log_incident(3002, "pull failed; keeping current "
                               "version")
            return
        smoke = subprocess.run(
            [sys.executable, "tests/test_pow_engine.py"], cwd=ROOT,
            capture_output=True, timeout=300)
        if smoke.returncode != 0:
            log_incident(3003, "smoke test FAILED on new code; "
                               "rolling back")
            self._git("reset", "--hard", old)
            return
        self.version = self._git("rev-parse", "--short", "HEAD") or self.version
        log_incident(3004, f"updated to {self.version}; "
                           f"restarting miner onto new code")
        if self.child and self.child.poll() is None:
            self.child.terminate()

    def run(self):
        self.start_child()
        while not self.stop_flag:
            time.sleep(POLL_S)
            if os.path.exists(STOP_PATH):
                log_incident(2003, "stop file present; "
                                   "shutting down")
                break
            self.maybe_update()
            state = self.child_state()
            if state != "running":
                lived = time.time() - self.child_started
                self.restarts += 1
                if lived >= MIN_HEALTHY_S:
                    self.backoff = BACKOFF_START_S
                log_incident(1001, f"miner {state} after "
                                   f"{lived:.0f}s; restart "
                                   f"#{self.restarts} in "
                                   f"{self.backoff:.0f}s")
                time.sleep(self.backoff)
                self.backoff = min(self.backoff * 2, BACKOFF_CAP_S)
                if not self.stop_flag:
                    self.start_child()
                continue
            _acc, last_ev = evidence_stats()
            if last_ev and time.time() - last_ev > STALE_S:
                log_incident(1002, f"evidence stale "
                                   f"{time.time() - last_ev:.0f}s; "
                                   f"killing hung miner")
                self.child.kill()
                continue
            if time.time() - self.last_hb >= HEARTBEAT_S:
                self.last_hb = time.time()
                self.heartbeat()
        if self.child and self.child.poll() is None:
            self.child.terminate()
            try:
                self.child.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.child.kill()
        self.heartbeat()
        log_incident(2002, "autopilot stopped")


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--duration", type=int, default=86400,
                    help="per-session miner duration in seconds")
    ap.add_argument("--address", default=None)
    ap.add_argument("--worker", default=None,
                    help="pool worker name; default is this "
                         "machine's hostname (see default_worker)")
    ap.add_argument("--auto-update", action="store_true")
    ap.add_argument("--status", action="store_true",
                    help="print heartbeat and exit")
    args = ap.parse_args()

    if args.status:
        try:
            print(open(HB_PATH).read())
        except OSError:
            print("no heartbeat yet (autopilot not running?)")
        return 0

    lock = acquire_lock()
    if lock is None:
        msg = "another autopilot already owns this checkout; " \
              "exiting"
        if _incident_codes is not None:
            try:
                msg = _incident_codes.prefix(2004) + msg
            except Exception:
                pass
        print(msg)
        return 0
    if os.path.exists(STOP_PATH):
        os.remove(STOP_PATH)

    override = os.environ.get("BAL_AP_MINER_CMD")
    worker = args.worker or os.environ.get("BAL_WORKER") \
        or default_worker()
    if override:
        miner_cmd = json.loads(override)
    else:
        miner_cmd = [sys.executable, os.path.join("mining", "mainnet_live.py"),
                     "--duration", str(args.duration), "--worker", worker]
        if args.address:
            miner_cmd += ["--address", args.address]
    auto_update = args.auto_update or os.environ.get("BAL_AUTO_UPDATE") == "1"
    ap_obj = Autopilot(miner_cmd, auto_update=auto_update)

    def on_signal(signum, frame):
        ap_obj.stop_flag = True
    signal.signal(signal.SIGTERM, on_signal)
    signal.signal(signal.SIGINT, on_signal)

    log_incident(2001, f"autopilot up pid={os.getpid()} "
                       f"version={ap_obj.version} "
                       f"auto_update={auto_update} worker={worker}")
    ap_obj.run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
