# Bitcoin Mining Probability Model

NOVA SHA-X Master Assignment, work package BR-011 (probability and
statistics). This is the complete probability specification for exact
SHA-256d mining: every output the Master Assignment requires, derived
from one stated assumption, with the anchors verified numerically in
RAW_RESULTS/probability_anchors_verify.py (output:
RAW_RESULTS/probability_anchors_verify_output.txt). Companion
documents: research/proof_of_work/PROOF_OF_WORK_AND_DIFFICULTY_
SPECIFICATION.md (the target T and difficulty D used here),
research/phase001/POW_TARGET_MATHEMATICS.md section 8 (the same
model derived against the v0.1.3 source), and mining/probability.py
(the production module; gap analysis in section 8 of this document).

Tier labels: PROVEN means derived here from the stated assumption by
exact mathematics and checked numerically; MEASURED means a number
the programme actually measured, cited to its experiment; OBJECTIVE
means a programme target (500 GH/s, 140 TH/s), which is not a
measurement and is never presented as one.

## 1. The assumption, stated once and carried everywhere

**Random-oracle assumption.** Each SHA-256d evaluation of a distinct
candidate header is treated as an independent draw, uniform on the
integers [0, 2^256). Success for target T is the event hash <= T.

Everything in this document is conditional on that assumption. It is
the standard model for SHA-256d mining analysis; the programme's own
reduced-round bias measurements (bias about 0.49 at 16 rounds, 0.08
at 20 rounds, indistinguishable from noise from 24 rounds up, with
the full construction applying 64 rounds twice) are consistent with
it at full rounds, but consistency is not proof, and no result here
is a statement about SHA-256d itself. Elapsed unsuccessful trials do
not change the probability of the next trial: the waiting-time
distribution below is memoryless, and an expected time is not a
deadline, a promise, or a schedule.

## 2. Per-hash success probability (exact)

The success set {0, 1, ..., T} contains exactly T + 1 integers out of
2^256, so under the assumption of section 1:

```
p(T) = (T + 1) / 2^256                                        (exact)
```

This is an integer statement before it is a probability statement:
the count T + 1 is exact, and equality (hash == T) is a success,
matching the consensus comparison rule hash <= T (see the PoW
specification, section 3).

At the genesis (difficulty-1) target T1 = 0xffff * 2^208 =
2^224 - 2^208 (nBits 0x1d00ffff):

```
p(T1) = 2.3282709094019083e-10          (exact fraction in the script output)
```

## 3. Probability of at least one block

Trials are independent, so the trial index of the first success is
geometric, and for N trials:

```
P(at least one success in N trials) = 1 - (1 - p)^N           (exact form)
                                     = 1 - exp(-N p)          (Poisson form)
```

The Poisson form is the limit form; at mining values of p the two
agree to float precision. Verified anchor (script section B): at
T1 with N = 2^32, both forms give 0.6321149454, absolute difference
4.3e-11. Note this is close to, but not exactly, 1 - 1/e =
0.6321205588; the difference is the gap between p(T1) and exactly
2^-32, quantified in section 4.

With a constant candidate rate R (hashes per second) sustained for
t seconds, N = R t and blocks arrive as a Poisson process with rate

```
lambda_rate = R * p  per second,
P(at least one block within t seconds) = 1 - exp(-R * t * p).
```

In difficulty form (section 4), with D the difficulty of the target:

```
lambda = R / (D * 2^32)  per second,
P(at least one within t) = 1 - exp(-lambda * t)
                         = 1 - exp(-R * t / (D * 2^32)).
```

## 4. Expected hashes, and the exact bridge between the two forms

Expected trials to first success (geometric mean):

```
E[hashes] = 1 / p = 2^256 / (T + 1)                           (exact)
```

At T1: E = 4,295,032,833.000015 (exact fraction in the script
output). The widely used statement "expected hashes at difficulty 1
is 2^32" is an approximation, and this model pins down its error
exactly:

- E(T1) / 2^32 = 1.0000152590218967. The difficulty form
  E = D * 2^32 understates the exact expectation at D = 1 by a
  relative 1.5259e-5.
- The identity E = 2^32 is EXACT not at T1 but at the target
  T_limit = 2^224 - 1 (the 0.1.3 proof-of-work limit,
  bnProofOfWorkLimit): E(T_limit) = 2^256 / 2^224 = 2^32 exactly
  (script section A, asserted in code).
