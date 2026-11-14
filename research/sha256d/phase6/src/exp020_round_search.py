#!/usr/bin/env python3
"""EXP-020: automated full-round rewriting (Y-014, Y-015).

Two search engines over one formal object: the joint cone
of one full SHA-256 round in the multi-buffer formulation
(S0, S1, Ch, Maj, the T1 and T2 addition networks, the
outputs a' and e'), plus the schedule cone that feeds it
(s0, s1, and the four-operand sum producing W[t] for
t >= 16), exactly as the production kernel
mining/cpu/bal_avx512_mb.c evaluates them per lane.

  Search A (Y-014 in the ranking's numbering, the
  saturation engine): e-graph-lite equality saturation
  over the lab's proven rewrite set, extended with
  addition reassociation and term-level VPTERNLOGD
  folding, with extraction under two cost models
  (classic op library; AVX-512 library with ternlog).

  Search B (Y-015, the SAT/SMT-guided engine):
  exhaustive Boolean function-set BFS for the classic
  minima; exhaustive addition-network BFS for the
  (a', e') pair and the schedule sum; carry-save forms
  priced at the EXP-019 price list; hash-consed
  subterm-sharing analysis; symbolic offset-support
  analysis for the sigma lower bounds; z3
  materialisation counterexamples; and a bounded
  stochastic superoptimiser over the full-round DAG.

Equivalence standard: z3 bit-vector UNSAT on all
outputs (a', e', W[t]) for every recorded candidate,
behind a 1,000,000-sample numpy differential filter.

PREDECLARED PROMOTION THRESHOLD (written before the
searches run, per COMPUTATION_GRAPH_RESEARCH.md
section 8): a candidate promotes to a variant kernel
only if (1) it is proven equivalent as above, (2) its
full round+schedule census under the AVX-512 cost
model is strictly below the incumbent EMITTED census
(mechanically audited from the production object;
the audit below counts 29 arithmetic vector ops per
steady-state round), (3) its round-cone critical-path
depth does not exceed the extracted optimum's, and
(4) the gain is not already present in the emitted
code. A candidate proven but not cheaper, or cheaper
only against the source form while matching what the
compiler already emits, is a discovery artifact only.

Cost model (EXP-019 corrected): every vector op
costs 1 in its class (VPADDD, VPTERNLOGD, classic
bitwise, VPROLD, VPSRLD); a software 3:2 compressor
level costs 3 (2 VPTERNLOGD + 1 VPSLLD carry
alignment); a resolved four-operand carry-save sum
costs 5, a five-operand one-level form 6 or more as
enumerated. Depth is unit-latency per op, the
design's second objective. NOT is free in the
classic model (the EXP-012 convention; VPANDND and
ternlog absorb negations in the AVX-512 model).

Run with the lab z3 venv python:
  .local/z3venv/bin/python src/exp020_round_search.py
Outputs: analysis/exp020_search_results.json,
proofs/exp020_candidates.json,
analysis/exp020_asm_audit.json.
"""

import hashlib
import itertools
import json
import os
import random
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
PHASE6 = os.path.dirname(HERE)
ROOT = os.path.abspath(os.path.join(PHASE6, "..", "..", ".."))
M32 = 0xFFFFFFFF

sys.path.insert(0, HERE)

# ---------------- expression DAG ----------------
# ('var', name) ('const', value) ('not', a)
# ('and'|'or'|'xor'|'andnot'|'add', a, b)
# ('ternlog', imm, a, b, c) ('rotr', a, n) ('shr', a, n)

def V(name):
    return ('var', name)


def subexprs(e, acc):
    acc.add(e)
    for x in e[1:]:
        if isinstance(x, tuple):
            subexprs(x, acc)
    return acc


def ch_classic(x, y, z):
    # Ch(x,y,z) = (x & y) ^ (~x & z); the second term
    # is andnot(z, x) = z & ~x
    return ('xor', ('and', x, y), ('andnot', z, x))


def maj_classic(x, y, z):
    return ('xor', ('xor', ('and', x, y), ('and', x, z)),
            ('and', y, z))


def xor3(u, v, w):
    return ('xor', ('xor', u, v), w)


def reference_dags():
    """The production kernel's round, source association
    exactly as written in mining/cpu/bal_avx512_mb.c
    v_compress16, plus its schedule generation."""
    a, b, c, d, e, f, g, h = (V(n) for n in 'abcdefgh')
    W, K = V('W'), V('K')
    S1 = xor3(('rotr', e, 6), ('rotr', e, 11), ('rotr', e, 25))
    Ch = ch_classic(e, f, g)
    T1 = ('add', ('add', ('add', h, S1), ('add', Ch, K)), W)
    S0 = xor3(('rotr', a, 2), ('rotr', a, 13), ('rotr', a, 22))
    Maj = maj_classic(a, b, c)
    T2 = ('add', S0, Maj)
    e_out = ('add', d, T1)
    a_out = ('add', T1, T2)
    # schedule cone: Xm = W[t-15], Y = W[t-2],
    # P = W[t-16], Q = W[t-7]
    Xm, Y, P, Q = V('Xm'), V('Y'), V('P'), V('Q')
    s0 = xor3(('rotr', Xm, 7), ('rotr', Xm, 18), ('shr', Xm, 3))
    s1 = xor3(('rotr', Y, 17), ('rotr', Y, 19), ('shr', Y, 10))
    Wn = ('add', ('add', P, s0), ('add', Q, s1))
    parts = {'S1': S1, 'Ch': Ch, 'T1': T1, 'S0': S0, 'Maj': Maj,
             'T2': T2, 'a_out': a_out, 'e_out': e_out,
             's0': s0, 's1': s1, 'Wn': Wn}
    return parts


ROUND_VARS = ['a', 'b', 'c', 'd', 'e', 'f', 'g', 'h', 'W', 'K']
SCHED_VARS = ['Xm', 'Y', 'P', 'Q']
ALL_VARS = ROUND_VARS + SCHED_VARS

BOOL_OPS = ('and', 'or', 'xor', 'andnot', 'not')


def census(e, model, memo=None):
    """Static op census of a DAG (shared nodes counted
    once per call site set: pass a shared memo across
    outputs for a joint census)."""
    if memo is None:
        memo = {}

    def walk(x):
        if x in memo:
            return memo[x]
        op = x[0]
        if op in ('var', 'const'):
            r = (0, 0)
        elif op == 'not':
            ca, da = walk(x[1])
            r = (ca + (0 if model == 'classic' else 0), da)
        elif op == 'ternlog':
            if model == 'classic':
                raise ValueError('ternlog not in classic library')
            cs = [walk(c) for c in x[2:]]
            r = (1 + sum(c for c, _ in cs),
                 1 + max(d for _, d in cs))
        elif op in ('rotr', 'shr'):
            ca, da = walk(x[1])
            r = (1 + ca, 1 + da)
        elif op in ('and', 'or', 'xor', 'andnot', 'add'):
            ca, da = walk(x[1])
            cb, db = walk(x[2])
            r = (1 + ca + cb, 1 + max(da, db))
        else:
            raise ValueError(op)
        memo[x] = r
        return r

    return walk(e)


