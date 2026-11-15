#!/usr/bin/env python3
"""EXP-040 category F end-to-end pipeline benchmark harness.

Times the production GBT mining pipeline as one system:
MiningEngine.mine_cycle (mining/engine.py) against the local
regtest Bitcoin Core node, unmodified. Stage attribution is
by wrapping, in this process only, the objects handed to the
harness's own engine instance: a delegating RPC proxy (GBT
fetch, submitblock, best-chain confirmation, other RPC), a
prepare_template wrapper plus a per-instance
PreparedTemplate.build wrapper (template prepare and
candidate construction steps), and a delegating compute
proxy (counted search). No production file is changed.

After each accepted cycle, the winning block's 80-byte
header is verified with the EXP-036 exact verifier
(mining.candidate_verify.verify_candidate) and that call is
timed as the verification component. A run counts only if
mine_cycle ended accepted AND the verifier classifies the
header "block_candidate" with a digest equal to the block
hash the node accepted; anything else is recorded as a
failed run and excluded from statistics.

Scenarios (see EXP040_REPORT.md section 1 for the design):
  A  empty mempool, real regtest target.
  B  mempool loaded with N simple wallet transactions,
     real regtest target.
  C  empty mempool, search target divided by 2^24 inside
     the compute proxy (harness-side difficulty
     amplification; found blocks still meet the real
     regtest target and are accepted by Core normally).

Usage:
  python3 category_f.py run-all [--runs-ab 8] [--runs-c 5]
  python3 category_f.py run --scenario A --sessions 1 --runs 2

Session files are append-only JSON in RAW_RESULTS next to
this file; a rerun creates new files, never overwrites.
"""

import argparse
import hashlib
import json
import os
import platform
import sys
import time
from contextlib import contextmanager
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, ROOT)

from mining.candidate_verify import verify_candidate          # noqa: E402
from mining.engine import MiningEngine                        # noqa: E402
from mining.pow_engine import POW_LIMIT_REGTEST               # noqa: E402
from gpu.engine import ComputeEngine                          # noqa: E402
from node.rpc_client import BitcoinRPC                        # noqa: E402

RAW_DIR = os.path.join(HERE, "RAW_RESULTS")
BATCH_SIZE = 65536
EXTRANONCE_SPACE = (0, 64)
AMPLIFY_SHIFT = 24
CONTENT_FILES = ("mining/engine.py", "mining/candidate_verify.py",
                 "gpu/engine.py")


# ---------------------------------------------------------------- timer

class SegmentTimer:
    """Stack-disciplined segment recorder. Stage totals are
    exclusive times: a segment minus the segments nested
    inside it, so nested calls are counted once, under their
    own label."""

    def __init__(self):
        self._stack = []
        self.segments = []   # [label, start, end] in closing order

    def reset(self):
        self._stack = []
        self.segments = []

    @contextmanager
    def segment(self, label):
        t0 = time.perf_counter()
        self._stack.append(label)
        try:
            yield
        finally:
            t1 = time.perf_counter()
            self._stack.pop()
            self.segments.append([label, t0, t1])

    def stage_totals(self):
        """Return ({label: seconds}, {label: calls}, covered_s).
        covered_s is the union of the outermost segments, so
        wall - covered is the unattributed residual."""
        segs = sorted(self.segments, key=lambda s: (s[1], -s[2]))
        totals = {}
        calls = {}
        # Build parent links by interval containment.
        exclusive = [s[2] - s[1] for s in segs]
        stack = []  # indices of currently open segments
        covered = 0.0
        for i, s in enumerate(segs):
            # Pop segments that ended before this one starts;
            # what remains on top, if anything, is the parent.
            while stack and segs[stack[-1]][2] <= s[1] + 1e-12:
                stack.pop()
            if stack:
                exclusive[stack[-1]] -= (s[2] - s[1])
            else:
                covered += s[2] - s[1]
            stack.append(i)
            totals[s[0]] = totals.get(s[0], 0.0)
            calls[s[0]] = calls.get(s[0], 0) + 1
        for i, s in enumerate(segs):
            totals[s[0]] += exclusive[i]
        return totals, calls, covered


# ---------------------------------------------------------------- proxies

