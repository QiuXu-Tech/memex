'use strict';
const assert=require('node:assert/strict');
const {Linter}=require(process.argv[2]);
const code='function withBraces(){if(a){b();}} function withoutBraces(){if(a)b();} function withSwitch(x){switch(x){case 1:a();b();c();break;}}';
const messages=new Linter().verify(code,{languageOptions:{ecmaVersion:'latest'},rules:{'max-statements':['error',1]}});
assert.equal(messages.filter(m=>m.ruleId==='max-statements').length,3);
