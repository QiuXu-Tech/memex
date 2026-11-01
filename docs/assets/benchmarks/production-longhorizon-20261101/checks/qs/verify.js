'use strict';
const assert = require('node:assert/strict');
const qs = require('/work/lib');
assert.equal(qs.stringify({list:['foo,bar','hello','world']}, {arrayFormat:'comma'}), 'list=foo%2Cbar,hello,world');
assert.equal(qs.stringify({list:['a','b']}, {arrayFormat:'comma'}), 'list=a,b');
assert.equal(qs.stringify({list:['x,y','z']}, {arrayFormat:'comma', encodeValuesOnly:true}), 'list=x%2Cy,z');
assert.equal(qs.stringify({list:['a','b']}, {arrayFormat:'indices'}), 'list%5B0%5D=a&list%5B1%5D=b');
assert.equal(qs.stringify({word:'a,b'}), 'word=a%2Cb');
console.log('issue #387 fixed checks passed');
