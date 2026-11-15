#!/usr/bin/env python3
"""Wave 3 verification 2: nonce taint through the SHA-256 schedule and the
compression function, for the 80-byte Bitcoin block header hashed with the
v0.1.3 layout (main.cpp FormatHashBlocks / BlockSHA256).

Model (symbolic taint, derived from the equations in src/sha.cpp):
  A value is tainted if its expression tree contains the nonce anywhere.
  XOR, rotations, shifts, modular addition and Ch/Maj all propagate taint
  (union of inputs). This is a may-depend analysis: tainted means the value
  CAN differ when only the nonce changes; untainted means it provably
  cannot.

Schedule (src/sha.cpp line 118, blk2, plus blk0 line 21):
  W[i] = data[i]                                        for i in 0..15
  W[i] = s1(W[i-2]) + W[i-7] + s0(W[i-15]) + W[i-16]    for i in 16..63

Round (src/sha.cpp lines 132-133, macro R):
  T1 = h + S1(e) + Ch(e,f,g) + K[i] + W[i]
  T2 = S0(a) + Maj(a,b,c)
  (a,b,c,d,e,f,g,h) -> (T1+T2, a, b, c, d+T1, e, f, g)

Header word layout in the padded buffer (big-endian words as Transform
sees them after BlockSHA256's ByteReverse on little-endian hosts):
  Pass 1 chunk 1: header bytes 0..63  (version, prevhash, merkle[0..27])
  Pass 1 chunk 2: header bytes 64..79 (merkle[28..31], nTime, nBits,
                  nNonce = word index 3 of this chunk), then padding.
  Pass 2 chunk 1: the 32-byte pass-1 digest (8 words), then padding.
"""
M = 0xFFFFFFFF


def schedule_taint(direct):
    """direct: list of 16 bools, taint of the chunk's input words."""
    W = list(direct) + [False] * 48
    for i in range(16, 64):
        W[i] = W[i - 2] or W[i - 7] or W[i - 15] or W[i - 16]
    return W


def compression_taint(W):
    """Returns list of 64 frozensets: tainted state positions (0=a..7=h)
    AFTER each round, plus the taint of the feed-forward output."""
    a, b, c, d, e, f, g, h = (False,) * 8
    rows = []
    for i in range(64):
        t1 = h or e or f or g or W[i]          # S1(e), Ch(e,f,g), h, W[i]
        t2 = a or b or c                        # S0(a), Maj(a,b,c)
        new_a = t1 or t2
        new_e = d or t1
        a, b, c, d, e, f, g, h = new_a, a, b, c, new_e, e, f, g
        rows.append(frozenset(j for j, v in enumerate((a, b, c, d, e, f, g, h)) if v))
    return rows


def bands(rows):
    out, start = [], 0
    for i in range(1, 65):
        if i == 64 or rows[i] != rows[start]:
            out.append((start, i - 1, rows[start]))
            start = i
    return out


names = "abcdefgh"

# Chunk 2 of pass 1: only word 3 (nNonce) is nonce-dependent.
direct_c2 = [False] * 16
direct_c2[3] = True
W_c2 = schedule_taint(direct_c2)
print("PASS 1 CHUNK 2 (nonce at W[3]):")
print("  schedule taint, W[0..15] :", "".join("N" if t else "." for t in W_c2[:16]))
print("  schedule taint, W[16..63]:", "".join("N" if t else "." for t in W_c2[16:]))
first_exp = min(i for i in range(16, 64) if W_c2[i])
print("  first nonce-dependent expanded word: W[%d]" % first_exp)
print("  all W[i] for i >= %d tainted: %s" % (first_exp, all(W_c2[first_exp:])))
rows_c2 = compression_taint(W_c2)
print("  state taint after each round (a..h, N = may depend on nonce):")
for s, e_, r in bands(rows_c2):
    print("    rounds %2d..%2d: %s" % (s, e_, "".join("N" if j in r else "." for j in range(8))))
sat = min(i for i, r in enumerate(rows_c2) if len(r) == 8)
print("  all 8 state words first tainted after round: %d" % sat)
print("  feed-forward output taint: state_in(untainted) + final state ->",
      "all 8 output words tainted" if len(rows_c2[-1]) == 8 else rows_c2[-1])

# Chunk 1 of pass 1: no nonce anywhere.
W_c1 = schedule_taint([False] * 16)
rows_c1 = compression_taint(W_c1)
print("PASS 1 CHUNK 1: schedule taint any:", any(W_c1),
      "; state taint any:", any(rows_c1),
      "=> chunk-1 output state (the midstate) is nonce-independent.")

# Pass 2: every input word is the pass-1 digest, hence nonce-dependent.
W_p2 = schedule_taint([True] * 16)
rows_p2 = compression_taint(W_p2)
print("PASS 2 CHUNK: schedule taint all:", all(W_p2),
      "; state fully tainted from round:", min(i for i, r in enumerate(rows_p2) if len(r) == 8))
