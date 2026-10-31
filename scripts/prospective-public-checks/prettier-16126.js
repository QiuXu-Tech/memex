'use strict';
const assert=require('node:assert/strict');const {pathToFileURL}=require('node:url');
(async()=>{const root=process.argv[2],p=await import(pathToFileURL(root+'/src/index.js')),yaml=require(root+'/node_modules/yaml');
const input="OffendingTextUsesFoldingBlockScalar:\n  - > \n    First Line.\n             This line is indented and exceeds the print width, but shouldn't be broken, since it will insert a line break where there isn't one currently.\n    This is another line, which should be preceded by a line break, but is safe to break!\n";const opts={parser:'yaml',printWidth:61,proseWrap:'always',embeddedLanguageFormatting:'off'};
const out=await p.format(input,opts);assert.deepStrictEqual(yaml.parse(out),yaml.parse(input));assert.equal(await p.format(out,opts),out);
console.log('issue semantic and idempotence checks passed')})().catch(e=>{console.error(e);process.exitCode=1});
