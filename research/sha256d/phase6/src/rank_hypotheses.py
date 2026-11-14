#!/usr/bin/env python3
"""Phase 6, Task 3: numerical ranking of all 108
Y-series hypotheses.

Method (published in HYPOTHESIS_RANKING.md; this script
is the method, so the table is reproducible):

Seven factors, each on a 0..5 scale:
  S  potential speedup, read from the registry's own
     Impact statement (negligible 0.5, small 1.5,
     small-to-moderate 2.5, moderate 3.5,
     moderate-to-large 4.5, breakthrough-class claim 5,
     indirect/methodology 1). S measures the size of
     the claim, never its credibility; credibility is
     P's job, so a large implausible claim cannot win
     on S alone.
  P  mathematical plausibility, from the registry's
     Confidence (high 5, medium 3, low 1), with
     evidence overrides applied after EXP-016.
  C  implementation cost, inverted (low 5, medium 3,
     high 1), from the registry's Cost.
  V  verification difficulty, inverted (Difficulty
     low 5, medium 3.5, high 2, very high 1).
  R  expected research value: what the programme
     learns whether the hypothesis wins or loses
     (methodology multipliers and graph-changing
     questions score high; one-off tweaks score low).
     Assigned per entry below; default 3.
  D  dependency readiness (5 = testable now with
     existing code and data; lower when it waits on
     an unbuilt predecessor or an environmental
     event). Assigned per entry below; default 5.
  X  duplication risk, inverted (5 = clearly new;
     lower when close to a tested idea, even with a
     stated new element). Assigned per entry below;
     default 4.

Score = 20 * (0.25 S + 0.20 P + 0.15 C + 0.10 V
              + 0.15 R + 0.05 D + 0.10 X), range 0..100.

Evidence overrides applied in this run (dated
2026-11-14, after EXP-016): Y-065 and Y-075 have P
set to 0: EXP-016 refuted both as work reductions
(their closure value is carried in R). Y-090, whose
mechanism is conditional on Y-065 or Y-075, has D
set to 1.

Outputs: analysis/hypothesis_ranking.json and
analysis/ranking_table.md (the full table, sorted).
"""

import json
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
PHASE6 = os.path.dirname(HERE)
EO = os.path.join(os.path.dirname(PHASE6), "extreme_optimization")
REG = os.path.join(EO, "HYPOTHESIS_REGISTRY_Y.md")

DIFF_V = {"low": 5.0, "medium": 3.5, "high": 2.0, "very high": 1.0}
CONF_P = {"high": 5.0, "medium": 3.0, "low": 1.0}
COST_C = {"low": 5.0, "medium": 3.0, "high": 1.0}

# Research value R (default 3), dependency readiness D
# (default 5), duplication inverted X (default 4).
R_OV = {
    "Y-001": 4.0, "Y-004": 3.5, "Y-007": 4.5, "Y-008": 3.0,
    "Y-012": 4.0, "Y-013": 3.5, "Y-014": 5.0, "Y-015": 5.0,
    "Y-016": 3.5, "Y-018": 3.0, "Y-019": 4.5, "Y-023": 4.5,
    "Y-037": 4.0, "Y-050": 5.0, "Y-052": 3.5, "Y-062": 3.5,
    "Y-065": 4.0, "Y-075": 4.0, "Y-081": 3.0, "Y-088": 3.5,
    "Y-090": 2.0, "Y-097": 3.5, "Y-100": 4.0, "Y-101": 5.0,
    "Y-102": 4.5, "Y-103": 4.5, "Y-108": 4.0,
    "Y-009": 2.5, "Y-011": 2.5, "Y-017": 2.5, "Y-020": 2.5,
    "Y-028": 2.5, "Y-042": 2.5, "Y-055": 2.5, "Y-064": 3.0,
    "Y-074": 2.5, "Y-078": 2.5, "Y-087": 2.5, "Y-089": 2.5,
    "Y-092": 2.5,
}
D_OV = {
    "Y-013": 4.5, "Y-018": 3.0, "Y-031": 4.0, "Y-044": 4.0,
    "Y-046": 4.0, "Y-049": 4.0, "Y-054": 4.0, "Y-061": 4.0,
    "Y-066": 2.0, "Y-067": 4.0, "Y-090": 1.0, "Y-091": 4.5,
    "Y-093": 5.0, "Y-095": 2.0, "Y-096": 4.0, "Y-098": 4.5,
    "Y-099": 3.5, "Y-100": 4.0, "Y-104": 2.0,
}
X_OV = {
    "Y-001": 4.5, "Y-003": 4.0, "Y-013": 4.0, "Y-025": 4.0,
    "Y-031": 3.0, "Y-047": 4.0, "Y-049": 3.5, "Y-056": 4.0,
    "Y-057": 3.5, "Y-065": 4.0, "Y-075": 4.5, "Y-093": 3.5,
    "Y-094": 4.0, "Y-095": 2.0, "Y-098": 3.5, "Y-101": 4.5,
    "Y-102": 4.5, "Y-103": 5.0, "Y-104": 4.5, "Y-108": 5.0,
    "Y-019": 5.0, "Y-050": 5.0,
    "Y-009": 3.0, "Y-011": 3.0, "Y-017": 3.0, "Y-020": 3.0,
    "Y-028": 3.0, "Y-042": 3.0, "Y-055": 3.0, "Y-074": 3.0,
    "Y-078": 3.0, "Y-087": 3.0, "Y-089": 3.0, "Y-092": 3.0,
}
P_OV = {"Y-065": 0.0, "Y-075": 0.0}  # EXP-016 refutation


