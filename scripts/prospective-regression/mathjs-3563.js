'use strict';const assert=require('node:assert/strict'),{pathToFileURL}=require('node:url');
(async()=>{const m=(await import(pathToFileURL(process.argv[2]+'/src/defaultInstance.js').href)).default;
assert.equal(m.evaluate('10 % 3'),1);assert.equal(m.evaluate('100 + 10%'),110);console.log('modulus and relative percentage controls passed');
})().catch(e=>{console.error(e);process.exitCode=1});
