# Phase 001, Deliverable 2: Complete Source-Code Architecture Map

Project: NOVA SHA-X, Research Phase 001 (Bitcoin Genesis Engine Reverse Engineering).
Subject: Bitcoin v0.1.3 (January 2009), verified tree inventoried in SOURCE_INVENTORY.md (Satoshi Nakamoto Institute RAR, extracted read-only at `.local/refs-genesis/extracted/sni_rar/`). This document expands ARCHITECTURE_MAP_SKELETON.md into the full map. Every claim cites file and line in that tree. "Proven" means read directly from the cited source in this session; "inferred" is marked where a conclusion goes beyond a single cited line. No original file was modified; no benchmarks were run.

## 1. Shape of the whole system

Bitcoin v0.1.3 is a single Windows GUI executable. There is no daemon, no RPC server, no command-line node mode, and no separation between wallet, node, miner and user interface: all of them are compiled into one binary (`bitcoin.exe`, 6,438,912 bytes in the release archive) from one flat `src/` directory of 19 C++ source/header modules plus generated UI code. The whole codebase is 19,901 lines of `.cpp`/`.h` under `src/` (measured with `wc -l` on the verified tree).

Three structural facts dominate everything else:

1. **One umbrella header.** `src/headers.h` (71 lines) includes the platform and library headers (wxWidgets, OpenSSL, Winsock, Boost) at lines 14 to 50 and then every project header in a fixed order at lines 54 to 70: serialize.h, uint256.h, util.h, key.h, bignum.h, base58.h, script.h, db.h, net.h, irc.h, main.h, market.h, uibase.h, ui.h. Nearly every `.cpp` includes only `headers.h`, so the module graph below is a logical graph, not an include graph: physically, everything sees everything.
2. **Global state, not objects with owners.** Chain state, the mempool, the wallet and the key store are file-scope globals in `src/main.cpp` lines 14 to 51 (see section 4). Synchronization is by global `CCriticalSection` mutexes (`cs_main`, `cs_mapTransactions`, `cs_mapWallet`, `cs_mapKeys`, `cs_vNodes`).
3. **Two different SHA-256 implementations coexist.** General hashing (block hashes, transaction hashes, merkle nodes) uses OpenSSL's `SHA256()` one-shot and `SHA256_CTX` API through the `Hash()` templates in `src/util.h` lines 339 to 380. The miner's inner loop alone uses a vendored, public-domain extract of Crypto++ 5.5.2 in `src/sha.h`/`src/sha.cpp` (file header at sha.h lines 1 to 6: "SHA routines extracted as a standalone file from: Crypto++ ... Version 5.5.2"), because it needs the raw single-block `Transform` primitive that OpenSSL's API does not expose. Proven from source: the only `CryptoPP::` uses outside sha.cpp/sha.h are in `BlockSHA256`, src/main.cpp lines 2153 to 2179.

## 2. File-by-file map

Line counts are from the verified tree. Roles marked proven are from reading the file in this session; files only skimmed for declarations are marked as such.

### 2.1 Release package root (not compiled modules)

| File | Role |
|------|------|
| bitcoin.exe | The shipped compiled v0.1.3 Windows client |
| libeay32.dll | OpenSSL crypto runtime the client links against (the makefile links `-l eay32`, src/makefile line 24) |
| mingwm10.dll | MinGW threading runtime |
| license.txt, readme.txt | MIT/X11 license; release readme headed "BitCoin v0.1.3 ALPHA" |

### 2.2 Foundations (no project dependencies of their own beyond libraries)

