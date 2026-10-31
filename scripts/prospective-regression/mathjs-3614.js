'use strict';const assert=require('node:assert/strict'),{pathToFileURL}=require('node:url');

(async()=>{const m=(await import(pathToFileURL(process.argv[2]+'/src/defaultInstance.js').href)).default;assert.equal(m.unit(1,'MW').to('kW').format(),'1000 kW');const s=m.unit(m.complex(1,2),'V').format();assert(s.startsWith('(')&&s.includes(') V'));console.log('real and genuinely complex unit formatting controls passed');})().catch(e=>{console.error(e);process.exitCode=1});
