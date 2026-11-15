#!/usr/bin/env python3
"""EXP-033 common machinery: reference SHA-256 with exposed
rounds, and a word-level DAG for composed rounds with an exact
evaluator.

The DAG op set and cost model are the EXP-020 census model:
  ADD (binary, mod 2^32)          cost 1
  LUT (VPTERNLOGD, imm over 3     cost 1
       operand words, bit index
       (a<<2)|(b<<1)|c)
  ROTR k                          cost 1
  SHR k                           cost 1
  SHL k                           cost 1
  INPUT / CONST                   cost 0
Under this model the incumbent round costs 17 ops and the
incumbent schedule word costs 11 ops (joint 28, EXP-020), and
two composed rounds plus two schedule words cost 56.

Ch imm is 0xCA, Maj imm is 0xE8, XOR3 imm is 0x96 under the
bit-index convention above (EXP-012 values, reproduced here
by construction and checked in the tests).
"""

import hashlib
import struct

M32 = 0xFFFFFFFF

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


def lut_eval(imm, a, b, c):
    """Per-bit 3-input LUT: out bit j uses index
    (a_j<<2)|(b_j<<1)|c_j into imm."""
    out = 0
    for j in range(32):
        idx = (((a >> j) & 1) << 2) | (((b >> j) & 1) << 1) | ((c >> j) & 1)
        out |= ((imm >> idx) & 1) << j
    return out


# LUT immediates under the convention above.
IMM_XOR = 0x96   # odd parity of (a, b, c); also a^b with c=0
IMM_CH = 0xCA    # (a, b, c) -> b if a else c
IMM_MAJ = 0xE8   # majority of (a, b, c)
IMM_AND = 0xC0   # a & b (c ignored: pattern over idx)
IMM_OR = 0xFC    # a | b (c ignored)


def compress(state, block_words):
    """Reference compression. Returns (W, states, out) with
    states[t] the state after t rounds."""
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


# ----------------------------------------------------------------
# Word-level DAG (hash-consed), for the e-graph search.
# A node is a tuple; node ids are indices into Dag.nodes.
#   ('in', name) ('const', v)
#   ('add', x, y) ('rotr', k, x) ('shr', k, x) ('shl', k, x)
#   ('lut', imm, x, y, z)
# ----------------------------------------------------------------

OP_COST = {"add": 1, "rotr": 1, "shr": 1, "shl": 1, "lut": 1,
           "in": 0, "const": 0}


class Dag:
    def __init__(self):
        self.nodes = []
        self.ids = {}

    def node(self, tup):
        if tup in self.ids:
            return self.ids[tup]
        i = len(self.nodes)
        self.nodes.append(tup)
        self.ids[tup] = i
        return i

    def inp(self, name):
        return self.node(("in", name))

    def const(self, v):
        return self.node(("const", v & M32))

    def add(self, x, y):
        if x > y:
            x, y = y, x
        return self.node(("add", x, y))

    def addn(self, xs):
        xs = list(xs)
        acc = xs[0]
        for x in xs[1:]:
            acc = self.add(acc, x)
        return acc

    def rotr(self, k, x):
        k %= 32
        if k == 0:
            return x
        return self.node(("rotr", k, x))

    def shr(self, k, x):
        return self.node(("shr", k, x))

    def lut(self, imm, x, y, z):
        return self.node(("lut", imm, x, y, z))

    def xor3(self, x, y, z):
        return self.lut(IMM_XOR, x, y, z)

    def sigma0(self, x):
        return self.xor3(self.rotr(2, x), self.rotr(13, x),
                         self.rotr(22, x))

    def sigma1(self, x):
        return self.xor3(self.rotr(6, x), self.rotr(11, x),
                         self.rotr(25, x))

    def s0(self, x):
        return self.xor3(self.rotr(7, x), self.rotr(18, x),
                         self.shr(3, x))

    def s1(self, x):
        return self.xor3(self.rotr(17, x), self.rotr(19, x),
                         self.shr(10, x))

    def ch(self, e, f, g):
        return self.lut(IMM_CH, e, f, g)

    def maj(self, a, b, c):
        return self.lut(IMM_MAJ, a, b, c)