| File | Lines | Contents and key symbols |
|------|-------|--------------------------|
| src/serialize.h | 1151 | Serialization framework. Protocol `VERSION = 103` (line 22). Stream-type flags `SER_NETWORK`, `SER_DISK`, `SER_GETHASH`, `SER_SKIPSIG`, `SER_BLOCKHEADERONLY` (lines 37 to 43). `IMPLEMENT_SERIALIZE` macro (lines 48 to 81) generates GetSerializeSize/Serialize/Unserialize from one statement list. Primitive types serialize by raw memory copy: `WRITEDATA(s, obj)` is `s.write((char*)&(obj), sizeof(obj))` (line 105), so integers land on the wire in host byte order (little-endian on x86). Compact-size (variable length) encoding: `WriteCompactSize` line 161, `ReadCompactSize` line 192 (thresholds: under 253 one byte; 253 plus uint16; 254 plus uint32; 255 plus uint64). `CFlatData`/`FLATDATA` (lines 226 to 227) serialize a raw memory range. `CDataStream` class at line 696; `CAutoFile` at line 1054. |
| src/uint256.h | 750 | `base_uint<BITS>` template (line 26) over `unsigned int pn[WIDTH]` (line 30): the value is stored as little-endian 32-bit limbs, pn[0] least significant. Comparisons scan from the most significant limb down (operator< at line 214, operator<= at line 226). `GetHex()` (line 294) prints the byte-reversed form, which is the displayed form of every hash. `begin()`/`end()` (lines 340 to 350) expose the raw memory bytes. Serialization writes the raw `pn` array (lines 360 to 363). `uint160` (line 397) and `uint256` (line 509) are copy-paste instantiations. |
| src/bignum.h | 498 | `CBigNum : public BIGNUM` (line 49), an OpenSSL arbitrary-precision integer. Two jobs matter here: compact target conversion, `SetCompact` (line 257) and `GetCompact` (line 269), implemented through OpenSSL's MPI format; and script number encoding, `getvch()` (line 246, little-endian sign-magnitude with the byte order reversed out of MPI form) and `setvch()` (about line 230). Also `getuint256()`/`setuint256()` bridge to uint256 (used by the miner at main.cpp line 2307). |
| src/util.h / src/util.cpp | 399 / 379 | Macros and helpers used everywhere: `foreach` is BOOST_FOREACH and `loop` is `for (;;)` (util.h lines 21 to 22); `BEGIN(a)`/`END(a)` (lines 23 to 24) produce the raw byte range of an object, the basis of all hashing. Double-SHA-256 `Hash()` overloads (util.h lines 339, 349, 364) and `SerializeHash()` (line 383), `Hash160()` (line 392, SHA-256 then RIPEMD-160). util.cpp: `RandAddSeed` (line 57), `error()` logging (line 157), `GetTime()` (line 336, seconds since epoch), `GetAdjustedTime()` (line 343, local time plus the median peer offset), `AddTimeData()` (line 348). On Windows, `printf` is redirected to `OutputDebugStringF` (util.h lines 31 to 33). |
| src/sha.h / src/sha.cpp | 177 / 554 | Vendored Crypto++ 5.5.2 SHA family (SHA-1, SHA-224, SHA-256, SHA-512 classes declared in namespace CryptoPP, sha.h lines 125 to 176). Only SHA-256 is used by Bitcoin code. `SHA256::InitState` (sha.cpp line 93) loads the standard initial state; `SHA256_K[64]` round constants at sha.cpp lines 99 to 114; `SHA256::Transform(word32 *state, const word32 *data)` (sha.cpp line 141) compresses exactly one 64-byte block, with a 16-word rolling schedule (`W[16]`, the `blk2` macro) and partially unrolled rounds. A slower alternative transform is present but commented out (sha.cpp line 168 onward). `ByteReverse` for word32 uses the x86 `bswap` instruction under GCC (sha.h lines 86 to 90). |
| src/key.h | 156 | `CKey` (line 43): an OpenSSL EC key on secp256k1 (`EC_KEY_new_by_curve_name(NID_secp256k1)`, line 51). `MakeNewKey()` (line 75), `GetPubKey()` (line 109, 65-byte uncompressed point via i2o_ECPublicKey), plus SetPrivKey/GetPrivKey, Sign, Verify. This is the coinbase payout key type. |
| src/base58.h | 201 | Base58 and Base58Check encode/decode for addresses (and reused by irc.cpp for peer address encoding). |

