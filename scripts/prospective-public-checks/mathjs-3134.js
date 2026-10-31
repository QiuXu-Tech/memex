'use strict';const assert=require('node:assert/strict'),{pathToFileURL}=require('node:url');const root=process.argv[2];
(async()=>{const m=(await import(pathToFileURL(root+'/src/defaultInstance.js').href)).default;const low=m.unit('9 degC'),high=m.unit('10 degC');assert.equal(m.smaller(low.to('degF'),high),true);console.log('checks passed')})().catch(e=>{console.error(e);process.exitCode=1});
