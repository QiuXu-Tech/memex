'use strict';const assert=require('node:assert/strict'),{pathToFileURL}=require('node:url');const root=process.argv[2];
(async()=>{const m=(await import(pathToFileURL(root+'/src/defaultInstance.js').href)).default;assert.equal(m.unit('m^2').equals(m.unit('m*m')),true);assert.throws(()=>m.unit('m^()'),SyntaxError);console.log('checks passed')})().catch(e=>{console.error(e);process.exitCode=1});
