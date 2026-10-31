import assert from 'node:assert/strict';import {pathToFileURL} from 'node:url';
const prettier=await import(pathToFileURL(process.argv[2]+'/src/index.js'));
const out=await prettier.format('await { then() {} };\n\nawait getPromise;\n',{parser:'typescript'});
assert.equal((out.match(/await getPromise/g)||[]).length,1);
