# Evidence Summary

Generated from the JSONL session logs in this directory. Every number
below is read from a log line, not written from memory.

Evidence level reached: E2 (live protocol plus live hashing with a
measured best hash). No share has been accepted by a pool yet, so no
E3 claim is made anywhere in this repository.

Session 1 note: pool difficulty was the default 100000, because the
client did not yet send mining.suggest_difficulty. Session 2 sent the
suggestion and the pool set difficulty 1, its minimum.

Hashrate note: this VM is capped at about 1.5 shared CPUs and runs
other work, so the measured rate varies by session (a quiet
single-thread benchmark reached about 0.66 MH/s; session 1 measured
0.44 MH/s; session 2 measured 0.12 MH/s under load).

## evidence/session-20261113-live1.jsonl
- Started: 2026-11-13T09:24:12.638552+00:00 pool public-pool.io:21496 worker bc1q528egeqsvv8aa382j43edxskqw6x7zxc2xpcf3.bal1
- Authorized by pool: True
- Pool difficulties seen: [100000]
- Jobs received: 9 (first job d200ded, last job d206a23)
- Total hashes counted by engine: 85000000
- Approx hashrate from counted chunks: 441746 H/s (varies with shared VM load)
- Best hash difficulty reached: None
- Best hash: None
- Shares submitted: 0, accepted: 0

## evidence/session-20261113-live2.jsonl
- Started: 2026-11-13T09:31:20.853581+00:00 pool public-pool.io:21496 worker bc1q528egeqsvv8aa382j43edxskqw6x7zxc2xpcf3.bal1
- Authorized by pool: True
- Pool difficulties seen: [1]
- Jobs received: 17 (first job d134bfc, last job d13fcfe)
- Total hashes counted by engine: 45000000
- Approx hashrate from counted chunks: 115729 H/s (varies with shared VM load)
- Best hash difficulty reached: 0.007983930397964866
- Best hash: 0000007d3feb242113e8500651e933b79a8cf71420b4d893da7c731ee2b12dba
- Shares submitted: 0, accepted: 0
