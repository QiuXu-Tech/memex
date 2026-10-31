'use strict';
// Fix a catch that only rethrows when a finally block remains; keep other cases intact.
const assert=require('node:assert/strict');const {Linter}=require(process.argv[2]);
const opts={languageOptions:{ecmaVersion:'latest'},rules:{'no-useless-catch':'error'}};
const f=new Linter().verifyAndFix('try { work(); } catch (e) { throw e; } finally { clean(); }',opts);
assert.equal(f.fixed,true);assert.doesNotMatch(f.output,/\bcatch\b/);assert.match(f.output,/work\(\)/);assert.match(f.output,/finally/);assert.match(f.output,/clean\(\)/);
const vm=require('node:vm');const scopeCase='const result=[]; let n=1; try { let n=2; result.push(n); } catch(e) { throw e; } result.push(n); globalThis.answer=result;';const noFinally=new Linter().verifyAndFix(scopeCase,opts);const before={},after={};vm.runInNewContext(scopeCase,before);vm.runInNewContext(noFinally.output,after);assert.deepStrictEqual(Array.from(after.answer),Array.from(before.answer));
const comment='try { work(); } catch (e) { /* keep this reason */ throw e; } finally { clean(); }';const c=new Linter().verifyAndFix(comment,opts);if(c.fixed)assert.match(c.output,/keep this reason/);
const effect='try { work(); } catch (e) { log(e); throw e; } finally { clean(); }';const side=new Linter().verifyAndFix(effect,opts);assert.equal(side.output,effect);assert.equal(side.fixed,false);
console.log('useless catch acceptance and safety controls passed');
