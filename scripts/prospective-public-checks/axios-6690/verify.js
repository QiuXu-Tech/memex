const assert = require('node:assert/strict');
const { pathToFileURL } = require('node:url');
const path = require('node:path');
(async () => {
  const root = process.argv[2];
  const utils = (await import(pathToFileURL(path.join(root, 'lib/utils.js')))).default;
  const previous = Object.getOwnPropertyDescriptor(Error.prototype, 'toJSON');
  try {
    Object.defineProperty(Error.prototype, 'toJSON', { configurable: true, writable: false, value() { return 'parent'; } });
    function Child() {}
    const childToJSON = () => 'child';
    utils.inherits(Child, Error, { toJSON: childToJSON });
    assert.equal(new Child().toJSON(), 'child');
    assert.equal(Error.prototype.toJSON(), 'parent');
    assert.equal(Child.prototype.constructor, Child);
    console.log('read-only inherited toJSON compatibility passed');
  } finally {
    if (previous) Object.defineProperty(Error.prototype, 'toJSON', previous);
    else delete Error.prototype.toJSON;
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
