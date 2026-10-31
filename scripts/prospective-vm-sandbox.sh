#!/usr/bin/env bash
# Run one fixed Node verifier in an isolated Linux guest. Never accepts shell code.
set -euo pipefail
if [[ $(id -u) != 0 || $# != 3 ]]; then
  echo 'usage (inside pilot VM as root): sandbox WORKSPACE CHECK_DIR TIMEOUT_SECONDS' >&2
  exit 2
fi
workspace=$(realpath -e -- "$1")
checks=$(realpath -e -- "$2")
seconds=$3
case "$workspace/" in /opt/memex-pilot/workspaces/*/) ;; *) echo 'workspace outside pilot root' >&2; exit 2;; esac
case "$checks/" in /opt/memex-pilot/checks/*/) ;; *) echo 'checks outside pilot root' >&2; exit 2;; esac
if [[ ! $seconds =~ ^[0-9]+$ ]] || (( seconds < 1 || seconds > 120 )); then
  echo 'timeout must be between 1 and 120 seconds' >&2; exit 2
fi
[[ -f "$checks/verify.js" && ! -L "$checks/verify.js" ]] || { echo 'missing verifier' >&2; exit 2; }
exec systemd-run --scope --quiet -p MemoryMax=768M -p TasksMax=64 -p CPUQuota=150% \
  timeout --signal=KILL --kill-after=2 "$seconds" \
  prlimit --as=17179869184 --nproc=64 --nofile=128 --fsize=16777216 -- \
  bwrap --unshare-all --die-with-parent --new-session --uid 65534 --gid 65534 --cap-drop ALL \
  --clearenv --setenv PATH /node/bin:/usr/bin:/bin --setenv HOME /tmp --setenv LANG C.UTF-8 --setenv CI 1 \
  --ro-bind /usr /usr --symlink usr/lib /lib --symlink usr/bin /bin \
  --ro-bind /opt/memex-pilot/node /node --ro-bind "$workspace" /work --ro-bind "$checks" /checks \
  --proc /proc --dev /dev --tmpfs /tmp --chdir /work \
  /node/bin/node /checks/verify.js /work
