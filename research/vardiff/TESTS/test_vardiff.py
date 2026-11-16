#!/usr/bin/env python3
"""Solo vardiff prototype verification (NOVA-ER-0004, R-12).

Gates 1 to 3 and 6 for the prototype in research/vardiff/
vardiff.py. No production file is touched and no rate is
measured or claimed (Gate 4 does not apply to this entry).

Sections:
  A  Control law under a simulated clock: convergence to the
     target interval from below and from above, hysteresis on
     increases, per-step factor caps, floor and ceiling
     clamps, idle decay to the floor inside the declared
     window, reconnect at the initial difficulty, and
     construction validation.
  B  Exactness primitives: the share target formula is
     integer-identical to production (SoloServer constructor
     and stratum_client.target_for_difficulty), and the
     acceptance comparison is exact at the boundary
     (value == target meets, value == target + 1 does not).
  C  Stub-RPC differential: with vardiff pinned at 0.02 the
     prototype's accept/reject decisions and reasons match
     the production SoloServer's exactly on a shared scripted
     share stream; in vardiff mode the same stream's duplicate
     and stale submissions are classified into their own
     categories.
  D  Live regtest over TCP: a fast client converges upward
     from the initial difficulty and its blocks are accepted
     by Bitcoin Core (Gate 6); a ceiling instance clamps; a
     duty-cycled slow client converges downward; a silent
     client decays to the floor on job changes; a stale share
     is classified and its block still reaches Core; a
     reconnect restarts at the initial difficulty; the
     adjustment log replays exactly.

The suite starts the lab regtest node only if it is not
already running, and stops it only if it started it. The
mainnet node, autopilot and miner are never touched.
"""

import json
import os
import socket
import sys
import threading
import time

# The lab RPC is loopback-only. Strip proxy configuration from
# this process so urllib can never route 127.0.0.1 traffic via
# the VM egress proxy (observed: a proxy 503 on submitblock
# while the node was healthy).
for _k in ("http_proxy", "https_proxy", "HTTP_PROXY",
           "HTTPS_PROXY", "all_proxy", "ALL_PROXY"):
    os.environ.pop(_k, None)
os.environ["NO_PROXY"] = "127.0.0.1,localhost"
os.environ["no_proxy"] = "127.0.0.1,localhost"

