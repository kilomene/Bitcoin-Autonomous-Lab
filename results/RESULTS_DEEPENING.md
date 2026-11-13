# Deepening pass (post Task 006): live results, 2026-11-13

Ordered by the owner after the Tasks 003 to 006 report: go deeper,
bigger, no self-imposed limits. Five advances, each tested live
(tests/test_deepening.py, all passing):

1. C midstate compute backend. mining/cpu/bal_batch.c computes the
   constant first SHA-256 compression of a header once; each nonce
   then costs two compressions via OpenSSL SHA256_Transform (SHA-NI).
   ComputeEngine order is now CUDA, C, Python. Measured through the
   full engine: about 2.0M H/s against 0.6M H/s for the Python
   backend on this VM; the raw library peaks above 8M H/s. Two real
   bugs were found and fixed on the way: OpenSSL 3.0's SHA256_CTX
   layout (h array, not h0..h7 fields), and an O(n squared) ctypes
   buffer read in the batch readers (per-index .raw copies).
2. Event-driven monitoring. MonitorService.run_event_driven blocks
   in Core's waitfornewblock and syncs on wakeup: measured wake and
   sync about 1.0s after a block was mined (the test mines it 1s
   into the wait). The mining engine also speaks GBT longpoll:
   wait_template returned the next height's template about 1.0s
   after the block landed.
3. Watch-only address tracking. blockchain/watch.py: a true
   watch-only descriptor wallet (no private keys), importdescriptors
   for any address, balances, UTXOs, incoming payments, plus a
   scantxoutset cross-check that needs no wallet. Test: a 0.33 BTC
   payment to a watched address was detected, and the scan agreed
   to the sat (33,000,000). The audit trail includes the initial
   createwallet argument bug (private keys enabled) that Core
   correctly refused, fixed by creating the wallet properly.
4. Second peered node. node/peer_node.py runs a full second
   bitcoind (RPC 18543, P2P 18544), peered to the primary. It synced
   the entire chain over P2P (271 blocks at test time) and followed
   newly mined blocks; both nodes agree on the tip hash.
5. Live dashboard. dashboard/server.py (stdlib only) serves a
   self-refreshing page and /api/status JSON: chain, latest blocks,
   mempool, engine sync, mining stats, compute backend and live
   benchmark. Verified over HTTP against the running node.