class TimingRPC:
    """Delegating proxy over BitcoinRPC that times calls by
    method. getblocktemplate -> "gbt", submitblock ->
    "submit", get_best_block_hash -> "confirm", everything
    else -> "rpc_other" (method names counted separately)."""

    def __init__(self, real, timer):
        object.__setattr__(self, "_real", real)
        object.__setattr__(self, "_timer", timer)
        object.__setattr__(self, "method_counts", {})

    def call(self, method, *params):
        if method == "getblocktemplate":
            label = "gbt"
        elif method == "submitblock":
            label = "submit"
        else:
            label = "rpc_other"
            counts = object.__getattribute__(self, "method_counts")
            counts[method] = counts.get(method, 0) + 1
        timer = object.__getattribute__(self, "_timer")
        with timer.segment(label):
            return object.__getattribute__(self, "_real").call(
                method, *params)

    def with_timeout(self, timeout, retries=1):
        real = object.__getattribute__(self, "_real")
        timer = object.__getattribute__(self, "_timer")
        return TimingRPC(real.with_timeout(timeout, retries), timer)

    def __getattr__(self, name):
        real = object.__getattribute__(self, "_real")
        attr = getattr(real, name)
        if not callable(attr):
            return attr
        timer = object.__getattribute__(self, "_timer")
        label = "confirm" if name == "get_best_block_hash" else "rpc_other"
        if label == "rpc_other":
            counts = object.__getattribute__(self, "method_counts")
            counts[name] = counts.get(name, 0) + 1

        def timed(*args, **kwargs):
            with timer.segment(label):
                return attr(*args, **kwargs)
        return timed


class TimingCompute:
    """Delegating proxy over ComputeEngine that times the
    counted search entry. With target_shift > 0 it divides
    the search target by 2**target_shift before delegating
    (scenario C difficulty amplification; see the report)."""

    def __init__(self, real, timer, target_shift=0):
        object.__setattr__(self, "_real", real)
        object.__setattr__(self, "_timer", timer)
        object.__setattr__(self, "_shift", target_shift)

    def _target(self, target):
        shift = object.__getattribute__(self, "_shift")
        return target >> shift if shift else target

    def search_first_counted(self, header, target, start, count):
        timer = object.__getattribute__(self, "_timer")
        real = object.__getattribute__(self, "_real")
        with timer.segment("search"):
            return real.search_first_counted(
                header, self._target(target), start, count)

    def search_first(self, header, target, start, count):
        timer = object.__getattribute__(self, "_timer")
        real = object.__getattribute__(self, "_real")
        with timer.segment("search"):
            return real.search_first(
                header, self._target(target), start, count)

    def __getattr__(self, name):
        return getattr(object.__getattribute__(self, "_real"), name)


def instrument_engine(engine, timer):
    """Wrap prepare_template on this engine instance so the
    prepare step and each PreparedTemplate.build step are
    timed. The class and its methods are untouched."""
    orig_prepare = engine.prepare_template

    def timed_prepare(template):
        with timer.segment("prepare"):
            prep, was_hit = orig_prepare(template)
        if not getattr(prep, "_exp040_timed", False):
            orig_build = prep.build

            def timed_build(extranonce_int, template=None, now=None):
                with timer.segment("construct"):
                    return orig_build(extranonce_int,
                                      template=template, now=now)
            prep.build = timed_build
            prep._exp040_timed = True
        return prep, was_hit

    engine.prepare_template = timed_prepare
    return engine


# ---------------------------------------------------------------- loader

def batch_call(rpc, calls):
    """One JSON-RPC batch HTTP request for a list of
    (method, params) pairs against rpc's endpoint (wallet
    path included). Setup only: the production RPC client
    speaks one call per request, but scenario setup issues
    hundreds of dependent-free calls and batching them is
    the difference between seconds and minutes. Results are
    returned in request order; any RPC error raises."""
    import base64
    import urllib.request
    payload = json.dumps([
        {"jsonrpc": "1.0", "id": f"exp040-{i}", "method": m,
         "params": list(p)}
        for i, (m, p) in enumerate(calls)]).encode()
    req = urllib.request.Request(rpc.url, data=payload,
                                 method="POST")
    req.add_header("Content-Type", "application/json")
    auth = base64.b64encode(
        f"{rpc.user}:{rpc.password}".encode()).decode()
    req.add_header("Authorization", f"Basic {auth}")
    with urllib.request.urlopen(req, timeout=600) as resp:
        body = json.loads(resp.read().decode())
    by_id = {item["id"]: item for item in body}
    out = []
    for i, (m, _p) in enumerate(calls):
        item = by_id[f"exp040-{i}"]
        if item.get("error"):
            raise RuntimeError(f"batch {m} failed: {item['error']}")
        out.append(item.get("result"))
    return out


