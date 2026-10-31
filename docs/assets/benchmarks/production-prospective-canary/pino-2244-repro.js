'use strict';
const assert=require('node:assert/strict');
const pino=require(process.argv[2]+'/browser');
const calls=[];const log=pino({browser:{asObject:true,write:(...args)=>calls.push(args)},level:'debug'});
log.debug('bla',{di:'da'});
assert.ok(JSON.stringify(calls).includes('"di":"da"'), 'logging argument should be retained');
