import assert from 'node:assert/strict';import {pathToFileURL} from 'node:url';
const prettier=await import(pathToFileURL(process.argv[2]+'/src/index.js'));const opts={parser:'typescript'};
const src='async function case1(row: BingConnectionRow): Promise<{ row: BingConnectionRow; bundle: BingCredentialBundle; accessToken: string; authorizationVersion: number }> { return null as never; }\n';
const one=await prettier.format(src,opts);const two=await prettier.format(one,opts);assert.equal(one,two);
