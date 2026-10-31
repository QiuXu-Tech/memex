'use strict';
const assert=require('node:assert/strict');
const {Linter}=require(process.argv[2]);
const code='Object.groupBy(inventory,({type})=>{if(type==="fruit")return "fruit";});';
const messages=new Linter().verify(code,{languageOptions:{ecmaVersion:'latest'},rules:{'array-callback-return':'error'}});
assert.ok(messages.some(m=>m.ruleId==='array-callback-return'));
