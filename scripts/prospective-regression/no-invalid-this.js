"use strict";
process.env.NODE_PATH = "/work/testdeps/node_modules";
require("node:module").Module._initPaths();
let count=0,failed=0;
global.describe=(name,fn)=>fn();
global.it=(name,fn)=>{count++;try{fn();}catch(e){failed++;console.error("FAIL",name,e.message)}};
try { require("/work/tests/lib/rules/no-invalid-this.js"); } catch(e) { failed++;console.error("SUITE_ERROR", e.stack); }
console.log(JSON.stringify({count,failed}));
if (failed || !count) process.exitCode=1;
