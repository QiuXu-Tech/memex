'use strict';
const assert = require('node:assert/strict');
const { Linter } = require(process.argv[2]);
const options = { languageOptions: { ecmaVersion: 'latest', sourceType: 'module' }, rules: { 'no-invalid-this': 'error' } };
const messages = new Linter().verify('JSON.parse(json, function(key, value) { return this[key]; });', options);
assert.equal(messages.filter(m => m.ruleId === 'no-invalid-this').length, 0);
console.log('public example passed');