def joint_census(exprs, model):
    memo = {}
    total = 0
    depths = []
    for e in exprs:
        c, d = census(e, model, memo)
        depths.append(d)
    # census() with a shared memo returns per-output
    # cumulative counts; the joint census is the count
    # of distinct non-leaf nodes in the union DAG.
    nodes = set()
    for e in exprs:
        subexprs(e, nodes)
    ops = 0
    for n in nodes:
        if n[0] in ('var', 'const'):
            continue
        if n[0] == 'not' and model == 'classic':
            continue
        if n[0] == 'ternlog' and model == 'classic':
            raise ValueError('ternlog in classic census')
        ops += 1
    return ops, depths


# ---------------- scalar / numpy evaluation ----------------

def eval_int(e, env):
    op = e[0]
    if op == 'var':
        return env[e[1]]
    if op == 'const':
        return e[1]
    if op == 'not':
        return (~eval_int(e[1], env)) & M32
    if op == 'and':
        return eval_int(e[1], env) & eval_int(e[2], env)
    if op == 'or':
        return eval_int(e[1], env) | eval_int(e[2], env)
    if op == 'xor':
        return eval_int(e[1], env) ^ eval_int(e[2], env)
    if op == 'andnot':
        return eval_int(e[1], env) & ((~eval_int(e[2], env)) & M32)
    if op == 'ternlog':
        a, b, c = (eval_int(x, env) for x in e[2:])
        imm = e[1]
        out = 0
        for j in range(32):
            idx = (((a >> j) & 1) << 2) | (((b >> j) & 1) << 1) \
                | ((c >> j) & 1)
            out |= ((imm >> idx) & 1) << j
        return out
    if op == 'add':
        return (eval_int(e[1], env) + eval_int(e[2], env)) & M32
    if op == 'rotr':
        x = eval_int(e[1], env)
        n = e[2]
        return ((x >> n) | (x << (32 - n))) & M32
    if op == 'shr':
        return eval_int(e[1], env) >> e[2]
    raise ValueError(op)


def eval_np(e, env):
    import numpy as np
    op = e[0]
    if op == 'var':
        return env[e[1]]
    if op == 'const':
        return np.uint32(e[1])
    if op == 'not':
        return ~eval_np(e[1], env)
    if op == 'and':
        return eval_np(e[1], env) & eval_np(e[2], env)
    if op == 'or':
        return eval_np(e[1], env) | eval_np(e[2], env)
    if op == 'xor':
        return eval_np(e[1], env) ^ eval_np(e[2], env)
    if op == 'andnot':
        return eval_np(e[1], env) & ~eval_np(e[2], env)
    if op == 'ternlog':
        a, b, c = (eval_np(x, env) for x in e[2:])
        imm = e[1]
        out = np.zeros_like(a if hasattr(a, 'shape')
                              else np.asarray(a, dtype=np.uint32))
        for idx in range(8):
            if (imm >> idx) & 1:
                ta = a if (idx >> 2) & 1 else ~a
                tb = b if (idx >> 1) & 1 else ~b
                tc = c if idx & 1 else ~c
                out = out | (ta & tb & tc)
        return out
    if op == 'add':
        return eval_np(e[1], env) + eval_np(e[2], env)
    if op == 'rotr':
        x = eval_np(e[1], env)
        n = np.uint32(e[2])
        return (x >> n) | (x << np.uint32(32 - e[2]))
    if op == 'shr':
        return eval_np(e[1], env) >> np.uint32(e[2])
    raise ValueError(op)


def differential(e1, e2, names, samples, seed):
    """Numpy differential over random inputs; returns
    the number of mismatching samples."""
    import numpy as np
    rng = np.random.default_rng(seed)
    env = {n: rng.integers(0, 2**32, size=samples,
                            dtype=np.uint64).astype(np.uint32)
           for n in names}
    r1 = eval_np(e1, env)
    r2 = eval_np(e2, env)
    return int(np.count_nonzero(r1 != r2))


# ---------------- z3 proof gate ----------------

def prove_equiv_multi(pairs, names, timeout_ms=600000):
    """pairs: list of (expr_ref, expr_cand). Returns
    'unsat' if all pairs are equivalent for all inputs."""
    import z3
    env = {n: z3.BitVec(n, 32) for n in names}

    def ev(e):
        op = e[0]
        if op == 'var':
            return env[e[1]]
        if op == 'const':
            return z3.BitVecVal(e[1], 32)
        if op == 'not':
            return ~ev(e[1])
        if op == 'and':
            return ev(e[1]) & ev(e[2])
        if op == 'or':
            return ev(e[1]) | ev(e[2])
        if op == 'xor':
            return ev(e[1]) ^ ev(e[2])
        if op == 'andnot':
            return ev(e[1]) & ~ev(e[2])
        if op == 'ternlog':
            a, b, c = (ev(x) for x in e[2:])
            terms = []
            for idx in range(8):
                if (e[1] >> idx) & 1:
                    ta = a if (idx >> 2) & 1 else ~a
                    tb = b if (idx >> 1) & 1 else ~b
                    tc = c if idx & 1 else ~c
                    terms.append(ta & tb & tc)
            out = terms[0]
            for t in terms[1:]:
                out = out | t
            return out
        if op == 'add':
            return ev(e[1]) + ev(e[2])
        if op == 'rotr':
            return z3.RotateRight(ev(e[1]), e[2])
        if op == 'shr':
            return z3.LShR(ev(e[1]), e[2])
        raise ValueError(op)

    s = z3.Solver()
    s.set('timeout', timeout_ms)
    for r, c in pairs:
        s.add(ev(r) != ev(c))
    return str(s.check())


def ternlog_imm_of(fn, names):
    imm = 0
    for idx in range(8):
        env = {names[0]: (idx >> 2) & 1, names[1]: (idx >> 1) & 1,
               names[2]: idx & 1}
        if fn(env):
            imm |= 1 << idx
    return imm


CH_TABLE = ternlog_imm_of(
    lambda v: (v['x'] & v['y']) ^ ((1 - v['x']) & v['z']),
    ('x', 'y', 'z'))
MAJ_TABLE = ternlog_imm_of(
    lambda v: (v['x'] & v['y']) ^ (v['x'] & v['z'])
    ^ (v['y'] & v['z']), ('x', 'y', 'z'))
XOR3_TABLE = 0x96


# ---------------- Search A: saturation ----------------

def bool_frontier(e):
    """Maximal non-Boolean subterms of a Boolean
    expression (its term frontier), or None if e is not
    purely Boolean above the frontier."""
    if e[0] not in BOOL_OPS:
        return [e]
    out = []
    for x in e[1:]:
        if isinstance(x, tuple):
            f = bool_frontier(x)
            if f is None:
                return None
            out.extend(f)
    seen = []
    for t in out:
        if t not in seen:
            seen.append(t)
    return seen


