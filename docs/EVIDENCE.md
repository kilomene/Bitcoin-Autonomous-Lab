# Evidence protocol

Every public claim this lab makes traces to one of:

1. A test suite in `tests/` that anyone can run (`make test-all`, 15 suites).
2. A session evidence file in `evidence/` (JSONL, timestamped UTC).
3. A third party record: the pool's acceptance messages in the session
   log, the public-pool dashboard for the lab address, and the Bitcoin
   blockchain itself for any payout.

## The mainnet share, 2026-11-13

- Authorize accepted: 18:40:48 UTC, worker
  `bc1q528egeqsvv8aa382j43edxskqw6x7zxc2xpcf3.bal1`, pool difficulty 1.
- Share submitted: 18:59:51.027 UTC, job `d45afbd`, nonce 3179128530,
  difficulty 41.35.
- Pool answer: 18:59:51.161 UTC, `accepted: true`, no error.
- Session totals at 19:03 UTC: 6,912,212,992 hashes, 5.18 MH/s
  average, best difficulty 41.35, 1 share submitted, 1 accepted.
- Raw record: `evidence/mainnet-live.jsonl`.

## Dashboard screenshot

`docs/images/pool-dashboard.jpg` is a real screenshot of
https://web.public-pool.io/#/app/bc1q528egeqsvv8aa382j43edxskqw6x7zxc2xpcf3
taken by the project owner on his phone at 10:47 PST on 2026-11-13.
It shows the live mainnet page (block height 975,702, network
difficulty 148.36T) minutes into session 1, before the first share
was credited, so Workers and Best Difficulty read 0. The pool's
statistics host does not answer from this lab's datacenter network
at all (the page sits on a loading skeleton and the API returns
empty from here, verified repeatedly on 2026-11-13), which is why
the owner's own capture is the dashboard evidence of record; the
post-share state (worker bal1, Best Difficulty 41.35) is proven by
the pool's acceptance messages in evidence/mainnet-live.jsonl and
is visible on the same page to any visitor. Generated artwork
(the hero image) is illustration only and is never used as
evidence; workflow diagrams are vector illustrations of the code
paths, drawn from the source.

## What is not claimed

- No block found. No BTC earned. Balance 0.00000000 BTC.
- No GPU hashes (no device). No FPGA board measurements (no board).
- No ASIC silicon metrics (pre-layout only).
