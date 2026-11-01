'use strict';
const assert = require('node:assert/strict');
const _ = require('/work/lodash.js');
let observed;
const target = Object.create({ set value(v) { observed = v; } });
_.assign(target, { value: 42 });
assert.equal(observed, 42);
assert.equal(Object.prototype.hasOwnProperty.call(target, 'value'), false);
console.log('inherited setter assignment preserved');
