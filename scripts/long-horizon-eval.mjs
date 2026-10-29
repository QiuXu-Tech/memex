/**
 * Long-horizon A/B evaluation: dsh-memory vs "no extra context" baselines.
 *
 * Modes:
 *  - `compaction` (default): builds a 120K-token synthetic project history with
 *    evenly spaced fact turns, a 60K-token L1 window, and writes:
 *      * old-span.txt        the span a DSH compaction would summarize
 *      * tail-span.txt       the retained tail the model would still see
 *      * facts.json          fact records (id, fact token, topic, depth)
 *      * queries.json        natural-language questions for retrieval eval
 *      * results.json        truncation baseline + dsh-memory retrieval metrics
 *    A model-written compaction summary is produced separately (see report);
 *    `--summary <file>` measures how many facts survive it.
 *  - `scale`: for each history size, measures dsh-memory retrieval recall and
 *    the no-memory availability ceiling (window / history), then writes
 *    results to `results.json`.
 *
 * Usage (repo root):
 *   node --import ./test/register.mjs scripts/long-horizon-eval.mjs --mode compaction --out /tmp/lh-compaction
 *   node --import ./test/register.mjs scripts/long-horizon-eval.mjs --mode scale --sizes 1000000,5000000,10000000 --window 1000000 --out /tmp/lh-scale
 *   node --import ./test/register.mjs scripts/long-horizon-eval.mjs --summary /tmp/summary.txt --out /tmp/lh-compaction
 */