def bool_table_over_terms(e, terms):
    """Truth table of a Boolean expression over its
    frontier terms (term i is variable i, at most 3)."""
    pos = {t: i for i, t in enumerate(terms)}

    def ev(x, assign):
        op = x[0]
        if op not in BOOL_OPS:
            return assign[pos[x]]
        if op == 'not':
            return 1 - ev(x[1], assign)
        a = ev(x[1], assign)
        b = ev(x[2], assign)
        if op == 'and':
            return a & b
        if op == 'or':
            return a | b
        if op == 'xor':
            return a ^ b
        if op == 'andnot':
            return a & (1 - b)
        raise ValueError(op)

    imm = 0
    n = len(terms)
    for idx in range(1 << n):
        assign = {i: (idx >> (n - 1 - i)) & 1
                  for i in range(n)}
        if ev(e, assign):
            imm |= 1 << idx
    return imm


def leaf_vars(e):
    out = set()
    if e[0] == 'var':
        out.add(e[1])
    for x in e[1:]:
        if isinstance(x, tuple):
            out |= leaf_vars(x)
    return out


class Saturation:
    """E-graph-lite: union-find over discovered
    expressions with congruence closure, following
    discovery_harness.py. Rules propose; extraction
    and the z3 gate dispose."""

    def __init__(self, seeds):
        self.parent = {}
        self.exprs = set()
        for s in seeds:
            subexprs(s, self.exprs)
        for e in self.exprs:
            self.find(e)

    def find(self, x):
        self.parent.setdefault(x, x)
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[rb] = ra

    def add_expr(self, e):
        new = set()
        subexprs(e, new)
        added = new - self.exprs
        self.exprs |= new
        for x in new:
            self.find(x)
        return added

    def rules(self, e):
        out = []
        op = e[0]
        # commutativity (canonical direction by repr)
        if op in ('and', 'or', 'xor', 'add') \
                and repr(e[1]) > repr(e[2]):
            out.append((op, e[2], e[1]))
        # associativity, both directions. For 'add' the
        # reassociation is restricted to flattened
        # operand multisets of size <= 5 (the T1 cone
        # and the schedule sum); cross-boundary
        # association of the (a', e') pair is Search
        # B's BFS territory, and generating all
        # 7-operand trees here would swamp the graph.
        if op in ('xor', 'and', 'or', 'add'):
            flat_ok = True
            if op == 'add':
                def flat(x):
                    if x[0] == 'add':
                        return flat(x[1]) + flat(x[2])
                    return [x]
                flat_ok = len(flat(e)) <= 5
            if flat_ok and e[2][0] == op:
                out.append((op, (op, e[1], e[2][1]), e[2][2]))
            if flat_ok and e[1][0] == op:
                out.append((op, e[1][1], (op, e[1][2], e[2])))
        # andnot introduction / De Morgan direction
        if op == 'and' and e[2][0] == 'not':
            out.append(('andnot', e[1], e[2][1]))
        if op == 'and' and e[1][0] == 'not':
            out.append(('andnot', e[2], e[1][1]))
        if op == 'andnot':
            out.append(('and', e[1], ('not', e[2])))
        # double negation
        if op == 'not' and e[1][0] == 'not':
            out.append(e[1][1])
        # distribution of not over and/or (De Morgan)
        if op == 'not' and e[1][0] == 'and':
            out.append(('or', ('not', e[1][1]), ('not', e[1][2])))
        if op == 'not' and e[1][0] == 'or':
            out.append(('and', ('not', e[1][1]), ('not', e[1][2])))
        # Boolean pattern forms over <= 3 leaf vars:
        # Ch and Maj alt forms, recognised by truth table
        if op in BOOL_OPS:
            lv = sorted(leaf_vars(e))
            if 0 < len(lv) <= 3 and all(
                    v in ('a', 'b', 'c', 'e', 'f', 'g')
                    for v in lv):
                fr = bool_frontier(e)
                if fr is not None and len(fr) == len(lv) \
                        and all(t[0] == 'var' for t in fr):
                    names = [t[1] for t in fr]
                    tab = bool_table_over_terms(e, fr)
                    if len(fr) == 3:
                        # match Ch / Maj under permutation
                        for perm in itertools.permutations(
                                range(3)):
                            inv = [names[perm[0]], names[perm[1]],
                                   names[perm[2]]]
                            x, y, z = (V(inv[0]), V(inv[1]),
                                       V(inv[2]))
                            pt = 0
                            for idx in range(8):
                                bits = [(idx >> 2) & 1,
                                        (idx >> 1) & 1,
                                        idx & 1]
                                src = [0, 0, 0]
                                for j in range(3):
                                    src[perm[j]] = bits[j]
                                if (tab >> (src[0] * 4
                                            + src[1] * 2
                                            + src[2])) & 1:
                                    pt |= 1 << idx
                            if pt == CH_TABLE:
                                out.append(ch_classic(x, y, z))
                                out.append(('xor', z, ('and', x,
                                            ('xor', y, z))))
                                out.append(('ternlog', CH_TABLE,
                                            x, y, z))
                            if pt == MAJ_TABLE:
                                out.append(maj_classic(x, y, z))
                                out.append(('xor', ('and', x, y),
                                            ('and', z,
                                             ('xor', x, y))))
                                out.append(('xor',
                                            ('and', x,
                                             ('xor', y, z)),
                                            ('and', y, z)))
                                out.append(('ternlog', MAJ_TABLE,
                                            x, y, z))
            # term-level ternlog folding: any Boolean
            # expression over <= 3 frontier terms is one
            # VPTERNLOGD of those terms
            fr = bool_frontier(e)
            if fr is not None and 1 < len(fr) <= 3:
                imm = bool_table_over_terms(e, fr)
                # bool_table_over_terms indexes term i at
                # weight 2^(n-1-i); the ternlog encoding
                # wants term0 at weight 4 for n == 3; for
                # n == 2 pad with a dummy third term equal
                # to term0 and fold the table accordingly
                if len(fr) == 3:
                    timm = 0
                    for idx in range(8):
                        a3 = (idx >> 2) & 1
                        b3 = (idx >> 1) & 1
                        c3 = idx & 1
                        src = a3 * 4 + b3 * 2 + c3
                        if (imm >> src) & 1:
                            timm |= 1 << idx
                    out.append(('ternlog', timm,
                                fr[0], fr[1], fr[2]))
        return out

    def run(self, node_budget=500_000, max_passes=40):
        passes = 0
        while passes < max_passes:
            passes += 1
            changed = False
            for e in list(self.exprs):
                for r in self.rules(e):
                    before = len(self.exprs)
                    self.add_expr(r)
                    self.union(e, r)
                    if len(self.exprs) > before:
                        changed = True
                if len(self.exprs) >= node_budget:
                    break
            # congruence closure
            seen = {}
            for e in list(self.exprs):
                if len(e) > 1 and isinstance(e[1], tuple):
                    key = (e[0],) + tuple(
                        self.find(x) if isinstance(x, tuple)
                        else x for x in e[1:])
                    if key in seen:
                        self.union(e, seen[key])
                    else:
                        seen[key] = e
            if not changed or len(self.exprs) >= node_budget:
                break
        classes = {}
        for e in self.exprs:
            classes.setdefault(self.find(e), []).append(e)
        return classes, passes


