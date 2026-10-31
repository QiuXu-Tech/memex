'use strict';const assert=require('node:assert/strict'),root=process.argv[2],q=require(root+'/lib/index.js');
(async()=>{assert.deepEqual(q.parse('=1&x=y&=2',{allowEmptyKeys:true}),{'':['1','2'],x:'y'});assert.deepEqual(q.parse('&&',{allowEmptyKeys:true}),{});console.log('checks passed')})().catch(e=>{console.error(e);process.exitCode=1});
