'use strict';
const assert = require('node:assert/strict');
const { Linter } = require(process.argv[2]);
const options = { languageOptions: { ecmaVersion: 'latest' }, rules: { eqeqeq: 'error' } };
const result = new Linter().verifyAndFix('const b={toString:()=>"number"};let a=1;typeof a == b;', options);
assert.equal(result.fixed, false);
assert.ok(result.messages.some(m => m.ruleId === 'eqeqeq'));
console.log('public example passed');