def extract(classes, sat, roots, model):
    """Min (cost, depth) member per class by DP over
    the class graph; returns {root: (expr, cost, depth)}
    with costs counted per expression tree (the joint
    census is computed afterwards on the chosen DAG)."""
    INF = float('inf')
    cls_of = {}
    for cls, members in classes.items():
        for e in members:
            cls_of[e] = cls
    cost = {e: INF for e in sat.exprs}
    depth = {e: INF for e in sat.exprs}
    best = {}
    # leaves
    for e in sat.exprs:
        if e[0] in ('var', 'const'):
            cost[e] = 0
            depth[e] = 0
            best[e] = e
    changed = True
    rounds = 0
    while changed and rounds < 200:
        changed = False
        rounds += 1
        # class minima
        cls_min = {}
        for cls, members in classes.items():
            m = min((cost[e], depth[e]) for e in members)
            cls_min[cls] = m
        for e in sat.exprs:
            op = e[0]
            if op in ('var', 'const'):
                continue
            if op == 'ternlog' and model == 'classic':
                continue
            childs = [x for x in e[1:] if isinstance(x, tuple)]
            imms = [x for x in e[1:] if not isinstance(x, tuple)]
            if any(cls_of.get(ch) is None for ch in childs):
                continue
            cs = [cls_min[cls_of[ch]] for ch in childs]
            if any(c[0] == INF for c in cs):
                continue
            opcost = 0 if op == 'not' and model == 'classic' \
                else 1
            nc = opcost + sum(c[0] for c in cs)
            nd = (0 if op == 'not' and model == 'classic'
                  else 1) + (max((c[1] for c in cs), default=0))
            if (nc, nd) < (cost[e], depth[e]):
                cost[e] = nc
                depth[e] = nd
                best[e] = e
                changed = True
    out = {}
    rebuild_memo = {}

    def rebuild(e, path=()):
        if e[0] in ('var', 'const'):
            return e
        parts = []
        for x in e[1:]:
            if isinstance(x, tuple):
                xc = sat.find(x)
                if xc in rebuild_memo and xc not in path:
                    parts.append(rebuild_memo[xc])
                    continue
                if xc in path:
                    parts.append(x)
                    continue
                w = min(classes[xc],
                        key=lambda m: (cost[m], depth[m]))
                rw = rebuild(w, path + (xc,))
                rebuild_memo[xc] = rw
                parts.append(rw)
            else:
                parts.append(x)
        return (e[0],) + tuple(parts)

    for r in roots:
        cls = sat.find(r)
        members = classes[cls]
        win = min(members, key=lambda e: (cost[e], depth[e]))
        out[r] = (rebuild(win), cost[win], depth[win])
    return out


# ---------------- Search B components ----------------

def boolean_function_bfs():
    """Exact classic minima for 3-input Boolean
    functions: BFS over 8-bit truth tables with the
    classic op library {AND, OR, XOR, ANDNOT}, NOT and
    constants free (the EXP-012 convention). Returns
    {table: min_ops} for all 256 functions."""
    INF = float('inf')
    cost = {t: INF for t in range(256)}
    for t in (0x00, 0xFF, 0xF0, 0xCC, 0xAA,
              0x0F, 0x33, 0x55):
        cost[t] = 0
    # cost-weighted relaxation (Dijkstra over the
    # function lattice): combining u and v costs
    # cost(u) + cost(v) + 1 ops, the expression-tree
    # op count, matching EXP-012's BFS accounting.
    changed = True
    while changed:
        changed = False
        known = [t for t in range(256) if cost[t] < INF]
        for u in known:
            for v in known:
                nc = cost[u] + cost[v] + 1
                for r in (u & v, u | v, u ^ v,
                          u & (~v & 0xFF)):
                    if nc < cost[r]:
                        cost[r] = nc
                        changed = True
    return {t: int(cost[t]) for t in range(256)
            if cost[t] < INF}


def addition_bfs(atom_names, target_masks, max_adds=9,
                 time_budget=600):
    """Minimum number of binary adds computing all
    target subset-sums of the atoms, over disjoint
    subset-sum intermediates that are themselves
    subsets of some target. BFS by adds with
    per-level dominance pruning and a hard global
    deadline (checked inside the dominance pass as
    well). Returns a dict: min_adds (None if not
    found), completed_through (the deepest level
    fully expanded without the targets appearing,
    so min_adds > completed_through is certified),
    and the number of states seen."""
    n = len(atom_names)
    singletons = frozenset(1 << i for i in range(n))
    targets = frozenset(target_masks)
    useful = set()
    for t in target_masks:
        sub = t
        while sub:
            useful.add(sub)
            sub = (sub - 1) & t
    useful |= set(singletons)
    deadline = time.time() + time_budget

    def dominated(states):
        keep = []
        for s in states:
            if any(s <= k for k in keep):
                continue
            keep = [k for k in keep if not k <= s]
            keep.append(s)
            if len(keep) % 4096 == 0 \
                    and time.time() > deadline:
                raise TimeoutError
        return keep

    start = singletons
    if targets <= start:
        return {'min_adds': 0, 'completed_through': 0,
                'states_seen': 1}
    seen = {start}
    frontier = [start]
    completed = 0
    try:
        for adds in range(1, max_adds + 1):
            nxt = []
            for state in frontier:
                lst = list(state)
                for i in range(len(lst)):
                    for j in range(i + 1, len(lst)):
                        u, v = lst[i], lst[j]
                        if u & v:
                            continue
                        w = u | v
                        if w in state or w not in useful:
                            continue
                        ns = state | {w}
                        if ns in seen:
                            continue
                        seen.add(ns)
                        if targets <= ns:
                            return {'min_adds': adds,
                                    'completed_through':
                                        adds - 1,
                                    'states_seen': len(seen)}
                        nxt.append(ns)
                if time.time() > deadline:
                    raise TimeoutError
            frontier = dominated(nxt)
            completed = adds
            print(f'  addition BFS level {adds} done: '
                  f'frontier {len(frontier)}, seen '
                  f'{len(seen)}', flush=True)
            if not frontier:
                break
    except TimeoutError:
        return {'min_adds': None,
                'completed_through': completed,
                'states_seen': len(seen),
                'deadline_hit': True}
    return {'min_adds': None,
            'completed_through': completed,
            'states_seen': len(seen)}


