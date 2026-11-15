"""Anchor verification for BITCOIN_MINING_PROBABILITY_MODEL.md.

Every probability quantity in the model document is recomputed
here. Exact rational arithmetic (fractions.Fraction) is used
wherever the quantity is rational; the exponential and
logarithm anchors are checked in float and cross-checked
between the exact Bernoulli form 1 - (1-p)^N and the Poisson
form 1 - exp(-N p), which must agree to float precision at
these p values.

Model assumption (stated in the document): SHA-256d outputs
are treated as independent uniform draws on [0, 2^256)
(the random-oracle model). All results are conditional on it.

Run: python3 probability_anchors_verify.py
"""

import math
from fractions import Fraction

TWO256 = 1 << 256

# ---------------------------------------------------------------- targets
T1 = 0xFFFF * (1 << 208)          # genesis / difficulty-1 target (nBits 0x1d00ffff)
T_LIMIT = (1 << 224) - 1          # 0.1.3 bnProofOfWorkLimit = 2^224 - 1

def p_exact(T):
    return Fraction(T + 1, TWO256)

def E_exact(T):
    return Fraction(TWO256, T + 1)

print("=== A. Per-hash probability and expected hashes (exact) ===")
p1 = p_exact(T1)
E1 = E_exact(T1)
print(f"T1                       = {T1}")
print(f"p(T1) exact              = {p1}")
print(f"p(T1) decimal            = {float(p1):.16e}")
print(f"E(T1) exact              = {E1}")
print(f"E(T1) decimal            = {float(E1):.6f}")
print(f"E(T1) / 2^32             = {float(E1 / (1 << 32)):.16f}")
print(f"E(T_limit)               = {E_exact(T_LIMIT)}  (exactly 2^32: "
      f"{E_exact(T_LIMIT) == (1 << 32)})")
print(f"T_limit / T1             = {float(Fraction(T_LIMIT, T1)):.16f}")

print()
print("=== B. P(at least one success in N trials): Bernoulli vs Poisson ===")
def p_at_least_one_exactish(p, N):
    # 1 - (1-p)^N evaluated stably: exp(N * log1p(-p)) in float.
    pf = float(p)
    return 1.0 - math.exp(N * math.log1p(-pf))

def p_at_least_one_poisson(p, N):
    return 1.0 - math.exp(-N * float(p))

for N in (1 << 32,):
    a = p_at_least_one_exactish(p1, N)
    b = p_at_least_one_poisson(p1, N)
    print(f"N = 2^32 at T1: Bernoulli form = {a:.10f}, Poisson form = {b:.10f}, "
          f"abs diff = {abs(a - b):.3e}")
    print(f"1 - 1/e = {1 - 1/math.e:.10f} (the familiar shape; not exact here)")

print()
print("=== C. Quantile anchors for the exponential waiting time ===")
print("Waiting time is exponential with mean mu = E/R (rate lambda = R/E).")
print("CDF F(t) = 1 - exp(-lambda t); quantile t_q = -ln(1-q) / lambda.")
for q, name in ((0.5, "median"), (0.9, "p90"), (0.95, "p95"), (0.99, "p99")):
    mult = -math.log(1.0 - q)
    cdf_at = 1.0 - math.exp(-mult)   # t = mult * mu, so lambda t = mult
    print(f"q = {q:<5} multiplier -ln(1-q) = {mult:.10f}   "
          f"CDF(multiplier x mean) = {cdf_at:.10f}  (must equal q)")
print(f"ln2  = {math.log(2):.10f}  -> median = ln2 x mean")
print(f"ln10 = {math.log(10):.10f}  -> p90    = ln10 x mean")
print(f"ln20 = {math.log(20):.10f}  -> p95    = ln20 x mean")
print(f"ln100= {math.log(100):.10f}  -> p99    = ln100 x mean")

print()
print("=== D. Difficulty form bridge ===")
print("Difficulty D(T) = T1 / T. Exact: E(T) = 2^256 / (T + 1).")
print("Difficulty form: E approx D * 2^32. The two differ by the")
print("factor (T1 + 1) / (2^256 / 2^32) evaluated at the target:")
for label, T in (("T1 (D=1)", T1),):
    exact = float(E_exact(T))
    dform = float(Fraction(T1, T)) * (1 << 32)
    print(f"{label}: exact E = {exact:.6f}, D*2^32 = {dform:.6f}, "
          f"ratio = {exact / dform:.16f}")
print("At smaller targets (larger D) the +1 terms vanish relative to T")
print("and the difficulty form's relative error tends to (T1+1)/2^224 - 1")
print(f"= {float(Fraction(T1 + 1, 1 << 224)) - 1:.6e} plus a 1/T term.")

print()
print("=== E. Worked tables ===")
# Rates used (all stated in the document with provenance):
R_LIVE = 20.6e6        # measured live v512dual session rate, AMD host (programme record)
R_MIN = 500e9          # 500 GH/s: programme minimum objective, NOT a measurement
R_BIG = 140e12         # 140 TH/s: programme larger objective, NOT a measurement
D_NOW = 134_823_837_323_272   # mainnet difficulty after the 2026-11-14 retarget
                              # at block 975,744 (public record; EXAMPLE value)

def report(label, D, rates):
    E = D * (1 << 32)  # difficulty-form expected hashes
    print(f"--- {label}: D = {D:,}, expected hashes (D x 2^32) = {E:.6e}")
    for R, rname in rates:
        mu = E / R                       # mean seconds
        lam_day = R * 86400 / E
        print(f"  R = {rname}: mean = {mu:.6e} s "
              f"({mu / 31557600:.6e} years)")
        print(f"    median = {math.log(2) * mu:.6e} s, "
              f"p90 = {math.log(10) * mu:.6e} s, "
              f"p95 = {math.log(20) * mu:.6e} s, "
              f"p99 = {math.log(100) * mu:.6e} s")
        for period, secs in (("day", 86400), ("week", 7 * 86400),
                             ("month (30.4375 d)", 2629800),
                             ("year (365.25 d)", 31557600),
                             ("ten years", 315576000)):
            lam = R * secs / E
            P = 1.0 - math.exp(-lam)
            print(f"    P(at least one in {period:>16}) = {P:.6e} "
                  f"(lambda = {lam:.6e})")

report("Genesis target", 1, [(R_LIVE, "20.6 MH/s (measured, programme record)")])
print()
report("Difficulty 1 (same target as genesis by definition of D)", 1,
       [(R_MIN, "500 GH/s (objective)"), (R_BIG, "140 TH/s (objective)")])
print()
report("Current-era example (2026-11-14 retarget)", D_NOW,
       [(R_LIVE, "20.6 MH/s (measured, programme record)"),
        (R_MIN, "500 GH/s (objective)"),
        (R_BIG, "140 TH/s (objective)")])

print()
print("=== F. Genesis-target times at the measured live rate (exact p) ===")
mu_exact = float(E1) / R_LIVE
print(f"mean   = {mu_exact:.4f} s")
print(f"median = {math.log(2) * mu_exact:.4f} s")
print(f"p90    = {math.log(10) * mu_exact:.4f} s")
print(f"p95    = {math.log(20) * mu_exact:.4f} s")
print(f"p99    = {math.log(100) * mu_exact:.4f} s")
print("ALL ANCHORS COMPUTED")
