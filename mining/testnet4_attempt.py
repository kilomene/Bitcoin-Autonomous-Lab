#!/usr/bin/env python3
"""Testnet4 solo attempt driver.

Waits for the testnet4 node to sync, then watches for
minimum-difficulty windows (testnet4's 20-minute rule: when no
block has been found for 20 minutes, the next block may be mined
at difficulty 1). During a window it points the lab's full solo
stack at the live template: our ComputeEngine searching nonce
and extranonce space, our block assembly, submitblock on a hit.

Everything is logged to .local/testnet4/attempt.log with a final
verdict line starting with VERDICT:. The attempt is bounded:
at most MAX_WINDOWS windows or MAX_HOURS hours, whichever comes
first. This is a lottery with honest odds (see
research/probability.py): at difficulty 1 our expected time to a
block is about 15 minutes of searching, but the window can be
taken by any other miner first, and most windows will close
before we finish an expected search.
"""

import json
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from gpu.engine import ComputeEngine
from mining.engine import MiningEngine
from node.rpc_client import BitcoinRPC

ROOT = os.path.join(os.path.dirname(__file__), "..")
LOG = os.path.join(ROOT, ".local", "testnet4", "attempt.log")
CFG = os.path.join(ROOT, ".local", "testnet4", "node-config.json")
MAX_HOURS = 6
MAX_WINDOWS = 8
MIN_BITS = "1d00ffff"  # difficulty 1: testnet4's minimum under the 20-minute rule


def log(msg):
    line = f"{time.strftime('%Y-%m-%d %H:%M:%S')} {msg}"
    with open(LOG, "a") as f:
        f.write(line + "\n")
    print(line, flush=True)


def tn4_rpc():
    cfg = json.load(open(CFG))
    return BitcoinRPC(host=cfg["rpc_host"], port=cfg["rpc_port"],
                      user=cfg["rpc_user"], password=cfg["rpc_password"])


def main():
    rpc = tn4_rpc()
    info = rpc.call("getblockchaininfo")
    if info["blocks"] < info["headers"]:
        log(f"not synced: {info['blocks']}/{info['headers']}")
        return 0
    log(f"synced at {info['blocks']}; watching for min-diff windows")
    if "bal-tn4" not in rpc.call("listwallets"):
        try:
            rpc.call("loadwallet", "bal-tn4")
        except Exception:
            rpc.call("createwallet", "bal-tn4")
    wallet = BitcoinRPC(host=tn4_cfg()["rpc_host"], port=tn4_cfg()["rpc_port"],
                        user=tn4_cfg()["rpc_user"],
                        password=tn4_cfg()["rpc_password"], wallet="bal-tn4")
    payout = wallet.call("getnewaddress", "", "bech32")
    engine = MiningEngine(rpc, payout, ComputeEngine(), batch_size=1 << 22)
    started = time.time()
    windows = 0
    while time.time() - started < MAX_HOURS * 3600 and windows < MAX_WINDOWS:
        t = rpc.call("getblocktemplate", {"rules": ["segwit"]})
        if t["bits"] != MIN_BITS:
            time.sleep(45)
            continue
        windows += 1
        log(f"window {windows}: min-difficulty template at height "
            f"{t['height']}; mining")
        res = engine.mine_cycle(max_batches=400, deadline_seconds=1500)
        log(f"window {windows} result: {res}")
        if res.get("accepted"):
            log(f"VERDICT: BLOCK FOUND AND ACCEPTED on testnet4 at "
                f"height {res['height']}: {res['hash']}")
            return 0
        time.sleep(5)
    log(f"VERDICT: attempt finished without a block after "
        f"{windows} windows (odds were always the long side; "
        f"see research/probability.py)")
    return 0


def tn4_cfg():
    return json.load(open(CFG))


if __name__ == "__main__":
    sys.exit(main())
