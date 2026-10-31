'use strict';
const assert=require('node:assert/strict');const path=require('node:path');const root=process.argv[2];
const lodash=require(path.join(root,'lodash.js'));const convert=require(path.join(root,'fp/_baseConvert.js'));
assert.equal(Array.isArray.convert,undefined);convert(lodash,lodash.runInContext());assert.equal(Array.isArray.convert,undefined);
