'use strict';const assert=require('node:assert/strict'),{pathToFileURL}=require('node:url');
(async()=>{const m=(await import(pathToFileURL(process.argv[2]+'/src/defaultInstance.js').href)).default;
assert(Math.abs(m.evaluate('10% + 20%')-.3)<1e-9);assert(Math.abs(m.evaluate('10% + 15%')-.25)<1e-9);console.log('pure percentages passed');
})().catch(e=>{console.error(e);process.exitCode=1});
