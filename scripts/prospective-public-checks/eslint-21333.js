'use strict';
const assert = require('node:assert/strict');
const { Linter } = require(process.argv[2]);
const options = { languageOptions: { ecmaVersion: 'latest', sourceType: 'module' }, rules: { 'max-statements': ['error', 1] } };
const messages = new Linter().verify('function f(){if(a)b();}', options);
assert.equal(messages.filter(m => m.ruleId === 'max-statements').length, 1);
console.log('public example passed');
