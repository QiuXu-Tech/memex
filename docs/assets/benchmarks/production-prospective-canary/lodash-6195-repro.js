'use strict';
const assert = require('node:assert/strict');
const _ = require(process.argv[2] + '/lodash.js');
const inverted = _.invert({ userId: 'alice', role: '__proto__', team: 'eng' });
assert.equal(Object.prototype.hasOwnProperty.call(inverted, '__proto__'), true);
assert.equal(inverted['__proto__'], 'role');
const groups = _.invertBy({ a: 'group1', b: '__proto__', c: 'group1' });
assert.equal(Object.prototype.hasOwnProperty.call(groups, '__proto__'), true);
assert.deepStrictEqual(groups['__proto__'], ['b']);
