'use strict';const assert=require('node:assert/strict'),{pathToFileURL}=require('node:url'),root=process.argv[2];
(async()=>{const m=(await import(pathToFileURL(root+'/src/defaultInstance.js').href)).default;assert.ok(Math.abs(m.lgamma(5)-3.178053830347945)<1e-9);assert.equal(m.lgamma(0),Infinity);console.log('checks passed')})().catch(e=>{console.error(e);process.exitCode=1});
