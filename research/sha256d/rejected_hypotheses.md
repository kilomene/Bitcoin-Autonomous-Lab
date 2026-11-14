# Rejected Hypotheses

Kept with their evidence, so the programme does not spend
itself twice on settled questions. A rejection can be
reopened only by evidence of a different kind than what
settled it, cited in a new registry entry.

## R-01: Statistical structure in full-round SHA-256d output can be exploited

Settled by the lab's own measurements (results/RESEARCH.md,
research/statistics.py, reproduced in brief): a parametrized
reduced-round SHA-256 shows a one-bit output bias of about
0.49 at 16 rounds and 0.08 at 20 rounds, indistinguishable
from noise from 24 rounds on (0.0077 at 24, flat through 64).
A fresh 1M-hash sample at full rounds shows bit fraction
0.49998 and worst-byte p about 0.015. Chain winners follow
the geometric law of the search protocol (median scaled
nonce 0.50 observed). Full SHA-256d applies 64 rounds twice;
every statistical foothold measured dies roughly 40 rounds
before the function ends. Registry mirror: H-24, REJECTED.

## R-02: A "lite" screen can confirm blocks faster than the full hash

Settled in results/RESEARCH.md section 5: confirmation IS
the full double SHA-256 at or under target; every output bit
depends on all rounds, and any partial screen produces
candidates that still require the full computation. The
legitimate meaning of "lite" in this lab is wasting none of
the full work (midstate reuse, early exit, exact accounting),
which the production path already does.

## R-03: Compiler flags on the production wrapper hide a large win

Settled by EXP-001 in this pass (compiler_experiments.md):
five gcc flag sets, verified and benchmarked under the shared
harness; none beat production flags, and the generated
wrapper code is instruction-identical across native variants
because the hot compression lives in libcrypto. Reopenable
only for a different source file (a hand kernel, H-02) or a
different compiler (clang, H-12), not for this file.

## R-04: More threads than the tuned count must help

Settled repeatedly on this VM, most recently EXP-000:
scaling past 2 threads buys contention-shaped variance
(4-thread spread 82.6%) under a cap of about 1.5 effective
CPUs. Thread count is a measured setting on this machine
(tune_c_threads), not a direction of improvement. Reopenable
if the VM's cap or core count changes; the probe and the
tuner would show it.

## R-05: The intrinsics kernel's deficit is a tuning detail

Settled by assembly evidence: the compiled intrinsics
library contains zero sha256msg instructions and recomputes
the message schedule in scalar C per nonce (Task 001 audit,
confirmed again in this pass). Its roughly 0.52x rate is a
structural consequence, not a flag or thread setting. The
fix is a different kernel (H-02), not adjustment of this one.

## R-06: Early partial target checks can skip the outer hash

Recorded as H-16's analysis: the target compares the full
outer digest, every word of which depends on all 64 outer
rounds plus feed-forward. No exact partial check exists in
the structure. Any future proposal must begin by refuting
that dependency argument in writing.
