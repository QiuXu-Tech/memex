'use strict';const assert=require('node:assert/strict'),fs=require('node:fs');const root=process.argv[2],ts=require(root+'/node_modules/typescript');
require.extensions['.ts']=(module,filename)=>{const source=ts.transpileModule(fs.readFileSync(filename,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022,esModuleInterop:true}}).outputText;module._compile(source,filename)};
const y=require(root+'/src/index.ts');const s=y.object().shape({});assert.equal(s.validateSync({constructor:'bar'}).constructor,'bar');console.log('prototype-name fields passed');