sys.path.insert(0, os.path.join(os.path.dirname(__file__),
                                "..", "..", ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from gpu.engine import ComputeEngine              # noqa: E402
from mining.candidate_verify import meets_target   # noqa: E402
from mining.pow import dsha256                     # noqa: E402
from mining.solo_server import SoloServer          # noqa: E402
from mining.stratum_client import (build_header,   # noqa: E402
                                   target_for_difficulty)
from node import node_manager                      # noqa: E402
from node.rpc_client import BitcoinRPC             # noqa: E402
from vardiff import (DIFF1, VarDiffController,     # noqa: E402
                     VarDiffSoloServer, VarDiffTCPServer,
                     share_target_for)

RESULTS = []


def check(name, cond, detail=""):
    RESULTS.append((name, bool(cond), detail))
    print(f"{'ok' if cond else 'FAIL'}: {name}"
          + (f" ({detail})" if detail and not cond else ""))


# ---------------------------------------------------------------- A
def section_a():
    print("== A: control law, simulated clock ==")
    H = 2**32 * 0.05 / 15.0  # equilibrium difficulty 0.05

    def drive(ctrl, shares):
        st = ctrl.new_connection(0.0)
        t = 0.0
        recs = []
        for _ in range(shares):
            t += st["difficulty"] * 2**32 / H
            r = ctrl.on_accepted_share(st, t)
            if r:
                recs.append(r)
        return st, recs

    # Convergence from below (initial 0.02 < equilibrium 0.05).
    ctrl = VarDiffController()
    st, recs = drive(ctrl, 120)
    check("A1 convergence from below lands near equilibrium",
          0.038 <= st["difficulty"] <= 0.075,
          f"final {st['difficulty']}")
    ups = [r for r in recs if r["new"] > r["old"]]
    check("A2 convergence from below is by increases only",
          len(ups) == len(recs) and len(ups) >= 2,
          f"{len(ups)} increases of {len(recs)} records")
    check("A3 per-step increase cap 1.5x respected",
          all(r["new"] / r["old"] <= 1.5 + 1e-12 for r in ups))
    check("A4 settled interval inside the target band",
          10.0 <= st["ema_interval"] <= 22.0,
          f"ema {st['ema_interval']}")

    # Convergence from above (initial 0.5 > equilibrium 0.05).
    # The EMA seeded by the first 150 s interval lags the
    # descent, so the controller overshoots below equilibrium
    # and climbs back under hysteresis; the share count is
    # sized for the full round trip (simulated time is free).
    ctrl = VarDiffController(initial=0.5)
    st, recs = drive(ctrl, 400)
    downs = [r for r in recs if r["new"] < r["old"]]
    check("A5 convergence from above lands near equilibrium",
          0.035 <= st["difficulty"] <= 0.095,
          f"final {st['difficulty']}")
    check("A6 decreases lead, capped at 2x per step",
          len(downs) >= 3 and all(
              r["old"] / r["new"] <= 2.0 + 1e-12 for r in downs))

    # Hysteresis: one fast share never raises; a second within
    # the grace period after an increase does not either.
    ctrl = VarDiffController()
    st = ctrl.new_connection(0.0)
    ctrl.on_accepted_share(st, 0.0)
    r = ctrl.on_accepted_share(st, 1.0)  # first interval, vote 1
    check("A7 single fast share does not raise difficulty",
          r is None and st["difficulty"] == 0.02)
    r = ctrl.on_accepted_share(st, 2.0)  # vote 2: first increase
    check("A8 confirmed fast shares raise difficulty",
          r is not None and r["new"] > r["old"] == 0.02)
    t_up = 2.0
    raised = None
    for i in range(1, 45):
        r = ctrl.on_accepted_share(st, t_up + i * 1.0)
        if r is not None:
            raised = t_up + i * 1.0
            break
    check("A9 grace period blocks the next increase",
          raised is not None and raised - t_up >= 30.0,
          f"second increase at {raised}")

    # Floor: hopeless intervals decay the difficulty to the
    # floor and it stays there, with a clamp recorded.
    ctrl = VarDiffController()
    st = ctrl.new_connection(0.0)
    recs = []
    t = 0.0
    for _ in range(30):
        t += 10000.0
        r = ctrl.on_accepted_share(st, t)
        if r:
            recs.append(r)
    check("A10 floor reached and held",
          st["difficulty"] == ctrl.floor
          and any(r["clamped"] for r in recs),
          f"final {st['difficulty']}")

    # Ceiling: flooding shares raise to the ceiling and clamp.
    ctrl = VarDiffController(ceiling=0.05)
    st = ctrl.new_connection(0.0)
    recs = []
    t = 0.0
    for _ in range(3000):
        t += 0.1
        r = ctrl.on_accepted_share(st, t)
        if r:
            recs.append(r)
    check("A11 ceiling reached and held under flooding",
          st["difficulty"] == 0.05
          and any(r["clamped"] for r in recs),
          f"final {st['difficulty']}")

    # Idle decay: no shares at all, job changes only. Declared
    # window: threshold 60 s, then one halving per job change,
    # floor in at most 4 steps from the initial 0.02.
    ctrl = VarDiffController()
    st = ctrl.new_connection(0.0)
    seq = []
    check("A12 no decay before the idle threshold",
          ctrl.on_job_change(st, 30.0) is None)
    for t in (61.0, 62.0, 63.0, 64.0, 65.0):
        r = ctrl.on_job_change(st, t)
        if r:
            seq.append(r["new"])
    check("A13 idle decay steps to the floor in 4 steps",
          seq == [0.01, 0.005, 0.0025, 0.002], f"{seq}")
    check("A14 decay stops at the floor",
          ctrl.on_job_change(st, 1000.0) is None)

    # Reconnect: fresh state at the initial difficulty.
    st2 = ctrl.new_connection(5000.0)
    check("A15 reconnect starts at the initial difficulty",
          st2["difficulty"] == ctrl.initial
          and st2["ema_interval"] is None)

    # Construction validation.
    try:
        VarDiffController(floor=0.5, initial=0.02)
        ok = False
    except ValueError:
        ok = True
    check("A16 floor above initial refused at construction", ok)


# ---------------------------------------------------------------- B
def section_b():
    print("== B: exactness primitives ==")
    same = True
    for d in (0.002, 0.01, 0.02, 0.05, 0.16, 0.5, 1.0, 3.7):
        prod = SoloServer(None, "bc1qexample",
                          share_difficulty=d).share_target
        if not (share_target_for(d) == prod
                == target_for_difficulty(d)):
            same = False
    check("B1 share target formula identical to production", same)
    tgt = share_target_for(0.02)
    check("B2 boundary: value == target meets the target",
          meets_target(tgt, tgt) is True)
    check("B3 boundary: value == target + 1 does not meet",
          meets_target(tgt + 1, tgt) is False)
    check("B4 difficulty-1 target constant matches production",
          DIFF1 == int("00000000ffff" + "00" * 26, 16))


# ---------------------------------------------------------------- C
PAYOUT = "bc1q528egeqsvv8aa382j43edxskqw6x7zxc2xpcf3"
SPK = "0014" + "11" * 20


class StubRPC:
    """Fixed synthetic template at genesis bits, so the share
    target sits far above the network target and share
    decisions are exercised without block candidates."""

    def __init__(self):
        self.template = {
            "version": 0x20000000,
            "previousblockhash": "ab" * 32,
            "transactions": [],
            "coinbasevalue": 5000000000,
            "height": 1000,
            "bits": "1d00ffff",
            "curtime": 1700000000,
            "mintime": 1,
        }
        self.submitted = []

    def call(self, method, *args):
        if method == "getblocktemplate":
            return self.template
        if method == "validateaddress":
            return {"isvalid": True, "scriptPubKey": SPK}
        if method == "getblockchaininfo":
            return {"chain": "regtest", "blocks": 1000,
                    "headers": 1000,
                    "initialblockdownload": False,
                    "bestblockhash": "ab" * 32}
        if method == "submitblock":
            self.submitted.append(args[0])
            return None
        raise ValueError(method)


def client_job(server):
    job = server.current
    p = server.notify_params(job)
    return {"job_id": p[0], "prevhash": p[1], "coinb1": p[2],
            "coinb2": p[3], "merkle_branch": p[4],
            "version": p[5], "nbits": p[6], "ntime": p[7]}


def find_share(engine, job, en1_hex, en2, target):
    hdr0, _, _ = build_header(job, en1_hex, f"{en2:08x}", 0,
                              "wordswap")
    start = 0
    while start < (1 << 32):
        hit = engine.search_first(hdr0, target, start, 1 << 22)
        if hit:
            return hit[0]
        start += 1 << 22
    raise RuntimeError("no share found")


def find_share_only(engine, job, en1_hex, en2, share_target,
                    net_target):
    """A share meeting the share target but NOT the network
    target (at genesis bits about 2 percent of share-target
    hits are also network hits; those take the block path and
    would blur the share classification under test)."""
    hdr0, _, _ = build_header(job, en1_hex, f"{en2:08x}", 0,
                              "wordswap")
    start = 0
    while start < (1 << 32):
        hit = engine.search_first(hdr0, share_target, start,
                                  1 << 22)
        if not hit:
            start += 1 << 22
            continue
        nonce, digest = hit
        if int.from_bytes(digest, "little") > net_target:
            return nonce
        start = nonce + 1
    raise RuntimeError("no share-only hit found")


def find_low(job, en1_hex, en2, share_target):
    """A nonce whose digest meets neither target."""
    nonce = 0
    while True:
        hdr, _, _ = build_header(job, en1_hex, f"{en2:08x}", nonce,
                                 "wordswap")
        if int.from_bytes(dsha256(hdr), "little") > share_target:
            return nonce
        nonce += 1


def section_c(engine):
    print("== C: stub differential, pinned vs production ==")
    en1 = (7).to_bytes(4, "little")
    en1_hex = en1.hex()
    target = target_for_difficulty(0.02)

    prod = SoloServer(StubRPC(), PAYOUT, share_difficulty=0.02)
    prod.refresh_job()
    pin = VarDiffSoloServer(StubRPC(), PAYOUT,
                            vardiff_enabled=False,
                            pinned_difficulty=0.02)
    pin.refresh_job()
    job = client_job(prod)
    check("C1 pinned and production jobs are identical",
          client_job(pin) == job
          and prod.current["job_id"] == pin.current["job_id"])

    n_a = find_share(engine, job, en1_hex, 1, target)
    n_b = find_share(engine, job, en1_hex, 2, target)
    n_c = find_share(engine, job, en1_hex, 4, target)
    n_low = find_low(job, en1_hex, 3, target)
    future = f"{int(time.time()) + 10000:08x}"
    stream = [
        ("valid share A", (job["job_id"], "00000001",
                            job["ntime"], f"{n_a:08x}")),
        ("valid share B", (job["job_id"], "00000002",
                            job["ntime"], f"{n_b:08x}")),
        ("low difficulty", (job["job_id"], "00000003",
                             job["ntime"], f"{n_low:08x}")),
        ("bad extranonce2 size", (job["job_id"], "aabbcc",
                                  job["ntime"], "00000000")),
        ("unknown job", ("ff", "00000001", job["ntime"],
                          "00000000")),
        ("ntime before mintime", (job["job_id"], "00000001",
                                  "00000000", f"{n_a:08x}")),
        ("ntime too far future", (job["job_id"], "00000001",
                                  future, f"{n_a:08x}")),
        ("valid share C", (job["job_id"], "00000004",
                            job["ntime"], f"{n_c:08x}")),
    ]
    mismatch = []
    for label, (jid, en2, ntime, nonce) in stream:
        a = prod.submit_share(jid, en1, en2, ntime, nonce,
                              worker="diff-worker")
        b = pin.submit_share(jid, en1, en2, ntime, nonce,
                             worker="diff-worker")
        ka = (a["accepted"], a.get("reason"),
              a.get("block") is not None)
        kb = (b["accepted"], b.get("reason"),
              b.get("block") is not None)
        if ka != kb:
            mismatch.append((label, a, b))
    check("C2 pinned decisions match production on the stream",
          not mismatch, f"{mismatch}")
    check("C3 pinned counters match production counters",
          (prod.shares_accepted, prod.shares_rejected)
          == (pin.shares_accepted, pin.shares_rejected),
          f"prod {(prod.shares_accepted, prod.shares_rejected)} "
          f"pin {(pin.shares_accepted, pin.shares_rejected)}")

    print("== C2: vardiff-mode classification on the stub ==")
    vd = VarDiffSoloServer(
        StubRPC(), PAYOUT,
        controller=VarDiffController(up_hysteresis_s=0.0))
    vd.register_connection(en1)
    vd.refresh_job()
    vjob = client_job(vd)
    n_v = find_share_only(engine, vjob, en1_hex, 1, target,
                          vd.current["target"])
    out = vd.submit_share(vjob["job_id"], en1, "00000001",
                          vjob["ntime"], f"{n_v:08x}",
                          worker="vd-worker")
    check("C4 vardiff mode accepts a valid share as a share",
          out["accepted"] and out["classification"] == "share",
          f"{out}")
    out = vd.submit_share(vjob["job_id"], en1, "00000001",
                          vjob["ntime"], f"{n_v:08x}",
                          worker="vd-worker")
    check("C5 exact repeat is classified duplicate",
          not out["accepted"]
          and out["classification"] == "duplicate"
          and vd.shares_duplicate == 1
          and vd.shares_accepted == 1, f"{out}")
    # Supersede the job, then answer the old one.
    n_old = find_share_only(engine, vjob, en1_hex, 2, target,
                            vd.current["target"])
    n_old_low = find_low(vjob, en1_hex, 3, target)
    vd.refresh_job()
    out = vd.submit_share(vjob["job_id"], en1, "00000002",
                          vjob["ntime"], f"{n_old:08x}",
                          worker="vd-worker")
    check("C6 share for a superseded job is classified stale",
          not out["accepted"]
          and out["classification"] == "stale"
          and vd.shares_stale == 1
          and vd.shares_accepted == 1, f"{out}")
    out = vd.submit_share(vjob["job_id"], en1, "00000003",
                          vjob["ntime"], f"{n_old_low:08x}",
                          worker="vd-worker")
    check("C7 below-target stale share is stale, not accepted",
          not out["accepted"]
          and out["classification"] == "stale"
          and "below target" in out["reason"]
          and vd.shares_stale == 2, f"{out}")
    out = vd.submit_share("ff", en1, "00000001", vjob["ntime"],
                          "00000000", worker="vd-worker")
    check("C8 never-issued job keeps the production verdict",
          not out["accepted"] and out["reason"] == "unknown job",
          f"{out}")


# ---------------------------------------------------------------- D
def wallet_rpc(rpc):
    if "bal-regtest" not in rpc.call("listwallets"):
        try:
            rpc.call("loadwallet", "bal-regtest")
        except Exception:
            rpc.call("createwallet", "bal-regtest")
    return BitcoinRPC(wallet="bal-regtest")


class Worker:
    """Scripted Stratum client, following tests/test_solo_server.py."""

    def __init__(self, port, payout):
        self.sock = socket.create_connection(("127.0.0.1", port),
                                             timeout=30)
        self._buf = b""
        self.payout = payout
        self.en1 = None
        self.job = None
        self.share_diff = None
        self.results = {}
        self._id = 0
        self._en2 = 0
        self.submitted = 0
        self.accepted = 0

    def send(self, obj):
        self.sock.sendall((json.dumps(obj) + "\n").encode())

    def _readline(self, timeout):
        """One newline-terminated line from our own buffer
        (a socket.makefile reader is poisoned by a single
        timed-out read; this buffer is not)."""
        self.sock.settimeout(timeout)
        while b"\n" not in self._buf:
            chunk = self.sock.recv(65536)
            if not chunk:
                raise ConnectionError("server closed connection")
            self._buf += chunk
        line, self._buf = self._buf.split(b"\n", 1)
        return line

    def rpc(self, method, params):
        self._id += 1
        self.send({"id": self._id, "method": method,
                   "params": params})
        while True:
            msg = json.loads(self._readline(60))
            if msg.get("id") == self._id:
                return msg
            self.handle_notify(msg)

    def handle_notify(self, msg):
        if msg.get("method") == "mining.set_difficulty":
            self.share_diff = msg["params"][0]
        elif msg.get("method") == "mining.notify":
            p = msg["params"]
            self.job = {"job_id": p[0], "prevhash": p[1],
                        "coinb1": p[2], "coinb2": p[3],
                        "merkle_branch": p[4], "version": p[5],
                        "nbits": p[6], "ntime": p[7]}

    def sync(self, quiet=0.6):
        """Read until the wire is quiet, applying notifies."""
        try:
            while True:
                msg = json.loads(self._readline(quiet))
                if msg.get("id") is not None:
                    continue
                self.handle_notify(msg)
        except (socket.timeout, TimeoutError):
            pass
        finally:
            self.sock.settimeout(30)

    def connect(self):
        r = self.rpc("mining.subscribe", ["bal-worker/1.0"])
        self.en1 = r["result"][1]
        r = self.rpc("mining.authorize", [self.payout, "x"])
        assert r["result"] is True
        self.sync()
        assert self.job is not None and self.share_diff is not None

    def close(self):
        try:
            self.sock.close()
        except OSError:
            pass


def mine_and_submit(w, engine, timeout=300, duty_sleep=0.0):
    """Mine the current job at the connection's difficulty and
    submit the first hit. Returns the submit response."""
    w.sync()
    deadline = time.time() + timeout
    while time.time() < deadline:
        job = dict(w.job)
        target = target_for_difficulty(w.share_diff)
        w._en2 += 1
        en2_hex = f"{w._en2:08x}"
        hdr0, _, _ = build_header(job, w.en1, en2_hex, 0,
                                  "wordswap")
        start = 0
        while start < (1 << 32) and time.time() < deadline:
            hit = engine.search_first(hdr0, target, start,
                                      1 << 22)
            if duty_sleep:
                time.sleep(duty_sleep)
            if hit:
                nonce, _digest = hit
                w.submitted += 1
                resp = w.rpc("mining.submit",
                             [w.payout, job["job_id"], en2_hex,
                              job["ntime"], f"{nonce:08x}"])
                if resp.get("result") is True:
                    w.accepted += 1
                w.sync()
                return resp
            start += 1 << 22
            w.sync(0.05)
            if w.job["job_id"] != job["job_id"]:
                break
    raise TimeoutError("no share mined within timeout")


def mine_without_submit(w, engine, timeout=300):
    w.sync()
    job = dict(w.job)
    target = target_for_difficulty(w.share_diff)
    w._en2 += 1
    en2_hex = f"{w._en2:08x}"
    hdr0, _, _ = build_header(job, w.en1, en2_hex, 0, "wordswap")
    start = 0
    deadline = time.time() + timeout
    while start < (1 << 32) and time.time() < deadline:
        hit = engine.search_first(hdr0, target, start, 1 << 22)
        if hit:
            return job, en2_hex, job["ntime"], f"{hit[0]:08x}"
        start += 1 << 22
    raise TimeoutError("no share mined within timeout")


def start_server(rpc, payout, port, controller):
    srv = VarDiffSoloServer(rpc, payout, controller=controller)
    tcp = VarDiffTCPServer(("127.0.0.1", port), srv)
    th = threading.Thread(target=tcp.serve_forever, daemon=True)
    th.start()
    srv.refresh_job()
    return srv, tcp


def section_d(rpc, payout, engine):
    print("== D: live regtest over TCP ==")
    tip_start = rpc.get_block_count()

    # D1: fast client converges upward; blocks reach Core.
    ctrl = VarDiffController(target_interval=15.0, initial=0.02,
                             floor=0.002, ceiling=0.5,
                             up_hysteresis_s=5.0,
                             up_confirmations=2)
    srv, tcp = start_server(rpc, payout, 33401, ctrl)
    w = Worker(33401, payout)
    w.connect()
    en1 = bytes.fromhex(w.en1)
    check("D1 subscribe serves the initial difficulty",
          w.share_diff == 0.02, f"{w.share_diff}")
    n = 0
    while n < 10 and srv.connection_difficulty(en1) < 0.05:
        mine_and_submit(w, engine, timeout=240)
        n += 1
    final_d = srv.connection_difficulty(en1)
    entries = [e for e in srv.adjustment_log
               if e["connection"] == w.en1]
    ups = [e for e in entries if e["new"] > e["old"]]
    check("D2 fast client drives difficulty upward",
          final_d >= 0.04 and len(ups) >= 2,
          f"final {final_d}, {len(ups)} increases, {n} shares")
    chain_ok = (entries and entries[0]["old"] == 0.02
                and all(entries[i]["old"] == entries[i - 1]["new"]
                        for i in range(1, len(entries)))
                and entries[-1]["new"] == final_d)
    fields_ok = all(
        set(e) >= {"ts", "connection", "worker", "reason", "old",
                   "new", "ema_interval", "clamped"}
        for e in entries)
    check("D3 adjustment log is complete and replayable",
          bool(chain_ok) and fields_ok,
          f"{len(entries)} entries")
    acc_blocks = [b for b in srv.blocks_found if b["accepted"]]
    check("D4 Gate 6: blocks mined via vardiff accepted by Core",
          len(acc_blocks) >= 1
          and len(acc_blocks) == w.accepted,
          f"{len(acc_blocks)} accepted blocks, "
          f"{w.accepted} accepted shares")
    hdr = rpc.call("getblockheader", acc_blocks[-1]["hash"], True)
    check("D5 accepted block is in the active chain",
          hdr.get("confirmations", 0) >= 1
          and rpc.get_block_count() > tip_start,
          f"confirmations {hdr.get('confirmations')}")
    st = srv.stats()
    identity = (w.submitted == st["shares_accepted"]
                + st["shares_rejected"]
                + st["vardiff"]["shares_stale"]
                + st["vardiff"]["shares_duplicate"])
    check("D6 accounting identity: submissions split exactly "
          "across disjoint categories",
          identity and w.accepted == st["shares_accepted"],
          f"submitted {w.submitted}, accepted "
          f"{st['shares_accepted']}, rejected "
          f"{st['shares_rejected']}")

    # D5 (reconnect) reuses this server while its difficulty
    # is above the initial value.
    w.close()
    time.sleep(0.3)
    w2 = Worker(33401, payout)
    w2.connect()
    check("D7 reconnect restarts at the initial difficulty",
          w2.share_diff == 0.02
          and srv.connection_difficulty(bytes.fromhex(w2.en1))
          == 0.02, f"{w2.share_diff}")
    w2.close()
    tcp.shutdown()

    # D8: ceiling clamp under a flooding client. The target
    # interval on this instance is 60 s, not the 15 s default:
    # "flooding" is relative to the target, and on this
    # contended VM a 0.02 share takes roughly 17 s of wall
    # time, which is flooding against a 60 s target but not
    # against 15 s. The property under test is the clamp.
    ctrl = VarDiffController(target_interval=60.0, initial=0.02,
                             floor=0.002, ceiling=0.035,
                             up_hysteresis_s=0.0,
                             up_confirmations=1)
    srv, tcp = start_server(rpc, payout, 33402, ctrl)
    w = Worker(33402, payout)
    w.connect()
    en1 = bytes.fromhex(w.en1)
    for _ in range(6):
        mine_and_submit(w, engine, timeout=240)
    entries = [e for e in srv.adjustment_log
               if e["connection"] == w.en1]
    check("D8 ceiling clamps a flooding client",
          srv.connection_difficulty(en1) == 0.035
          and any(e["clamped"] for e in entries)
          and all(e["new"] <= 0.035 for e in entries),
          f"final {srv.connection_difficulty(en1)}")
    w.close()
    tcp.shutdown()

    # D9: duty-cycled slow client converges downward.
    ctrl = VarDiffController(target_interval=15.0, initial=0.10,
                             floor=0.002, ceiling=1.0)
    srv, tcp = start_server(rpc, payout, 33403, ctrl)
    w = Worker(33403, payout)
    w.connect()
    en1 = bytes.fromhex(w.en1)
    for _ in range(4):
        mine_and_submit(w, engine, timeout=420, duty_sleep=0.3)
    entries = [e for e in srv.adjustment_log
               if e["connection"] == w.en1]
    downs = [e for e in entries if e["new"] < e["old"]]
    check("D9 slow client drives difficulty downward",
          len(downs) >= 2
          and srv.connection_difficulty(en1) <= 0.03,
          f"final {srv.connection_difficulty(en1)}, "
          f"{len(downs)} decreases")
    w.close()
    tcp.shutdown()

    # D10: silent client decays to the floor on job changes.
    ctrl = VarDiffController(target_interval=15.0, initial=0.02,
                             floor=0.002, ceiling=1.0,
                             decay_after_s=5.0, decay_factor=2.0)
    srv, tcp = start_server(rpc, payout, 33404, ctrl)
    w = Worker(33404, payout)
    w.connect()
    en1 = bytes.fromhex(w.en1)
    for _ in range(16):
        srv.refresh_job()
        time.sleep(1.2)
    entries = [e for e in srv.adjustment_log
               if e["connection"] == w.en1]
    decays = [e for e in entries if e["reason"] == "idle decay"]
    check("D10 silent client decays to the floor",
          srv.connection_difficulty(en1) == 0.002
          and len(decays) >= 3,
          f"final {srv.connection_difficulty(en1)}, "
          f"{len(decays)} decay steps")
    w.close()
    tcp.shutdown()

    # D11: stale share over the wire, block still reaches Core.
    ctrl = VarDiffController(target_interval=15.0, initial=0.02,
                             floor=0.002, ceiling=1.0,
                             up_hysteresis_s=5.0)
    srv, tcp = start_server(rpc, payout, 33405, ctrl)
    w = Worker(33405, payout)
    w.connect()
    job1, en2_hex, ntime, nonce_hex = mine_without_submit(
        w, engine, timeout=240)
    tip0 = rpc.get_block_count()
    srv.refresh_job()
    check("D11 job superseded by refresh",
          srv.current["job_id"] != job1["job_id"])
    w.submitted += 1
    resp = w.rpc("mining.submit",
                 [payout, job1["job_id"], en2_hex, ntime,
                  nonce_hex])
    reason = (resp.get("error") or [None, "", None])[1]
    rec = srv.blocks_found[-1] if srv.blocks_found else {}
    check("D12 stale share classified, never accepted as share",
          resp.get("result") is False and "stale" in reason
          and srv.shares_stale == 1 and srv.shares_accepted == 0,
          f"reason {reason!r}")
    check("D13 stale block candidate still reached Core",
          rec.get("stale") is True and rec.get("accepted")
          is True and rpc.get_block_count() == tip0 + 1
          and rpc.get_best_block_hash() == rec.get("hash"),
          f"{rec.get('hash')}")
    w.close()
    tcp.shutdown()


def main():
    started_node = False
    if not node_manager.is_running():
        node_manager.start()
        started_node = True
    try:
        rpc = BitcoinRPC()
        wallet = wallet_rpc(rpc)
        payout = wallet.call("getnewaddress", "", "bech32")
        engine = ComputeEngine()
        section_a()
        section_b()
        section_c(engine)
        section_d(rpc, payout, engine)
    finally:
        if started_node:
            node_manager.stop()
    failed = [r for r in RESULTS if not r[1]]
    print(f"\n{len(RESULTS) - len(failed)}/{len(RESULTS)} "
          f"checks passed")
    if failed:
        print("FAILED:", [r[0] for r in failed])
        return 1
    print("ALL VARDIFF TESTS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
