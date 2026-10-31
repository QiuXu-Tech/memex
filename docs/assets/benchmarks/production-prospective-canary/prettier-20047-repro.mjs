import assert from 'node:assert/strict';import {pathToFileURL} from 'node:url';
const prettier=await import(pathToFileURL(process.argv[2]+'/src/index.js'));
const out=await prettier.format('alpha <!-- retained comment --> beta\n',{parser:'markdown',proseWrap:'always',printWidth:20});
assert.ok(!/^<!--/m.test(out),'inline HTML comment should not become an HTML block');