def build_two_rounds(t0=20):
    """Build the DAG for two composed rounds (rounds t0 and
    t0+1) plus the two schedule words they consume.
    Inputs: state words a..h and schedule atoms
    W{t0-16}..W{t0-1}. Returns (dag, roots) where roots maps
    'state' to the 8 output ids, 'Wt' and 'Wt1' to the
    schedule word ids, and 'inputs' to the input name list."""
    d = Dag()
    names = ["a", "b", "c", "d", "e", "f", "g", "h"]
    st = {n: d.inp(n) for n in names}
    watoms = {}
    for t in range(t0 - 16, t0):
        watoms[t] = d.inp(f"W{t}")
    zero = d.const(0)

    def sched_word(t):
        s0 = d.s0(watoms[t - 15])
        s1 = d.s1(watoms[t - 2])
        return d.addn([watoms[t - 16], s0, watoms[t - 7], s1])

    Wt = sched_word(t0)
    # W{t0+1} needs W{t0} as an atom of its own recurrence.
    watoms[t0] = Wt
    Wt1 = sched_word(t0 + 1)
    watoms[t0 + 1] = Wt1

    def one_round(st, W, kt):
        S1 = d.sigma1(st["e"])
        Ch = d.ch(st["e"], st["f"], st["g"])
        KW = d.add(W, d.const(K[kt]))
        T1 = d.addn([st["h"], S1, Ch, KW])
        S0 = d.sigma0(st["a"])
        Maj = d.maj(st["a"], st["b"], st["c"])
        T2 = d.add(S0, Maj)
        return {
            "a": d.add(T1, T2), "b": st["a"], "c": st["b"],
            "d": st["c"], "e": d.add(st["d"], T1), "f": st["e"],
            "g": st["f"], "h": st["g"],
        }, T1

    st1, _ = one_round(st, Wt, t0)
    st2, _ = one_round(st1, Wt1, t0 + 1)
    roots = {
        "state": [st2[n] for n in names],
        "Wt": Wt, "Wt1": Wt1,
        "mid_state": [st1[n] for n in names],
        "inputs": names + [f"W{t}" for t in range(t0 - 16, t0)],
        "t0": t0,
    }
    return d, roots


def dag_eval(dag, roots_state, env):
    """Evaluate DAG nodes under env {input name: word}."""
    vals = [0] * len(dag.nodes)
    for i, nd in enumerate(dag.nodes):
        op = nd[0]
        if op == "in":
            vals[i] = env[nd[1]] & M32
        elif op == "const":
            vals[i] = nd[1]
        elif op == "add":
            vals[i] = (vals[nd[1]] + vals[nd[2]]) & M32
        elif op == "rotr":
            vals[i] = rotr(vals[nd[2]], nd[1])
        elif op == "shr":
            vals[i] = vals[nd[2]] >> nd[1]
        elif op == "shl":
            vals[i] = (vals[nd[2]] << nd[1]) & M32
        elif op == "lut":
            vals[i] = lut_eval(nd[1], vals[nd[2]], vals[nd[3]],
                               vals[nd[4]])
        else:
            raise ValueError(op)
    return [vals[i] for i in roots_state]


def node_children(nd):
    op = nd[0]
    if op == "add":
        return (nd[1], nd[2])
    if op in ("rotr", "shr", "shl"):
        return (nd[2],)
    if op == "lut":
        return (nd[2], nd[3], nd[4])
    return ()


def dag_cost(dag, root_ids):
    """Exact DAG cost: sum of op costs over distinct nodes
    reachable from the roots."""
    seen = set()
    stack = list(root_ids)
    while stack:
        i = stack.pop()
        if i in seen:
            continue
        seen.add(i)
        stack.extend(node_children(dag.nodes[i]))
    return sum(OP_COST[dag.nodes[i][0]] for i in seen), len(seen)
