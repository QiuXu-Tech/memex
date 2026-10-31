'use strict';
const assert=require('node:assert/strict');const {pathToFileURL}=require('node:url');
(async()=>{const root=process.argv[2],p=await import(pathToFileURL(root+'/src/index.js')),yaml=require(root+'/node_modules/yaml');
const cases=['name: sample\nitems:\n  - one\n  - two\n','message: >-\n  This is a longer ordinary line that may wrap but must keep its parsed contents.\n','script: |\n  echo one\n  echo two\n'];
for(const s of cases){const o={parser:'yaml',printWidth:40,proseWrap:'always'};const a=await p.format(s,o);assert.deepStrictEqual(yaml.parse(a),yaml.parse(s));assert.equal(await p.format(a,o),a)}console.log('three YAML regression controls passed')})().catch(e=>{console.error(e);process.exitCode=1});
