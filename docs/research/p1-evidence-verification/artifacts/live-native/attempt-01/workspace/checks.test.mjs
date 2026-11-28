import test from 'node:test';
import assert from 'node:assert/strict';
import { sum } from './sum.mjs';
test('sum', () => assert.equal(sum(20, 22), 42));
