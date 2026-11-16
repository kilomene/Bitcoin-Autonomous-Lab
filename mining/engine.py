"""Tasks 005/006: autonomous mining engine.

Obtains real mining work with getblocktemplate, constructs candidate
blocks (BIP34 coinbase, BIP141 witness commitment, merkle root, exact
fee accounting), searches nonces through the ComputeEngine (CUDA when
a real device exists, CPU otherwise, every candidate CPU verified),
submits with submitblock, and counts a block as mined only when the
node has it on the active chain as its best block.

generatetoaddress is never used here. Template transactions are
re-parsed and their txids (and wtxids) recomputed; a mismatch rejects
the template. The engine is chain-agnostic at this layer; the
autonomous agent enforces the regtest-only default.
"""

import logging
import struct
import threading
import time

from blockchain.transactions import btc_to_sats
from gpu.engine import ComputeEngine
from mining.mining_statistics import (FrontierAccountant,
                                      MiningStatistics)
from mining.pow import coinbase_subsidy, merkle_root, dsha256
from mining.prefetch import PrefetchFeed, PrefetchQueue
from mining.work_checkpoint import WorkCheckpoint

log = logging.getLogger("bal.mining.engine")

WITNESS_COMMITMENT_HEADER = bytes.fromhex("aa21a9ed")
RESERVED_VALUE = b"\x00" * 32


def encode_varint(n):
    if n < 0xFD:
        return bytes([n])
    if n <= 0xFFFF:
        return b"\xfd" + struct.pack("<H", n)
    if n <= 0xFFFFFFFF:
        return b"\xfe" + struct.pack("<I", n)
    return b"\xff" + struct.pack("<Q", n)


def push_data(data):
    if len(data) < 0x4C:
        return bytes([len(data)]) + data
    if len(data) <= 0xFF:
        return b"\x4c" + bytes([len(data)]) + data
    raise ValueError("push too large")


def script_num_push(value):
    """CScript push of a small integer, as Core encodes block height."""
    if value == 0:
        return b"\x00"
    neg = value < 0
    absval = -value if neg else value
    out = bytearray()
    while absval:
        out.append(absval & 0xFF)
        absval >>= 8
    if out[-1] & 0x80:
        out.append(0x80 if neg else 0x00)
    elif neg:
        out[-1] |= 0x80
    return push_data(bytes(out))


def address_script_pubkey(rpc, address):
    info = rpc.call("validateaddress", address)
    if not info.get("isvalid"):
        raise ValueError(f"invalid payout address: {address}")
    return bytes.fromhex(info["scriptPubKey"])


def strip_witness(raw):
    """Return (stripped_bytes, has_witness) for a raw transaction."""
    if len(raw) >= 6 and raw[4] == 0 and raw[5] == 1:
        # marker 0x00, flag 0x01 after the 4-byte version
        pos = 6
        def read_varint(p):
            first = raw[p]
            if first < 0xFD:
                return first, p + 1
            if first == 0xFD:
                return struct.unpack("<H", raw[p + 1:p + 3])[0], p + 3
            if first == 0xFE:
                return struct.unpack("<I", raw[p + 1:p + 5])[0], p + 5
            return struct.unpack("<Q", raw[p + 1:p + 9])[0], p + 9
        vin_count, pos = read_varint(pos)
        vin_start = pos
        for _ in range(vin_count):
            pos += 36
            slen, pos = read_varint(pos)
            pos += slen + 4
        vin_end = pos
        vout_count, pos = read_varint(pos)
        for _ in range(vout_count):
            pos += 8
            slen, pos = read_varint(pos)
            pos += slen
        vout_end = pos
        # version + (vin and vout, which sit between the marker and
        # the witness data) + locktime; witness bytes live between
        # vout_end and the final 4 locktime bytes.
        stripped = raw[:4] + raw[6:vout_end] + raw[-4:]
        return stripped, True
    return raw, False


def txid_of(raw):
    stripped, _ = strip_witness(raw)
    return dsha256(stripped)


def wtxid_of(raw):
    return dsha256(raw)


