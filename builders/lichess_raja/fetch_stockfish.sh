#!/usr/bin/env bash
# Download official Stockfish into engines/stockfish (not committed).
# https://github.com/official-stockfish/Stockfish/releases
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
DEST_DIR="$ROOT/engines"
DEST="$DEST_DIR/stockfish"
BASE="https://github.com/official-stockfish/Stockfish/releases/latest/download"

os="$(uname -s)"
arch="$(uname -m)"
case "$os:$arch" in
  Darwin:arm64)  asset="stockfish-macos-m1-apple-silicon.tar" ;;
  Darwin:x86_64) asset="stockfish-macos-x86-64-avx2.tar" ;;
  Linux:x86_64)  asset="stockfish-ubuntu-x86-64-avx2.tar" ;;
  Linux:aarch64|Linux:arm64)
    echo "no official linux-arm64 tarball — compile Stockfish or set STOCKFISH_PATH" >&2
    exit 1
    ;;
  *)
    echo "unknown platform $os $arch — set STOCKFISH_PATH yourself" >&2
    exit 1
    ;;
esac

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
url="$BASE/$asset"
echo "fetch $url"
curl -fsSL -o "$tmp/sf.tar" "$url"
tar -xf "$tmp/sf.tar" -C "$tmp"
bin="$(find "$tmp" -type f \( -name 'stockfish*' -o -name 'stockfish' \) ! -name '*.tar' | head -1)"
if [[ -z "$bin" ]]; then
  echo "no stockfish binary in archive" >&2
  find "$tmp" -type f | head -40 >&2
  exit 1
fi
mkdir -p "$DEST_DIR"
cp "$bin" "$DEST"
chmod +x "$DEST"
echo "installed $DEST"
"$DEST" quit <<< $'uci\nquit' | head -5
