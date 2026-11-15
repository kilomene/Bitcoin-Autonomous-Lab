# Phase 001, Deliverable 14: CPU Utilization and Threading Analysis

Project: NOVA SHA-X, Research Phase 001, Wave 4.
Subject: the threading model and CPU utilization structure of the whole v0.1.3 node, from source. Sources: ARCHITECTURE_MAP.md section 4 (thread inventory), MINING_EXECUTION_FLOW.md (miner lifetime), and direct re-reading of src/net.cpp, src/main.cpp and src/ui.cpp in the verified tree for this deliverable. No benchmarks were run; every utilization statement is structural (what the code does with the CPU), not measured.

## 1. Thread inventory of the whole node

All threads are Windows `_beginthread` threads; there is no thread pool, no work queue and no job system. Each long-lived subsystem is exactly one thread running an infinite loop with Sleep-based pacing and cooperative shutdown through CheckForShutdown(n), where n is the thread's slot in vfThreadRunning.

| Slot | Thread | Started by | Body | Pacing |
|---|---|---|---|---|
| (main) | GUI / main thread | OS, IMPLEMENT_APP (ui.cpp line 2848) | wxWidgets event loop | Event-driven |
| (none) | ThreadIRCSeed | StartNode (net.cpp line 1004) | irc.cpp | One-shot bootstrap; exits after seeding |
| 0 | ThreadSocketHandler | StartNode (net.cpp line 1010) | net.cpp line 458 | Socket loop |
| 1 | ThreadOpenConnections | StartNode (net.cpp line 1017) | net.cpp line 705 | Sleep-paced connection maintenance |
| 2 | ThreadMessageHandler | StartNode (net.cpp line 1024) | net.cpp line 852 | Message processing loop |
| 3 | ThreadBitcoinMiner | UI at startup (ui.cpp lines 3039 to 3041) or menu toggle (ui.cpp line 828) | net.cpp line 894 wrapper, main.cpp line 2183 BitcoinMiner | None in the search (section 3) |
| (ad hoc) | One-shot UI threads | UI actions | e.g. SendingDialogStartTransfer (ui.cpp line 1434), ThreadRandSendTest (ui.cpp line 3071) | Run to completion |

StopNode (net.cpp line 1037) waits on slots 0, 2 and 3; slot 1 is not in the wait list recorded in ARCHITECTURE_MAP.md section 4, a small asymmetry in the original shutdown design.

## 2. The miner thread

- Host: `ThreadBitcoinMiner(void* parg)`, src/net.cpp line 894. The comment directly above it, line 893, is the version's own scaling statement: "todo: start one thread per processor, use getenv("NUMBER_OF_PROCESSORS")". Verified in the tree for this deliverable. Parallel mining was a recorded intention, never implemented in this version.
- Priority: BitcoinMiner's first act is `SetThreadPriority(GetCurrentThread(), THREAD_PRIORITY_LOWEST)` (main.cpp line 2186). On success it briefly raises itself to THREAD_PRIORITY_NORMAL for the critical section that saves the key and processes the block (lines 2325 and 2337), then restores LOWEST. The miner is designed to be the lowest-priority consumer of the machine: it fills idle cycles and yields to everything, including the GUI it ships inside.
- Lifetime: started once per process if the persisted fGenerateBitcoins setting (or /gen) is on, and once more per menu toggle-on. Toggling off does not kill the thread; it sets the shared flag, which the search notices at its next housekeeping gate and the outer loop then exits. Toggling on again starts a second thread; see section 5 for what that would mean.
- Identity: slot 3 in vfThreadRunning; CheckForShutdown(3) is its cooperative exit.

## 3. CPU utilization structure of the search

The utilization profile is determined by three nested regimes:

1. **Waiting for peers.** Before each template: `Sleep(50)`, then while vNodes is empty, `Sleep(1000)` in a loop (main.cpp lines 2193 to 2199). Utilization in this regime is zero by construction.
2. **Template construction.** The mempool sweep with its per-candidate scratch copies of mapTestPool (MINING_EXECUTION_FLOW.md section 3.4) is bursty, allocation-heavy work on the miner thread under cs_main and cs_mapTransactions. It happens once per template and once per rebuild trigger.
3. **The search loop.** Lines 2310 to 2357: no Sleep call exists anywhere in the loop. Between housekeeping gates (262,144 hashes) the thread executes an unbroken sequence of hash, compare, increment. This is a pure busy loop at the thread's priority: on an otherwise idle machine it consumes one full logical processor continuously; the LOWEST priority means the operating system, not the code, decides what it displaces. After a found block there is one `Sleep(500)` (line 2339), a half-second pause before the next template.

