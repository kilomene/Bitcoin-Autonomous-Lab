#!/usr/bin/env python3
"""Solo cutover: move mainnet mining from public-pool.io to
our own solo server, once, automatically, when the node is
ready. See docs/SOLO_CUTOVER.md for the full design.

    python3 scripts/solo_cutover.py check     # READY or NOT_READY
    python3 scripts/solo_cutover.py fire      # do the switch
    python3 scripts/solo_cutover.py rollback  # switch back
    python3 scripts/solo_cutover.py status    # human summary

fire is idempotent and guarded by a marker file,
.local/solo-cutover.json. It acts only when ALL of these
hold: the mainnet node reports initialblockdownload false
with blocks caught up to headers (within 2), the miner is
healthy under the autopilot, and the endpoint config still
points at the pool. It then starts the solo server under
systemd supervision, proves the server live with a real
Stratum subscribe against the node tip, flips
.local/mining-endpoint.json to mode "solo", restarts the
miner child (the autopilot respawns it onto the new
endpoint), and verifies from the server's own per-worker
accounting that shares are being accepted. Any verification
failure rolls the miner back to the pool automatically and
records the outcome in the marker. Terminal marker states
(complete, rolled_back) make later runs no-ops: re-arming
is a deliberate human act (edit the marker), never an
accident of scheduling.
"""

import json
import os
import signal
import socket
import subprocess
import sys
import time
from datetime import datetime, timezone

ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, ROOT)

from mining import endpoint_config
from mining.autopilot import default_worker
from mining.stratum_client import swap_words

LOCAL = os.path.join(ROOT, ".local")
HEARTBEAT = os.path.join(LOCAL, "heartbeat.json")
MARKER = os.path.join(LOCAL, "solo-cutover.json")
SOLO_STATUS = os.path.join(LOCAL, "solo-status.json")
SOLO_UNIT = "/etc/systemd/system/bal-solo.service"
SOLO_UNIT_NAME = "bal-solo.service"
EVIDENCE = os.path.join(ROOT, "evidence", "mainnet-live.jsonl")

VERIFY_WINDOW_S = 420
ROLLBACK_WINDOW_S = 240
SOLO_START_WINDOW_S = 240


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def read_json(path):
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def write_marker(marker):
    tmp = MARKER + ".tmp"
    with open(tmp, "w") as f:
        json.dump(marker, f, indent=2)
        f.write("\n")
    os.replace(tmp, MARKER)


def marker_update(status, **fields):
    marker = read_json(MARKER) or {"status": "armed", "history": []}
    marker["status"] = status
    marker.update(fields)
    marker.setdefault("history", []).append(
        {"ts": now_iso(), "status": status, **fields})
    write_marker(marker)
    return marker


def node_info():
    try:
        return endpoint_config.load_mainnet_rpc().call(
            "getblockchaininfo")
    except Exception:
        return None


def node_ready(info):
    """The task's sync test: out of initial block download and
    blocks caught up to headers (within 2)."""
    if not info:
        return False, "node RPC unreachable"
    if info.get("initialblockdownload"):
        return False, (f"node in initial block download "
                       f"({info.get('blocks')} of "
                       f"{info.get('headers')} headers)")
    gap = int(info.get("headers", 0)) - int(info.get("blocks", 0))
    if gap > 2:
        return False, f"blocks lag headers by {gap}"
    return True, "node synced"