_SECP256K1_N = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364141


class OfflineKey:
    """A single secp256k1 key held only in this process's
    memory, generated fresh per harness process. It funds
    and signs every loader transaction offline, because on
    this host every wallet RPC that touches keys costs
    seconds (measured: getnewaddress about 2 to 4 s,
    signrawtransactionwithwallet about 1.4 s per call),
    which would make a 500-transaction reload take many
    minutes of pure setup. The key guards regtest coins
    only; it is never written to disk and never leaves the
    process. Address derivation reuses the lab's own
    wallet_gen primitives (hash160, bech32)."""

    def __init__(self):
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric import ec
        from mining.wallet_gen import bech32_encode, hash160
        self._ec = ec
        self._key = ec.generate_private_key(ec.SECP256K1())
        pub = self._key.public_key().public_bytes(
            serialization.Encoding.X962,
            serialization.PublicFormat.CompressedPoint)
        self.pubkey = pub
        self.h160 = hash160(pub)
        self.address = bech32_encode("bcrt", 0, self.h160)
        self.script_pubkey = b"\x00\x14" + self.h160
        self.script_code = b"\x76\xa9\x14" + self.h160 + b"\x88\xac"

    def sign_digest(self, digest32):
        """ECDSA over a 32-byte digest, low-S normalised,
        DER encoded with the SIGHASH_ALL byte appended."""
        from cryptography.hazmat.primitives.asymmetric import (
            ec as _ec, utils)
        from cryptography.hazmat.primitives import hashes
        der = self._key.sign(
            digest32,
            _ec.ECDSA(utils.Prehashed(hashes.SHA256())))
        r, s = utils.decode_dss_signature(der)
        if s > _SECP256K1_N // 2:
            s = _SECP256K1_N - s
        return utils.encode_dss_signature(r, s) + b"\x01"


def _ser_outpoint(txid_display, vout):
    return bytes.fromhex(txid_display)[::-1] + \
        vout.to_bytes(4, "little")


def _ser_output(sats, script_pubkey):
    return sats.to_bytes(8, "little") + bytes([len(script_pubkey)]) \
        + script_pubkey


def _varint(n):
    if n < 0xfd:
        return bytes([n])
    if n <= 0xffff:
        return b"\xfd" + n.to_bytes(2, "little")
    return b"\xfe" + n.to_bytes(4, "little")


def build_signed_tx(key, inputs, outputs):
    """Build and sign a P2WPKH transaction fully offline.
    inputs: [(txid_display, vout, sats)] all paying key.
    outputs: [(sats, script_pubkey)]. Returns (raw_bytes,
    txid_display). BIP143 sighash, SIGHASH_ALL, sequence
    0xffffffff, locktime 0, version 2."""
    from mining.pow import dsha256
    version = (2).to_bytes(4, "little")
    locktime = (0).to_bytes(4, "little")
    seq = (0xffffffff).to_bytes(4, "little")
    prevouts = b"".join(_ser_outpoint(t, v) for t, v, _s in inputs)
    hash_prevouts = dsha256(prevouts)
    hash_sequence = dsha256(seq * len(inputs))
    outs_ser = b"".join(_ser_output(s, spk) for s, spk in outputs)
    hash_outputs = dsha256(outs_ser)
    witnesses = []
    for txid_in, vout_in, sats_in in inputs:
        preimage = (
            version + hash_prevouts + hash_sequence
            + _ser_outpoint(txid_in, vout_in)
            + bytes([len(key.script_code)]) + key.script_code
            + sats_in.to_bytes(8, "little")
            + seq + hash_outputs + locktime
            + (1).to_bytes(4, "little"))
        sig = key.sign_digest(dsha256(preimage))
        witnesses.append(b"\x02" + bytes([len(sig)]) + sig
                         + bytes([len(key.pubkey)]) + key.pubkey)
    stripped = (version + _varint(len(inputs))
                + b"".join(_ser_outpoint(t, v) + b"\x00" + seq
                           for t, v, _s in inputs)
                + _varint(len(outputs)) + outs_ser + locktime)
    full = (version + b"\x00\x01" + _varint(len(inputs))
            + b"".join(_ser_outpoint(t, v) + b"\x00" + seq
                       for t, v, _s in inputs)
            + _varint(len(outputs)) + outs_ser
            + b"".join(witnesses) + locktime)
    txid = dsha256(stripped)[::-1].hex()
    return full, txid


