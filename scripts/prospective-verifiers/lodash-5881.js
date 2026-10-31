'use strict';
const assert=require('node:assert/strict');const _=require(process.argv[2]+'/lodash.js');const failures=[];
try{let count=0;const input={a:1,b:2,get c(){count++;throw Error('omitted getter accessed');}};const actual=_.omit(input,'c');assert.deepStrictEqual(actual,{a:1,b:2});assert.equal(count,0);}catch(e){failures.push({case:'omitted getter',error:e.message});}
try{let count=0;const input={a:1,get b(){count++;return 2;},c:3};assert.deepStrictEqual(_.omit(input,'c'),{a:1,b:2});assert.equal(count,1);}catch(e){failures.push({case:'retained getter',error:e.message});}
try{assert.deepStrictEqual(_.omit({a:1,b:2},'b'),{a:1});}catch(e){failures.push({case:'plain values',error:e.message});}
assert.deepStrictEqual(failures,[]);console.log('acceptance and regression checks passed');