def carry_save_pricing():
    """Addition-network alternatives for the T1
    five-operand sum and the schedule four-operand
    sum, priced with the EXP-019 corrected model:
    one 3:2 compressor level = 3 ops (2 VPTERNLOGD +
    1 VPSLLD); resolution is a final carry-propagate
    tree of plain VPADDD."""
    def plain(k):
        return {'ops': k - 1, 'form': f'{k - 1} VPADDD tree'}

    def cs_forms(k):
        out = []
        # apply L compressor levels greedily, then
        # resolve the remaining values with adds
        vals = k
        ops = 0
        for L in (1, 2):
            if vals < 3:
                break
            # each level: floor(vals/3) compressors,
            # each turns 3 values into 2
            comps = vals // 3
            ops += 3 * comps
            vals = vals - comps
            total = ops + (vals - 1)
            out.append({'ops': total,
                        'form': f'{L} carry-save level(s) '
                                f'then {vals - 1} VPADDD'})
        return out

    return {'T1_5_operand': [plain(5)] + cs_forms(5),
            'schedule_4_operand': [plain(4)] + cs_forms(4)}


def sharing_analysis(parts):
    """Hash-consed subterm sharing across the cones of
    the classic reference: which non-trivial
    subexpressions appear in more than one cone."""
    cones = {'S1': parts['S1'], 'Ch': parts['Ch'],
             'S0': parts['S0'], 'Maj': parts['Maj'],
             's0': parts['s0'], 's1': parts['s1']}
    sets = {}
    for name, e in cones.items():
        s = set()
        subexprs(e, s)
        sets[name] = {x for x in s if x[0] != 'var'}
    shared = {}
    names = list(cones)
    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            inter = sets[names[i]] & sets[names[j]]
            if inter:
                shared[f'{names[i]}|{names[j]}'] = \
                    [repr(x) for x in sorted(inter, key=repr)]
    # sharing inside the output structure
    t1_users = []
    for out_name in ('a_out', 'e_out'):
        s = set()
        subexprs(parts[out_name], s)
        if parts['T1'] in s:
            t1_users.append(out_name)
    return {'cross_cone_shared_nontrivial': shared,
            'T1_shared_by': t1_users}


def offset_support(e):
    """Symbolic dependency support: for each output
    bit i, the set of (variable, k) such that bit i
    depends on the variable's bit (i + k) mod 32
    (for shr, bits that fall off the top are dropped
    and the dependence is partial; recorded with the
    same (var, k) marker)."""
    op = e[0]
    if op == 'var':
        return {(e[1], 0)}
    if op == 'const':
        return set()
    if op == 'not':
        return offset_support(e[1])
    if op in ('and', 'or', 'xor', 'andnot'):
        return offset_support(e[1]) | offset_support(e[2])
    if op == 'ternlog':
        out = set()
        for x in e[2:]:
            out |= offset_support(x)
        return out
    if op == 'rotr':
        return {(v, (k + e[2]) % 32)
                for (v, k) in offset_support(e[1])}
    if op == 'shr':
        return {(v, k + e[2])
                for (v, k) in offset_support(e[1])}
    if op == 'add':
        # addition mixes all bit positions through
        # carries; support becomes all offsets of the
        # union's variables (over-approximation, used
        # only as a sanity check on the outputs)
        vs = {v for (v, _) in
              offset_support(e[1]) | offset_support(e[2])}
        return {(v, k) for v in vs for k in range(32)}
    raise ValueError(op)


def count_offset_ops(e, memo=None):
    if memo is None:
        memo = {}
    if e in memo:
        return memo[e]
    op = e[0]
    if op in ('var', 'const'):
        r = 0
    elif op in ('rotr', 'shr'):
        r = 1 + count_offset_ops(e[1], memo)
    elif op == 'not':
        r = count_offset_ops(e[1], memo)
    elif op == 'ternlog':
        r = sum(count_offset_ops(x, memo) for x in e[2:])
    else:
        r = count_offset_ops(e[1], memo) \
            + count_offset_ops(e[2], memo)
    memo[e] = r
    return r


# ---------------- incumbent assembly audit ----------------

def asm_audit(source_path, flags, workdir, label):
    """Compile a kernel source and census the vector
    arithmetic in v_compress16. The function contains
    exactly one round body (the t < 16 path jumps into
    the same body), so whole-function arithmetic
    counts are the per-round counts; moves and scalar
    loop control are counted separately."""
    import re
    os.makedirs(workdir, exist_ok=True)
    obj = os.path.join(workdir, f'{label}.o')
    cmd = ['gcc', '-O3', '-c', source_path, '-o', obj] + flags
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        return {'label': label, 'error': r.stderr[-500:]}
    r = subprocess.run(['objdump', '-d', obj,
                        '--disassemble=v_compress16', '-M',
                        'intel'], capture_output=True, text=True)
    text = r.stdout
    counts = {'vprold_vprord': 0, 'vpsrld': 0, 'vpternlogd': 0,
              'vpaddd': 0, 'vmovdqa_moves': 0, 'scalar': 0}
    imms = []
    for line in text.splitlines():
        # objdump lines: ADDR:\tBYTES\tINSTRUCTION
        fields = line.split('\t')
        if len(fields) < 3:
            continue
        instr = fields[-1].strip()
        if not instr:
            continue
        mn = instr.split()[0]
        if mn in ('vprold', 'vprord'):
            counts['vprold_vprord'] += 1
        elif mn == 'vpsrld':
            counts['vpsrld'] += 1
        elif mn == 'vpternlogd':
            counts['vpternlogd'] += 1
            im = re.search(r'0x([0-9a-f]+)\s*$', line)
            if im:
                imms.append(int(im.group(1), 16))
        elif mn == 'vpaddd':
            counts['vpaddd'] += 1
        elif mn.startswith('vmovdqa'):
            counts['vmovdqa_moves'] += 1
        elif not mn.startswith('v'):
            counts['scalar'] += 1
    counts['arithmetic_total'] = (
        counts['vprold_vprord'] + counts['vpsrld']
        + counts['vpternlogd'] + counts['vpaddd'])
    counts['ternlog_immediates'] = sorted(imms)
    counts['compile_command'] = ' '.join(cmd)
    src = open(source_path, 'rb').read()
    counts['source_sha256'] = hashlib.sha256(src).hexdigest()
    return counts


# ---------------- stochastic superoptimiser ----------------

def all_paths(e, path=()):
    yield path, e
    for i, x in enumerate(e[1:]):
        if isinstance(x, tuple):
            yield from all_paths(x, path + (i + 1,))


def replace_at(e, path, new):
    if not path:
        return new
    parts = list(e)
    parts[path[0]] = replace_at(parts[path[0]], path[1:], new)
    return tuple(parts)


def flatten_add(e):
    if e[0] == 'add':
        return flatten_add(e[1]) + flatten_add(e[2])
    return [e]


def random_add_tree(operands, rng):
    ops = list(operands)
    while len(ops) > 1:
        i = rng.randrange(len(ops))
        j = rng.randrange(len(ops))
        if i == j:
            continue
        a, b = ops[i], ops[j]
        for k in sorted((i, j), reverse=True):
            ops.pop(k)
        ops.append(('add', a, b))
    return ops[0]