import { mkdirSync, readFileSync, writeFileSync, existsSync } from 'node:fs'
import { mkdtempSync, rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { performance } from 'node:perf_hooks'
import { LocalStoreCore } from '../packages/dsh-memory-local/lib/store.js'

const arg = (name, fallback) => {
  const index = process.argv.indexOf(`--${name}`)
  return index >= 0 ? process.argv[index + 1] : fallback
}
const MODE = arg('mode', 'compaction')
const OUT = arg('out', `/tmp/lh-${MODE}`)
const WINDOW = Number(arg('window', MODE === 'compaction' ? 60_000 : 1_000_000))
const SIZES = String(arg('sizes', '1000000,5000000,10000000')).split(',').map(Number)

/** Deterministic PRNG so runs are reproducible. */
function rng(seed) {
  let state = seed >>> 0
  return () => {
    state = (state * 1664525 + 1013904223) >>> 0
    return state / 0xffffffff
  }
}
const WORDS = ['gateway', 'ledger', 'scheduler', 'parser', 'cache', 'router', 'worker', 'indexer', 'bridge', 'queen', 'harbor', 'orchid', 'cobalt', 'ember', 'falcon']
const TOPICS = [...WORDS, 'billing', 'onboarding', 'telemetry', 'migration', 'rollback', 'quota', 'sandbox', 'webhook']

const buildHistory = (totalTokens) => {
  const random = rng(42)
  const tokensPerRecord = 1500
  const recordCount = Math.max(12, Math.round(totalTokens / tokensPerRecord))
  let facts = []
  const records = []
  for (let index = 0; index < recordCount; index += 1) {
    const isFact = index % 2 === 0
    const topic = TOPICS[index % TOPICS.length]
    // Deterministic identifiers (seeded PRNG) so summaries and results are
    // reproducible across runs.
    const draw = () => Math.floor(random() * 36 ** 5).toString(36).padStart(5, '0')
    const cue = `CTX-${String(index).padStart(3, '0')}-${draw().toUpperCase()}`
    const fact = isFact ? `FACT-${String(index).padStart(3, '0')}-${draw()}` : undefined
    // A technically rich turn so a compaction summary must genuinely choose what
    // to keep instead of trivially copying a short fact ledger.
    const filler = Array.from({ length: Math.max(30, Math.round((tokensPerRecord * 4 - 400) / 7)) }, () => WORDS[Math.floor(random() * WORDS.length)]).join(' ')
    const user = isFact
      ? `Turn ${index} (${topic}): I need you to remember ${cue} — the value for later lookup is ${fact}.`
      : `Turn ${index} (${topic}): continue the ${topic} work, check the previous config and retry.`
    const assistant = isFact
      ? `Noted. ${cue} → ${fact}. I also updated modules/${topic}/handler.js, ran the integration suite (3 passed, 1 skipped) and aligned the ${topic} config with the rollout. ${filler}`
      : `Updated modules/${topic}/handler.js and services/${topic}.ts; ran the integration suite (2 passed), saw a transient timeout on the ${topic} retry path, tuned the backoff and verified the dashboard. ${filler}`
    const body = `User: ${user}\nAssistant: ${assistant}`
    const record = {
      index,
      isFact,
      topic,
      cue,
      fact,
      title: isFact ? `${topic} identifier ${cue}` : `${topic} work log turn ${index}`,
      summary: isFact ? `${cue} maps to ${fact}.` : `Continued ${topic} implementation and tests.`,
      body,
      tokens: Math.max(100, Math.round(body.length / 4)),
    }
    records.push(record)
    if (isFact) facts.push({ id: undefined, index, fact, topic, cue, recordIndex: index })
  }
  // Keep at most 40 retrieval probes, evenly spread over the history.
  const maxFacts = 40
  if (facts.length > maxFacts) {
    const step = facts.length / maxFacts
    const keep = new Set(Array.from({ length: maxFacts }, (_, i) => Math.floor(i * step)))
    facts = facts.filter((_, i) => keep.has(i))
  }
  return { records, facts }
}

const writeStore = (records, coldThrough) => {
  const root = mkdtempSync(join(tmpdir(), 'lh-store-'))
  const core = new LocalStoreCore({ root, capacityTokens: 1_000_000_000, sessionCapacityTokens: 100_000_000, defaultLevels: { l2: false, l3: false } })
  const written = []
  for (const record of records) {
    const card = core.write({
      kind: 'episode',
      title: record.title,
      summary: record.summary,
      useWhen: `read when continuing ${record.topic}`,
      body: record.body,
      tokens: record.tokens,
      workspaceKey: 'lh-ws',
      sessionId: 'lh-session',
      scope: 'workspace',
    })
    written.push({ ...record, id: card.id })
  }
  // Simulate L1 eviction: the oldest `coldThrough` records moved to the cold tier.
  let coldTokens = 0
  for (const record of written.filter((entry) => entry.index < coldThrough)) {
    core.archiveCold(record.id)
    coldTokens += record.tokens
  }
  return { core, written, coldTokens, root }
}

const queryFor = (fact) => `之前在 ${fact.cue} 记下的 ${fact.topic} 编号是什么？`

const runRetrieval = (core, written, facts) => {
  let hit1 = 0
  let hit3 = 0
  let hit5 = 0
  const latencies = []
  let tokensSpent = 0
  const details = []
  for (const fact of facts) {
    const record = written[fact.index]
    fact.id = record.id
    const started = performance.now()
    const hits = core.search({ query: queryFor(fact), workspaceKey: 'lh-ws', scope: 'workspace', limit: 5 }).hits
    latencies.push(performance.now() - started)
    const rank = hits.findIndex((card) => card.id === record.id)
    if (rank === 0) hit1 += 1
    if (rank >= 0 && rank < 3) hit3 += 1
    if (rank >= 0 && rank < 5) hit5 += 1
    // Cost of answering: result card tokens + opened body tokens (the model
    // would memory_open the hit to read the fact).
    const cardTokens = hits.reduce((sum, card) => sum + Math.ceil((card.title.length + card.summary.length) / 4) + 24, 0)
    tokensSpent += cardTokens + (rank >= 0 ? record.tokens : 0)
    details.push({ fact: fact.fact, topic: fact.topic, recordIndex: fact.index, rank, cold: undefined })
  }
  return {
    facts: facts.length,
    hit1: hit1 / facts.length,
    hit3: hit3 / facts.length,
    hit5: hit5 / facts.length,
    medianLatencyMs: latencies.sort((a, b) => a - b)[Math.floor(latencies.length / 2)],
    tokensPerQuestion: Math.round(tokensSpent / facts.length),
    details,
  }
}

mkdirSync(OUT, { recursive: true })

if (MODE === 'compaction') {
  const totalTokens = Number(arg('tokens', 120_000))
  const { records, facts } = buildHistory(totalTokens)
  // Facts stay where they were written; the window keeps the newest WINDOW tokens.
  const ordered = [...records].sort((a, b) => a.index - b.index)
  let accumulated = 0
  let cut = ordered.length
  for (let index = ordered.length - 1; index >= 0; index -= 1) {
    accumulated += ordered[index].tokens
    cut = index
    if (accumulated >= WINDOW) break
  }
  const coldThrough = cut
  const oldRecords = ordered.slice(0, cut)
  const tailRecords = ordered.slice(cut)
  const { core, written } = writeStore(records, coldThrough)
  const retrieval = runRetrieval(core, written, facts)
  for (const detail of retrieval.details) {
    const record = written[detail.recordIndex]
    detail.cold = record.index < coldThrough
  }
  const oldSpanFacts = facts.filter((fact) => fact.index < coldThrough)
  const tailFacts = facts.filter((fact) => fact.index >= coldThrough)
  // Baseline 1: truncation — the model only sees the retained tail.
  const truncationAvailable = tailFacts.length
  const truncation = { facts: facts.length, available: truncationAvailable, accuracy: truncationAvailable / facts.length }
  // Baseline 2: model-written compaction summary, measured when --summary given.
  let compaction
  const summaryPath = arg('summary')
  if (summaryPath !== undefined && existsSync(summaryPath)) {
    const summary = readFileSync(summaryPath, 'utf8')
    const survived = facts.filter((fact) => summary.includes(fact.fact) || summary.includes(fact.cue))
    const survivedOld = survived.filter((fact) => fact.index < coldThrough).length
    // Under DSH compaction the model still sees the retained tail plus the
    // summary, so availability = tail facts + old facts the summary kept.
    const tailAvailable = facts.filter((fact) => fact.index >= coldThrough).length
    compaction = {
      facts: facts.length,
      tailFacts: tailAvailable,
      oldFacts: oldSpanFacts.length,
      survivedOld,
      oldFactRecovery: oldSpanFacts.length === 0 ? undefined : survivedOld / oldSpanFacts.length,
      accuracy: (tailAvailable + survivedOld) / facts.length,
      reportTokens: Math.round(summary.length / 4),
    }
  }
  writeFileSync(join(OUT, 'old-span.txt'), oldRecords.map((record) => `### Turn ${record.index} (${record.topic})\n${record.body}`).join('\n\n'))
  writeFileSync(join(OUT, 'tail-span.txt'), tailRecords.map((record) => record.body).join('\n\n'))
  writeFileSync(join(OUT, 'facts.json'), JSON.stringify(written.filter((record) => record.isFact), null, 2))
  writeFileSync(join(OUT, 'queries.json'), JSON.stringify(facts.map((fact) => ({ fact: fact.fact, topic: fact.topic, query: queryFor(fact), recordIndex: fact.index })), null, 2))
  const stats = {
    mode: 'compaction',
    historyTokens: records.reduce((sum, record) => sum + record.tokens, 0),
    windowTokens: WINDOW,
    records: records.length,
    coldRecords: coldThrough,
    tailRecords: ordered.length - coldThrough,
    oldSpanTokens: oldRecords.reduce((sum, record) => sum + record.tokens, 0),
    truncation,
    compaction,
    dshMemory: retrieval,
  }
  writeFileSync(join(OUT, 'results.json'), JSON.stringify(stats, null, 2))
  console.log(JSON.stringify({ historyTokens: stats.historyTokens, oldSpanTokens: stats.oldSpanTokens, truncation, compaction, dshMemory: { hit5: retrieval.hit5, hit3: retrieval.hit3, coldFacts: retrieval.details.filter((detail) => detail.cold).length, tokensPerQuestion: retrieval.tokensPerQuestion, medianLatencyMs: retrieval.medianLatencyMs } }, null, 2))
  core.close()
  rmSync(core.root, { recursive: true, force: true })
} else if (MODE === 'scale') {
  const results = []
  for (const size of SIZES) {
    const { records, facts } = buildHistory(size)
    const ordered = [...records].sort((a, b) => a.index - b.index)
    let accumulated = 0
    let cut = ordered.length
    for (let index = ordered.length - 1; index >= 0; index -= 1) {
      accumulated += ordered[index].tokens
      cut = index
      if (accumulated >= WINDOW) break
    }
    const { core, written } = writeStore(records, cut)
    const retrieval = runRetrieval(core, written, facts)
    const noMemoryAvailability = Math.min(1, WINDOW / Math.max(1, records.reduce((sum, record) => sum + record.tokens, 0)))
    results.push({
      historyTokens: records.reduce((sum, record) => sum + record.tokens, 0),
      records: records.length,
      windowTokens: WINDOW,
      noMemoryAvailability,
      dshMemoryHit5: retrieval.hit5,
      dshMemoryHit3: retrieval.hit3,
      tokensPerQuestion: retrieval.tokensPerQuestion,
      medianLatencyMs: retrieval.medianLatencyMs,
    })
    console.log(JSON.stringify(results.at(-1)))
    core.close()
    rmSync(core.root, { recursive: true, force: true })
  }
  writeFileSync(join(OUT, 'results.json'), JSON.stringify({ mode: 'scale', windowTokens: WINDOW, results }, null, 2))
}

rmSync(join(OUT, '.tmp'), { recursive: true, force: true })
