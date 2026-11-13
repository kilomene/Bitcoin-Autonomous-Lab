#!/usr/bin/env python3
"""Generate the Lab its own Bitcoin wallet (single-key bc1q address).

The private key is written ONLY to the output path given on the command
line, which must live outside the repository. The repository records the
public address only. File permissions on the key file are set to 0600.

Usage:
    wallet_gen.py <key-output-path-outside-repo>

Prints the public address as JSON: {"address": "bc1q..."}
"""

import hashlib
import json
import os
import secrets
import sys

# secp256k1 domain parameters
P = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEFFFFFC2F
N = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364141
GX = 0x79BE667EF9DCBBAC55A06295CE870B07029BFCDB2DCE28D959F2815B16F81798
GY = 0x483ADA7726A3C4655DA4FBFC0E1108A8FD17B448A68554199C47D08FFB10D4B8


def point_add(p, q):
    if p is None:
        return q
    if q is None:
        return p
    x1, y1 = p
    x2, y2 = q
    if x1 == x2 and y1 != y2:
        return None
    if p == q:
        m = (3 * x1 * x1) * pow(2 * y1, P - 2, P) % P
    else:
        m = (y2 - y1) * pow((x2 - x1) % P, P - 2, P) % P
    x3 = (m * m - x1 - x2) % P
    y3 = (m * (x1 - x3) - y1) % P
    return (x3, y3)


def point_mul(k, point):
    result = None
    addend = point
    while k:
        if k & 1:
            result = point_add(result, addend)
        addend = point_add(addend, addend)
        k >>= 1
    return result


def hash160(data: bytes) -> bytes:
    sha = hashlib.sha256(data).digest()
    ripemd = hashlib.new("ripemd160", sha).digest()
    return ripemd


CHARSET = "qpzry9x8gf2tvdw0s3jn54khce6mua7l"


def bech32_polymod(values):
    chk = 1
    gen = [0x3B6A57B2, 0x26508E6D, 0x1EA119FA, 0x3D4233DD, 0x2A1462B3]
    for v in values:
        top = chk >> 25
        chk = (chk & 0x1FFFFFF) << 5 ^ v
        for i in range(5):
            if (top >> i) & 1:
                chk ^= gen[i]
    return chk


def bech32_hrp_expand(hrp):
    return [ord(x) >> 5 for x in hrp] + [0] + [ord(x) & 31 for x in hrp]


def bech32_encode(hrp, witver, witprog):
    data = [witver] + convertbits(witprog, 8, 5)
    values = bech32_hrp_expand(hrp) + data
    const = 1  # bech32 (BIP173) for witness v0
    polymod = bech32_polymod(values + [0] * 6) ^ const
    checksum = [(polymod >> 5 * (5 - i)) & 31 for i in range(6)]
    return hrp + "1" + "".join(CHARSET[d] for d in data + checksum)


def convertbits(data, frombits, tobits, pad=True):
    acc = 0
    bits = 0
    ret = []
    maxv = (1 << tobits) - 1
    for value in data:
        acc = (acc << frombits) | value
        bits += frombits
        while bits >= tobits:
            bits -= tobits
            ret.append((acc >> bits) & maxv)
    if pad and bits:
        ret.append((acc << (tobits - bits)) & maxv)
    return ret


def main():
    if len(sys.argv) != 2:
        print(__doc__, file=sys.stderr)
        return 2
    out_path = sys.argv[1]
    repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if os.path.abspath(out_path).startswith(repo + os.sep):
        print("refusing: key output path must be outside the repository",
              file=sys.stderr)
        return 2

    priv = 0
    while not (1 <= priv < N):
        priv = int.from_bytes(secrets.token_bytes(32), "big")
    x, y = point_mul(priv, (GX, GY))
    compressed = (b"\x03" if y & 1 else b"\x02") + x.to_bytes(32, "big")
    address = bech32_encode("bc", 0, hash160(compressed))

    record = {
        "purpose": "Bitcoin Autonomous Lab payout identity",
        "type": "Single-key P2WPKH address (BIP173 bech32, witness v0). Not a BIP39 seed wallet and not a BIP84 derivation path wallet.",
        "address": address,
        "private_key_hex": "%064x" % priv,
        "compressed_pubkey_hex": compressed.hex(),
        "warning": "Keep this file private and outside the repository. Whoever holds this key controls any coins sent to the address.",
    }
    fd = os.open(out_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as f:
        json.dump(record, f, indent=2)
    print(json.dumps({"address": address}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
