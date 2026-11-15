#!/usr/bin/env python3
"""EXP-026 fresh regtest gate.

Binds the research mask-search kernel into the real
production block-building path: a small research shim
exposes the engine's counted-search interface
(search_first_counted) backed by bal_v_msearcha2
(design C) or bal_v_msearch2 (design B) from
libbal_m512.so, and production mining/engine.py
MiningEngine drives it: getblocktemplate from the
lab's regtest Core, build_candidate (production),
search (mask kernel, through the shim), block assembly
(production), submitblock, best-chain confirmation.

Exactly which parts ran where:
  * Template, coinbase, Merkle root, header and block
    assembly, submission: production code
    (mining/engine.py), unmodified.
  * The nonce search itself: the EXP-026 research
    kernel in libbal_m512.so, through the shim below.
    The production ComputeEngine is NOT used for the
    search in this harness; that is the honest limit of
    binding a research kernel without editing
    production code, and it is labelled as such.
  * Candidate verification: the shim independently
    recomputes every kernel candidate with hashlib
    (gpu.engine.cpu_digest) and checks the target
    before returning it, mirroring the production
    engine's fail-closed verify_candidate rule. A
    mismatch raises instead of submitting.

The regtest node is the lab's own regtest datadir
(.local/regtest, RPC 18443) managed by
node.node_manager. The mainnet node, autopilot and
miner are not touched.
"""
import ctypes
import json
import os
import sys
import time
from datetime import datetime, timezone

ROOT = "/home/hatch/workspace/bitcoin-autonomous-lab"
EO_SRC = os.path.join(ROOT, "research/sha256d/extreme_optimization/src")
HERE = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(HERE, "exp026")
sys.path.insert(0, ROOT)

from gpu.engine import cpu_digest  # noqa: E402
from mining.engine import MiningEngine  # noqa: E402
from node import node_manager  # noqa: E402
from node.rpc_client import BitcoinRPC  # noqa: E402

SEARCH_SIG = [
    ctypes.c_char_p, ctypes.c_uint64, ctypes.c_uint64,
    ctypes.c_uint, ctypes.c_char_p,
    ctypes.POINTER(ctypes.c_uint32), ctypes.c_char_p,
    ctypes.POINTER(ctypes.c_uint64),
    ctypes.POINTER(ctypes.c_uint64)]


class MaskCompute:
    """Research shim: the ComputeEngine counted-search
    surface backed by one EXP-026 mask search arm."""

    def __init__(self, symbol, label, threads=2, libname="libbal_e26d.so"):
        lib = ctypes.CDLL(os.path.join(EO_SRC, libname))
        fn = getattr(lib, symbol)
        fn.restype = ctypes.c_int
        fn.argtypes = SEARCH_SIG
        self._fn = fn
        self._threads = threads
        self.backend = label
        self.last_search_stats = {}

    def search_first_counted(self, header, target, start, count):
        if len(header) != 80 or not (1 <= target < (1 << 256)):
            raise ValueError("bad header or target")
        if not (0 <= start and 0 < count and
                start + count <= (1 << 32)):
            raise ValueError("nonce range out of bounds")
        nonce = ctypes.c_uint32(0)
        dig = ctypes.create_string_buffer(32)
        att = ctypes.c_uint64(0)
        back = ctypes.c_uint64(0)
        t0 = time.perf_counter()
        rc = self._fn(header, start, count, self._threads,
                      target.to_bytes(32, "little"),
                      ctypes.byref(nonce), dig,
                      ctypes.byref(att), ctypes.byref(back))
        dt = time.perf_counter() - t0
        if rc not in (0, 1):
            raise RuntimeError(f"mask search returned {rc}")
        self.last_search_stats = {
            "backend": self.backend, "counted": True,
            "attempted": att.value, "backend_hashes": back.value,
            "unique_coverage": att.value,
            "candidate_count": 1 if rc == 1 else 0,
            "verification_hashes": 1 if rc == 1 else 0}
        if rc == 0:
            return None, att.value, dt
        n, d = nonce.value, dig.raw
        # Fail-closed independent verification, mirroring
        # the production engine: hashlib recompute plus
        # target check before the candidate is used.
        if cpu_digest(header, n) != d or \
                int.from_bytes(d, "little") > target:
            raise RuntimeError(
                "mask candidate failed independent verification")
        return (n, d), att.value, dt


def mine_one(rpc, payout, symbol, label, libname="libbal_e26d.so"):
    compute = MaskCompute(symbol, label, libname=libname)
    eng = MiningEngine(rpc, payout, compute=compute,
                       batch_size=100_000)
    tip0 = rpc.get_block_count()
    out = eng.mine_cycle(max_batches=1000, deadline_seconds=600)
    assert out["accepted"], out
    assert rpc.get_best_block_hash() == out["hash"], out
    assert rpc.get_block_count() == tip0 + 1, out
    # Independent confirmation of the winning digest.
    header = None
    blk = rpc.call("getblock", out["hash"], 0)
    raw = bytes.fromhex(blk)
    header = raw[:80]
    nonce = int.from_bytes(header[76:80], "little")
    assert nonce == out["nonce"], (nonce, out["nonce"])
    d = cpu_digest(header, nonce)
    assert d[::-1].hex() == out["hash"], (d[::-1].hex(), out["hash"])
    print(f"ok regtest ({label}): block accepted, height "
          f"{out['height']} hash {out['hash']} nonce "
          f"{out['nonce']} hashes {out['hashes']}", flush=True)
    return {"arm": label, "symbol": symbol,
            "height": out["height"], "hash": out["hash"],
            "nonce": out["nonce"], "hashes": out["hashes"],
            "batches": out["batches"],
            "extranonce_rounds": out["extranonce_rounds"],
            "submit_result": out["submit_result"]}


def main():
    node_manager.start()
    rpc = BitcoinRPC()
    if "bal-regtest" not in rpc.call("listwallets"):
        try:
            rpc.call("loadwallet", "bal-regtest")
        except Exception:
            rpc.call("createwallet", "bal-regtest")
    wallet = BitcoinRPC(wallet="bal-regtest")
    payout = wallet.call("getnewaddress", "", "bech32")
    record = {"experiment": "EXP-026",
              "started_utc": datetime.now(timezone.utc).isoformat(),
              "node": "regtest (.local/regtest, RPC 18443)",
              "blocks": []}
    record["blocks"].append(mine_one(
        rpc, payout, "bal_v_e26d_search2",
        "exp026-dualmask (candidate C2, research)"))
    record["blocks"].append(mine_one(
        rpc, payout, "bal_v_e26t_search2",
        "exp026-ternmask (candidate C1, research)",
        libname="libbal_e26t.so"))
    record["finished_utc"] = datetime.now(timezone.utc).isoformat()
    record["all_accepted"] = True
    os.makedirs(OUT_DIR, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = os.path.join(OUT_DIR, f"regtest_{stamp}.json")
    suffix = 2
    while os.path.exists(path):
        path = os.path.join(OUT_DIR, f"regtest_{stamp}_r{suffix}.json")
        suffix += 1
    with open(path, "x") as fh:
        json.dump(record, fh, indent=2)
    print(f"wrote {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
