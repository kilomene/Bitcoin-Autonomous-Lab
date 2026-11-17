"""EXP-057 Gates 2, 3 and 5: share validation differentials,
identity spoofing and stale work injection, restart behaviour.

All workers are in-process on this VM against a synthetic
workbase built by the production SoloServer machinery from
a FakeRPC template (nBits at the difficulty-1 target, so
block candidacy is decidable but rare, and the EXP-036
verdict is computable directly for every corpus entry).
No other machine is contacted; no upstream submitter is
ever invoked by the tier (a counting spy proves it).
"""

import hashlib
import json
import os
import random
import struct
import sys
import time
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, ROOT)

from mining.aggregation import AggregationTier, IdentityError  # noqa: E402
from mining.candidate_verify import verify_candidate  # noqa: E402
from mining.pow_engine import POW_LIMIT_REGTEST  # noqa: E402

PREDECLARATION_SHA256 = \
    "3cf0ed03b65e220092603e75b16b26a9ad741f57ca4f3590d87177b5e923c01a"
FLEET = "nova-fleet-exp057"
SHARE_DIFFICULTY = 2.0 ** -28   # share target about 2^252
PAYOUT = "exp057-synthetic-payout"


def check_predeclaration():
    with open(os.path.join(HERE, "PREDECLARATION.md"),
              "rb") as fh:
        assert hashlib.sha256(fh.read()).hexdigest() \
            == PREDECLARATION_SHA256


class FakeRPC:
    """A node-shaped stub: getblockchaininfo,
    validateaddress and getblocktemplate over a fixed
    regtest-shaped template the test can advance."""

    def __init__(self):
        self.height = 100
        self.prevhash = "00" * 32
        self.curtime = int(time.time())

    def advance(self):
        self.height += 1
        self.prevhash = hashlib.sha256(
            bytes.fromhex(self.prevhash)).hexdigest()
        self.curtime += 600

    def call(self, method, *args):
        if method == "getblockchaininfo":
            return {"chain": "regtest", "blocks": self.height - 1,
                    "headers": self.height - 1,
                    "initialblockdownload": False,
                    "bestblockhash": self.prevhash}
        if method == "validateaddress":
            return {"isvalid": True,
                    "scriptPubKey": "0014" + "11" * 20}
        if method == "getblocktemplate":
            return {"height": self.height,
                    "coinbasevalue": 5000000000,
                    "previousblockhash": self.prevhash,
                    "transactions": [], "bits": "1d00ffff",
                    "version": 0x20000000,
                    "curtime": self.curtime,
                    "mintime": self.curtime - 1000}
        raise ValueError("FakeRPC: unexpected %r" % method)


def make_tier(spy=None):
    rpc = FakeRPC()
    tier = AggregationTier(
        rpc, PAYOUT, FLEET, share_difficulty=SHARE_DIFFICULTY,
        expected_chain="regtest", operator_token="op-token-057",
        submitter=spy)
    tier.refresh_workbase()
    return tier, rpc


def direct_verdict(tier, job, en1, en2, ntime, nonce):
    """The Gate 2 reference: EXP-036 verify_candidate on the
    header the production validate_share reconstructs,
    mapped through the tier's stated mapping."""
    res, err = tier.solo.validate_share(job, en1, en2, ntime,
                                        nonce)
    if err:
        return False, "invalid"
    v = verify_candidate(res["header"], POW_LIMIT_REGTEST,
                         share_target=tier.share_target)
    if v["classification"] == "invalid":
        return False, "invalid"
    if v["meets_network_target"]:
        return True, "block_candidate"
    if v["meets_share_target"]:
        return True, "share"
    return False, "below_target"


