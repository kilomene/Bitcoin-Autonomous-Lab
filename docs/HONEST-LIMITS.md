# Honest Limits

These numbers are part of the project. Removing them to make the Lab
look stronger would be lying, and the Lab exists to produce evidence,
not marketing.

## The math (measured, 2026-11-13)

- This VM: 4 visible CPU cores with SHA-NI, but the VM is capped at
  about 1.5 shared CPUs, and other work shares it. Measured double
  SHA-256 rates in live sessions so far range from 0.12 MH/s under
  load to 0.44 MH/s (session 1: 85,000,000 hashes in 192 seconds of
  engine time). A quiet single-thread benchmark reached about
  0.66 MH/s.
- Bitcoin network: hundreds of exahashes per second (hundreds of
  billions of times more).
- Network difficulty at session 1 (from the job nbits 1701e5ac) is
  about 148 trillion. The expected number of hashes to find one block
  is difficulty times 2^32, about 6.3 x 10^23 hashes.
- At 0.44 MH/s, the expected wait for one block is about 46 billion
  years. The probability of a block on any given day of Lab mining is
  about 6 in 100 trillion. It is a lottery ticket that costs nothing
  extra, not an income plan.
- Pool shares are a different, reachable target: with difficulty
  suggested down to the pool minimum of 1, one accepted share needs
  about 2^32 hashes on average, roughly 3 to 10 hours at the measured
  rates depending on how busy the shared VM is. That is what Phase 2
  long runs aim at: one pool accepted share, recorded as evidence
  level E3.

## What success means here

Success is not a block. Success is:

1. A real pool connection and a real mainnet job.
2. Real hashing at a measured rate, in real time.
3. The best hash found in each run, with its true difficulty computed
   from the hash itself, recorded in the evidence log.
4. Pool responses recorded verbatim in the evidence log, and a share
   counted as accepted only when the pool accepts it.
5. Code that any reviewer can run to reproduce points 1 to 4.

## What this Lab will never claim

- It will never present testnet, regtest, or a low difficulty lab
  target as mainnet mining.
- It will never present a locally found low difficulty hash as a pool
  accepted share unless the pool accepted it.
- It will never project earnings from this hashrate.
- It will never run on hardware the owner does not own or control.

## Cost

$0 to run beyond the VM that already exists. No paid pool account, no
rented hashrate, no purchased miner. Electricity and hardware wear on
this VM are the owner's existing costs, not new spend.
