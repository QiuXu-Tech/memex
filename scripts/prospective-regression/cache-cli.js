'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),os=require('node:os'),path=require('node:path'),{spawnSync}=require('node:child_process');
const dir=fs.mkdtempSync(path.join(os.tmpdir(),'eslint-cache-reg-'));const root=process.argv[2];fs.writeFileSync(path.join(dir,'x.js'),'debugger;\n');
fs.writeFileSync(path.join(dir,'eslint.config.js'),'module.exports=[{rules:{"no-debugger":"off"}}];\n');
function run(args){const r=spawnSync(process.execPath,[path.join(root,'bin/eslint.js'),...args],{cwd:dir,encoding:'utf8',timeout:12000});if(r.error)throw r.error;return {code:r.status,out:r.stdout+r.stderr};}
assert.equal(run(['--cache','--cache-location','cache','x.js']).code,0);
const cached=run(['--debug','--cache','--cache-location','cache','x.js']);assert.equal(cached.code,0);assert.match(cached.out,/Skipping file since it hasn't changed/);
fs.writeFileSync(path.join(dir,'eslint.config.js'),'module.exports=[{rules:{"no-debugger":"error"}}];\n');
const changed=run(['--cache','--cache-location','cache','x.js']);assert.equal(changed.code,1);assert.match(changed.out,/no-debugger/);
console.log('cache reuse and config invalidation controls passed');
