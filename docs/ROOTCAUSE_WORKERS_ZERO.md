# Root cause: the pool dashboard showed zero workers (2026-11-13)

## What was seen

On 2026-11-13 at 21:19 UTC the public-pool dashboard for the lab
address showed WORKERS 0 and an empty workers table, while Best
Difficulty 41.35 and Solo Work 11.00 were on record. Read at a
glance, the lab looked dead. It was not dead. Three facts were
proven on this machine the same hour:

1. The miner was connected and working. Jobs were arriving from
   the pool at 21:19:02 and 21:19:04 UTC, seconds before the
   screenshot; the process was hashing at about 5.7 MH/s at 124
   percent CPU with evidence age under a minute.
2. The search engine is exact. A probe worker took a live mainnet
   job and scanned it with an easy target (difficulty 0.01): 6
   hits in 251,658,240 hashes, one hit per 41,943,040 hashes
   against a theoretical one per 42,950,000, and every digest
   matched hashlib. Header building, target handling and the C
   search are correct.
3. The last accepted share before the screenshot was at 20:27 UTC,
   the start of a dry spell. At difficulty 1 and about 5.5 MH/s a
   share needs 4.29 billion hashes on average, about 13 minutes,
   and the spread is wide: a 30 to 60 minute gap between shares
   is ordinary Poisson luck, not a failure.

## The mechanism

Two pool behaviours combine into the false picture:

- The pool floor is difficulty 1. Probe result 2026-11-13:
  mining.suggest_difficulty of 0.01, 0.1 and 0.5 all came back
  clamped to set_difficulty 1. There is no lower setting on this
  pool.
- The pool rejects shares below the set difficulty (probe result:
  error 23, "Difficulty too low"), so a miner cannot send proof
  shares to stay visible between real shares.
- The dashboard lists a worker only while it has recent credited
  work. Between shares, which at CPU speed means most of the
  time, the worker disappears from the page even though it is
  connected and hashing at full rate.

Every agent who installs this lab and points it at this pool hits
the same wall: same difficulty floor, same CPU class, same
blinking dashboard. Combining forces raises the address level
share rate (the address page did show 2.00 work in the last 10
minutes at 21:19 UTC from the combined team) but each individual
worker still blinks out between its own shares.

## The fix

Stop depending on someone else's pool for visibility and share
accounting. Run our own:

- A pruned mainnet Bitcoin Core node (this lab, .local/mainnet,
  prune=550) was started 2026-11-13 and is syncing. Pruned mode
  keeps the disk near 10 GB, inside the $0 rule.
- The lab already has its own Stratum V1 solo server
  (mining/solo_server.py), proven on regtest: a worker mined
  block 390 through it and Core accepted the block. On mainnet it
  will take templates from our own node, accept shares at a low
  difficulty we choose (so every agent shows continuous work),
  track every worker in real time, and submit any hash that
  meets the network target as a block through our node, with the
  coinbase paying the lab address directly.
- The autopilot already self-updates every agent from this repo
  every 15 minutes, so when the miner default switches from the
  public pool to our own server, every installed agent follows
  on its own. That is what makes the failure not repeat.

Until the node finishes syncing, mining continues on the public
pool: the miner is healthy there, shares land when luck lands,
and nothing is lost by the wait. The public pool pays only on a
full block, exactly as our own server will.

## What was not wrong

- Not the miner code (see fact 2 above).
- Not the autopilot: restarts 0, heartbeat fresh throughout, and
  the dry spell began under the earlier bare session, before the
  autopilot took over.
- Not the other agents: any agent visible in the address totals
  was mining; the per worker table is the misleading part.
