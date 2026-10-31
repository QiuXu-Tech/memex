import assert from 'node:assert/strict';import {pathToFileURL} from 'node:url';
const prettier=await import(pathToFileURL(process.argv[2]+'/src/index.js'));
const src='.foo {\n  width: someVeryLongFunctionNameForJustAPow(2, someVeryLongFunctionNameForJustAPow(2, someVeryLongFunctionNameForJustAPow(2,\n  // THIS\n  someVeryLongFunctionNameForJustAPow(2, someVeryLongFunctionNameForJustAPow(2, someVeryLongFunctionNameForJustAPow(2, 2))))));\n}\n';
const out=await prettier.format(src,{parser:'scss'});assert.ok(/someVeryLongFunctionNameForJustAPow\(\n          2,/.test(out),'inner indentation should match expected');
