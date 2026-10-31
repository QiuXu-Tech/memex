'use strict';const assert=require('node:assert/strict'),{pathToFileURL}=require('node:url');
(async()=>{const m=(await import(pathToFileURL(process.argv[2]+'/src/defaultInstance.js').href)).default;
for(const meters of [1]){const r=m.evaluate(`(${meters} m).splitUnit([\"ft\",\"in\"])`);const a=Array.isArray(r)?r:r.toArray();assert.equal(a.length,2);assert.equal(a[0].toNumber('ft'),3*meters);assert(Math.abs(a[1].toNumber('in')-3.37007874015748*meters)<1e-8)}console.log('splitUnit parser conversions passed');
})().catch(e=>{console.error(e);process.exitCode=1});
