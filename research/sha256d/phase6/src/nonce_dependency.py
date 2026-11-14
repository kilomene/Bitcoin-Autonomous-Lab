#!/usr/bin/env python3
"""EXP-016: exact nonce-dependency derivation for SHA-256 block 2.

Question (Phase 6, Task 2D; the foundation under Y-065 and
Y-075): exactly how does the nonce word W3 contaminate the
block-2 schedule and the compression state, round by round?
Which dependence is GF(2)-linear, which is integer-affine,
and where does addition-carry coupling make it genuinely
nonlinear?

Method, four independent legs that must agree:

1. Reference implementation. A pure-Python SHA-256 whose
   compression exposes every schedule word and every
   post-round state. It is verified against hashlib on
   random messages and on full 80-byte headers (SHA-256d)
   before any dependency claim is read from it.

2. Sound influence tracking. Every bit of every schedule
   word and state word carries a 32-bit mask of the nonce
   bits that may influence it. Linear ops (rotate, shift,
   XOR, AND, OR) propagate masks per bit (union). Addition
   propagates the carry bound: sum bit j may depend on
   operand bits 0..j of every addend. This is a sound
   over-approximation of "may depend" and is exact about
   independence: a zero mask is a proof of independence.

3. Functional classification by sampling. For fixed
   templates, each schedule word (as the nonce varies)
   and each state word after each round is classified:
     IND    constant as the nonce varies;
     AFF    w(n) == w(n_ref) + (n - n_ref) mod 2^32
            (integer-affine with slope exactly 1);
     LIN    GF(2)-affine in the nonce bits;
     NONLIN none of the above.
   For schedule words the decisive test for Y-065 is
   delta-linearity: D(n) = W(n) - W(0) mod 2^32 must be
   GF(2)-linear in n for a decomposition W = C + L(n)
   (integer add, L GF(2)-linear, C template-only) to
   exist, because setting n = 0 forces C = W(0) and
   hence L = D. The tool tests D-linearity directly.

4. z3. The load-bearing positive claims (round-3 state
   affinity; W18 and W19 delta decompositions) are
   proven by bit-vector UNSAT over symbolic template
   words. The load-bearing negative claim (W20's delta
   is not GF(2)-linear) is disproven by a z3 SAT model
   whose concrete values are then re-verified in the
   reference implementation.

Indexing: rounds r = 0..63 consume W[r]. S_t is the
state after t rounds (S_0 is the block-2 initial state,
the midstate). Block 2 of a Bitcoin header: W0 = merkle
tail, W1 = timestamp, W2 = nBits, W3 = nonce, W4..W14 =
0, W15 = 0x280 (640-bit length padding).

Run with the lab z3 venv python so leg 4 executes:
  .local/z3venv/bin/python nonce_dependency.py
Without z3, legs 1 to 3 still run and leg 4 reports
itself skipped (the EXP-012 discipline).

Outputs: analysis/exp016_dependency_results.json and
proofs/exp016_z3_results.json relative to the phase6
directory, plus a printed summary.
"""

import hashlib
import json
import os
import random
import struct
import sys

M32 = 0xFFFFFFFF
HERE = os.path.dirname(os.path.abspath(__file__))
PHASE6 = os.path.dirname(HERE)

K = [
    0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5,
    0x3956c25b, 0x59f111f1, 0x923f82a4, 0xab1c5ed5,
    0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3,
    0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174,
    0xe49b69c1, 0xefbe4786, 0x0fc19dc6, 0x240ca1cc,
    0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da,
    0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7,
    0xc6e00bf3, 0xd5a79147, 0x06ca6351, 0x14292967,
    0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13,
    0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85,
    0xa2bfe8a1, 0xa81a664b, 0xc24b8b70, 0xc76c51a3,
    0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070,
    0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5,
    0x391c0cb3, 0x4ed8aa4a, 0x5b9cca4f, 0x682e6ff3,
    0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208,
    0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2,
]
H0 = [
    0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a,
    0x510e527f, 0x9b05688c, 0x1f83d9ab, 0x5be0cd19,
]


