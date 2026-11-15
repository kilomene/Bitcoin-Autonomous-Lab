#!/usr/bin/env python3
"""EXP-033 scope 2: fresh re-derivation of the header
mathematics.

Legs:
  A. Sound influence masks (may-depend over-approximation;
     a zero mask is a proof of independence) for block 2
     with the nonce as source, and for the outer compression
     with the inner digest as source.
  B. Exact identity checks by arithmetic sampling:
     W18(n) - W18(0) == s0(n) and W19(n) - W19(0) == n
     (mod 2^32) over random templates and nonces.
  C. z3 proofs: the same two identities with fully symbolic
     template words (UNSAT), round-3 state affinity (UNSAT),
     and a SAT counterexample to W20 delta GF(2)-linearity,
     numerically re-verified.
  D. Consumption census: where each produced state word is
     consumed in later rounds, bitwise vs arithmetic,
     derived from the round equations.

Run with the lab z3 venv python. Writes
RAW_RESULTS/exp033_taint_<ts>.json and
PROOFS/exp033_taint_proofs_<ts>.json.
"""

import hashlib
import json
import os
import random
import struct
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from exp033_common import K, H0, M32, compress, rotr, sha256_ref

HERE = os.path.dirname(os.path.abspath(__file__))
EXP033 = os.path.dirname(HERE)


# ---------------- influence masks (generalised) ----------------
# A word is a list of 32 masks; mask[j] is a Python int whose
# bit s is set iff source bit s may influence word bit j.

def m_zero():
    return [0] * 32


def m_word_bits(base):
    """Word whose bit j is exactly source bit base+j."""
    return [1 << (base + j) for j in range(32)]


def m_rotr(w, n):
    return [w[(j + n) % 32] for j in range(32)]


def m_shr(w, n):
    return [w[j + n] if j + n < 32 else 0 for j in range(32)]


def m_xor(*ws):
    out = [0] * 32
    for w in ws:
        for j in range(32):
            out[j] |= w[j]
    return out


def m_add(*ws):
    prefixes = []
    for w in ws:
        p = [0] * 32
        acc = 0
        for j in range(32):
            acc |= w[j]
            p[j] = acc
        prefixes.append(p)
    out = [0] * 32
    for j in range(32):
        m = 0
        for p in prefixes:
            m |= p[j]
        out[j] = m
    return out


def mask_run(block_words_mask, state_mask):
    """Symbolic compression over masks. block_words_mask is
    16 mask-words; state_mask is 8 mask-words."""
    W = list(block_words_mask)
    for t in range(16, 64):
        s0 = m_xor(m_rotr(W[t - 15], 7), m_rotr(W[t - 15], 18),
                   m_shr(W[t - 15], 3))
        s1 = m_xor(m_rotr(W[t - 2], 17), m_rotr(W[t - 2], 19),
                   m_shr(W[t - 2], 10))
        W.append(m_add(W[t - 16], s0, W[t - 7], s1))
    st = list(state_mask)
    states = [st]
    for t in range(64):
        a, b, c, d, e, f, g, h = st
        S1 = m_xor(m_rotr(e, 6), m_rotr(e, 11), m_rotr(e, 25))
        Ch = m_xor(e, f, g)
        T1 = m_add(h, S1, Ch, m_zero(), W[t])
        S0 = m_xor(m_rotr(a, 2), m_rotr(a, 13), m_rotr(a, 22))
        Maj = m_xor(a, b, c)
        T2 = m_add(S0, Maj)
        st = [m_add(T1, T2), a, b, c, m_add(d, T1), e, f, g]
        states.append(st)
    return W, states


def word_depends(w):
    return any(m != 0 for m in w)


