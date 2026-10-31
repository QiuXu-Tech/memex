import assert from 'node:assert/strict';import {pathToFileURL} from 'node:url';
const prettier=await import(pathToFileURL(process.argv[2]+'/src/index.js'));const out=await prettier.format('{\n"a": "b"\n}',{parser:'jsonc'});assert.ok(!/"b",/.test(out));
