'use strict';const assert=require('node:assert/strict'),{pathToFileURL}=require('node:url');
(async()=>{const m=(await import(pathToFileURL(process.argv[2]+'/src/defaultInstance.js').href)).default;
const h=m.evaluate('help(not)');assert(h.toString().toLowerCase().includes('not'));console.log('help not passed');
})().catch(e=>{console.error(e);process.exitCode=1});
