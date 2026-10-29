#!/bin/sh
# Link the sibling @qiuxu packages into this workspace root so that the
# packages can import each other by package name during local development and
# tests (the host resolves the same names through the profile's node_modules).
set -eu
HERE=$(cd "$(dirname "$0")/.." && pwd)
mkdir -p "$HERE/node_modules/@qiuxu"
for pkg in dsh-memory dsh-memory-seam dsh-memory-local dsh-memory-checkpoint dsh-memory-tool dsh-memory-command dsh-memory-api dsh-memory-ui dsh-memory-evict dsh-memory-compress; do
  ln -sfn "../../packages/$pkg" "$HERE/node_modules/@qiuxu/$pkg"
done
echo "linked @qiuxu/* into $HERE/node_modules/@qiuxu"
