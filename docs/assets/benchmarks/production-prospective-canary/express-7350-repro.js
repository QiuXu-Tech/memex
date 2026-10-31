'use strict';
const assert = require('node:assert/strict');
const express=require(process.argv[2]);const app=express();app.set('view engine','ejs');
let called=false;
assert.doesNotThrow(()=>app.render('index.',()=>{called=true;}));
assert.ok(called);