def heartbeat_state():
    hb = read_json(HEARTBEAT)
    if not hb:
        return None, "no heartbeat file"
    ts = hb.get("ts", "")
    try:
        beat = datetime.strptime(
            ts[:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc)
        age = (datetime.now(timezone.utc) - beat).total_seconds()
    except ValueError:
        return hb, "heartbeat timestamp unparsable"
    if age > 60:
        return hb, f"heartbeat stale ({age:.0f}s old)"
    if hb.get("miner_state") != "running":
        return hb, f"miner_state is {hb.get('miner_state')!r}"
    return hb, "miner healthy"


def preconditions():
    """(ready, reasons, context) for firing the cutover."""
    reasons = []
    info = node_info()
    ok, why = node_ready(info)
    if not ok:
        reasons.append(why)
    hb, why = heartbeat_state()
    if hb is None or "healthy" not in why:
        reasons.append(why)
    cfg = endpoint_config.load_config()
    if cfg["mode"] != "pool":
        reasons.append(
            f"endpoint mode is {cfg['mode']!r}, expected 'pool' "
            f"(cutover already fired, or config edited by hand)")
    return not reasons, reasons, {"info": info, "heartbeat": hb,
                                  "config": cfg}


def evidence_since(ts_epoch, tail_bytes=4_000_000):
    events = []
    try:
        with open(EVIDENCE, "rb") as f:
            f.seek(0, os.SEEK_END)
            f.seek(max(0, f.tell() - tail_bytes))
            tail = f.read().decode("utf-8", "replace")
    except OSError:
        return events
    for line in tail.splitlines():
        try:
            ev = json.loads(line)
            ts = datetime.fromisoformat(ev["ts"]).timestamp()
        except (ValueError, KeyError):
            continue
        if ts >= ts_epoch:
            events.append(ev)
    return events


def restart_miner_child():
    """SIGTERM the miner the autopilot is supervising; the
    autopilot respawns it within seconds onto whatever the
    endpoint config then says. Returns the old pid."""
    hb = read_json(HEARTBEAT) or {}
    pid = hb.get("miner_pid")
    if pid:
        try:
            os.kill(int(pid), signal.SIGTERM)
        except (ProcessLookupError, PermissionError, ValueError):
            pass
    return pid


def wait_for(pred, timeout_s, interval_s=5, desc=""):
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        val = pred()
        if val:
            return val
        time.sleep(interval_s)
    return None


def solo_status_fresh(max_age_s=20):
    st = read_json(SOLO_STATUS)
    if not st:
        return None
    try:
        ts = datetime.strptime(
            st["ts"][:19], "%Y-%m-%dT%H:%M:%S").replace(
                tzinfo=timezone.utc)
        age = (datetime.now(timezone.utc) - ts).total_seconds()
    except (ValueError, KeyError):
        return None
    return st if age <= max_age_s else None


def ensure_solo_running():
    """Start the solo server under supervision. Returns the
    supervision mode string. systemd is the design (the unit
    restarts it on failure and on VM replacement once
    installed); a nohup fallback keeps the cutover possible on
    a machine without systemd control, and says so loudly."""
    if solo_status_fresh():
        return "already-running"
    systemctl = "/usr/bin/systemctl"
    if os.path.exists(systemctl):
        if not os.path.exists(SOLO_UNIT):
            r = subprocess.run(
                ["bash", "scripts/autopilot.sh",
                 "install-solo-service"],
                cwd=ROOT, capture_output=True, text=True,
                timeout=120)
            if r.returncode != 0:
                print(f"solo-cutover: unit install failed: "
                      f"{r.stdout} {r.stderr}", flush=True)
        if os.path.exists(SOLO_UNIT):
            subprocess.run([systemctl, "start", SOLO_UNIT_NAME],
                           capture_output=True, timeout=120)
            return "systemd"
    print("solo-cutover: WARNING: systemd supervision "
          "unavailable; starting the solo runner under nohup. "
          "It will not restart on failure or reboot until the "
          "bal-solo unit is installed.", flush=True)
    out = open(os.path.join(LOCAL, "solo-server.out"), "a")
    proc = subprocess.Popen(
        [sys.executable, os.path.join("mining", "solo_mainnet.py")],
        cwd=ROOT, stdout=out, stderr=subprocess.STDOUT,
        start_new_session=True)
    with open(os.path.join(LOCAL, "solo-server.pid"), "w") as f:
        f.write(str(proc.pid))
    return "nohup-fallback"


def solo_smoke(host, port, tip_hash, expect_difficulty, user):
    """A real Stratum handshake against the running server:
    subscribe, authorize, and require a mining.notify whose
    prevhash is the node tip (in Stratum word-swapped form)
    and a set_difficulty equal to the configured share
    difficulty. Proves the server is serving THIS node's tip,
    not a stale or foreign template."""
    expect_prev = swap_words(bytes.fromhex(tip_hash)[::-1]).hex()
    try:
        sock = socket.create_connection((host, port), timeout=15)
    except OSError as exc:
        return False, f"cannot connect to solo server: {exc}"
    f = sock.makefile("rwb")
    got_diff = None
    got_notify = None
    try:
        f.write(b'{"id": 1, "method": "mining.subscribe", '
                b'"params": ["bal-cutover-check"]}\n')
        f.write(json.dumps(
            {"id": 2, "method": "mining.authorize",
             "params": [user, "x"]}).encode() + b"\n")
        f.flush()
        sock.settimeout(30)
        deadline = time.time() + 30
        while time.time() < deadline and got_notify is None:
            line = f.readline()
            if not line:
                break
            msg = json.loads(line)
            if msg.get("method") == "mining.set_difficulty":
                got_diff = msg["params"][0]
            elif msg.get("method") == "mining.notify":
                got_notify = msg["params"]
    except (OSError, ValueError) as exc:
        return False, f"smoke handshake failed: {exc}"
    finally:
        try:
            sock.close()
        except OSError:
            pass
    if got_notify is None:
        return False, "no mining.notify received from solo server"
    if got_diff is None or abs(float(got_diff)
                               - float(expect_difficulty)) > 1e-9:
        return False, (f"set_difficulty {got_diff!r} != configured "
                       f"{expect_difficulty!r}")
    if got_notify[1] != expect_prev:
        return False, (f"notify prevhash {got_notify[1][:16]}... "
                       f"!= node tip {expect_prev[:16]}...")
    return True, "solo server live on node tip at configured difficulty"


def miner_worker_name(cfg):
    return f"{cfg['payout_address']}.{default_worker()}"


def verify_on_solo(cfg, old_pid, flip_epoch):
    """Post-flip verification from primary sources: the
    autopilot heartbeat (new miner process), the miner's
    evidence log (it connected to the solo endpoint), and the
    solo server's own per-worker accounting (shares accepted,
    and still arriving)."""
    worker = miner_worker_name(cfg)

    def new_miner():
        hb, why = heartbeat_state()
        if hb and hb.get("miner_pid") not in (None, old_pid) \
                and "healthy" in why:
            return hb
        return None
    if not wait_for(new_miner, 180, desc="miner respawn"):
        return False, "miner did not respawn under the autopilot"

    def connected():
        for ev in evidence_since(flip_epoch):
            if ev.get("event") == "connected" and ev.get(
                    "pool") == f"{cfg['solo']['host']}:{cfg['solo']['port']}":
                return ev
        return None
    if not wait_for(connected, 120, desc="miner connected to solo"):
        return False, "miner never connected to the solo endpoint"

    def shares_flowing():
        st = solo_status_fresh(30)
        if not st:
            return None
        rec = st.get("workers", {}).get(worker)
        if rec and rec.get("accepted", 0) >= 3 \
                and rec.get("last_share_at"):
            return rec
        return None
    rec = wait_for(shares_flowing, VERIFY_WINDOW_S,
                   desc="solo shares accepted")
    if not rec:
        return False, (f"solo server shows no accepted shares "
                       f"from worker {worker}")
    first = rec["accepted"]
    time.sleep(45)
    st = solo_status_fresh(30)
    rec2 = (st or {}).get("workers", {}).get(worker, {})
    age = (time.time() - rec2["last_share_at"]) \
        if rec2.get("last_share_at") else None
    if not (rec2.get("accepted", 0) > first
            or (age is not None and age <= 45)):
        return False, "solo shares stopped arriving after first burst"
    return True, (f"worker {worker} accepted "
                  f"{rec2.get('accepted')} solo shares and counting")


def do_rollback(reason):
    print(f"solo-cutover: ROLLING BACK: {reason}", flush=True)
    endpoint_config.set_mode("pool")
    flip_epoch = time.time()
    old_pid = restart_miner_child()

    def back_on_pool():
        hb, why = heartbeat_state()
        if not hb or "healthy" not in why \
                or hb.get("miner_pid") in (None, old_pid):
            return None
        for ev in evidence_since(flip_epoch):
            if ev.get("event") == "connected" and ev.get(
                    "pool") == "public-pool.io:21496":
                return hb
        return None
    hb = wait_for(back_on_pool, ROLLBACK_WINDOW_S,
                  desc="miner back on pool")
    marker_update("rolled_back", reason=reason,
                  rollback_verified=bool(hb))
    print(f"ROLLED_BACK reason={reason} verified={bool(hb)}",
          flush=True)
    return 0 if hb else 1


def cmd_check():
    marker = read_json(MARKER)
    if marker and marker.get("status") in ("complete", "rolled_back"):
        print(marker["status"].upper())
        print(f"terminal marker: {marker.get('status')} "
              f"(see {MARKER})")
        return 0
    ready, reasons, _ctx = preconditions()
    if ready:
        print("READY")
        print("node synced, miner healthy, endpoint still on pool")
        return 0
    print("NOT_READY")
    for r in reasons:
        print(f"- {r}")
    return 3


def cmd_fire():
    marker = read_json(MARKER)
    if marker and marker.get("status") == "complete":
        print("ALREADY_COMPLETE")
        return 0
    if marker and marker.get("status") == "rolled_back":
        print("ALREADY_ROLLED_BACK (re-arm by editing the marker)")
        return 0
    ready, reasons, ctx = preconditions()
    if not ready:
        print("NOT_READY")
        for r in reasons:
            print(f"- {r}")
        return 3
    cfg = ctx["config"]
    marker_update("firing", started=now_iso())
    try:
        supervision = ensure_solo_running()
    except Exception as exc:
        marker_update("armed", abort=f"solo start failed: {exc}")
        print(f"ABORTED_PRE_FLIP solo start failed: {exc}",
              flush=True)
        return 1
    marker_update("firing", supervision=supervision)

    def server_on_tip():
        st = solo_status_fresh()
        if not st or not st.get("node_ready"):
            return None
        job = st.get("current_job") or {}
        info = node_info()
        if info and job.get("prevhash") == info.get("bestblockhash"):
            return st
        return None
    if not wait_for(server_on_tip, SOLO_START_WINDOW_S,
                    desc="solo server serving node tip"):
        marker_update("armed",
                      abort="solo server did not serve the node "
                            "tip in time; miner untouched")
        print("ABORTED_PRE_FLIP solo server not on node tip; "
              "miner untouched", flush=True)
        return 1
    info = node_info()
    ok, why = solo_smoke(cfg["solo"]["host"],
                         int(cfg["solo"]["port"]),
                         info["bestblockhash"],
                         float(cfg["solo"]["share_difficulty"]),
                         f"{cfg['payout_address']}.cutover-check")
    if not ok:
        marker_update("armed", abort=f"smoke failed: {why}")
        print(f"ABORTED_PRE_FLIP smoke failed: {why}", flush=True)
        return 1
    print(f"solo-cutover: self-check passed: {why}", flush=True)

    endpoint_config.set_mode("solo")
    flip_epoch = time.time()
    old_pid = restart_miner_child()
    marker_update("firing", flipped_at=now_iso(),
                  old_miner_pid=old_pid)
    print(f"solo-cutover: endpoint flipped to solo; miner "
          f"{old_pid} signalled; verifying", flush=True)
    ok, why = verify_on_solo(cfg, old_pid, flip_epoch)
    if not ok:
        return do_rollback(why)
    marker_update("complete", verified=why, supervision=supervision,
                  completed_at=now_iso())
    print(f"CUTOVER_COMPLETE {why}", flush=True)
    return 0


def cmd_status():
    marker = read_json(MARKER)
    info = node_info()
    ok, why = node_ready(info)
    hb, hb_why = heartbeat_state()
    cfg = endpoint_config.load_config()
    st = solo_status_fresh(3600)
    print(f"cutover marker: "
          f"{marker.get('status') if marker else 'absent (armed)'}")
    print(f"node: {why}")
    print(f"miner: {hb_why}")
    print(f"endpoint mode: {cfg['mode']} "
          f"(pool {cfg['pool']['host']}:{cfg['pool']['port']}, "
          f"solo {cfg['solo']['host']}:{cfg['solo']['port']} "
          f"diff {cfg['solo']['share_difficulty']})")
    print(f"solo server status: "
          f"{'fresh file present' if st else 'not running (no fresh status)'}")
    if st:
        print(f"  shares accepted {st.get('shares_accepted')}, "
              f"rejected {st.get('shares_rejected')}, workers "
              f"{list(st.get('workers', {}))}")
    return 0


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
    if cmd == "check":
        return cmd_check()
    if cmd == "fire":
        return cmd_fire()
    if cmd == "rollback":
        marker = read_json(MARKER)
        if marker and marker.get("status") == "complete":
            return do_rollback("manual rollback after completed "
                               "cutover")
        endpoint_config.set_mode("pool")
        restart_miner_child()
        marker_update("rolled_back", reason="manual rollback")
        print("ROLLED_BACK reason=manual rollback", flush=True)
        return 0
    if cmd == "status":
        return cmd_status()
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main())
