'use strict';const assert=require('node:assert/strict');const _=require(process.argv[2]+'/lodash.js');
assert.deepEqual(_.pick({a:{b:1,c:2}},['a.b']),{a:{b:1}});assert.deepEqual(_.pick({x:1,y:2},['x']),{x:1});console.log('ordinary pick controls passed');
