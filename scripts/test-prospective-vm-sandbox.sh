#!/usr/bin/env bash
# Run only inside a dedicated disposable VM, as root.
set -euo pipefail
[[ $(id -u) == 0 ]] || { echo 'requires VM root' >&2; exit 2; }
base=/opt/memex-pilot
sandbox=${1:?supply prospective-vm-sandbox.sh path}
mkdir -p "$base/workspaces/smoke" "$base/checks/smoke" "$base/checks/timeout"
printf 'visible\n' > "$base/workspaces/smoke/input.txt"
printf 'not-a-secret\n' > "$base/sentinel.txt"
cat > "$base/checks/smoke/verify.js" <<'JS'
'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),net=require('node:net'),cp=require('node:child_process');
assert.equal(process.getuid(),65534);assert.equal(fs.readFileSync('/work/input.txt','utf8'),'visible\n');
for(const p of ['/opt/memex-pilot/sentinel.txt','/Users','/etc/shadow']) assert.throws(()=>fs.readFileSync(p));
assert.throws(()=>fs.writeFileSync('/work/input.txt','changed'));
assert.throws(()=>fs.writeFileSync('/node/blocked','changed'));
assert.notEqual(cp.spawnSync('/usr/bin/sudo',['-n','id']).status,0);
const s=net.connect({host:'192.168.5.2',port:7890});s.on('connect',()=>{throw Error('unexpected network access')});s.on('error',e=>{assert.ok(['ENETUNREACH','EACCES','EPERM'].includes(e.code),e.code);console.log('sandbox boundary smoke passed')});
JS
cat > "$base/checks/timeout/verify.js" <<'JS'
for (;;) {}
JS
chmod -R a+rX "$base/workspaces/smoke" "$base/checks/smoke" "$base/checks/timeout"
"$sandbox" "$base/workspaces/smoke" "$base/checks/smoke" 5
set +e
"$sandbox" "$base/workspaces/smoke" "$base/checks/timeout" 2 >/dev/null 2>&1
status=$?
set -e
[[ $status == 124 || $status == 137 ]] || { echo "timeout failed: $status" >&2; exit 1; }
if "$sandbox" /etc "$base/checks/smoke" 5 >/dev/null 2>&1; then echo 'path check failed' >&2; exit 1; fi
echo 'timeout and path checks passed'
