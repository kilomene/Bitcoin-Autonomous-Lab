# Design

## Goal

Mine Bitcoin for real from this VM, in real time, with evidence that a
third party can verify. Private until the evidence exists.

## Architecture

1. Pool layer (Python, `src/stratum_miner.py`)
   - TCP connection to a public Stratum V1 pool.
   - mining.subscribe, mining.authorize, mining.notify handling.
   - Header construction: coinbase assembly from coinb1, extranonce1,
     extranonce2, coinb2; merkle root through the branch list; version,
     prevhash, merkle root, ntime, nbits, nonce packed into 80 bytes.
   - Difficulty to target conversion using the standard difficulty-1
     target.
   - Share submission and pool response handling.
   - JSONL evidence logging of every event.

2. Hash layer (C, `src/bal_miner.c`)
   - Multi-threaded nonce search over caller supplied ranges.
   - Double SHA-256 via OpenSSL. On SHA-NI hosts (this one included)
     OpenSSL dispatches to hardware SHA instructions.
   - Reports FOUND with nonce and display hash, or NONE with an exact
     hash count and elapsed time so hashrate is measured, not guessed.

3. Identity layer (`src/wallet_gen.py`)
   - The Lab has its own single-key P2WPKH address so any pool payout
     (a block on a solo pool) has a destination that belongs to the
     project, not borrowed from a third party.
   - Key material lives outside the repository at 0600. Only the
     public address is committed.

4. Verification layer (`tests/`)
   - Genesis block reproduction: the known header must hash to the
     known block hash, and the Stratum builder must reproduce the
     header byte for byte.
   - C engine search test: searching a small nonce window around the
     genesis nonce must find it, with the genesis hash.

## Job handling

A clean job from the pool kills any in-flight nonce search immediately
(the coordinator polls the job generation while the engine runs). Stale
work is never submitted as fresh.

## Difficulty handling (learned live, 2026-11-13)

public-pool.io assigns difficulty 100000 to a new worker by default,
which a CPU would need decades to reach even for one share. Sending
mining.suggest_difficulty before authorize changes the assignment:
the pool clamps any suggestion at or below its minimum to difficulty
1. One accepted share at difficulty 1 needs about 2^32 hashes on
average, about 2 to 3 hours at the measured rate. The client sends
the suggestion by default and logs both the request and the pool
answer, so the difficulty in force is always in the evidence.

The engine also reports the best (smallest) hash of every search
chunk. The coordinator converts it to a true difficulty and logs a
best_share event whenever it improves. Best share is honest progress
evidence; it is never described as an accepted share.

## Why a public solo pool first

- No account, no KYC, no capital. Fits the standing $0 rule.
- The worker name is the Lab address, so authorization and any payout
  are self describing.
- Solo means a found block pays the Lab address in full (minus the
  pool fee). It also means no steady share income: evidence comes from
  the protocol transcript and any accepted shares, not from payouts.

## Phases

- Phase 1 (this build): correct engine, real pool session, evidence
  log, private repo.
- Phase 2: longer unattended runs under a supervisor, automatic
  evidence summaries, difficulty aware reporting (best share found).
- Phase 3: evaluate pointing the same engine at additional small hosts
  the owner controls. Only hosts the owner owns. No third party
  hardware, ever.
- Public release only after Phase 1 evidence is reviewed by the owner.