def rotr(x, n):
    return ((x >> n) | (x << (32 - n))) & M32


def compress(state, block_words):
    """One SHA-256 compression. Returns (schedule, states)
    with states[t] the state after t rounds."""
    W = list(block_words[:16])
    for t in range(16, 64):
        s0 = rotr(W[t - 15], 7) ^ rotr(W[t - 15], 18) ^ (W[t - 15] >> 3)
        s1 = rotr(W[t - 2], 17) ^ rotr(W[t - 2], 19) ^ (W[t - 2] >> 10)
        W.append((W[t - 16] + s0 + W[t - 7] + s1) & M32)
    a, b, c, d, e, f, g, h = state
    states = [tuple(state)]
    for t in range(64):
        S1 = rotr(e, 6) ^ rotr(e, 11) ^ rotr(e, 25)
        Ch = (e & f) ^ ((~e & M32) & g)
        T1 = (h + S1 + Ch + K[t] + W[t]) & M32
        S0 = rotr(a, 2) ^ rotr(a, 13) ^ rotr(a, 22)
        Maj = (a & b) ^ (a & c) ^ (b & c)
        T2 = (S0 + Maj) & M32
        a, b, c, d, e, f, g, h = (
            (T1 + T2) & M32, a, b, c, (d + T1) & M32, e, f, g)
        states.append((a, b, c, d, e, f, g, h))
    out = tuple((state[i] + (a, b, c, d, e, f, g, h)[i]) & M32
                for i in range(8))
    return W, states, out


def sha256_ref(msg):
    """Full SHA-256 via the reference compression."""
    ml = len(msg) * 8
    msg = msg + b"\x80"
    while len(msg) % 64 != 56:
        msg += b"\x00"
    msg += struct.pack(">Q", ml)
    state = list(H0)
    for off in range(0, len(msg), 64):
        words = list(struct.unpack(">16I", msg[off:off + 64]))
        _, _, out = compress(state, words)
        state = list(out)
    return b"".join(struct.pack(">I", w) for w in state)


def block2_words(header_tail16, nonce):
    """Block-2 message words for an 80-byte header: the
    caller passes header bytes 64..79 (16 bytes, big-endian
    word order as stored); nonce replaces the last word."""
    words = list(struct.unpack("<4I", header_tail16))
    # header words are stored little-endian per field for
    # timestamp/nBits/nonce but the merkle tail is raw hash
    # bytes; SHA-256 reads big-endian words of the byte
    # stream, which is exactly struct '>4I' of the bytes.
    words = list(struct.unpack(">4I", header_tail16))
    words[3] = nonce
    return words + [0] * 11 + [0x280]


def random_template(rng):
    """A random header: returns (block1_words, tail16)."""
    hdr = bytes(rng.getrandbits(8) for _ in range(80))
    b1 = list(struct.unpack(">16I", hdr[:64]))
    return b1, hdr[64:80]


# ----------------------------------------------------------------
# Leg 2: influence masks. A word is a list of 32 masks;
# masks[j] has bit i set iff nonce bit i may influence bit j.
# ----------------------------------------------------------------

def m_const():
    return [0] * 32


def m_nonce():
    return [1 << j for j in range(32)]


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
    out = [0] * 32
    prefixes = []
    for w in ws:
        p = [0] * 32
        acc = 0
        for j in range(32):
            acc |= w[j]
            p[j] = acc
        prefixes.append(p)
    for j in range(32):
        m = 0
        for p in prefixes:
            m |= p[j]
        out[j] = m
    return out