class MempoolLoader:
    """Loads the regtest mempool with N simple one-input
    one-output transactions spending confirmed UTXOs only.
    All transactions pay one offline key (see OfflineKey):
    the lab wallet funds that key's address with a single
    sendtoaddress, a split transaction creates N confirmed
    UTXOs, and each reload spends the previous generation's
    outputs with transactions constructed and signed in
    this process and broadcast in chunks (submitpackage,
    falling back to batched sendrawtransaction). Node RPC
    per reload is broadcast only. All of this is scenario
    setup and is never inside a timed run."""

    FEE_SATS = 2000
    SPLIT_FEE_SATS = 100_000
    PACKAGE_CHUNK = 25      # Core's default max package count

    def __init__(self, funder_rpc, plain_rpc, n_tx=500,
                 seed_sats=2_000_000):
        self.funder = funder_rpc        # lab wallet (bal-regtest)
        self.plain = plain_rpc
        self.key = OfflineKey()
        self.n = n_tx
        self.seed_sats = seed_sats
        self.pool = []          # [(txid, vout, sats)]
        self.fund_seconds = None
        self.reload_seconds = []

    def _confirm_one(self):
        self.plain.call("generatetoaddress", 1, self.key.address)

    def fund(self):
        t0 = time.perf_counter()
        need = self.n * self.seed_sats + self.SPLIT_FEE_SATS
        send_sats = need + 1_000_000
        fund_txid = self.funder.call(
            "sendtoaddress", self.key.address, send_sats / 1e8)
        self._confirm_one()
        tx = self.plain.call("getrawtransaction", fund_txid, True)
        vout, amount = None, None
        for i, o in enumerate(tx["vout"]):
            if self.key.address in o.get("scriptPubKey", {}).get(
                    "address", "") or o["scriptPubKey"]["hex"] == \
                    self.key.script_pubkey.hex():
                vout, amount = i, int(round(o["value"] * 1e8))
                break
        if vout is None:
            raise RuntimeError("funding output to loader key not found")
        change = amount - self.n * self.seed_sats - self.SPLIT_FEE_SATS
        outputs = [(self.seed_sats, self.key.script_pubkey)
                   for _ in range(self.n)]
        outputs.append((change, self.key.script_pubkey))
        raw, split_txid = build_signed_tx(
            self.key, [(fund_txid, vout, amount)], outputs)
        self.plain.call("sendrawtransaction", raw.hex())
        self._confirm_one()
        self.pool = [(split_txid, i, self.seed_sats)
                     for i in range(self.n)]
        self.fund_seconds = time.perf_counter() - t0
        return split_txid

    def _broadcast(self, hexes):
        """Broadcast independent transactions in package
        chunks; fall back to batched sendrawtransaction for
        any chunk the package route refuses."""
        for i in range(0, len(hexes), self.PACKAGE_CHUNK):
            chunk = hexes[i:i + self.PACKAGE_CHUNK]
            try:
                res = self.plain.call("submitpackage", chunk)
                if res.get("package_msg") != "success":
                    raise RuntimeError(f"package_msg={res}")
            except Exception:
                batch_call(self.plain, [
                    ("sendrawtransaction", (h,)) for h in chunk])

    def reload(self):
        if not self.pool:
            self.fund()
        assert len(self.pool) >= self.n
        t0 = time.perf_counter()
        hexes, new_pool = [], []
        for txid_in, vout_in, sats in self.pool[:self.n]:
            out_sats = sats - self.FEE_SATS
            raw, new_txid = build_signed_tx(
                self.key, [(txid_in, vout_in, sats)],
                [(out_sats, self.key.script_pubkey)])
            hexes.append(raw.hex())
            new_pool.append((new_txid, 0, out_sats))
        self._broadcast(hexes)
        self.pool = new_pool
        secs = time.perf_counter() - t0
        self.reload_seconds.append(secs)
        return secs


