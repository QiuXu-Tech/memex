'use strict';
const assert = require('node:assert/strict');
(async () => {
  const { Chalk } = await import('/work/source/index.js');
  const c = new Chalk({ level: 1 });
  for (let code = 232; code <= 255; code++) {
    const fg = code < 244 ? 30 : code < 251 ? 37 : 97;
    const bg = code < 244 ? 40 : code < 251 ? 47 : 107;
    assert.equal(c.ansi256(code)('x'), `\u001b[${fg}mx\u001b[39m`);
    assert.equal(c.bgAnsi256(code)('x'), `\u001b[${bg}mx\u001b[49m`);
  }
  assert.equal(c.ansi256(231)('x'), '\u001b[97mx\u001b[39m');
  assert.equal(c.rgb(248, 248, 248)('x'), '\u001b[97mx\u001b[39m');
  assert.equal(c.hex('#f8f8f8')('x'), '\u001b[97mx\u001b[39m');
  assert.equal(new Chalk({ level: 2 }).ansi256(255)('x'), '\u001b[38;5;255mx\u001b[39m');
  assert.equal(new Chalk({ level: 3 }).rgb(248, 248, 248)('x'), '\u001b[38;2;248;248;248mx\u001b[39m');
  console.log('issue #690 fixed checks passed');
})().catch(error => { console.error(error); process.exitCode = 1; });