def influence_run():
    """Symbolic block-2 run over masks. Block-1 state is
    nonce-independent; W3 is the nonce."""
    W = [m_const() for _ in range(64)]
    W[3] = m_nonce()
    for t in range(16, 64):
        s0 = m_xor(m_rotr(W[t - 15], 7), m_rotr(W[t - 15], 18),
                   m_shr(W[t - 15], 3))
        s1 = m_xor(m_rotr(W[t - 2], 17), m_rotr(W[t - 2], 19),
                   m_shr(W[t - 2], 10))
        W[t] = m_add(W[t - 16], s0, W[t - 7], s1)
    st = [m_const() for _ in range(8)]
    states = [[list(w) for w in st]]
    for t in range(64):
        a, b, c, d, e, f, g, h = st
        S1 = m_xor(m_rotr(e, 6), m_rotr(e, 11), m_rotr(e, 25))
        Ch = m_xor(e, f, g)  # union is the sound mask for AND/XOR mix
        T1 = m_add(h, S1, Ch, m_const(), W[t])
        S0 = m_xor(m_rotr(a, 2), m_rotr(a, 13), m_rotr(a, 22))
        Maj = m_xor(a, b, c)
        T2 = m_add(S0, Maj)
        st = [m_add(T1, T2), a, b, c, m_add(d, T1), e, f, g]
        states.append(st)
    return W, states


def mask_full(w):
    return sum(1 for m in w if m == M32)


def mask_union_bits(w):
    u = 0
    for m in w:
        u |= m
    return bin(u).count("1")


# ----------------------------------------------------------------
# Leg 3: functional classification by sampling
# ----------------------------------------------------------------

def classify(values, ref_nonce, ref_val, nonce_of):
    """values: dict nonce -> word value. Classify the map."""
    vals = set(values.values())
    if len(vals) == 1:
        return "IND"
    aff = all(v == (ref_val + (n - ref_nonce)) & M32
              for n, v in values.items())
    if aff:
        return "AFF"
    items = list(values.items())
    lin = True
    rng = random.Random(1234)
    for _ in range(60):
        n1 = items[rng.randrange(len(items))][0]
        n2 = items[rng.randrange(len(items))][0]
        n3 = n1 ^ n2 ^ ref_nonce
        if n3 not in values:
            lin = False
            break
        if values[n3] != (values[n1] ^ values[n2] ^ ref_val):
            lin = False
            break
    return "LIN" if lin else "NONLIN"


def delta_linearity(Wfun, rng, trials=300):
    """Test D(n) = W(n) - W(0) for GF(2)-linearity.
    Returns the fraction of random pairs violating
    D(n1 ^ n2) == D(n1) ^ D(n2)."""
    cache = {0: Wfun(0)}
    def D(n):
        if n not in cache:
            cache[n] = (Wfun(n) - cache[0]) & M32
        return cache[n]
    bad = 0
    for _ in range(trials):
        n1 = rng.getrandbits(32)
        n2 = rng.getrandbits(32)
        if D(n1 ^ n2) != (D(n1) ^ D(n2)):
            bad += 1
    return bad / trials


# ----------------------------------------------------------------
# Leg 4: z3 proofs
# ----------------------------------------------------------------

