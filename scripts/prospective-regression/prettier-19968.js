'use strict';
const assert=require('node:assert/strict');const {pathToFileURL}=require('node:url');
(async()=>{const p=await import(pathToFileURL(process.argv[2]+'/src/index.js'));const o={parser:'typescript'};const samples=['function id<T>(x: T): T { return x; }\n','type Item = { id: number; name: string };\n','class C { method(a: number): string { return String(a); } }\n'];for(const s of samples){const one=await p.format(s,o);assert.equal(await p.format(one,o),one);}console.log('regression controls passed');})().catch(e=>{console.error(e);process.exitCode=1});