def impact_to_S(text):
    t = text.lower()
    if "unproven breakthrough" in t or "potentially moderate to large" in t:
        return 5.0
    if t.startswith("indirect"):
        return 1.0
    if "moderate to large" in t:
        return 4.5
    if "small to moderate" in t:
        return 2.5
    if t.startswith("moderate"):
        return 3.5
    if t.startswith("small"):
        return 1.5
    if t.startswith("negligible"):
        return 0.5
    if t.startswith("speculative"):
        return 2.0
    return 2.0


def main():
    txt = open(REG).read()
    parts = re.split(r"\n### (Y-\d+): ", txt)
    rows = []
    for i in range(1, len(parts), 2):
        yid, body = parts[i], parts[i + 1]
        title = body.split("\n")[0].strip()
        flat = re.sub(r"\s+", " ", body)
        m = re.search(
            r"Workstream (\w+) / Difficulty (very high|high|medium|low)"
            r" / Confidence (high|medium|low) / Cost (low|medium|high)",
            flat)
        ws, diff, conf, cost = m.groups()
        imp = re.search(r"- Impact: ([^\n]+)", body).group(1)
        S = impact_to_S(imp)
        # nuanced S overrides where the Impact text is
        # density- or shape-conditional:
        if yid == "Y-036":
            S = 3.0
        if yid == "Y-005":
            S = 2.0
        P = P_OV.get(yid, CONF_P[conf])
        C = COST_C[cost]
        V = DIFF_V[diff]
        R = R_OV.get(yid, 3.0)
        D = D_OV.get(yid, 5.0)
        X = X_OV.get(yid, 4.0)
        score = 20 * (0.25 * S + 0.20 * P + 0.15 * C
                      + 0.10 * V + 0.15 * R + 0.05 * D
                      + 0.10 * X)
        rows.append({
            "id": yid, "title": title, "workstream": ws,
            "S": S, "P": P, "C": C, "V": V, "R": R, "D": D,
            "X": X, "score": round(score, 1),
        })
    rows.sort(key=lambda r: (-r["score"], r["id"]))
    for rank, r in enumerate(rows, 1):
        r["rank"] = rank
    os.makedirs(os.path.join(PHASE6, "analysis"), exist_ok=True)
    with open(os.path.join(PHASE6, "analysis",
                           "hypothesis_ranking.json"), "w") as fh:
        json.dump({"method": "rank_hypotheses.py, weights "
                             "S.25 P.20 C.15 V.10 R.15 D.05 X.10, "
                             "score = 20 x weighted sum",
                   "rows": rows}, fh, indent=2)
    lines = [
        "| Rank | ID | Hypothesis | WS | S | P | C | V | R | D | X | Score |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        lines.append(
            f"| {r['rank']} | {r['id']} | {r['title']} | "
            f"{r['workstream']} | {r['S']:g} | {r['P']:g} | "
            f"{r['C']:g} | {r['V']:g} | {r['R']:g} | {r['D']:g} | "
            f"{r['X']:g} | {r['score']:.1f} |")
    with open(os.path.join(PHASE6, "analysis",
                           "ranking_table.md"), "w") as fh:
        fh.write("\n".join(lines) + "\n")
    for r in rows[:15]:
        print(r["rank"], r["id"], r["score"], r["title"][:60])
    print("...")
    for r in rows[-5:]:
        print(r["rank"], r["id"], r["score"], r["title"][:60])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
