#!/usr/bin/env python3
"""EXP-051 tests: the prepared-work prefetch queue (R-33).

Layers, in order:

  1. Queue unit gates against a fake node: serve, starve,
     stale-tip drop, unverifiable-tip drop, identity drop
     (in-place mutation after prepare, and a mutation that
     makes identity recomputation raise), superseded drops,
     overflow eviction, duplicate refusal, curtime refresh.
  2. Feed gates with stub fetch/prepare: dedupe against the
     current identity and against queued identities.
  3. Engine gates against the fake node through the real
     MiningEngine.mine_cycle: cold-start starvation, a served
     second cycle, the identity-confusion attack (a queued
     template mutated after prepare is never searched), the
     stale-tip attack (an external block lands while work is
     queued), rapid successive tip changes, and the disabled
     default (no queue, no counters, byte-identical
     candidates: the rollback surface).
  4. Gate 6 against the real regtest node: blocks mined
     through the queued path, accepted by Core, at least one
     cycle verifiably queue-served, the served block passing
     the EXP-036 exact verifier.

A stale serve anywhere is a critical defect by definition;
these tests are written so one cannot pass silently.
"""

import os
import struct
import sys
import threading
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from gpu.engine import ComputeEngine
from mining.engine import (MiningEngine, PreparedTemplate,
                           TemplateFamily, template_identity,
                           txid_of)
from mining.mining_statistics import MiningStatistics
from mining.pow import coinbase_subsidy, dsha256
from mining.pow_engine import POW_LIMIT_REGTEST
from mining.prefetch import PrefetchFeed, PrefetchQueue

PAYOUT = "bcrt1qexp051fakeaddress0000000000000000000"
SCRIPT_HEX = (b"\x00\x14" + b"\x22" * 20).hex()
TARGET_HEX = format(POW_LIMIT_REGTEST, "064x")


def simple_tx(fee=1000, tag=b"\x2a"):
    raw = (struct.pack("<i", 1) + b"\x01" + b"\x11" * 32
           + struct.pack("<I", 0) + b"\x00"
           + struct.pack("<I", 0xFFFFFFFF)
           + b"\x01" + struct.pack("<Q", 5000)
           + b"\x01" + tag + struct.pack("<I", 0))
    return {"txid": txid_of(raw)[::-1].hex(), "data": raw.hex(),
            "fee": fee}


def make_template(height, prevhash, txs=(), longpollid=None):
    fees = sum(t.get("fee", 0) for t in txs)
    return {
        "version": 536870912,
        "previousblockhash": prevhash,
        "bits": "207fffff",
        "target": TARGET_HEX,
        "height": height,
        "coinbasevalue": coinbase_subsidy(height, 150) + fees,
        "coinbaseaux": {"flags": ""},
        "transactions": list(txs),
        "mintime": 0,
        "curtime": int(time.time()),
        "longpollid": longpollid or f"lp-{height}-{id(txs)}",
    }


