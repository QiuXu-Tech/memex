'use strict';const assert=require('node:assert/strict'),{pathToFileURL}=require('node:url');
(async()=>{const m=(await import(pathToFileURL(process.argv[2]+'/src/defaultInstance.js').href)).default;
assert.equal(m.evaluate('not true'),false);assert.equal(m.evaluate('not(false)'),true);assert(m.evaluate('help(and)').toString().toLowerCase().includes('and'));console.log('logical controls passed');
})().catch(e=>{console.error(e);process.exitCode=1});
