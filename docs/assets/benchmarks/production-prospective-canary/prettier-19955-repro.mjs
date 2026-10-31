import assert from 'node:assert/strict';import {pathToFileURL} from 'node:url';
const prettier=await import(pathToFileURL(process.argv[2]+'/src/index.js'));
const opts={parser:'babel',singleQuote:true};const one=await prettier.format('x2 = (a) => (a /* ! */ // K\n)\n',opts);const two=await prettier.format(one,opts);assert.equal(one,two);
