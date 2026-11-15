#!/usr/bin/env python3
"""EXP-033 scope 1a: equality saturation over the composed
two-round DAG.

The initial DAG is the incumbent computation (two rounds
plus the two schedule words they consume; exact cost 56
under the EXP-020 census model, verified against the
reference implementation in exp033_common). Saturation
applies only sound word-level rewrite rules:

  R1  rotr(rotr(x,i),j) = rotr(x,i+j); rotr(x,0) = x
  R2  rotr(LUT(a,b,c),k) = LUT(rotr(a,k),rotr(b,k),rotr(c,k))
  R2b LUT(rotr(a,k),rotr(b,k),rotr(c,k)) = rotr(LUT(a,b,c),k)
  R3  constant folding for rotr/shr/shl/add/LUT
  R4  LUT flattening: a LUT whose child class contains a
      LUT is recomposed over the union of leaf atoms when
      that union has at most 3 distinct classes (exact
      per-bit truth-table recomposition over the atoms)
  R5  add associativity (both directions); add(x,0) = x;
      add(x,x) = shl(x,1)
  R6  LUT degeneracies: projection immediates union with
      the projected child; constant immediates union with
      the constant class; inputs an immediate ignores are
      replaced by the zero constant

There is deliberately NO rule pushing a bitwise op through
an ADD, because none is sound; that wall is the subject of
the companion cone-synthesis experiment (scope 1b).

After saturation, a cost DP over e-classes (tree cost) is
compared against the baseline DP, and a greedy extraction
is counted exactly as a DAG. Any extracted form cheaper
than the baseline would be a candidate identity, to be
proven in z3 and differentially tested before being
called anything; the JSON states what actually happened.

Run with the lab z3 venv python. Writes
RAW_RESULTS/exp033_egraph_<ts>.json.
"""

import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from exp033_common import (M32, OP_COST, build_two_rounds,
                           dag_cost, rotr)

HERE = os.path.dirname(os.path.abspath(__file__))
EXP033 = os.path.dirname(HERE)

ZERO = ("const", 0)
ONES = ("const", M32)


def lut_bit(imm, abit, bbit, cbit):
    return (imm >> ((abit << 2) | (bbit << 1) | cbit)) & 1


def permute_imm(imm, order):
    """order maps new position -> old position: the operand
    now at position i was at position order[i]."""
    out = 0
    for na in range(2):
        for nb in range(2):
            for nc in range(2):
                newbits = (na, nb, nc)
                oldbits = [0, 0, 0]
                for i in range(3):
                    oldbits[order[i]] = newbits[i]
                out |= lut_bit(imm, *oldbits) << \
                    ((na << 2) | (nb << 1) | nc)
    return out


def flatten_imm(outer_imm, pos, inner_imm, kids, inner_kids):
    """Compose outer LUT with an inner LUT sitting at operand
    position pos. kids are the outer operand classes,
    inner_kids the inner operand classes. If the union of
    distinct classes has at most 3 members, return
    (atoms, imm3) for a single LUT over those atoms (padded
    to 3 operands by repeating the last atom, with the
    table expanded so the composition is exact on every
    consistent input); else return None."""
    distinct = []
    for c in list(kids) + list(inner_kids):
        if c not in distinct:
            distinct.append(c)
    if len(distinct) > 3:
        return None
    n = len(distinct)
    # value of the composition for each atom assignment,
    # indexed by (v0<<2)|(v1<<1)|v2 over the distinct atoms
    # (missing atoms read as 0).
    table = {}
    for m in range(1 << n):
        abit = {distinct[i]: (m >> (n - 1 - i)) & 1
                for i in range(n)}
        inner_bit = lut_bit(inner_imm, abit[inner_kids[0]],
                            abit[inner_kids[1]],
                            abit[inner_kids[2]])
        obits = [inner_bit if p == pos else abit[kids[p]]
                 for p in range(3)]
        val = lut_bit(outer_imm, *obits)
        idx = 0
        for i in range(3):
            v = abit[distinct[i]] if i < n else 0
            idx |= v << (2 - i)
        table[idx] = val
    atoms = distinct + [distinct[-1]] * (3 - n)
    imm3 = 0
    for na in range(2):
        for nb in range(2):
            for nc in range(2):
                bits = (na, nb, nc)
                # atom i takes the bit of the first padded
                # position holding it
                av = []
                for i in range(n):
                    p = atoms.index(distinct[i])
                    av.append(bits[p])
                idx = 0
                for i in range(3):
                    v = av[i] if i < n else 0
                    idx |= v << (2 - i)
                imm3 |= table[idx] << ((na << 2) | (nb << 1) | nc)
    return atoms, imm3


