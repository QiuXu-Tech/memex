'use strict';
// The issue and maintainer comment specify nested/braceless and empty cases.
const assert=require('node:assert/strict');
const {Linter}=require(process.argv[2]);
const config={languageOptions:{ecmaVersion:'latest',sourceType:'module'},rules:{'max-statements':['error',1]}};
const cases=[
 ['braced','function f(){if(a){b();}}',1],
 ['braceless','function f(){if(a)b();}',1],
 ['switch','function f(x){switch(x){case 1:a();b();c();break;}}',1],
 ['empty statement','function f(){if(true);}',0],
 ['empty block','function f(){if(true){}}',0],
 ['one statement','function f(){a();}',0],
 ['separate nested function','function f(){function g(){a();b();}}',1],
];
const failures=[];
for(const [name,code,expected] of cases){const messages=new Linter().verify(code,config);const actual=messages.filter(x=>x.ruleId==='max-statements').length;const other=messages.filter(x=>x.ruleId!=='max-statements');if(actual!==expected||other.length)failures.push({name,expected,actual,other});}
assert.deepStrictEqual(failures,[]);console.log('acceptance and regression checks passed');
