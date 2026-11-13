# Evidence Protocol

The Lab stays private until evidence, not enthusiasm, says it works.

## Evidence levels

- E0, code correctness: genesis block tests pass; the C engine finds
  the genesis nonce inside a small search window. Proves the hashing
  and header code are Bitcoin correct.
- E1, live protocol: a recorded session shows connect, subscribe,
  authorize accepted, set_difficulty, and at least one mining.notify
  job whose prevhash matches the real chain tip at that time (checkable
  against any public block explorer by timestamp).
- E2, live hashing: the same session records hash counts and elapsed
  seconds from the engine, giving a measured hashrate, plus at least
  one share found at or above the session's lowest reached difficulty,
  with its full hash published in the log.
- E3, pool acceptance: the pool answers a mining.submit with result
  true. Only E3 counts as a pool accepted share.
- E4, block: a block found and confirmed on chain. Not expected. If it
  ever happens it will be visible to the whole world by definition.

## Rules

- Logs are append only during a session and committed as recorded.
- Summaries in evidence/SUMMARY files are generated from the JSONL
  logs and state which log they summarize.
- A claim in the README may only cite the highest level actually
  reached, by name (for example: "evidence level E2 as of <date>").
- Failed sessions are kept too. A rejected share is evidence about
  correctness of a different kind and is never deleted to look better.

## Going public

The owner reviews the evidence level reached and decides. The repo
becomes public only on the owner's word, and only with the honest
limits document included and unedited in substance.