class EGraph:
    def __init__(self):
        self.parent = []
        self.class_enodes = {}   # rep -> set of enodes
        self.hashcons = {}       # canonical enode -> rep
        self.enodes = set()      # all canonical enodes

    def find(self, x):
        root = x
        while self.parent[root] != root:
            root = self.parent[root]
        while self.parent[x] != root:
            self.parent[x], x = root, self.parent[x]
        return root

    def _new_class(self, en):
        i = len(self.parent)
        self.parent.append(i)
        self.class_enodes[i] = {en}
        self.hashcons[en] = i
        self.enodes.add(en)
        return i

    def canon(self, en):
        op = en[0]
        if op in ("in", "const"):
            return en
        if op == "add":
            a, b = self.find(en[1]), self.find(en[2])
            if a > b:
                a, b = b, a
            return ("add", a, b)
        if op in ("rotr", "shr", "shl"):
            return (op, en[1] % 32 if op == "rotr" else en[1],
                    self.find(en[2]))
        if op == "lut":
            kids = [self.find(en[2]), self.find(en[3]),
                    self.find(en[4])]
            order = sorted(range(3), key=lambda i: kids[i])
            if order != [0, 1, 2]:
                imm = permute_imm(en[1], order)
                kids = [kids[order[0]], kids[order[1]],
                        kids[order[2]]]
                return ("lut", imm, kids[0], kids[1], kids[2])
            return ("lut", en[1], kids[0], kids[1], kids[2])
        raise ValueError(op)

    def add_enode(self, en):
        en = self.canon(en)
        if en in self.hashcons:
            return self.find(self.hashcons[en])
        return self._new_class(en)

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra == rb:
            return False
        if len(self.class_enodes.get(ra, ())) < \
                len(self.class_enodes.get(rb, ())):
            ra, rb = rb, ra
        self.parent[rb] = ra
        merged = self.class_enodes.pop(rb, set())
        self.class_enodes.setdefault(ra, set()).update(merged)
        return True

    def rebuild(self):
        for _ in range(100):
            changed = False
            # canonicalise enodes inside each class
            for rep in list(self.class_enodes):
                if self.find(rep) != rep:
                    continue
                newset = {self.canon(en)
                          for en in self.class_enodes[rep]}
                if newset != self.class_enodes[rep]:
                    self.class_enodes[rep] = newset
                    changed = True
            # merge classes sharing a canonical enode
            seen = {}
            for rep in list(self.class_enodes):
                if self.find(rep) != rep:
                    continue
                for en in list(self.class_enodes.get(rep, ())):
                    if en in seen:
                        if self.union(seen[en], rep):
                            changed = True
                    else:
                        seen[en] = rep
            if not changed:
                break
        self.hashcons = {}
        self.enodes = set()
        for rep, ens in self.class_enodes.items():
            if self.find(rep) != rep:
                continue
            for en in ens:
                self.hashcons[en] = rep
                self.enodes.add(en)


def enode_children(en):
    op = en[0]
    if op == "add":
        return (en[1], en[2])
    if op in ("rotr", "shr", "shl"):
        return (en[2],)
    if op == "lut":
        return (en[2], en[3], en[4])
    return ()


def load_dag(eg, dag):
    ids = []
    for nd in dag.nodes:
        op = nd[0]
        if op == "in":
            ids.append(eg.add_enode(("in", nd[1])))
        elif op == "const":
            ids.append(eg.add_enode(("const", nd[1])))
        elif op == "add":
            ids.append(eg.add_enode(("add", ids[nd[1]],
                                     ids[nd[2]])))
        elif op in ("rotr", "shr", "shl"):
            ids.append(eg.add_enode((op, nd[1], ids[nd[2]])))
        elif op == "lut":
            ids.append(eg.add_enode(("lut", nd[1], ids[nd[2]],
                                     ids[nd[3]], ids[nd[4]])))
    return ids