def build_coinbase(height, value_sats, script_pubkey, extranonce=b"",
                   flags_hex="", witness_commitment=None):
    """Returns (full_bytes, txid_internal_order)."""
    script_sig = script_num_push(height) + b"/BAL/" + extranonce
    if flags_hex:
        script_sig += bytes.fromhex(flags_hex)
    if not (2 <= len(script_sig) <= 100):
        raise ValueError(f"coinbase scriptSig length {len(script_sig)}")
    vin = (b"\x00" * 32 + struct.pack("<I", 0xFFFFFFFF)
           + encode_varint(len(script_sig)) + script_sig
           + struct.pack("<I", 0xFFFFFFFF))
    outputs = [(value_sats, script_pubkey)]
    if witness_commitment is not None:
        commit_script = b"\x6a" + push_data(
            WITNESS_COMMITMENT_HEADER + witness_commitment)
        outputs.append((0, commit_script))
    vout = encode_varint(len(outputs))
    for value, script in outputs:
        vout += struct.pack("<Q", value) + encode_varint(len(script)) + script
    version = struct.pack("<i", 2)
    locktime = struct.pack("<I", 0)
    stripped = version + encode_varint(1) + vin + vout + locktime
    if witness_commitment is None:
        return stripped, dsha256(stripped)
    witness = encode_varint(1) + encode_varint(32) + RESERVED_VALUE
    full = version + b"\x00\x01" + encode_varint(1) + vin + vout \
        + witness + locktime
    return full, dsha256(stripped)


class TemplateError(Exception):
    pass


# ---------------------------------------------------------------------
# EXP-025 repaired template cache (integrated 2026-11-14 on the
# owner's decision, option A). Ported from the research design in
# research/sha256d/phase6b/benchmarks/exp025_repaired.py, which
# EXP-025 accepted after demonstrating that the earlier EXP-023
# prototype's 8-field fingerprint silently served stale candidates
# (5 stale serves, 2 validation bypasses). The prototype's
# fingerprint design is NOT used here in any form.
#
# Design: a deterministic layered identity. Every cached object
# belongs to exactly one layer, and each layer's key is a double
# SHA-256 over the COMPLETE dependency set of that layer's objects
# (dependency matrix: research/sha256d/phase6b/
# EXP025_CACHE_CORRECTNESS.md section 2):
#
#   family_key   payout address, payout scriptPubKey, chain,
#                halving interval.
#   tx_key       transaction count, and for every transaction IN
#                ORDER: its txid (internal byte order), its wtxid,
#                its fee; plus the template's
#                default_witness_commitment string (a validation
#                input: any change forces revalidation, so it is
#                keyed even though it is not itself cached data).
#   coinbase_key family_key, height, coinbasevalue, coinbaseaux
#                flags, witness commitment (or an explicit none
#                marker).
#   header_key   version, previousblockhash, bits, target.
#
#   identity = dsha256(tx_key || coinbase_key || header_key)
#
# Completeness: every byte of every cached object is a
# deterministic function of the inputs hashed into its layer key
# (raw transaction bytes enter through their wtxid, which is
# dsha256 of the full serialisation, and through the verified
# txid, which is dsha256 of the stripped serialisation). The
# identity is therefore exact up to SHA-256 collision resistance,
# the same assumption Bitcoin itself places on txids.
#
# Serving rule: any serve that takes a template recomputes that
# template's identity FROM SCRATCH (full transaction pass with
# txid re-verification, witness commitment cross-check, and the
# coinbasevalue equals subsidy plus fees check, identical to the
# uncached path's validations) and raises TemplateError on any
# mismatch. It never silently serves. The one exception is the
# mining loop's own steps: MiningEngine.mine_cycle prepares a
# template once (identity verified at prepare time) and then
# steps extranonces off that prepared entry without re-passing
# the template, because the template object is held by the loop
# itself and never handed out between steps. That is the steps
# shape EXP-025 verified (pooled 23.02x candidate-construction
# rate under the EXP-017 protocol; a candidate-construction
# rate, never a hash rate). The family shape (a fresh identity
# per job) was NOT verified by EXP-025 and no gain is claimed
# for it here.
#
# Deliberately NOT in any key: mintime and curtime. The uncached
# construction reads them fresh from the passed template on
# every call; no cached object depends on them; the header time
# is assembled per build from the passed (or prepared) template
# exactly as the uncached path does. The extranonce is likewise
# a per-build input, never cached.
# ---------------------------------------------------------------------

_CACHE_ZERO32 = b"\x00" * 32


def _lp(data):
    """Length-prefixed bytes, for unambiguous key material."""
    return struct.pack("<Q", len(data)) + data


class TemplateFamily:
    """Level 1: constants shared by every template a node serves
    to one payout address, keyed by everything they depend on.
    Constructed lazily by MiningEngine on the first cached build,
    so engine construction itself performs no RPC."""

    def __init__(self, rpc, payout_address):
        self.rpc = rpc
        self.payout = payout_address
        self.script = address_script_pubkey(rpc, payout_address)
        self.chain = rpc.get_blockchain_info()["chain"]
        self.interval = 150 if self.chain == "regtest" else 210000
        self.family_key = dsha256(
            b"bal/template-cache/family/v1"
            + _lp(payout_address.encode())
            + _lp(self.script)
            + _lp(self.chain.encode())
            + struct.pack("<Q", self.interval))


