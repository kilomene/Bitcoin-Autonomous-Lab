#!/usr/bin/env python3
"""Mainnet runner for the lab's own solo Stratum server.

Serves mining/solo_server.py against our own pruned mainnet
node (.local/mainnet, RPC 8332) and pays the lab address. This
is the cutover target of docs/SOLO_CUTOVER.md: it is started by
the bal-solo systemd unit when the cutover fires, and by
nothing before that. Run manually only if you mean it:

    python3 mining/solo_mainnet.py

Behaviour that matters:

- Chain is verified twice: here at startup (the node's
  getblockchaininfo chain must be "main", and the node-config
  must agree) and inside SoloServer on every job refresh.
- While the node is in initial block download the server
  refuses work with a clear log line instead of serving stale
  templates; the JobRefresher announces state changes.
- A fresh job is broadcast whenever the tip moves (checked
  every 2 s) or the current job ages past 120 s.
- Status is written atomically to .local/solo-status.json
  every 5 s: node state, current job, per-worker share counts.
  The cutover script verifies the switch from this file plus a
  live subscribe smoke test.
"""

import argparse
import json
import os
import signal
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from mining import endpoint_config
from mining.solo_server import (JobRefresher, SoloServer,
                                SoloTCPServer, VarDiffController)

ROOT = os.path.join(os.path.dirname(__file__), "..")
STATUS_PATH = os.path.join(ROOT, ".local", "solo-status.json")
EXPECTED_CHAIN = "main"


def log(msg):
    line = (f"{time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())} "
            f"solo-mainnet: {msg}")
    print(line, flush=True)


def write_status(solo, node_info):
    st = solo.stats()
    st["ts"] = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
    if node_info:
        st["node"] = {
            "chain": node_info.get("chain"),
            "blocks": node_info.get("blocks"),
            "headers": node_info.get("headers"),
            "initialblockdownload": node_info.get(
                "initialblockdownload"),
            "tip": node_info.get("bestblockhash"),
        }
        st["node_ready"] = (
            node_info.get("chain") == EXPECTED_CHAIN
            and not node_info.get("initialblockdownload"))
    else:
        st["node"] = None
        st["node_ready"] = False
    tmp = STATUS_PATH + ".tmp"
    with open(tmp, "w") as f:
        json.dump(st, f, indent=2)
    os.replace(tmp, STATUS_PATH)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bind", default=None)
    ap.add_argument("--port", type=int, default=None)
    ap.add_argument("--share-difficulty", type=float, default=None)
    ap.add_argument("--address", default=None)
    args = ap.parse_args()

    cfg = endpoint_config.load_config()
    solo_cfg = cfg["solo"]
    bind = args.bind or solo_cfg["host"]
    port = args.port or int(solo_cfg["port"])
    share_difficulty = (args.share_difficulty
                        if args.share_difficulty is not None
                        else float(solo_cfg["share_difficulty"]))
    payout = args.address or cfg["payout_address"]

    rpc = endpoint_config.load_mainnet_rpc()
    info = rpc.call("getblockchaininfo")
    if info.get("chain") != EXPECTED_CHAIN:
        log(f"FATAL: node chain is {info.get('chain')!r}, expected "
            f"{EXPECTED_CHAIN!r}; not starting")
        return 2
    log(f"node chain {info['chain']}, blocks {info['blocks']} of "
        f"headers {info['headers']}, ibd="
        f"{info.get('initialblockdownload')}")

    # Vardiff (Stage 6): enabled only when the endpoint config
    # says so (default off; see mining/endpoint_config.py). The
    # controller's initial difficulty is the configured share
    # difficulty, the single source D10 was closed on. With
    # vardiff off the server is constructed exactly as before.
    vd_cfg = endpoint_config.solo_vardiff_config(cfg)
    if vd_cfg["enabled"]:
        vardiff = VarDiffController(
            target_interval=float(vd_cfg["target_interval"]),
            floor=float(vd_cfg["floor"]),
            ceiling=float(vd_cfg["ceiling"]),
            initial=share_difficulty,
            ema_alpha=float(vd_cfg["ema_alpha"]),
            deadband=float(vd_cfg["deadband"]),
            up_hysteresis_s=float(vd_cfg["up_hysteresis_s"]),
            up_confirmations=int(vd_cfg["up_confirmations"]),
            max_up_factor=float(vd_cfg["max_up_factor"]),
            max_down_factor=float(vd_cfg["max_down_factor"]),
            decay_after_s=float(vd_cfg["decay_after_s"]),
            decay_factor=float(vd_cfg["decay_factor"]))
        solo = SoloServer(rpc, payout, vardiff=vardiff,
                          expected_chain=EXPECTED_CHAIN)
    else:
        vardiff = None
        solo = SoloServer(rpc, payout,
                          share_difficulty=share_difficulty,
                          expected_chain=EXPECTED_CHAIN)
    server = SoloTCPServer((bind, port), solo)
    refresher = JobRefresher(solo, server.broadcast, log=log)
    refresher.start()
    write_status(solo, solo.node_info())
    log(f"solo server listening on {bind}:{port}, share "
        f"difficulty {share_difficulty}, payout {payout}, "
        f"vardiff {'enabled' if vardiff is not None else 'off'}")

    stop = {"flag": False}

    def on_signal(signum, frame):
        stop["flag"] = True
    signal.signal(signal.SIGTERM, on_signal)
    signal.signal(signal.SIGINT, on_signal)

    import threading
    serve_thread = threading.Thread(target=server.serve_forever,
                                    daemon=True)
    serve_thread.start()
    try:
        while not stop["flag"]:
            time.sleep(5)
            write_status(solo, solo.node_info())
    finally:
        refresher.stop()
        server.shutdown()
        server.server_close()
        write_status(solo, solo.node_info())
        log("solo server stopped")
    return 0


if __name__ == "__main__":
    sys.exit(main())
