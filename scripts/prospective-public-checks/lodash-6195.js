'use strict';
const assert=require('node:assert/strict');const _=require(process.argv[2]+'/lodash.js');
const result=_.invert({role:'__proto__'});assert.equal(Object.hasOwn(result,'__proto__'),true);assert.equal(result.__proto__,'role');console.log('public example passed');
