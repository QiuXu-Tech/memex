'use strict';
const assert=require('node:assert/strict');
const pino=require(process.argv[2]+'/browser');
const out=pino.stdSerializers.errWithCause(new Error('outer',{cause:new Error('inner')}));
assert.ok(out.cause, 'nested cause should be serialized');
