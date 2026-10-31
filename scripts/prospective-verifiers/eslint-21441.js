'use strict';
// Cache must not reuse results across changes to inline-config or quiet behavior.
const assert=require('node:assert/strict');const fs=require('node:fs');const os=require('node:os');const path=require('node:path');const {spawnSync}=require('node:child_process');
const root=process.argv[2];const dir=fs.mkdtempSync(path.join(os.tmpdir(),'eslint-cache-check-'));
fs.writeFileSync(path.join(dir,'eslint.config.js'),'module.exports=[{rules:{"no-debugger":"error","no-unused-vars":"warn"}}];\n');
fs.writeFileSync(path.join(dir,'b.js'),'debugger; // eslint-disable-line no-debugger\n');fs.writeFileSync(path.join(dir,'w.js'),'const unused = 1;\n');
function run(args){const r=spawnSync(process.execPath,[path.join(root,'bin/eslint.js'),...args],{cwd:dir,encoding:'utf8',timeout:12000});if(r.error)throw r.error;return {code:r.status,out:r.stdout+r.stderr};}
const failures=[];
function check(name,fn){try{fn();}catch(e){failures.push({name,error:e.message});}}
check('uncached inline control',()=>{const r=run(['--no-inline-config','b.js']);assert.equal(r.code,1);assert.match(r.out,/no-debugger/);});
check('cached inline toggle',()=>{assert.equal(run(['--cache','--cache-location','cache-inline','b.js']).code,0);const r=run(['--cache','--cache-location','cache-inline','--no-inline-config','b.js']);assert.equal(r.code,1);assert.match(r.out,/no-debugger/);});
check('uncached warning control',()=>{const r=run(['--max-warnings','0','w.js']);assert.equal(r.code,1);assert.match(r.out,/no-unused-vars/);});
check('cached quiet toggle',()=>{assert.equal(run(['--cache','--cache-location','cache-quiet','--quiet','w.js']).code,0);const r=run(['--cache','--cache-location','cache-quiet','--max-warnings','0','w.js']);assert.equal(r.code,1);assert.match(r.out,/no-unused-vars/);});
check('unchanged file still uses cache',()=>{assert.equal(run(['--cache','--cache-location','cache-steady','b.js']).code,0);const r=run(['--debug','--cache','--cache-location','cache-steady','b.js']);assert.equal(r.code,0);assert.match(r.out,/Skipping file since it hasn't changed/);});
assert.deepStrictEqual(failures,[]);console.log('cache behavior and controls passed');
