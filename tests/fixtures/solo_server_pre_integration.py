"""Pre-integration solo server, kept as the Gate 2 differential
fixture for tests/test_solo_vardiff.py.

This is mining/solo_server.py exactly as it stood at remote
HEAD 3ebbaeb216bc1260cfca22c63b9af60d780a971e, before the
Stage 6 vardiff integration (fetched via the contents API;
sha256 of the original file
518ef05c5c7d49fdf6408e68494fecde24a1c55b337c59576696f77a2a37ab44).
It is loaded by file path under its own module name and is
never imported by production code. Do not edit it to match
the current server: its whole value is that it differs."""

"""Solo mining server: our own Stratum V1 pool of one.

The full solo stack, ours end to end: Bitcoin Core supplies
getblocktemplate; this server turns templates into Stratum jobs,
validates shares, and when a share meets the NETWORK target it
assembles the complete block and submits it via submitblock.
No third-party pool anywhere.

Candidate handling follows the EXP-036 pipeline: any share
that meets the share target or claims the network target is
re-verified exactly in mining/candidate_verify.py (independent
pure-Python SHA-256d plus the strict check_pow target rules)
before anything is submitted, and a submitted block counts as
accepted only when the node's own chain state confirms it
(best block hash, or the block in the active chain). A bare
submitblock None no longer counts as success on its own.

Conventions match Stratum V1 as implemented by the lab's client
(mining/stratum_client.py), whose header builder is reused by the
test worker so client and server can disagree loudly in tests if
either side drifts.

Job model: the coinbase scriptSig carries an 8-byte extranonce
slot (extranonce1 = per-connection, extranonce2 = per-share).
The server keeps the full template, so on a block candidate it
rebuilds the exact block (coinbase with the submitted extranonce,
the template's transactions verbatim) and submits it.

Mainnet hardening (2026-11-14, see docs/SOLO_CUTOVER.md): the
server refuses to serve work when the node is on the wrong
chain or still in initial block download (SoloNotReady), tracks
shares per worker, survives submitblock RPC failures without
losing the candidate record, and a JobRefresher thread keeps
the current job on the node's tip so workers never mine a
stale prevhash after a new block arrives.
"""

import json
import socket
import socketserver
import struct
import threading
import time

from mining.candidate_verify import (classify_submit_result,
                                       pow_limit_for_chain,
                                       verify_candidate,
                                       verify_chain_acceptance)
from mining.pow import dsha256 as double_sha256
from mining.pow import merkle_root, target_from_nbits
from mining.pow_engine import POW_LIMIT_MAINNET


class SoloNotReady(Exception):
    """The node cannot supply trustworthy work right now (wrong
    chain, initial block download, or state unavailable). The
    server refuses to serve rather than hand out stale jobs."""


class ChainMismatch(SoloNotReady):
    """The node is on a different chain than the server was
    configured for. Refusing is deliberate: a mainnet server
    fed by a regtest node (or the reverse) would build blocks
    for the wrong network while looking perfectly healthy."""


def attach_witness(stripped_coinbase):
    """Re-attach the coinbase witness to a stripped coinbase:
    marker and flag after the version, and one witness stack
    item holding the 32-byte reserved value (all zero, exactly
    as mining.engine.build_coinbase emits it) before the
    locktime. Inverse of mining.engine.strip_witness for the
    coinbases this server builds."""
    return (stripped_coinbase[:4] + b"\x00\x01"
            + stripped_coinbase[4:-4]
            + b"\x01\x20" + bytes(32) + stripped_coinbase[-4:])


def _varint(n):
    if n < 0xfd:
        return bytes([n])
    if n <= 0xffff:
        return b"\xfd" + struct.pack("<H", n)
    return b"\xfe" + struct.pack("<I", n)


