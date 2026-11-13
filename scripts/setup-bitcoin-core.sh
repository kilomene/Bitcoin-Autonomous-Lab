#!/usr/bin/env bash
# Download and checksum-verify the Bitcoin Core release used by the Lab.
# The tarball lands outside the repository, in ~/workspace/bitcoin-core-dist.
set -euo pipefail
VERSION="${1:-28.1}"
DIST="$HOME/workspace/bitcoin-core-dist"
mkdir -p "$DIST"
cd "$DIST"
BASE="https://bitcoincore.org/bin/bitcoin-core-$VERSION"
if [ ! -f "bitcoin-$VERSION.tar.gz" ]; then
  curl -sSL -o "bitcoin-$VERSION.tar.gz" "$BASE/bitcoin-$VERSION-x86_64-linux-gnu.tar.gz"
fi
curl -sSL -o SHA256SUMS "$BASE/SHA256SUMS"
EXPECTED="$(grep "bitcoin-$VERSION-x86_64-linux-gnu.tar.gz" SHA256SUMS | awk '{print $1}')"
ACTUAL="$(sha256sum "bitcoin-$VERSION.tar.gz" | awk '{print $1}')"
if [ "$EXPECTED" != "$ACTUAL" ]; then
  echo "CHECKSUM MISMATCH: expected $EXPECTED got $ACTUAL" >&2
  exit 1
fi
echo "checksum verified: $ACTUAL"
if [ ! -d "bitcoin-core-$VERSION" ]; then
  tar xzf "bitcoin-$VERSION.tar.gz"
  mv "bitcoin-$VERSION" "bitcoin-core-$VERSION"
fi
"bitcoin-core-$VERSION/bin/bitcoind" --version | head -1
