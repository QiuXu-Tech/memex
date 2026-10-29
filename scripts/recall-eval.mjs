/**
 * Recall evaluation for the extra-context subsystem (dependency-free, synthetic).
 *
 * Two deterministic suites:
 *  - synthetic: unique card cues + body-only facts, half archived cold;
 *  - demo: a small generic "long project" archive (deployment, database,
 *    API, UI, review, incident topics) with natural-language questions.
 *
 * Reports hit@1/@3/@5, MRR and cold-record recall for the direct search path
 * and the auto-recall query-extraction path. `--threshold` turns the result
 * into a CI gate.
 *
 * Usage (from the repo root; the test register provides host resolution):
 *   node --import ./test/register.mjs scripts/recall-eval.mjs --suite all
 *   node --import ./test/register.mjs scripts/recall-eval.mjs --suite synthetic --threshold 0.9
 */
import { mkdtempSync, rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { performance } from 'node:perf_hooks'
import { LocalStoreCore } from '../packages/memex-local/lib/store.js'
import { memoryQueryTerms } from '../packages/memex-seam/lib/index.js'

const arg = (name, fallback) => {
  const index = process.argv.indexOf(`--${name}`)
  return index >= 0 ? process.argv[index + 1] : fallback
}
const SUITE = arg('suite', 'all')
const THRESHOLD = Number(arg('threshold', 0))

const percentile = (values, ratio) => {
  const sorted = [...values].sort((a, b) => a - b)
  return sorted[Math.min(sorted.length - 1, Math.floor(sorted.length * ratio))] ?? 0
}

const evaluate = (label, probes, search) => {
  let hit1 = 0
  let hit3 = 0
  let hit5 = 0
  let mrr = 0
  let coldTotal = 0
  let coldHit = 0
  const latencies = []
  for (const probe of probes) {
    const started = performance.now()
    const hits = search(probe)
    latencies.push(performance.now() - started)
    const rank = hits.findIndex((card) => probe.any.includes(card.id))
    if (rank === 0) hit1 += 1
    if (rank >= 0 && rank < 3) hit3 += 1
    if (rank >= 0 && rank < 5) hit5 += 1
    if (rank >= 0) mrr += 1 / (rank + 1)
    if (probe.cold === true) {
      coldTotal += 1
      if (rank >= 0) coldHit += 1
    }
  }
  const total = probes.length
  const report = {
    label,
    total,
    hit1: hit1 / total,
    hit3: hit3 / total,
    hit5: hit5 / total,
    mrr: mrr / total,
    coldRecall: coldTotal === 0 ? undefined : coldHit / coldTotal,
    p50Ms: percentile(latencies, 0.5),
    p95Ms: percentile(latencies, 0.95),
  }
  const pct = (value) => `${Math.round(value * 100)}%`
  console.log(`${label}: n=${report.total} hit@1 ${pct(report.hit1)} | hit@3 ${pct(report.hit3)} | hit@5 ${pct(report.hit5)} | MRR ${report.mrr.toFixed(2)}${report.coldRecall === undefined ? '' : ` | cold recall ${pct(report.coldRecall)}`} | p50 ${report.p50Ms.toFixed(2)}ms p95 ${report.p95Ms.toFixed(2)}ms`)
  return report
}

const withCore = async (name, build) => {
  const root = mkdtempSync(join(tmpdir(), `mem-eval-${name}-`))
  const core = new LocalStoreCore({ root, capacityTokens: 100_000_000, sessionCapacityTokens: 10_000_000, defaultLevels: { l2: false, l3: false } })
  try {
    return await build(core)
  } finally {
    core.close()
    rmSync(root, { recursive: true, force: true })
  }
}

const syntheticSuite = () => withCore('synthetic', (core) => {
  const written = []
  for (let index = 0; index < 120; index += 1) {
    const fact = `FACT-${String(index).padStart(3, '0')}-${Math.random().toString(36).slice(2, 7)}`
    const cue = `cardcue-${index}-${Math.random().toString(36).slice(2, 6)}`
    const body = `earlier discussion number ${index}. The answer id is ${fact}. ` + 'x'.repeat(300)
    written.push(core.write({ kind: index % 3 === 0 ? 'fact' : 'artifact', title: `turn ${index} ${cue}`, summary: `summary turn ${index} marker ${cue}`, useWhen: `read when continuing ${cue}`, body, tokens: Math.max(20, Math.round(body.length / 4)), workspaceKey: 'syn', sessionId: 'syn-sess', scope: 'workspace' }))
  }
  for (const card of written.slice(0, 60)) core.archiveCold(card.id)
  const probes = []
  for (let index = 0; index < 40; index += 1) {
    const record = written[(index * 5 + 1) % 120]
    const fact = core.get(record.id).body.match(/FACT-\d{3}-[a-z0-9]+/)[0]
    probes.push({ q: record.title.split(' ')[2], any: [record.id], cold: written.indexOf(record) < 60 })
    probes.push({ q: fact, any: [record.id], cold: written.indexOf(record) < 60 })
  }
  const search = (probe) => core.search({ query: probe.q, workspaceKey: 'syn', scope: 'workspace', limit: 5 }).hits
  return evaluate('synthetic suite', probes, search)
})

const demoSuite = () => withCore('demo', (core) => {
  const topics = [
    ['deployment', 'Production deploy used Cloudflare Pages with pinned build IDs and seven security headers; rollback keeps the previous deployment ID.'],
    ['database', 'The store uses SQLite in WAL mode with node:sqlite; migrations run lazily on first open and are idempotent.'],
    ['api', 'The HTTP API is document-relative: GET /api/memory.index and POST /api/memory.compress are owner-scoped.'],
    ['ui', 'The memory panel lives in the shell overlay; the context ring inner arc is teal for session capture and blue for workspace capture.'],
    ['review', 'Code review requires a green offline harness, bundle parity, and no personal data in fixtures.'],
    ['incident', 'An install once crashed the host: the generated bundle was missing a module; the fix was rebuilding modules before install.'],
    ['backup', 'Backups use VACUUM INTO plus sha256 manifests; restore refuses non-empty targets without --force.'],
    ['privacy', 'L3 is shared across sessions; secret-looking spans are forced into L2 or eviction is skipped.'],
  ]
  const written = []
  for (const [topic, body] of topics) {
    for (let index = 0; index < 6; index += 1) {
      const id = `rec-${topic}-${index}`
      const record = core.write({ kind: index % 2 === 0 ? 'episode' : 'decision', title: `${topic} decision ${index}`, summary: `${topic} note ${index}`, useWhen: `read when continuing ${topic} work`, body: `${body} (variant ${index})`, tokens: 60, workspaceKey: 'demo', sessionId: 'demo-sess', scope: 'workspace' })
      written.push({ id: record.id, topic, index })
    }
  }
  for (const record of written.filter((entry) => entry.index < 3)) core.archiveCold(record.id)
  const probes = []
  for (const [topic] of topics) {
    const expected = written.filter((entry) => entry.topic === topic).map((entry) => entry.id)
    probes.push({ q: `how did we handle ${topic}?`, any: expected, cold: expected.some((id) => written.find((entry) => entry.id === id)?.index < 3) })
    probes.push({ q: `${topic} 决策`, any: expected, cold: false })
  }
  const search = (probe) => core.search({ query: probe.q, workspaceKey: 'demo', scope: 'workspace', limit: 5 }).hits
  const direct = evaluate('demo suite (memory_search)', probes, search)
  const autoRecall = evaluate('demo suite (auto-recall query)', probes, (probe) => {
    const query = memoryQueryTerms(probe.q, 12).join(' ')
    return core.search({ query: query.length >= 3 ? query : probe.q, workspaceKey: 'demo', scope: 'workspace', limit: 3 }).hits
  })
  return [direct, autoRecall]
})

console.log(`suite=${SUITE} threshold=${THRESHOLD}`)
const results = []
if (SUITE === 'synthetic' || SUITE === 'all') results.push(await syntheticSuite())
if (SUITE === 'demo' || SUITE === 'all') results.push(...(await demoSuite()))
const failed = results.filter((report) => report.hit5 < THRESHOLD)
if (failed.length > 0) {
  console.error(`BELOW THRESHOLD: ${failed.map((report) => report.label).join(', ')}`)
  process.exit(1)
}