def merkle_branch(txids):
    """Stratum merkle branch for the coinbase at index 0. The full
    layer includes the coinbase as element 0 (a dummy stands in for
    it: the branch only ever reads siblings of the coinbase path,
    and the one parent that would depend on the coinbase value is
    never a sibling on that path)."""
    branch = []
    layer = [bytes(32)] + list(txids)
    idx = 0
    while len(layer) > 1:
        sib = idx ^ 1
        branch.append(layer[sib] if sib < len(layer) else layer[idx])
        layer = [double_sha256(
            layer[i] + (layer[i + 1] if i + 1 < len(layer) else layer[i]))
            for i in range(0, len(layer), 2)]
        idx //= 2
    return branch


class SoloServer:
    def __init__(self, rpc, payout_address, share_difficulty=0.01,
                 tag=b"/BAL-solo/", expected_chain=None,
                 allow_ibd=False, pow_limit=None):
        self.rpc = rpc
        self.payout = payout_address
        self.share_difficulty = share_difficulty
        self.expected_chain = expected_chain
        self.allow_ibd = allow_ibd
        # Explicit proof-of-work limit for exact verification;
        # when None it is derived from the expected or reported
        # chain (see _pow_limit).
        self.pow_limit = pow_limit
        # Stratum difficulty 1 target: 0x00000000FFFF followed by
        # 26 zero bytes; share target = DIFF1 / difficulty.
        diff1 = int("00000000ffff" + "00" * 26, 16)
        self.share_target = (int(diff1 / share_difficulty)
                             if share_difficulty else 0)
        self.tag = tag
        self.jobs = {}
        self.job_seq = 0
        self.lock = threading.Lock()
        self.blocks_found = []
        # Candidates that met a target on the fast compare but
        # failed exact verification (EXP-036): recorded, never
        # submitted.
        self.candidates_rejected = []
        self.shares_accepted = 0
        self.shares_rejected = 0
        self.workers = {}
        self.current = None
        self._stop = False

    # -- node gating --------------------------------------------------------
    def node_info(self):
        """getblockchaininfo, or None when the node cannot be
        reached or does not answer coherently."""
        try:
            info = self.rpc.call("getblockchaininfo")
        except Exception:
            return None
        return info if isinstance(info, dict) else None

    def check_node(self):
        """Return getblockchaininfo when the node may supply
        work; raise SoloNotReady (or ChainMismatch) otherwise.
        Serving a template from a syncing node means miners
        grind a prevhash the network has long moved past, and a
        winning hash would be stillborn, so the refusal is the
        feature, not an error path."""
        info = self.node_info()
        if info is None:
            raise SoloNotReady(
                "node state unavailable: getblockchaininfo failed; "
                "refusing to serve work")
        chain = info.get("chain")
        if self.expected_chain and chain != self.expected_chain:
            raise ChainMismatch(
                f"node is on chain {chain!r} but this server is "
                f"configured for {self.expected_chain!r}; refusing "
                f"to serve work")
        if info.get("initialblockdownload") and not self.allow_ibd:
            raise SoloNotReady(
                f"node in initial block download (blocks "
                f"{info.get('blocks')} of headers "
                f"{info.get('headers')}); refusing to serve work")
        return info

    def _pow_limit(self):
        """The proof-of-work limit exact verification judges
        against: the explicit constructor value when given,
        else the expected chain's limit, else the limit of the
        chain the node reports, else mainnet's (the strictest,
        so an unreadable chain never widens the target)."""
        if self.pow_limit is not None:
            return self.pow_limit
        if self.expected_chain:
            return pow_limit_for_chain(self.expected_chain)
        info = self.node_info()
        if info:
            return pow_limit_for_chain(info.get("chain"))
        return POW_LIMIT_MAINNET

    # -- worker accounting ----------------------------------------------------
    def _worker_rec(self, worker):
        """Per-worker counters, created on first sight. Caller
        holds self.lock."""
        rec = self.workers.get(worker)
        if rec is None:
            rec = {"accepted": 0, "rejected": 0, "blocks": 0,
                   "block_candidates": 0, "connected_at": time.time(),
                   "last_share_at": None, "last_submit_at": None}
            self.workers[worker] = rec
        return rec

    def note_authorize(self, worker):
        with self.lock:
            self._worker_rec(worker or "unknown")

    def stats(self):
        """Snapshot for status reporting (the mainnet runner
        writes this to .local/solo-status.json)."""
        with self.lock:
            cur = self.current
            return {
                "share_difficulty": self.share_difficulty,
                "payout": self.payout,
                "shares_accepted": self.shares_accepted,
                "shares_rejected": self.shares_rejected,
                "blocks_found": len(self.blocks_found),
                "blocks": list(self.blocks_found),
                "candidates_rejected": list(self.candidates_rejected),
                "workers": {k: dict(v)
                            for k, v in self.workers.items()},
                "current_job": None if cur is None else {
                    "job_id": cur["job_id"],
                    "height": cur["template"]["height"],
                    "prevhash": cur["template"]["previousblockhash"],
                },
            }

    # -- job construction -------------------------------------------------
    def refresh_job(self):
        self.check_node()
        from mining.engine import (address_script_pubkey, build_coinbase)
        t = self.rpc.call("getblocktemplate", {"rules": ["segwit"]})
        # Build the coinbase with the lab engine's own builder, with
        # an 8-byte placeholder where the extranonce pair will land.
        # The engine builder handles BIP34, the payout output, and
        # the segwit witness commitment exactly as direct mining does.
        placeholder = b"\xee" * 8
        script = address_script_pubkey(self.rpc, self.payout)
        commitment = None
        if t.get("default_witness_commitment"):
            # Core returns the full commitment scriptPubKey:
            # OP_RETURN, push 36, the aa21a9ed header, then the
            # 32-byte commitment hash. Anything else is not the
            # field this code was written against; fail loudly
            # instead of slicing blind.
            raw_commit = bytes.fromhex(t["default_witness_commitment"])
            if (len(raw_commit) != 38
                    or raw_commit[:6] != b"\x6a\x24\xaa\x21\xa9\xed"):
                raise ValueError(
                    "unexpected default_witness_commitment format: "
                    f"{len(raw_commit)} bytes")
            commitment = raw_commit[6:]
        coinbase, _ = build_coinbase(
            t["height"], t["coinbasevalue"], script, placeholder,
            witness_commitment=commitment)
        marker = b"/BAL/" + placeholder
        # Serve the STRIPPED coinbase over Stratum: the worker hashes
        # what it assembles, and that hash must be the coinbase txid
        # (which excludes witness data). The server re-attaches the
        # witness (the fixed 32-byte reserved value) when it
        # assembles a winning block, which is exactly the form the
        # template's witness commitment was computed over.
        # The split offset MUST be located in the stripped bytes:
        # the full coinbase carries the 2-byte segwit marker and
        # flag ahead of the input, so an offset taken from it
        # lands 2 bytes late in the stripped form, leaving
        # placeholder bytes in coinb1 and eating the first 2
        # bytes after the extranonce slot (EXP-034 finding).
        from mining.engine import strip_witness
        stripped, has_witness = strip_witness(coinbase)
        at = stripped.index(marker) + len(b"/BAL/")
        coinb1 = stripped[:at]
        coinb2 = stripped[at + 8:]
        txids = [bytes.fromhex(tx["txid"])[::-1] for tx in t["transactions"]]
        branch = merkle_branch(txids)
        with self.lock:
            self.job_seq += 1
            job = {
                "job_id": f"{self.job_seq:x}",
                "template": t,
                "has_witness": bool(has_witness),
                "coinb1": coinb1, "coinb2": coinb2,
                "branch": branch,
                "txids": txids,
                "target": target_from_nbits(int(t["bits"], 16)),
            }
            self.jobs = {job["job_id"]: job}
            self.current = job
        return job

    def notify_params(self, job):
        t = job["template"]
        prev = bytes.fromhex(t["previousblockhash"])[::-1]
        prev_swapped = b"".join(prev[i:i + 4][::-1]
                                for i in range(0, 32, 4))
        return [job["job_id"], prev_swapped.hex(),
                job["coinb1"].hex(), job["coinb2"].hex(),
                [b.hex() for b in job["branch"]],
                f'{t["version"]:08x}', t["bits"],
                f'{t["curtime"]:08x}', True]

    # -- share validation ---------------------------------------------------
    def validate_share(self, job, extranonce1, extranonce2_hex, ntime_hex,
                       nonce_hex):
        en2 = bytes.fromhex(extranonce2_hex)
        if len(en2) != 4:
            return None, "bad extranonce2 size"
        # A share whose ntime the network would reject must not
        # be counted, and must never reach block assembly.
        try:
            ntime = int(ntime_hex, 16)
        except ValueError:
            return None, "bad ntime"
        mintime = job["template"].get("mintime")
        if mintime and ntime < mintime:
            return None, "ntime before template mintime"
        if ntime > int(time.time()) + 7200:
            return None, "ntime too far in the future"
        coinbase = job["coinb1"] + extranonce1 + en2 + job["coinb2"]
        cb_txid = double_sha256(coinbase)  # served stripped: this is the txid
        # Full root via stored txids (server has the whole template).
        root = merkle_root([cb_txid] + job["txids"])
        t = job["template"]
        header = (
            struct.pack("<i", t["version"])
            + bytes.fromhex(t["previousblockhash"])[::-1]
            + root
            + struct.pack("<I", int(ntime_hex, 16))
            + struct.pack("<I", int(t["bits"], 16))
            + struct.pack("<I", int(nonce_hex, 16)))
        digest = double_sha256(header)
        value = int.from_bytes(digest, "little")
        return ({"header": header, "digest": digest, "value": value,
                 "coinbase": coinbase}, None)

    def _count(self, worker, accepted, block=False, candidate=False):
        with self.lock:
            rec = self._worker_rec(worker or "unknown")
            rec["last_submit_at"] = time.time()
            if accepted:
                self.shares_accepted += 1
                rec["accepted"] += 1
                rec["last_share_at"] = time.time()
            else:
                self.shares_rejected += 1
                rec["rejected"] += 1
            if candidate:
                rec["block_candidates"] += 1
            if block:
                rec["blocks"] += 1

    def submit_share(self, job_id, extranonce1, en2, ntime, nonce,
                     worker=None):
        with self.lock:
            job = self.jobs.get(job_id)
        if not job:
            self._count(worker, False)
            return {"accepted": False, "reason": "unknown job"}
        res, err = self.validate_share(job, extranonce1, en2, ntime, nonce)
        if err:
            self._count(worker, False)
            return {"accepted": False, "reason": err}
        # Fast integer compare first: a submission meeting
        # neither target is rejected here, exactly as before,
        # and costs no verification work.
        if not (res["value"] <= job["target"]
                or res["value"] <= self.share_target):
            self._count(worker, False)
            return {"accepted": False, "reason": "low difficulty share"}
        # EXP-036 exact verification gate. Only candidate hits
        # reach this point, so the independent pure-Python
        # verification never touches the search path. A
        # candidate that fails here is rejected and is NEVER
        # submitted, whatever the fast compare said.
        v = verify_candidate(res["header"], self._pow_limit(),
                             share_target=self.share_target)
        if v["target"] != job["target"]:
            # The reconstructed header's nBits decodes to a
            # different target than the job it claims to belong
            # to: the candidate cannot be trusted.
            v = dict(v, classification="invalid",
                     reason="header-target-mismatch")
        if v["classification"] == "invalid":
            rec = {"height": job["template"]["height"],
                   "hash": res["digest"][::-1].hex(),
                   "reason": v["reason"], "worker": worker}
            with self.lock:
                self.candidates_rejected.append(rec)
            self._count(worker, False, candidate=True)
            return {"accepted": False,
                    "reason": f"exact verification failed: {v['reason']}"}
        is_block = v["meets_network_target"]
        is_share = v["meets_share_target"]
        if is_block:
            t = job["template"]
            txs = b"".join(bytes.fromhex(tx["data"])
                           for tx in t["transactions"])
            coinbase = res["coinbase"]
            if job.get("has_witness"):
                coinbase = attach_witness(coinbase)
            block = (res["header"] + _varint(1 + len(t["transactions"]))
                     + coinbase + txs)
            block_hash = res["digest"][::-1].hex()
            # submitblock returns None when the node accepts the
            # block for processing and a reason string otherwise;
            # a transport or RPC failure must not kill the
            # connection handler or lose the record of a
            # network-target candidate, so it is captured here
            # and reported as a failed submission.
            rpc_error = None
            try:
                r = self.rpc.call("submitblock", block.hex())
            except Exception as exc:
                rpc_error = exc
                r = f"submitblock RPC failed: {exc}"
            classification = ("rpc-error" if rpc_error is not None
                              else classify_submit_result(r))
            # Pipeline step 12: the response is a claim, chain
            # state is the fact. The block counts as accepted
            # only when the node holds it in its active chain,
            # the standard mining.engine.mine_cycle applies.
            if rpc_error is None:
                chain_status, chain_ok = verify_chain_acceptance(
                    self.rpc, block_hash)
            else:
                chain_status, chain_ok = "unknown", False
            ok = bool(chain_ok and classification
                      in ("accepted", "duplicate"))
            if not ok:
                print(f"solo-server: BLOCK NOT ACCEPTED at height "
                      f"{t['height']}: submitblock said {r!r} "
                      f"({classification}), chain state "
                      f"{chain_status}", flush=True)
            rec = {"height": t["height"], "hash": block_hash,
                   "submit_result": r,
                   "submit_classification": classification,
                   "chain_status": chain_status,
                   "chain_verified": chain_ok,
                   "verify_reason": v["reason"],
                   "accepted": ok}
            with self.lock:
                self.blocks_found.append(rec)
            self._count(worker, True, block=ok, candidate=True)
            return {"accepted": True, "block": rec}
        if is_share:
            self._count(worker, True)
            return {"accepted": True, "block": None}
        self._count(worker, False)
        return {"accepted": False, "reason": "low difficulty share"}


