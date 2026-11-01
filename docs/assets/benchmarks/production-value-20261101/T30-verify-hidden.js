const assert=require('node:assert/strict')
const {register}=require('node:module')
register('file:///checks/loader.mjs')
;(async()=>{
 const {Window}=await import('file:///work/packages/happy-dom/src/index.ts')
 let failures=0
 const test=(label,fn)=>{try{fn();console.log('PASS '+label)}catch(e){failures++;console.log('FAIL '+label+': '+e.message)}}
 test('replace root with imported HTML',()=>{
  const win=new Window();const doc=win.document;const parsed=new win.DOMParser().parseFromString('<html><body>replaced</body></html>','text/html')
  doc.documentElement.replaceWith(doc.importNode(parsed.documentElement,true));assert.equal(doc.body.textContent,'replaced');assert.equal(doc.documentElement.parentNode,doc)
 })
 test('replaceChild document root directly',()=>{
  const doc=new Window().document;const old=doc.documentElement;const replacement=doc.createElementNS('http://www.w3.org/2000/svg','svg')
  assert.equal(doc.replaceChild(replacement,old),old);assert.equal(doc.documentElement,replacement);assert.equal(old.parentNode,null)
 })
 test('replace an ordinary element with multiple nodes',()=>{
  const doc=new Window().document;const parent=doc.createElement('div');const old=doc.createElement('i');parent.append(old);const a=doc.createElement('a');const b=doc.createElement('b')
  old.replaceWith(a,'text',b);assert.equal(parent.childNodes.length,3);assert.equal(parent.childNodes[0],a);assert.equal(parent.childNodes[1].textContent,'text');assert.equal(parent.childNodes[2],b)
 })
 test('replaceWith no arguments removes ordinary child',()=>{
  const doc=new Window().document;const parent=doc.createElement('div');const old=doc.createElement('i');parent.append(old);old.replaceWith();assert.equal(parent.childNodes.length,0);assert.equal(old.parentNode,null)
 })
 test('reject invalid two-root replacement without losing the old root',()=>{
  const doc=new Window().document;const old=doc.documentElement;const a=doc.createElement('a');const b=doc.createElement('b')
  assert.throws(()=>old.replaceWith(a,b));assert.equal(doc.documentElement,old);assert.equal(old.parentNode,doc)
 })
 if(failures) process.exitCode=1
})().catch(e=>{console.error(e.stack);process.exitCode=2})