def saturate(eg, max_rounds=25, max_classes=4000, log=print):
    zero_c = eg.add_enode(ZERO)
    ones_c = eg.add_enode(ONES)
    stats = []
    for rnd in range(max_rounds):
        before = (len(eg.enodes), len(eg.class_enodes))
        added = [0]

        def put(en, into):
            r = eg.add_enode(en)
            if eg.find(r) != eg.find(into):
                eg.union(r, into)
                added[0] += 1
            return r

        snapshot = {}
        for rep, ens in eg.class_enodes.items():
            if eg.find(rep) == rep:
                snapshot[rep] = list(ens)

        def class_forms(cls):
            return snapshot.get(eg.find(cls), [])

        for rep, ens in snapshot.items():
            for en in ens:
                op = en[0]
                if op == "rotr":
                    k, x = en[1], en[2]
                    for xen in class_forms(x):
                        if xen[0] == "rotr":
                            put(("rotr", (k + xen[1]) % 32,
                                 xen[2]), rep)
                        elif xen[0] == "const":
                            put(("const", rotr(xen[1], k)), rep)
                        elif xen[0] == "lut":
                            ra = eg.add_enode(("rotr", k,
                                               xen[2]))
                            rb = eg.add_enode(("rotr", k,
                                               xen[3]))
                            rc = eg.add_enode(("rotr", k,
                                               xen[4]))
                            put(("lut", xen[1], ra, rb, rc), rep)
                elif op in ("shr", "shl"):
                    k, x = en[1], en[2]
                    for xen in class_forms(x):
                        if xen[0] == "const":
                            v = xen[1]
                            nv = (v >> k) if op == "shr" else \
                                ((v << k) & M32)
                            put(("const", nv), rep)
                elif op == "add":
                    x, y = en[1], en[2]
                    if x == y:
                        put(("shl", 1, x), rep)
                    for xen in class_forms(x):
                        if xen[0] == "const" and xen[1] == 0:
                            if eg.union(rep, eg.find(y)):
                                added[0] += 1
                        elif xen[0] == "add":
                            inner = eg.add_enode(
                                ("add", xen[2], y))
                            put(("add", xen[1], inner), rep)
                        elif xen[0] == "const":
                            for yen in class_forms(y):
                                if yen[0] == "const":
                                    put(("const",
                                         (xen[1] + yen[1]) & M32),
                                        rep)
                    for yen in class_forms(y):
                        if yen[0] == "const" and yen[1] == 0:
                            if eg.union(rep, eg.find(x)):
                                added[0] += 1
                        elif yen[0] == "add":
                            inner = eg.add_enode(
                                ("add", x, yen[1]))
                            put(("add", inner, yen[2]), rep)
                elif op == "lut":
                    imm = en[1]
                    kids = [en[2], en[3], en[4]]
                    if imm == 0x00:
                        if eg.union(rep, zero_c):
                            added[0] += 1
                    elif imm == 0xFF:
                        if eg.union(rep, ones_c):
                            added[0] += 1
                    elif imm == 0xF0:
                        if eg.union(rep, eg.find(kids[0])):
                            added[0] += 1
                    elif imm == 0xCC:
                        if eg.union(rep, eg.find(kids[1])):
                            added[0] += 1
                    elif imm == 0xAA:
                        if eg.union(rep, eg.find(kids[2])):
                            added[0] += 1
                    # inputs the immediate ignores -> zero
                    for pos in range(3):
                        depends = False
                        for m in range(8):
                            bits = [(m >> 2) & 1, (m >> 1) & 1,
                                    m & 1]
                            flipped = list(bits)
                            flipped[pos] ^= 1
                            if lut_bit(imm, *bits) != \
                                    lut_bit(imm, *flipped):
                                depends = True
                                break
                        if not depends and \
                                eg.find(kids[pos]) != zero_c:
                            nk = list(kids)
                            nk[pos] = zero_c
                            put(("lut", imm, nk[0], nk[1],
                                 nk[2]), rep)
                    # R2b: factor a common rotation out
                    forms = []
                    ok = True
                    for kid in kids:
                        fs = [e for e in class_forms(kid)
                              if e[0] == "rotr"]
                        if not fs:
                            ok = False
                            break
                        forms.append(fs)
                    if ok:
                        ks = {f[1] for f in forms[0]}
                        for fs in forms[1:]:
                            ks &= {f[1] for f in fs}
                        for k in ks:
                            bases = []
                            for fs in forms:
                                bases.append(next(
                                    g[2] for g in fs
                                    if g[1] == k))
                            inner = eg.add_enode(
                                ("lut", imm, bases[0], bases[1],
                                 bases[2]))
                            put(("rotr", k, inner), rep)
                    # R4: flatten a child LUT
                    for pos, kid in enumerate(kids):
                        for ken in class_forms(kid):
                            if ken[0] != "lut":
                                continue
                            red = flatten_imm(
                                imm, pos, ken[1], kids,
                                [ken[2], ken[3], ken[4]])
                            if red is not None:
                                atoms, imm3 = red
                                put(("lut", imm3, atoms[0],
                                     atoms[1], atoms[2]), rep)
        eg.rebuild()
        after = (len(eg.enodes), len(eg.class_enodes))
        stats.append({"round": rnd, "enodes": after[0],
                      "classes": after[1],
                      "unions_added": added[0]})
        log(f"  saturation round {rnd}: enodes {after[0]}, "
            f"classes {after[1]}, unions {added[0]}")
        if after == before and added[0] == 0:
            break
        if after[1] > max_classes:
            log("  class cap reached")
            break
    return stats