### 2.3 Script

| File | Lines | Contents |
|------|-------|----------|
| src/script.h | 597 | `opcodetype` enum (line 17): OP_0 = 0, OP_PUSHDATA1 = 76, OP_PUSHDATA2 = 77, OP_PUSHDATA4 = 78, OP_1NEGATE = 79, OP_1 = 81 through OP_16 = 96, OP_CHECKSIG in the crypto group (its numeric value 0xac follows from the enum order; the genesis scriptPubKey ends in byte 0xac, verified in our recomputation). `CScript : public vector<unsigned char>` (line 327). Push machinery: `push_int64`/`push_uint64` (lines 330 to 356) emit OP_1..OP_16 single bytes for values 1 to 16 and minus 1, otherwise a CBigNum byte-vector push; `operator<<(opcodetype)` (line 408); `operator<<(const vector<unsigned char>&)` (line 443) emits a length-prefixed push (direct length byte under 76, OP_PUSHDATA1 to 255, OP_PUSHDATA2 above); `operator<<(const CBigNum&)` (line 437) pushes `getvch()`. `GetOp` parser at line 473. Serialization of a CScript is the vector serialization: compact-size length then raw bytes (serialize.h lines 429 to 458 pattern). |
| src/script.cpp | 1127 | The interpreter: `EvalScript` (line 44), a stack machine over the opcode set; `Solver` template matcher (line 913) and `Solver` scriptSig builder (line 975); `SignSignature` (line 1090); `VerifySignature` (line 1115), which evaluates scriptSig concatenated with OP_CODESEPARATOR and scriptPubKey (line 1126). Signature hashing (SignatureHash) is in this file's earlier portion. |

### 2.4 Core: main.h and main.cpp

`src/main.h` (1317 lines) declares the consensus and wallet data types; `src/main.cpp` (2660 lines) implements chain processing, the mempool, the wallet glue, message processing and the miner. This pair is the centre of the system: there are no separate consensus, wallet, or miner modules.

Classes in main.h, in declaration order:

| Class | Lines | Role |
|-------|-------|------|
| CDiskTxPos | 80 | (nFile, nBlockPos, nTxPos) disk pointer to a transaction; serialized FLATDATA |
| CInPoint | 132 | In-memory pointer (CTransaction*, index) used by mapNextTx |
| COutPoint | 147 | (hash, n) reference to a previous output; FLATDATA serialized (32-byte hash then uint32) |
| CTxIn | 193 | prevout, scriptSig, nSequence (default UINT_MAX); serialize block at line 219 |
| CTxOut | 274 | int64 nValue, scriptPubKey; serialize block at line 292 |
| CTransaction | 357 | nVersion, vin, vout, nLockTime; serialize block at line 371; GetHash() = SerializeHash (line 393); IsCoinBase() (line 437): exactly one input whose prevout IsNull; CheckTransaction() (line 442); GetMinFee() (line 504): (1 + bytes/1000) * CENT, free under 10 KB when fDiscount |
| CMerkleTx | 598 | CTransaction plus hashBlock, vMerkleBranch, nIndex: a transaction with its merkle proof into a block |
| CWalletTx | 660 | CMerkleTx plus vtxPrev, mapValue (string metadata: to/from/message), vOrderForm, receive time and spent flags: the wallet's record type |
| CTxIndex | 738 | Database record: CDiskTxPos pos plus vSpent, one CDiskTxPos per output (null until spent) |
| CBlock | 805 | Header fields, vtx, and the mutable cached vMerkleTree; full treatment in BLOCK_HEADER_SPECIFICATION.md. GetHash() line 862, BuildMerkleTree() line 868, CheckBlock()/AcceptBlock() declared lines 992 to 993 |
| CBlockIndex | 1009 | In-memory chain node: phashBlock, pprev, pnext, nFile, nBlockPos, nHeight, and a copy of the header fields. GetMedianTimePast() (line 1086, median of up to 11 ancestors) |
| CDiskBlockIndex | 1133 | CBlockIndex as stored in blkindex.dat, with hashPrev/hashNext replacing pointers; its GetBlockHash() rebuilds a CBlock header and hashes it (line 1170) |
| CBlockLocator | 1212 | Exponentially spaced list of block hashes for fork negotiation with peers |