- For a general target, with D = T1 / T, the exact ratio is

  ```
  E_exact / (D * 2^32) = (2^224 / T1) * (T / (T + 1))
                       = 1.0000152590218967 * T / (T + 1),
  ```

  so at every realistic target (T very large) the difficulty form
  understates E by the same relative 1.5259e-5, and the correction
  is a stated constant of this model, not an error term to discover
  later.

**Convention adopted by this model.** The exact form 2^256 / (T + 1)
is authoritative wherever a target is available. The difficulty form
D * 2^32 is used for the worked tables of section 7 (difficulty is
the published quantity), with the 1.5259e-5 understatement stated
once here and inherited by every difficulty-form number below.

Expected time at constant rate R:

```
E[time] = E[hashes] / R  seconds.
```

## 5. Median and percentile times (derived, anchors verified)

The waiting time to the first block is exponential with rate
lambda = R / (D * 2^32) per second (difficulty form; substitute
lambda = R * p for the exact form). Its distribution function is
F(t) = 1 - exp(-lambda t). Setting F(t_q) = q and solving:

```
t_q = -ln(1 - q) / lambda = -ln(1 - q) * (D * 2^32) / R.
```

Since the mean is mu = 1 / lambda, every quantile is a fixed
multiple of the mean:

| Quantile | Multiplier -ln(1-q) | As named constants |
|---|---|---|
| median (q = 0.50) | 0.6931471806 | ln 2 x mean |
| p90 (q = 0.90) | 2.3025850930 | ln 10 x mean |
| p95 (q = 0.95) | 2.9957322736 | ln 20 x mean |
| p99 (q = 0.99) | 4.6051701860 | ln 100 x mean |

Verified (script section C): evaluating the CDF at each multiplier
times the mean returns exactly q (0.5000000000, 0.9000000000,
0.9500000000, 0.9900000000). Interpretation, stated because these
numbers are routinely misread: the median is about 69 percent of
the mean (half of all searches finish sooner, half later); there is
a 10 percent chance a search runs past 2.30 means, a 5 percent
chance past 3.00 means, and a 1 percent chance past 4.61 means,
however long it has already run (memorylessness, section 1).

## 6. Probabilities over calendar periods

For a period of length t seconds at constant R and difficulty D:

```
P(at least one block in the period) = 1 - exp(-R * t / (D * 2^32)).
```

Period lengths used in the tables: day = 86,400 s; week = 604,800 s;
month = 2,629,800 s (365.25 / 12 days); year = 31,557,600 s
(365.25 days); ten years = 315,576,000 s. When lambda * t is small,
P is approximately lambda * t itself (the tables show both); when
lambda * t is large, P saturates at 1 and the informative quantity
is the expected count lambda * t.

## 7. Worked tables

Rates used, each labelled by provenance:

- **R = 20.6 MH/s: MEASURED.** The live production miner's session
  rate on the AMD EPYC 9D25 host with the v512dual backend, from the
  programme record (EXP-030 closure, 2026-11-15). It is a session
  observation on one VM, not a guaranteed rate.
- **R = 500 GH/s: OBJECTIVE.** The programme's minimum system
  throughput target. Not measured anywhere; used here only to show
  what the target would imply if reached.
- **R = 140 TH/s: OBJECTIVE.** The programme's larger system
  objective. Same status as above.

Difficulty values: D = 1 is the genesis target by definition. The
current-era example uses **D = 134,823,837,323,272 (about 134.82
trillion)**, the mainnet difficulty set by the retarget at block
975,744 on 2026-11-14 (public record, checked 2026-11-15). It is an
EXAMPLE value for the model's arithmetic, labelled as such; it
changes every 2016 blocks and no conclusion in this document
depends on its exact digits. All table values are computed by the
verification script (sections E and F); difficulty-form numbers
carry the section 4 understatement of relative 1.5259e-5.

### 7.1 Genesis target (D = 1), exact form, R = 20.6 MH/s (measured)

Expected hashes E = 4,295,032,833.000015 (exact).

| Quantity | Value |
|---|---|
| mean time | 208.4967 s |
| median | 144.5189 s |
| p90 | 480.0815 s |
| p95 | 624.6004 s |
| p99 | 960.1630 s |
| P(at least one in 2^32 trials) | 0.6321149454 |

### 7.2 Genesis target (D = 1), difficulty form

