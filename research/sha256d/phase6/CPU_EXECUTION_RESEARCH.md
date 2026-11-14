# Phase 6, CPU Execution Research

Workstream D's Phase 6 view. Everything here is
labelled: MEASURED (this programme's data),
STATIC (assembly counts), or REASONING (port and
dependency analysis not yet measured; this machine
exposes no performance counters, so port-level
claims cannot be measured directly and are stated
as reasoning with their testable consequences).

## 1. Questions reopened by the Phase 6 corrections

The corrections (Task 2) reopen three execution
questions that earlier documents treated as closed:

1. **Memory costs are execution costs.** With the
   DRAM-only reading withdrawn, the execution
   research agenda is now: register allocation as
   the primary design variable (EXP-018), spill and
   stack traffic as reported metrics in every
   kernel record (already the assembly-audit rule,
   now with the EXP-005 and EXP-011 numbers as the
   baseline accounts), and L1 load/store pressure
   and vector to scalar transfer costs as open
   questions (Y-029, Y-054) rather than dismissed
   ones.
2. **The dependency chain is a property of the
   evaluation, not the function.** Q3 of the
   ceiling report, as corrected, means execution
   research may not assume the conventional round
   chain when pricing a candidate graph: each
   graph brings its own critical path. The discovery
   system's cost model (COMPUTATION_GRAPH_RESEARCH
   .md section 4) therefore carries DAG depth as a
   first-class term.
3. **The ceiling bands price families, not
   silicon.** Execution work that stays inside a
   priced family inherits its band; work that
   changes the family's shape (register-resident
   state, hybrid pipes) must be priced from its own
   assembly census, not argued from the old band.

## 2. What is established about execution here

- MEASURED: a single SHA-NI stream is
  latency-bound; the round pair instruction retires
  two rounds and the chain through T1 into e sets
  the pace. Streams scale 1.06M to 3.30M H/s per
  worker (1 to 4 streams, EXP-003) until spill
  slots and issue contention stop them.
- STATIC: the H-02 hot function is 494
  instructions with 63 RNDS2, 24 MSG1 and 24 MSG2,
  zero frame; the production wrapper is 408
  instructions around libcrypto's transform; the
  MB kernel's loop body is 116 instructions
  covering 8 rounds for all 16 lanes at once; the
  dual-batch body is 239 instructions with 48
  memory state transfers (vmovdqa64).
- MEASURED: at two threads, every research kernel's
  distribution overlaps production's under the
  programme's decision rule (EXP-010); the VM's
  cap (about 1.5 effective CPUs) is part of every
  two-thread measurement and cannot be factored
  out with the covariates available (EXP-010's
  attribution analysis).
- MEASURED: the AVX-512 kernel's rate does not
  track steal the way the scalar control does
  (EXP-010: correlations +0.221 versus -0.521).
  REASONING: the vector kernel is bound by
  something steal does not modulate on the
  timescales sampled: candidates are 512-bit issue
  behaviour on the host (including double-pumping,
  unobservable from the guest), frequency behaviour
  under wide-vector load, or the kernel's own
  memory-backed schedule staging. The discriminating
  experiment is Y-097's heterogeneous pairing plus
  EXP-018's spill audit: if removing state traffic
  removes the anomaly's shape, the third candidate
  was load-bearing.

## 3. Hybrid SHA-NI plus AVX-512: design questions

No hybrid kernel exists; EXP-008 pipelined phases
within the SHA-NI family only. The design questions
a hybrid must answer, in order:

1. **Work partition.** SHA-NI lanes are scalar and
   latency-shaped; AVX-512 lanes are vector and
   throughput-shaped. A hybrid splits the nonce
   space, not the round: interleaving families
   inside one hash would pay vector to scalar
   transfers at every boundary (the exact cost
   class section 1 reopens). REASONING: partition
   by nonce ranges, with each family running its
   proven kernel; the only shared state is the
   template and the candidate queue.
2. **Ratio.** The partition ratio is an empirical
   quantity under the cap: Y-097's three-
   configuration pair bench (MB only, SHA-NI only,
   mixed) is the designed measurement, and its
   result sets the ratio for any larger deployment
   on this VM class.
3. **Schedule supply.** Both families consume the
   same schedule words at different shapes
   (transposed versus sequential). Y-038 and Y-039
   ask whether one family's schedule engine can
   feed the other; both rank low (ranks 107, 108)
   because the transfer cost they must beat is the
   one this section flags as unmeasured. They stay
   designed, not selected.
4. **Confirmation.** A hybrid doubles the candidate
   sources feeding confirmation; EXP-009's
   accounting (confirmation about 2.8 percent of a
   core at regtest density at 6.5M H/s) says the
   merge is cheap at current rates and becomes the
   design constraint only above roughly 100M H/s
   per worker, where Y-105's repricing applies.

## 4. Port and dependency reasoning (REASONING, unmeasured)

Stated as the programme's current best model, with
the understanding that no counter on this machine
can verify port assignments:

- The SHA-NI family's round pair is a single
  instruction with multi-cycle latency; the chain
  a -> Sigma0 -> Maj and e -> Sigma1 -> Ch run in
  parallel down the two sides of the round and join
  at T1/T2. The measured stream scaling (about 3.1x
  from 1 to 4 streams, then flat) is consistent
  with two to three independent chains saturating
  the useful issue width for this instruction mix.
- The MB family's 240 vector ops per hash (set C
  census) at the measured 3.20M H/s confirmation
  median imply about 0.51 vector ops per cycle at
  the guest's nominal 1.5 GHz clock
  (240 x 3.20M / 1.49775G), well under any
  plausible issue bound, which is why set C's low
  end and the measurement can both be right: the
  kernel is not issue-bound at guest clocks, it is
  bound by the same dependency structure plus its
  memory-backed staging (EXP-011's audit).
- The dual-batch body's 48 state transfers are the
  single largest identified removable cost in any
  measured kernel; that is a STATIC fact with a
  MEASURED consequence (EXP-011's instability is
  consistent with state traffic interacting with
  contention), and EXP-018 exists to convert the
  reasoning into a measurement.
- Frequency and double-pumping of 512-bit ops on
  the host are unobservable from this guest. Any
  execution claim that needs them is labelled
  ARCH-BOUND in the ceiling report's terms and
  must not be quoted as a property of "CPUs" in
  general.

## 5. Standing rules adopted for Workstream D

- Every kernel record reports its assembly census
  (hot-function instructions, frame, stack ops,
  state transfers) before its first rate.
- Rates are reported under the decision discipline
  of the day (EXP-017's stack once it exists);
  single-session medians are labelled OBSERVED
  ONCE in any summary that quotes them.
- No port-level claim graduates from REASONING
  without a discriminating experiment named in the
  same paragraph.
