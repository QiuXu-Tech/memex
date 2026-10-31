'use strict';
const assert = require('node:assert/strict');
const path = require('node:path');
const root = process.argv[2];
const lodash = require(path.join(root, 'lodash.js'));
const convert = require(path.join(root, 'fp/_baseConvert.js'));
const fp = convert(lodash, lodash.runInContext());
for (const selector of ['foo.0.bar', 'foo[0].bar']) {
  const input = { foo: [{ bar: 1, keep: 2 }], untouched: 3 };
  const output = fp.omit([selector], input);
  assert.deepStrictEqual(input, { foo: [{ bar: 1, keep: 2 }], untouched: 3 });
  assert.deepStrictEqual(output, { foo: [{ keep: 2 }], untouched: 3 });
}
{
 const input = {a:{b:1,c:2}, k:3};
 assert.deepStrictEqual(fp.omit(['a.b'], input), {a:{c:2}, k:3});
 assert.deepStrictEqual(input, {a:{b:1,c:2},k:3});
}
{
 const input = {arr:[1,2], x:3};
 assert.deepStrictEqual(fp.omit(['x'], input), {arr:[1,2]});
 assert.deepStrictEqual(input, {arr:[1,2],x:3});
}
console.log('PASS');
