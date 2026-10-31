'use strict';
const assert=require('node:assert/strict');
const pino=require(process.argv[2]+'/pino');
const log=pino({}, {write(){}});const fn=log.error;
assert.doesNotThrow(()=>fn('FAIL'));
