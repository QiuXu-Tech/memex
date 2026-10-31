'use strict';const assert=require('node:assert/strict'),root=process.argv[2],q=require(root+'/lib/index.js');
(async()=>{assert.deepEqual(q.parse('=1&=2',{allowEmptyKeys:true}),{'':['1','2']});console.log('checks passed')})().catch(e=>{console.error(e);process.exitCode=1});