# ---------------------------------------------------------------- manifest

def build_manifest(backend):
    model = ""
    flags = []
    try:
        with open("/proc/cpuinfo") as fh:
            text = fh.read()
        for line in text.splitlines():
            if line.startswith("model name") and not model:
                model = line.split(":", 1)[1].strip()
            if line.startswith("flags") and not flags:
                flags = line.split(":", 1)[1].split()
    except OSError:
        pass
    keep = [f for f in ("avx2", "avx512f", "avx512bw", "avx512vl",
                        "avx512vbmi", "avx512vbmi2", "sha_ni", "sse4_1",
                        "ssse3") if f in flags]
    hashes = {}
    for rel in CONTENT_FILES + ("research/sha256d/exp040/category_f.py",):
        path = os.path.join(ROOT, rel)
        with open(path, "rb") as fh:
            hashes[rel] = hashlib.sha256(fh.read()).hexdigest()
    return {
        "host_cpu": model,
        "hostname": platform.node(),
        "cpu_flags_relevant": keep,
        "python": platform.python_version(),
        "backend_selected": backend,
        "dispatch_order": ["cuda", "v512dual", "v512", "shani",
                           "avx2", "c", "hashlib"],
        "batch_size": BATCH_SIZE,
        "extranonce_space": list(EXTRANONCE_SPACE),
        "loadavg_at_manifest": list(os.getloadavg()),
        "contention": ("live mainnet pool miner (v512dual) and "
                       "pruned mainnet node running throughout; "
                       "figures are contended single-VM regtest "
                       "pipeline figures, category F"),
        "source_sha256": hashes,
    }


# ---------------------------------------------------------------- sessions

def wallet_rpc():
    rpc = BitcoinRPC()
    if "bal-regtest" not in rpc.call("listwallets"):
        try:
            rpc.call("loadwallet", "bal-regtest")
        except Exception:
            rpc.call("createwallet", "bal-regtest")
    return BitcoinRPC(wallet="bal-regtest")


def verify_block(plain_rpc, block_hash):
    """EXP-036 exact verification of the accepted block's
    header. Returns (seconds, ok, classification)."""
    raw = plain_rpc.call("getblock", block_hash, 0)
    header = bytes.fromhex(raw)[:80]
    t0 = time.perf_counter()
    v = verify_candidate(header, POW_LIMIT_REGTEST)
    secs = time.perf_counter() - t0
    ok = (v["classification"] == "block_candidate"
          and v["meets_network_target"]
          and v["digest"][::-1].hex() == block_hash)
    return secs, ok, v["classification"]


