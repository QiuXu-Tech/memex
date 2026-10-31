'use strict';
const assert=require('node:assert/strict');const pino=require(process.argv[2]+'/browser');
const calls=[];const root=pino({level:'info',browser:{write:(...args)=>calls.push(args)}});const child=root.child({name:'child',level:'debug'});child.debug('Child Debug');assert.ok(calls.length>0,'child debug should be logged');
