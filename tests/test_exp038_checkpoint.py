#!/usr/bin/env python3
"""EXP-038 tests: work-state checkpoint for the GBT path.

Pins the honesty rules of mining/work_checkpoint.py as wired
into MiningEngine.mine_cycle:

- A cycle interrupted by its batch budget leaves a frontier
  covering exactly the batches that completed, no more.
- A restarted engine on the same template resumes at the
  frontier: across both processes the searched ranges are
  disjoint and together cover the space (no silent repeated
  work, no skipped work).
- A completed space is not rescanned under the same template
  identity, space and time basis.
- Any mismatch (template identity, extranonce space, curtime
  basis), a corrupt file, or an out-of-space frontier starts
  fresh, with the reason in the result's "checkpoint" note.
- With no checkpoint configured the engine behaves exactly as
  before: no "checkpoint" key in results, full rescans.

The engine runs against a fake RPC serving one fixed regtest
template and a fake compute that records every searched
(extranonce, start, count) range without hashing.
"""

import json
import os
import sys
import tempfile

ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, ROOT)

from mining.engine import MiningEngine
from mining.pow import target_from_nbits
from mining.work_checkpoint import WorkCheckpoint

PAYOUT = "bcrt1qcheckpoint0000000000000000000000000000"
SCRIPT = "0014" + "00" * 20


def make_template(prevhash="11" * 32, height=100, curtime=1700000000):
    return {
        "version": 0x20000000,
        "previousblockhash": prevhash,
        "transactions": [],
        "coinbaseaux": {"flags": ""},
        "coinbasevalue": 5_000_000_000,
        "target": format(target_from_nbits(0x207FFFFF), "064x"),
        "bits": "207fffff",
        "height": height,
        "mintime": 1,
        "curtime": curtime,
    }


class FakeRPC:
    def __init__(self, template):
        self.template = template

    def call(self, method, *args):
        if method == "getblocktemplate":
            return dict(self.template)
        if method == "validateaddress":
            return {"isvalid": True, "scriptPubKey": SCRIPT}
        if method == "submitblock":
            return None
        raise AssertionError(f"unexpected RPC call {method}")

    def get_blockchain_info(self):
        return {"chain": "regtest", "blocks": 99, "headers": 99}

    def get_best_block_hash(self):
        return "00" * 32


class FakeCompute:
    backend = "fake"

    def __init__(self, header_to_extranonce):
        self.map = header_to_extranonce
        self.searched = []

    def search_first_counted(self, header, target, start, count):
        en = self.map[bytes(header)]
        self.searched.append((en, start, count))
        return None, count, 0.0


def make_engine(rpc, template, compute, ckpt_path, **kw):
    engine = MiningEngine(rpc, PAYOUT, compute=compute,
                          checkpoint_path=ckpt_path, **kw)
    header_to_en = {}
    for en in range(*_space_span(kw.get("extranonce_space",
                                       (0, 64)))):
        cand = engine.build_candidate(template, en)
        header_to_en[cand["header"]] = en
    compute.map = header_to_en
    return engine


def _space_span(space):
    first, count = space
    return first, first + count


def test_resume_across_restart(tmp):
    template = make_template()
    rpc = FakeRPC(template)
    ckpt = os.path.join(tmp, "work.json")

    compute = FakeCompute({})
    engine = make_engine(rpc, template, compute, ckpt,
                         batch_size=1 << 32, extranonce_space=(0, 2))
    r1 = engine.mine_cycle(max_batches=1, deadline_seconds=10000)
    assert r1["reason"] == "budget exhausted", r1
    assert compute.searched == [(0, 0, 1 << 32)], compute.searched
    assert "fresh" in r1["checkpoint"], r1["checkpoint"]
    saved = json.load(open(ckpt))
    assert saved["frontier_extranonce"] == 1, saved
    assert saved["frontier_nonce"] == 0, saved
    assert saved["complete"] is False, saved
    print("ok: budget-interrupted cycle checkpoints exactly "
          "the one completed round")

    compute2 = FakeCompute({})
    engine2 = make_engine(rpc, template, compute2, ckpt,
                          batch_size=1 << 32, extranonce_space=(0, 2))
    r2 = engine2.mine_cycle(max_batches=10, deadline_seconds=10000)
    assert r2["reason"] == "nonce space exhausted", r2
    assert compute2.searched == [(1, 0, 1 << 32)], compute2.searched
    assert "resumed" in r2["checkpoint"], r2["checkpoint"]
    all_ranges = compute.searched + compute2.searched
    assert sorted(all_ranges) == [(0, 0, 1 << 32),
                                  (1, 0, 1 << 32)], all_ranges
    saved = json.load(open(ckpt))
    assert saved["complete"] is True, saved
    print("ok: restarted engine resumes at the frontier; the "
          "two processes' ranges are disjoint and complete")

    compute3 = FakeCompute({})
    engine3 = make_engine(rpc, template, compute3, ckpt,
                          batch_size=1 << 32, extranonce_space=(0, 2))
    r3 = engine3.mine_cycle(max_batches=10, deadline_seconds=10000)
    assert r3["reason"] == "nonce space exhausted", r3
    assert r3["hashes"] == 0 and r3["batches"] == 0, r3
    assert compute3.searched == [], compute3.searched
    assert "fully examined" in r3["checkpoint"], r3["checkpoint"]
    print("ok: a completed space is not rescanned under the "
          "same template")

    template2 = make_template(prevhash="22" * 32, height=101)
    rpc2 = FakeRPC(template2)
    compute4 = FakeCompute({})
    engine4 = make_engine(rpc2, template2, compute4, ckpt,
                          batch_size=1 << 32, extranonce_space=(0, 2))
    r4 = engine4.mine_cycle(max_batches=1, deadline_seconds=10000)
    assert compute4.searched == [(0, 0, 1 << 32)], compute4.searched
    assert "different template identity" in r4["checkpoint"], \
        r4["checkpoint"]
    print("ok: a new template starts fresh, and says why")


