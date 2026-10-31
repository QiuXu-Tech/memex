'use strict';
const assert=require('node:assert/strict');
const {Linter}=require(process.argv[2]);
const result=new Linter().verifyAndFix('const b={toString:()=>"number"}; let a=1; typeof a == b;', {languageOptions:{ecmaVersion:'latest'},rules:{eqeqeq:'error'}});
assert.equal(result.fixed,false,'an unsafe comparison should not be autofixed');
