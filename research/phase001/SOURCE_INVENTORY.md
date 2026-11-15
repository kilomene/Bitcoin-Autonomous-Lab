# Phase 001, Deliverable 1: Historical Source Inventory

Project: NOVA SHA-X, Research Phase 001 (Bitcoin Genesis Engine Reverse Engineering).
Task: acquire the original Bitcoin v0.1.3 source (January 2009 era), verify its historical integrity, and inventory it. Acquisition and verification performed 2026-11-15. No original file was modified; no NOVA code was changed; no benchmarks were run.

Storage: archives and extracted trees live outside the pushed tree at `.local/refs-genesis/` (downloads/, extracted/sni_rar/, extracted/obl_targz/), extracted trees set read-only. Machine-readable manifests are in `research/phase001/RAW_RESULTS/`.

## 1. Provenance: every source tried

| # | Source | What it served | Result |
|---|--------|---------------|--------|
| 1 | Satoshi Nakamoto Institute CDN, https://cdn.nakamotoinstitute.org/code/bitcoin-0.1.3.rar | bitcoin-0.1.3.rar, 2,127,418 bytes, RAR v4 solid, Win32 host flag, retrieved 2026-11-15 17:08 to 17:09 UTC, HTTP 200 | THE verified v0.1.3 tree (below). Archive SHA-256: 3d73b1a80ce775e0cec7f9476644a6bf9b361e99567fd143807ad1d1c81b1756 |
| 2 | Original Bitcoin Laboratory (bitcoin-lab.org) GitHub release "Bitcoin-v0.1.3", bitcoin-0.1.3.tar.gz | tar.gz, 4,153,845 bytes, SHA-256 d24469a4894ad40554fab111b823faf2aa57a42d901f38089a1bb87753c93c9b, matching the SHA256SUMS file published with the release | NOT the historical v0.1.3. Its own RELEASE.txt states the tree is composed from the v0.1.0 source plus a 10-line patch for a new 2026 experimental chain (own genesis, magic, port). serialize.h carries VERSION = 101 and its readme is the v0.01 text. Retained only as a cross-check for the 0.1.0-derived file majority. It is not relabelled as 0.1.3 anywhere in this inventory. |
| 3 | diyhpl.us archive directory (Bryan Bishop), https://diyhpl.us/~bryan/irc/bitcoin-satoshi/ | Directory listing; bitcoin-satoshi.zip (33,869 bytes, SHA-256 604aa299e9ff82151e719b7a097b9b9452d5614700bb61b2cb96de5e0eb9e0d2) contains emails only | This is the source the ChainBulletin researchers state they obtained their 0.1.3 copy from. The 0.1.3 archive itself is not present in the directory today (only bitcoin-0.1.0.rar and bitcoin_src1.rar are). Its value here is the published per-file CRC32 manifest (source 4). |
| 4 | ChainBulletin, "Satoshi Used Timestamps For Early Bitcoin Source Code Versioning" (chainbulletin.com) | Published RAR listings with per-file size and CRC32 for bitcoin-0.1.0.rar and a diff listing for bitcoin-0.1.3.rar, from a separately obtained copy | Independent cross-check manifest. 47 of our 48 files match its published CRC32 values exactly (details in section 3). |
| 5 | SourceForge, https://sourceforge.net/projects/bitcoin/files/Bitcoin/ | HTTP 404 | Historical path no longer exists (project reorganized). Nothing obtained. The original January 2009 distribution point is gone. |
| 6 | Internet Archive Wayback Machine, CDX queries for three SourceForge download URL patterns for bitcoin-0.1.3.rar | No captures returned | Nothing obtained. |

Full machine-readable provenance: RAW_RESULTS/archive_provenance.json.

## 2. Version evidence inside the source

The SNI tree identifies itself as v0.1.3 in three independent places:

- `readme.txt` line 1, exact text: `BitCoin v0.1.3 ALPHA`
- `src/readme.txt` line 1, exact text: `BitCoin v0.1.3 ALPHA`
- `src/serialize.h` line 22, exact text: `static const int VERSION = 103;`

