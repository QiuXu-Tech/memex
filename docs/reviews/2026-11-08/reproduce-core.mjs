// Audit diagnostics, not passing regression assertions. Synthetic temporary data only.
// A zero exit status means the probes ran; inspect their observations for failures.
import fs from 'node:fs'
import path from 'node:path'
import os from 'node:os'
import { pathToFileURL } from 'node:url'
import { syncBuiltinESMExports } from 'node:module'
import { spawnSync } from 'node:child_process'
if (!process.argv[2] || !process.argv[3]) throw new Error('Usage: node reproduce-core.mjs REPO OUTPUT_JSON')
const repo=path.resolve(process.argv[2]), out=path.resolve(process.argv[3])
const base=fs.mkdtempSync(path.join(os.tmpdir(),'memex-audit-probes-'))
const load=p=>import(pathToFileURL(path.join(repo,p)).href)
const {LocalStoreCore}=await load('packages/memex-core/lib/store.js')
const {materializeContext}=await load('packages/memex-core/lib/context-materializer.js')
const {materializeStoreContext}=await load('packages/memex-core/lib/context-pager.js')
const {canonicalEventsFromDsh}=await load('packages/memex-core/lib/context-events.js')
const {AgentMemory}=await load('packages/memex-core/lib/engine.js')
const {PagedKvContextHost}=await load('packages/memex-core/lib/context-kv-host.js')
const {materializeWithHost}=await load('packages/memex-core/lib/context-kv.js')
const results=[]
const store=name=>new LocalStoreCore({root:path.join(base,name),capacityTokens:1000000})
const record=(id,extra={})=>({id,workspaceKey:'audit-workspace',scope:'workspace',kind:'fact',title:'Ordinary words',body:'ordinary words with no identifiers',...extra})
async function probe(name,fn){try{results.push({name,observation:await fn()})}catch(e){results.push({name,probeError:e.message,stack:e.stack?.split('\n').slice(0,3)})}}
await probe('pinned_hard_budget',()=>{
 const r=materializeContext({pages:[{id:'pinned',body:'word '.repeat(1200)}],budgetTokens:100,pinnedIds:['pinned'],enforceTotalBudget:true})
 return {requested:100,returned:r.tokens,status:r.budgetStatus,overBudget:r.overBudgetBy}
})
await probe('canonical_block_order',()=>{
 const s=store('order'),id='audit-order';s.write(record(id))
 const events=canonicalEventsFromDsh([{seq:1,type:'user/message',message:{role:'user',content:Array.from({length:12},(_,i)=>({type:'text',text:'block-'+i}))}}],{recordId:id,sessionId:'audit'})
 s.appendContextEvents({recordId:id,events});const order=s.listContextEvents(id).map(x=>x.content);s.close();return {expected:Array.from({length:12},(_,i)=>'block-'+i),actual:order}
})
await probe('forced_nonresident_record',()=>{
 const s=store('forced');s.write(record('audit-old',{createdAt:1}))
 for(let i=0;i<45;i++)s.write(record('audit-new-'+i,{createdAt:100+i}))
 const r=materializeStoreContext({store:s,workspaceKey:'audit-workspace',scopes:['workspace'],sessionId:'audit',alwaysIncludeIds:['audit-old'],budgetTokens:50000});s.close()
 return {forcedRecordIncluded:r.includedIds.includes('audit-old'),candidatePages:r.pages}
})
await probe('forced_canonical_record_mapping',()=>{
 const s=store('forced-canonical');s.write(record('audit-canonical'));s.appendContextEvents({recordId:'audit-canonical',events:[{id:'block',sequence:1,content:'canonical body'}]})
 const r=materializeStoreContext({store:s,workspaceKey:'audit-workspace',scopes:['workspace'],sessionId:'audit',alwaysIncludeIds:['audit-canonical'],budgetTokens:1000});s.close()
 return {included:r.includedIds,forced:r.forcedIds}
})
await probe('mixed_ordering_units',()=>{
 const r=materializeContext({pages:[{id:'older-note',sequence:1000,createdAt:1000,body:'old note'},{id:'newer-event',sequence:1,createdAt:2000,body:'new event'}],budgetTokens:1000})
 return {expected:['older-note','newer-event'],actual:r.order}
})
await probe('kv_reference_contract',()=>{
 const host=new PagedKvContextHost();materializeWithHost({text:'data'},host,{prefixKey:'audit',spans:[{id:'s',text:'ACTUAL-CONTENT'}]})
 return {expected:'ACTUAL-CONTENT',actual:host.blocks.get('audit:block:0')?.text}
})
await probe('grep_open_coordinates',()=>{
 const e=new AgentMemory({root:path.join(base,'grep'),cwd:base,sessionId:'audit',levels:['l3']});const r=e.write({kind:'fact',title:'lines',body:'first\nTARGET_MARKER\nlast'})
 const hit=e.grep({pattern:'TARGET_MARKER',id:r.id})[0];const opened=e.open({id:r.id,offset:hit.line,limit:1});e.close();return {grepLine:hit.line,expectedBodyLine:2,openedBody:opened.body}
})
await probe('concurrent_sticky_enable',()=>{
 const a=store('sticky'),b=new LocalStoreCore({root:a.root,capacityTokens:1000000});a.ensure();b.ensure()
 const original=a.getLevels.bind(a);let interleave=true;a.getLevels=id=>{const result=original(id);if(interleave){interleave=false;b.enableLevel(id,'l3')}return result}
 a.enableLevel('audit','l2');const levels=b.getLevels('audit');a.close();b.close();return {expected:{l2:true,l3:true},actual:levels}
})
await probe('zero_term_reindex_on_reopen',()=>{
 let s=store('reindex');const r=s.write(record('audit-natural'));s.close()
 const original=fs.readFileSync;let reads=0;fs.readFileSync=function(p,...args){if(String(p)===r.path)reads++;return original(p,...args)};syncBuiltinESMExports()
 const counts=[];try{for(let i=0;i<2;i++){reads=0;s=new LocalStoreCore({root:path.join(base,'reindex'),capacityTokens:1000000});s.ensure();counts.push(reads);s.close()}}finally{fs.readFileSync=original;syncBuiltinESMExports()}
 return {bodyReadsOnSuccessiveOpen:counts}
})
await probe('canonical_default_id_collision',()=>{
 const s=store('event-collision');s.write(record('audit-a'));s.write(record('audit-b'))
 s.appendContextEvents({recordId:'audit-a',events:[{sequence:1,content:'first'}]});s.appendContextEvents({recordId:'audit-b',events:[{sequence:1,content:'second'}]})
 const counts=[s.listContextEvents('audit-a').length,s.listContextEvents('audit-b').length];s.close();return {expected:[1,1],actual:counts}
})
await probe('backup_manifest_validation',()=>{
 const dir=path.join(base,'empty-backup');fs.mkdirSync(dir);fs.writeFileSync(path.join(dir,'manifest.json'),JSON.stringify({files:[],createdAt:'synthetic'}))
 const r=spawnSync(process.execPath,[path.join(repo,'scripts/memory-backup.mjs'),'verify','--dir',dir],{encoding:'utf8',timeout:10000});return {exit:r.status,output:r.stdout.trim()}
})
await probe('restore_failure_preserves_existing_target',()=>{
 const dir=path.join(base,'backup-out'),target=path.join(base,'restore-target')
 const s=store('restore-source');s.write(record('audit-restore'));s.close()
 const backup=spawnSync(process.execPath,[path.join(repo,'scripts/memory-backup.mjs'),'backup','--root',s.root,'--out',dir],{encoding:'utf8',timeout:10000})
 if(backup.status!==0)throw new Error('Synthetic backup preparation failed: '+backup.stderr)
 fs.mkdirSync(target);fs.writeFileSync(path.join(target,'keep.txt'),'previous-state')
 const injected=path.join(base,'copy-failure.mjs');fs.writeFileSync(injected,"import fs from 'node:fs';import {syncBuiltinESMExports} from 'node:module';fs.cpSync=()=>{throw new Error('AUDIT_INJECTED_COPY_FAILURE')};syncBuiltinESMExports();")
 const r=spawnSync(process.execPath,['--import',injected,path.join(repo,'scripts/memory-backup.mjs'),'restore','--dir',dir,'--to',target,'--force'],{encoding:'utf8',timeout:10000})
 return {exit:r.status,injectedErrorObserved:r.stderr.includes('AUDIT_INJECTED_COPY_FAILURE'),oldStateSurvives:fs.existsSync(path.join(target,'keep.txt'))}
})

