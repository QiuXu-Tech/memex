'use strict';
const assert=require('node:assert/strict');const pino=require(process.argv[2]+'/browser');const failures=[];
try{const source=new Error('outer',{cause:new Error('inner')});const out=pino.stdSerializers.errWithCause(source);assert.equal(out.type,'Error');assert.equal(out.msg,'outer');assert.ok(out.cause && typeof out.cause==='object');assert.ok(JSON.stringify(out.cause).includes('inner'));}catch(e){failures.push({case:'cause preserved',error:e.message});}
try{const out=pino.stdSerializers.err(new Error('plain'));assert.equal(out.type,'Error');assert.equal(out.msg,'plain');assert.equal(typeof out.stack,'string');}catch(e){failures.push({case:'ordinary error',error:e.message});}
assert.deepStrictEqual(failures,[]);console.log('acceptance and regression checks passed');