def dp_costs(eg):
    INF = float("inf")
    reps = [r for r in eg.class_enodes
            if eg.find(r) == r]
    cost = {r: INF for r in reps}
    choice = {}
    for _ in range(10000):
        changed = False
        for rep in reps:
            for en in eg.class_enodes[rep]:
                c = OP_COST[en[0]]
                ok = True
                for ch in enode_children(en):
                    r = eg.find(ch)
                    if cost.get(r, INF) == INF:
                        ok = False
                        break
                    c += cost[r]
                if ok and c < cost[rep]:
                    cost[rep] = c
                    choice[rep] = en
                    changed = True
        if not changed:
            break
    return cost, choice


def extract_dag_cost(eg, root_reps, choice):
    chosen = {}
    stack = list(root_reps)
    while stack:
        r = eg.find(stack.pop())
        if r in chosen:
            continue
        en = choice.get(r)
        if en is None:
            continue
        chosen[r] = en
        for ch in enode_children(en):
            stack.append(ch)
    total = sum(OP_COST[en[0]] for en in chosen.values())
    return total, chosen


def baseline_choices(eg, dag, ids):
    """Map each class arising from the loaded DAG to the
    enode the incumbent computation uses (children resolved
    to current class reps)."""
    choice = {}
    for i, nd in enumerate(dag.nodes):
        op = nd[0]
        if op == "in":
            en = ("in", nd[1])
        elif op == "const":
            en = ("const", nd[1])
        elif op == "add":
            en = ("add", eg.find(ids[nd[1]]),
                  eg.find(ids[nd[2]]))
        elif op in ("rotr", "shr", "shl"):
            en = (op, nd[1], eg.find(ids[nd[2]]))
        elif op == "lut":
            en = ("lut", nd[1], eg.find(ids[nd[2]]),
                  eg.find(ids[nd[3]]), eg.find(ids[nd[4]]))
        else:
            raise ValueError(op)
        choice[eg.find(ids[i])] = eg.canon(en)
    return choice


def union_cost(eg, root_reps, choice):
    chosen = {}
    stack = list(root_reps)
    while stack:
        r = eg.find(stack.pop())
        if r in chosen:
            continue
        en = choice.get(r)
        if en is None:
            continue
        chosen[r] = en
        for ch in enode_children(en):
            stack.append(ch)
    return sum(OP_COST[en[0]] for en in chosen.values()), chosen


def hill_climb_extract(eg, root_reps, choice, max_passes=12):
    """Local search over per-class enode choices, starting
    from the incumbent's choices; only swaps that do not
    increase the exact union DAG cost are kept. The result
    is therefore never worse than the incumbent, and any
    strict improvement is a real candidate form."""
    best, _ = union_cost(eg, root_reps, choice)
    for _ in range(max_passes):
        improved = False
        # classes reachable under current choices
        _, chosen = union_cost(eg, root_reps, choice)
        for rep in list(chosen):
            cur = choice.get(rep)
            for en in eg.class_enodes.get(rep, ()):
                if en == cur:
                    continue
                trial = dict(choice)
                trial[rep] = en
                c, _ = union_cost(eg, root_reps, trial)
                if c < best:
                    best = c
                    choice = trial
                    improved = True
                    break
        if not improved:
            break
    return best, choice


