"""Original statistical research on the lab's own mining data.

Question (the owner's): is there ANY statistical structure in
double SHA-256 mining that a formula could exploit: winning
nonces clustering, hash bytes deviating from uniform, adjacent
nonces correlating, some header regions luckier than others?

Method: measure, on data we produced ourselves:
1. Every block header on our regtest chain (about 390 blocks):
   winning nonce distribution across the 2^32 space (chi-square
   over 16 buckets), and the winning hash's leading-zero count
   against the geometric law the target implies.
2. A fresh 2,000,000-hash sample from the C engine: per-byte
   chi-square over all 32 digest positions, bit balance, and the
   lag-1 correlation between consecutive nonces' digests.
3. Reduced-round SHA-256 (our parametrized implementation):
   flip one input bit and measure output bias as rounds rise
   from 16 to 64. This maps exactly where statistical structure
   exists (few rounds) and where it dies (full rounds) - the
   honest boundary of what statistics can and cannot do here.

Conclusions are whatever the numbers say; the script prints them
and tests/test_research.py pins the qualitative findings.
"""

import hashlib
import math
import struct
import sys, os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def chi2_uniform(counts):
    n = sum(counts)
    e = n / len(counts)
    return sum((c - e) ** 2 / e for c in counts), len(counts) - 1


def chi2_sf_approx(x, df):
    """Wilson-Hilferty normal approximation to the chi-square
    survival function; plenty for the effect sizes here."""
    z = ((x / df) ** (1 / 3) - (1 - 2 / (9 * df))) / math.sqrt(2 / (9 * df))
    return 0.5 * math.erfc(z / math.sqrt(2))