class JobRefresher(threading.Thread):
    """Keeps the served job on the node's tip.

    Without this, the job built at subscribe time is served
    until a block is found through it: on mainnet the tip moves
    every ten minutes on average and every share on the old
    prevhash is wasted. The refresher polls the node, and when
    the tip has moved (or the job has aged past max_age_s, so
    mempool changes and curtime advance reach workers), it
    builds a fresh job and hands it to the broadcast callback.
    While the node cannot supply work (initial block download,
    wrong chain, unreachable) it logs the state change once and
    waits; refresh_job re-checks the gate itself, so no path
    can serve a template the gate would refuse."""

    def __init__(self, solo, broadcast, poll_s=2.0, max_age_s=120.0,
                 log=print):
        super().__init__(daemon=True, name="solo-job-refresher")
        self.solo = solo
        self.broadcast = broadcast
        self.poll_s = poll_s
        self.max_age_s = max_age_s
        self.log = log
        self._stop_evt = threading.Event()
        self._job_born = 0.0
        self._ready = None
        self._reason = None

    def stop(self):
        self._stop_evt.set()

    def _note_state(self, ready, reason=None):
        if ready != self._ready or reason != self._reason:
            self._ready, self._reason = ready, reason
            if ready:
                self.log("solo-server: node ready; serving work")
            else:
                self.log(f"solo-server: refusing to serve work: "
                         f"{reason}")

    def run(self):
        while not self._stop_evt.is_set():
            try:
                info = self.solo.check_node()
            except SoloNotReady as exc:
                self._note_state(False, str(exc))
                self._stop_evt.wait(self.poll_s)
                continue
            self._note_state(True)
            cur = self.solo.current
            tip = info.get("bestblockhash")
            stale = (
                cur is None
                or cur["template"].get("previousblockhash") != tip
                or time.time() - self._job_born > self.max_age_s)
            if stale:
                try:
                    job = self.solo.refresh_job()
                except Exception as exc:
                    self.log(f"solo-server: job refresh failed: "
                             f"{exc}")
                else:
                    self._job_born = time.time()
                    self.broadcast(job)
            self._stop_evt.wait(self.poll_s)


