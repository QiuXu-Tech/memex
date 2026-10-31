import assert from 'node:assert/strict';import {pathToFileURL} from 'node:url';
const prettier=await import(pathToFileURL(process.argv[2]+'/src/index.js'));const opts={parser:'yaml',proseWrap:'always',printWidth:60};
const src="OffendingTextUsesFoldingBlockScalar:\n  - > \n    First Line.\n             This line is indented and exceeds the print width, but shouldn't be broken, since it will insert a line break where there isn't one currently.\n    This is another line, which should be preceded by a line break, but is safe to break!\n";
const one=await prettier.format(src,opts);const two=await prettier.format(one,opts);assert.equal(one,two);
