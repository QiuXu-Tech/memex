import assert from 'node:assert/strict';import {pathToFileURL} from 'node:url';
const prettier=await import(pathToFileURL(process.argv[2]+'/src/index.js'));
const one=await prettier.format('> Foo\n===\n',{parser:'markdown'});assert.equal(one,'> Foo\n===\n');