| Rate | Mean | Median | p90 | p95 | p99 |
|---|---|---|---|---|---|
| 20.6 MH/s (measured) | 208.4936 s | 144.5167 s | 480.0742 s | 624.5909 s | 960.1483 s |
| 500 GH/s (objective) | 0.0085899 s | 0.0059541 s | 0.0197791 s | 0.0257331 s | 0.0395581 s |
| 140 TH/s (objective) | 3.0678e-5 s | 2.1265e-5 s | 7.0639e-5 s | 9.1904e-5 s | 1.4128e-4 s |

At D = 1 every calendar period in section 6 has lambda * t in the
hundreds or more at all three rates, so P(at least one) is 1.000000
for day, week, month, year and ten years alike; the expected counts
(lambda for one day) are 414.4 at the measured rate, 1.005828e7 at
500 GH/s and 2.816319e9 at 140 TH/s. (At the genesis target the
historical network of course found blocks far more slowly than the
measured modern rate; the table is the model's arithmetic at the
stated rates, not a historical claim.)

### 7.3 Current-era example: D = 134,823,837,323,272 (2026-11-14)

Expected hashes (difficulty form) E = D * 2^32 = 5.790640e23.

Times to first block:

| Rate | Mean | Median | p90 | p95 | p99 |
|---|---|---|---|---|---|
| 20.6 MH/s (measured) | 2.810990e16 s (8.907490e8 years) | 1.948430e16 s | 6.472544e16 s | 8.420974e16 s | 1.294509e17 s |
| 500 GH/s (objective) | 1.158128e12 s (36,698.86 years) | 8.027531e11 s | 2.666688e12 s | 3.469441e12 s | 5.333376e12 s |
| 140 TH/s (objective) | 4.136171e9 s (131.0674 years) | 2.866975e9 s | 9.523886e9 s | 1.239086e10 s | 1.904777e10 s |

P(at least one block in the period):

| Period | 20.6 MH/s (measured) | 500 GH/s (objective) | 140 TH/s (objective) |
|---|---|---|---|
| day | 3.073652e-12 | 7.460315e-08 | 2.088867e-05 |
| week | 2.151557e-11 | 5.222220e-07 | 1.462115e-04 |
| month | 9.355428e-11 | 2.270731e-06 | 6.356033e-04 |
| year | 1.122651e-09 | 2.724843e-05 | 7.600633e-03 |
| ten years | 1.122651e-08 | 2.724509e-04 | 7.345869e-02 |

Reading of the table, stated plainly because it is the point of the
model: at the measured single-VM rate, a mainnet block at the
example difficulty is an event with expected waiting time of about
890 million years; reaching the 500 GH/s objective would still
leave a mean wait of about 36,700 years; even the 140 TH/s
objective leaves a mean wait of about 131 years and only a 7.35
percent chance of at least one block in ten years. These are the
model's numbers at the stated rates and difficulty, under the
section 1 assumption. They are why the programme's success
criterion is stated as discovering and submitting a valid block,
and why no probability in this document may be reported as progress
toward it.

## 8. Gap analysis: mining/probability.py against this model

The production module (mining/probability.py, EXP-037) implements:

- expected_hashes(difficulty) = D * 2^32 (difficulty form only);
- expected_seconds(hashrate, difficulty) = (D * 2^32) / R, infinite
  at R = 0;
- prob_at_least_one(hashrate, difficulty, seconds) =
  1 - exp(-R t / (D * 2^32)), with alias prob_within;
- prob_within_days(hashrate, difficulty, days).

Its formulas agree with this model wherever they overlap (the
anchors expected_hashes(1) = 2^32 and the probability at one
expected period are pinned by its tests, per EXP-037's
STATISTICAL_MODEL.md). Against the full output set the Master
Assignment requires, the gaps are:

1. **No percentile or median outputs.** The module has no median,
   p90, p95 or p99 function. This is the gap the Master Assignment
   names explicitly.
2. **No exact-target form.** Every function takes difficulty, never
   a target; the exact p = (T + 1) / 2^256 and E = 2^256 / (T + 1)
   are not computable through its API, so the section 4 correction
   (relative 1.5259e-5) cannot be applied by a caller.
3. **No N-trial form.** prob_at_least_one is time-based only; the
   Bernoulli form 1 - (1 - p)^N over a stated number of hashes
   (the natural form for a declared search space, see
   research/nonce_search/NONCE_AND_SEARCH_SPACE_MODEL.md) has no
   entry point.