class _Handler(socketserver.StreamRequestHandler):
    def setup(self):
        super().setup()
        try:  # signals travel immediately: no Nagle delay on jobs
            self.request.setsockopt(
                socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        except OSError:
            pass

    def handle(self):
        srv: SoloServer = self.server.solo
        extranonce1 = self.server.next_en1()
        with self.server.clients_lock:
            self.server.clients.add(self)
        try:
            self._run(srv, extranonce1)
        finally:
            with self.server.clients_lock:
                self.server.clients.discard(self)

    def _run(self, srv, extranonce1):
        worker_name = "unknown"
        for raw in self.rfile:
            try:
                msg = json.loads(raw.decode())
            except Exception:
                continue
            method = msg.get("method")
            mid = msg.get("id")
            if method == "mining.subscribe":
                self._send({"id": mid, "result": [
                    [["mining.set_difficulty", "bal1"],
                     ["mining.notify", "bal2"]],
                    extranonce1.hex(), 4], "error": None})
                self._send({"id": None, "method": "mining.set_difficulty",
                            "params": [srv.share_difficulty]})
                try:
                    job = srv.current or srv.refresh_job()
                except SoloNotReady as exc:
                    # Refuse the session, loudly, rather than
                    # serve a template the node cannot back. The
                    # lab client reconnects on a dropped session,
                    # so it returns on its own once work is real.
                    print(f"solo-server: subscribe refused: {exc}",
                          flush=True)
                    return
                self._send({"id": None, "method": "mining.notify",
                            "params": srv.notify_params(job)})
            elif method == "mining.authorize":
                if msg.get("params"):
                    worker_name = str(msg["params"][0])
                srv.note_authorize(worker_name)
                self._send({"id": mid, "result": True, "error": None})
            elif method == "mining.suggest_difficulty":
                # Our own client sends this. The server sets the
                # difficulty; the suggestion is acknowledged and
                # otherwise ignored.
                self._send({"id": mid, "result": True, "error": None})
            elif method == "mining.submit":
                worker, job_id, en2, ntime, nonce = msg["params"]
                out = srv.submit_share(job_id, extranonce1, en2, ntime,
                                       nonce, worker=str(worker))
                self._send({"id": mid, "result": out["accepted"],
                            "error": None if out["accepted"]
                            else [20, out["reason"], None]})
                if out.get("block"):
                    try:
                        job = srv.refresh_job()
                    except SoloNotReady as exc:
                        print(f"solo-server: post-block refresh "
                              f"refused: {exc}", flush=True)
                    else:
                        self._broadcast(job)
            else:
                self._send({"id": mid, "result": None,
                            "error": [501, "unknown method", None]})

    def _send(self, obj):
        self.wfile.write((json.dumps(obj) + "\n").encode())
        self.wfile.flush()

    def _broadcast(self, job):
        self.server.broadcast(job)


class SoloTCPServer(socketserver.ThreadingTCPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, addr, solo: SoloServer, share_difficulty=None):
        self.solo = solo
        # Kept for call compatibility; the SoloServer's own
        # share_difficulty is the single source of truth that
        # handlers serve and validate against.
        self.share_difficulty = (solo.share_difficulty
                                 if share_difficulty is None
                                 else share_difficulty)
        self._en1 = 0
        self._en1_lock = threading.Lock()
        self.clients = set()
        self.clients_lock = threading.Lock()
        super().__init__(addr, _Handler)

    def next_en1(self):
        with self._en1_lock:
            self._en1 += 1
            return self._en1.to_bytes(4, "little")

    def broadcast(self, job):
        """Send a fresh job to every connected worker."""
        with self.clients_lock:
            clients = list(self.clients)
        for h in clients:
            try:
                h._send({"id": None, "method": "mining.notify",
                         "params": self.solo.notify_params(job)})
            except Exception:
                pass
