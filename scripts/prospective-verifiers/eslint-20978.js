'use strict';
// The issue distinguishes unused inner names from names used recursively.
const assert=require('node:assert/strict');const {Linter}=require(process.argv[2]);
const config={languageOptions:{ecmaVersion:'latest',sourceType:'module'},rules:{'no-shadow':'error'}};
const cases=[
 ['unreferenced wrapped function','const TabList = React.forwardRef(function TabList(props, ref) {});',0],
 ['self-referenced wrapper','const a = wrap(function a(){a();});',1],
 ['recursive wrapper','const fib = memo(function fib(n){return n <= 1 ? 1 : fib(n-1);});',1],
 ['ordinary shadow','const value=1; function f(value){return value;}',1]
];
const failures=[];
for(const [name,code,expected] of cases){const messages=new Linter().verify(code,config);const actual=messages.filter(m=>m.ruleId==='no-shadow').length;const other=messages.filter(m=>m.ruleId!=='no-shadow');if(actual!==expected||other.length)failures.push({name,expected,actual,other});}
assert.deepStrictEqual(failures,[]);console.log('acceptance and regression checks passed');
