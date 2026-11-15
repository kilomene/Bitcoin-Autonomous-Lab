# Phase 001, Deliverable 8: SHA-256 Compression Reconstruction

Project: NOVA SHA-X, Research Phase 001, Wave 3.
Subject: the complete SHA-256 compression function exactly as Bitcoin v0.1.3 implements it in the Crypto++ 5.5.2 extract at src/sha.cpp / src/sha.h, how the code maps to the standard equations, and where padding and the streaming API actually live in this version (not where a modern reader would expect them).

Labels: SOURCE FACT (file and line in the verified 0.1.3 tree), PROVEN (checked by recomputation in RAW_RESULTS), STANDARD (FIPS 180 mathematics derived independently).

## 1. The API that exists, and the API that does not

SOURCE FACT. The Crypto++ extract exposes exactly two SHA-256 operations, declared in src/sha.h lines 132 to 139:

```cpp
class SHA256
{
public:
    typedef word32 HashWordType;
    static void InitState(word32 *state);
    static void Transform(word32 *digest, const word32 *data);
    static const char * StaticAlgorithmName() {return "SHA-256";}
};
```

There is no SHA256_Init, no SHA256_Update, no SHA256_Final and no padding code anywhere in src/sha.cpp or src/sha.h. The extract is a raw block primitive: InitState loads H(0), Transform absorbs exactly one 64-byte block (16 word32 values) into an 8-word state.

The names SHA256_Init / SHA256_Update / SHA256_Final DO appear in the tree, at src/util.h lines 354 to 357 and 370 to 374, but those are OpenSSL's functions: src/headers.h line 21 includes `<openssl/sha.h>`, and util.h's Hash() templates call the OpenSSL one-shot SHA256() and SHA256_CTX streaming API. Padding for every non-mining hash in the program is therefore OpenSSL's internal padding. Padding for the mining path is done by hand in src/main.cpp (FormatHashBlocks, lines 2138 to 2151; see Deliverable 11). This split is one of the sharpest structural facts of the 0.1.3 tree: two independent SHA-256 implementations coexist, OpenSSL for general hashing (txids, merkle trees, block GetHash) and the Crypto++ extract for the miner's inner loop only, where the code needs direct state access.

## 2. The macros, exactly as named in the source

All in src/sha.cpp. There are no functions named SHA256_S0 or similar; everything is a preprocessor macro.

Message-word macros:

```cpp
#define blk0(i) (W[i] = data[i])                                            // line 21 (defined in the SHA-1 section, reused)
#define blk2(i) (W[i&15]+=s1(W[(i-2)&15])+W[(i-7)&15]+s0(W[(i-15)&15]))     // line 118
```

Boolean functions (lines 120 to 121):

```cpp
#define Ch(x,y,z)  (z^(x&(y^z)))
#define Maj(x,y,z) ((x&y)|(z&(x|y)))
```

These are the alternative algebraically equivalent forms, not the textbook forms: Ch(x,y,z) = z XOR (x AND (y XOR z)) equals (x AND y) XOR ((NOT x) AND z) bit for bit (PROVEN identity, standard Boolean algebra; it is also the form modern Core uses). Maj(x,y,z) = (x AND y) OR (z AND (x OR y)) equals (x AND y) XOR (y AND z) XOR (z AND x) bit for bit (same status).

Sigma functions (lines 136 to 139, defined AFTER the round macro that uses them; the preprocessor does not care):

```cpp
#define S0(x) (rotrFixed(x,2)^rotrFixed(x,13)^rotrFixed(x,22))    // line 136, big Sigma_0
#define S1(x) (rotrFixed(x,6)^rotrFixed(x,11)^rotrFixed(x,25))    // line 137, big Sigma_1
#define s0(x) (rotrFixed(x,7)^rotrFixed(x,18)^(x>>3))              // line 138, small sigma_0
#define s1(x) (rotrFixed(x,17)^rotrFixed(x,19)^(x>>10))            // line 139, small sigma_1
```

`rotrFixed` is the template in src/sha.h lines 32 to 36: `(x>>y) | (x<<(32-y))` for word32. All arithmetic is on unsigned 32-bit words, so every addition is implicitly modulo 2^32 (C++ unsigned wraparound); the source writes no explicit mask anywhere in the round code.

