'use strict';const assert=require('node:assert/strict');const _=require(process.argv[2]+'/lodash.js');
assert.deepEqual(_.cloneDeep([1,{x:2}]),[1,{x:2}]);assert.deepEqual(_.cloneDeep([]),[]);console.log('dense clone controls passed');
