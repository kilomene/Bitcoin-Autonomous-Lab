# Phase 001, Deliverable 2 (skeleton): Source-Code Architecture Map

Scope: skeleton built from the verified v0.1.3 tree inventoried in SOURCE_INVENTORY.md (SNI RAR, extracted read-only at .local/refs-genesis/extracted/sni_rar/). Every file below is from the actual archive listing. Line numbers cite the extracted tree. This skeleton fixes the file roles and the mining call chain; the full architecture map (classes, dependencies, data flow) is built on top of it by later Phase 001 work.

## 1. File roles

### Root of the archive (release package, not source modules)

| File | Role |
|------|------|
| bitcoin.exe | The compiled v0.1.3 Windows client shipped in the release (6,438,912 bytes) |
| libeay32.dll | OpenSSL crypto library runtime the client links against |
| mingwm10.dll | MinGW threading runtime DLL |
| license.txt | MIT/X11 license text |
| readme.txt | Release readme, headed "BitCoin v0.1.3 ALPHA" |

### src/ core (consensus, chain, wallet, network)

| File | Role |
|------|------|
| src/main.cpp | Core implementation: block and transaction processing, chain index, genesis construction, difficulty retarget, and the CPU miner itself (2,660 lines) |
| src/main.h | Core class declarations: CTransaction, CTxIn, CTxOut, CBlock, CBlockIndex, wallet transaction types; COIN constant at line 18; CBlock::GetHash at line 862; BuildMerkleTree at line 868 |
| src/sha.cpp | SHA-256 implementation (SHA256 class: InitState line 93, Transform line 141, SHA256_Transform line 168) |
| src/sha.h | SHA-256 declarations used by the hashing templates |
| src/util.h | Utility templates including the double-SHA-256 Hash() overloads at lines 339, 349, 364 |
| src/util.cpp | General utilities: logging, time, string and system helpers |
| src/uint256.h | uint256 fixed-width integer type and arithmetic |
| src/bignum.h | CBigNum wrapper over OpenSSL BIGNUM; compact target (SetCompact) and script number encoding |
| src/serialize.h | Serialization framework (CDataStream, SER_DISK/SER_NETWORK); protocol VERSION = 103 at line 22 |
| src/base58.h | Base58 and Base58Check encoding for addresses |
| src/key.h | CKey: OpenSSL EC key pair handling, signing and verification |
| src/script.h | Script opcodes and CScript definition |
| src/script.cpp | Script interpreter (EvalScript) and solver |
| src/db.h | Berkeley DB layer declarations: CTxDB, CWalletDB, address book DB |
| src/db.cpp | Berkeley DB implementation: block index, transactions, wallet and settings persistence (fGenerateBitcoins setting read at lines 570 to 577) |
| src/net.h | P2P declarations: CNode, message header, network addresses |
| src/net.cpp | P2P networking, socket threads, node startup (StartNode line 917) and the miner thread wrapper (ThreadBitcoinMiner line 894) |
| src/irc.h | IRC peer-discovery declarations |
| src/irc.cpp | IRC bootstrap: joins the IRC channel to discover peer addresses |
| src/market.h | Market declarations (early, largely placeholder market feature) |
| src/market.cpp | Market implementation stubs and data structures |
| src/headers.h | Common include umbrella pulling in the standard and library headers |

### src/ user interface

