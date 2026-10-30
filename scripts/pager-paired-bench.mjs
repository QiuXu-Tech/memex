/** Re-evaluate saved synthetic probes on a copy of their original store. */
import { existsSync, readFileSync, writeFileSync } from 'node:fs'
import { performance } from 'node:perf_hooks'
import { LocalStoreCore } from '../packages/memex-local/lib/store.js'
import { materializeStoreContext } from '../packages/memex-core/lib/context-pager.js'
const arg = (key) => { const i = process.argv.indexOf(`--${key}`); return i < 0 ? undefined : process.argv[i + 1] }
const input = arg('input'), root = arg('store'), output = arg('out')
if (!input || !root || !output) throw new Error('usage: --input BASELINE_JSON --store CLONED_STORE --out NEW_FILE')
if (existsSync(output)) throw new Error('output already exists')
const baseline = JSON.parse(readFileSync(input, 'utf8'))
const weights = JSON.parse(readFileSync(new URL('../packages/memex-core/lib/lexical-reranker.json', import.meta.url), 'utf8'))
const store = new LocalStoreCore({ root, capacityTokens: 10_000_000, sessionCapacityTokens: 10_000_000, defaultLevels: { l2: false, l3: false } })
const rows = []
try {
  for (const probe of baseline.probes) {
    const target = store.get(probe.targetId)
    if (!target) throw new Error(`target missing from copied store: ${probe.targetId}`)
    const fact = target.body.match(/FACT-S\d+-\d{4}-[0-9a-f]{8}/)?.[0]
    if (!fact) throw new Error(`target fact missing from copied store: ${probe.targetId}`)
    const query = `What unique answer was recorded for cardcue${probe.targetIndex}?`
    const request = { store, workspaceKey: `bench-${baseline.seed}`, scopes: ['workspace'], query, budgetTokens: 1800, pageTokenCap: 400, learnedPageMaxTokens: 700 }
    const hits = store.search({ workspaceKey: request.workspaceKey, scopes: request.scopes, query, limit: 8, excludeSuperseded: true }).hits
    const after = {}
    for (const name of (probe.index % 2 === 0 ? ['rule', 'hybrid'] : ['hybrid', 'rule'])) {
      const started = performance.now()
      const result = materializeStoreContext({ ...request, ...(name === 'hybrid' ? { learnedRerank: weights, learnedTopK: 8 } : {}) })
      after[name] = { latencyMs: performance.now() - started, targetInCandidates: result.sources.some((x) => x.recordId === probe.targetId), targetSelected: result.includedIds.includes(probe.targetId), factPresent: result.text.includes(fact), tokens: result.tokens, status: result.budgetStatus, selectedIds: result.includedIds, candidateIds: result.sources.map((x) => x.recordId).sort() }
    }
    rows.push({ index: probe.index, targetId: probe.targetId, targetIndex: probe.targetIndex, targetCold: probe.targetCold, baselineGroup: probe.group, fullQuerySearchRank: hits.findIndex((x) => x.id === probe.targetId) + 1, before: probe.choices, after })
  }
  const result = { kind: 'synthetic-pager-paired-retest', seed: baseline.seed, baselineVersion: 'c05dd12', environment: { node: process.version, platform: process.platform, arch: process.arch }, setup: { probes: rows.length, data: 'same baseline probe IDs and copied archive', query: 'natural-language question including the exact cardcue', budgetTokens: 1800, pageTokenCap: 400, learnedPageMaxTokens: 700, learnedTopK: 8, searchLimit: 8, forcedCoreIds: [], counter: 'chars/4 estimate' }, probes: rows }
  writeFileSync(output, JSON.stringify(result, null, 2))
  console.log(JSON.stringify({ seed: baseline.seed, probes: rows.length, querySearchHit1: rows.filter((x) => x.fullQuerySearchRank === 1).length, ruleBefore: rows.filter((x) => x.before.rule.factPresent).length, ruleAfter: rows.filter((x) => x.after.rule.factPresent).length, hybridBefore: rows.filter((x) => x.before.hybrid.factPresent).length, hybridAfter: rows.filter((x) => x.after.hybrid.factPresent).length }))
} finally { store.close() }
