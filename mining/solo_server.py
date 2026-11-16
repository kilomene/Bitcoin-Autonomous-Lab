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

Vardiff (Stage 6 integration of the NOVA-ER-0004 prototype,
register R-12; design in research/vardiff/DESIGN.md): SoloServer
accepts an optional VarDiffController as its vardiff component.
With vardiff=None (the default) the server is the fixed-
difficulty server it has always been, bit for bit: that is the
rollback surface. With a controller, share difficulty adapts
per connection toward a target share interval, shares are
judged against the difficulty snapshot taken when their job
was issued, stale and duplicate submissions are classified
into their own accounting categories, and every adjustment is
logged. Difficulty remains a share criterion only: block
candidacy is decided solely by the EXP-036 exact test against
the network target at every difficulty.
"""

import json
import socket
import socketserver
import struct
import threading
import time

from mining import endpoint_config
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


# Stratum difficulty-1 target: 0x00000000FFFF followed by 26
# zero bytes; the share target at difficulty d is DIFF1 / d.
DIFF1 = int("00000000ffff" + "00" * 26, 16)


def share_target_for(difficulty):
    """The share target for a difficulty, int(DIFF1 / difficulty),
    integer-exact; identical to SoloServer's constructor
    computation and to stratum_client.target_for_difficulty."""
    return int(DIFF1 / difficulty)


class VarDiffController:
    """The decided vardiff control law (research/vardiff/
    DESIGN.md section 4), ported from the verified prototype.

    One instance serves every connection; per-connection state
    lives in the dicts returned by new_connection and is passed
    back on each event. The controller holds no locks and no
    clock: callers serialise events and supply time, which is
    what makes the law reproducible under a simulated clock in
    tests."""

    def __init__(self, target_interval=15.0, floor=0.002,
                 ceiling=1.0, initial=0.02, ema_alpha=0.35,
                 deadband=1.25,
                 up_hysteresis_s=30.0, up_confirmations=2,
                 max_up_factor=1.5, max_down_factor=2.0,
                 decay_after_s=60.0, decay_factor=2.0):
        if not (0 < floor <= initial <= ceiling):
            raise ValueError(
                "require 0 < floor <= initial <= ceiling")
        if target_interval <= 0:
            raise ValueError("target_interval must be positive")
        if deadband < 1:
            raise ValueError("deadband must be >= 1")
        if not (0 < ema_alpha <= 1):
            raise ValueError("ema_alpha must be in (0, 1]")
        if max_up_factor < 1 or max_down_factor < 1:
            raise ValueError("adjustment factors must be >= 1")
        if decay_factor < 1:
            raise ValueError("decay_factor must be >= 1")
        self.target_interval = float(target_interval)
        self.deadband = float(deadband)
        self.floor = float(floor)
        self.ceiling = float(ceiling)
        self.initial = float(initial)
        self.ema_alpha = float(ema_alpha)
        self.up_hysteresis_s = float(up_hysteresis_s)
        self.up_confirmations = int(up_confirmations)
        self.max_up_factor = float(max_up_factor)
        self.max_down_factor = float(max_down_factor)
        self.decay_after_s = float(decay_after_s)
        self.decay_factor = float(decay_factor)

    def new_connection(self, now):
        return {
            "difficulty": self.initial,
            "connected_at": now,
            "last_share_at": None,
            "ema_interval": None,
            "fast_votes": 0,
            "last_up_at": None,
            "shares": 0,
            "last_clamp_reason": None,
        }

    def _record(self, st, new, reason, ema, clamped):
        old = st["difficulty"]
        st["difficulty"] = new
        return {"reason": reason, "old": old, "new": new,
                "ema_interval": ema, "clamped": clamped}

    def _clamp_event(self, st, desired, reason, ema):
        """Apply a desired difficulty inside the bounds.
        Returns an adjustment record, or None when nothing
        changed (including a repeated clamp at the same bound,
        which is logged once per distinct bound state)."""
        new = min(max(desired, self.floor), self.ceiling)
        clamped = new != desired
        if new == st["difficulty"]:
            if clamped and st["last_clamp_reason"] != reason:
                st["last_clamp_reason"] = reason
                return self._record(st, new, reason, ema, True)
            return None
        st["last_clamp_reason"] = None
        return self._record(st, new, reason, ema, clamped)

    def on_accepted_share(self, st, now):
        """One accepted share from this connection. Returns an
        adjustment record or None. Decreases apply at once;
        increases carry the decided hysteresis (confirmation
        count plus a grace period since the last increase)."""
        st["shares"] += 1
        if st["last_share_at"] is None:
            st["last_share_at"] = now
            return None
        dt = max(now - st["last_share_at"], 1e-9)
        st["last_share_at"] = now
        if st["ema_interval"] is None:
            st["ema_interval"] = dt
        else:
            a = self.ema_alpha
            st["ema_interval"] = a * dt + (1 - a) * st["ema_interval"]
        ema = st["ema_interval"]
        if ema > self.target_interval * self.deadband:
            st["fast_votes"] = 0
            factor = min(ema / self.target_interval,
                         self.max_down_factor)
            return self._clamp_event(
                st, st["difficulty"] / factor,
                "interval above target: decrease", ema)
        if ema < self.target_interval / self.deadband:
            st["fast_votes"] += 1
            if st["fast_votes"] < self.up_confirmations:
                return None
            if (st["last_up_at"] is not None
                    and now - st["last_up_at"]
                    < self.up_hysteresis_s):
                return None
            factor = min(self.target_interval / ema,
                         self.max_up_factor)
            rec = self._clamp_event(
                st, st["difficulty"] * factor,
                "interval below target: increase", ema)
            if rec is not None:
                st["last_up_at"] = now
                st["fast_votes"] = 0
            return rec
        st["fast_votes"] = 0
        return None

    def on_job_change(self, st, now):
        """Idle decay, evaluated on job changes only (there is
        no timer in this design; the JobRefresher guarantees
        job changes on tip moves and at a maximum job age).
        One decay step per job change once the idle threshold
        has passed, toward the floor."""
        ref = st["last_share_at"]
        if ref is None:
            ref = st["connected_at"]
        if now - ref <= self.decay_after_s:
            return None
        if st["difficulty"] <= self.floor:
            return None
        return self._clamp_event(
            st, st["difficulty"] / self.decay_factor,
            "idle decay", st["ema_interval"])


class SoloServer:
    def __init__(self, rpc, payout_address, share_difficulty=None,
                 tag=b"/BAL-solo/", expected_chain=None,
                 allow_ibd=False, pow_limit=None, vardiff=None,
                 job_history_size=8):
        self.rpc = rpc
        self.payout = payout_address
        # Vardiff (Stage 6, DESIGN.md section 9 step 1): an
        # optional VarDiffController. None keeps the fixed-
        # difficulty behaviour this server has always had, bit
        # for bit; that is the rollback surface. A controller
        # owns the difficulty outright, so passing both is a
        # configuration error, refused here.
        if vardiff is not None and share_difficulty is not None:
            raise ValueError(
                "share_difficulty is owned by the vardiff "
                "controller: pass the controller's initial, not "
                "both")
        self.vardiff = vardiff
        if vardiff is not None:
            share_difficulty = vardiff.initial
        elif share_difficulty is None:
            # D10 closed (Stage 6, DESIGN.md section 9 step 3):
            # the endpoint config is the single source of the
            # fixed share difficulty. The divergent 0.01
            # constructor default this parameter used to carry
            # is gone; a caller who wants another value passes
            # it explicitly.
            share_difficulty = endpoint_config.SOLO_SHARE_DIFFICULTY
        self.share_difficulty = share_difficulty
        self.expected_chain = expected_chain
        self.allow_ibd = allow_ibd
        # Explicit proof-of-work limit for exact verification;
        # when None it is derived from the expected or reported
        # chain (see _pow_limit).
        self.pow_limit = pow_limit
        # Share target = DIFF1 / difficulty.
        self.share_target = (int(DIFF1 / share_difficulty)
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
        # Vardiff state (inert when self.vardiff is None):
        # superseded jobs retained for stale classification,
        # per-connection difficulty state keyed by extranonce1,
        # the append-only adjustment log, and the two disjoint
        # accounting categories the vardiff layer adds.
        self.job_history_size = int(job_history_size)
        self.job_history = []
        # en1 bytes -> {"state", "worker", "snapshots", "seen",
        #               "notified"}
        self.connections = {}
        self.adjustment_log = []
        self.shares_stale = 0
        self.shares_duplicate = 0
        self.stale_records = []

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

    # -- vardiff connection lifecycle --------------------------------
    # All of these are inert when self.vardiff is None: the
    # fixed-difficulty server has no per-connection state.

    def register_connection(self, extranonce1, now=None):
        if self.vardiff is None:
            return
        now = time.time() if now is None else now
        with self.lock:
            conn = {
                "state": self.vardiff.new_connection(now),
                "worker": None,
                "snapshots": {},
                "seen": set(),
                "notified": self.vardiff.initial,
            }
            if self.current is not None:
                conn["snapshots"][self.current["job_id"]] = \
                    self.vardiff.initial
            self.connections[bytes(extranonce1)] = conn

    def unregister_connection(self, extranonce1):
        if self.vardiff is None:
            return
        with self.lock:
            self.connections.pop(bytes(extranonce1), None)

    def connection_difficulty(self, extranonce1):
        """The difficulty this connection is currently told to
        mine at: its own adapted value under vardiff, else the
        server's fixed share difficulty."""
        if self.vardiff is None:
            return self.share_difficulty
        with self.lock:
            conn = self.connections.get(bytes(extranonce1))
        if conn is None:
            return self.share_difficulty
        return conn["state"]["difficulty"]

    def pending_notice(self, extranonce1):
        """The difficulty to push to this client, if it changed
        since the last notice; consumes the notice."""
        if self.vardiff is None:
            return None
        with self.lock:
            conn = self.connections.get(bytes(extranonce1))
            if conn is None:
                return None
            cur = conn["state"]["difficulty"]
            if cur == conn["notified"]:
                return None
            conn["notified"] = cur
            return cur

    def _log_adjustment(self, extranonce1, conn, rec, now):
        entry = {"ts": now,
                 "connection": bytes(extranonce1).hex(),
                 "worker": conn["worker"] if conn else None,
                 "reason": rec["reason"], "old": rec["old"],
                 "new": rec["new"],
                 "ema_interval": rec["ema_interval"],
                 "clamped": rec["clamped"]}
        with self.lock:
            self.adjustment_log.append(entry)
        return entry

    def _count_vd(self, worker, kind):
        """Vardiff accounting: the stale and duplicate
        categories, disjoint from accepted and rejected and
        from each other (DESIGN.md section 6)."""
        with self.lock:
            rec = self._worker_rec(worker or "unknown")
            rec["last_submit_at"] = time.time()
            rec[kind] = rec.get(kind, 0) + 1
            if kind == "stale":
                self.shares_stale += 1
            elif kind == "duplicate":
                self.shares_duplicate += 1

    def stats(self):
        """Snapshot for status reporting (the mainnet runner
        writes this to .local/solo-status.json)."""
        with self.lock:
            cur = self.current
            out = {
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
            if self.vardiff is not None:
                conns = {
                    en1.hex(): {
                        "difficulty":
                            c["state"]["difficulty"],
                        "ema_interval":
                            c["state"]["ema_interval"],
                        "shares": c["state"]["shares"],
                        "worker": c["worker"],
                    } for en1, c in self.connections.items()}
                out["vardiff"] = {
                    "enabled": True,
                    "target_interval":
                        self.vardiff.target_interval,
                    "floor": self.vardiff.floor,
                    "ceiling": self.vardiff.ceiling,
                    "initial": self.vardiff.initial,
                    "shares_stale": self.shares_stale,
                    "shares_duplicate": self.shares_duplicate,
                    "adjustments": len(self.adjustment_log),
                    "connections": conns,
                }
            else:
                out["vardiff"] = {"enabled": False,
                                  "pinned": self.share_difficulty}
            return out

    # -- job construction -------------------------------------------------
    def refresh_job(self):
        old = self.current
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
        if self.vardiff is not None:
            self._vardiff_on_refresh(old, job)
        return job

    def _vardiff_on_refresh(self, old, job):
        """Vardiff job lifecycle (DESIGN.md sections 4 and 5):
        retain the superseded job in the bounded history,
        snapshot each live connection's current difficulty
        against the new job (a share is judged against the
        difficulty in force for the job it answers), prune
        snapshots for evicted jobs, and evaluate idle decay
        for every connection."""
        now = time.time()
        with self.lock:
            if old is not None and old["job_id"] != job["job_id"]:
                self.job_history.append(old)
                del self.job_history[:-self.job_history_size]
            keep = {j["job_id"] for j in self.job_history}
            keep.add(job["job_id"])
            conns = list(self.connections.items())
        for en1, conn in conns:
            st = conn["state"]
            conn["snapshots"][job["job_id"]] = st["difficulty"]
            conn["snapshots"] = {
                k: v for k, v in conn["snapshots"].items()
                if k in keep}
            rec = self.vardiff.on_job_change(st, now)
            if rec is not None:
                self._log_adjustment(en1, conn, rec, now)

    def _find_job(self, job_id):
        """(job, stale) for a job id: current first, then the
        bounded superseded history (vardiff mode only; without
        vardiff the history is always empty)."""
        with self.lock:
            job = self.jobs.get(job_id)
            if job is not None:
                return job, False
            for j in self.job_history:
                if j["job_id"] == job_id:
                    return j, True
        return None, False

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
        if self.vardiff is None:
            return self._submit_share_fixed(
                job_id, extranonce1, en2, ntime, nonce,
                worker=worker)
        return self._submit_share_vardiff(
            job_id, extranonce1, en2, ntime, nonce, worker=worker)

    def _submit_share_fixed(self, job_id, extranonce1, en2, ntime,
                            nonce, worker=None):
        """The fixed-difficulty submit path, unchanged from
        before the vardiff integration: this is what runs
        whenever vardiff is None."""
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
            rec = self._submit_block(job, res, v, worker)
            self._count(worker, True, block=rec["accepted"],
                        candidate=True)
            return {"accepted": True, "block": rec}
        if is_share:
            self._count(worker, True)
            return {"accepted": True, "block": None}
        self._count(worker, False)
        return {"accepted": False, "reason": "low difficulty share"}

    def _submit_block(self, job, res, v, worker):
        """Block assembly and submission for a verified network-
        target candidate (EXP-036: the submitblock response is
        a claim; chain state is the fact). Shared by the fixed
        and vardiff submit paths; the record shape is the one
        this server has always produced."""
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
        return rec

    # -- vardiff share submission -----------------------------------
    def _submit_share_vardiff(self, job_id, extranonce1, en2,
                              ntime, nonce, worker=None):
        """The vardiff submit path (DESIGN.md section 5).
        Duplicate detection precedes all judging; a share is
        judged against the difficulty snapshot taken when its
        job was issued; superseded jobs are classified stale
        against the bounded history; block candidacy runs the
        identical EXP-036 pipeline as the fixed path."""
        en1 = bytes(extranonce1)
        with self.lock:
            conn = self.connections.get(en1)
            if conn is not None and worker:
                conn["worker"] = str(worker)
        if conn is not None:
            key = (job_id, en2, ntime, nonce)
            with self.lock:
                seen = key in conn["seen"]
                if not seen:
                    conn["seen"].add(key)
                    if len(conn["seen"]) > 200000:
                        conn["seen"] = {key}
            if seen:
                self._count_vd(worker, "duplicate")
                return {"accepted": False,
                        "reason": "duplicate share",
                        "classification": "duplicate"}
        job, stale = self._find_job(job_id)
        if job is None:
            self._count(worker, False)
            return {"accepted": False, "reason": "unknown job",
                    "classification": "unknown_job"}
        if stale:
            return self._submit_stale(
                job, conn, extranonce1, en2, ntime, nonce, worker)
        snap = None
        if conn is not None:
            snap = conn["snapshots"].get(job_id)
        share_target = (share_target_for(snap) if snap is not None
                        else self.share_target)
        return self._submit_current(
            job, share_target, conn, extranonce1, en2, ntime,
            nonce, worker)

    def _after_accept(self, conn, extranonce1):
        if conn is None:
            return
        now = time.time()
        rec = self.vardiff.on_accepted_share(conn["state"], now)
        if rec is not None:
            self._log_adjustment(extranonce1, conn, rec, now)

    def _submit_current(self, job, share_target, conn,
                        extranonce1, en2, ntime, nonce, worker):
        """The production submit pipeline with the share target
        taken from this connection's snapshot for this job. The
        network-target leg is identical to the fixed path:
        difficulty never enters candidate judging."""
        res, err = self.validate_share(job, extranonce1, en2,
                                       ntime, nonce)
        if err:
            self._count(worker, False)
            return {"accepted": False, "reason": err,
                    "classification": "invalid"}
        if not (res["value"] <= job["target"]
                or res["value"] <= share_target):
            self._count(worker, False)
            return {"accepted": False,
                    "reason": "low difficulty share",
                    "classification": "below_target"}
        v = verify_candidate(res["header"], self._pow_limit(),
                             share_target=share_target)
        if v["target"] != job["target"]:
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
                    "reason": f"exact verification failed: "
                              f"{v['reason']}",
                    "classification": "invalid"}
        if v["meets_network_target"]:
            rec = self._submit_block(job, res, v, worker)
            rec["stale"] = False
            self._count(worker, True, block=rec["accepted"],
                        candidate=True)
            self._after_accept(conn, extranonce1)
            return {"accepted": True, "block": rec,
                    "classification": "block_candidate"}
        if v["meets_share_target"]:
            self._count(worker, True)
            self._after_accept(conn, extranonce1)
            return {"accepted": True, "block": None,
                    "classification": "share"}
        self._count(worker, False)
        return {"accepted": False,
                "reason": "low difficulty share",
                "classification": "below_target"}

    def _submit_stale(self, job, conn, extranonce1, en2, ntime,
                      nonce, worker):
        """A share answering a superseded job: classified,
        never counted as an accepted share, and judged against
        its own job and its own snapshot. A network-target hit
        is still a real candidate and goes through the exact
        pipeline; chain state decides its acceptance."""
        res, err = self.validate_share(job, extranonce1, en2,
                                       ntime, nonce)
        if err:
            self._count_vd(worker, "stale")
            self._stale_record(job, worker, "stale-invalid", err)
            return {"accepted": False,
                    "reason": f"stale job: {err}",
                    "classification": "stale"}
        snap = None
        if conn is not None:
            snap = conn["snapshots"].get(job["job_id"])
        share_target = (share_target_for(snap) if snap is not None
                        else None)
        meets_net = res["value"] <= job["target"]
        meets_share = (share_target is not None
                       and res["value"] <= share_target)
        if not (meets_net or meets_share):
            self._count_vd(worker, "stale")
            self._stale_record(job, worker, "stale-low",
                               "below its job's targets")
            return {"accepted": False,
                    "reason": "stale job: below target",
                    "classification": "stale"}
        v = verify_candidate(res["header"], self._pow_limit(),
                             share_target=share_target)
        if v["target"] != job["target"]:
            v = dict(v, classification="invalid",
                     reason="header-target-mismatch")
        if v["classification"] == "invalid":
            rec = {"height": job["template"]["height"],
                   "hash": res["digest"][::-1].hex(),
                   "reason": v["reason"], "worker": worker,
                   "stale": True}
            with self.lock:
                self.candidates_rejected.append(rec)
            self._count_vd(worker, "stale")
            return {"accepted": False,
                    "reason": f"stale job: exact verification "
                              f"failed: {v['reason']}",
                    "classification": "stale"}
        if v["meets_network_target"]:
            rec = self._submit_block(job, res, v, worker)
            rec["stale"] = True
            self._count_vd(worker, "stale")
            return {"accepted": False, "block": rec,
                    "reason": "stale job: block candidate "
                              "submitted",
                    "classification": "stale"}
        self._count_vd(worker, "stale")
        self._stale_record(job, worker, "stale-valid",
                           "met its job's share target")
        return {"accepted": False, "reason": "stale job",
                "classification": "stale"}

    def _stale_record(self, job, worker, kind, detail):
        with self.lock:
            self.stale_records.append({
                "height": job["template"]["height"],
                "job_id": job["job_id"], "worker": worker,
                "kind": kind, "detail": detail,
                "ts": time.time()})


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
        self._en1 = extranonce1
        # Vardiff delta 1: connection registration at connect
        # and teardown at disconnect (inert without vardiff).
        srv.register_connection(extranonce1)
        with self.server.clients_lock:
            self.server.clients.add(self)
        try:
            self._run(srv, extranonce1)
        finally:
            with self.server.clients_lock:
                self.server.clients.discard(self)
            srv.unregister_connection(extranonce1)

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
                # Vardiff delta 2: the connection's own
                # difficulty (the fixed share difficulty when
                # vardiff is off: the same value as before).
                self._send({"id": None, "method": "mining.set_difficulty",
                            "params": [srv.connection_difficulty(
                                extranonce1)]})
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
                if srv.vardiff is not None:
                    with srv.lock:
                        conn = srv.connections.get(
                            bytes(extranonce1))
                        if conn is not None:
                            conn["worker"] = worker_name
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
                # Vardiff delta 3: a set_difficulty notice after
                # any submit that changed this connection's
                # difficulty (never fires without vardiff).
                notice = srv.pending_notice(extranonce1)
                if notice is not None:
                    self._send({"id": None,
                                "method": "mining.set_difficulty",
                                "params": [notice]})
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

    def __init__(self, addr, solo: SoloServer, share_difficulty=None,
                 handler_class=_Handler):
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
        # The handler class is a parameter (Stage 6, DESIGN.md
        # section 9 step 2); the default is the production
        # handler, which carries the vardiff deltas itself.
        super().__init__(addr, handler_class)

    def next_en1(self):
        with self._en1_lock:
            self._en1 += 1
            return self._en1.to_bytes(4, "little")

    def broadcast(self, job):
        """Send a fresh job to every connected worker. Under
        vardiff, each notify is preceded by that connection's
        own current difficulty (vardiff delta 4: the difficulty
        in force for the job it is about to receive); without
        vardiff the broadcast is the bare notify, as before."""
        with self.clients_lock:
            clients = list(self.clients)
        for h in clients:
            try:
                if self.solo.vardiff is not None:
                    en1 = getattr(h, "_en1", None)
                    if en1 is not None:
                        h._send({"id": None,
                                 "method": "mining.set_difficulty",
                                 "params": [
                                     self.solo.connection_difficulty(
                                         en1)]})
                        with self.solo.lock:
                            conn = self.solo.connections.get(
                                bytes(en1))
                            if conn is not None:
                                conn["notified"] = \
                                    conn["state"]["difficulty"]
                h._send({"id": None, "method": "mining.notify",
                         "params": self.solo.notify_params(job)})
            except Exception:
                pass
