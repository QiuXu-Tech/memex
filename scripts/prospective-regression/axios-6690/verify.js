const assert = require('node:assert/strict');
const { pathToFileURL } = require('node:url');
const path = require('node:path');
(async () => {
  const utils = (await import(pathToFileURL(path.join(process.argv[2], 'lib/utils.js')))).default;
  let assigned;
  function Parent() {}
  Object.defineProperty(Parent.prototype, 'observed', { configurable: true, set(value) { assigned = value; } });
  function Child() {}
  utils.inherits(Child, Parent, { observed: 42, plain: 'ok' });
  assert.equal(assigned, 42, 'preserve inherited setter behavior');
  assert.equal(Object.hasOwn(Child.prototype, 'observed'), false);
  assert.equal(Child.prototype.plain, 'ok');
  assert.equal(Child.prototype.constructor, Child);
  console.log('inherited setter and ordinary properties passed');
})().catch(error => { console.error(error); process.exitCode = 1; });
