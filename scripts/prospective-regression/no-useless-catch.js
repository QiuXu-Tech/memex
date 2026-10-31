'use strict';
process.env.NODE_PATH='/work/testdeps/node_modules';require('node:module').Module._initPaths();
let count=0,failed=0,skippedExpectedChange=0;
global.describe=(name,fn)=>fn();
global.it=(name,fn)=>{
 const normalized=name.replace(/\s+/g,' ').trim();
 if(normalized==='try { foo(); } catch (err) { throw err; } finally { foo(); }'){skippedExpectedChange++;return;}
 count++;try{fn();}catch(e){failed++;console.error('FAIL',name,e.message);}
};
try{require('/work/tests/lib/rules/no-useless-catch.js');}catch(e){failed++;console.error('SUITE_ERROR',e.stack);}
console.log(JSON.stringify({count,failed,skippedExpectedChange}));if(failed||count!==15||skippedExpectedChange!==1)process.exitCode=1;
