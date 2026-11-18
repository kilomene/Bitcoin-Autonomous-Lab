#!/usr/bin/env python3
"""Stage 9.4: GBT path status publisher (DEF-9.2-4).

The pool path (mining/mainnet_live.py) publishes a status
event every 10 s; the GBT path in mining/engine.py published
nothing between cycle start and cycle completion, which
starved the awareness layer's rate observation in Stage 8
run 1. mining/engine.py now carries an opt-in StatusPublisher
(the Stage 8 demo miner's shape promoted into the engine).
This suite proves, with a stub RPC and a fake compute (no
node, no native backend):

1. Default off is the historical behaviour: no publisher
   thread, no status events, and the cycle result is
   identical to the publisher-enabled result.
2. Enabled with the default sink: status dicts land in
   engine.status_events during a long cycle, carry the pool
   path's status fields (hashes, rate, submitted, statistics,
   statistics_errors), and hashes never decrease.
3. The publisher thread is stopped and joined when the cycle
   returns, and also when the cycle raises.
4. A raising sink is counted on the publisher and never
   breaks the cycle.
5. A cycle shorter than the interval publishes nothing and
   still completes cleanly.

Run: python3 tests/test_status_publisher.py
"""

import os
import random
import struct
import sys
import threading
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from mining.engine import MiningEngine, txid_of  # noqa: E402
from mining.pow import coinbase_subsidy  # noqa: E402

PAYOUT = "bc1q528egeqsvv8aa382j43edxskqw6x7zxc2xpcf3"
SPK = "0014" + "11" * 20


class StubRPC:
    """The test_template_cache.py fixture shape."""

    def __init__(self, template=None):
        self.template = template
        self.counts = {}

    def call(self, method, *args):
        self.counts[method] = self.counts.get(method, 0) + 1
        if method == "getblocktemplate":
            return self.template
        if method == "validateaddress":
            return {"isvalid": True, "scriptPubKey": SPK}
        if method == "getblockchaininfo":
            return {"chain": "regtest"}
        if method == "submitblock":
            return None
        raise ValueError(method)

    def get_blockchain_info(self):
        return self.call("getblockchaininfo")

    def get_best_block_hash(self):
        return "00" * 32

    def with_timeout(self, _t):
        return self


def synth_template(height=1000):
    rng = random.Random(94)
    raw = (struct.pack("<i", 1) + b"\x01"
           + rng.randbytes(32) + struct.pack("<I", 0)
           + b"\x00" + struct.pack("<I", 0xFFFFFFFE)
           + b"\x01" + struct.pack("<Q", 5000)
           + b"\x19" + b"\x76\xa9\x14" + rng.randbytes(20)
           + b"\x88\xac" + struct.pack("<I", 0))
    tx = {"txid": txid_of(raw)[::-1].hex(), "data": raw.hex(),
          "fee": 1000}
    return {
        "version": 0x20000000,
        "previousblockhash": rng.randbytes(32).hex(),
        "transactions": [tx],
        "coinbaseaux": {"flags": ""},
        "coinbasevalue": coinbase_subsidy(height, 150) + 1000,
        "target": "7fffff0000000000000000000000000000000000000000"
                  "000000000000000000",
        "mintime": 1, "curtime": 1700000000,
        "bits": "207fffff", "height": height,
    }


class SlowCompute:
    """Fake backend: never finds a hit, sleeps per batch so
    the cycle lasts long enough to publish into."""

    backend = "fake"

    def __init__(self, sleep_s=0.05, fail_on=None):
        self.sleep_s = sleep_s
        self.fail_on = fail_on
        self.calls = 0

    def search_first_counted(self, header, target, start, count):
        self.calls += 1
        if self.fail_on is not None and self.calls >= self.fail_on:
            raise RuntimeError("fake backend failure")
        time.sleep(self.sleep_s)
        return None, count, self.sleep_s


def make_engine(**kw):
    stub = StubRPC(synth_template())
    return MiningEngine(stub, PAYOUT, compute=SlowCompute(),
                        batch_size=1024, **kw)


def publisher_threads():
    return [t for t in threading.enumerate()
            if t.__class__.__name__ == "StatusPublisher"]


def main():
    # 1. Default off: historical behaviour, identical result.
    off = make_engine()
    assert off.status_publish is False
    assert off.status_interval_s == 10.0
    res_off = off.mine_cycle(max_batches=20, deadline_seconds=60)
    assert res_off["accepted"] is False
    assert res_off["reason"] == "budget exhausted", res_off
    assert res_off["batches"] == 20 and res_off["hashes"] == 20 * 1024
    assert len(off.status_events) == 0
    assert off._status_publisher is None
    assert not publisher_threads()
    print("ok 1: default off, no thread, no events, cycle result "
          f"hashes={res_off['hashes']} batches={res_off['batches']}")

    # 2. Enabled, default sink: periodic republication with
    # the pool path's status fields, hashes non-decreasing,
    # and a result identical to the disabled run.
    on = make_engine(status_publish=True, status_interval_s=0.1)
    res_on = on.mine_cycle(max_batches=20, deadline_seconds=60)
    assert res_on == res_off, (res_on, res_off)
    events = list(on.status_events)
    assert len(events) >= 4, events
    hashes = [e["hashes"] for e in events]
    assert hashes == sorted(hashes), hashes
    for e in events:
        assert e["event"] == "status"
        assert e["submitted"] == 0
        assert e["rate"] >= 0
        assert e["statistics"]["backend_hashes"] == e["hashes"]
        assert e["statistics_errors"] == 0
    final = on.statistics.snapshot()["totals"]["backend_hashes"]
    assert events[-1]["hashes"] <= final == res_on["hashes"]
    assert on._status_publisher is None
    assert not publisher_threads()
    print(f"ok 2: enabled, {len(events)} status events during one "
          f"cycle, hashes {hashes[0]}..{hashes[-1]} of final "
          f"{final}, result identical to disabled run, thread "
          "stopped at return")

    # 3. Raising sink: counted, cycle unharmed.
    def bad_sink(_status):
        raise RuntimeError("sink failure")

    bad = make_engine(status_publish=True, status_interval_s=0.05,
                      status_sink=bad_sink)
    res_bad = bad.mine_cycle(max_batches=10, deadline_seconds=60)
    assert res_bad["hashes"] == 10 * 1024
    assert len(bad.status_events) == 0
    assert bad._status_publisher is None
    assert not publisher_threads()
    print("ok 3: raising sink never breaks the cycle and the "
          "publisher thread still stops")

    # 4. Cycle shorter than the interval: nothing published,
    # clean completion.
    short = make_engine(status_publish=True, status_interval_s=30.0)
    res_short = short.mine_cycle(max_batches=2, deadline_seconds=60)
    assert res_short["batches"] == 2
    assert len(short.status_events) == 0
    assert not publisher_threads()
    print("ok 4: sub-interval cycle publishes nothing, completes "
          "cleanly")

    # 5. Exception inside the cycle: propagates, and the
    # publisher is still stopped and joined.
    boom = MiningEngine(StubRPC(synth_template()), PAYOUT,
                        compute=SlowCompute(fail_on=3),
                        batch_size=1024, status_publish=True,
                        status_interval_s=0.05)
    try:
        boom.mine_cycle(max_batches=20, deadline_seconds=60)
        raise AssertionError("expected the backend failure")
    except RuntimeError as exc:
        assert "fake backend failure" in str(exc)
    assert boom._status_publisher is None
    assert not publisher_threads()
    print("ok 5: cycle exception propagates and no publisher "
          "thread survives it")

    print("test_status_publisher: all checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
