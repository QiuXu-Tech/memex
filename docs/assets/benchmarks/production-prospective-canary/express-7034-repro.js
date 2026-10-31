'use strict';
const assert = require('node:assert/strict');
const response=require(process.argv[2]+'/lib/response');let observed;
const mock={setHeader(_name,value){observed=value;}};
response.set.call(mock,'Content-Type','some-custom-type');
assert.equal(observed,'some-custom-type');
