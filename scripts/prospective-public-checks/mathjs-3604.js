'use strict';const assert=require('node:assert/strict'),{pathToFileURL}=require('node:url'),root=process.argv[2];
(async()=>{const m=(await import(pathToFileURL(root+'/src/defaultInstance.js').href)).default;const v=m.lgamma(-1.5);assert.ok(Math.abs(v.re-0.860047015376481)<1e-9);console.log('checks passed')})().catch(e=>{console.error(e);process.exitCode=1});
