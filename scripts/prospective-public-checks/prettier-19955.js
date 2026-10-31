'use strict';
const assert=require('node:assert/strict');const {pathToFileURL}=require('node:url');
(async()=>{const p=await import(pathToFileURL(process.argv[2]+'/src/index.js'));const o={parser:'babel',singleQuote:true};const one=await p.format('x2 = (a) => (a /* ! */ // K\n)\n',o);assert.equal(await p.format(one,o),one);assert.ok(one.includes('/* ! */')&&one.includes('// K'));console.log('public example passed');})().catch(e=>{console.error(e);process.exitCode=1});
