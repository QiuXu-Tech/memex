'use strict';
const assert=require('node:assert/strict');const {pathToFileURL}=require('node:url');
(async()=>{const p=await import(pathToFileURL(process.argv[2]+'/src/index.js'));const o={parser:'typescript'};const samples=[
'async function case1(row: BingConnectionRow): Promise<{ row: BingConnectionRow; bundle: BingCredentialBundle; accessToken: string; authorizationVersion: number }> { return null as never; }\n',
'function case2(row: BingConnectionRow): Record<string, { row: BingConnectionRow; bundle: BingCredentialBundle; accessToken: string; authorizationVersion: number }> { return null as never; }\n',
'class A {\n  m(\n    a: string,\n  ): { aaaaaaaaaaaaaaa: number, bbbbbbbbbbbbbbbb: number, cccccccccccccccccc: number } | null {\n    return null\n  }\n}\n'];const failed=[];for(const [i,s] of samples.entries()){const one=await p.format(s,o),two=await p.format(one,o);try{assert.equal(one,two)}catch(e){failed.push(i+1)}};console.log(JSON.stringify({cases:samples.length,unstable:failed}));if(failed.length)process.exitCode=1;})().catch(e=>{console.error(e);process.exitCode=1});
