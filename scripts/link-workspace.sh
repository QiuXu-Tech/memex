#!/bin/sh
# Link the sibling @qiuxu packages into this workspace root so that the
# packages can import each other by package name during local development and
# tests (the host resolves the same names through the profile's node_modules).
set -eu
HERE=$(cd "$(dirname "$0")/.." && pwd)
mkdir -p "$HERE/node_modules/@qiuxu"
for pkg in memex memex-seam memex-local memex-checkpoint memex-tool memex-command memex-api memex-ui memex-evict memex-compress; do
  ln -sfn "../../packages/$pkg" "$HERE/node_modules/@qiuxu/$pkg"
done
echo "linked @qiuxu/* into $HERE/node_modules/@qiuxu"