| File | Role |
|------|------|
| src/ui.cpp | wxWidgets GUI implementation and application entry (CMyApp); node startup and miner start/stop from the UI |
| src/ui.h | GUI class declarations |
| src/uibase.cpp | wxFormBuilder-generated UI implementation (dialogs and panels) |
| src/uibase.h | wxFormBuilder-generated UI declarations |
| src/uiproject.fbp | wxFormBuilder project file the uibase sources were generated from |
| src/ui.rc | Windows resource script |
| src/rc/*.bmp, src/rc/*.ico | GUI bitmaps and icons (address book, send, check, bitcoin icon) |

### Build and documentation

| File | Role |
|------|------|
| src/makefile | MinGW makefile |
| src/makefile.vc | Visual C++ makefile |
| src/readme.txt | Developer readme, headed "BitCoin v0.1.3 ALPHA", lists supported compilers |
| src/license.txt | License copy inside src |
| src/obj/ | Empty directory shipped in the archive (build object output location) |

## 2. Mining-relevant files

Primary: src/main.cpp (miner, block assembly, genesis, retarget), src/main.h (block and header types, GetHash, BuildMerkleTree, target comparison), src/sha.cpp and src/sha.h (the hash), src/util.h (Hash() double-SHA-256), src/bignum.h (target decoding), src/serialize.h (header and transaction serialization), src/net.cpp (miner thread host), src/ui.cpp (miner start/stop and the generate toggle), src/db.cpp (miner setting persistence).

Supporting: src/key.h (coinbase key), src/script.h and src/script.cpp (coinbase script), src/db.h (chain storage the miner reads).

## 3. Mining call entry points (actual symbols in this version)

Application and node startup:

- `IMPLEMENT_APP(CMyApp)`, src/ui.cpp line 2848; `CMyApp::OnInit()` line 2850, leading to OnInit2
- `StartNode(string& strError)`, src/net.cpp line 917; called from src/ui.cpp line 3036
- Miner thread first start: `_beginthread(ThreadBitcoinMiner, 0, NULL)`, src/ui.cpp line 3040

Miner thread and main loop:

- `ThreadBitcoinMiner(void* parg)`, src/net.cpp line 894; calls `BitcoinMiner()` at line 900 and catches exceptions
- `BitcoinMiner()`, src/main.cpp line 2183 (section banner comment at line 2135). Single function containing template assembly, the nonce search loop and success handling; there is no separate CreateNewBlock or miner module in this version
- Miner on/off flag: global `fGenerateBitcoins`, src/main.cpp line 49; set by the UI menu handler at src/ui.cpp line 823, which restarts the thread via `_beginthread(ThreadBitcoinMiner, ...)` at src/ui.cpp line 828; persisted in the wallet DB (src/db.cpp lines 570 to 577)

Inside BitcoinMiner (src/main.cpp):

- Difficulty for the candidate: `GetNextWorkRequired(const CBlockIndex* pindexLast)`, src/main.cpp line 685, called at line 2203; retarget clamps to bnProofOfWorkLimit (lines 719 to 720)
- Hash-block padding preparation: `FormatHashBlocks(void* pbuffer, unsigned int len)`, src/main.cpp line 2138, applied to the header buffer and the first hash at lines 2299 to 2300 (an early midstate-style arrangement the full map will document)
- Target for the search: `uint256 hashTarget = CBigNum().SetCompact(pblock->nBits).getuint256();`, line 2307

Validation path a found candidate takes:

- `ProcessBlock(CNode* pfrom, CBlock* pblock)`, src/main.cpp line 1236
- `CBlock::CheckBlock() const`, src/main.cpp line 1154; the proof-of-work checks are inline here (nBits below minimum work, line 1181; hash does not match nBits, line 1183). There is no standalone CheckProofOfWork function in v0.1.3
- `CBlock::AcceptBlock()`, declared src/main.h line 993

Hash path:

- `CBlock::GetHash()`, src/main.h line 862 (header double-SHA-256 over the 80-byte serialization)
- `Hash()` template overloads, src/util.h lines 339 to 380 (double SHA-256 via the SHA256 class)
- `SHA256::Transform(word32 *state, const word32 *data)`, src/sha.cpp line 141

Genesis (full treatment in SOURCE_INVENTORY.md section 5):

- `LoadBlockIndex(bool fAllowNew)`, src/main.cpp line 1420; genesis construction lines 1441 to 1490; expected hash constant `hashGenesisBlock` at line 24

## 4. Differences from modern Bitcoin Core naming (for later deliverables)

- The hash lives in sha.cpp/sha.h, not crypto/sha256.cpp; the class is SHA256 with an explicit Transform over one 64-byte block.
- Mining, block validation, chain state and wallet logic are concentrated in main.cpp/main.h; there are no node/, consensus/ or wallet/ modules.
- Block construction for mining is inline in BitcoinMiner; there is no BlockAssembler and no getblocktemplate (RPC mining does not exist yet in this version).
- Peer discovery at startup uses IRC (irc.cpp), not DNS seeds or addrman.