def build_two_rounds_only():
    """Two composed rounds with the schedule words as input
    atoms (no schedule computation). Baseline cost 34."""
    from exp033_common import Dag, K
    d = Dag()
    names = ["a", "b", "c", "d", "e", "f", "g", "h"]
    st = {n: d.inp(n) for n in names}

    def one_round(st, W, kt):
        S1 = d.sigma1(st["e"])
        Ch = d.ch(st["e"], st["f"], st["g"])
        KW = d.add(W, d.const(K[kt]))
        T1 = d.addn([st["h"], S1, Ch, KW])
        S0 = d.sigma0(st["a"])
        Maj = d.maj(st["a"], st["b"], st["c"])
        T2 = d.add(S0, Maj)
        return {"a": d.add(T1, T2), "b": st["a"], "c": st["b"],
                "d": st["c"], "e": d.add(st["d"], T1),
                "f": st["e"], "g": st["f"], "h": st["g"]}

    st1 = one_round(st, d.inp("Wt"), 20)
    st2 = one_round(st1, d.inp("Wt1"), 21)
    return d, {"state": [st2[n] for n in names]}


def run_case(label, dag, roots, ts, log=print):
    base_cost, _ = dag_cost(dag, roots["state"])
    log(f"[{label}] baseline exact DAG cost: {base_cost}")
    eg = EGraph()
    ids = load_dag(eg, dag)
    eg.rebuild()
    root_reps = [eg.find(ids[i]) for i in roots["state"]]
    cost0, choice0 = dp_costs(eg)
    base_tree = [cost0[r] for r in root_reps]
    log(f"[{label}] baseline per-root DP tree costs: "
        f"{base_tree}")
    log(f"[{label}] saturating...")
    stats = saturate(eg, log=log)
    root_reps = [eg.find(r) for r in root_reps]
    cost1, choice1 = dp_costs(eg)
    sat_tree = [cost1[r] for r in root_reps]
    greedy, _ = extract_dag_cost(eg, root_reps, choice1)
    bchoice = baseline_choices(eg, dag, ids)
    # merge: DP choice as fallback for classes the baseline
    # does not cover (should not happen for reachable ones)
    merged = dict(choice1)
    merged.update(bchoice)
    hc, _ = hill_climb_extract(eg, root_reps, merged)
    log(f"[{label}] post per-root DP tree costs: {sat_tree}")
    log(f"[{label}] greedy extraction: {greedy}; "
        f"hill-climb from incumbent: {hc}")
    return {
        "case": label,
        "baseline_exact_dag_cost": base_cost,
        "baseline_dp_tree_cost_per_root": base_tree,
        "saturation_rounds": stats,
        "final_enodes": len(eg.enodes),
        "final_classes": len(eg.class_enodes),
        "post_dp_tree_cost_per_root": sat_tree,
        "greedy_extraction_cost": greedy,
        "hill_climb_extraction_cost": hc,
        "improvement_found": hc < base_cost,
    }


def main():
    ts = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    dag, roots = build_two_rounds(20)
    cases = []
    cases.append(run_case("two_rounds_plus_schedule_pair",
                          dag, roots, ts))
    dag2, roots2 = build_two_rounds_only()
    cases.append(run_case("two_rounds_only", dag2, roots2, ts))
    result = {
        "experiment": "EXP-033 egraph saturation",
        "timestamp_utc": ts,
        "host": "Intel(R) Xeon(R) Platinum 8321HC",
        "cases": cases,
        "improvement_found": any(c["improvement_found"]
                                 for c in cases),
    }
    rp = os.path.join(EXP033, "RAW_RESULTS",
                      f"exp033_egraph_{ts}.json")
    with open(rp, "w") as fh:
        json.dump(result, fh, indent=2)
    print("wrote", rp)
    return 0


if __name__ == "__main__":
    sys.exit(main())