Constants in main.h: MAX_SIZE = 0x02000000 (32 MB, line 17), COIN = 100000000 (line 18), CENT = 1000000 (line 19), COINBASE_MATURITY = 100 (line 20), bnProofOfWorkLimit = ~uint256(0) >> 32 (line 22), i.e. the easiest allowed target is 2^224 minus a correction, whose compact form is 0x1d00ffff.

Global state (definitions src/main.cpp lines 14 to 51, declarations main.h lines 26 to 43 and 1310 to 1317):

- `mapBlockIndex` (uint256 to CBlockIndex*), `pindexGenesisBlock`, `pindexBest`, `hashBestChain`, `nBestHeight`: the chain.
- `mapTransactions` (uint256 to CTransaction) plus `mapNextTx` (COutPoint to CInPoint) and counter `nTransactionsUpdated`: the mempool. There is no mempool class; these two maps are it.
- `mapOrphanBlocks`, `mapOrphanBlocksByPrev`, `mapOrphanTransactions`, `mapOrphanTransactionsByPrev`: holding areas for out-of-order data.
- `mapWallet`, `mapKeys`, `mapPubKeys`, `keyUser`: the wallet and key store.
- Settings: `fGenerateBitcoins` (miner on/off, main.cpp line 49), `nTransactionFee` (line 50), `addrIncoming` (line 51).

Function groups in main.cpp (definition lines):

| Group | Functions |
|-------|-----------|
| Keys and wallet glue | AddKey (65), GenerateNewKey (75), AddToWallet (92), AddToWalletIfMine (149), EraseFromWallet (162), GetBalance (2386), SelectCoins (2410), CreateTransaction (2514), CommitTransactionSpent (2595), SendMoney (2625) |
| Orphan transactions | AddOrphanTx (185), EraseOrphanTx (197) |
| Mempool | CTransaction::AcceptTransaction (406), AddToMemoryPool (481), RemoveFromMemoryPool (497), CMerkleTx/CWalletTx accept variants (548, 564), ReacceptWalletTransactions (583), relay helpers (599, 621) |
| Input connection | CTransaction::DisconnectInputs (739), ConnectInputs (772), ClientConnectInputs (873). ConnectInputs is the single function that validates spends, verifies signatures via script.cpp, checks double spends against CTxIndex.vSpent, enforces coinbase maturity, and tallies fees (nTxFee = value in minus value out, lines 848 to 855) |
| Chain | CBlock::DisconnectBlock (918), ConnectBlock (937, includes the coinbase value ceiling check at line 953: vtx[0] value out must not exceed GetBlockValue(nFees)), Reorganize (974), AddToBlockIndex (1072) |
| Block validation entry | CBlock::CheckBlock (1154), CBlock::AcceptBlock (1192), ProcessBlock (1236). Proof of work is checked inline in CheckBlock at lines 1180 to 1184; there is no CheckProofOfWork function in this version |
| Difficulty | CBlock::GetBlockValue (675, subsidy; see TRANSACTION_RECONSTRUCTION.md), GetNextWorkRequired (685, retarget every 2016 blocks, timespan clamped to a factor of 4, result clamped to bnProofOfWorkLimit) |
| Chain loading | LoadBlockIndex (1420), including genesis construction (1456 to 1490); PrintBlockTree (1496) |
| Block files | GetAppDir (1344), OpenBlockFile (1379), AppendBlockFile (1399): blocks are appended to blk0001.dat style files with a 4-byte message-start prefix and a size (CBlock::WriteToDisk, main.h line 919) |
| Network message handling | AlreadyHave (1592), ProcessMessages (1611), ProcessMessage (1690; its command dispatch, lines 1705 to 2015, covers version, addr, inv, getdata, getblocks, tx, review, block, getaddr, checkorder, submitorder, reply; there is no verack in this version), SendMessages (2056) |
| Miner | FormatHashBlocks (2138), BlockSHA256 (2156), BitcoinMiner (2183). Full treatment in MINING_EXECUTION_FLOW.md |