Rotating-window state macros (lines 123 to 130): instead of eight named variables, the transform keeps `word32 T[8]` and addresses the working registers relative to the current round i:

```cpp
#define a(i) T[(0-i)&7]
#define b(i) T[(1-i)&7]
#define c(i) T[(2-i)&7]
#define d(i) T[(3-i)&7]
#define e(i) T[(4-i)&7]
#define f(i) T[(5-i)&7]
#define g(i) T[(6-i)&7]
#define h(i) T[(7-i)&7]
```

The round macro (lines 132 to 133):

```cpp
#define R(i) h(i)+=S1(e(i))+Ch(e(i),f(i),g(i))+SHA256_K[i+j]+(j?blk2(i):blk0(i));\
    d(i)+=h(i);h(i)+=S0(a(i))+Maj(a(i),b(i),c(i))
```

## 3. The transform, step by step (src/sha.cpp lines 141 to 164)

```cpp
void SHA256::Transform(word32 *state, const word32 *data)
{
    word32 W[16];
    word32 T[8];
    memcpy(T, state, sizeof(T));                       // line 146
    for (unsigned int j=0; j<64; j+=16)                 // line 148
    {
        R( 0); R( 1); ... R(15);                        // lines 150 to 153
    }
    state[0] += a(0); ... state[7] += h(0);             // lines 156 to 163
}
```

Structural facts:

