'use strict';const assert=require('node:assert/strict'),fs=require('node:fs');const root=process.argv[2],ts=require(root+'/node_modules/typescript');
require.extensions['.ts']=(module,filename)=>{const source=ts.transpileModule(fs.readFileSync(filename,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022,esModuleInterop:true}}).outputText;module._compile(source,filename)};
const y=require(root+'/src/index.ts');assert.deepEqual(y.array().of(y.number().required()).default([1]).validateSync(undefined),[1]);console.log('array default validation passed');