def _derive_tx_pass(template):
    """The full transaction pass, mirroring the uncached
    build_candidate's checks exactly. Returns (txs_raw, txids,
    wtxids, total_fees, witness_count, commitment). Raises
    TemplateError on any inconsistency the uncached path would
    raise."""
    txs_raw = []
    txids = []
    wtxids = []
    total_fees = 0
    for tx in template.get("transactions", []):
        for field in ("txid", "data"):
            if field not in tx:
                raise TemplateError(f"template tx missing {field}")
        raw = bytes.fromhex(tx["data"])
        computed_txid = txid_of(raw)[::-1].hex()
        if computed_txid != tx["txid"]:
            raise TemplateError(
                f"template txid mismatch: core {tx['txid']} vs "
                f"computed {computed_txid}")
        txs_raw.append(raw)
        txids.append(bytes.fromhex(tx["txid"])[::-1])
        wtxids.append(wtxid_of(raw))
        total_fees += tx.get("fee", 0)
    witness_count = sum(1 for a, b in zip(txids, wtxids) if a != b)
    commitment = None
    if witness_count:
        wroot = merkle_root([_CACHE_ZERO32] + wtxids)
        commitment = dsha256(wroot + RESERVED_VALUE)
        expected = template.get("default_witness_commitment")
        if expected and commitment.hex() not in expected:
            raise TemplateError(
                "witness commitment disagrees with Core")
    return (txs_raw, txids, wtxids, total_fees, witness_count,
            commitment)


def _tx_layer_key(template, txids, wtxids, fees):
    parts = [b"bal/template-cache/tx/v1", encode_varint(len(txids))]
    for txid, wtxid, fee in zip(txids, wtxids, fees):
        parts.append(txid)
        parts.append(wtxid)
        parts.append(struct.pack("<q", fee))
    dwc = template.get("default_witness_commitment")
    parts.append(_lp(dwc.encode() if dwc else b""))
    return dsha256(b"".join(parts))


def _coinbase_layer_key(family, template, commitment):
    flags = template.get("coinbaseaux", {}).get("flags", "")
    return dsha256(
        b"bal/template-cache/coinbase/v1"
        + family.family_key
        + struct.pack("<Q", template["height"])
        + struct.pack("<q", template["coinbasevalue"])
        + _lp(bytes.fromhex(flags) if flags else b"")
        + (commitment if commitment is not None else b"\x00" * 32)
        + (b"\x01" if commitment is not None else b"\x00"))


def _header_layer_key(template):
    return dsha256(
        b"bal/template-cache/header/v1"
        + struct.pack("<i", template["version"])
        + bytes.fromhex(template["previousblockhash"])
        + bytes.fromhex(template["bits"])
        + template["target"].encode())


def template_identity(family, template):
    """Recompute a template's full layered identity from
    scratch, performing every validation the uncached
    construction performs on the identity inputs (txid
    re-verification, witness commitment cross-check,
    coinbasevalue equals subsidy plus fees). Returns
    (identity, tx_key, coinbase_key, header_key, derived)
    where derived is the _derive_tx_pass tuple. Raises
    TemplateError exactly where the uncached path would."""
    derived = _derive_tx_pass(template)
    txs_raw, txids, wtxids, total_fees, witness_count, \
        commitment = derived
    fees = [tx.get("fee", 0)
            for tx in template.get("transactions", [])]
    subsidy = coinbase_subsidy(template["height"], family.interval)
    if template["coinbasevalue"] != subsidy + total_fees:
        raise TemplateError(
            f"coinbasevalue {template['coinbasevalue']} != subsidy "
            f"{subsidy} + fees {total_fees}")
    tx_key = _tx_layer_key(template, txids, wtxids, fees)
    cb_key = _coinbase_layer_key(family, template, commitment)
    hd_key = _header_layer_key(template)
    identity = dsha256(tx_key + cb_key + hd_key)
    return identity, tx_key, cb_key, hd_key, derived