def test_mid_round_frontier(tmp):
    template = make_template()
    rpc = FakeRPC(template)
    ckpt = os.path.join(tmp, "work.json")
    compute = FakeCompute({})
    engine = make_engine(rpc, template, compute, ckpt,
                         batch_size=1 << 31, extranonce_space=(0, 1))
    r1 = engine.mine_cycle(max_batches=1, deadline_seconds=10000)
    assert r1["reason"] == "budget exhausted", r1
    assert compute.searched == [(0, 0, 1 << 31)], compute.searched
    saved = json.load(open(ckpt))
    assert (saved["frontier_extranonce"],
            saved["frontier_nonce"]) == (0, 1 << 31), saved

    compute2 = FakeCompute({})
    engine2 = make_engine(rpc, template, compute2, ckpt,
                          batch_size=1 << 31, extranonce_space=(0, 1))
    r2 = engine2.mine_cycle(max_batches=10, deadline_seconds=10000)
    assert r2["reason"] == "nonce space exhausted", r2
    assert compute2.searched == [(0, 1 << 31, 1 << 31)], \
        compute2.searched
    print("ok: mid-round frontier resumes inside the round, "
          "at the exact nonce")


def test_checkpoint_unit(tmp):
    path = os.path.join(tmp, "unit.json")
    ck = WorkCheckpoint(path)
    status, en, nonce, note = ck.resume(b"\x01" * 32, (0, 64), 123)
    assert status == "fresh" and en is None, (status, note)

    ck.record(b"\x01" * 32, 100, "11" * 32, 123, (0, 64), 5, 999)
    assert not os.path.exists(path + ".tmp")
    status, en, nonce, note = ck.resume(b"\x01" * 32, (0, 64), 123)
    assert (status, en, nonce) == ("resume", 5, 999), (status, en,
                                                      nonce)
    # Every match rule refuses independently.
    assert ck.resume(b"\x02" * 32, (0, 64), 123)[0] == "fresh"
    assert ck.resume(b"\x01" * 32, (0, 32), 123)[0] == "fresh"
    assert ck.resume(b"\x01" * 32, (0, 64), 124)[0] == "fresh"
    # A frontier outside the space is refused, not trusted.
    ck.record(b"\x01" * 32, 100, "11" * 32, 123, (0, 64), 5000, 0)
    status, _, _, note = ck.resume(b"\x01" * 32, (0, 64), 123)
    assert status == "fresh" and "outside" in note, (status, note)
    # Completion is a distinct verdict from resume.
    ck.record(b"\x01" * 32, 100, "11" * 32, 123, (0, 64), 64, 0,
              complete=True)
    assert ck.resume(b"\x01" * 32, (0, 64), 123)[0] == "exhausted"
    # Corruption starts fresh and says so.
    with open(path, "w") as f:
        f.write("{not json")
    status, _, _, note = ck.resume(b"\x01" * 32, (0, 64), 123)
    assert status == "fresh" and "corrupt" in note, (status, note)
    print("ok: checkpoint match rules, completion verdict, "
          "out-of-space and corrupt-file handling")


def test_no_checkpoint_is_historical(tmp):
    template = make_template()
    rpc = FakeRPC(template)
    compute = FakeCompute({})
    engine = MiningEngine(rpc, PAYOUT, compute=compute,
                          batch_size=1 << 32, extranonce_space=(0, 1))
    header_to_en = {engine.build_candidate(template, 0)["header"]: 0}
    compute.map = header_to_en
    r1 = engine.mine_cycle(max_batches=5, deadline_seconds=10000)
    assert r1["reason"] == "nonce space exhausted", r1
    assert "checkpoint" not in r1, r1
    r2 = engine.mine_cycle(max_batches=5, deadline_seconds=10000)
    assert compute.searched == [(0, 0, 1 << 32)] * 2, \
        compute.searched
    print("ok: without a checkpoint the engine rescans exactly "
          "as it always did, and results carry no checkpoint key")


def main():
    with tempfile.TemporaryDirectory() as tmp:
        test_resume_across_restart(tmp)
    with tempfile.TemporaryDirectory() as tmp:
        test_mid_round_frontier(tmp)
    with tempfile.TemporaryDirectory() as tmp:
        test_checkpoint_unit(tmp)
        test_no_checkpoint_is_historical(tmp)
    print("ALL EXP-038 CHECKPOINT TESTS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
