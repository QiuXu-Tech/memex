'use strict';const assert=require('node:assert/strict'),{pathToFileURL}=require('node:url');
(async()=>{const m=(await import(pathToFileURL(process.argv[2]+'/src/defaultInstance.js').href)).default;
const d=m.derivative('x * e^x','x');assert(Math.abs(d.evaluate({x:1})-2*Math.E)<1e-8);assert.equal(m.derivative('x^2','x').evaluate({x:3}),6);console.log('ordinary derivative controls passed');
})().catch(e=>{console.error(e);process.exitCode=1});
