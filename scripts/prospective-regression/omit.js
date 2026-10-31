'use strict';
const assert=require('node:assert/strict');const _=require(process.argv[2]+'/lodash.js');
const source={a:{b:2,c:3},z:4};assert.deepStrictEqual(_.omit(source,'a.b'),{a:{c:3},z:4});assert.deepStrictEqual(source,{a:{b:2,c:3},z:4});
assert.deepStrictEqual(_.omit({a:1,b:2},['a']),{b:2});assert.deepStrictEqual(_.omit(null,'a'),{});console.log('four ordinary omission controls passed');
