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
- SELF-UPDATE: every UPDATE_CHECK_S (default 900 s, 15 minutes)
  it compares HEAD with origin/main. On a new version it pulls
  fast-forward only, runs the PoW engine smoke test, and only
  then restarts the miner onto the new code. If the smoke test
  fails it resets to the previous HEAD and keeps the old code
  mining. Enabled by default by scripts/autopilot.sh and the
  systemd unit; disable with BAL_AUTO_UPDATE=0 or by omitting
  --auto-update when running the module directly.

Sensitivity profile (owner-specified): heartbeat every 5 s,
watchdog crash detection on a 2 s poll, hung-miner window 300 s
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

ROOT = os.path.join(os.path.dirname(__file__), "..")
LOCAL = os.path.join(ROOT, ".local")
HB_PATH = os.path.join(LOCAL, "heartbeat.json")
LOCK_PATH = os.path.join(LOCAL, "autopilot.lock")
STOP_PATH = os.path.join(LOCAL, "autopilot.stop")
LOG_PATH = os.path.join(LOCAL, "autopilot.log")
EVIDENCE = os.path.join(ROOT, "evidence", "mainnet-live.jsonl")


def default_worker():
    """Worker name for this machine when none is given: the
    sanitized hostname, so a team of agents mining into one
    payout address never collide on a single shared name like
    bal1. Stratum worker names travel as address.worker, so the
    name is kept to lowercase letters, digits and dashes."""
    host = socket.gethostname() or "bal"
    name = re.sub(r"[^a-z0-9-]+", "-", host.lower()).strip("-")
    return (name or "bal")[:24]

POLL_S = float(os.environ.get("BAL_AP_POLL_S", "2"))
STALE_S = float(os.environ.get("BAL_AP_STALE_S", "300"))
HEARTBEAT_S = float(os.environ.get("BAL_AP_HEARTBEAT_S", "5"))
UPDATE_CHECK_S = float(os.environ.get("BAL_AP_UPDATE_CHECK_S", "900"))
BACKOFF_START_S = 2.0
BACKOFF_CAP_S = 300.0
MIN_HEALTHY_S = 60.0  # a child living this long resets backoff


def log(msg):
    line = f"{time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())} autopilot: {msg}"
    print(line, flush=True)
    try:
        with open(LOG_PATH, "a") as f:
            f.write(line + "\n")
    except OSError:
        pass


def evidence_stats():
    """(accepted_shares, last_event_epoch) from the evidence log."""
    accepted = 0
    last_epoch = 0.0
    try:
        with open(EVIDENCE, "rb") as f:
            f.seek(0, os.SEEK_END)
            size = f.tell()
            f.seek(max(0, size - 2_000_000))
            tail = f.read().decode("utf-8", "replace")
        for line in tail.splitlines():
            try:
                ev = json.loads(line)
            except ValueError:
                continue
            if ev.get("event") == "share_result" and ev.get("accepted"):
                accepted += 1
            ts = ev.get("ts")
            if ts:
                try:
                    import calendar
                    last_epoch = max(last_epoch, calendar.timegm(
                        time.strptime(ts[:19], "%Y-%m-%dT%H:%M:%S")))
                except ValueError:
                    pass
    except OSError:
        pass
    return accepted, last_epoch


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
        log(f"miner started pid={self.child.pid} cmd={' '.join(self.miner_cmd)}")

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
        log(f"update available {local[:8]} -> {remote_sha[:8]}; pulling")
        old = local
        if self._git("pull", "--ff-only", "origin", "main") is None:
            log("pull failed; keeping current version")
            return
        smoke = subprocess.run(
            [sys.executable, "tests/test_pow_engine.py"], cwd=ROOT,
            capture_output=True, timeout=300)
        if smoke.returncode != 0:
            log("smoke test FAILED on new code; rolling back")
            self._git("reset", "--hard", old)
            return
        self.version = self._git("rev-parse", "--short", "HEAD") or self.version
        log(f"updated to {self.version}; restarting miner onto new code")
        if self.child and self.child.poll() is None:
            self.child.terminate()

    def run(self):
        self.start_child()
        while not self.stop_flag:
            time.sleep(POLL_S)
            if os.path.exists(STOP_PATH):
                log("stop file present; shutting down")
                break
            self.maybe_update()
            state = self.child_state()
            if state != "running":
                lived = time.time() - self.child_started
                self.restarts += 1
                if lived >= MIN_HEALTHY_S:
                    self.backoff = BACKOFF_START_S
                log(f"miner {state} after {lived:.0f}s; restart "
                    f"#{self.restarts} in {self.backoff:.0f}s")
                time.sleep(self.backoff)
                self.backoff = min(self.backoff * 2, BACKOFF_CAP_S)
                if not self.stop_flag:
                    self.start_child()
                continue
            _acc, last_ev = evidence_stats()
            if last_ev and time.time() - last_ev > STALE_S:
                log(f"evidence stale {time.time() - last_ev:.0f}s; "
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
        log("autopilot stopped")


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
        print("another autopilot already owns this checkout; exiting")
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

    log(f"autopilot up pid={os.getpid()} version={ap_obj.version} "
        f"auto_update={auto_update} worker={worker}")
    ap_obj.run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