def main():
    ts = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    rng = random.Random(20261115)
    out = {"experiment": "EXP-033 taint re-derivation",
           "host": os.uname().machine + " / " +
                   open("/proc/cpuinfo").read().split("model name")[1]
                   .split("\n")[0].strip(": ").strip(),
           "timestamp_utc": ts}
    proofs = {"experiment": "EXP-033 taint z3 proofs",
              "timestamp_utc": ts}

    # ---- Leg A1: block 2, nonce source (source bits 0..31) ----
    bw = [m_zero() for _ in range(16)]
    bw[3] = m_word_bits(0)
    Wm, Sm = mask_run(bw, [m_zero() for _ in range(8)])
    first_dep_word = next(t for t in range(16, 64)
                          if word_depends(Wm[t]))
    dep_words = [t for t in range(64) if word_depends(Wm[t])]
    state_dep_after = {}
    for t in range(0, 10):
        state_dep_after[t] = [word_depends(w) for w in Sm[t]]
    first_state_dep = next(
        t for t in range(65) if any(word_depends(w) for w in Sm[t]))
    out["block2_nonce_taint"] = {
        "first_nonce_dependent_expanded_word": first_dep_word,
        "nonce_dependent_message_words": [3],
        "nonce_dependent_expanded_words": dep_words,
        "count_nonce_dependent_expanded": len(dep_words),
        "state_dependence_after_t_rounds": state_dep_after,
        "first_state_with_nonce_dependence": first_state_dep,
        "nonce_free_rounds_at_block2_start": 3,
    }
    # rounds 0..2 leave the state nonce-free: S_3 is the state
    # after 3 rounds; dependence first appears in S_4.
    out["block2_nonce_taint"]["state_after_3_rounds_nonce_free"] = \
        not any(word_depends(w) for w in Sm[3])
    out["block2_nonce_taint"]["state_after_4_rounds"] = \
        [word_depends(w) for w in Sm[4]]

    # ---- Leg A2: outer compression, digest source (256 bits) ----
    ow = [m_word_bits(32 * i) for i in range(8)] + \
         [m_zero() for _ in range(8)]
    # outer block: W0..W7 digest words, W8 = 0x80000000,
    # W9..W14 = 0, W15 = 256 (length). Constants: zero mask.
    Wom, Som = mask_run(ow, [m_zero() for _ in range(8)])
    dep_sched = [t for t in range(16, 64) if word_depends(Wom[t])]
    rounds_dep = []
    for t in range(64):
        a, b, c, d, e, f, g, h = Som[t]
        produced = [Som[t + 1][0], Som[t + 1][4]]
        rounds_dep.append(any(word_depends(w) for w in produced))
    out["outer_digest_taint"] = {
        "digest_dependent_computed_schedule_words": dep_sched,
        "count": len(dep_sched),
        "rounds_producing_digest_dependent_words": rounds_dep,
        "count_rounds_digest_dependent": sum(rounds_dep),
        "digest_independent_complete_rounds": 64 - sum(rounds_dep),
    }

    # ---- Leg B: exact identity checks by sampling ----
    def sched_words(template16, n):
        words = list(template16)
        words[3] = n
        W = list(words)
        for t in range(16, 21):
            s0 = rotr(W[t - 15], 7) ^ rotr(W[t - 15], 18) ^ \
                (W[t - 15] >> 3)
            s1 = rotr(W[t - 2], 17) ^ rotr(W[t - 2], 19) ^ \
                (W[t - 2] >> 10)
            W.append((W[t - 16] + s0 + W[t - 7] + s1) & M32)
        return W

    def s0(x):
        return rotr(x, 7) ^ rotr(x, 18) ^ (x >> 3)

    ntest = 100000
    ok18 = ok19 = 0
    for _ in range(ntest):
        tpl = [rng.getrandbits(32) for _ in range(16)]
        n = rng.getrandbits(32)
        W0 = sched_words(tpl, 0)
        Wn = sched_words(tpl, n)
        if (Wn[18] - W0[18]) & M32 == s0(n):
            ok18 += 1
        if (Wn[19] - W0[19]) & M32 == n:
            ok19 += 1
    out["identity_sampling"] = {
        "trials": ntest,
        "W18_delta_equals_s0_nonce": ok18,
        "W19_delta_equals_nonce": ok19,
    }
    assert ok18 == ntest and ok19 == ntest

    # ---- Leg C: z3 proofs ----
    import z3

    def zrotr(x, k):
        return z3.RotateRight(x, k)

    def zsched(Words, n, upto=21):
        W = list(Words)
        W[3] = n
        for t in range(16, upto):
            s0v = zrotr(W[t - 15], 7) ^ zrotr(W[t - 15], 18) ^ \
                z3.LShR(W[t - 15], 3)
            s1v = zrotr(W[t - 2], 17) ^ zrotr(W[t - 2], 19) ^ \
                z3.LShR(W[t - 2], 10)
            W.append(W[t - 16] + s0v + W[t - 7] + s1v)
        return W

    Wsym = [z3.BitVec(f"W{i}", 32) for i in range(16)]
    n1 = z3.BitVec("n1", 32)
    n2 = z3.BitVec("n2", 32)
    Wa = zsched(Wsym, n1)
    Wb = zsched(Wsym, n2)

    def zs0(x):
        return zrotr(x, 7) ^ zrotr(x, 18) ^ z3.LShR(x, 3)

    s = z3.Solver()
    s.add(Wa[18] - zs0(n1) != Wb[18] - zs0(n2))
    proofs["W18_delta_form"] = str(s.check())
    s = z3.Solver()
    s.add(Wa[19] - n1 != Wb[19] - n2)
    proofs["W19_delta_form"] = str(s.check())

    # Round-3 state affinity with symbolic pre-state S_3.
    pre = [z3.BitVec(f"s{i}", 32) for i in range(8)]

    def zround(st, Wv, kt):
        a, b, c, d, e, f, g, h = st
        S1 = zrotr(e, 6) ^ zrotr(e, 11) ^ zrotr(e, 25)
        Ch = (e & f) ^ (~e & g)
        T1 = h + S1 + Ch + K[kt] + Wv
        S0 = zrotr(a, 2) ^ zrotr(a, 13) ^ zrotr(a, 22)
        Maj = (a & b) ^ (a & c) ^ (b & c)
        T2 = S0 + Maj
        return [T1 + T2, a, b, c, d + T1, e, f, g]

    sta = zround(pre, n1, 3)
    stb = zround(pre, n2, 3)
    s = z3.Solver()
    s.add(sta[0] - n1 != stb[0] - n2)
    proofs["round3_a_affine"] = str(s.check())
    s = z3.Solver()
    s.add(sta[4] - n1 != stb[4] - n2)
    proofs["round3_e_affine"] = str(s.check())

    # W20 delta GF(2)-linearity counterexample.
    W0v = zsched(Wsym, z3.BitVecVal(0, 32))
    Wab = zsched(Wsym, n1 ^ n2)
    D1 = Wa[20] - W0v[20]
    D2 = Wb[20] - W0v[20]
    D12 = Wab[20] - W0v[20]
    s = z3.Solver()
    s.add(D12 != (D1 ^ D2))
    res = str(s.check())
    proofs["W20_delta_linearity_counterexample"] = res
    if res == "sat":
        m = s.model()
        model = {str(d): m[d].as_long() for d in m.decls()}
        proofs["W20_counterexample_model"] = model
        Wvals = [model.get(f"W{i}", 0) for i in range(16)]
        nn1, nn2 = model.get("n1", 0), model.get("n2", 0)

        def W20(n):
            return sched_words(Wvals, n)[20]
        D = lambda n: (W20(n) - W20(0)) & M32
        proofs["W20_counterexample_numeric_recheck"] = {
            "n1": nn1, "n2": nn2,
            "D(n1^n2)": D(nn1 ^ nn2),
            "D(n1)^D(n2)": D(nn1) ^ D(nn2),
            "violates_linearity": D(nn1 ^ nn2) != (D(nn1) ^ D(nn2)),
        }

    # ---- Leg D: consumption census (from the round equations) ----
    # a' is at position 0 in S_{t+1}; then 1, 2, 3 in the
    # following states; consumed as addend when at position 3
    # (d) by e_new = d + T1. e' is at position 4 in S_{t+1};
    # then 5, 6, 7; consumed as addend when at position 7 (h)
    # inside T1.
    out["consumption_census"] = {
        "a_prime": {
            "bitwise_consumers_next_round": ["Sigma0(a)", "Maj(a,b,c)"],
            "positions_in_successive_states": [0, 1, 2, 3],
            "arithmetic_consumer": "e_new = d + T1, 3 rounds later",
        },
        "e_prime": {
            "bitwise_consumers_next_round": ["Sigma1(e)", "Ch(e,f,g)"],
            "positions_in_successive_states": [4, 5, 6, 7],
            "arithmetic_consumer": "T1 addend h, 3 rounds later",
        },
        "statement": "Every word produced by an addition is "
                     "consumed bitwise in the very next round "
                     "and arithmetically 3 rounds later; no "
                     "produced word has a bitwise-free window.",
    }

    # ---- Accounting ----
    out["accounting"] = {
        "compressions_per_trial": 3,
        "rounds_per_compression": 64,
        "total_round_slots": 192,
        "per_template_rounds": {
            "inner_block1": 64,
            "inner_block2_rounds_0_to_2": 3,
            "total": 67,
        },
        "per_nonce_rounds_conventional": {
            "inner_block2_rounds_3_to_63": 61,
            "outer_block": 64,
            "total": 125,
        },
        "status": "Accounting of the conventional "
                  "implementation. NOT a lower bound on any "
                  "implementation (Phase 6 correction).",
    }

    os.makedirs(os.path.join(EXP033, "RAW_RESULTS"), exist_ok=True)
    os.makedirs(os.path.join(EXP033, "PROOFS"), exist_ok=True)
    rp = os.path.join(EXP033, "RAW_RESULTS",
                      f"exp033_taint_{ts}.json")
    pp = os.path.join(EXP033, "PROOFS",
                      f"exp033_taint_proofs_{ts}.json")
    with open(rp, "w") as fh:
        json.dump(out, fh, indent=2)
    with open(pp, "w") as fh:
        json.dump(proofs, fh, indent=2)
    print(json.dumps({k: out[k] for k in
                      ("block2_nonce_taint", "outer_digest_taint",
                       "identity_sampling", "accounting")},
                     indent=2)[:2400])
    print("proofs:", {k: v for k, v in proofs.items()
                      if k not in ("W20_counterexample_model",)})
    print("wrote", rp)
    print("wrote", pp)
    return 0


if __name__ == "__main__":
    sys.exit(main())