def gate2(rng):
    spy_calls = []
    tier, _rpc = make_tier(
        spy=lambda *a: spy_calls.append(a) or {"accepted": False})
    tier.enroll_worker("w1", "tok-w1")
    sid, en1 = tier.open_session("w1", FLEET, "tok-w1")
    job = tier.current_job()
    job_id = job["job_id"]
    curtime = job["template"]["curtime"]
    mintime = job["template"]["mintime"]
    used = set()
    corpus = []

    def fresh(en2, ntime, nonce):
        key = (en2, ntime, nonce)
        if key in used:
            return False
        used.add(key)
        corpus.append((en2, ntime, nonce))
        return True

    while len(corpus) < 3000:
        en2 = struct.pack(">I", rng.getrandbits(32)).hex()
        nonce = struct.pack(">I", rng.getrandbits(32)).hex()
        fresh(en2, "%08x" % curtime, nonce)
    invalid_made = 0
    while invalid_made < 80:   # bad extranonce2 size
        en2 = struct.pack(">I", rng.getrandbits(32)).hex()[:6]
        nonce = struct.pack(">I", rng.getrandbits(32)).hex()
        if fresh(en2, "%08x" % curtime, nonce):
            invalid_made += 1
    invalid_made = 0
    while invalid_made < 80:   # ntime before mintime
        en2 = struct.pack(">I", rng.getrandbits(32)).hex()
        nonce = struct.pack(">I", rng.getrandbits(32)).hex()
        if fresh(en2, "%08x" % (mintime - 1), nonce):
            invalid_made += 1
    invalid_made = 0
    while invalid_made < 80:   # ntime too far in the future
        en2 = struct.pack(">I", rng.getrandbits(32)).hex()
        nonce = struct.pack(">I", rng.getrandbits(32)).hex()
        if fresh(en2, "%08x" % (int(time.time()) + 10000), nonce):
            invalid_made += 1
    agree = 0
    tally = {}
    for en2, ntime, nonce in corpus:
        exp_acc, exp_cat = direct_verdict(tier, job, en1, en2,
                                          ntime, nonce)
        out = tier.submit_share(sid, job_id, en2, ntime, nonce)
        got_cat = out["category"]
        ok = (out["accepted"] == exp_acc and got_cat == exp_cat)
        tally[exp_cat] = tally.get(exp_cat, 0) + 1
        assert ok, ("gate2 disagreement", en2, ntime, nonce,
                    exp_acc, exp_cat, out)
        agree += 1
    # Unknown job entries: direct reference is the tier's own
    # stated category; verify_candidate is not reachable for
    # a job that does not exist, so these are counted apart.
    unknown = 0
    for _ in range(60):
        en2 = struct.pack(">I", rng.getrandbits(32)).hex()
        nonce = struct.pack(">I", rng.getrandbits(32)).hex()
        out = tier.submit_share(sid, "deadbeef", en2,
                                "%08x" % curtime, nonce)
        assert out["category"] == "unknown_job" \
            and not out["accepted"], out
        unknown += 1
    tier.assert_accounting_identity()
    assert spy_calls == [] and tier.upstream_submissions == 0
    return {"corpus": len(corpus), "agree": agree,
            "unknown_job_entries": unknown, "tally": tally}


