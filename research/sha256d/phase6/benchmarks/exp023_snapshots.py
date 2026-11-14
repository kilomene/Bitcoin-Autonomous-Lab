#!/usr/bin/env python3
"""EXP-023 snapshot ladder (Y-079 tooling, Y-076/Y-077 gates).

A round-stepping SHA-256 compression in pure Python (round
math shared with mining/pow_engine.py, the lab's from-spec
implementation) that can stop at any round and expose the
working state, so snapshot depths can be constructed and
compared exactly rather than argued.

Definitions used throughout EXP-023 (one indexing, matching
research/sha256d/header_and_midstate_analysis.md):

  R0    working state after round 0 of inner block 1
        (depends on block-1 W0: version)
  R8    after round 8 (W0..W8: version, prevhash)
  R11   after round 11 (W0..W11: plus merkle bytes 0..11;
        the registry dialect's "block-1 half", the first
        48 of the 64 block-1 bytes absorbed)
  MID   chaining state after all 64 rounds of block 1
        (the midstate; depends on every block-1 word)
  B2R0  working state after round 0 of inner block 2
        (depends on MID and block-2 W0: merkle tail)
  B2R1  after round 1 (plus W1: time)
  B2R2  after round 2 (plus W2: nbits; the nonce word W3
        is first consumed by round 3)
  SCH17 B2R2 plus block-2 schedule words W16 and W17
        (both nonce-independent per the W18 derivation)

A snapshot at a rung is a function of exactly the words
listed; the gates verify equality and inequality of every
rung by construction over randomised headers.
"""
import struct

import os
import sys

ROOT = "/home/hatch/workspace/bitcoin-autonomous-lab"
sys.path.insert(0, ROOT)

from mining.pow_engine import H0, K, MASK, _rr  # noqa: E402

RUNGS = ["R0", "R8", "R11", "MID", "B2R0", "B2R1", "B2R2",
         "SCH17"]


def schedule_words(block):
    """The 64 message-schedule words of one 64-byte block."""
    w = list(struct.unpack(">16I", block))
    for i in range(16, 64):
        s0 = _rr(w[i - 15], 7) ^ _rr(w[i - 15], 18) ^ (w[i - 15] >> 3)
        s1 = _rr(w[i - 2], 17) ^ _rr(w[i - 2], 19) ^ (w[i - 2] >> 10)
        w.append((w[i - 16] + s0 + w[i - 7] + s1) & MASK)
    return w


def run_rounds(working, w, start, end):
    """Advance working state (a..h) through rounds
    start..end-1 of the schedule w."""
    a, b, c, d, e, f, g, h = working
    for i in range(start, end):
        s1 = _rr(e, 6) ^ _rr(e, 11) ^ _rr(e, 25)
        ch = (e & f) ^ (~e & g)
        t1 = (h + s1 + ch + K[i] + w[i]) & MASK
        s0 = _rr(a, 2) ^ _rr(a, 13) ^ _rr(a, 22)
        mj = (a & b) ^ (a & c) ^ (b & c)
        t2 = (s0 + mj) & MASK
        h, g, f, e, d, c, b, a = (g, f, e, (d + t1) & MASK,
                                  c, b, a, (t1 + t2) & MASK)
    return (a, b, c, d, e, f, g, h)


def working_after(state, block, nrounds, w=None):
    """Working state after nrounds rounds of compressing
    block from chaining state `state`. No feedforward."""
    if w is None:
        w = schedule_words(block)
    return run_rounds(tuple(state), w, 0, nrounds)


def complete(state, block, working, nrounds, w=None):
    """Finish a compression: run rounds nrounds..63 from
    `working`, then feed forward with chaining `state`.
    Returns the new chaining state (8 words)."""
    if w is None:
        w = schedule_words(block)
    work = run_rounds(working, w, nrounds, 64)
    return tuple((s + x) & MASK for s, x in zip(state, work))


def chaining_after(state, block):
    """Full one-block compression with feedforward."""
    return complete(state, block, tuple(state), 0)


def block2_block(header):
    """Inner block 2 as a full 64-byte block: header bytes
    64..79 plus SHA-256 padding for an 80-byte message."""
    return (header[64:80] + b"\x80" + b"\x00" * 39
            + struct.pack(">Q", 640))


def ladder(header):
    """Every snapshot rung of an 80-byte header."""
    b1 = header[:64]
    b2 = block2_block(header)
    w2 = schedule_words(b2)
    mid = chaining_after(H0, b1)
    b2r2 = working_after(mid, b2, 3, w2)
    return {
        "R0": working_after(H0, b1, 1),
        "R8": working_after(H0, b1, 9),
        "R11": working_after(H0, b1, 12),
        "MID": mid,
        "B2R0": working_after(mid, b2, 1, w2),
        "B2R1": working_after(mid, b2, 2, w2),
        "B2R2": b2r2,
        "SCH17": (b2r2, w2[16], w2[17]),
    }


def inner_from_mid(mid, header):
    """Inner digest (8 words) completing block 2 from MID."""
    b2 = block2_block(header)
    return complete(mid, b2, tuple(mid), 0)


def inner_from_b2r2(mid, header, b2r2):
    """Inner digest completing block 2 from the B2R2
    working state (rounds 3..63 remain)."""
    b2 = block2_block(header)
    return complete(mid, b2, b2r2, 3)


def inner_from_sch17(mid, header, sch17):
    """Inner digest from SCH17: the stored schedule words
    must match the block's own W16/W17 (asserted), then
    rounds 3..63 complete the block."""
    b2r2, w16, w17 = sch17
    b2 = block2_block(header)
    w2 = schedule_words(b2)
    assert w2[16] == w16 and w2[17] == w17, "SCH17 words stale"
    return complete(mid, b2, b2r2, 3, w2)


def words_to_bytes(words):
    return struct.pack(">8I", *words)
