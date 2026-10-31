'use strict';const assert=require('node:assert/strict'),{pathToFileURL}=require('node:url'),root=process.argv[2];
(async()=>{const m=(await import(pathToFileURL(root+'/src/defaultInstance.js').href)).default;assert.equal(m.evaluate('2 not(false)'),2);console.log('checks passed')})().catch(e=>{console.error(e);process.exitCode=1});
