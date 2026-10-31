'use strict';
const assert=require('node:assert/strict');const pino=require(process.argv[2]+'/pino');let text='';
const root=pino({base:{},nestedKey:'properties'},{write(v){text+=v;}});root.child({inner:1}).info({one:1});
const value=JSON.parse(text);assert.equal(value.properties.inner,1);assert.equal(value.properties.one,1);
