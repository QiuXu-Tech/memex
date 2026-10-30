/** Paired synthetic synonym diagnostic. Model-generated alternatives are input data. */
import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs'
import { join } from 'node:path'
import { pathToFileURL } from 'node:url'
import { LocalStoreCore } from '../packages/memex-local/lib/store.js'
import { materializeStoreContext } from '../packages/memex-core/lib/context-pager.js'
const arg = (key) => { const i = process.argv.indexOf(`--${key}`); return i < 0 ? undefined : process.argv[i + 1] }
const baseline = arg('baseline'), root = arg('store'), output = arg('out'), expansion = arg('expansions'), seed = Number(arg('seed'))
if (!baseline || !root || !output || !expansion || !Number.isSafeInteger(seed) || existsSync(root) || existsSync(output)) throw new Error('usage: --baseline REPO --store NEW_DIR --out NEW_FILE --expansions JSONL --seed INTEGER')
const fixtures = JSON.parse(readFileSync(new URL('./pager-semantic-fixtures.json', import.meta.url)))
const alternatives = new Map(readFileSync(expansion, 'utf8').trim().split('\n').map(JSON.parse).filter((x) => x.group === 'synthetic').map((x) => [x.id, x]))
if (fixtures.some((x) => alternatives.get(x.id)?.status !== 'ok')) throw new Error('missing successful model-generated alternatives')
let state = seed >>> 0
const random = () => { state = (Math.imul(state, 1664525) + 1013904223) >>> 0; return state / 4294967296 }
const shuffled = (values) => values.map((value) => ({ value, sort: random() })).sort((a, b) => a.sort - b.sort).map((x) => x.value)
mkdirSync(root)
const store = new LocalStoreCore({ root, capacityTokens: 10000000, defaultLevels: { l2: false, l3: false } })
const before = await import(pathToFileURL(join(baseline, 'packages/memex-core/lib/context-pager.js')).href)
const weights = JSON.parse(readFileSync(new URL('../packages/memex-core/lib/lexical-reranker.json', import.meta.url)))
try {
  for (const [i, t] of shuffled(fixtures).entries()) {
    store.write({ id: `target-${t.id}`, kind: 'fact', title: t.title, summary: t.summary, body: t.body, workspaceKey: 'semantic-eval', scope: 'workspace' })
    if (i % 2 === 0) store.archiveCold(`target-${t.id}`)
  }
  for (const i of shuffled(Array.from({ length: 60 }, (_, i) => i))) {
    const topic = fixtures[i % fixtures.length]
    store.write({ id: `distractor-${i}`, kind: 'fact', title: `project record ${i} ${topic.title.split(' ')[0]}`, summary: 'other project note ' + topic.summary.split(' ').slice(0, 2).join(' '), body: `Unrelated note ${i}: no requested target fact. ` + 'ordinary content '.repeat(20), workspaceKey: 'semantic-eval', scope: 'workspace' })
  }
  const probes = []
  for (const t of fixtures) {
    const base = { store, workspaceKey: 'semantic-eval', scopes: ['workspace'], query: t.query, budgetTokens: 500, pageTokenCap: 80, learnedPageMaxTokens: 200 }
    const conditions = {}
    for (const [phase, fn, queryAlternatives] of [['before', before.materializeStoreContext, []], ['after-default', materializeStoreContext, []], ['after-expanded', materializeStoreContext, alternatives.get(t.id).queries]]) {
      for (const policy of ['rule', 'hybrid']) {
        const result = fn({ ...base, queryAlternatives, ...(policy === 'hybrid' ? { learnedRerank: weights, learnedTopK: 4 } : {}) })
        conditions[`${phase}-${policy}`] = { candidate: result.sources.some((x) => x.recordId === `target-${t.id}`), selected: result.includedIds.includes(`target-${t.id}`), fact: result.text.includes(t.fact), tokens: result.tokens }
      }
    }
    probes.push({ id: t.id, query: t.query, alternatives: alternatives.get(t.id).queries, conditions })
  }
  const result = { kind: 'synthetic-synonym-paired-diagnostic', baselineCommit: '13b9301', seed, design: '12 handcrafted questions, same 12 targets and 60 partly topical distractors across seeds; targets always older; half cold; model paraphrases generated once from question alone; no human labels; no production claim', probes }
  writeFileSync(output, JSON.stringify(result, null, 2))
  console.log(JSON.stringify({ seed, counts: Object.fromEntries(Object.keys(probes[0].conditions).map((key) => [key, probes.filter((p) => p.conditions[key].fact).length])) }))
} finally { store.close() }
