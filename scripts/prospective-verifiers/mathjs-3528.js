'use strict';const assert=require('node:assert/strict'),{pathToFileURL}=require('node:url');
(async()=>{const m=(await import(pathToFileURL(process.argv[2]+'/src/defaultInstance.js').href)).default;
const d=m.derivative('x * derivative(\"e^x\", \"x\")','x');assert(Math.abs(d.evaluate({x:1})-2*Math.E)<1e-8);assert(Math.abs(d.evaluate({x:0})-1)<1e-8);console.log('nested derivative passed');
})().catch(e=>{console.error(e);process.exitCode=1});