Supporting internal evidence: archive member timestamps follow the pattern documented by ChainBulletin (file time encodes the release that last changed the file: 01:00 = 0.1.0, 01:01 = 0.1.1, 01:02 = 0.1.2, 01:03 = 0.1.3). Members last changed in 0.1.3 carry 2009-01-12 01:03 (src/net.cpp, bitcoin.exe, readme.txt, src/readme.txt); members changed in 0.1.2 carry 2009-01-11 01:02 (src/db.cpp, src/irc.cpp, src/util.cpp, src/net.h). src/serialize.h is stamped 01:00 despite containing VERSION = 103, the reset anomaly ChainBulletin also recorded.

## 3. Integrity verification

Three independent checks were run against the SNI tree:

1. Extraction integrity. For all 48 files, the CRC32 computed from the extracted bytes equals the CRC32 stored in the RAR header. Zero mismatches. (RAW_RESULTS/sni_rar_tree_manifest.json)
2. Published-manifest cross-check. ChainBulletin's published CRC32 values (0.1.3 diff listing for the 10 files that changed in 0.1.3; 0.1.0 listing for the files that did not change) match our computed CRC32 for 47 of 48 files. The single exception is src/ui.h: no 0.1.3 CRC32 for it was published in the article. Its size differs from the 0.1.0 archive (11,922 vs 11,887 bytes), so it changed in 0.1.2 or 0.1.3; it is carried as verified by checks 1 and 3 plus internal consistency, and flagged here explicitly as the one file without a published-value match. (RAW_RESULTS/published_crc_crosscheck.json)
3. Independent-tree comparison. Against the OBL tar tree (v0.1.0 base, source 2): 35 files are byte-identical, 11 differ, 2 files exist only in the RAR (libeay32.dll, mingwm10.dll, which the statically linked OBL build omits) and 1 only in the tar (RELEASE.txt, OBL's own document). Every differing file is accounted for: db.cpp, util.cpp, serialize.h, ui.h and net.cpp differ because genuine 0.1.3 changed them after 0.1.0; main.cpp, net.h and irc.cpp differ both by the 0.1.3 changes and by OBL's own 10-line chain patch; the two readmes and bitcoin.exe differ by release. No unexplained differences. (RAW_RESULTS/obl_targz_comparison.json)

A fourth, functional check: the genesis block was recomputed from the source's own constants and matches the source's asserted values exactly (section 5).

### Integrity verdict

**VERIFIED BY CROSS-SOURCE AGREEMENT** for the tree as a whole, with one flagged file (src/ui.h, see check 2).

### Limitations, stated honestly

- 2009 Bitcoin releases carry no author signature that we can verify. There is no Satoshi-signed checksum for v0.1.3. Integrity therefore rests on agreement between independently held copies and published analyses, not on cryptographic authorship proof.
- The strongest single artifact, the SNI RAR, comes from one host. Its contents are corroborated file-by-file by a published manifest derived from a different copy (diyhpl.us) and by an independent 0.1.0-derived tree for the unchanged majority, but a second byte-identical copy of the RAR archive itself was not obtained: SourceForge's original file is gone and the Wayback Machine returned no captures for the URL patterns tried. The archive-level SHA-256 above is therefore our own first published-style record for this copy, and any future second copy should be compared against it.
- RAR CRC32 is a weak checksum; it is used here because it is what the historical archive and the published manifest carry. The SHA-256 manifest below is the strong record going forward.

## 4. Verified tree listing (SNI RAR, 48 files, 3 directories, 9,291,816 bytes uncompressed)

Archive member timestamps are the values stored in the RAR. CRC32 is computed from the extracted bytes (and equals the RAR header value for every file).

| Path | Size | Archive timestamp | CRC32 | SHA-256 |
|------|------|-------------------|-------|---------|
| src/makefile | 2693 | 2009-01-07 01:00:00 | C3C06DAC | fa2f6c3031eb8625e24aa012fa7c0d6e17c7f61e7b9604d45cde5b7bfdade161 |
| src/obj/ | dir | 2009-01-07 15:36:27.4687500 |  |  |
| src/rc/addressbook16.bmp | 1334 | 2009-01-07 01:00:00 | 7D00BCF5 | a8687dc93616ba8d56a44c4edd52e1b6dc93b87b97b8177a65b369b3e9c4f853 |
| src/rc/addressbook16mask.bmp | 126 | 2009-01-07 01:00:00 | 6428BA44 | a22071608f7e38b4b18f69d87123f6d7429710e8ea7b5370f1c86b14193fbf50 |
| src/rc/addressbook20.bmp | 1478 | 2009-01-07 01:00:00 | 747AADED | 76fe6679da5c4d9fd763084a19d1d0cf0eb3fb78f8799ba064e912d1ab4b0b10 |
| src/rc/addressbook20mask.bmp | 142 | 2009-01-07 01:00:00 | 49D20842 | 392154912bd31605dee19df89e999db180bfa5a595a668ef097d5d3338fbedc8 |
| src/rc/send16.bmp | 1334 | 2009-01-07 01:00:00 | 9D892475 | 553d3ee80472f791d1da36600f534b702af159f98c54191031847f283f70715e |
| src/rc/send16mask.bmp | 126 | 2009-01-07 01:00:00 | 51360655 | 7297c773da79fc0ef61799b3b698274fd4f6d74d3c3a727ad6dff41358968191 |
| src/rc/send16masknoshadow.bmp | 126 | 2009-01-07 01:00:00 | F6876188 | 08c7efff95fc90a198dd190e50761281cbfab42e17f064b7146d952d94601749 |
| src/rc/send20.bmp | 1478 | 2009-01-07 01:00:00 | 39F9B908 | b4959ca84a316e494e2d5b61f406e54344249ace24b854e90f34d5deaccf61c3 |
| src/rc/send20mask.bmp | 142 | 2009-01-07 01:00:00 | FA78BFA8 | efb5d66bb902a281406d3b5cc4092008dbdcb5c77b298c06b3ef79e8bfa16160 |
| src/rc/ | dir | 2009-01-07 15:37:33.6718750 |  |  |
| src/db.cpp | 16616 | 2009-01-11 01:02:00 | 9309EFB7 | d30fa51dedf951e2a36abf7a2096be87c8e0b16bc82fb710de776b754ecd9bf5 |
| src/irc.cpp | 7173 | 2009-01-11 01:02:00 | 806DD781 | 24eab76785cfd889ffbf80cee1c5674e1bee81064544a60f5bf79ed250a6180e |
| src/main.cpp | 83058 | 2009-01-07 01:00:00 | E51CE2B1 | c7357a9bece0a9efc19de966f6a2c1c6a708918359b27a9c992a7a2873b2057a |
| src/market.cpp | 6938 | 2009-01-07 01:00:00 | D087E0DE | 81c15691f9ca4c0a0d66b4a4a95e631caf3f31af26575e5ab49f8db838fa6e39 |
| src/net.cpp | 32774 | 2009-01-12 01:03:00 | B5CED220 | 8fadb290c8ff9245fbbda7e246ea283be14438156e9935894d53a830889568a3 |
| src/script.cpp | 35279 | 2009-01-07 01:00:00 | 70DE7357 | 347c7526932d42a4d10ae487150b709e2ead737aa4b05f50aa9e2eefeb05a5b5 |
| src/sha.cpp | 19000 | 2009-01-07 01:00:00 | 7B45200F | e99fec6d660bf7b06f7455f41567c5454b04c63e0ad0ee16b51ef421110cd0b5 |
| src/ui.cpp | 97185 | 2009-01-07 01:00:00 | 0F952088 | bec80418526c9fe45f3b83c99c0a708363942df271d3f048c18fec6ebff8fa63 |
| src/uibase.cpp | 108295 | 2009-01-07 01:00:00 | 26639AFE | a6270e7d73012541cd086a5ca1d9b06ad8ec3422e2e3ce1c9ce0a064f0c350da |
| src/util.cpp | 9610 | 2009-01-11 01:02:00 | 5CE3CB17 | 9fff6bc6eb125a2afffc7cde2643dfb054ddc0d9d71c3e87c5b3f238b3bfb054 |
| src/ | dir | 2009-01-10 23:15:06.7031250 |  |  |
| libeay32.dll | 1306630 | 2009-01-07 01:00:00 | A1896702 | d108cdff2922a60e0054718a84178a40526ba00401fa34a87fb055947c77a182 |
| mingwm10.dll | 11673 | 2009-01-07 01:00:00 | 555A37B7 | 1badf3972d9a861a69fafb2c5e3282aecc30007b9d51c199806e542b32d7708f |
| bitcoin.exe | 6438912 | 2009-01-12 01:03:00 | 292232FB | 72906601a2ca1de16b3b1cf2760f37969397781f6d46e3b767832d27470040ee |
| src/uiproject.fbp | 841798 | 2009-01-07 01:00:00 | C4A39D79 | 60a494786f42edd610c7cf23c6a6427f2897cf78fc99604a5d0a471859ae2305 |
| src/base58.h | 5639 | 2009-01-07 01:00:00 | DD2EC569 | f74d61273812f0966968f4bdf5e42ff8cc28837f0df463fe09980065e84209eb |
| src/bignum.h | 14096 | 2009-01-07 01:00:00 | A9A6A507 | c946d2678051772a771ec2ba9c33fee64d8c1d0c92b6a791d6637ba673b36fc0 |
| src/db.h | 10979 | 2009-01-07 01:00:00 | F6BAF4B2 | 6f0abeb8ae108f9823783a71ef214824e9f6ab72e93990bc70838cd55a433eda |
| src/headers.h | 1639 | 2009-01-07 01:00:00 | 5C745AA1 | dac61d922a9cdce5f6f6a8acd0e5628721d865ce9bb54ded32b5fa9a7a6e202f |
| src/irc.h | 317 | 2009-01-07 01:00:00 | 00C6F007 | f3c40402a7809562de6cc659e099ba9ccfee6f119958b7811ba82414edc42e7a |
| src/key.h | 4639 | 2009-01-07 01:00:00 | 0C5ABC88 | f631451db96081b0eeb4ca74d2f9c221de934f1079b166077055f4d0cea63e68 |
| src/main.h | 33212 | 2009-01-07 01:00:00 | 5369988D | f134c66c90c9ee054573a4f3199a0231b95c9e7a26e1ee45a73748ff4ac3511e |
| src/market.h | 3745 | 2009-01-07 01:00:00 | 27420D6A | 85aa4b054d749e094e641d41233384c1e7b58c84696b7be145ab53e6c0fbdbc4 |
| src/net.h | 21397 | 2009-01-11 01:02:00 | FAC43B12 | 46e9974eaa9b4182381131db12e4ed42d80fd0932ce96251cac78efbd624e43a |
| src/script.h | 17707 | 2009-01-07 01:00:00 | FF1DE242 | f905858b5d6d4593a3051b593c45fb5a8dd4cd38b5636c5e4456060b034fa218 |
| src/serialize.h | 39878 | 2009-01-07 01:00:00 | 71E29667 | 6b4bf47d96a73d53b396b5d19940dba3cc7eb21db46f2f13555ff533ceb72a9c |
| src/sha.h | 5023 | 2009-01-07 01:00:00 | 9CF10FA3 | 8b4c2faf5156b67491aa78ead117870999c807f7627afc6d223194416df02ede |
| src/ui.h | 11922 | 2009-01-07 01:00:00 | AA7C3703 | a99010147ea081ecbf22f6c3ce80954f1fe7fec72e26cc15a11f246dd6a271c4 |
| src/uibase.h | 27772 | 2009-01-07 01:00:00 | 9D64FB45 | 945c2abf4280518a6d1ede7319e835fb3df82674e8a907ec4a2d1e8c74674eab |
| src/uint256.h | 25269 | 2009-01-07 01:00:00 | 524954B7 | 54818c679957094352ca5a6d7b7d131cfa7052ee54d8481053f87f57217b0c59 |
| src/util.h | 11482 | 2009-01-07 01:00:00 | D10D475F | 1411b8f3ff7c712ea80f98587e3b8a9cf05b81a1dc8c45021bbf491de6292534 |
| src/rc/bitcoin.ico | 22486 | 2009-01-07 01:00:00 | EE40473A | 8571889ac8a29b5c2e537f3fb11973295fcffc8f9b348623aa87b3598e869033 |
| src/rc/check.ico | 766 | 2009-01-07 01:00:00 | F4E0FC06 | 8a1978ca70d9aa80942dac340a212d1e42650c21182e785cca99e586c9ccb620 |
| src/ui.rc | 602 | 2009-01-07 01:00:00 | 4303CA25 | a9cd94ed8280943bc35724ca7a53c46f2b167dce27adeca248920c5c16ff46b7 |
| license.txt | 1079 | 2009-01-07 01:00:00 | 1EF87B23 | bf78d9cb6275b70fc0dd8af1248e9fd8cb4327d854a0e39ceb1b2d9993a96220 |
| src/license.txt | 1079 | 2009-01-07 01:00:00 | 1EF87B23 | bf78d9cb6275b70fc0dd8af1248e9fd8cb4327d854a0e39ceb1b2d9993a96220 |
| readme.txt | 1857 | 2009-01-12 01:03:00 | 628FFF0C | 8e20b611f302f536db97bcd5153a3fd1dc3fe10fee432db875a03e395a0908dd |
| src/readme.txt | 2664 | 2009-01-12 01:03:00 | 20E4D16A | dc0b70534e186d74e268c5fc21c050d565139b6dc79e39a2d220a23c8e48af1c |
| src/makefile.vc | 2647 | 2009-01-07 01:00:00 | 35548F9A | c00a4413d656f958120265590701e0fe2159020e474470726f826f1178d790ed |

## 5. Genesis block facts, from the source itself

Location: `src/main.cpp`, function `LoadBlockIndex(bool fAllowNew)` at line 1420; the genesis construction is lines 1441 to 1490 (comment block 1441 to 1453, code 1456 to 1480). The expected hash is a file-scope constant at `src/main.cpp` line 24:

`const uint256 hashGenesisBlock("0x000000000019d6689c085ae165831e934ff763ae46a2a6c172b3f1b60a8ce26f");`

Construction inputs, exactly as written in the source:

- Coinbase timestamp text (line 1456): "The Times 03/Jan/2009 Chancellor on brink of second bailout for banks" (69 characters)
- scriptSig (line 1460): CScript() << 486604799 << CBigNum(4) << timestamp bytes, serializing to 77 bytes: 04ffff001d010445 followed by the 69 text bytes (also printed in the source comment at line 1450)
- Coinbase value (line 1461): 50 * COIN = 5,000,000,000 satoshis, with COIN = 100000000 at src/main.h line 18
- scriptPubKey (line 1462): CBigNum("0x5F1DF16B2B704C8A578D0BBAF74D385CDE12C11EE50455F3C438EF4C3FBCF649B6DE611FEAE06279A60939E028A8D65C10B73071A6F16719274855FEB0FD8A6704") << OP_CHECKSIG. The CBigNum byte vector reverses to the 65-byte public key 04678afdb0fe5548271967f1a67130b7105cd6a828e03909a67962e0ea1f61deb649f6bc3f4cef38c4f35504e51ec112de5c384df7ba0b8d578a4c702b6bf11d5f
- hashPrevBlock = 0 (line 1465); hashMerkleRoot = block.BuildMerkleTree() (line 1466, BuildMerkleTree defined at src/main.h line 868)
- nVersion = 1 (line 1467); nTime = 1231006505 (line 1468); nBits = 0x1d00ffff (line 1469); nNonce = 2083236893 (line 1470)
- Source assertions: merkle root equals 0x4a5e1e4baab89f3a32518a88c31bc87f618f76673e2cc77ab2127b7afdeda33b (line 1479) and block.GetHash() equals hashGenesisBlock (line 1480)

### Our recomputation (integrity cross-check, not a build of the original code)

RAW_RESULTS/genesis_recompute.py parses the timestamp, the scriptPubKey constant, nTime, nBits, nNonce and nVersion directly out of src/main.cpp, rebuilds the coinbase transaction (204 bytes), the merkle root and the 80-byte header with Python hashlib, and compares. Result, 2026-11-15 (RAW_RESULTS/genesis_recompute_output.txt, exit code 0):

- Merkle root recomputed: 4a5e1e4baab89f3a32518a88c31bc87f618f76673e2cc77ab2127b7afdeda33b, MATCH
- Genesis hash recomputed: 000000000019d6689c085ae165831e934ff763ae46a2a6c172b3f1b60a8ce26f, MATCH
- Header bytes: 01000000 0000000000000000000000000000000000000000000000000000000000000000 3ba3edfd7a7b12b27ac72c3e67768f617fc81bc3888a51323a9fb8aa4b1e5e4a 29ab5f49 ffff001d 1dac2b7c

## 6. What this unblocks and what it does not

Unblocked: deliverable 2 (architecture map, skeleton in ARCHITECTURE_MAP_SKELETON.md alongside this file) and all source-reading deliverables 3 to 22, which can now cite a verified tree with stable SHA-256 references per file.

Not done in this task, by design: no build of the 2009 code (historical build assumptions are a later deliverable), no optimization, no benchmarks, no changes to NOVA.