### 2.5 Persistence: db.h and db.cpp

`src/db.h` (420 lines) and `src/db.cpp` (608 lines) wrap Berkeley DB (the makefile links `-l db_cxx`, src/makefile line 23). `CDB` (db.h line 26) is the base environment/database handle. Databases:

| Class | db.h line | File | Contents |
|-------|-----------|------|----------|
| CTxDB | 251 | blkindex.dat | Block index (CDiskBlockIndex by hash), transaction index (CTxIndex by txid), hashBestChain. Methods include ReadTxIndex/UpdateTxIndex/AddTxIndex/EraseTxIndex (lines 259 to 262), ContainsTx (263), WriteBlockIndex (269), LoadBlockIndex (272) |
| CWalletDB | 337 | wallet.dat | Wallet transactions, keys, the default key, address book entries, and settings. This is where fGenerateBitcoins is read at startup (db.cpp lines 565 to 577, inside CWalletDB::LoadWallet) and where the UI writes it (ui.cpp line 825) |
| CAddrDB | 319 | addr.dat | Known peer addresses (LoadAddresses, db.h line 331) |
| CReviewDB | 280 | (reviews) | Product review records for the market feature |
| CMarketDB | 306 | (market) | Market product records |

Blocks themselves are not in Berkeley DB; they are in the flat blk*.dat files, located through CDiskTxPos/CBlockIndex file and position fields.

### 2.6 Networking: net.h and net.cpp

`src/net.h` (856 lines) and `src/net.cpp` (1067 lines) implement a Winsock TCP peer network.

- Wire framing: `pchMessageStart` = {0xf9, 0xbe, 0xb4, 0xd9} (net.h line 54); `CMessageHeader` (line 56): 4-byte magic, 12-byte command, uint32 nMessageSize, serialized FLATDATA.
- `CAddress` (net.h line 132): ip, port, services, last-seen time; DEFAULT_PORT = htons(8333) (net.h line 13), the port the node binds in StartNode.
- `CInv` (net.h line 320): inventory vector entry, type MSG_TX = 1 or MSG_BLOCK = 2 (lines 303 to 304) plus a hash.
- `CNode` (net.h line 434): per-peer socket, receive/send CDataStream buffers (vRecv, vSend), message assembly, `PushMessage` overloads (lines 632 to 711) that frame and queue outbound messages, inventory relay helpers `RelayInventory` (line 766) and `RelayMessage` (line 775). Peers live in the global `vNodes` vector with `cs_vNodes` (net.h lines 420 to 421).
- Threads in net.cpp, each a thin exception-catching wrapper (the `2` suffixed function is the body): ThreadSocketHandler (440/458, accepts connections and pumps sockets), ThreadOpenConnections (687/705, maintains outbound connections), ThreadMessageHandler (834/852, calls ProcessMessages/ProcessMessage in main.cpp and SendMessages), ThreadBitcoinMiner (894, hosts the miner; section 5).
- `StartNode(string&)` (net.cpp line 917): WSAStartup, resolve local host, create and bind the nonblocking listen socket, listen, discover the external IP, then start ThreadIRCSeed (line 1004), ThreadSocketHandler (1010), ThreadOpenConnections (1017), ThreadMessageHandler (1024). It does not start the miner; the UI does (section 3).
- `StopNode()` (net.cpp line 1037): sets fShutdown, waits for the thread-running flags, WSACleanup. `CheckForShutdown(int n)` (line 1059): called cooperatively by every thread; if fShutdown is set it clears the caller's running flag and ends the thread with _endthread().

### 2.7 Peer discovery: irc.h and irc.cpp

