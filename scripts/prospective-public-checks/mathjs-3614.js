'use strict';const assert=require('node:assert/strict'),{pathToFileURL}=require('node:url');

(async()=>{const m=(await import(pathToFileURL(process.argv[2]+'/src/defaultInstance.js').href)).default;assert.equal(m.unit(1,'MVAR').to('kVAR').format(),'1000 kVAR');console.log('unit complex component formatting checks passed');})().catch(e=>{console.error(e);process.exitCode=1});
