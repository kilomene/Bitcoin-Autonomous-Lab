# EXP-051 predeclaration (written before any measurement)

Written: 2026-11-16T18:09Z, before the mechanism was measured
and before the Gate 4 campaign ran. The campaign manifest
records this file's sha256 at campaign start (the EXP-049
audit note N-1 lesson: preserve the pre-campaign statement as
its own file). EXP-051 is portfolio NOVA-ER-0011, register
R-33.

## Hypothesis

At regtest and solo difficulties, a bounded prefetch queue
between the template engine and the search, keyed to the
EXP-025 layered identity, removes most of the prepare-side
bubble at template transitions: while search runs on the
current template, a background longpoll feed prepares the
next template; at the transition the prepared candidate is
served only after its identity is recomputed from scratch
and its previousblockhash is confirmed to still be the
node's best block. At mainnet difficulty the effect is nil
(the prepare cost is amortised over an astronomical search)
and this entry claims NOTHING there.

## Predeclared success criteria (Gate 4, category F form)

Measured through the EXP-040 harness shape (production
MiningEngine.mine_cycle against the regtest node, stage
timers, EXP-036 verification of every accepted block),
scenarios A (empty) and B (loaded, 500 transactions),
3 sessions per arm per scenario, arms = synchronous
(prefetch disabled, the current production behaviour) and
prefetch (queue enabled), strictly one timed run at a time.
Non-search overhead per block is defined as cycle wall time
minus the search stage time, the EXP-040 definition.

- H1 (correctness, hard gate): ZERO stale serves anywhere:
  no served candidate whose recomputed layered identity
  differs from the identity it was prepared under, and no
  served candidate built on a previousblockhash that is
  not the node's best block at serve time. Any single stale
  serve fails the experiment regardless of speed.
- H2 (effect, loaded scenario B): the pooled median
  non-search overhead per block in the prefetch arm is at
  least 15 percent below the pooled median in the
  synchronous arm. (EXP-040 priced the removable stages at
  loaded difficulty: GBT 38.0 ms + prepare 19.7 ms of a
  206.3 ms overhead; the serve check keeps one identity
  recomputation plus one best-hash call on the critical
  path, so the predeclared margin is set below the naive
  28 percent stage share.)
- H3 (attribution): at least half of the prefetch arm's
  scenario B runs are queue-served, and in served runs the
  combined (gbt + prepare) critical-path stage median is
  under 5 ms. Without H3, an H2 pass is not attributable
  to the queue.

## Predeclared failure criteria

- Any stale serve (H1) fails the experiment outright.
- H2 or H3 missed: the mechanism is reported as not
  measurably justified at loaded regtest difficulty; the
  starvation counter alone does not justify it (portfolio
  failure criterion).

## Scope statements declared in advance

- The starvation counter (prefetch_starved) counts template
  transitions where no valid prepared work was ready,
  including the first cycle of a cold engine. It is a
  separated EXP-037 statistics category, never summed into
  any combined total.
- The solo server path (mining/solo_server.py) does not
  consume MiningEngine: it has its own JobRefresher thread
  that pre-builds the next job server-side. Wiring this
  queue into that seam would be a redesign of a different
  interface, so EXP-051 covers the GBT engine path (which
  the solo MINER side also uses when it mines through
  MiningEngine) and declares the solo server seam out of
  scope rather than forcing it.
- Disabled by default (opt-in, EXP-025/EXP-034 style): with
  the queue disabled, behaviour is byte-for-byte the
  current behaviour, and the disabled path is the rollback
  surface.
