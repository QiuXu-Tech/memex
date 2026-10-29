/**
 * Registers the offline stub loader before the test runner starts.
 *
 * Run the suite with:
 *
 *   node --import ./test/register.mjs ./test/run.mjs
 *
 * (`register()` lives in `node:module`; it installs the resolve hook in
 * `./loader.mjs` for this process.)
 */
import { register } from 'node:module'

register('./loader.mjs', import.meta.url)
