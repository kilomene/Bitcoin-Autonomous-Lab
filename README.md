# Bitcoin Autonomous Lab

A private research lab that mines Bitcoin for real, from an ordinary
CPU virtual machine, and proves it with evidence instead of claims.

Status: private development. Evidence level reached: E2 (see
docs/EVIDENCE-PROTOCOL.md) as of 2026-11-13: a live session connected
to public-pool.io, was authorized, received real mainnet jobs for
block height 975657, and hashed 85,000,000 real headers at a
measured 0.44 MH/s. Next milestone: E3, one pool accepted share at
the pool minimum difficulty of 1 (the client now requests that
difficulty explicitly; without the
request the pool assigns 100000, and a share at difficulty 1 is
expected roughly every 3 to 10 hours at the measured rates).

Lab payout address (public):
bc1q528egeqsvv8aa382j43edxskqw6x7zxc2xpcf3

This repository stays private until the owner reviews the evidence
and says otherwise.

## What this is

- A Stratum V1 client (`src/stratum_miner.py`) that connects to a real
  public pool, receives a real mainnet block job, builds the 80-byte
  block header, submits shares, and logs every protocol event as JSONL.
- A CPU miner engine (`src/bal_miner.c`) that performs double SHA-256
  over block headers. It links OpenSSL, which uses the host CPU SHA-NI
  hardware instructions when present. The current host exposes `sha_ni`
  (AMD EPYC 9D25, 4 cores).
- A correctness suite (`tests/test_known_blocks.py`) that reproduces
  the real genesis block hash from its real header, and reproduces the
  genesis header byte for byte through the Stratum header builder.
- A single-key wallet generator (`src/wallet_gen.py`) that gives the
  Lab its own public payout address. The private key is written only
  outside this repository, with 0600 permissions.

## What this is not

Read docs/HONEST-LIMITS.md before believing anything about returns.
In short: this VM measured about 0.44 MH/s in its first live session
while the Bitcoin network produces hundreds of EH/s. The Lab proves
genuine mining and collects genuine evidence. It does not promise
blocks, shares on demand, or profit. Anyone claiming otherwise about
CPU mining in 2026 is selling something.

## Run it

```
make test        # correctness proofs, including a C engine nonce search
make bench       # live hashrate on this host
make             # build ./bal-miner

python3 src/stratum_miner.py \
  --address <lab-btc-address> \
  --duration 300 \
  --evidence evidence/live-session.jsonl
```

Default pool: public-pool.io on port 21496 (a public solo pool that
accepts small miners). The payout address belongs to the Lab wallet;
the private key never enters this repository.

## Evidence

Every live run writes `evidence/*.jsonl`: connection, subscription,
authorization result, difficulty, each job (prevhash, nbits, ntime),
each share found with its actual difficulty, each submission, and the
pool answer. An accepted share is recorded only when the pool itself
answers true. Session summaries are generated from those logs, never
written by hand.

## Layout

- `src/` miner engine, Stratum client, wallet generator
- `tests/` correctness proofs against known Bitcoin data
- `docs/` design, honest limits, evidence protocol
- `scripts/` run helpers
- `evidence/` live session logs and summaries (no keys, ever)