def gate3_one(rng, n_workers):
    spy_calls = []
    tier, rpc = make_tier(
        spy=lambda *a: spy_calls.append(a) or {"accepted": False})
    workers = ["w%d" % i for i in range(n_workers)]
    sessions = {}
    for w in workers:
        tier.enroll_worker(w, "tok-%s" % w)
        sessions[w] = tier.open_session(w, FLEET, "tok-%s" % w)
    job = tier.current_job()
    job_id = job["job_id"]
    curtime = job["template"]["curtime"]
    harness = {c: 0 for c in
               ("accepted", "below_target", "invalid", "stale",
                "duplicate", "unknown_job")}
    identity_rejected = 0

    def submit(w, en2, ntime, nonce, jid=None):
        out = tier.submit_share(sessions[w][0], jid or job_id,
                                en2, ntime, nonce)
        cat = out["category"]
        harness["accepted" if cat in ("share", "block_candidate")
                else cat] += 1
        return out

    # Legitimate traffic: 10 submissions per worker.
    first_share = {}
    for w in workers:
        for i in range(10):
            en2 = struct.pack(">I", rng.getrandbits(32)).hex()
            nonce = struct.pack(">I", rng.getrandbits(32)).hex()
            out = submit(w, en2, "%08x" % curtime, nonce)
            if i == 0:
                first_share[w] = (en2, "%08x" % curtime, nonce)
    # Replay: each worker's first share again -> duplicate.
    for w in workers:
        en2, ntime, nonce = first_share[w]
        out = tier.submit_share(sessions[w][0], job_id, en2,
                                ntime, nonce)
        assert out["category"] == "duplicate", out
        harness["duplicate"] += 1
    # Identity injections: every one must raise IdentityError.
    def expect_identity(fn):
        nonlocal identity_rejected
        try:
            fn()
        except IdentityError:
            identity_rejected += 1
            return
        raise AssertionError("spoof was not rejected")

    expect_identity(lambda: tier.open_session(
        "ghost", FLEET, "tok-ghost"))                    # unenrolled
    expect_identity(lambda: tier.open_session(
        workers[0], "other-fleet", "tok-%s" % workers[0]))  # fleet
    expect_identity(lambda: tier.open_session(
        workers[0], FLEET, "wrong-token"))               # wrong token
    expect_identity(lambda: tier.open_session(
        workers[0], FLEET, "tok-%s" % workers[-1]))      # other's token
    victim = workers[0]
    attacker = workers[-1]
    expect_identity(lambda: tier.submit_share(           # hijack claim
        sessions[attacker][0], job_id,
        struct.pack(">I", rng.getrandbits(32)).hex(),
        "%08x" % curtime,
        struct.pack(">I", rng.getrandbits(32)).hex(),
        claimed_worker=victim))
    expect_identity(lambda: tier.submit_share(           # dead session
        "S999999", job_id,
        struct.pack(">I", rng.getrandbits(32)).hex(),
        "%08x" % curtime,
        struct.pack(">I", rng.getrandbits(32)).hex()))
    # Closed session: open, close, submit.
    sid_tmp, _ = tier.open_session(workers[0], FLEET,
                                   "tok-%s" % workers[0])
    tier.close_session(sid_tmp)
    expect_identity(lambda: tier.submit_share(
        sid_tmp, job_id,
        struct.pack(">I", rng.getrandbits(32)).hex(),
        "%08x" % curtime,
        struct.pack(">I", rng.getrandbits(32)).hex()))
    # Unknown job through a legitimate session.
    out = tier.submit_share(
        sessions[workers[0]][0], "cafebabe",
        struct.pack(">I", rng.getrandbits(32)).hex(),
        "%08x" % curtime,
        struct.pack(">I", rng.getrandbits(32)).hex())
    assert out["category"] == "unknown_job", out
    harness["unknown_job"] += 1
    # Stale injection: refresh the workbase, then submit
    # against the superseded job id.
    rpc.advance()
    tier.refresh_workbase()
    new_job = tier.current_job()
    assert new_job["job_id"] != job_id
    for w in workers:
        out = tier.submit_share(
            sessions[w][0], job_id,
            struct.pack(">I", rng.getrandbits(32)).hex(),
            "%08x" % curtime,
            struct.pack(">I", rng.getrandbits(32)).hex())
        assert out["category"] == "stale" \
            and not out["accepted"], out
        harness["stale"] += 1
    # Exact accounting, global and per worker.
    tier.assert_accounting_identity()
    for cat, n in harness.items():
        assert tier.counters[cat] == n, (cat, tier.counters, harness)
    assert tier.counters["identity_rejected"] == identity_rejected, \
        (tier.counters["identity_rejected"], identity_rejected)
    assert identity_rejected == 7, identity_rejected
    assert spy_calls == [] and tier.upstream_submissions == 0
    return {"workers": n_workers, "harness": harness,
            "identity_rejected": identity_rejected,
            "exp037_submitted":
                tier.stats.snapshot()["totals"]
                ["pool_shares_submitted"]}


