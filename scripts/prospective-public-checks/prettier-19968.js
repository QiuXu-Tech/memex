'use strict';
const assert=require('node:assert/strict');const {pathToFileURL}=require('node:url');
(async()=>{const p=await import(pathToFileURL(process.argv[2]+'/src/index.js'));const o={parser:'typescript'};const s='async function case1(row: BingConnectionRow): Promise<{ row: BingConnectionRow; bundle: BingCredentialBundle; accessToken: string; authorizationVersion: number }> { return null as never; }\n';const one=await p.format(s,o);assert.equal(await p.format(one,o),one);console.log('public example passed');})().catch(e=>{console.error(e);process.exitCode=1});
