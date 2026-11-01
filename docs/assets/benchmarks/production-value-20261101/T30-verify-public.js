const assert=require('node:assert/strict')
const {register}=require('node:module')
register('file:///checks/loader.mjs')
;(async()=>{
 const {Window}=await import('file:///work/packages/happy-dom/src/index.ts')
 let failures=0
 const test=(label,fn)=>{try{fn();console.log('PASS '+label)}catch(e){failures++;console.log('FAIL '+label+': '+e.message)}}
 test('replace document root with SVG',()=>{
  const doc=new Window().document;const old=doc.documentElement;const svg=doc.createElementNS('http://www.w3.org/2000/svg','svg')
  old.replaceWith(svg);assert.equal(doc.documentElement,svg);assert.equal(svg.parentNode,doc);assert.equal(old.parentNode,null)
 })
 test('replace ordinary child without losing sibling',()=>{
  const doc=new Window().document;const parent=doc.createElement('div');const old=doc.createElement('i');const next=doc.createElement('b');parent.append(old,next)
  const replacement=doc.createElement('span');old.replaceWith(replacement);assert.equal(parent.children.length,2);assert.equal(parent.children[0],replacement);assert.equal(parent.children[1],next)
 })
 test('reject a second document root',()=>{
  const doc=new Window().document;const old=doc.documentElement;assert.throws(()=>doc.appendChild(doc.createElement('other')));assert.equal(doc.documentElement,old)
 })
 if(failures) process.exitCode=1
})().catch(e=>{console.error(e.stack);process.exitCode=2})