class PreparedTemplate:
    """Level 2: one template's extranonce-independent work,
    paid once, served only under its full layered identity."""

    def __init__(self, family, template):
        self.family = family
        (identity, tx_key, cb_key, hd_key, derived) = \
            template_identity(family, template)
        (txs_raw, txids, wtxids, total_fees, witness_count,
         commitment) = derived
        self.identity = identity
        self.tx_key = tx_key
        self.coinbase_key = cb_key
        self.header_key = hd_key
        self.template = template
        self.txs_raw = txs_raw
        self.txids = txids
        self.total_fees = total_fees
        self.witness_count = witness_count
        self.commitment = commitment
        self.value = template["coinbasevalue"]
        self.flags_hex = template.get("coinbaseaux", {}).get(
            "flags", "")
        self.target = int(template["target"], 16)
        self.height = template["height"]
        levels = [[_CACHE_ZERO32] + list(txids)]
        while len(levels[-1]) > 1:
            lvl = levels[-1]
            levels.append([
                dsha256(lvl[i] + (lvl[i + 1] if i + 1 < len(lvl)
                                  else lvl[i]))
                for i in range(0, len(lvl), 2)])
        self.levels = levels
        self.body_head = encode_varint(1 + len(txs_raw))
        self.body_tail = b"".join(txs_raw)

    def root_with_coinbase(self, cb_txid):
        if len(self.levels) == 1:
            return cb_txid
        cur = cb_txid
        idx = 0
        for level in self.levels[:-1]:
            sib = idx ^ 1
            sib_hash = level[sib] if sib < len(level) else level[idx]
            cur = (dsha256(cur + sib_hash) if idx % 2 == 0
                   else dsha256(sib_hash + cur))
            idx //= 2
        return cur

    def build(self, extranonce_int, template=None, now=None):
        """One extranonce step. A sibling template is served
        ONLY if its freshly recomputed full layered identity
        equals the prepared identity; any other sibling raises
        TemplateError. With template=None the prepared template
        itself is stepped (the mine_cycle fast path: identity
        was verified at prepare time and the loop holds the
        template object). Time fields are read from the
        template in use per build, exactly as the uncached
        path reads them."""
        t = self.template if template is None else template
        if template is not None:
            sibling_identity = template_identity(
                self.family, template)[0]
            if sibling_identity != self.identity:
                raise TemplateError(
                    "template identity mismatch: refusing to "
                    "serve a sibling under a different layered "
                    "identity")
        coinbase, cb_txid = build_coinbase(
            self.height, self.value, self.family.script,
            extranonce=struct.pack("<I", extranonce_int),
            flags_hex=self.flags_hex,
            witness_commitment=self.commitment)
        root = self.root_with_coinbase(cb_txid)
        if now is None:
            now = int(time.time())
        curtime = max(t.get("mintime", 0) + 1,
                      min(now, t.get("curtime", now)))
        header = (
            struct.pack("<i", t["version"])
            + bytes.fromhex(t["previousblockhash"])[::-1]
            + root
            + struct.pack("<I", curtime)
            + bytes.fromhex(t["bits"])[::-1]
            + struct.pack("<I", 0))
        body = self.body_head + coinbase + self.body_tail
        return {
            "header": header, "body": body,
            "target": self.target,
            "height": self.height, "fees": self.total_fees,
            "tx_count": 1 + len(self.txs_raw),
            "witness_count": self.witness_count,
        }


class TemplateCache:
    """Identity-keyed template store with reuse counters, so
    tests can assert that reuse actually happened (and only
    under an identical identity). Bounded: the oldest entries
    are evicted past max_entries so a long-running engine does
    not accumulate one prepared template per block forever."""

    def __init__(self, max_entries=128):
        self.by_identity = {}
        self.max_entries = max_entries
        self.prepares = 0
        self.hits = 0
        self.identity_checks = 0
        # EXP-051: the prefetch feed prepares templates from
        # its own thread while the mining thread prepares on
        # the synchronous path; the lock keeps the
        # check-then-store sequence and the counters exact
        # under that concurrency. Semantics are unchanged for
        # single-threaded callers.
        self._lock = threading.Lock()

    def get(self, family, template):
        with self._lock:
            identity = template_identity(family, template)[0]
            self.identity_checks += 1
            key = (family.family_key, identity)
            if key in self.by_identity:
                self.hits += 1
                return self.by_identity[key], True
            prep = PreparedTemplate(family, template)
            assert prep.identity == identity
            self.by_identity[key] = prep
            while len(self.by_identity) > self.max_entries:
                self.by_identity.pop(next(iter(self.by_identity)))
            self.prepares += 1
            return prep, False


