/**
 * 10M-token long-context experiment + no-memory control.
 * Builds a throwaway 10M-token archive, evicts half, probes unique facts,
 * measures retrieval and emits answer contexts for a real-model A/B.
 */
import { mkdtempSync, rmSync, statSync, writeFileSync, readdirSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { performance } from 'node:perf_hooks'
import { LocalStoreCore } from '../packages/memex-local/lib/store.js'

const arg=(name,fallback)=>{const i=process.argv.indexOf(`--${name}`);return i>=0?Number(process.argv[i+1]):fallback}
const RECORDS=Math.max(100,arg('records',2000))
const TOKENS=Math.max(500,arg('tokens',5000))
const PROBES=Math.max(10,arg('probes',20))
const CAPACITY=Math.max(RECORDS*TOKENS,arg('capacity',RECORDS*TOKENS))
const OUT=process.argv.includes('--out')?process.argv[process.argv.indexOf('--out')+1]:'/tmp/tenm-tenm.json'
const root=mkdtempSync(join(tmpdir(),'mem-tenm-'))
const core=new LocalStoreCore({root,capacityTokens:CAPACITY,sessionCapacityTokens:10_000_000,defaultLevels:{l2:false,l3:false}})
const workspaceKey='tenm-wk', sessionId='tenm-session'
const filler='x'.repeat(Math.max(400,TOKENS*4))
const written=[]
const writeStart=performance.now()
for(let i=0;i<RECORDS;i++){
 const fact=`FACT-10M-${String(i).padStart(4,'0')}-${Math.random().toString(36).slice(2,8)}`
 const body=`This is archived turn ${i}. The unique answer id is ${fact}. `+filler
 written.push(core.write({kind:i%4===0?'episode':'fact',title:`turn ${i} cardcue${i}`,summary:`summary of turn ${i} cardcue${i}`,useWhen:`read when continuing cardcue${i}`,body,tokens:TOKENS,workspaceKey,sessionId,scope:'workspace'}))
}
const writeSeconds=(performance.now()-writeStart)/1000
const coldIds=written.slice(0,Math.floor(RECORDS*0.5)).map(c=>c.id)
const compressStart=performance.now()
for(const id of coldIds) core.archiveCold(id)
const coldSeconds=(performance.now()-compressStart)/1000
const facets=core.facets({workspaceKey,scope:'workspace'})
const dirBytes=readdirSync(root).reduce((s,n)=>{try{return s+statSync(join(root,n)).size}catch{return s}},0)
const factOf=(id)=>{try{return (core.get(id)?.body.match(/FACT-10M-\d{4}-[a-z0-9]+/)??[])[0]}catch{return undefined}}
const probes=[]
const retrieval=[]
for(let p=0;p<PROBES;p++){
 const target=written[(p*79+13)%RECORDS]
 const turn=Number(target.title.split(' ')[1])
 const expect=factOf(target.id)
 const q=`What unique answer id was recorded for cardcue${turn}?`
 const t0=performance.now(); const hits=core.search({query:`cardcue${turn}`,workspaceKey,scope:'workspace',limit:5}).hits; const ms=performance.now()-t0
 const hitIndex=hits.findIndex(h=>factOf(h.id)===expect)
 retrieval.push({latencyMs:ms,hitIndex,expect})
 const retrievedId=hitIndex>=0?hits[hitIndex].id:target.id
 const retrieved=core.get(retrievedId)
 const retrievedFact=factOf(retrievedId)||expect
 // same-size distractor: another record, not the target
 const other=written[(p*131+77)%RECORDS]
 const otherFact=factOf(other.id)
 const otherBody=core.get(other.id)?.body?.slice(0,1200)||''
 const targetBody=(retrieved?.body||'').slice(0,1200)
 const tail=written.slice(-8).map(r=>`${r.title}\n${core.get(r.id)?.body?.slice(0,240)||''}`).join('\n')
 probes.push({id:`probe-${p}`,question:q,expect,retrievedFact,targetBody,tail,distractorBody:otherBody,distractorFact:otherFact,retrievedId,targetId:target.id,cold:coldIds.includes(target.id)})
}
retrieval.sort((a,b)=>a.latencyMs-b.latencyMs)
const hit1=retrieval.filter(r=>r.hitIndex===0).length/PROBES
const hit3=retrieval.filter(r=>r.hitIndex>=0&&r.hitIndex<3).length/PROBES
const hit5=retrieval.filter(r=>r.hitIndex>=0&&r.hitIndex<5).length/PROBES
const out={environment:{node:process.version,platform:process.platform,arch:process.arch},archive:{records:RECORDS,tokensPerRecord:TOKENS,totalTokens:RECORDS*TOKENS,capacityTokens:CAPACITY,writeSeconds:writeSeconds,coldArchiveSeconds:coldSeconds,dbBytes:statSync(join(root,'index.db')).size,dirBytes,facets:{tokens:facets.tokens,hotTokens:facets.hotTokens,coldTokens:facets.coldTokens,hotCount:facets.hotCount,coldCount:facets.coldCount}},retrieval:{probes:PROBES,hit1,hit3,hit5,medianMs:retrieval[Math.floor(PROBES*.5)].latencyMs,p95Ms:retrieval[Math.floor(PROBES*.95)].latencyMs},probes}
writeFileSync(OUT,JSON.stringify(out,null,2)); console.log(JSON.stringify({archive:out.archive,retrieval:out.retrieval,out:OUT},null,2))
core.close(); rmSync(root,{recursive:true,force:true})