class FakeNode:
    """A minimal in-process GBT node with the exact surface
    MiningEngine uses: getblocktemplate (with longpoll
    semantics), validateaddress, submitblock (advances the
    tip and the template), get_blockchain_info,
    get_best_block_hash, with_timeout."""

    def __init__(self, txs=()):
        self.txs = list(txs)
        self.tip = "00" * 32
        self.height = 100
        self.template = make_template(101, self.tip, self.txs,
                                      longpollid="lp-101")
        self.cond = threading.Condition()
        self.submitted = []       # block hashes, in order
        self.submitted_blocks = []  # block hexes, in order
        self.external = 0

    # -- helpers for tests ----------------------------------
    def external_advance(self):
        with self.cond:
            self.external += 1
            self.height += 1
            self.tip = dsha256(
                b"external-block" + struct.pack(
                    "<I", self.external))[::-1].hex()
            self.template = make_template(
                self.height + 1, self.tip, self.txs,
                longpollid=f"lp-ext-{self.external}")
            self.cond.notify_all()
        return self.tip

    def set_txs(self, txs):
        with self.cond:
            self.txs = list(txs)
            self.template = make_template(
                self.height + 1, self.tip, self.txs,
                longpollid=f"lp-mempool-{time.time_ns()}")
            self.cond.notify_all()

    # -- engine-facing surface ------------------------------
    def with_timeout(self, timeout, retries=1):
        return self

    def get_blockchain_info(self):
        return {"chain": "regtest"}

    def get_best_block_hash(self):
        return self.tip

    def call(self, method, *params):
        if method == "validateaddress":
            return {"isvalid": True, "scriptPubKey": SCRIPT_HEX}
        if method == "getblocktemplate":
            want = params[0].get("longpollid") if params else None
            with self.cond:
                if want is not None and want == \
                        self.template["longpollid"]:
                    self.cond.wait(timeout=3.0)
                return dict(self.template)
        if method == "submitblock":
            raw = bytes.fromhex(params[0])
            block_hash = dsha256(raw[:80])[::-1].hex()
            with self.cond:
                self.submitted.append(block_hash)
                self.submitted_blocks.append(params[0])
                self.height = self.template["height"]
                self.tip = block_hash
                self.template = make_template(
                    self.height + 1, self.tip, self.txs,
                    longpollid=f"lp-{self.height + 1}")
                self.cond.notify_all()
            return None
        raise ValueError(f"FakeNode: unhandled method {method}")


def stats_of(engine):
    return engine.statistics.snapshot()["totals"]