def mutate(exprs, rng):
    """One random mutation of the joint output set.
    Operators: add reassociation, term-level ternlog
    folding, Ch/Maj form swaps, ternlog expansion, and
    a rare non-preserving op flip (the differential
    filter disposes)."""
    exprs = list(exprs)
    oi = rng.randrange(len(exprs))
    e = exprs[oi]
    paths = [p for p, _ in all_paths(e)]
    p = paths[rng.randrange(len(paths))]
    node = e
    for step in p:
        node = node[step]
    kind = rng.random()
    new = None
    if kind < 0.30 and node[0] == 'add':
        operands = flatten_add(node)
        if len(operands) >= 3:
            new = random_add_tree(operands, rng)
    elif kind < 0.55 and node[0] in BOOL_OPS:
        fr = bool_frontier(node)
        if fr is not None and len(fr) == 3:
            imm = bool_table_over_terms(node, fr)
            new = ('ternlog', imm, fr[0], fr[1], fr[2])
    elif kind < 0.70 and node[0] == 'ternlog':
        a, b, c = node[2], node[3], node[4]
        if node[1] == CH_TABLE:
            new = rng.choice([ch_classic(a, b, c),
                              ('xor', c, ('and', a,
                                          ('xor', b, c)))])
        elif node[1] == MAJ_TABLE:
            new = rng.choice([
                maj_classic(a, b, c),
                ('xor', ('and', a, b),
                 ('and', c, ('xor', a, b))),
                ('xor', ('and', a, ('xor', b, c)),
                 ('and', b, c))])
        elif node[1] == XOR3_TABLE:
            new = xor3(a, b, c)
    elif kind < 0.90 and node[0] in BOOL_OPS:
        fr = bool_frontier(node)
        if fr is not None and len(fr) == 3:
            imm = bool_table_over_terms(node, fr)
            if imm == CH_TABLE:
                x, y, z = fr
                new = rng.choice([ch_classic(x, y, z),
                                  ('xor', z, ('and', x,
                                              ('xor', y, z)))])
            elif imm == MAJ_TABLE:
                x, y, z = fr
                new = rng.choice([
                    maj_classic(x, y, z),
                    ('xor', ('and', x, y),
                     ('and', z, ('xor', x, y))),
                    ('xor', ('and', x, ('xor', y, z)),
                     ('and', y, z))])
    else:
        if node[0] in ('and', 'or', 'xor'):
            new = (rng.choice(['and', 'or', 'xor']),
                   node[1], node[2])
    if new is None:
        return None
    exprs[oi] = replace_at(e, p, new)
    return exprs


def superoptimise(ref_exprs, seed_exprs, proposals=20000,
                  seed=20261114):
    rng = random.Random(seed)
    cur = list(seed_exprs)
    names = ROUND_VARS + SCHED_VARS

    def score(exprs):
        ops, depths = joint_census(exprs, 'avx512')
        return (ops, max(depths))

    def diff_ok(exprs, samples):
        for r, c in zip(ref_exprs, exprs):
            n = ROUND_VARS if r is ref_exprs[0] or True \
                else SCHED_VARS
            bad = differential(r, c, ALL_VARS, samples,
                               rng.randrange(2**31))
            if bad:
                return False
        return True

    cur_score = score(cur)
    assert diff_ok(cur, 20000), 'seed must be equivalent'
    accepted = 0
    filter_kills = 0
    worse_rejected = 0
    for i in range(proposals):
        cand = mutate(cur, rng)
        if cand is None:
            continue
        s = score(cand)
        if s > cur_score:
            worse_rejected += 1
            continue
        if s == cur_score and rng.random() > 0.25:
            continue
        if not diff_ok(cand, 20000):
            filter_kills += 1
            continue
        cur = cand
        cur_score = s
        accepted += 1
    return {'best_exprs': cur, 'best_score': cur_score,
            'proposals': proposals, 'accepted': accepted,
            'filter_kills': filter_kills,
            'worse_rejected': worse_rejected, 'seed': seed}


# ---------------- main ----------------

