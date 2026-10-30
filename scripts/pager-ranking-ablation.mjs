/** Compare old and new hybrid order on the identical post-fix candidate pages. */
import { existsSync, readFileSync, writeFileSync } from 'node:fs'
import { join } from 'node:path'
import { pathToFileURL } from 'node:url'
import { LocalStoreCore } from '../packages/memex-local/lib/store.js'
import { materializeContext } from '../packages/memex-core/lib/context-materializer.js'
const arg = (key) => { const i = process.argv.indexOf(`--${key}`); return i < 0 ? undefined : process.argv[i + 1] }
const baselineRepo = arg('baseline'), input = arg('input'), root = arg('store'), output = arg('out')
if (!baselineRepo || !input || !root || !output) throw new Error('usage: --baseline BASELINE_REPO --input PAIRED_JSON --store CLONED_STORE --out NEW_FILE')
if (existsSync(output)) throw new Error('output already exists')
const old = await import(pathToFileURL(join(baselineRepo, 'packages/memex-core/lib/context-materializer.js')).href)
const data = JSON.parse(readFileSync(input, 'utf8'))
const weights = JSON.parse(readFileSync(new URL('../packages/memex-core/lib/lexical-reranker.json', import.meta.url), 'utf8'))
const store = new LocalStoreCore({ root, capacityTokens: 10_000_000, sessionCapacityTokens: 10_000_000, defaultLevels: { l2: false, l3: false } })
const rows = []
try {
  for (const probe of data.probes) {
    const pages = probe.after.hybrid.candidateIds.map((id) => {
      const row = store.get(id)
      if (!row || row.kind !== 'fact') throw new Error(`unexpected missing or non-fact page ${id}`)
      return { id: row.id, title: row.title, summary: row.summary, useWhen: row.useWhen, body: row.body, sequence: Number(row.createdAt), createdAt: Number(row.createdAt) }
    })
    const target = store.get(probe.targetId)
    const fact = target?.body.match(/FACT-S\d+-\d{4}-[0-9a-f]{8}/)?.[0]
    if (!fact) throw new Error(`target fact missing ${probe.targetId}`)
    const request = { pages, query: `What unique answer was recorded for cardcue${probe.targetIndex}?`, budgetTokens: 1800, pageTokenCap: 400, learnedPageMaxTokens: 700, learnedRerank: weights, learnedTopK: 8 }
    const before = old.materializeContext(request)
    const after = materializeContext(request)
    if (JSON.stringify(after.includedIds) !== JSON.stringify(probe.after.hybrid.selectedIds) || after.tokens !== probe.after.hybrid.tokens) throw new Error(`pager/ablation mismatch: ${probe.index}`)
    rows.push({ index: probe.index, targetId: probe.targetId, candidateCount: pages.length, oldSelected: before.includedIds.includes(probe.targetId), oldFact: before.text.includes(fact), newSelected: after.includedIds.includes(probe.targetId), newFact: after.text.includes(fact), oldTokens: before.tokens, newTokens: after.tokens })
  }
  writeFileSync(output, JSON.stringify({ kind: 'synthetic-hybrid-ranking-ablation', seed: data.seed, baseline: 'c05dd12', setup: 'identical post-fix candidate pages and query; old versus new materializer', rows }, null, 2))
  console.log(JSON.stringify({ seed: data.seed, probes: rows.length, oldFact: rows.filter((r) => r.oldFact).length, newFact: rows.filter((r) => r.newFact).length }))
} finally { store.close() }
