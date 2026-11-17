#!/usr/bin/env python3
"""EXP-055 Gate 6: a regtest block produced through
coordinator-assigned work.

Shape (predeclaration): a job is declared from the regtest
node's own getblocktemplate; a worker leases one nonce
range through the wire protocol (TCP loopback, persistent
coordinator with a real state directory); the worker
searches only inside its leased range; on a hit it hands
the candidate to the coordinator through the candidate
protocol; the coordinator verifies it with the EXP-036
verifier (mining/candidate_verify.py, regtest limit); only
the coordinator side submits; the block counts only when
the node holds it on its active chain
(verify_chain_acceptance) and the height advanced by
exactly one.

Regtest only. No other machine is contacted.
"""

import hashlib
import json
import os
import struct
import sys
import time
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)

from mining.coordinator import (CoordinatorClient,  # noqa: E402
                                CoordinatorServer)
from mining.candidate_verify import (  # noqa: E402
    POW_LIMIT_REGTEST, verify_candidate,
    verify_chain_acceptance)
from mining.pow import dsha256  # noqa: E402
from exp055_campaign import call_ok, start_tcp, stop_tcp  # noqa: E402

PREDECLARATION_SHA256 = \
    "b455d16ba878144d82abe90b531a58a1fcaa1333576d4c73098b3d59a5de93ea"
FLEET = "nova-fleet-test"


def main():
    with open(os.path.join(HERE, "PREDECLARATION.md"),
              "rb") as fh:
        assert hashlib.sha256(fh.read()).hexdigest() \
            == PREDECLARATION_SHA256
    from node import node_manager
    from node.rpc_client import BitcoinRPC
    from mining.engine import MiningEngine
    from gpu.engine import ComputeEngine

    node_manager.start()
    rpc = BitcoinRPC()
    if "bal-regtest" not in rpc.call("listwallets"):
        try:
            rpc.call("loadwallet", "bal-regtest")
        except Exception:
            rpc.call("createwallet", "bal-regtest")
    wallet = BitcoinRPC(wallet="bal-regtest")
    payout = wallet.call("getnewaddress", "", "bech32")
    engine = MiningEngine(rpc, payout)
    template = engine.get_template()
    cand = engine.build_candidate(template, 0)
    header = cand["header"]
    target = cand["target"]
    height = cand["height"]
    tip0 = rpc.get_block_count()
    version = struct.unpack("<i", header[0:4])[0]
    ntime = struct.unpack("<I", header[68:72])[0]

    import shutil
    state = os.path.join(HERE, "RAW_RESULTS", "gate6_state")
    if os.path.exists(state):
        shutil.rmtree(state)

    verdicts = []

    def verifier(rec):
        v = verify_candidate(
            bytes.fromhex(rec["header_hex"]),
            POW_LIMIT_REGTEST)
        verdicts.append(v["classification"])
        return v["classification"]

    server = CoordinatorServer(FLEET, state_dir=state,
                               verifier=verifier)
    port = start_tcp(server)
    client = CoordinatorClient(host="127.0.0.1", port=port)
    try:
        call_ok(client, {"type": "register",
                         "worker_id": "w-gate6",
                         "fleet_id": FLEET, "now": time.time()})
        n_slices = call_ok(client, {
            "type": "declare_job",
            "job_id": "gate6-%d" % height, "generation": 1,
            "nonce_count": 1 << 20, "chunk_size": 1 << 20,
            "n_slots": 1,
            "version_variants": [version],
            "ntime_values": [ntime], "counters_per_slot": 1})
        assert n_slices == 1
        lease = call_ok(client, {"type": "lease",
                                 "worker_id": "w-gate6",
                                 "now": time.time(),
                                 "ttl": 3600.0})
        assert lease is not None
        lo, hi = lease["lo"], lease["hi"]
        # The worker searches ONLY its leased range.
        compute = ComputeEngine()
        hit, attempted, _secs = compute.search_first_counted(
            header, target, lo, hi - lo)
        searched_with = compute.backend
        if hit is None:
            # Fallback: exact hashlib scan of the same range
            # (regtest target admits about one hit per two
            # hashes, so a full-range miss is not expected;
            # recorded honestly if it happens).
            nonce = None
            for n in range(lo, hi):
                h = header[:76] + struct.pack("<I", n)
                if int.from_bytes(dsha256(h),
                                  "little") <= target:
                    nonce = n
                    break
            assert nonce is not None, \
                "no hit inside the leased range"
            hit = (nonce, dsha256(
                header[:76] + struct.pack("<I", nonce)))
            searched_with = "hashlib-fallback"
        nonce = hit[0]
        assert lo <= nonce < hi, (nonce, lo, hi)
        final_header = header[:76] + struct.pack(
            "<I", nonce)
        block = final_header + cand["body"]
        block_hash = dsha256(final_header)[::-1].hex()
        rec = {"job_id": "gate6-%d" % height, "generation": 1,
               "extranonce2": lease["extranonce2"],
               "version": version, "ntime": ntime,
               "nonce": nonce,
               "lease_id": lease["lease_id"],
               "worker_id": "w-gate6",
               "header_hex": final_header.hex(),
               "block_hex": block.hex()}
        r = call_ok(client, {"type": "candidate_submit",
                             "record": rec})
        assert r == "ACCEPTED", r
        r = call_ok(client, {"type": "candidate_submit",
                             "record": rec})
        assert r == "DUPLICATE", r
        drained = call_ok(client, {"type": "candidate_drain"})
        assert len(drained) == 1, drained
        assert drained[0]["verdict"] == "block_candidate", \
            drained
        assert verdicts == ["block_candidate"], verdicts
        # Coverage credit is the lease's own act, separate
        # from candidate judgment (design section 8).
        done = call_ok(client, {
            "type": "progress", "worker_id": "w-gate6",
            "lease_id": lease["lease_id"],
            "token": lease["token"],
            "examined": nonce - lo + 1})
        assert done == "OK", done
        # Only the coordinator side submits.
        submit = rpc.call("submitblock", block.hex())
        assert submit is None, submit
        status, accepted = verify_chain_acceptance(
            rpc, block_hash)
        assert accepted, (status, block_hash)
        tip1 = rpc.get_block_count()
        assert tip1 == tip0 + 1, (tip0, tip1)
        assert rpc.get_best_block_hash() == block_hash
    finally:
        client.close()
        stop_tcp(server)
        server.close()
    out = {"height": height, "hash": block_hash,
           "nonce": nonce, "leased_range": [lo, hi],
           "attempted": attempted,
           "search_backend": searched_with,
           "verdicts": verdicts,
           "tip_before": tip0, "tip_after": tip1,
           "chain_status": status}
    stamp = datetime.now(timezone.utc).strftime(
        "%Y%m%dT%H%M%SZ")
    record = {"experiment": "EXP-055", "gate": 6,
              "host_cpu": "AMD EPYC 9D25", "when_utc": stamp,
              "predeclaration_sha256":
                  PREDECLARATION_SHA256,
              "result": out}
    path = os.path.join(HERE, "RAW_RESULTS",
                        "gate6_%s.json" % stamp)
    with open(path, "w") as fh:
        json.dump(record, fh, indent=1, sort_keys=True)
    print("WROTE", path, flush=True)
    print("EXP-055 GATE 6 PASSED:", out, flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