def wait_queue(engine, n=1, timeout=20.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if len(engine.prefetch_queue) >= n:
            return True
        time.sleep(0.05)
    return False


# ----------------------------------------------------------------
# 1. Queue unit gates
# ----------------------------------------------------------------

def test_queue_unit():
    node = FakeNode()
    family = TemplateFamily(node, PAYOUT)
    stats = MiningStatistics()
    q = PrefetchQueue(max_entries=2,
                      recorder=lambda c: stats.record(c))
    t = stats.total

    # Empty queue: starved, nothing served.
    assert q.serve(family, node.get_best_block_hash) is None
    assert t("prefetch_starved") == 1 and t("prefetch_served") == 0

    # Happy path: prepared under the current tip, served.
    tpl_a = make_template(101, node.tip, longpollid="lp-a")
    prep_a = PreparedTemplate(family, tpl_a)
    assert q.enqueue(tpl_a, prep_a) is True
    assert t("prefetch_enqueued") == 1
    # Duplicate identity refused.
    assert q.enqueue(tpl_a, prep_a) is False
    assert t("prefetch_enqueued") == 1
    before = int(time.time())
    got = q.serve(family, node.get_best_block_hash)
    assert got is not None and got[1] is prep_a
    assert got[0]["curtime"] >= before, "curtime not refreshed"
    assert t("prefetch_served") == 1

    # Stale tip: the entry's prevhash is no longer the tip.
    tpl_b = make_template(101, node.tip, longpollid="lp-b")
    prep_b = PreparedTemplate(family, tpl_b)
    q.enqueue(tpl_b, prep_b)
    assert q.serve(family, lambda: "ff" * 32) is None
    assert t("prefetch_dropped_stale") == 1
    assert t("prefetch_starved") == 2

    # Unverifiable tip: best_hash raises -> stale drop.
    q.enqueue(tpl_b, prep_b)

    def boom():
        raise RuntimeError("node unreachable")
    assert q.serve(family, boom) is None
    assert t("prefetch_dropped_stale") == 2
    assert t("prefetch_starved") == 3

    # Identity confusion: mutate the queued template in place
    # after prepare (version feeds header_key, no validation
    # error) -> recomputed identity differs -> drop, no serve.
    tpl_c = make_template(101, node.tip, longpollid="lp-c")
    prep_c = PreparedTemplate(family, tpl_c)
    q.enqueue(tpl_c, prep_c)
    tpl_c["version"] += 1
    assert q.serve(family, node.get_best_block_hash) is None
    assert t("prefetch_dropped_identity") == 1
    assert t("prefetch_starved") == 4
    assert t("prefetch_served") == 1, "a mutated entry was served"

    # Mutation that makes recomputation raise (coinbasevalue
    # no longer equals subsidy + fees) -> identity drop too.
    tpl_d = make_template(101, node.tip, longpollid="lp-d")
    prep_d = PreparedTemplate(family, tpl_d)
    q.enqueue(tpl_d, prep_d)
    tpl_d["coinbasevalue"] += 1
    assert q.serve(family, node.get_best_block_hash) is None
    assert t("prefetch_dropped_identity") == 2
    assert t("prefetch_starved") == 5

    # Superseded: two entries, only the newest may serve.
    tx1 = simple_tx(fee=1000, tag=b"\x01")
    tx2 = simple_tx(fee=2000, tag=b"\x02")
    tpl_e = make_template(101, node.tip, [tx1], longpollid="lp-e")
    tpl_f = make_template(101, node.tip, [tx1, tx2],
                          longpollid="lp-f")
    prep_e = PreparedTemplate(family, tpl_e)
    prep_f = PreparedTemplate(family, tpl_f)
    q.enqueue(tpl_e, prep_e)
    q.enqueue(tpl_f, prep_f)
    got = q.serve(family, node.get_best_block_hash)
    assert got is not None and got[1] is prep_f
    assert t("prefetch_dropped_superseded") == 1
    assert t("prefetch_served") == 2

    # Overflow: bounded at 2, oldest evicted and counted.
    tpl_g = make_template(101, node.tip, [tx2], longpollid="lp-g")
    tpl_h = make_template(102, node.tip, [tx2], longpollid="lp-h")
    prep_g = PreparedTemplate(family, tpl_g)
    prep_h = PreparedTemplate(family, tpl_h)
    prep_e2 = PreparedTemplate(family, tpl_e)
    q.enqueue(tpl_g, prep_g)
    q.enqueue(tpl_h, prep_h)
    q.enqueue(tpl_e, prep_e2)
    assert t("prefetch_dropped_overflow") == 1
    assert len(q) == 2
    assert q.identities() == [prep_h.identity, prep_e2.identity]
    print("ok: queue unit gates (serve, starve, stale, "
          "unverifiable tip, identity confusion x2, superseded, "
          "overflow, duplicate)")


# ----------------------------------------------------------------
# 2. Feed gates
# ----------------------------------------------------------------

def test_feed_dedupe():
    node = FakeNode()
    family = TemplateFamily(node, PAYOUT)
    stats = MiningStatistics()
    q = PrefetchQueue(max_entries=4,
                      recorder=lambda c: stats.record(c))
    tpl_cur = make_template(101, node.tip, longpollid="lp-cur")
    cur_identity = template_identity(family, tpl_cur)[0]
    tpl_new = make_template(102, node.tip, longpollid="lp-new")
    answers = [tpl_cur, tpl_new, tpl_new]

    def fetch(_lp):
        if answers:
            return answers.pop(0)
        time.sleep(0.05)
        return tpl_new

    feed = PrefetchFeed(
        q, fetch,
        lambda tpl: (PreparedTemplate(family, tpl), False),
        error_sleep=0.05)
    feed.note_current(tpl_cur, cur_identity)
    feed.start()
    try:
        deadline = time.time() + 10
        while time.time() < deadline and len(q) < 1:
            time.sleep(0.05)
        time.sleep(0.3)   # let any duplicate attempts land
        assert len(q) == 1, f"queue holds {len(q)}, want 1"
        assert stats.total("prefetch_enqueued") == 1
    finally:
        feed.stop()
    print("ok: feed dedupes against the current identity and "
          "against queued identities")


# ----------------------------------------------------------------
# 3. Engine gates on the fake node
# ----------------------------------------------------------------

def test_engine_fake_node(compute):
    # -- happy path: cold starve, feed fill, served cycle ---
    node = FakeNode()
    eng = MiningEngine(node, PAYOUT, compute=compute,
                       use_prefetch=True)
    try:
        r1 = eng.mine_cycle()
        assert r1["accepted"], r1
        t = stats_of(eng)
        assert t["prefetch_starved"] == 1, t
        assert t["prefetch_served"] == 0, t
        assert wait_queue(eng, 1, timeout=20), "feed never queued"
        tip1 = node.get_best_block_hash()
        r2 = eng.mine_cycle()
        assert r2["accepted"], r2
        t = stats_of(eng)
        assert t["prefetch_served"] == 1, t
        # The served block builds on the tip cycle 1 created:
        # parse its header's previousblockhash field.
        assert node.submitted[-1] == r2["hash"]
        header2 = bytes.fromhex(node.submitted_blocks[-1])[:80]
        assert header2[4:36][::-1].hex() == tip1
        assert r2["height"] == 102
        assert tip1 != node.get_best_block_hash()
        print("ok: engine cold start starves once, feed fills, "
              "second cycle is queue-served and accepted")
    finally:
        eng.close_prefetch()

    # -- identity confusion at engine level -----------------
    node = FakeNode()
    eng = MiningEngine(node, PAYOUT, compute=compute,
                       use_prefetch=True)
    try:
        r1 = eng.mine_cycle()
        assert r1["accepted"], r1
        assert wait_queue(eng, 1, timeout=20)
        # Corrupt the queued template in place: its identity
        # no longer matches the prepared entry it travels
        # with. The cycle must never search it.
        with eng.prefetch_queue._lock:
            queued_tpl = eng.prefetch_queue._entries[-1][0]
        queued_tpl["version"] += 1
        r2 = eng.mine_cycle()
        assert r2["accepted"], r2
        t = stats_of(eng)
        assert t["prefetch_dropped_identity"] == 1, t
        assert t["prefetch_served"] == 0, t
        assert t["prefetch_starved"] == 2, t
        print("ok: identity confusion refused at engine level; "
              "the mutated work was never searched, the cycle "
              "fell back and was accepted")
    finally:
        eng.close_prefetch()

    # -- stale tip at engine level --------------------------
    node = FakeNode()
    eng = MiningEngine(node, PAYOUT, compute=compute,
                       use_prefetch=True)
    try:
        r1 = eng.mine_cycle()
        assert r1["accepted"], r1
        assert wait_queue(eng, 1, timeout=20)
        # Stop the feed so the queue keeps ONLY the stale
        # entry: with a live feed the fresh template would
        # legitimately arrive and dominate the queue (that is
        # the superseded path, covered above). This gate is
        # the starvation-with-stale-entry case: the only
        # queued work is built on a dead tip.
        eng._prefetch_feed.stop()
        time.sleep(0.3)
        ext_tip = node.external_advance()
        with eng.prefetch_queue._lock:
            newest_tpl = eng.prefetch_queue._entries[-1][0]
        assert newest_tpl["previousblockhash"] != ext_tip, \
            "precondition: newest queued entry is not stale"
        r2 = eng.mine_cycle()
        assert r2["accepted"], r2
        t = stats_of(eng)
        assert t["prefetch_dropped_stale"] >= 1, t
        assert t["prefetch_served"] == 0, t
        # The accepted block builds on the external tip, not
        # on the stale queued work: its height is the
        # external template's height.
        assert r2["height"] == node.height, (r2, node.height)
        assert ext_tip != r2["hash"]
        print("ok: stale queued work dropped after an external "
              "block; the cycle mined the live tip")
    finally:
        eng.close_prefetch()

    # -- rapid successive tip changes -----------------------
    node = FakeNode()
    eng = MiningEngine(node, PAYOUT, compute=compute,
                       use_prefetch=True)
    try:
        r1 = eng.mine_cycle()
        assert r1["accepted"], r1
        for _ in range(3):
            node.external_advance()
        r2 = eng.mine_cycle()
        assert r2["accepted"], r2
        t = stats_of(eng)
        assert t["prefetch_served"] + t["prefetch_starved"] == 2, t
        assert r2["height"] == node.height
        print("ok: rapid successive tip changes: no stale "
              "serve, counters account for every transition")
    finally:
        eng.close_prefetch()


def test_disabled_default(compute):
    node = FakeNode()
    eng_off = MiningEngine(node, PAYOUT, compute=compute)
    assert eng_off.prefetch_queue is None
    assert eng_off.use_prefetch is False
    r = eng_off.mine_cycle()
    assert r["accepted"], r
    t = stats_of(eng_off)
    for cat in ("prefetch_enqueued", "prefetch_served",
                "prefetch_starved", "prefetch_dropped_identity",
                "prefetch_dropped_stale",
                "prefetch_dropped_superseded",
                "prefetch_dropped_overflow"):
        assert t[cat] == 0, (cat, t[cat])
    # Byte-for-byte rollback surface: candidate construction
    # is identical with the flag on (queue never consulted by
    # build_candidate) and off.
    eng_on = MiningEngine(node, PAYOUT, compute=compute,
                          use_prefetch=True)
    try:
        tpl = node.template
        for en in (0, 1, 63):
            a = eng_off.build_candidate(tpl, en)
            b = eng_on.build_candidate(tpl, en)
            assert a == b, f"candidate differs at extranonce {en}"
    finally:
        eng_on.close_prefetch()
    print("ok: disabled default has no queue, no counters, "
          "and byte-identical candidates")


# ----------------------------------------------------------------
# 4. Gate 6 on the real regtest node
# ----------------------------------------------------------------

def test_gate6_real_node():
    from node import node_manager
    from node.rpc_client import BitcoinRPC
    from mining.candidate_verify import verify_candidate
    from mining.pow_engine import POW_LIMIT_REGTEST as LIMIT
    node_manager.start()
    rpc = BitcoinRPC()
    if "bal-regtest" not in rpc.call("listwallets"):
        try:
            rpc.call("loadwallet", "bal-regtest")
        except Exception:
            rpc.call("createwallet", "bal-regtest")
    wallet = BitcoinRPC(wallet="bal-regtest")
    payout = wallet.call("getnewaddress", "", "bech32")
    eng = MiningEngine(rpc, payout, use_prefetch=True)
    served_cycles = 0
    try:
        for cycle in range(4):
            before = stats_of(eng)["prefetch_served"]
            res = eng.mine_cycle()
            assert res["accepted"], res
            assert rpc.get_best_block_hash() == res["hash"]
            raw = rpc.call("getblock", res["hash"], 0)
            v = verify_candidate(bytes.fromhex(raw)[:80], LIMIT)
            assert v["classification"] == "block_candidate", v
            after = stats_of(eng)["prefetch_served"]
            if after > before:
                served_cycles += 1
            if served_cycles:
                break
            assert wait_queue(eng, 1, timeout=30), \
                "feed never queued on the real node"
        assert served_cycles >= 1, \
            "no queue-served cycle in 4 attempts"
        t = stats_of(eng)
        print(f"ok: Gate 6 real node: queue-served regtest "
              f"block accepted and EXP-036 verified "
              f"(served {t['prefetch_served']}, starved "
              f"{t['prefetch_starved']}, enqueued "
              f"{t['prefetch_enqueued']})")
    finally:
        eng.close_prefetch()


def main():
    test_queue_unit()
    test_feed_dedupe()
    compute = ComputeEngine()
    print(f"compute backend for engine gates: {compute.backend}")
    test_engine_fake_node(compute)
    test_disabled_default(compute)
    test_gate6_real_node()
    print("EXP-051 prefetch suite: ALL PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
