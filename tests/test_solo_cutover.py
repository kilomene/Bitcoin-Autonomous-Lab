#!/usr/bin/env python3
"""Solo cutover gates: node gating, endpoint config, and the
cutover script's own decision logic.

These tests pin the behaviours docs/SOLO_CUTOVER.md promises:

- SoloServer refuses to build or serve a job while the node
  is in initial block download, on the wrong chain, or
  unreachable (SoloNotReady / ChainMismatch), and builds one
  happily from a synced node of the expected chain.
- A malformed default_witness_commitment from the node is a
  loud error, never a blind slice.
- attach_witness is the exact inverse of strip_witness for
  the coinbases this server builds (the block-assembly path).
- The cutover script's node_ready test matches the task's
  rule: IBD false and blocks within 2 of headers.
- The script's live self-check (solo_smoke) succeeds against
  a real running server on the node tip, and fails when the
  tip or difficulty does not match.
- Endpoint resolution: config absent means public-pool
  (today's behaviour), mode solo means our server, env and
  CLI override the file, a corrupt file falls back to the
  pool default, and set_mode round-trips.

The live regtest end-to-end (a real block through a real
miner connection) stays in tests/test_solo_server.py.
"""

import importlib.util
import json
import os
import socket
import sys
import tempfile
import threading
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from mining import endpoint_config
from mining.engine import build_coinbase, strip_witness
from mining.solo_server import (ChainMismatch, SoloNotReady, SoloServer,
                                SoloTCPServer, attach_witness)

ROOT = os.path.join(os.path.dirname(__file__), "..")
PAYOUT = "bc1q528egeqsvv8aa382j43edxskqw6x7zxc2xpcf3"
TIP = "ab" * 32
COMMITMENT_SCRIPT = (b"\x6a\x24\xaa\x21\xa9\xed" + bytes(32)).hex()


