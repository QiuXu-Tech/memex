'use strict';
// Suggest both strict and null-or-undefined comparisons only where safe.
const assert=require('node:assert/strict');const {Linter}=require(process.argv[2]);const opts={languageOptions:{ecmaVersion:'latest'},rules:{'no-eq-null':'error'}};
function suggestions(code){const m=new Linter().verify(code,opts).filter(x=>x.ruleId==='no-eq-null');assert.equal(m.length,1);assert.equal(m[0].fix,undefined);return (m[0].suggestions||[]).map(s=>code.slice(0,s.fix.range[0])+s.fix.text+code.slice(s.fix.range[1]));}
let a=suggestions('function f(value){return value == null;}');assert.ok(a.some(s=>s.includes('value === null')));assert.ok(a.some(s=>s.includes('value === undefined')&&s.includes('||')));
a=suggestions('function f(value){return value != null;}');assert.ok(a.some(s=>s.includes('value !== null')));assert.ok(a.some(s=>s.includes('value !== undefined')&&s.includes('&&')));
a=suggestions('function f(){return getValue() == null;}');assert.ok(a.some(s=>s.includes('getValue() === null')));assert.ok(a.every(s=>!s.includes('undefined')));
a=suggestions('function f(undefined,value){return value == null;}');assert.ok(a.some(s=>s.includes('value === null')));assert.ok(a.every(s=>!s.includes('undefined)')&&!s.includes('=== undefined')));
console.log('suggestion and safety controls passed');
a=suggestions('function f(obj){return obj.x == null;}');assert.ok(a.some(s=>s.includes('obj.x === null')));assert.ok(a.every(s=>!s.includes('undefined')));
a=suggestions('function f(i){return i++ == null;}');assert.ok(a.some(s=>s.includes('i++ === null')));assert.ok(a.every(s=>!s.includes('undefined')));
a=suggestions('function f(value){return null == value;}');assert.ok(a.some(s=>s.includes('null === value')));assert.ok(a.some(s=>s.includes('value === undefined')&&s.includes('||')));
console.log('extended suggestion safety controls passed');
