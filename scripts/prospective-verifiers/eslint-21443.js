'use strict';
// Project discussion specifies direct JSON callbacks, not arrows or other functions.
const assert=require('node:assert/strict');
const {Linter}=require(process.argv[2]);
const config={languageOptions:{ecmaVersion:'latest',sourceType:'module'},rules:{'no-invalid-this':'error'}};
const cases=[
 ['direct parse','JSON.parse(json,function(k,v){return this[k]});',0],
 ['direct stringify','JSON.stringify(data,function(k,v){return this[k]});',0],
 ['arrow within replacer','JSON.parse(json,function(k,v){return () => this;});',0],
 ['arrow callback','JSON.parse(json,(k,v)=>this);',1],
 ['nested function','JSON.parse(json,function(k,v){function inner(){return this} return inner();});',1],
 ['named callback','function reviver(k,v){return this;} JSON.parse(json,reviver);',1],
 ['unrelated callback','other(function(){return this;});',1],
 ['shadowed JSON','function f(JSON){JSON.parse(json,function(k,v){return this[k]});}',1],
];
let failures=[];
for(const [name,code,expected] of cases){
 const messages=new Linter().verify(code,config);
 const errors=messages.filter(m=>m.ruleId==='no-invalid-this').length;
 const other=messages.filter(m=>m.ruleId!=='no-invalid-this');
 if(errors!==expected || other.length) failures.push({name,expected,actual:errors,other});
}
assert.deepStrictEqual(failures,[]);
console.log('acceptance and regression checks passed');
