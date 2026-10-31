import assert from 'node:assert/strict';import {pathToFileURL} from 'node:url';
const prettier=await import(pathToFileURL(process.argv[2]+'/src/index.js'));
const out=await prettier.format('a:\n  b: |\n    x \n  c: 1\n',{parser:'yaml'});
assert.ok(/^  c: 1$/m.test(out),'key c should remain nested');
