'use strict';
const assert=require('node:assert/strict');const _=require(process.argv[2]+'/lodash.js');const failures=[];
try{const result=_.invert({userId:'alice',role:'__proto__',team:'eng'});assert.equal(Object.hasOwn(result,'__proto__'),true);assert.equal(result['__proto__'],'role');assert.equal(result.alice,'userId');assert.equal(result.eng,'team');assert.equal(Object.getPrototypeOf(result),Object.prototype);}catch(e){failures.push({case:'invert',error:e.message});}
try{const result=_.invertBy({a:'group1',b:'__proto__',c:'group1'});assert.equal(Object.hasOwn(result,'__proto__'),true);assert.deepStrictEqual(result['__proto__'],['b']);assert.deepStrictEqual(result.group1,['a','c']);assert.equal(Object.getPrototypeOf(result),Object.prototype);}catch(e){failures.push({case:'invertBy',error:e.message});}
assert.deepStrictEqual(failures,[]);console.log('acceptance and regression checks passed');