class MiningEngine:
    def __init__(self, rpc, payout_address, compute=None, batch_size=65536,
                 use_template_cache=True, extranonce_space=(0, 64),
                 checkpoint_path=None, statistics=None,
                 use_prefetch=False, prefetch_depth=2,
                 prefetch_fetcher=None):
        self.rpc = rpc
        self.payout = payout_address
        self.compute = compute or ComputeEngine()
        self.batch_size = batch_size
        # EXP-034: the extranonce rounds mine_cycle steps, as
        # (first_round, round_count) over the 32-bit coinbase
        # extranonce. The default (0, 64) is the historical
        # behaviour exactly. Two engines mining the same template
        # for the same payout address build byte-identical
        # candidates over the same rounds (proven in
        # tests/test_exp034_job_template.py), so engines that
        # must not duplicate each other's work are constructed
        # with disjoint spaces; assigning those spaces to
        # workers is the coordinator's job (EXP-035).
        # build_candidate itself is unchanged: it still takes an
        # absolute extranonce value.
        en_first, en_count = extranonce_space
        if not (0 <= en_first and 1 <= en_count
                and en_first + en_count <= (1 << 32)):
            raise ValueError(
                f"extranonce_space {extranonce_space} outside the "
                f"32-bit extranonce range")
        self.extranonce_space = (en_first, en_count)
        # EXP-025 repaired template cache (see the cache section
        # above). Enabled by default; use_template_cache=False (or
        # a direct build_candidate_uncached call) is the preserved
        # uncached fallback path, mirroring how the v512
        # integration preserved the C backend.
        self.use_template_cache = use_template_cache
        self.template_cache = TemplateCache()
        self._cache_family = None
        # EXP-038 work-state checkpoint (opt-in): when a path is
        # given, mine_cycle records its completed search
        # frontier per template identity and a restarted engine
        # resumes there instead of rescanning from nonce 0 and
        # extranonce 0. Default None is exactly the historical
        # behaviour; every checkpoint touch below is behind
        # `self._work_checkpoint is not None`. See
        # mining/work_checkpoint.py for the honesty rules
        # (only completed batches advance the frontier, and any
        # identity, space or time-basis mismatch starts fresh).
        self.checkpoint_path = checkpoint_path
        self._work_checkpoint = (WorkCheckpoint(checkpoint_path)
                                 if checkpoint_path else None)
        # EXP-037 statistics wiring (Phase 002 step 4):
        # mine_cycle records search accounting, candidate
        # events and block submission outcomes into separated
        # MiningStatistics counters as the work happens. A
        # caller may pass its own MiningStatistics to share one
        # across engines; the default is a fresh instance per
        # engine, exposed as self.statistics. Recording goes
        # through the failure-isolated FrontierAccountant, so a
        # statistics defect never stops mining, and no result
        # dict changes: the counters are observable only
        # through self.statistics.snapshot(). The accountant's
        # per-header frontier is this engine's in-memory
        # accounting for its own lifetime; the EXP-038
        # checkpoint above remains the cross-restart mechanism
        # and is untouched by this.
        self.statistics = (statistics if statistics is not None
                           else MiningStatistics())
        self._accountant = FrontierAccountant(self.statistics)
        self._stats_recorder = self._accountant.recorder
        self._family_lock = threading.Lock()
        # EXP-051 prefetch queue (opt-in, register R-33): a
        # bounded queue of prepared templates filled by a
        # background GBT longpoll feed (mining/prefetch.py),
        # served at mine_cycle transitions only after the
        # EXP-025 identity recomputation and a best-block tip
        # check. Default use_prefetch=False is exactly the
        # historical behaviour and is the rollback surface:
        # no queue is constructed, no feed thread exists, and
        # mine_cycle resolves its template synchronously as
        # before. The queue is only ever consulted on the
        # steps fast path (template cache on, build_candidate
        # not overridden); on any other shape it stays inert.
        # prefetch_fetcher, when given, replaces the feed's
        # longpoll fetch (longpollid -> template); the default
        # is this engine's wait_template. The category F
        # harness uses it to give the feed its own RPC
        # connection so stage timing stays on the mining
        # thread.
        self.use_prefetch = use_prefetch
        self.prefetch_fetcher = prefetch_fetcher
        self.prefetch_queue = None
        self._prefetch_feed = None
        if use_prefetch:
            self.prefetch_queue = PrefetchQueue(
                max_entries=prefetch_depth,
                recorder=lambda category:
                    self._stats_recorder.record(category))

    def cache_family(self):
        """The engine's TemplateFamily, built lazily on the
        first cached build (one validateaddress and one
        getblockchaininfo round trip, then held for the
        engine's life, keyed into every cache identity).
        EXP-051: construction is lock-guarded because the
        prefetch feed thread can race the mining thread to
        the first build; the family is a pure function of
        (rpc answers, payout), so either build is the same
        family."""
        if self._cache_family is None:
            with self._family_lock:
                if self._cache_family is None:
                    self._cache_family = TemplateFamily(
                        self.rpc, self.payout)
        return self._cache_family

    # ------------------------------------------------ EXP-051

    def _prefetch_usable(self):
        """The queue is consulted only where the EXP-025
        steps fast path applies: template cache enabled and
        build_candidate not overridden by a caller or
        subclass. Everywhere else the prefetch machinery is
        inert and mine_cycle is the historical code path."""
        return (self.use_prefetch and self.use_template_cache
                and "build_candidate" not in self.__dict__
                and type(self).build_candidate
                is MiningEngine.build_candidate)

    def _prefetch_try_serve(self):
        """One queue serve attempt at a template transition.
        Records exactly one prefetch_served or
        prefetch_starved in the separated statistics (inside
        PrefetchQueue.serve). Returns (template, prepared)
        or None."""
        return self.prefetch_queue.serve(
            self.cache_family(), self.rpc.get_best_block_hash)

    def _prefetch_note_current(self, template, prep):
        """Start the feed on first use and tell it which
        template this cycle is mining, so its longpoll chain
        tracks the live one."""
        if prep is None or not self._prefetch_usable():
            return
        feed = self._prefetch_feed
        if feed is None:
            fetch = self.prefetch_fetcher
            if fetch is None:
                fetch = lambda lp: self.wait_template(lp)  # noqa: E731
            feed = PrefetchFeed(self.prefetch_queue, fetch,
                                self.prepare_template)
            self._prefetch_feed = feed
            feed.start()
        feed.note_current(template, prep.identity)

    def close_prefetch(self):
        """Stop the prefetch feed thread (the queue and its
        counters remain inspectable). Safe to call when
        prefetch was never enabled or never started."""
        if self._prefetch_feed is not None:
            self._prefetch_feed.stop()
            self._prefetch_feed = None

    def prepare_template(self, template):
        """Verify a template's full layered identity and return
        (PreparedTemplate, was_hit) from the identity-keyed
        cache. Raises TemplateError exactly where the uncached
        construction would. This is the prepare step the mining
        loop pays once per template before stepping extranonces
        off the prepared entry."""
        return self.template_cache.get(self.cache_family(), template)

    def get_template(self):
        return self.rpc.call("getblocktemplate", {"rules": ["segwit"]})

    def wait_template(self, longpollid, timeout_s=70):
        """GBT longpoll: Core holds this call until the template
        changes (new block or new mempool state) or the longpoll
        window passes, then returns the fresh template. This is how
        production miners avoid hammering the node for work."""
        client = self.rpc.with_timeout(timeout_s + 15)
        return client.call("getblocktemplate",
                           {"rules": ["segwit"], "longpollid": longpollid})

    def build_candidate(self, template, extranonce_int=0):
        """Construct one candidate. With the template cache
        enabled (the default), the construction is served by
        the EXP-025 repaired cache: the template's full layered
        identity is recomputed from scratch with the uncached
        path's own validations (in TemplateCache.get, and again
        in PreparedTemplate.build for the sibling serve), and
        any mismatch or invalid input raises TemplateError
        instead of serving. Output is byte-identical to the
        uncached path in all cases (gated in
        tests/test_template_cache.py)."""
        if not self.use_template_cache:
            return self.build_candidate_uncached(template,
                                                 extranonce_int)
        prep, _was_hit = self.prepare_template(template)
        return prep.build(extranonce_int, template=template)

    def build_candidate_uncached(self, template, extranonce_int=0):
        """The original uncached construction, preserved
        unchanged as the fallback path and as the differential
        reference for the cache gates."""
        txs_raw = []
        txids = []
        wtxids = []
        total_fees = 0
        for tx in template.get("transactions", []):
            for field in ("txid", "data"):
                if field not in tx:
                    raise TemplateError(f"template tx missing {field}")
            raw = bytes.fromhex(tx["data"])
            computed_txid = txid_of(raw)[::-1].hex()
            if computed_txid != tx["txid"]:
                raise TemplateError(
                    f"template txid mismatch: core {tx['txid']} vs "
                    f"computed {computed_txid}")
            txs_raw.append(raw)
            txids.append(bytes.fromhex(tx["txid"])[::-1])
            wtxids.append(wtxid_of(raw))
            total_fees += tx.get("fee", 0)
        witness_count = sum(1 for a, b in zip(txids, wtxids) if a != b)
        commitment = None
        if witness_count:
            wroot = merkle_root([b"\x00" * 32] + wtxids)
            commitment = dsha256(wroot + RESERVED_VALUE)
            expected = template.get("default_witness_commitment")
            if expected and commitment.hex() not in expected:
                raise TemplateError("witness commitment disagrees with Core")
        # Subsidy schedule is chain specific: regtest halves every
        # 150 blocks, mainnet and the public testnets every 210000.
        chain = self.rpc.get_blockchain_info()["chain"]
        interval = 150 if chain == "regtest" else 210000
        subsidy = coinbase_subsidy(template["height"], interval)
        value = template["coinbasevalue"]
        if value != subsidy + total_fees:
            raise TemplateError(
                f"coinbasevalue {value} != subsidy {subsidy} + fees "
                f"{total_fees}")
        script = address_script_pubkey(self.rpc, self.payout)
        coinbase, cb_txid = build_coinbase(
            template["height"], value, script,
            extranonce=struct.pack("<I", extranonce_int),
            flags_hex=template.get("coinbaseaux", {}).get("flags", ""),
            witness_commitment=commitment)
        root = merkle_root([cb_txid] + txids)
        now = int(time.time())
        curtime = max(template.get("mintime", 0) + 1,
                      min(now, template.get("curtime", now)))
        header = (
            struct.pack("<i", template["version"])
            + bytes.fromhex(template["previousblockhash"])[::-1]
            + root
            + struct.pack("<I", curtime)
            + bytes.fromhex(template["bits"])[::-1]
            + struct.pack("<I", 0))
        block_body = encode_varint(1 + len(txs_raw)) + coinbase \
            + b"".join(txs_raw)
        return {
            "header": header, "body": block_body,
            "target": int(template["target"], 16),
            "height": template["height"], "fees": total_fees,
            "tx_count": 1 + len(txs_raw), "witness_count": witness_count,
        }

    @staticmethod
    def batch_count(batch_size, start):
        """Nonces to request for the batch beginning at start
        (Task 003.2). The final batch is clamped to the remaining
        nonce space, count = min(batch_size, 2^32 - start), so the
        loop never submits a range extending past 0xFFFFFFFF, never
        skips a valid nonce, and covers the final nonce exactly
        once for any batch size, including sizes that do not
        divide 2^32. All arithmetic is on Python ints and cannot
        overflow."""
        if not (0 <= start < (1 << 32)):
            raise ValueError("batch start outside the nonce space")
        if batch_size < 1:
            raise ValueError("batch size must be positive")
        return min(batch_size, (1 << 32) - start)

    def mine_cycle(self, max_batches=200, deadline_seconds=120):
        """One full cycle. Returns a result dict; accepted means the
        block was submitted and is the node's best block.

        Hash accounting (Task 001 correction): total_hashes counts
        ACTUAL hash attempts reported by the backend through
        search_first_counted, never the requested batch size. The
        old code added the full batch size after every search,
        including early-exit searches that stopped after a handful
        of attempts, inflating every reported hashrate. Elapsed
        time uses a monotonic clock.

        Batch sizing (Task 003.2): every batch passes
        batch_count(self.batch_size, start) to the backend, never
        the raw configured batch size, so the final batch of a
        nonce-space walk stays inside the 32-bit space."""
        # Template resolution. EXP-051: with the prefetch
        # queue enabled and usable, one serve attempt comes
        # first (identity recomputed and tip verified inside
        # PrefetchQueue.serve; exactly one served/starved
        # counter is recorded). A served template skips the
        # GBT fetch and the prepare entirely; anything else
        # falls through to the synchronous resolution below,
        # which is the historical behaviour byte-for-byte.
        template = None
        prep = None
        if self._prefetch_usable():
            got = self._prefetch_try_serve()
            if got is not None:
                template, prep = got
        if template is None:
            template = self.get_template()
        started = time.perf_counter()
        total_hashes = 0
        batches = 0
        # Steps fast path (the EXP-025 verified shape): with the
        # cache enabled and build_candidate not overridden by a
        # caller or subclass, prepare the template once (full
        # layered identity verified at prepare time) and step
        # extranonces off the prepared entry. The loop holds the
        # template object itself and never hands it out between
        # steps, so no sibling serve is involved. When
        # build_candidate is overridden, the override is called
        # per round exactly as before this integration.
        if prep is None and (self.use_template_cache
                and "build_candidate" not in self.__dict__
                and type(self).build_candidate
                is MiningEngine.build_candidate):
            prep, _was_hit = self.prepare_template(template)
        if self.use_prefetch:
            self._prefetch_note_current(template, prep)
        en_first, en_count = self.extranonce_space
        # EXP-038 checkpoint resume: with a checkpoint enabled,
        # a previous process may already have examined part of
        # this exact template's space. The checkpoint decides
        # (fresh / resume / exhausted) under the identity,
        # space and time-basis match rules in
        # mining/work_checkpoint.py; the decision and its reason
        # ride in the result dicts as "checkpoint" so repeated
        # work across restarts is visible, never silent.
        ckpt = self._work_checkpoint
        ckpt_identity = None
        ckpt_note = None
        start_extranonce = en_first
        start_nonce = 0
        if ckpt is not None:
            ckpt_identity = (
                prep.identity if prep is not None
                else template_identity(self.cache_family(),
                                       template)[0])
            status, ck_en, ck_nonce, ckpt_note = ckpt.resume(
                ckpt_identity, self.extranonce_space,
                template.get("curtime"))
            if status == "exhausted":
                return {"accepted": False,
                        "reason": "nonce space exhausted",
                        "checkpoint": ckpt_note,
                        "height": template["height"], "hashes": 0,
                        "batches": 0,
                        "backend": self.compute.backend}
            if status == "resume":
                start_extranonce, start_nonce = ck_en, ck_nonce
        for extranonce in range(start_extranonce, en_first + en_count):
            cand = (prep.build(extranonce) if prep is not None
                    else self.build_candidate(template, extranonce))
            start = start_nonce if extranonce == start_extranonce else 0
            while start < (1 << 32):
                if time.perf_counter() - started > deadline_seconds or batches >= max_batches:
                    result = {"accepted": False, "reason": "budget exhausted",
                              "height": cand["height"], "hashes": total_hashes,
                              "batches": batches,
                              "backend": self.compute.backend}
                    if ckpt is not None:
                        result["checkpoint"] = ckpt_note
                    return result
                count = self.batch_count(self.batch_size, start)
                if hasattr(self.compute, "search_first_counted"):
                    hit, attempted, _secs = self.compute.search_first_counted(
                        cand["header"], cand["target"], start, count)
                else:
                    hit = self.compute.search_first(
                        cand["header"], cand["target"], start, count)
                    attempted = count
                total_hashes += attempted
                batches += 1
                self._accountant.record_search(
                    cand["header"], start, attempted, not hit,
                    backend=self.compute.backend)
                if hit:
                    # A candidate the backend presented. The
                    # GBT path's verification is Core's own
                    # submitblock and best-chain verdict below,
                    # so valid_candidates and
                    # network_target_candidates (defined by the
                    # EXP-036 verifier's classification) are not
                    # recorded here; the block counters carry
                    # this path's outcomes.
                    self._stats_recorder.record(
                        "candidates", 1,
                        backend=self.compute.backend)
                    sol = {"nonce": hit[0]}
                    header = cand["header"][:76] + struct.pack(
                        "<I", sol["nonce"])
                    block = header + cand["body"]
                    block_hash = dsha256(header)[::-1].hex()
                    submit = self.rpc.call("submitblock", block.hex())
                    self._stats_recorder.record(
                        "blocks_submitted", 1,
                        backend=self.compute.backend)
                    best = self.rpc.get_best_block_hash()
                    accepted = (submit is None and best == block_hash)
                    self._stats_recorder.record(
                        "blocks_accepted" if accepted
                        else "blocks_rejected", 1,
                        backend=self.compute.backend)
                    result = {
                        "accepted": accepted,
                        "submit_result": submit,
                        "height": cand["height"], "hash": block_hash,
                        "nonce": sol["nonce"], "hashes": total_hashes,
                        "batches": batches,
                        # Rounds searched in THIS cycle: with no
                        # checkpoint start_extranonce == en_first
                        # and this is the historical value; with
                        # a resume it honestly excludes the
                        # rounds a previous process examined.
                        "extranonce_rounds":
                            extranonce - start_extranonce + 1,
                        "backend": self.compute.backend,
                        "seconds": time.perf_counter() - started,
                        "hashrate": total_hashes / max(time.perf_counter() - started, 1e-9),
                        "tx_count": cand["tx_count"], "fees": cand["fees"],
                    }
                    if ckpt is not None:
                        result["checkpoint"] = ckpt_note
                    return result
                start += count
                if ckpt is not None:
                    # The batch above has returned without a
                    # hit, so its whole range is examined: the
                    # frontier may advance over it. A hit batch
                    # never reaches this line (the hit return
                    # above leaves the frontier at the last
                    # completed batch), so unfinished work is
                    # never recorded as completed.
                    if start >= (1 << 32):
                        f_en, f_nonce = extranonce + 1, 0
                    else:
                        f_en, f_nonce = extranonce, start
                    ckpt.record(
                        ckpt_identity, template["height"],
                        template["previousblockhash"],
                        template.get("curtime"),
                        self.extranonce_space, f_en, f_nonce)
        result = {"accepted": False, "reason": "nonce space exhausted",
                  "height": template["height"], "hashes": total_hashes,
                  "batches": batches, "backend": self.compute.backend}
        if ckpt is not None:
            ckpt.record(
                ckpt_identity, template["height"],
                template["previousblockhash"],
                template.get("curtime"), self.extranonce_space,
                en_first + en_count, 0, complete=True)
            result["checkpoint"] = (
                (ckpt_note + "; " if ckpt_note else "")
                + "space completed and checkpointed")
        return result