def load_cutover():
    spec = importlib.util.spec_from_file_location(
        "solo_cutover", os.path.join(ROOT, "scripts",
                                     "solo_cutover.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class FakeRPC:
    """The slice of Core the solo server talks to."""

    def __init__(self, info, template=None, commitment=None):
        self.info = info
        self.template = template
        self.commitment = commitment

    def call(self, method, *params):
        if method == "getblockchaininfo":
            if isinstance(self.info, Exception):
                raise self.info
            return self.info
        if method == "getblocktemplate":
            t = dict(self.template)
            if self.commitment is not None:
                t["default_witness_commitment"] = self.commitment
            return t
        if method == "validateaddress":
            return {"isvalid": True,
                    "scriptPubKey": "0014" + "22" * 20}
        raise AssertionError(f"unexpected RPC {method}")


def synced_info(chain="main"):
    return {"chain": chain, "blocks": 900000, "headers": 900000,
            "initialblockdownload": False, "bestblockhash": TIP}


def template():
    return {"height": 900001, "coinbasevalue": 312500000,
            "previousblockhash": TIP, "bits": "1d00ffff",
            "curtime": 1700000000, "mintime": 1600000000,
            "version": 0x20000000, "transactions": []}


def test_ibd_refusal():
    info = dict(synced_info(), initialblockdownload=True,
                blocks=412000, headers=975819)
    solo = SoloServer(FakeRPC(info, template()), PAYOUT,
                      expected_chain="main")
    try:
        solo.refresh_job()
    except SoloNotReady as exc:
        assert "initial block download" in str(exc), exc
        print("ok: refresh refused during initial block download")
        return
    raise AssertionError("refresh_job served a job during IBD")


def test_chain_mismatch_refusal():
    solo = SoloServer(FakeRPC(synced_info("regtest"), template()),
                      PAYOUT, expected_chain="main")
    try:
        solo.refresh_job()
    except ChainMismatch as exc:
        print(f"ok: chain mismatch refused ({exc})")
        return
    raise AssertionError("refresh_job served a job from the "
                         "wrong chain")


def test_node_down_refusal():
    solo = SoloServer(
        FakeRPC(ConnectionError("refused"), template()), PAYOUT,
        expected_chain="main")
    try:
        solo.refresh_job()
    except SoloNotReady:
        print("ok: refresh refused when the node is unreachable")
        return
    raise AssertionError("refresh_job served a job with no node")


def test_synced_refresh_and_commitment():
    solo = SoloServer(
        FakeRPC(synced_info(), template(),
                commitment=COMMITMENT_SCRIPT),
        PAYOUT, expected_chain="main", share_difficulty=0.02)
    job = solo.refresh_job()
    assert job["template"]["previousblockhash"] == TIP
    assert job["has_witness"] is True
    params = solo.notify_params(job)
    assert params[0] == job["job_id"] and params[8] is True
    print("ok: job built from a synced node, witness commitment "
          "parsed and validated")


def test_malformed_commitment_is_loud():
    solo = SoloServer(
        FakeRPC(synced_info(), template(), commitment="abcd"),
        PAYOUT, expected_chain="main")
    try:
        solo.refresh_job()
    except ValueError as exc:
        assert "default_witness_commitment" in str(exc), exc
        print("ok: malformed witness commitment raises, no slice")
        return
    raise AssertionError("malformed commitment was accepted")


def test_witness_reassembly_inverse():
    full, _txid = build_coinbase(
        800000, 312500000, bytes.fromhex("0014" + "11" * 20),
        b"\x01\x02\x03\x04\x05\x06\x07\x08",
        witness_commitment=bytes(range(32)))
    stripped, has_witness = strip_witness(full)
    assert has_witness
    assert attach_witness(stripped) == full
    print("ok: attach_witness inverts strip_witness exactly")


def test_node_ready_rule():
    cut = load_cutover()
    ok, _ = cut.node_ready(synced_info())
    assert ok
    ok, _ = cut.node_ready(dict(synced_info(), headers=900002))
    assert ok, "gap of 2 must be ready"
    ok, _ = cut.node_ready(dict(synced_info(), headers=900003))
    assert not ok, "gap of 3 must not be ready"
    ok, _ = cut.node_ready(
        dict(synced_info(), initialblockdownload=True))
    assert not ok, "IBD must not be ready"
    ok, _ = cut.node_ready(None)
    assert not ok
    print("ok: cutover node_ready matches IBD-false, gap <= 2")


def test_smoke_against_live_server():
    cut = load_cutover()
    solo = SoloServer(FakeRPC(synced_info("regtest"), template(),
                              commitment=COMMITMENT_SCRIPT),
                      PAYOUT, expected_chain="regtest",
                      share_difficulty=0.02)
    server = SoloTCPServer(("127.0.0.1", 33499), solo)
    th = threading.Thread(target=server.serve_forever, daemon=True)
    th.start()
    try:
        ok, why = cut.solo_smoke("127.0.0.1", 33499, TIP, 0.02,
                                 f"{PAYOUT}.cutover-check")
        assert ok, why
        ok, why = cut.solo_smoke("127.0.0.1", 33499, "cd" * 32,
                                 0.02, f"{PAYOUT}.cutover-check")
        assert not ok, "smoke passed against the wrong tip"
        ok, why = cut.solo_smoke("127.0.0.1", 33499, TIP, 0.05,
                                 f"{PAYOUT}.cutover-check")
        assert not ok, "smoke passed at the wrong difficulty"
        print("ok: solo_smoke verifies tip and difficulty live, "
              "and rejects wrong ones")
    finally:
        server.shutdown()
        server.server_close()


def test_subscribe_refused_during_ibd():
    info = dict(synced_info("regtest"), initialblockdownload=True,
                blocks=10, headers=900000)
    solo = SoloServer(FakeRPC(info, template()), PAYOUT,
                      expected_chain="regtest")
    server = SoloTCPServer(("127.0.0.1", 33501), solo)
    th = threading.Thread(target=server.serve_forever, daemon=True)
    th.start()
    try:
        sock = socket.create_connection(("127.0.0.1", 33501),
                                        timeout=10)
        f = sock.makefile("rwb")
        f.write(b'{"id": 1, "method": "mining.subscribe", '
                b'"params": ["gate-test"]}\n')
        f.flush()
        sock.settimeout(10)
        saw_notify = False
        while True:
            line = f.readline()
            if not line:
                break
            try:
                msg = json.loads(line)
            except ValueError:
                continue
            if msg.get("method") == "mining.notify":
                saw_notify = True
        assert not saw_notify, "a job was served during IBD"
        sock.close()
        print("ok: subscribe during IBD gets no job; session "
              "is refused")
    finally:
        server.shutdown()
        server.server_close()


def test_endpoint_config():
    with tempfile.TemporaryDirectory() as td:
        path = os.path.join(td, "mining-endpoint.json")
        host, port, mode, _ = endpoint_config.resolve_endpoint(
            env={}, path=path)
        assert (host, port, mode) == ("public-pool.io", 21496,
                                      "pool")
        endpoint_config.set_mode("solo", path)
        host, port, mode, _ = endpoint_config.resolve_endpoint(
            env={}, path=path)
        assert (host, port, mode) == ("127.0.0.1", 3333, "solo")
        host, port, mode, _ = endpoint_config.resolve_endpoint(
            env={"BAL_POOL_HOST": "example.org",
                 "BAL_POOL_PORT": "9999"}, path=path)
        assert (host, port) == ("example.org", 9999), \
            "env must override the file"
        host, port, mode, _ = endpoint_config.resolve_endpoint(
            "cli.example", 4444, env={"BAL_POOL_HOST": "e.org"},
            path=path)
        assert (host, port) == ("cli.example", 4444), \
            "CLI must override env"
        endpoint_config.set_mode("pool", path)
        host, port, mode, _ = endpoint_config.resolve_endpoint(
            env={}, path=path)
        assert (host, port, mode) == ("public-pool.io", 21496,
                                      "pool")
        with open(path, "w") as f:
            f.write("{not json")
        host, port, mode, _ = endpoint_config.resolve_endpoint(
            env={}, path=path)
        assert (host, port, mode) == ("public-pool.io", 21496,
                                      "pool"), \
            "corrupt config must fall back to the pool default"
    print("ok: endpoint resolution (default, solo, env, CLI, "
          "corrupt) and set_mode round-trip")


def main():
    test_ibd_refusal()
    test_chain_mismatch_refusal()
    test_node_down_refusal()
    test_synced_refresh_and_commitment()
    test_malformed_commitment_is_loud()
    test_witness_reassembly_inverse()
    test_node_ready_rule()
    test_smoke_against_live_server()
    test_subscribe_refused_during_ibd()
    test_endpoint_config()
    print("ALL SOLO CUTOVER TESTS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
