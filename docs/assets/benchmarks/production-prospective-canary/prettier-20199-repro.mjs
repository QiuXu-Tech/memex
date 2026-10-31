import assert from 'node:assert/strict';import {pathToFileURL} from 'node:url';
const prettier=await import(pathToFileURL(process.argv[2]+'/src/index.js'));
const input='$\\alpha^*$ and $\\beta^*$\n\n**$\\hat{x}_i$ and $\\hat{y}_j$**\n';
assert.equal(await prettier.format(input,{parser:'markdown'}),input);
