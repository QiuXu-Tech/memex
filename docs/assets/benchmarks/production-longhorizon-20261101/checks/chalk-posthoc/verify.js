'use strict';
const assert = require('node:assert/strict');
(async () => {
  const { Chalk } = await import('/work/source/index.js');
  const c = new Chalk({ level: 1 });
  const actual = {
    ansi255: c.ansi256(255)('hello'),
    underline196: c.underlineAnsi256(196)('hello'),
    underline255: c.underlineAnsi256(255)('hello'),
  };
  console.log(JSON.stringify(actual));
  // Pinned upstream test/chalk.js:145 asserts ANSI-16 code 37 for this input.
  assert.equal(actual.ansi255, '\u001b[37mhello\u001b[39m');
})().catch(error => { console.error(error); process.exitCode = 1; });
