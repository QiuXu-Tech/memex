'use strict';
const assert=require('node:assert/strict');
const {Linter}=require(process.argv[2]);
const code='if(foo === globalThis.NaN){}; [1,2,3].indexOf(globalThis.NaN);';
const messages=new Linter().verify(code,{languageOptions:{ecmaVersion:'latest'},rules:{'use-isnan':['error',{enforceForIndexOf:true}]}});
assert.equal(messages.filter(m=>m.ruleId==='use-isnan').length,2);
