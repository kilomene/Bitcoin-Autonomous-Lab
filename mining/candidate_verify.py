"""EXP-036: the Exact Candidate Verifier.

One production stage that every candidate from every search
path routes through before anything is submitted anywhere.
It implements the verification core of the EXP-036 twelve-step
pipeline (directive section 9, steps 4 to 7 and 12):

- compute SHA-256d independently: the candidate header is
  hashed twice over, once with hashlib (mining.pow.dsha256)
  and once with the lab's from-specification pure-Python
  SHA-256 (mining.pow_engine.double_sha256_pure), an
  implementation that shares no code with OpenSSL. The two
  digests must agree byte for byte.
- decode nBits to the exact 256-bit target with Core's
  SetCompact semantics, including the negative, overflow,
  zero and above-limit rejections (mining.pow_engine.check_pow,
  the strict verifier that was previously called only by
  tests; EXP-036 wires it into production here).
- compare the full digest against the target with exact
  integer semantics only. Floating-point difficulty is never
  the authoritative test anywhere in this module: it appears
  in no comparison. (Matrix row M02 adopts the Bitaxe exact
  integer compare; row M03 rejects the Qaxe floating-point
  difficulty judgement, weakness W1.)

Cost discipline: verify_candidate runs the pure-Python hash,
so it is called only on candidate hits (a share at or above
the share target, or a claimed block candidate), never inside
a search loop. The hot path keeps its native speed; exactness
is paid for only where a decision is made.

verify_chain_acceptance implements pipeline step 12 for the
Bitcoin Core adapter: a submitblock response is a claim, and
acceptance is a fact about chain state. A block counts as
accepted only when the node holds it in its active chain
(as the tip, or with at least one confirmation), which is
the standard mining.engine.mine_cycle has always applied on
regtest and which the solo server previously skipped.
"""

import struct

from mining.pow import dsha256
from mining.pow_engine import (POW_LIMIT_MAINNET, POW_LIMIT_REGTEST,
                               check_pow, compact_decode,
                               double_sha256_pure)

# Compact-target sanity failures: when check_pow returns one
# of these, the header's target itself is not a legal Bitcoin
# target, so no comparison against it can be trusted.
TARGET_SANITY_REASONS = ("header-length", "negative-target",
                         "overflow-target", "zero-target",
                         "target-above-limit")

# Per-chain proof-of-work limits. Testnet and signet share
# mainnet's limit (their minimum difficulty is difficulty 1);
# regtest has its own permissive limit. Unknown chains fall
# back to the mainnet limit, the strictest: an unknown chain
# must prove its target is legal under mainnet rules before
# any candidate on it is trusted.
POW_LIMIT_BY_CHAIN = {
    "main": POW_LIMIT_MAINNET,
    "test": POW_LIMIT_MAINNET,
    "testnet4": POW_LIMIT_MAINNET,
    "signet": POW_LIMIT_MAINNET,
    "regtest": POW_LIMIT_REGTEST,
}


def pow_limit_for_chain(chain):
    """The proof-of-work limit for a Core chain name, with the
    conservative mainnet fallback for anything unrecognised."""
    return POW_LIMIT_BY_CHAIN.get(chain, POW_LIMIT_MAINNET)


def meets_target(value, target):
    """The one authoritative comparison form in the lab: exact
    integer value <= target. Boundary semantics match Core:
    a digest exactly equal to the target meets it."""
    return value <= target


