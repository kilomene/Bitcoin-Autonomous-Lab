# Phase 6, Performance Target Model (Workstream E)

Purpose: state, level by level, what the two
programme objectives require in resources, under
stated assumptions, so that every claim about the
gap is arithmetic rather than adjectives. This
model quantifies the gap and the breakthrough
required. It does not declare the targets
impossible, and it does not claim scaling alone
solves them: the tables below are precisely the
resource arithmetic that any scaling claim must
answer.

Objectives (standing, not modified by this model):
500 GH/s minimum system objective; 140 TH/s larger
objective. Ratios: 140 TH/s is 280x 500 GH/s.

## Levels and rates used

Rates are per unit at each level, drawn from the
programme's records, each labelled:

- **Worker** (one thread running one kernel):
  measured best per-worker 3.30M H/s (EXP-003,
  4-stream SHA-NI, 1 thread); AVX-512 MB
  confirmation median 3.20M H/s (EXP-007
  confirmation); production wrapper 1.31M H/s at
  1 thread (EXP-000 baseline). OBSERVED ONCE:
  EXP-011 session A dual-batch figure, not used in
  the tables (evidence class too weak; using it
  would flatter every count by about 2.5x).
- **Physical core**: the implementation-model
  band of PERFORMANCE_CEILING.md section 2:
  6 to 25 MH/s at its defensible assumptions,
  20 MH/s planning figure (roadmap). These are
  MODEL numbers for the implementation families
  priced there, used here as the optimistic case,
  not as measurements.
- **Complete CPU**: a 64-core server CPU at the
  model band per core; a 96-core part scales
  linearly in the table's formula. No such machine
  is available to this programme; the level exists
  so fleet claims can be priced.
- **Multi-CPU node**: 2 sockets x 64 cores.
- **Distributed deployment**: N nodes; the table
  gives N for the node shapes above.
- **This environment**: the VM as measured,
  aggregate best about 6.53M H/s (EXP-007 combined
  session) under a cap of about 1.5 effective CPUs.

Assumptions stated once: sustained rates equal the
labelled rates (no thermal or contention decay);
fleet efficiency 100 percent (any real deployment
multiplies counts by 1/efficiency); power, cost,
and availability are out of scope for this model
and are not zero in reality.

## Required counts for 500 GH/s (5.0e11 H/s)

| Level | Rate used | Units required |
|---|---|---|
| Worker (best measured, 3.30M H/s) | 3.30e6 | about 151,500 workers |
| Worker (MB confirmation, 3.20M H/s) | 3.20e6 | about 156,300 workers |
| Worker (production, 1.31M H/s) | 1.31e6 | about 381,700 workers |
| Physical core (model, 20 MH/s) | 2.0e7 | 25,000 cores |
| Physical core (model band low, 6 MH/s) | 6.0e6 | about 83,300 cores |
| Complete CPU (64 cores at 20 MH/s) | 1.28e9 | about 391 CPUs |
| Multi-CPU node (128 cores at 20 MH/s) | 2.56e9 | about 196 nodes |
| This environment (6.53M H/s aggregate) | 6.53e6 | about 76,600 such VMs |

## Required counts for 140 TH/s (1.4e14 H/s)

Multiply the 500 GH/s counts by 280:

| Level | Units required |
|---|---|
| Worker (best measured) | about 42.4 million workers |
| Worker (production) | about 106.9 million workers |
| Physical core (model, 20 MH/s) | 7.0 million cores |
| Complete CPU (64 cores at 20 MH/s) | about 109,400 CPUs |
| Multi-CPU node (128 cores at 20 MH/s) | about 54,700 nodes |
| This environment | about 21.4 million such VMs |

## What the model says, exactly

1. At every rate this programme has measured, and
   at the model band's optimistic planning figure,
   both objectives are fleet-scale numbers:
   hundreds of CPUs for 500 GH/s at the most
   optimistic per-core model, tens of thousands of
   nodes for 140 TH/s. That is the size of the
   gap, stated as counts.
2. The gap has two independent factors, and the
   model keeps them separate: a per-unit factor
   (measured best worker to model planning figure
   is about 6x; to the band's low end about 2x) and
   a deployment factor (units). Research addresses
   the first; only resources address the second.
   Neither factor may be silently borrowed against
   the other in programme documents.
3. A breakthrough, in this model's terms, is a
   per-unit rate outside the model band's
   assumptions: a computation graph whose per-core
   rate the ceiling sets do not price (they price
   the conventional graph's families), or hardware
   outside the CPU classes modelled. The model
   therefore does not bound what a Workstream A
   result could do; it bounds what the known
   families do, which is the honest statement.
4. Solo-mining context, for scale only: at
   500 GH/s against the difficulty recorded in
   EXP-010's era (about 1.35e14), the expected time
   to one block is on the order of 3.7e4 years;
   at 140 TH/s, on the order of 1.3e2 years. These
   are expectations of a Poisson process at a
   frozen difficulty, quoted so the objectives are
   understood as capability targets, not as a
   mining plan. The lab's live mining continues on
   its own terms regardless (pool shares are its
   feedback signal, not its objective).

## Maintenance rule

When a VERIFIED IMPROVEMENT changes any rate in
the levels table, this model is recomputed and the
change is recorded here with the experiment number.
Model-band changes require a ceiling-report
revision, not an edit to this file alone.