def z3_checks():
    try:
        import z3
    except ImportError:
        return {"status": "skipped: z3 not importable"}
    out = {"status": "ran"}

    def rotr(x, n):
        return z3.RotateRight(x, n)

    # Symbolic prefix state (entering round 3) and nonce.
    pre = [z3.BitVec(f"s{i}", 32) for i in range(8)]

    def round3(state, W0, W1, W2, n):
        # rounds 0,1,2 with constant-per-template words are
        # folded into `pre` by the caller; here only round 3.
        a, b, c, d, e, f, g, h = state
        S1 = rotr(e, 6) ^ rotr(e, 11) ^ rotr(e, 25)
        Ch = (e & f) ^ (~e & g)
        T1 = h + S1 + Ch + K[3] + n
        S0 = rotr(a, 2) ^ rotr(a, 13) ^ rotr(a, 22)
        Maj = (a & b) ^ (a & c) ^ (b & c)
        T2 = S0 + Maj
        return [T1 + T2, a, b, c, d + T1, e, f, g]

    n1 = z3.BitVec("n1", 32)
    n2 = z3.BitVec("n2", 32)
    st1 = round3(pre, None, None, None, n1)
    st2 = round3(pre, None, None, None, n2)
    # a after round 3 minus nonce is nonce-independent?
    s = z3.Solver()
    s.add(st1[0] - n1 != st2[0] - n2)
    out["round3_a_affine_unsat"] = str(s.check()) == "unsat"
    s = z3.Solver()
    s.add(st1[4] - n1 != st2[4] - n2)
    out["round3_e_affine_unsat"] = str(s.check()) == "unsat"

    # Schedule words with symbolic template words.
    W = [z3.BitVec(f"W{i}", 32) for i in range(16)]

    def sched(Words, n):
        Wfull = list(Words)
        Wfull[3] = n
        for t in range(16, 21):
            s0 = (rotr(Wfull[t - 15], 7) ^ rotr(Wfull[t - 15], 18)
                  ^ z3.LShR(Wfull[t - 15], 3))
            s1 = (rotr(Wfull[t - 2], 17) ^ rotr(Wfull[t - 2], 19)
                  ^ z3.LShR(Wfull[t - 2], 10))
            Wfull.append(Wfull[t - 16] + s0 + Wfull[t - 7] + s1)
        return Wfull

    W1v = sched(W, n1)
    W2v = sched(W, n2)
    # W18 delta: W18(n) - s0(n) nonce-independent?
    def s0z(x):
        return rotr(x, 7) ^ rotr(x, 18) ^ z3.LShR(x, 3)
    s = z3.Solver()
    s.add(W1v[18] - s0z(n1) != W2v[18] - s0z(n2))
    out["W18_delta_form_unsat"] = str(s.check()) == "unsat"
    # W19 delta: W19(n) - n nonce-independent?
    s = z3.Solver()
    s.add(W1v[19] - n1 != W2v[19] - n2)
    out["W19_delta_form_unsat"] = str(s.check()) == "unsat"
    # W20 delta GF(2)-linearity: find a counterexample.
    n0 = z3.BitVecVal(0, 32)
    W0v = sched(W, n0)
    W12 = sched(W, n1 ^ n2)
    D1 = W1v[20] - W0v[20]
    D2 = W2v[20] - W0v[20]
    D12 = W12[20] - W0v[20]
    s = z3.Solver()
    s.add(D12 != (D1 ^ D2))
    res = s.check()
    out["W20_delta_linear_counterexample_sat"] = str(res) == "sat"
    if str(res) == "sat":
        m = s.model()
        model = {str(d): m[d].as_long() for d in m.decls()}
        out["W20_counterexample_model"] = model
    return out


# ----------------------------------------------------------------
# Main
# ----------------------------------------------------------------

