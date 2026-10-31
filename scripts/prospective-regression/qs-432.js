'use strict';const assert=require('node:assert/strict'),root=process.argv[2],q=require(root+'/lib/index.js');
(async()=>{assert.deepEqual(q.parse('=1&=2'),{});assert.deepEqual(q.parse('a=1&a=2'),{a:['1','2']});assert.deepEqual(q.parse('x[y]=z'),{x:{y:'z'}});console.log('checks passed')})().catch(e=>{console.error(e);process.exitCode=1});
