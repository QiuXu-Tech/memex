'use strict';
// Unsafe typeof comparisons must be reported but not autofixed; safe ones remain fixable.
const assert=require('node:assert/strict');const {Linter}=require(process.argv[2]);
const config={languageOptions:{ecmaVersion:'latest'},rules:{eqeqeq:'error'}};
const cases=[
 ['unsafe object','const b={toString:()=>"number"};let a=1;typeof a == b;',false],
 ['unsafe identifier','typeof x != value;',false],
 ['string right','typeof x == "string";',true],
 ['string left','"string" == typeof x;',true],
 ['both typeof','typeof x == typeof y;',true],
 ['ordinary comparison','x == y;',false]
];
const failures=[];
for(const [name,code,expected] of cases){const result=new Linter().verifyAndFix(code,config);if(result.fixed!==expected)failures.push({name,expected,actual:result.fixed});if(!expected&&!result.messages.some(x=>x.ruleId==='eqeqeq'))failures.push({name,reason:'rule report missing'});if(name.startsWith('unsafe')&&!result.messages.some(x=>x.ruleId==='eqeqeq'&&(x.suggestions||[]).some(y=>y.messageId==='replaceOperator')))failures.push({name,reason:'replaceOperator suggestion missing'});}
assert.deepStrictEqual(failures,[]);console.log('acceptance and regression checks passed');