1. The message schedule is a 16-word circular buffer `W[16]`, not a 64-word array. blk0 loads W[i] = data[i] for the first 16 rounds (selected by the `j ? blk2 : blk0` test in R: j is the block-of-16 counter, so rounds 0 to 15 use blk0). blk2 updates W[i mod 16] in place for rounds 16 to 63, adding the schedule expansion to the word already in the slot, which is W[i-16]. See Deliverable 9 for the recurrence.
2. The state is the same rotating trick: because a(i) is T[(0-i) mod 8], incrementing i logically rotates which physical slot plays each role, so the per-round register renaming (a,b,c,d,e,f,g,h) -> (new, a, b, c, new, e, f, g) costs zero data movement. R(i) writes only two slots: h(i) becomes T1 (the macro first does h += ... making h(i) hold T1), then d(i) += h(i) forms the new e in place, then h(i) += S0(a)+Maj(...) forms the new a in the same slot that held T1.
3. The loop is "partially loop unrolled" (the source's own comment, line 147): 4 iterations of 16 macro-expanded rounds.
4. Feed-forward: after 64 rounds the working registers are added back into the caller's state (lines 156 to 163), all additions mod 2^32. This is the standard Davies-Meyer style feed-forward of SHA-256 (STANDARD), implemented here as 8 separate `state[k] +=` statements reading through the a(0)..h(0) window, which after 64 rounds (64 mod 8 = 0) is aligned back to T[0..7] in order.

## 4. The round equations in symbolic form

Let (a,b,c,d,e,f,g,h)_t be the working state after t rounds, W_t the schedule word and K_t the round constant. Unrolling macro R(i) with the rotating window gives exactly the FIPS 180 round (STANDARD form, and a line-by-line transcription of the macro):

```
T1 = h + S1(e) + Ch(e,f,g) + K_t + W_t          (all additions mod 2^32)
T2 = S0(a) + Maj(a,b,c)
(a,b,c,d,e,f,g,h)_{t+1} = (T1+T2, a, b, c, d+T1, e, f, g)
```

with

```
S0(x) = ROTR^2(x)  XOR ROTR^13(x) XOR ROTR^22(x)
S1(x) = ROTR^6(x)  XOR ROTR^11(x) XOR ROTR^25(x)
s0(x) = ROTR^7(x)  XOR ROTR^18(x) XOR SHR^3(x)     (schedule only)
s1(x) = ROTR^17(x) XOR ROTR^19(x) XOR SHR^10(x)    (schedule only)
Ch(e,f,g)  = g XOR (e AND (f XOR g))
Maj(a,b,c) = (a AND b) OR (c AND (a OR b))
```

Code-to-equation mapping, per macro line: `h(i)+=S1(e(i))+Ch(...)+SHA256_K[i+j]+(j?blk2(i):blk0(i))` is T1 accumulated into the h slot (K index i+j is the absolute round number, since the outer loop steps j by 16 and R is expanded with i = 0..15); `d(i)+=h(i)` is the new e = d + T1; `h(i)+=S0(a(i))+Maj(...)` completes the new a = T1 + T2 in the slot that held T1. There are exactly 5 additions in T1 (h, S1(e), Ch, K, W) and the source writes them as one chained `+=` expression; addition count per round: 5 in T1 counting the accumulation into h (4 binary adds plus the slot add), 1 for T2, 1 for d+T1, 1 for T1+T2, total 7 word additions per round in the round function proper, plus 4 in blk2 for rounds 16 to 63 (3 adds inside the expansion expression plus the `+=` into the W slot). All counts are transcriptions of the macro text, not measurements.

The 64-round symbolic unrolling is fully determined by the recurrence above plus the initial condition (a..h)_0 = state input and the schedule of Deliverable 9; writing out 64 expanded equations adds no information beyond the recurrence, so this deliverable states the recurrence and the two boundary conditions (InitState for the first block of a hash, the previous block's post-feed-forward state for later blocks) as the complete specification. PROVEN completeness: RAW_RESULTS/sha256d_layout_verify.py implements precisely this recurrence in Python and reproduces SHA256(SHA256(genesis header)) equal to the source's asserted genesis hash, and RAW_RESULTS/genesis_recompute.py (Wave 1) independently reproduces the same digest with hashlib.

## 5. Endianness handling

Transform itself is endian-agnostic in a dangerous way: it interprets the caller's word32 array numerically. The data words must already be the big-endian interpretation of the block bytes. Making that true is the caller's job:

- In the mining path, BlockSHA256 (src/main.cpp lines 2156 to 2182) tests a static endianness flag (line 2154, `detectlittleendian`) and on little-endian hosts byte-reverses every input word into a scratch buffer before each Transform, then byte-reverses the 8 state words afterwards so the output state is stored in big-endian byte order in memory. On a big-endian host it passes the data pointer straight through.
- ByteReverse(word32) is src/sha.h lines 73 to 94: on GCC it is a single inline `bswap` instruction; fallbacks use rotates and masks.
- In the OpenSSL path, endianness is OpenSSL's internal concern and invisible to the 0.1.3 code.

Consequence worth stating plainly: SHA256::Transform alone does not hash a byte string. It hashes 16 host words whose values must be the big-endian words. Any reimplementation that feeds it little-endian-loaded words gets a different, non-SHA-256 function. The genesis recomputation in Wave 1 confirms the composed behaviour (BlockSHA256 semantics) equals standard SHA-256.

## 6. Padding, as implemented in this version

There are exactly two padding implementations in play, neither inside sha.cpp:

1. OpenSSL's internal FIPS padding for all Hash() calls (invisible in this tree; the tree only calls the API, src/util.h lines 339 to 377).
2. FormatHashBlocks (src/main.cpp lines 2138 to 2151) for the mining path, fully analysed in Deliverable 11: zero-fill, a single 0x80 byte, and only the low 32 bits of the bit length written into the last 4 bytes of the final block (the high 4 bytes of the standard 8-byte length field are left as memset zeros, which is correct for any message shorter than 2^32 bits, and is a real structural difference from the general standard form).

## 7. The commented-out alternative (source archaeology)

src/sha.cpp lines 166 to 249 contain a complete second SHA-256 transform inside a block comment, headed "smaller but slower" (line 167). It uses a different schedule layout (W[32] with doubled writes) and a sliding state pointer. It is dead text, never compiled. Its presence matters for one reason: it shows the shipped transform was a deliberate size/speed choice by the Crypto++ author, not the only form known to the codebase. No claim about its speed is made here; the phase forbids benchmarks of the original code in this wave, and the comment's own claim is recorded as an untested author assertion.

## 8. Reproduction

- Constants: RAW_RESULTS/constants_verify.py (Deliverable 7).
- Round equations: RAW_RESULTS/sha256d_layout_verify.py implements S0/S1/s0/s1/Ch/Maj with the exact rotate and shift amounts above and reproduces the genesis double hash.
- Source lines: every macro and function cited can be read at the stated lines of src/sha.cpp in the verified tree.

## 9. Limitations

- The mapping from macro text to the symbolic round is a transcription; its correctness is anchored by the end-to-end genesis reproduction, not by a formal proof over the C++ preprocessor.
- Instruction-level cost of the macro form on 2009 compilers is a later deliverable (CPU utilization and threading); nothing here measures it.
