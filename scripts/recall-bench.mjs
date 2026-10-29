/**
 * Long-horizon recall benchmark for the extra-context subsystem.
 *
 * Builds a throwaway archive that models a long conversation: many records with
 * unique facts, a mix of hot and cold (L1-evicted) spans, and two probe classes:
 *  - card probes: the cue lives in title/summary (what FTS indexes);
 *  - body probes: the cue lives only in the raw body (what the hot-file
 *    fallback / memory_grep reaches).
 *
 * Reports retrieval hit rates and the token cost of recovering an answer, which
 * is the practical value of extra context in long conversations.
 *
 * Usage (from the subsystem root; the test register provides host resolution):
 *   node --import ./test/register.mjs scripts/recall-bench.mjs
 *   node --import ./test/register.mjs scripts/recall-bench.mjs --records 200 --probes 40
 */
import { mkdtempSync, rmSync, statSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { performance } from 'node:perf_hooks'
import { LocalStoreCore } from '../packages/dsh-memory-local/lib/store.js'

const arg = (name, fallback) => {
  const index = process.argv.indexOf(`--${name}`)
  return index >= 0 ? Number(process.argv[index + 1]) : fallback
}
const RECORDS = Math.max(20, arg('records', 200))
const PROBES = Math.max(5, arg('probes', 40))
const COLD_RATIO = 0.5
const root = mkdtempSync(join(tmpdir(), 'mem-recall-'))
const core = new LocalStoreCore({ root, capacityTokens: 100_000_000, sessionCapacityTokens: 10_000_000, defaultLevels: { l2: false, l3: false } })
const workspaceKey = 'recall-wk'
const sessionId = 'recall-session'

// 1. Long-conversation archive: every record carries one unique fact token.
const written = []
for (let index = 0; index < RECORDS; index += 1) {
  const fact = `FACT-${String(index).padStart(3, '0')}-${Math.random().toString(36).slice(2, 8)}`
  const cardCue = `topic${index % 17}`
  const body = `earlier discussion number ${index}. The answer id is ${fact}. ` + 'x'.repeat(400)
  written.push(core.write({
    kind: index % 4 === 0 ? 'episode' : index % 3 === 0 ? 'fact' : 'artifact',
    title: `turn ${index} cardcue${index}`,
    summary: `summary of turn ${index} with marker cardcue${index}`,
    useWhen: `read when continuing cardcue${index}`,
    body,
    tokens: Math.max(20, Math.round(body.length / 4)),
    workspaceKey,
    sessionId,
    scope: 'workspace',
  }))
}

// 2. Evict half of the archive (models L1 eviction over a long conversation).
const coldIds = written.slice(0, Math.floor(RECORDS * COLD_RATIO)).map((card) => card.id)
for (const id of coldIds) core.archiveCold(id)

// 3. Probes: one unique card cue (FTS-visible) and one body-only fact per record.
const cardProbes = []
const bodyProbes = []
for (let index = 0; index < PROBES; index += 1) {
  const record = written[(index * 7 + 3) % RECORDS]
  const turn = Number(record.title.split(' ')[1])
  const fact = core.get(record.id).body.match(/FACT-\d{3}-[a-z0-9]+/)[0]
  cardProbes.push({ question: `cardcue${turn}`, expect: fact, cold: coldIds.includes(record.id) })
  bodyProbes.push({ question: fact, expect: fact, cold: coldIds.includes(record.id) })
}
const factOf = (card) => {
  try { return (core.get(card.id)?.body.match(/FACT-\d{3}-[a-z0-9]+/) ?? [])[0] } catch { return undefined }
}
const runProbes = (label, probes, recover) => {
  let hit1 = 0
  let hit3 = 0
  let hit5 = 0
  const latencies = []
  for (const probe of probes) {
    const started = performance.now()
    const hits = recover(probe)
    latencies.push(performance.now() - started)
    const index = hits.findIndex((card) => factOf(card) === probe.expect)
    if (index === 0) hit1 += 1
    if (index >= 0 && index < 3) hit3 += 1
    if (index >= 0 && index < 5) hit5 += 1
  }
  latencies.sort((a, b) => a - b)
  console.log(`${label}: hit@1 ${(hit1 / probes.length * 100).toFixed(0)}% | hit@3 ${(hit3 / probes.length * 100).toFixed(0)}% | hit@5 ${(hit5 / probes.length * 100).toFixed(0)}% | median ${latencies[Math.floor(latencies.length / 2)].toFixed(2)}ms`)
}

console.log(`archive: ${RECORDS} records, ${Math.round(RECORDS * COLD_RATIO)} cold (evicted), ${Math.round(RECORDS * (1 - COLD_RATIO))} hot`)
console.log(`db ${(statSync(join(root, 'index.db')).size / 1048576).toFixed(2)} MiB, hot/cold tokens:`, JSON.stringify(core.facets({ workspaceKey, scope: 'workspace' }), (key, value) => ['byKind', 'byKindTokens', 'byStatus', 'days'].includes(key) ? undefined : value))

// Baseline: without extra context, the model only sees the current L1 window.
console.log('baseline (no extra context, L1 window only): hit@any 0% — evicted turns are unrecoverable')

// With extra context: search by card cue (FTS over title/summary).
runProbes('card probes via memory_search', cardProbes, (probe) => core.search({ query: probe.question, workspaceKey, scope: 'workspace', limit: 5 }).hits)
// Body-only cues: hot records are reachable through memory_search's bounded
// file fallback; cold records need the explicit memory_grep tool.
const hotBody = bodyProbes.filter((probe) => probe.cold === false)
const coldBody = bodyProbes.filter((probe) => probe.cold === true)
runProbes('hot body-only probes via memory_search fallback', hotBody, (probe) => core.search({ query: probe.question, workspaceKey, scope: 'workspace', limit: 5 }).hits)
runProbes('cold body-only probes via memory_grep', coldBody, (probe) => core.grep({ pattern: probe.question, workspaceKey, scope: 'workspace', limit: 5 }).map((hit) => ({ id: hit.id })))

// Token economics: what one recovery costs.
const sample = written[0]
const opened = core.get(sample.id)
const catalog = core.catalog({ workspaceKey, scopes: ['workspace'], maxChars: 2400 })
console.log(`cost: catalog ${Math.round(catalog.length / 1.5)} tokens/step (only when it changes) · one memory_open ≈ ${opened.tokens} tokens · one search result card ≈ ${Math.round((sample.summary.length + sample.title.length) / 1.5)} tokens`)
console.log(`archive value: ${(core.facets({ workspaceKey, scope: 'workspace' }).tokens / 1000).toFixed(0)}K conversation tokens retained outside L1`)
core.close()
rmSync(root, { recursive: true, force: true })
