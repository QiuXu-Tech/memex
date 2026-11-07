// Fake DSH + real Store diagnostics. No network or real model calls.
import fs from 'node:fs'
import path from 'node:path'
import os from 'node:os'
import {pathToFileURL} from 'node:url'
import {spawnSync} from 'node:child_process'
if(!process.argv[2]||!process.argv[3])throw new Error('Usage: node --import REPO/test/register.mjs reproduce-integration.mjs REPO OUTPUT_JSON')
const repo=path.resolve(process.argv[2]),out=path.resolve(process.argv[3]),base=fs.mkdtempSync(path.join(os.tmpdir(),'memex-integration-probes-'))
const load=p=>import(pathToFileURL(path.join(repo,p)).href)
const {createFakeContext}=await load('test/fake-ctx.mjs')
const {default:LocalMemoryStore}=await load('packages/memex-local/index.js')
const {registerCheckpointPolicy}=await load('packages/memex-checkpoint/lib/checkpoint.js')
const {apply:compress}=await load('packages/memex-compress/index.js')
const {apply:api}=await load('packages/memex-api/index.js')
const {LocalStoreCore}=await load('packages/memex-core/lib/store.js')
const {memoryWorkspaceKey}=await load('packages/memex-core/index.js')
const results=[]
async function probe(name,fn){try{results.push({name,observation:await fn()})}catch(e){results.push({name,probeError:e.message,stack:e.stack?.split('\n').slice(0,4)})}}
await probe('async_refinement_overwrites_new_status',async()=>{
 let release,entered;const gate=new Promise(r=>release=r),started=new Promise(r=>entered=r)
 const ctx=createFakeContext({llm:{async *stream(){entered();await gate;yield {type:'text-delta',index:0,text:JSON.stringify({title:'enriched title'})}}}})
 const memory=new LocalMemoryStore(ctx,{root:path.join(base,'refine')});ctx.memory=memory
 const session={id:'audit',header:{cwd:base},requestHeader:()=>({config:{provider:'synthetic',model:'synthetic'}})}
 await memory.enableLevel(session.id,'l3');const policy=registerCheckpointPolicy(ctx,memory,{cardModel:'auto'})
 await ctx.emit('session/event',session,{seq:1,type:'user/message',data:{role:'user',content:[{type:'text',text:'synthetic source'}]}})
 await ctx.emit('session/event',session,{seq:2,type:'compaction/summary',data:{compactionId:'audit',shadowedSeqs:[1],summary:[{type:'text',text:'synthetic summary'}],shadowedTokenCount:10}})
 await started;const row=memory.core.list({workspaceKey:memoryWorkspaceKey(base),limit:10})[0]
 await memory.setStatus(row.id,'superseded');const before=(await memory.get(row.id)).status
 release();await policy.drain();const after=(await memory.get(row.id)).status;policy.dispose();await ctx.dispose()
 return {statusDuringPendingRefinement:before,statusAfterRefinement:after}
})
await probe('failed_digest_attempt_accounting',async()=>{
 let actualAttempts=0;const ctx=createFakeContext({llm:{async *stream(){actualAttempts++;throw new Error('SYNTHETIC_PROVIDER_FAILURE')}}})
 const memory=new LocalMemoryStore(ctx,{root:path.join(base,'digest'),capacityTokens:100});ctx.memory=memory
 const session={id:'audit',header:{cwd:base},requestHeader:()=>({config:{provider:'synthetic',model:'synthetic'}})}
 await memory.enableLevel(session.id,'l3');await memory.write({id:'audit-digest-input',workspaceKey:memoryWorkspaceKey(base),sessionId:'audit',scope:'workspace',kind:'fact',title:'input',body:'word '.repeat(500),createdAt:1,updatedAt:1})
 compress(ctx,{minAgeMs:0,minDigestTokens:1,maxBatches:1});await ctx.tool('memory_compress').execute({level:'l3',strategy:'digest',targetRatio:0.6},{agent:{session}})
 const stats=await memory.compressionStats('audit',3);await ctx.dispose();return {actualAttempts,recordedCalls:stats.last?.llmCalls}
})
await probe('http_unicode_pagination',async()=>{
 const ctx=createFakeContext();const memory=new LocalMemoryStore(ctx,{root:path.join(base,'http')});ctx.memory=memory
 const session={id:'audit',header:{cwd:base}};await memory.enableLevel('audit','l3')
 const row=await memory.write({id:'audit-unicode',workspaceKey:memoryWorkspaceKey(base),scope:'workspace',kind:'fact',title:'unicode',body:'汉'.repeat(100000)})
 const routes=[];ctx.sessions={list:()=>[session]};ctx.connection={fetch:{register:r=>{routes.push(r);return()=>{}}}};api(ctx)
 const route=routes.find(x=>x.path==='/api/memory.record');const resp=await route.fetch(new Request('http://example.invalid/api/memory.record?sessionId=audit&id='+row.id));const data=await resp.json()
 await ctx.dispose();return {returnedChars:data.body.length,declaredBodyLimit:data.bodyLimit,totalChars:data.bodyTotalChars,truncated:data.truncated,containsReplacementCharacter:data.body.includes('\uFFFD'),hasNextOffset:'nextOffset' in data||'nextCharOffset' in data}
})
await probe('fts_migration_interruption',()=>{
 const root=path.join(base,'migration'),s=new LocalStoreCore({root});s.write({id:'audit-oldindex',workspaceKey:'w',scope:'workspace',kind:'fact',title:'MigrationTitle',body:'body'})
 s.database().exec('DROP TABLE records_fts; CREATE VIRTUAL TABLE records_fts USING fts5(title,summary,use_when,tags,body)');s.close()
 const hook=path.join(base,'migration-stop.mjs');fs.writeFileSync(hook,"import{DatabaseSync}from'node:sqlite';const original=DatabaseSync.prototype.exec;DatabaseSync.prototype.exec=function(sql){const result=original.call(this,sql);if(sql.startsWith('CREATE VIRTUAL TABLE records_fts USING fts5(title, summary, use_when, tags, abstract'))process.exit(91);return result};")
 const code=`import{LocalStoreCore}from ${JSON.stringify(pathToFileURL(path.join(repo,'packages/memex-core/lib/store.js')).href)};new LocalStoreCore({root:${JSON.stringify(root)}}).ensure()`
 const r=spawnSync(process.execPath,['--import',hook,'--input-type=module','-e',code],{encoding:'utf8',timeout:10000})
 const reopened=new LocalStoreCore({root});reopened.ensure();const cards=reopened.database().prepare('SELECT count(*) n FROM records').get().n,fts=reopened.database().prepare('SELECT count(*) n FROM records_fts').get().n;reopened.close();return {faultExit:r.status,records:cards,ftsRowsAfterRecovery:fts}
})
fs.writeFileSync(out,JSON.stringify({syntheticOnly:true,host:'fake DSH with real store',results},null,2)+'\n');console.log(JSON.stringify(results,null,2));fs.rmSync(base,{recursive:true,force:true})

if(results.some(x=>x.probeError))process.exitCode=1