4. **No period helpers beyond days.** Week, month, year and
   ten-year probabilities require the caller to convert to seconds
   or days by hand.

**Specification of the functions to add** (specification only; no
code was changed by this deliverable, per the wave's rules). All
additions keep the module's existing conventions: difficulty is
validated positive by the existing _check_difficulty; a
non-positive hashrate yields infinite times and zero probabilities,
matching expected_seconds and prob_at_least_one.

| Function | Signature | Definition | Required behaviour |
|---|---|---|---|
| quantile_seconds | (hashrate, difficulty, q) | -ln(1 - q) * (D * 2^32) / R | q must satisfy 0 < q < 1, else ValueError; R <= 0 returns math.inf |
| median_seconds | (hashrate, difficulty) | quantile_seconds(..., 0.5) = ln 2 * (D * 2^32) / R | as above |
| percentile_seconds | (hashrate, difficulty, p) | quantile_seconds(..., p / 100) for p in {90, 95, 99} at minimum; accept any 0 < p < 100 | p outside (0, 100) raises ValueError |
| prob_at_least_one_hashes | (difficulty, n_hashes) | 1 - (1 - p_D)^N with p_D = 1 / (D * 2^32) evaluated stably as -expm1(N * log1p(-p_D)) | N must be a non-negative int; N = 0 returns 0.0 |
| expected_hashes_exact | (target) | 2^256 / (target + 1) as an exact Fraction or int pair | target must be an int with 0 <= target < 2^256, else ValueError |
| prob_at_least_one_exact | (target, n_hashes) | 1 - (1 - (target + 1) / 2^256)^N, computed with Fraction for the probability or log1p float with the exact p | as prob_at_least_one_hashes, target-validated as above |
| prob_within_period | (hashrate, difficulty, period) | prob_at_least_one over the named period lengths of section 6: day 86400, week 604800, month 2629800, year 31557600, ten_years 315576000 seconds | unknown period name raises ValueError |

Acceptance tests the implementation must pass when built (to be
added to the EXP-037 test suite at that time): median_seconds(R, D)
== ln 2 * expected_seconds(R, D) to float precision;
percentile_seconds(R, D, 90) == ln 10 * expected_seconds(R, D), and
likewise ln 20 at 95 and ln 100 at 99; the CDF round trip
prob_at_least_one(R, D, quantile_seconds(R, D, q)) == q for q in
{0.5, 0.9, 0.95, 0.99}; expected_hashes_exact(T1) ==
Fraction(2^256, T1 + 1) with float value 4295032833.000015;
prob_at_least_one_hashes(1, 2^32) == 0.6321205589 to 1e-9 (the
difficulty-form anchor, since p_D at D = 1 is exactly 2^-32);
prob_at_least_one_exact(T1, 2^32) == 0.6321149454 to 1e-9 (the
exact-target anchor of section 3). The two anchors differ in the
fifth decimal place, because p(T1) is smaller than 2^-32 by the
section 4 factor; a test that conflates them fails, which is
exactly why both are pinned separately.

Until those functions exist, any consumer needing a median or a
percentile must compute it from this document's formulas, not from
the module; the module's absence of the outputs is a known,
recorded gap (already noted in the Phase A NOVA audit), not a
silent one.

## 9. What this model does not do

- It does not estimate difficulty, hashrate, or their futures.
  Difficulty changes every 2016 blocks by the retarget rule (PoW
  specification, section 5); a probability over a period longer
  than one retarget interval at a frozen D is a conditional
  statement, labelled by the D it assumes.
- It does not model pooled or shared work: a pool share is a
  candidate meeting a lower, pool-set target, not a block, and its
  probability uses that lower target in the same formulas. Pool
  shares are never evidence of block probability realised.
- It does not convert probabilities into revenue, rankings, or
  progress claims. The programme's success criterion remains a
  discovered, verified, submitted and accepted block.

## 10. Reproduction

Run `python3 research/probability/RAW_RESULTS/
probability_anchors_verify.py`. It prints the exact fractions for
section 2 and 4, both forms of the section 3 anchor, the section 5
quantile multipliers with their CDF round trips, the section 4
bridge ratio, and every number in the section 7 tables. Output of
the run made for this deliverable is saved alongside it as
probability_anchors_verify_output.txt.
