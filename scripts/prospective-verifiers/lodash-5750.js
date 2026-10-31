'use strict';
const assert=require('node:assert/strict');const _=require(process.argv[2]+'/lodash.js');
const cases=[['IDs','ids'],['Product XMLs','productXmls'],['Foo Bar','fooBar'],['foo-bar','fooBar'],['XMLHttpRequest','xmlHttpRequest']];
const failures=[];for(const [input,expected] of cases){const actual=_.camelCase(input);if(actual!==expected)failures.push({input,expected,actual});}assert.deepStrictEqual(failures,[]);console.log('acceptance and regression checks passed');