def verify_candidate(header, pow_limit, share_target=None):
    """Verify one reconstructed 80-byte candidate header.

    Returns a dict:
      classification: "block_candidate", "share",
        "below_target", or "invalid".
      reason: the check_pow reason code ("ok", "high-hash",
        a target-sanity code), or "digest-disagreement" when
        the two independent SHA-256d implementations disagree,
        which is an invalid candidate regardless of targets.
      digest / digest_independent: the hashlib and pure-Python
        digests (internal byte order).
      digests_agree, valid_header: booleans. valid_header is
        True only when the digests agree and the decoded
        target is a legal target under pow_limit.
      value, target, nbits: exact integers.
      meets_network_target: the exact consensus test passed
        (check_pow ok and digests agree). This, and only
        this, decides block candidacy.
      meets_share_target: value <= share_target under the
        same validity conditions. The share target is a pool
        or server criterion, never a consensus test.
    """
    if len(header) != 80:
        return {"classification": "invalid", "reason": "header-length",
                "digest": None, "digest_independent": None,
                "digests_agree": False, "valid_header": False,
                "value": None, "target": None, "nbits": None,
                "meets_network_target": False,
                "meets_share_target": False}
    nbits = struct.unpack("<I", header[72:76])[0]
    target, _negative, _overflow = compact_decode(nbits)
    digest = dsha256(header)
    digest_independent = double_sha256_pure(header)
    agree = digest == digest_independent
    value = int.from_bytes(digest, "little")
    ok_exact, reason = check_pow(header, pow_limit)
    sane = reason not in TARGET_SANITY_REASONS
    valid_header = bool(agree and sane)
    meets_network = bool(agree and ok_exact)
    meets_share = bool(
        valid_header and share_target is not None
        and meets_target(value, share_target))
    if not agree:
        classification, out_reason = "invalid", "digest-disagreement"
    elif not sane:
        classification, out_reason = "invalid", reason
    elif meets_network:
        classification, out_reason = "block_candidate", reason
    elif meets_share:
        classification, out_reason = "share", reason
    else:
        classification, out_reason = "below_target", reason
    return {"classification": classification, "reason": out_reason,
            "digest": digest, "digest_independent": digest_independent,
            "digests_agree": agree, "valid_header": valid_header,
            "value": value, "target": target, "nbits": nbits,
            "meets_network_target": meets_network,
            "meets_share_target": meets_share}


def classify_submit_result(result):
    """Classify a submitblock return value.

    Core returns None when it accepts a block for processing,
    and a string otherwise: "duplicate" (already in the block
    index), "duplicate-invalid" (already processed and marked
    invalid), "inconclusive" (not in the best chain and its
    parent was not processed), or a validation reject reason
    such as "high-hash". The verbatim value is always recorded
    alongside this classification; the classification never
    replaces it. A None result is classified "accepted" as a
    statement about the response only: actual acceptance is
    decided by verify_chain_acceptance, never by this alone.
    """
    if result is None:
        return "accepted"
    if isinstance(result, str):
        if result.startswith("duplicate-invalid"):
            return "duplicate-invalid"
        if result.startswith("duplicate"):
            return "duplicate"
        if result == "inconclusive":
            return "inconclusive"
        return "rejected"
    return "rejected"


def verify_chain_acceptance(rpc, block_hash_hex):
    """Pipeline step 12: verify acceptance through node chain
    state, via the rpc.call interface the lab's adapters use.

    Returns (status, accepted):
      "tip": the block is the node's best block hash.
      "in-chain": the block is in the active chain with at
        least one confirmation (a descendant already sits on
        it, so it is not the tip but is accepted).
      "not-in-chain": the node does not hold the block in its
        active chain (unknown to its block index, or present
        only as a fork block with no confirmations).
      "unknown": chain state could not be read, so acceptance
        is unproven and reported as not accepted.
    """
    try:
        best = rpc.call("getbestblockhash")
    except Exception:
        return "unknown", False
    if best == block_hash_hex:
        return "tip", True
    try:
        header = rpc.call("getblockheader", block_hash_hex, True)
    except Exception as exc:
        if getattr(exc, "code", None) == -5:  # Block not found
            return "not-in-chain", False
        return "unknown", False
    if isinstance(header, dict):
        confirmations = header.get("confirmations")
        if confirmations is not None and confirmations >= 1:
            return "in-chain", True
        return "not-in-chain", False
    return "unknown", False
