'use strict';const assert=require('node:assert/strict'),{pathToFileURL}=require('node:url');
(async()=>{const m=(await import(pathToFileURL(process.argv[2]+'/src/defaultInstance.js').href)).default;
const a=m.unit(1,'m').splitUnit(['ft','in']);assert.equal(a.length,2);assert.equal(a[0].toNumber('ft'),3);assert.equal(m.unit(1,'m').toNumber('cm'),100);console.log('unit controls passed');
})().catch(e=>{console.error(e);process.exitCode=1});
