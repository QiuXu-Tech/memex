/** Seeded synthetic 10M assigned-token store; compare rule/hybrid through the real pager. */
import { mkdirSync, readFileSync, statSync, writeFileSync } from 'node:fs'
import { performance } from 'node:perf_hooks'
import { LocalStoreCore } from '../packages/memex-local/lib/store.js'
import { materializeStoreContext } from '../packages/memex-core/lib/context-pager.js'

const arg = (key) => { const index = process.argv.indexOf(`--${key}`); return index < 0 ? undefined : process.argv[index + 1] }
const seed = Number(arg('seed'))
const root = arg('store')
const output = arg('out')
if (!Number.isSafeInteger(seed) || seed < 0 || !root || !output) throw new Error('usage: --seed N --store NEW_DIRECTORY --out FILE')
mkdirSync(root)
let state = seed >>> 0
const random = () => { state = (state + 0x6D2B79F5) >>> 0; let t = state; t = Math.imul(t ^ (t >>> 15), t | 1); t ^= t + Math.imul(t ^ (t >>> 7), t | 61); return ((t ^ (t >>> 14)) >>> 0) / 4294967296 }
const pick = (values) => values[Math.floor(random() * values.length)]
const workspaceKey = `bench-${seed}`
const store = new LocalStoreCore({ root, capacityTokens: 10_000_000, sessionCapacityTokens: 10_000_000, defaultLevels: { l2: false, l3: false } })
const weights = JSON.parse(readFileSync(new URL('../packages/memex-core/lib/lexical-reranker.json', import.meta.url), 'utf8'))
const records = []
const filler = 'x'.repeat(19_850)
try {
  const writeStart = performance.now()
  for (let i = 0; i < 2000; i += 1) {
    const fact = `FACT-S${seed}-${String(i).padStart(4, '0')}-${Math.floor(random() * 0xffffffff).toString(16).padStart(8, '0')}`
    const card = store.write({ kind: 'fact', title: `turn ${i} cardcue${i}`, summary: `summary turn ${i} cardcue${i}`, useWhen: `read for cardcue${i}`, body: `Historical note about cardcue${i}. Unique answer: ${fact}. ${filler}`, tokens: 5000, workspaceKey, sessionId: `session-${seed}`, scope: 'workspace' })
    records.push({ id: card.id, i, fact })
  }
  const writeMs = performance.now() - writeStart
  const coldStart = performance.now()
  for (const row of records.slice(0, 1000)) store.archiveCold(row.id)
  const coldMs = performance.now() - coldStart
  const base = { store, workspaceKey, scopes: ['workspace'], budgetTokens: 1800, pageTokenCap: 400, learnedPageMaxTokens: 700 }
  const resident = new Set(materializeStoreContext({ ...base, budgetTokens: 0 }).sources.map((row) => row.recordId))
  const inside = records.filter((row) => resident.has(row.id))
  const outside = records.filter((row) => !resident.has(row.id))
  if (inside.length < 20 || outside.length < 20) throw new Error('not enough resident/nonresident records')
  const chosen = new Set()
  const targets = []
  for (const group of [inside, outside]) {
    for (let i = 0; i < 20; i += 1) {
      let target
      do { target = pick(group) } while (chosen.has(target.id))
      chosen.add(target.id)
      targets.push(target)
    }
  }
  const probes = []
  for (const [index, target] of targets.entries()) {
    const cue = `cardcue${target.i}`
    const query = `What unique answer was recorded for ${cue}?`
    const searchStart = performance.now()
    const hits = store.search({ query: cue, workspaceKey, scope: 'workspace', limit: 5 }).hits
    const searchMs = performance.now() - searchStart
    const choices = {}
    for (const name of (index % 2 === 0 ? ['rule', 'hybrid'] : ['hybrid', 'rule'])) {
      const start = performance.now()
      const result = materializeStoreContext({ ...base, query, ...(name === 'hybrid' ? { learnedRerank: weights, learnedTopK: 8 } : {}) })
      choices[name] = { latencyMs: performance.now() - start, targetInCandidates: result.sources.some((x) => x.recordId === target.id), targetSelected: result.includedIds.includes(target.id), factPresent: result.text.includes(target.fact), tokens: result.tokens, status: result.budgetStatus, selectedCount: result.includedIds.length, selectedIds: result.includedIds }
    }
    probes.push({ index, targetId: target.id, targetIndex: target.i, targetCold: target.i < 1000, group: resident.has(target.id) ? 'resident' : 'nonresident', searchRank: hits.findIndex((row) => row.id === target.id) + 1, searchMs, choices })
  }
  const data = { kind: 'synthetic-pager-10m', seed, environment: { node: process.version, platform: process.platform, arch: process.arch }, archive: { records: records.length, assignedTokens: 10_000_000, tokensPerRecord: 5000, fillerChars: filler.length, hot: 1000, cold: 1000, writeMs, coldMs, indexBytes: statSync(`${root}/index.db`).size }, setup: { probes: 40, sampling: '20 resident and 20 nonresident targets', search: 'exact cardcue; evaluated separately and not injected into pager', budgetTokens: 1800, pageTokenCap: 400, learnedPageMaxTokens: 700, learnedTopK: 8, counter: 'chars/4 estimate', pinnedOrCoreIds: [], ruleAndHybridSameQuery: true }, probes }
  writeFileSync(output, JSON.stringify(data, null, 2))
  console.log(JSON.stringify({ seed, probes: probes.length, searchHit1: probes.filter((p) => p.searchRank === 1).length, ruleFact: probes.filter((p) => p.choices.rule.factPresent).length, hybridFact: probes.filter((p) => p.choices.hybrid.factPresent).length, output }))
} finally {
  store.close()
}
