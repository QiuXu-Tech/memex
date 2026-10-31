'use strict';
const assert = require('node:assert/strict');
const _ = require(process.argv[2] + '/lodash.js');
const input = {a:1,b:2,get c(){throw new Error('unimplemented');}};
assert.deepStrictEqual(_.omit(input, 'c'), {a:1,b:2});
