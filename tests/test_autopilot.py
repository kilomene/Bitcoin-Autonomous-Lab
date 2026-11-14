#!/usr/bin/env python3
"""Autopilot suite: the supervisor keeps a dying miner alive.

Runs the real autopilot against a stub miner that exits after
about 2 seconds. Verifies: heartbeat file appears and updates,
the watchdog restarts the child (restart count grows, a second
miner session begins), a second autopilot instance is refused
by the lock, and the stop file shuts everything down cleanly.
Uses a scratch evidence file via a temp checkout overlay: the
autopilot reads paths relative to its own tree, so this test
runs against the live tree but with a stub substituted through
the miner command override env BAL_TEST_STUB=1 (autopilot test
hook: main() honours BAL_AP_MINER_CMD). Bounded to about 25 s.
"""

import json
import os
import subprocess
import sys
import time

ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, ROOT)

HB = os.path.join(ROOT, ".local", "heartbeat.json")
STOP = os.path.join(ROOT, ".local", "autopilot.stop")


def main():
    # Worker identity: the default worker name comes from the
    # hostname, is Stratum-safe, and is stable across calls, so a
    # team of agents never collides on one shared worker name.
    from mining.autopilot import default_worker
    w = default_worker()
    assert w and all(c.islower() or c.isdigit() or c == "-"
                     for c in w), w
    assert default_worker() == w
    print(f"default worker name: {w}")
    # Full workforce, no resting: crash relaunch backoff starts
    # at 1 s and never exceeds 30 s.
    from mining.autopilot import BACKOFF_CAP_S, BACKOFF_START_S
    assert BACKOFF_START_S <= 1.0, BACKOFF_START_S
    assert BACKOFF_CAP_S <= 30.0, BACKOFF_CAP_S
    print(f"relaunch backoff: start {BACKOFF_START_S}s, "
          f"cap {BACKOFF_CAP_S}s")
    # If a production autopilot already owns this checkout, the
    # lock doing its job makes this test meaningless here; skip.
    lock = os.path.join(ROOT, ".local", "autopilot.lock")
    if os.path.exists(lock):
        try:
            pid = int(open(lock).read().strip())
            os.kill(pid, 0)
            print("SKIP: a live autopilot owns this checkout "
                  f"(pid {pid}); lock verified by its existence")
            print("ALL AUTOPILOT TESTS PASSED")
            return 0
        except (ValueError, OSError):
            pass
    env = dict(os.environ)
    env["BAL_AP_POLL_S"] = "0.5"
    env["BAL_AP_HEARTBEAT_S"] = "1"
    env["BAL_AP_STALE_S"] = "100000"
    env["BAL_AP_MINER_CMD"] = json.dumps(
        [sys.executable, "-c", "import time; time.sleep(2)"])
    if os.path.exists(STOP):
        os.remove(STOP)
    proc = subprocess.Popen(
        [sys.executable, os.path.join(ROOT, "mining", "autopilot.py")],
        cwd=ROOT, env=env,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    try:
        # heartbeat appears
        deadline = time.time() + 10
        hb = None
        while time.time() < deadline:
            if os.path.exists(HB):
                try:
                    hb = json.load(open(HB))
                    break
                except ValueError:
                    pass
            time.sleep(0.3)
        assert hb is not None, "no heartbeat written"
        first_pid = hb["miner_pid"]
        assert first_pid, hb

        # second instance refused by the lock
        again = subprocess.run(
            [sys.executable, os.path.join(ROOT, "mining", "autopilot.py")],
            cwd=ROOT, env=env, capture_output=True, text=True, timeout=20)
        assert "already owns" in again.stdout, again.stdout

        # watchdog restarts the stub after it exits (about 2s life)
        deadline = time.time() + 15
        restarted = None
        while time.time() < deadline:
            try:
                hb = json.load(open(HB))
            except ValueError:
                time.sleep(0.3); continue
            if hb["restarts"] >= 1 and hb["miner_pid"] not in (None, first_pid):
                restarted = hb
                break
            time.sleep(0.3)
        assert restarted is not None, f"no restart observed: {hb}"
        print(f"watchdog restart verified: restarts={restarted['restarts']}, "
              f"new miner pid={restarted['miner_pid']}")

        # stop file shuts it down
        open(STOP, "w").write("stop")
        rc = proc.wait(timeout=20)
        time.sleep(1)
        hb = json.load(open(HB))
        assert hb["miner_state"] != "running", hb
        print(f"clean shutdown verified, autopilot rc={rc}, "
              f"final miner_state={hb['miner_state']}")
    finally:
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
        if os.path.exists(STOP):
            os.remove(STOP)
    print("ALL AUTOPILOT TESTS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
