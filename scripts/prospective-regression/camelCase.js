'use strict';
const assert=require('node:assert/strict');const _=require(process.argv[2]+'/lodash.js');
for(const [x,y] of [['Foo Bar','fooBar'],['foo-bar','fooBar'],['XMLHttpRequest','xmlHttpRequest'],['déjà Vu','dejaVu'],['abc 123 def','abc123Def']])assert.equal(_.camelCase(x),y);
console.log('five ordinary casing controls passed');
