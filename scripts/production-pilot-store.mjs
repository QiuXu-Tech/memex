/** Private pilot worker: isolated real Memex tools and an independent keyword baseline. */
import { createInterface } from 'node:readline'
import { LocalStoreCore } from '../packages/memex-core/lib/store.js'
import { materializeStoreContext } from '../packages/memex-core/lib/context-pager.js'
import { memoryWorkspaceKey } from '../packages/memex-core/index.js'
import { registerMemoryTools } from '../packages/memex-tool/lib/tools.js'

let store, records = [], definitions = new Map(), workspaceKey, sessionId = 'pilot-session', cwd = '/isolated-pilot'
const send = (value) => process.stdout.write(JSON.stringify(value) + '\n')
const fields = (schema) => Object.fromEntries(Object.entries(schema).map(([name, v]) => {
  const { required, ...rest } = v; return [name, rest]
}))
const schemas = (names) => names.map((name) => {
  const def = definitions.get(name); if (!def) throw new Error(`missing tool ${name}`)
  const required = Object.entries(def.parameters).filter(([,v]) => v.required).map(([k]) => k)
  return { type: 'function', function: { name, description: def.description, parameters: { type: 'object', properties: fields(def.parameters), required, additionalProperties: false } } }
})
const terms = (q) => {
  const text = String(q ?? '').toLowerCase(); const words = text.match(/[a-z0-9_]{3,}|[\u4e00-\u9fff]{2,}/g) ?? []
  return [...new Set(words.flatMap(w => /[\u4e00-\u9fff]/.test(w) && w.length > 2 ? [w, ...Array.from({length:w.length-1}, (_,i)=>w.slice(i,i+2))] : [w]).filter(w => !['what','the','and','how','for','are','was','that','with','which'].includes(w)))].slice(0,20)
}
const baselineTools = [
  {type:'function',function:{name:'archive_search',description:'Search the existing archived history using keywords. Returns record IDs and short matching excerpts.',parameters:{type:'object',properties:{query:{type:'string'}},required:['query'],additionalProperties:false}}},
  {type:'function',function:{name:'archive_open',description:'Open a retrieved archive record by ID.',parameters:{type:'object',properties:{id:{type:'string'}},required:['id'],additionalProperties:false}}},
]
async function action(req) {
  if (req.op === 'init') {
    if (store) throw new Error('already initialized')
    cwd = req.cwd; sessionId = req.sessionId; workspaceKey = memoryWorkspaceKey(cwd, sessionId)
    store = new LocalStoreCore({root:req.root,capacityTokens:10000000,defaultLevels:{l2:false,l3:false}})
    records = Array.isArray(req.records) ? req.records : []
    if (req.seedToStore !== false) for (const [i,p] of records.entries()) store.write({id:p.id,kind:p.kind,title:p.title,summary:p.summary,useWhen:p.useWhen,body:p.body,createdAt:i+1,workspaceKey,scope:'workspace'})
    const memory = { getLevels: async()=>({l2:false,l3:true}), search: async x=>store.search(x), get:async id=>store.get(id), markRead:async ids=>store.markRead(ids), write:async x=>store.write(x), grep:async x=>store.grep(x) }
    registerMemoryTools({tools:{register(def){definitions.set(def.name,def)}}},memory,{})
    return {ok:true, schemas:schemas(['memory_search','memory_open','memory_write']),baselineTools, archiveRecords:records.length, seededInStore:req.seedToStore === false ? 0 : records.length}
  }
  if (!store) throw new Error('not initialized')
  if (req.op === 'pager') {
    const result = materializeStoreContext({store,workspaceKey,scopes:['workspace'],sessionId,query:req.query,budgetTokens:1800,pageTokenCap:400})
    return {text:result.text,ids:result.includedIds,tokens:result.tokens,sources:result.sources}
  }
  if (req.op === 'tool') {
    if (req.name === 'archive_search') {
      const q=terms(req.args?.query); const hits=records.map(p=>{const text=`${p.title} ${p.summary} ${p.body}`.toLowerCase();return {p,score:q.reduce((n,w)=>n+(text.includes(w)?1:0),0)}}).filter(x=>x.score>0).sort((a,b)=>b.score-a.score || a.p.id.localeCompare(b.p.id)).slice(0,8)
      return {text:hits.length ? hits.map(x=>`${x.p.id} · ${x.p.title}\n${String(x.p.summary).slice(0,200)}`).join('\n') : 'No matching records.'}
    }
    if (req.name === 'archive_open') {const p=records.find(x=>x.id===req.args?.id);return {text:p ? `${p.id} · ${p.title}\n${p.body}` : 'No record with that ID.'}}
    const def=definitions.get(req.name);if(!def || !['memory_search','memory_open','memory_write'].includes(req.name))throw new Error('unsupported tool')
    const text=await def.execute(req.args ?? {},{agent:{session:{id:sessionId,header:{cwd}}}})
    return {text:String(text).replace(/^file: .*\n/gm,'')}
  }
  if (req.op === 'stats') return {records:store.list({workspaceKey,scopes:['workspace'],sessionId,limit:1000,includeStatus:true}).length}
  if (req.op === 'close') {store.close();store=undefined;return {ok:true}}
  throw new Error('unsupported operation')
}
for await (const line of createInterface({input:process.stdin,crlfDelay:Infinity})) {
  try {send({ok:true,result:await action(JSON.parse(line))})} catch(error) {send({ok:false,error:String(error?.message ?? error)})}
}
if(store)store.close()
