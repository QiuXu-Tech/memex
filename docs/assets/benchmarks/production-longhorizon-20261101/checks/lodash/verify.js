'use strict';
const assert = require('node:assert/strict');
const _ = require('/work/lodash.js');
Object.freeze(Object.prototype);
const original = { foo: 'bar', hasOwnProperty: 'data', nested: { hasOwnProperty: 'nested' } };
for (const clone of [_.clone(original), _.cloneDeep(original)]) {
  assert.equal(Object.prototype.hasOwnProperty.call(clone, 'hasOwnProperty'), true);
  assert.equal(clone.hasOwnProperty, 'data');
  assert.equal(clone.foo, 'bar');
}
assert.equal(_.cloneDeep(original).nested.hasOwnProperty, 'nested');
const special = JSON.parse('{"__proto__":{"polluted":true},"safe":1}');
const copied = _.cloneDeep(special);
assert.equal(Object.prototype.polluted, undefined);
assert.equal(Object.prototype.hasOwnProperty.call(copied, '__proto__'), true);
assert.equal(copied.safe, 1);
console.log('issue #6112 fixed checks passed');