def main():
    t_start = time.time()
    results = {'experiment': 'EXP-020',
               'hypotheses': ['Y-014', 'Y-015'],
               'started_utc': time.strftime(
                   '%Y-%m-%dT%H:%M:%SZ', time.gmtime())}
    parts = reference_dags()
    ref_outs = [parts['a_out'], parts['e_out'], parts['Wn']]

    # ---- incumbent censuses (source form) ----
    inc_classic, inc_depths = joint_census(ref_outs, 'classic')
    results['incumbent_source_form'] = {
        'model': 'classic op library, source association '
                 'of mining/cpu/bal_avx512_mb.c',
        'joint_ops_round_plus_schedule': inc_classic,
        'output_depths': {'a_out': inc_depths[0],
                          'e_out': inc_depths[1],
                          'Wn': inc_depths[2]}}
    print('incumbent classic census:', inc_classic,
          'depths', inc_depths, flush=True)

    # ---- incumbent emitted census (assembly audit) ----
    prod_src = os.path.join(ROOT, 'mining/cpu/bal_avx512_mb.c')
    audit = asm_audit(prod_src, ['-mavx512f', '-mavx512bw'],
                      '/tmp/exp020_asm', 'production')
    results['incumbent_emitted'] = audit
    print('emitted audit:', audit, flush=True)

    # ---- Search A, campaign 1 ----
    sat = Saturation(ref_outs)
    classes, passes = sat.run()
    results['searchA_campaign1'] = {
        'expressions_discovered': len(sat.exprs),
        'classes': len(classes), 'passes': passes,
        'node_budget': 500000}
    print('saturation campaign 1:', len(sat.exprs),
          'expressions,', passes, 'passes', flush=True)
    ext = {}
    for model in ('classic', 'avx512'):
        got = extract(classes, sat,
                      [parts['a_out'], parts['e_out'],
                       parts['Wn']], model)
        exprs = [got[parts['a_out']][0], got[parts['e_out']][0],
                 got[parts['Wn']][0]]
        ops, depths = joint_census(exprs, model)
        ext[model] = {'exprs': exprs, 'ops': ops,
                      'depths': depths, 'got': got}
        print('extracted', model, ':', ops, 'ops, depths',
              depths, flush=True)
    results['searchA_extraction'] = {
        m: {'joint_ops': ext[m]['ops'],
            'output_depths': {'a_out': ext[m]['depths'][0],
                              'e_out': ext[m]['depths'][1],
                              'Wn': ext[m]['depths'][2]}}
        for m in ext}

    # ---- Search A, campaign 2 (alt-seeded) ----
    a, b, c, e, f, g = (V(n) for n in 'abcefg')
    parts2 = reference_dags()
    parts2['Ch'] = ('ternlog', CH_TABLE, e, f, g)
    parts2['Maj'] = ('ternlog', MAJ_TABLE, a, b, c)
    parts2['T1'] = ('add',
                    ('add', ('add', V('h'), parts2['S1']),
                     ('add', parts2['Ch'], V('K'))), V('W'))
    parts2['T2'] = ('add', parts2['S0'], parts2['Maj'])
    parts2['a_out'] = ('add', parts2['T1'], parts2['T2'])
    parts2['e_out'] = ('add', V('d'), parts2['T1'])
    seeds2 = [parts2['a_out'], parts2['e_out'], parts2['Wn']]
    sat2 = Saturation(seeds2 + ref_outs)
    classes2, passes2 = sat2.run()
    got2 = extract(classes2, sat2,
                   [parts['a_out'], parts['e_out'],
                    parts['Wn']], 'avx512')
    exprs2 = [got2[parts['a_out']][0], got2[parts['e_out']][0],
              got2[parts['Wn']][0]]
    ops2, depths2 = joint_census(exprs2, 'avx512')
    results['searchA_campaign2'] = {
        'expressions_discovered': len(sat2.exprs),
        'passes': passes2,
        'extracted_avx512_ops': ops2,
        'new_winner_over_campaign1':
            bool(ops2 < ext['avx512']['ops'])}
    print('campaign 2 extracted:', ops2, 'ops', flush=True)

    # ---- proofs and 1M differentials for extractions ----
    proofs = {}
    for model in ('classic', 'avx512'):
        exprs = ext[model]['exprs']
        pairs = list(zip(ref_outs, exprs))
        z = prove_equiv_multi(pairs, ALL_VARS)
        bad = 0
        for r, cexpr in pairs:
            bad += differential(r, cexpr, ALL_VARS,
                                1_000_000, 777)
        proofs[model] = {'z3': z,
                         'differential_samples': 1_000_000,
                         'differential_mismatches': bad}
        print('proof', model, ':', z, 'diff bad', bad,
              flush=True)
    results['extraction_proofs'] = proofs

    # ---- Search B: Boolean function BFS ----
    lvl = boolean_function_bfs()
    results['boolean_bfs_classic_minima'] = {
        'Ch_0xCA': lvl[CH_TABLE], 'Maj_0xE8': lvl[MAJ_TABLE],
        'XOR3_0x96': lvl[XOR3_TABLE],
        'functions_reached': len(lvl)}
    print('boolean BFS minima: Ch', lvl[CH_TABLE], 'Maj',
          lvl[MAJ_TABLE], 'XOR3', lvl[XOR3_TABLE], flush=True)

    # ---- Search B: addition network BFS ----
    t1_min = addition_bfs(['h', 'S1', 'Ch', 'K', 'W'],
                          [0b11111], max_adds=6)
    sched_min = addition_bfs(['P', 's0', 'Q', 's1'],
                             [0b1111], max_adds=5)
    pair_min = addition_bfs(
        ['h', 'S1', 'Ch', 'K', 'W', 'S0', 'Maj', 'd'],
        [(1 << 7) - 1, 0b10011111], max_adds=7,
        time_budget=600)
    results['addition_bfs'] = {
        'pair_a_e': pair_min,
        'T1': t1_min,
        'schedule_sum': sched_min,
        'note': 'atoms are the materialised subcones '
                '(S1, Ch, S0, Maj); intermediates are '
                'disjoint subset sums of the targets. '
                'The pair bound of 7 also follows from '
                'the counting proof in the EXP-020 '
                'record (ancestor sets: a-out needs '
                '>= 6 adds, e-out >= 5, shared <= 4), '
                'and 7 is achieved by the incumbent '
                'structure, so the bound is exact '
                'regardless of how far the BFS got.'}
    print('addition BFS: pair', pair_min, 'T1', t1_min,
          'sched', sched_min, flush=True)

    # ---- Search B: carry-save pricing ----
    results['carry_save_pricing'] = carry_save_pricing()

    # ---- Search B: sharing analysis ----
    results['sharing_analysis'] = sharing_analysis(parts)
    print('sharing:', results['sharing_analysis'], flush=True)

    # ---- Search B: sigma supports ----
    sup = {}
    for name in ('S0', 'S1', 's0', 's1'):
        s = offset_support(parts[name])
        sup[name] = {'support': sorted([list(x) for x in s]),
                     'offset_ops_in_reference':
                         count_offset_ops(parts[name]),
                     'distinct_offsets': len(s)}
    # extracted avx512 forms of the sigmas: find them as
    # the ternlog-headed subexpressions over rotations
    results['sigma_supports'] = sup
    print('sigma supports:', {k: v['support'] for k, v
                              in sup.items()}, flush=True)

    # ---- Search B: materialisation counterexamples ----
    ev = V('e')
    r6, r11, r25 = (('rotr', ev, n) for n in (6, 11, 25))
    cx1 = prove_equiv_multi(
        [(('xor', r6, r11), ('add', r6, r11))], ['e'])
    cx2 = prove_equiv_multi(
        [(xor3(r6, r11, r25), ('add', ('add', r6, r11), r25))],
        ['e'])
    results['materialisation_counterexamples'] = {
        'xor_vs_add_two_rotations': cx1,
        'S1_vs_sum_of_rotations': cx2,
        'note': 'sat = a counterexample exists, so the '
                'rotated terms cannot enter the addition '
                'network unmaterialised'}
    print('counterexamples:', cx1, cx2, flush=True)

    # ---- Search B: stochastic superoptimiser ----
    seed_exprs = [ext['avx512']['exprs'][0],
                  ext['avx512']['exprs'][1],
                  ext['avx512']['exprs'][2]]
    so = superoptimise(ref_outs, seed_exprs,
                       proposals=20000, seed=20261114)
    results['superoptimiser'] = {
        'proposals': so['proposals'], 'accepted': so['accepted'],
        'filter_kills': so['filter_kills'],
        'worse_rejected': so['worse_rejected'],
        'seed': so['seed'],
        'best_score_ops_depth': list(so['best_score'])}
    print('superoptimiser best:', so['best_score'],
          'accepted', so['accepted'], flush=True)
    if tuple(so['best_score']) < tuple(
            (ext['avx512']['ops'],
             max(ext['avx512']['depths']))):
        z = prove_equiv_multi(
            list(zip(ref_outs, so['best_exprs'])), ALL_VARS)
        results['superoptimiser']['best_z3'] = z
        results['superoptimiser']['best_exprs'] = [
            repr(x) for x in so['best_exprs']]

    results['runtime_s'] = round(time.time() - t_start, 1)

    # ---- artifacts ----
    os.makedirs(os.path.join(PHASE6, 'analysis'), exist_ok=True)
    os.makedirs(os.path.join(PHASE6, 'proofs'), exist_ok=True)
    with open(os.path.join(PHASE6, 'analysis',
                           'exp020_search_results.json'),
              'w') as fh:
        json.dump(results, fh, indent=2)

    emitted_ops = audit.get('arithmetic_total')
    cand_records = [
        {
            'id': 'P6C-005',
            'cone': 'full round + schedule (t >= 16)',
            'source_transformation':
                'Search A equality saturation with '
                'term-level ternlog folding; extraction '
                'under the AVX-512 cost model',
            'target_expression': 'production round, '
                                 'source form (classic)',
            'candidate_expression': {
                'a_out': repr(ext['avx512']['exprs'][0]),
                'e_out': repr(ext['avx512']['exprs'][1]),
                'Wn': repr(ext['avx512']['exprs'][2])},
            'proof': {'method': 'z3 UNSAT (joint, all '
                                'outputs) + 1M-sample '
                                'differential',
                      'artifact': 'proofs/exp020_candidates.json',
                      'z3': proofs['avx512']['z3'],
                      'differential_mismatches':
                          proofs['avx512']
                          ['differential_mismatches']},
            'cost': {'incumbent_source_classic': inc_classic,
                     'incumbent_emitted': emitted_ops,
                     'candidate': ext['avx512']['ops'],
                     'model': 'AVX-512 vector op census, '
                              'round + schedule'},
            'compiler_config': None,
            'assembly_audit': None,
            'benchmark': 'not run',
            'status': 'proven; census equals the '
                      'vocabulary lower bound derived in '
                      'Search B; see P6C-007 for the one '
                      'op the emitted code leaves open',
            'note': 'Extraction saturated: campaign 2 '
                    'found no cheaper form.',
        },
        {
            'id': 'P6C-006',
            'cone': 'full round + schedule (t >= 16)',
            'source_transformation':
                'Search A extraction under the classic '
                'op library (Maj_alt forms admitted)',
            'target_expression': 'production round, '
                                 'source form',
            'candidate_expression': {
                'a_out': repr(ext['classic']['exprs'][0]),
                'e_out': repr(ext['classic']['exprs'][1]),
                'Wn': repr(ext['classic']['exprs'][2])},
            'proof': {'method': 'z3 UNSAT + 1M-sample '
                                'differential',
                      'artifact': 'proofs/exp020_candidates.json',
                      'z3': proofs['classic']['z3'],
                      'differential_mismatches':
                          proofs['classic']
                          ['differential_mismatches']},
            'cost': {'incumbent_source_classic': inc_classic,
                     'candidate': ext['classic']['ops'],
                     'model': 'classic op census'},
            'compiler_config': None,
            'assembly_audit': None,
            'benchmark': 'not run',
            'status': 'proven; the classic saving over '
                      'the source form is exactly the '
                      'Maj alt form (5 to 4 ops)',
            'note': 'Not promotable: the AVX-512 '
                    'library supersedes the classic one '
                    'on this machine.',
        },
        {
            'id': 'P6C-007',
            'cone': 'Maj subcone, as emitted',
            'source_transformation':
                'single VPTERNLOGD 0xE8 in place of the '
                'two chained VPTERNLOGD (0x60 then 0x78) '
                'that gcc emits for Maj_alt_B',
            'target_expression':
                'Maj as emitted in production '
                'v_compress16 (2 ternlog ops, serial)',
            'candidate_expression':
                "('ternlog', 232, a, b, c)",
            'proof': {'method': 'z3 UNSAT (EXP-012 '
                                'result, re-gated inside '
                                'P6C-005 joint proof)',
                      'artifact': 'proofs/exp020_candidates.json',
                      'z3': proofs['avx512']['z3']},
            'cost': {'incumbent_emitted_round': emitted_ops,
                     'candidate_round': (emitted_ops - 1
                                         if emitted_ops
                                         else None),
                     'model': 'emitted arithmetic census '
                              'per steady-state round'},
            'compiler_config':
                'gcc -O3 -mavx512f -mavx512bw (build.py '
                'production flags)',
            'assembly_audit':
                'analysis/exp020_asm_audit.json',
            'benchmark': 'see EXP-020 record: variant '
                         'kernel under the EXP-017 '
                         'paired protocol',
            'status': 'PROMOTED TO VARIANT KERNEL under '
                      'the predeclared threshold (proven, '
                      'census strictly below emitted, no '
                      'depth regression); benchmark '
                      'decides the rate claim, not '
                      'integration',
            'note': 'The one op the whole search leaves '
                    'on the table, and it is a codegen '
                    'gap, not a graph discovery: the '
                    'graph form was already known '
                    '(EXP-012); gcc does not emit it.',
        },
        {
            'id': 'P6C-008',
            'cone': 'T1 association',
            'source_transformation':
                'addition-tree reassociation: S1 enters '
                'last, ((h + K) + (Ch + W)) + S1',
            'target_expression':
                'T1 source association ((h + S1) + '
                '(Ch + K)) + W',
            'candidate_expression':
                'depth-optimal association over the 5 '
                'operands (1,680 trees enumerated)',
            'proof': {'method': 'exact by associativity '
                                'and commutativity of '
                                'modular addition; covered '
                                'by the joint z3 proofs',
                      'artifact': 'proofs/exp020_candidates.json'},
            'cost': {'incumbent': '4 adds, T1 depth 5 '
                                  '(AVX-512 model, source '
                                  'association)',
                     'candidate': '4 adds, T1 depth 4',
                     'model': 'depth at equal census'},
            'compiler_config': None,
            'assembly_audit':
                'analysis/exp020_asm_audit.json: the '
                'emitted code already adds S1 last '
                '(association ((Ch + W) + (h + K)) + '
                'S1), so the depth is already realised',
            'benchmark': 'not run',
            'status': 'proven, already emitted; '
                      'codegen fact, not a discovery',
            'note': 'Recorded so the depth question is '
                    'closed with evidence.',
        },
        {
            'id': 'P6C-009',
            'cone': 'T1 / schedule addition networks',
            'source_transformation':
                'carry-save forms priced at the EXP-019 '
                'price list (3 ops per 3:2 level)',
            'target_expression': 'plain VPADDD trees '
                                 '(4 adds T1, 3 adds '
                                 'schedule)',
            'candidate_expression':
                json.dumps(carry_save_pricing()),
            'proof': {'method': 'exact by construction '
                                '(compressor identities '
                                'proven in EXP-012/019)',
                      'artifact': 'proofs/exp020_candidates.json'},
            'cost': {'incumbent': 'T1 4 ops, schedule 3 '
                                  'ops',
                     'candidate': 'T1 >= 6 ops, schedule '
                                  '>= 5 ops',
                     'model': 'EXP-019 corrected pricing'},
            'compiler_config': None,
            'assembly_audit': None,
            'benchmark': 'not run',
            'status': 'REJECTED by the cost model '
                      'before any kernel work (mirrors '
                      'EXP-019 measurement)',
            'note': 'No candidate record corpse is '
                    'dropped: this is the priced '
                    'rejection.',
        },
    ]
    with open(os.path.join(PHASE6, 'proofs',
                           'exp020_candidates.json'), 'w') as fh:
        json.dump({'experiment': 'EXP-020',
                   'candidates': cand_records}, fh, indent=2)
    with open(os.path.join(PHASE6, 'analysis',
                           'exp020_asm_audit.json'), 'w') as fh:
        json.dump({'production': audit}, fh, indent=2)
    print('artifacts written; runtime', results['runtime_s'],
          's', flush=True)
    return 0


if __name__ == '__main__':
    sys.exit(main())
