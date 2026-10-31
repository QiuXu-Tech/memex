'use strict';
const assert=require('node:assert/strict');const _=require(process.argv[2]+'/lodash.js');
assert.deepStrictEqual(_.invert({a:'one',b:'two'}),{one:'a',two:'b'});
assert.deepStrictEqual(_.invert({a:'one',b:'one'}),{one:'b'});
assert.deepStrictEqual(_.invertBy({a:'one',b:'one'}),{one:['a','b']});
const out=_.invert({x:'constructor'});assert.equal(Object.hasOwn(out,'constructor'),true);assert.equal(out.constructor,'x');
assert.equal(Object.getPrototypeOf(out),Object.prototype);console.log('five ordinary inversion controls passed');