def main():
    rng = random.Random(20261114)
    results = {"experiment": "EXP-016 nonce dependency derivation"}

    # Leg 1: reference verification against hashlib.
    ok = True
    for _ in range(50):
        msg = bytes(rng.getrandbits(8) for _ in range(rng.randrange(200)))
        if sha256_ref(msg) != hashlib.sha256(msg).digest():
            ok = False
    hdr_ok = True
    for _ in range(20):
        hdr = bytes(rng.getrandbits(8) for _ in range(80))
        inner = sha256_ref(hdr)
        if inner != hashlib.sha256(hdr).digest():
            hdr_ok = False
        if sha256_ref(inner) != hashlib.sha256(inner).digest():
            hdr_ok = False
    results["leg1_reference_vs_hashlib"] = {
        "random_messages": ok, "header_inner_outer": hdr_ok}

    # Leg 2: influence masks.
    Wm, Sm = influence_run()
    sched_tab = {}
    for t in range(16, 64):
        sched_tab[t] = {
            "union_nonce_bits": mask_union_bits(Wm[t]),
            "bits_fully_dependent": mask_full(Wm[t]),
        }
    state_tab = {}
    for t in range(0, 17):
        state_tab[t] = [{
            "union_nonce_bits": mask_union_bits(w),
            "bits_fully_dependent": mask_full(w),
        } for w in Sm[t]]
    first_full_sched = next(
        (t for t in range(16, 64) if mask_full(Wm[t]) == 32), None)
    first_full_state = next(
        (t for t in range(65)
         if all(mask_full(w) == 32 for w in Sm[t])), None)
    results["leg2_influence"] = {
        "schedule": sched_tab, "state": state_tab,
        "first_schedule_word_all_bits_full": first_full_sched,
        "first_state_all_words_all_bits_full": first_full_state,
    }

    # Leg 3: classification. Three random templates.
    templates = []
    for _ in range(3):
        b1, tail = random_template(rng)
        _, _, mid = compress(list(H0), b1)
        templates.append((list(mid), tail))
    ref_nonce = 0x12345678
    nonces = [ref_nonce] + [rng.getrandbits(32) for _ in range(48)]
    # add XOR-closed partners for the LIN test
    extra = []
    for i in range(0, 20, 2):
        extra.append(nonces[i] ^ nonces[i + 1] ^ ref_nonce)
    nonces = list(dict.fromkeys(nonces + extra))
    classes_state = {}
    classes_sched = {}
    for mid, tail in templates:
        runs = {}
        for n in nonces:
            Wc, states, _ = compress(mid, block2_words(tail, n))
            runs[n] = (Wc, states)
        for t in range(0, 13):
            for wi in range(8):
                vals = {n: runs[n][1][t][wi] for n in nonces}
                cl = classify(vals, ref_nonce,
                              runs[ref_nonce][1][t][wi], None)
                key = f"S{t}.w{wi}"
                classes_state.setdefault(key, []).append(cl)
        for t in range(16, 26):
            vals = {n: runs[n][0][t] for n in nonces}
            cl = classify(vals, ref_nonce, runs[ref_nonce][0][t], None)
            classes_sched.setdefault(f"W{t}", []).append(cl)
    def consensus(d):
        return {k: (v[0] if len(set(v)) == 1 else v)
                for k, v in d.items()}
    results["leg3_state_classes"] = consensus(classes_state)
    results["leg3_schedule_classes"] = consensus(classes_sched)

    # Delta linearity for schedule words (Y-065's question).
    mid, tail = templates[0]
    dl = {}
    for t in range(16, 26):
        def Wfun(n, t=t):
            Wc, _, _ = compress(mid, block2_words(tail, n))
            return Wc[t]
        dl[f"W{t}"] = round(delta_linearity(Wfun, rng), 3)
    results["leg3_delta_linearity_violation_rate"] = dl

    # Empirical avalanche signature at S_4 for words a, e:
    # flip nonce bit i, record flip probability per bit.
    samples = 40
    flip_prob = {}
    mid, tail = templates[0]
    base_n = rng.getrandbits(32)
    _, base_states, _ = compress(mid, block2_words(tail, base_n))
    for wi, name in ((0, "a"), (4, "e")):
        mat = [[0.0] * 32 for _ in range(32)]
        for i in range(32):
            cnt = [0] * 32
            for _ in range(samples):
                n = rng.getrandbits(32)
                _, s0_, _ = compress(mid, block2_words(tail, n))
                _, s1_, _ = compress(
                    mid, block2_words(tail, n ^ (1 << i)))
                diff = s0_[4][wi] ^ s1_[4][wi]
                for j in range(32):
                    if (diff >> j) & 1:
                        cnt[j] += 1
            for j in range(32):
                mat[i][j] = cnt[j] / samples
        flip_prob[name] = {
            "diag_mean": round(sum(mat[i][i] for i in range(32)) / 32, 3),
            "below_diag_max": max(
                (mat[i][j] for i in range(32) for j in range(i)),
                default=0.0),
            "above_diag_mean": round(
                sum(mat[i][j] for i in range(32)
                    for j in range(i + 1, 32)) / (32 * 31 / 2), 3),
        }
    results["leg3_S4_flip_signature"] = flip_prob

    # Empirical completeness: first S_t where every state
    # bit flips for every nonce bit, over samples.
    emp_full = None
    ever = [ [ [False]*32 for _ in range(8)] for _ in range(17)]
    for i in range(32):
        for _ in range(12):
            n = rng.getrandbits(32)
            _, sa, _ = compress(mid, block2_words(tail, n))
            _, sb, _ = compress(mid, block2_words(tail, n ^ (1 << i)))
            for t in range(17):
                for wi in range(8):
                    diff = sa[t][wi] ^ sb[t][wi]
                    for j in range(32):
                        if (diff >> j) & 1:
                            ever[t][wi][j] = True
    for t in range(17):
        if all(all(ever[t][wi]) for wi in range(8)):
            emp_full = t
            break
    results["leg3_empirical_first_full_state"] = emp_full

    # Leg 4: z3.
    results["leg4_z3"] = z3_checks()

    # Numeric re-verification of the z3 W20 counterexample.
    z3res = results["leg4_z3"]
    if z3res.get("W20_delta_linear_counterexample_sat"):
        model = z3res["W20_counterexample_model"]
        Wvals = [model.get(f"W{i}", 0) for i in range(16)]
        n1 = model.get("n1", 0)
        n2 = model.get("n2", 0)
        def W20(n):
            words = list(Wvals)
            words[3] = n
            W = list(words)
            for t in range(16, 21):
                s0 = rotr(W[t-15], 7) ^ rotr(W[t-15], 18) ^ (W[t-15] >> 3)
                s1 = rotr(W[t-2], 17) ^ rotr(W[t-2], 19) ^ (W[t-2] >> 10)
                W.append((W[t-16] + s0 + W[t-7] + s1) & M32)
            return W[20]
        D = lambda n: (W20(n) - W20(0)) & M32
        results["leg4_W20_counterexample_numeric_check"] = {
            "n1": n1, "n2": n2,
            "D_n1_xor_n2": D(n1 ^ n2),
            "D_n1_xor_D_n2": D(n1) ^ D(n2),
            "violates": D(n1 ^ n2) != (D(n1) ^ D(n2)),
        }

    os.makedirs(os.path.join(PHASE6, "analysis"), exist_ok=True)
    os.makedirs(os.path.join(PHASE6, "proofs"), exist_ok=True)
    with open(os.path.join(PHASE6, "analysis",
                           "exp016_dependency_results.json"), "w") as fh:
        json.dump(results, fh, indent=2)
    with open(os.path.join(PHASE6, "proofs",
                           "exp016_z3_results.json"), "w") as fh:
        json.dump(results["leg4_z3"], fh, indent=2)

    # Printed summary of the load-bearing rows.
    print("leg1 hashlib agreement:", results["leg1_reference_vs_hashlib"])
    print("first schedule word, all bits fully dependent:",
          first_full_sched)
    print("first state (sound masks), all words all bits full:",
          first_full_state)
    print("first state (empirical flips), complete:", emp_full)
    for t in range(0, 10):
        row = [results["leg3_state_classes"][f"S{t}.w{wi}"]
               for wi in range(8)]
        print(f"state classes S{t}:", row)
    for t in range(16, 26):
        print(f"W{t}: class", results["leg3_schedule_classes"][f"W{t}"],
              "delta-linearity violation rate", dl[f"W{t}"])
    print("S4 flip signature:", flip_prob)
    print("z3:", {k: v for k, v in z3res.items()
                  if k != "W20_counterexample_model"})
    print("W20 numeric check:",
          results.get("leg4_W20_counterexample_numeric_check"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
