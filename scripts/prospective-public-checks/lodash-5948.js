'use strict';const assert=require('node:assert/strict');const _=require(process.argv[2]+'/lodash.js');
const o={a:{'0':{c:'ABC',d:'DEF'}}};assert.deepEqual(_.pick(o,[['a','0','c']]),{a:{'0':{c:'ABC'}}});console.log('numeric key containers preserved');