def run_session(scenario, session_index, n_runs, loader=None,
                runs_out=None):
    plain = BitcoinRPC()
    wallet = wallet_rpc()
    payout = wallet.call("getnewaddress", "", "bech32")
    timer = SegmentTimer()
    trpc = TimingRPC(BitcoinRPC(), timer)
    real_compute = ComputeEngine()
    shift = AMPLIFY_SHIFT if scenario == "C" else 0
    tcompute = TimingCompute(real_compute, timer, target_shift=shift)
    engine = MiningEngine(trpc, payout, compute=tcompute,
                          batch_size=BATCH_SIZE,
                          extranonce_space=EXTRANONCE_SPACE)
    instrument_engine(engine, timer)
    cycle_kwargs = {}
    if scenario == "C":
        cycle_kwargs = {"max_batches": 100000, "deadline_seconds": 900}

    session = {
        "experiment": "EXP-040",
        "category": "F",
        "scenario": scenario,
        "session_index": session_index,
        "started_utc": datetime.now(timezone.utc).isoformat(),
        "manifest": build_manifest(real_compute.backend),
        "target_shift": shift,
        "n_runs_declared": n_runs,
        "setup": {},
        "warmup": None,
        "runs": [],
    }

    def setup_mempool():
        if scenario == "B":
            secs = loader.reload()
            size = plain.call("getmempoolinfo")["size"]
            assert size == loader.n, (size, loader.n)
            return {"reload_seconds": secs, "mempool_size": size}
        size = plain.call("getmempoolinfo")["size"]
        assert size == 0, f"expected empty mempool, got {size}"
        return {"mempool_size": 0}

    # Warm-up cycle (untimed; pays TemplateFamily construction
    # and backend warm-up). Must end accepted.
    session["setup"]["warmup_mempool"] = setup_mempool()
    warm = engine.mine_cycle(**cycle_kwargs)
    session["warmup"] = {"accepted": bool(warm.get("accepted")),
                         "height": warm.get("height"),
                         "hash": warm.get("hash"),
                         "hashes": warm.get("hashes")}
    if not warm.get("accepted"):
        raise RuntimeError(f"warm-up cycle not accepted: {warm}")

    for i in range(n_runs):
        setup_info = setup_mempool()
        timer.reset()
        t0 = time.perf_counter()
        result = engine.mine_cycle(**cycle_kwargs)
        wall = time.perf_counter() - t0
        totals, calls, covered = timer.stage_totals()
        run = {
            "run_index": i,
            "setup": setup_info,
            "accepted": bool(result.get("accepted")),
            "height": result.get("height"),
            "hash": result.get("hash"),
            "nonce": result.get("nonce"),
            "hashes_counted": result.get("hashes"),
            "batches": result.get("batches"),
            "tx_count": result.get("tx_count"),
            "fees_sats": result.get("fees"),
            "cycle_wall_s": wall,
            "stages_s": {k: round(v, 6) for k, v in
                         sorted(totals.items())},
            "stage_calls": calls,
            "residual_s": wall - covered,
            "failed": False,
        }
        if not result.get("accepted"):
            run["failed"] = True
            run["fail_reason"] = result.get("reason")
        else:
            v_secs, v_ok, v_class = verify_block(plain, result["hash"])
            run["verify"] = {"seconds": v_secs, "ok": v_ok,
                             "classification": v_class}
            if not v_ok:
                run["failed"] = True
                run["fail_reason"] = "EXP-036 verification gate failed"
        session["runs"].append(run)
        if runs_out is not None:
            runs_out.append(run)
        print(f"  [{scenario} s{session_index} run {i}] "
              f"accepted={run['accepted']} height={run['height']} "
              f"wall={wall:.4f}s hashes={run['hashes_counted']} "
              f"failed={run['failed']}", flush=True)

    session["finished_utc"] = datetime.now(timezone.utc).isoformat()
    if loader is not None:
        session["setup"]["loader"] = {
            "fund_seconds": loader.fund_seconds,
            "reload_seconds": loader.reload_seconds,
            "n_tx": loader.n,
        }
    os.makedirs(RAW_DIR, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = os.path.join(
        RAW_DIR, f"session_{scenario}_{session_index}_{stamp}.json")
    with open(path, "x") as fh:
        json.dump(session, fh, indent=1)
    print(f"  session file: {path}", flush=True)
    return session


def main(argv=None):
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    ra = sub.add_parser("run-all")
    ra.add_argument("--sessions", type=int, default=3)
    ra.add_argument("--runs-ab", type=int, default=8)
    ra.add_argument("--runs-c", type=int, default=5)
    ra.add_argument("--n-tx", type=int, default=500)
    r1 = sub.add_parser("run")
    r1.add_argument("--scenario", required=True, choices="ABC")
    r1.add_argument("--sessions", type=int, default=1)
    r1.add_argument("--runs", type=int, default=2)
    r1.add_argument("--n-tx", type=int, default=500)
    args = ap.parse_args(argv)

    if args.cmd == "run-all":
        plan = [("A", args.runs_ab), ("C", args.runs_c),
                ("B", args.runs_ab)]
        sessions_n = args.sessions
        n_tx = args.n_tx
    else:
        plan = [(args.scenario,
                 args.runs if args.scenario != "C" else args.runs)]
        sessions_n = args.sessions
        n_tx = args.n_tx

    loader = None
    if any(s == "B" for s, _ in plan):
        loader = MempoolLoader(wallet_rpc(), BitcoinRPC(), n_tx=n_tx)
    for scenario, n_runs in plan:
        for s in range(sessions_n):
            print(f"EXP-040 scenario {scenario} session {s}: "
                  f"{n_runs} timed runs", flush=True)
            run_session(scenario, s, n_runs, loader=loader)
    return 0


if __name__ == "__main__":
    sys.exit(main())
