/** Replay timestamp-checked historical write snapshots locally through the pager. */
import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs'
import { join } from 'node:path'
import { performance } from 'node:perf_hooks'
import { LocalStoreCore } from '../packages/memex-local/lib/store.js'
import { materializeStoreContext } from '../packages/memex-core/lib/context-pager.js'
const arg = (key) => { const i = process.argv.indexOf(`--${key}`); return i < 0 ? undefined : process.argv[i + 1] }
const input = arg('input'), output = arg('out'), stores = arg('stores')
if (!input || !output || !stores) throw new Error('usage: --input EPISODES_JSON --out PRIVATE_OUTPUT --stores NEW_DIRECTORY')
if (existsSync(output)) throw new Error('output already exists; refusing to overwrite private replay data')
mkdirSync(stores)
const data = JSON.parse(readFileSync(input, 'utf8'))
const expansionFile = arg('expansions')
const expansions = expansionFile ? new Map(readFileSync(expansionFile, 'utf8').trim().split('\n').map(JSON.parse).filter((row) => row.group === 'private' && row.status === 'ok').map((row) => [row.id, row.queries])) : new Map()
const weights = JSON.parse(readFileSync(new URL('../packages/memex-core/lib/lexical-reranker.json', import.meta.url), 'utf8'))
const results = []
for (const episode of data.episodes) {
  if (expansionFile && !expansions.has(episode.id)) throw new Error(`missing successful query expansion for ${episode.id}`)
  if (episode.pages.some((page) => page.availableAfter >= episode.querySeq) || episode.tail.some((item) => item.seq >= episode.querySeq)) throw new Error(`future event in ${episode.id}`)
  const root = join(stores, episode.id)
  mkdirSync(root)
  const store = new LocalStoreCore({ root, capacityTokens: 100_000_000, sessionCapacityTokens: 10_000_000, defaultLevels: { l2: false, l3: false } })
  try {
    for (const page of episode.pages) store.write({ id: page.id, kind: page.kind ?? 'fact', title: page.title, summary: page.summary, useWhen: page.useWhen, body: page.body, createdAt: page.sequence, workspaceKey: 'replay', sessionId: episode.id, scope: 'workspace' })
    const base = { store, workspaceKey: 'replay', scopes: ['workspace'], budgetTokens: 1800, query: episode.question, pageTokenCap: 400, learnedPageMaxTokens: 700 }
    const conditions = {}
    for (const name of expansionFile ? ['rule', 'hybrid', 'rule-expanded', 'hybrid-expanded'] : ['rule', 'hybrid']) {
      const start = performance.now()
      const result = materializeStoreContext({ ...base, ...(name.endsWith('-expanded') ? { queryAlternatives: expansions.get(episode.id) ?? [] } : {}), ...(name.startsWith('hybrid') ? { learnedRerank: weights, learnedTopK: 8 } : {}) })
      conditions[name] = { text: result.text, ids: result.includedIds, tokens: result.tokens, status: result.budgetStatus, sources: result.sources, latencyMs: performance.now() - start }
    }
    results.push({ id: episode.id, querySeq: episode.querySeq, question: episode.question, tail: episode.tail, referencePages: episode.pages, conditions })
  } finally { store.close() }
}
writeFileSync(output, JSON.stringify({ sourceSha256: data.sourceSha256, conditions: 'same timestamp-checked successful write snapshots and tail; store/pager; rule vs lexical hybrid topK8; 1800 chars/4; page cap 400; max learned page 700; no forced core', limitations: data.limitations, episodes: results }, null, 2), { mode: 0o600 })
console.log(JSON.stringify({ episodes: results.length, allWithinBudget: results.every((e) => Object.values(e.conditions).every((x) => x.tokens <= 1800)), output }))