So the version's CPU contract is: one thread, one core at most, saturated while searching, throttled only by the scheduler's priority rules. There is no duty cycling, no hash-rate limiting, no pause API, and no adaptation to system load; the only throttle is the priority class and the operator's toggle.

The remaining Sleep in main.cpp (line 1661, Sleep(100)) is in network message handling, not on the miner path; it is recorded here only to keep the inventory complete.

## 4. What the rest of the node costs the miner

The miner shares the process with the socket, connection and message threads and the GUI. Contention channels visible in source:

- **Locks.** Template construction takes cs_main and cs_mapTransactions; the success path takes cs_main. The message handler takes cs_main for block and transaction processing. A busy network therefore stalls template construction and block acceptance, but never the search loop itself, which holds no lock while hashing (it reads pindexBest and nTransactionsUpdated unlocked, main.cpp lines 2202 and 2351; a stale read costs a late rebuild, not correctness, as analysed in Deliverable 13).
- **Priority.** The network and GUI threads run at normal priority; the miner at lowest. Under load the miner is preempted first, which is the intended behaviour of the design.
- **Memory.** BuildMerkleTree materializes the full flattened tree per template (COINBASE_MERKLE_ANALYSIS.md section 5); at 2009 block sizes this is negligible, recorded for completeness.

## 5. What parallelization the structure would and would not permit

Analysis from the code structure, labelled as analysis:

**Would permit, with local changes only:**

- Multiple miner threads over disjoint nonce ranges of one template. The search state per candidate is the scratch struct tmp (a stack local of BitcoinMiner); the hash primitive is stateless per call. Nothing in the inner loop touches shared mutable state between housekeeping gates. The recorded todo (one thread per processor) is structurally honest: the loop as written is re-entrant per thread.
- Multiple miner threads over disjoint extranonce ranges (the modern answer), since the extranonce is already a per-invocation local (line 2190).

**Would not permit without redesign:**

- Sharing one template build across threads. Template construction reads and writes globals (mapTransactions, the test pool, nFees accumulation) and is not thread-safe as written; parallel threads today would each build their own template. Worse, two threads started by toggling would build templates that differ only by coinbase key (each invocation makes its own CKey), so their work would be disjoint by accident of key freshness, not by any coordination: there is no shared coverage record, no range assignment, and the shared fGenerateBitcoins flag means one toggle-off stops all of them at their next gates.
- Any work distribution across processes or machines. There is no protocol surface for it: no RPC, no job channel, no worker identity. The network protocol carries blocks and transactions, not work.
- Lock-free tip tracking. The unlocked reads of pindexBest are safe only under the single-writer assumption of this design (chain updates under cs_main on other threads, pointer-sized reads); a parallel miner writing chain state would invalidate the argument.

**Utilization ceiling implied by the structure:** one thread at saturation on one logical processor, minus preemption by the node's own threads. On the multi-core machines already common in 2009, the design leaves every other core idle for mining purposes; the todo comment shows the author knew. This is the historical baseline against which NOVA's multi-threaded, multi-backend dispatch (NOVA audit sections 1 and 2) is the modern contrast in Deliverable 20.

## 6. Historical build assumptions bearing on CPU use

From ARCHITECTURE_MAP.md section 2.10: MinGW or Visual C++ builds, Windows only, wxWidgets GUI mandatory, OpenSSL and Berkeley DB linked, Crypto++ vendored as source. The miner's hot loop therefore ran as 32-bit-era Windows code scheduled by the Windows priority system, inside a GUI process. No CPU feature detection exists anywhere in the mining path: BlockSHA256 detects only endianness at runtime (a static int read as a char, main.cpp line 2154); the Transform is whatever the compiler made of the Crypto++ macros for the build target. There is no SSE, no multiple code paths, no dispatch. The contrast with modern Core's SHA256AutoDetect (research/bitcoin_core/CORE_SOURCE_AUDIT.md section 4) and with NOVA's probe-gated dispatch is a Deliverable 20 row.

## 7. Reproduction

Thread inventory: ARCHITECTURE_MAP.md section 4 with per-file lines. Miner priority and sleeps: src/main.cpp lines 2186, 2193 to 2199, 2339 (grep "Sleep" over src/main.cpp returns exactly lines 1661, 2193, 2197, 2339, re-run for this deliverable). Todo comment: src/net.cpp line 893, re-read for this deliverable.

## 8. Limitations

- Utilization is described structurally. Actual 2009-era achieved rates, scheduler behaviour on period hardware, and any comparison to modern measurements are outside this phase's evidence and are not claimed.
- The parallelization analysis is a code-structure argument, not an experiment; no parallel variant of the 0.1.3 miner was built or run, per the phase rule against modifying the original source.