`src/irc.h` (7 lines) declares the IRC seed thread. `src/irc.cpp` (288 lines) implements bootstrap-by-IRC: `ThreadIRCSeed` connects to an IRC server, joins the Bitcoin channel, encodes this node's address into its nickname (`EncodeAddress`, line 17: the address packed and Base58Check-encoded with a "u" prefix), and decodes other users' nicknames back into CAddress records (`DecodeAddress`, line 27) to seed outbound connections. There are no DNS seeds and no addrman in this version (proven: no such symbols exist in the tree; peer addresses come from addr.dat, IRC, and addr messages).

### 2.8 Market: market.h and market.cpp

`src/market.h` (182 lines) and `src/market.cpp` (264 lines) declare CUser (market.h line 25), CReview (line 72), CProduct (line 120) and the order/review plumbing of an early built-in marketplace (the "checkorder" and "reply" network messages in ProcessMessage belong to it). It is not on the mining or consensus path; its database classes (CReviewDB, CMarketDB) sit in db.h alongside the chain databases. Included here for completeness of the map; nothing in the miner references it (proven by symbol search: no market symbol appears in BitcoinMiner or the validation path).

### 2.9 User interface: ui.h/ui.cpp, uibase.h/uibase.cpp

| File | Lines | Role |
|------|-------|------|
| src/ui.h | 418 | GUI class declarations: CMainFrame, dialogs, CMyApp |
| src/ui.cpp | 3228 | wxWidgets application and main window logic. `IMPLEMENT_APP(CMyApp)` (line 2848) makes the GUI the process entry point. CMyApp::OnInit (2850) delegates to OnInit2 (2885), the startup sequence of section 3. Menu handler OnMenuOptionsGenerate (line 821) is the miner toggle. Shutdown (called from OnExit, line 3081) tears the node down |
| src/uibase.h / src/uibase.cpp | 720 / 1806 | wxFormBuilder-generated frame and dialog layouts (from src/uiproject.fbp); pure presentation, regenerated code |
| src/ui.rc, src/rc/* | | Windows resources: icons and bitmaps |
| src/uiproject.fbp | | wxFormBuilder project the uibase sources were generated from |

The UI is not a shell over a daemon: it is the process. All long-running work (network, miner) runs on worker threads the UI and StartNode spawn, and the UI reads the same globals (mapWallet, mapBlockIndex, fGenerateBitcoins) directly.

### 2.10 Build files

`src/makefile` (MinGW) and `src/makefile.vc` (Visual C++). The MinGW LIBS line (makefile lines 22 to 26) links Berkeley DB (db_cxx), OpenSSL (eay32), wxWidgets 2.8 (wxmsw28 core/html/richtext and wxbase28), and Winsock (ws2_32) plus the usual Win32 libraries. Boost is header-only here (foreach, lexical_cast, tuple, array, included from headers.h lines 46 to 50). Historical build assumptions in detail are a separate Phase 001 topic; the map only records what the link line proves: Windows-only, wxWidgets GUI required, OpenSSL and Berkeley DB as the two substantive external dependencies, Crypto++ not linked (its SHA-256 is vendored as source in sha.cpp).

## 3. Node startup flow (proven, in call order)

1. Process entry: `IMPLEMENT_APP(CMyApp)`, ui.cpp line 2848. wxWidgets calls `CMyApp::OnInit()` (line 2850), which wraps `OnInit2()` (line 2885) in an exception handler.
2. Single-instance guard: a wxSingleInstanceChecker named from HOMEPATH (lines 2901 to 2932); a second instance focuses the first and exits.
3. Argument parsing: `ParseParameters` (line 2864) into mapArgs with "/" style switches (lines 2937 to 2962): /datadir sets strSetDataDir, /proxy, /debug, /dropmessages, /loadblockindextest (a test path that loads the block index, prints the tree and exits).
4. Data loading (lines 2970 to 2991), each timed and accumulated into strErrors: `LoadAddresses()` (addr.dat via CAddrDB), `LoadBlockIndex()` (main.cpp line 1420: CTxDB::LoadBlockIndex fills mapBlockIndex; if empty and fAllowNew, the genesis block is constructed, asserted against hashGenesisBlock, written to disk and added to the index, lines 1431 to 1492), `LoadWallet()` (wallet.dat via CWalletDB::LoadWallet, db.cpp line 583; this restores mapKeys, mapWallet, the default key into keyUser, and the settings fGenerateBitcoins, nTransactionFee, addrIncoming, db.cpp lines 565 to 577).
5. `ReacceptWalletTransactions()` (ui.cpp line 3009) returns the wallet's unconfirmed transactions to mapTransactions.
6. /gen handling (lines 3021 to 3027): `/gen` or `/gen=1` sets fGenerateBitcoins = true, overriding the persisted setting for this run.
7. Main window: CMainFrame is created and shown (lines 3033 to 3034).
8. `StartNode(strErrors)` (ui.cpp line 3036; net.cpp line 917) starts sockets and the IRC, socket, open-connections and message-handler threads (section 2.6).
9. Miner start (ui.cpp lines 3039 to 3041): if fGenerateBitcoins is set, `_beginthread(ThreadBitcoinMiner, 0, NULL)`.
10. Optional test sends (/send, /randsendtest, lines 3046 to 3075).

Shutdown: CMyApp::OnExit (line 3081) calls Shutdown, which leads to StopNode (net.cpp line 1037): fShutdown is set and every thread exits cooperatively at its next CheckForShutdown call; the miner checks at main.cpp lines 2194, 2198 and 2346 and in its wait loops.

## 4. Threading model at the map level

All threading is Windows `_beginthread` (process.h, included from headers.h line 31). There is no thread pool and no work queue; each subsystem is one long-lived thread running an infinite loop with Sleep-based pacing and cooperative shutdown via CheckForShutdown(n), where n is the thread's slot in the global vfThreadRunning array (slots: 0 socket handler, 1 open connections, 2 message handler, 3 miner; StopNode waits on slots 0, 2, 3 at net.cpp lines 1042 to 1052).

| Thread | Started by | Body | Owns |
|--------|-----------|------|------|
| GUI/main | OS via IMPLEMENT_APP | CMyApp / CMainFrame event loop | Window, dialogs, direct reads of wallet and chain globals |
| ThreadIRCSeed | StartNode (net.cpp 1004) | irc.cpp | Peer discovery bootstrap; exits after seeding |
| ThreadSocketHandler | StartNode (net.cpp 1010) | net.cpp 458 | Listening socket, per-node socket I/O, message byte assembly |
| ThreadOpenConnections | StartNode (net.cpp 1017) | net.cpp 705 | Choosing and opening outbound peer connections |
| ThreadMessageHandler | StartNode (net.cpp 1024) | net.cpp 852 | ProcessMessages/ProcessMessage and SendMessages for all nodes |
| ThreadBitcoinMiner | UI at startup (ui.cpp 3040) or from the menu toggle (ui.cpp 828) | net.cpp 894 wrapper, main.cpp 2183 BitcoinMiner | Block assembly and the nonce search; runs at THREAD_PRIORITY_LOWEST (main.cpp line 2186) |
| Ad hoc | UI actions | e.g. SendingDialogStartTransfer (ui.cpp 1434), ThreadRequestProductDetails (ui.cpp 2423), ThreadRandSendTest (ui.cpp 3071) | One-shot UI operations |

Concurrency rules that matter for mining (details in MINING_EXECUTION_FLOW.md): the miner thread is a single thread. The source says so itself: the comment directly above ThreadBitcoinMiner at net.cpp line 893 reads "todo: start one thread per processor, use getenv("NUMBER_OF_PROCESSORS")", an unimplemented intention, proven from source. Multiple miner threads can exist only if the user toggles generation off and on (each toggle-on starts a new thread; the loop condition is the shared fGenerateBitcoins flag, so toggling is the only multiplication path, and the threads would assemble duplicate work from the same globals; inferred from ui.cpp lines 821 to 829 and main.cpp line 2191).

Shared-state synchronization: `CRITICAL_BLOCK(cs_main)` wraps chain and wallet mutation (for example the miner's success path, main.cpp lines 2326 to 2336, and its transaction collection, lines 2240 to 2241 nesting cs_main and cs_mapTransactions). The miner reads pindexBest and nTransactionsUpdated without holding a lock while searching (main.cpp lines 2202, 2351), which is safe only because a stale read costs a restarted template, not correctness; the restart checks are part of the loop design.

## 5. Module dependency summary

Reading direction: A depends on B if A's code calls or includes B's facilities (physically everything includes headers.h; these are the logical uses).

- ui.cpp depends on: net.cpp (StartNode, ThreadBitcoinMiner), main.cpp (LoadBlockIndex, LoadWallet via db.cpp, globals, SendMoney), uibase (frames), db.cpp (WriteSetting for the miner toggle).
- net.cpp depends on: main.cpp (ProcessMessages, ProcessMessage, SendMessages, BitcoinMiner, mapBlockIndex/pindexBest for locators), irc.cpp (ThreadIRCSeed), db.cpp (CWalletDB for the addrIncoming setting), util.
- irc.cpp depends on: net.h (CAddress), base58.h (address encoding), sockets.
- main.cpp depends on: serialize.h/uint256.h/bignum.h (types and target math), util.h (Hash, time), sha.h (Crypto++ Transform, miner only), script.cpp (VerifySignature from ConnectInputs), key.h (CKey for coinbase and wallet), db.h (CTxDB, CWalletDB), net.h (CNode, CInv, RelayInventory/RelayMessage for ProcessBlock and relay paths).
- db.cpp depends on: main.h types (CBlockIndex, CTxIndex, CWalletTx serialization), Berkeley DB.
- script.cpp depends on: script.h, bignum.h (script numbers and signature math), key.h (ECDSA verify), serialize.h.
- Everything depends on serialize.h and util.h; sha.cpp depends on nothing in the project (standalone vendored file, sha.h lines 1 to 6).

Data-flow spine for a mined block: miner (main.cpp) assembles a CBlock from mapTransactions plus a fresh coinbase, searches with sha.cpp, and on success hands the block to ProcessBlock (main.cpp), which validates via CheckBlock (main.h GetHash over util.h Hash/OpenSSL, BuildMerkleTree, GetNextWorkRequired), stores via AcceptBlock (WriteToDisk to blk*.dat, AddToBlockIndex to blkindex.dat via CTxDB), and advertises via RelayInventory (net.h) to CNode peers managed by net.cpp threads.

## 6. Boundaries, stated plainly

- Wallet boundary: there is none at the API level. Wallet data (mapWallet, mapKeys) is global in main.cpp and persisted by db.cpp's CWalletDB; the UI, the miner (coinbase key), and transaction creation all touch it directly under cs_mapWallet/cs_main.
- Database boundary: db.cpp is the only file that talks to Berkeley DB; block bodies bypass it into flat files. Chain reads during mining go through CTxDB (ConnectInputs) and the in-memory mapBlockIndex.
- Network boundary: net.cpp/net.h own sockets and framing; main.cpp owns message semantics (ProcessMessage). The miner touches the network only through the vNodes.empty() gate (main.cpp line 2195: it will not mine with zero peers) and through ProcessBlock's relay on success.
- IRC boundary: irc.cpp is used once at startup for peer discovery and never by consensus or mining code afterwards.
- UI boundary: the UI owns process lifetime and the miner on/off switch, and nothing else in the consensus path; validation and mining never call into ui.cpp.

## 7. What is absent (proven by symbol search over the verified tree)

No CheckProofOfWork function, no CreateNewBlock or BlockAssembler, no getblocktemplate or any RPC server, no mining module file, no DNS seeds, no addrman, no separate daemon target, no unit-test suite in the archive. The modern names from research/bitcoin_core/ must not be projected onto this tree; each later Phase 001 deliverable uses this version's actual symbols, as catalogued above.