def chain_statistics(rpc):
    tip = rpc.get_block_count()
    nonces = []
    lead_zeros = []
    h = rpc.get_best_block_hash()
    while True:
        b = rpc.call("getblock", h, 0)
        raw = bytes.fromhex(b)
        nonce = struct.unpack("<I", raw[76:80])[0]
        nonces.append(nonce)
        digest = hashlib.sha256(hashlib.sha256(raw[:80]).digest()).digest()
        disp = digest[::-1]
        z = 0
        for byte in disp:
            if byte == 0:
                z += 8
            else:
                z += 8 - byte.bit_length()
                break
        lead_zeros.append(z)
        if len(nonces) >= tip:
            break
        # prev hash is bytes 4..36 internal order
        h = raw[4:36][::-1].hex()
        if h == "00" * 32:
            break
    buckets = [0] * 16
    for n in nonces:
        buckets[n >> 28] += 1
    stat, df = chi2_uniform(buckets)
    # The raw nonce histogram is EXPECTED to be violently
    # non-uniform on regtest, and the reason matters: every miner
    # on this chain (Core's internal miner and our engines) scans
    # from nonce 0, and the regtest target accepts about half of
    # all hashes, so the winner is almost always a tiny nonce.
    # The correct test under sequential search: (nonce+1) follows
    # a geometric law with p = target/2^256, so (nonce+1)*p has
    # median ln(2) = 0.693 under uniform hashing. The median is
    # used because the mean is hostage to a couple of blocks whose
    # miners were hunting a much smaller share target first (our
    # own solo test is one: its winner sits at nonce 44,364,155).
    # That is the number that would expose hash structure if any
    # existed.
    from mining.pow import target_from_nbits
    scaled = []
    h = rpc.get_best_block_hash()
    count = 0
    while count < len(nonces):
        b = rpc.call("getblock", h, 0)
        raw = bytes.fromhex(b)
        bits = struct.unpack("<I", raw[72:76])[0]
        p = target_from_nbits(bits) / (1 << 256)
        scaled.append((nonces[count] + 1) * p)
        h = raw[4:36][::-1].hex()
        count += 1
        if h == "00" * 32:
            break
    scaled.sort()
    median_scaled = scaled[len(scaled) // 2]
    return {"blocks": len(nonces), "nonce_chi2": stat, "nonce_df": df,
            "nonce_p": chi2_sf_approx(stat, df),
            "median_scaled_nonce": median_scaled,
            "mean_leading_zeros": sum(lead_zeros) / len(lead_zeros)}


def sample_statistics(samples=2_000_000):
    import ctypes
    from gpu.engine import ComputeEngine
    eng = ComputeEngine()
    header = bytes(range(80))
    byte_counts = [[0] * 256 for _ in range(32)]
    bit_ones = 0
    prev = None
    lag_pairs = 0
    lag_agree = 0
    done = 0
    start = 0
    while done < samples:
        count = min(1 << 16, samples - done)
        digests = eng._c_batch(eng._c_lib, header, (1 << 256) - 1,
                               start, count)
        for d in digests:
            for i in range(32):
                byte_counts[i][d[i]] += 1
            bit_ones += bin(int.from_bytes(d, "big")).count("1")
            cur = d[0] >> 7
            if prev is not None:
                lag_pairs += 1
                if cur == prev:
                    lag_agree += 1
            prev = cur
        done += count
        start += count
    worst = 0.0
    worst_pos = -1
    for i in range(32):
        stat, _ = chi2_uniform(byte_counts[i])
        if stat > worst:
            worst, worst_pos = stat, i
    return {"samples": samples, "worst_byte_chi2": worst,
            "worst_byte_pos": worst_pos, "byte_chi2_df": 255,
            "byte_chi2_p": chi2_sf_approx(worst, 255),
            "bit_one_fraction": bit_ones / (samples * 256),
            "lag1_msb_agreement": lag_agree / lag_pairs}


# --- reduced-round SHA-256 for the bias experiment ----------------------

from mining.pow_engine import H0, K


def _rr(x, n):
    return ((x >> n) | (x << (32 - n))) & 0xffffffff


def sha256_reduced(data: bytes, rounds: int) -> bytes:
    """SHA-256 with a truncated round count (single block input
    of exactly 64 bytes), for measuring bias vs rounds."""
    w = list(struct.unpack(">16I", data))
    for i in range(16, 64):
        s0 = _rr(w[i - 15], 7) ^ _rr(w[i - 15], 18) ^ (w[i - 15] >> 3)
        s1 = _rr(w[i - 2], 17) ^ _rr(w[i - 2], 19) ^ (w[i - 2] >> 10)
        w.append((w[i - 16] + s0 + w[i - 7] + s1) & 0xffffffff)
    a, b, c, d, e, f, g, h = H0
    for i in range(rounds):
        s1 = _rr(e, 6) ^ _rr(e, 11) ^ _rr(e, 25)
        ch = (e & f) ^ (~e & g)
        t1 = (h + s1 + ch + K[i] + w[i]) & 0xffffffff
        s0 = _rr(a, 2) ^ _rr(a, 13) ^ _rr(a, 22)
        mj = (a & b) ^ (a & c) ^ (b & c)
        t2 = (s0 + mj) & 0xffffffff
        h, g, f, e, d, c, b, a = (g, f, e, (d + t1) & 0xffffffff,
                                  c, b, a, (t1 + t2) & 0xffffffff)
    out = [(x + y) & 0xffffffff for x, y in
           zip(H0, (a, b, c, d, e, f, g, h))]
    return struct.pack(">8I", *out)


def bias_vs_rounds(trials=4000):
    """Flip the last message bit; measure the mean absolute bias
    of output bits from 0.5. Full avalanche gives about
    1/sqrt(trials) noise; structured rounds give far more."""
    base = bytearray(64)
    base[0:3] = b"abc"
    base[3] = 0x80
    struct.pack_into(">Q", base, 56, 24)
    results = {}
    import random
    rng = random.Random(20261113)
    for rounds in (16, 20, 24, 28, 32, 40, 48, 56, 64):
        flips = [0] * 256
        for t in range(trials):
            blk = bytearray(base)
            # randomize a nonce-like word to decorrelate trials
            struct.pack_into(">I", blk, 40, rng.getrandbits(32))
            d0 = sha256_reduced(bytes(blk), rounds)
            blk[63] ^= 1  # flip one padding-adjacent bit... use len byte
            blk2 = bytearray(blk)
            d1 = sha256_reduced(bytes(blk2), rounds)
            x = int.from_bytes(d0, "big") ^ int.from_bytes(d1, "big")
            for bit in range(256):
                flips[bit] += (x >> bit) & 1
        bias = sum(abs(f / trials - 0.5) for f in flips) / 256
        results[rounds] = bias
    return results
