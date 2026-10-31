'use strict';
const assert=require('node:assert/strict');const pino=require(process.argv[2]+'/pino');let text='';
const root=pino({base:{},formatters:{bindings(o){return Object.fromEntries(Object.entries(o).map(([k,v])=>[k,typeof v==='string'?v.toUpperCase():v]));}}},{write(v){text+=v;}});root.child({partner:'Apple'}).info('hello');
assert.equal(JSON.parse(text).partner,'APPLE');
