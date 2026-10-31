'use strict';
const assert=require('node:assert/strict');const _=require(process.argv[2]+'/lodash.js');
assert.equal(_.camelCase('IDs'),'ids');assert.equal(_.camelCase('Product XMLs'),'productXmls');console.log('public example passed');
