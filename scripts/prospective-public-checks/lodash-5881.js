'use strict';
const assert=require('node:assert/strict');const _=require(process.argv[2]+'/lodash.js');
const object={a:1,b:2,get c(){throw Error('omitted getter');}};assert.deepStrictEqual(_.omit(object,'c'),{a:1,b:2});console.log('public example passed');