def gate5(rng):
    tier, _rpc = make_tier()
    tier.enroll_worker("w1", "tok-w1")
    tier.enroll_worker("w2", "tok-w2")
    sid1, _e1 = tier.open_session("w1", FLEET, "tok-w1")
    job = tier.current_job()
    job_id = job["job_id"]
    curtime = job["template"]["curtime"]
    sent = []
    for _ in range(12):
        en2 = struct.pack(">I", rng.getrandbits(32)).hex()
        nonce = struct.pack(">I", rng.getrandbits(32)).hex()
        tier.submit_share(sid1, job_id, en2, "%08x" % curtime,
                          nonce)
        sent.append((en2, "%08x" % curtime, nonce))
    # A planted pending candidate, labelled as such: it
    # exercises persistence mechanics only (a real verified
    # candidate's persistence is the same code path; Gate 6
    # produces the real one on regtest).
    tier.pending_candidates.append({
        "job_id": job_id, "worker": "w1",
        "header": "00" * 80, "coinbase": "00" * 40,
        "hash": "ab" * 32, "stale": False,
        "verify_reason": "planted-for-persistence-test"})
    before = tier.accounting()
    path = os.path.join(HERE, "RAW_RESULTS",
                        "gate5_snapshot.json")
    tier.write_snapshot(path)
    tier2 = AggregationTier.restore(
        path, FakeRPC(), PAYOUT,
        share_difficulty=SHARE_DIFFICULTY,
        expected_chain="regtest")
    after = tier2.accounting()
    assert tier2.epoch == before["epoch"] + 1
    assert after["categories"] == before["categories"], \
        (before, after)
    assert after["pending_candidates"] == 1
    assert tier2.pending_candidates[0]["verify_reason"] \
        == "planted-for-persistence-test"
    # Pre-restart session is dead.
    try:
        tier2.submit_share(sid1, job_id, sent[0][0], sent[0][1],
                           sent[0][2])
        raise AssertionError("pre-restart session survived")
    except IdentityError:
        pass
    # Fresh session: dedup survived (replay is a duplicate)
    # and new work is accounted.
    sid2, _ = tier2.open_session("w1", FLEET, "tok-w1")
    out = tier2.submit_share(sid2, job_id, sent[0][0],
                             sent[0][1], sent[0][2])
    assert out["category"] == "duplicate", out
    en2 = struct.pack(">I", rng.getrandbits(32)).hex()
    nonce = struct.pack(">I", rng.getrandbits(32)).hex()
    tier2.submit_share(sid2, job_id, en2, "%08x" % curtime,
                       nonce)
    tier2.assert_accounting_identity()
    return {"epoch_before": before["epoch"],
            "epoch_after": tier2.epoch,
            "categories_preserved": after["categories"],
            "pending_preserved": 1}


def main():
    check_predeclaration()
    rng = random.Random(20261117)
    out = {"experiment": "EXP-057",
           "host_cpu": "AMD EPYC 9D25",
           "predeclaration_sha256": PREDECLARATION_SHA256,
           "when_utc": datetime.now(timezone.utc).strftime(
               "%Y%m%dT%H%M%SZ")}
    print("EXP-057 Gate 2: differentials ...", flush=True)
    out["gate2"] = gate2(rng)
    print("Gate 2 PASS:", out["gate2"], flush=True)
    out["gate3"] = []
    for n in (2, 4, 8):
        print("EXP-057 Gate 3: %d workers ..." % n, flush=True)
        r = gate3_one(rng, n)
        out["gate3"].append(r)
        print("Gate 3 PASS (%d workers):" % n, r, flush=True)
    print("EXP-057 Gate 5: restart ...", flush=True)
    out["gate5"] = gate5(rng)
    print("Gate 5 PASS:", out["gate5"], flush=True)
    stamp = out["when_utc"]
    path = os.path.join(HERE, "RAW_RESULTS",
                        "campaign_%s.json" % stamp)
    with open(path, "w") as fh:
        json.dump(out, fh, indent=1, sort_keys=True)
    print("WROTE", path, flush=True)
    print("EXP-057 GATES 2, 3, 5: ALL PASSED", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