await probe('clean_adapter_startup',()=>{
 return ['packages/memex-mcp/bin/server.mjs','packages/memex-claude/bin/cli.mjs','packages/memex-codex/bin/cli.mjs'].map(p=>{
  const child=spawnSync(process.execPath,[path.join(repo,p),'--help'],{input:'',encoding:'utf8',timeout:5000,env:{PATH:process.env.PATH,HOME:base,TMPDIR:base,LANG:'C'}})
  return {entry:p,exit:child.status,missingCore:child.stderr?.includes("Cannot find package '@qiuxu/memex-core'")??false}
 })
})
await probe('bm25_score_direction',async()=>{
 const {DatabaseSync}=await import('node:sqlite');const db=new DatabaseSync(':memory:')
 db.exec('CREATE VIRTUAL TABLE audit USING fts5(t)')
 for(const text of ['alpha alpha alpha alpha','alpha beta gamma delta'])db.prepare('INSERT INTO audit VALUES (?)').run(text)
 const values=db.prepare('SELECT bm25(audit) rank FROM audit WHERE audit MATCH ?').all('alpha').map(x=>({raw:x.rank,currentFormula:1/(1+Math.max(0,x.rank))}))
 db.close();return values
})

fs.writeFileSync(out,JSON.stringify({baseline:'5bf65f6ede777c00cf35ec2ba1e4b14dbc17f182',node:process.version,syntheticOnly:true,results},null,2)+'\n')
console.log(JSON.stringify(results,null,2))
fs.rmSync(base,{recursive:true,force:true})

if(results.some(x=>x.probeError))process.exitCode=1
