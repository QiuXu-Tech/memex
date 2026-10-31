'use strict';
const assert=require('node:assert/strict');
const {Linter}=require(process.argv[2]);
const code='JSON.stringify(data,function(key,value){return this[key]}); JSON.parse(json,function(key,value){return this.type});';
const messages=new Linter().verify(code,{languageOptions:{ecmaVersion:'latest',sourceType:'module'},rules:{'no-invalid-this':'error'}});
assert.equal(messages.filter(m=>m.ruleId==='no-invalid-this').length,0);
