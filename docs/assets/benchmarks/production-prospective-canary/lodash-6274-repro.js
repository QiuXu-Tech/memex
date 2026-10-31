'use strict';
const _ = require(process.argv[2] + '/lodash.js');
_.truncate('a,b' + 'X'.repeat(200), { length: 30, separator: /(?<=,)\s*/ });
console.log('completed');
