/**
 * Live endpoint A/B: does memex retrieval evidence improve long-horizon answers?
 *
 * Builds a deterministic long-horizon fixture, asks questions under two
 * conditions, and grades answers by the exact fact token:
 *   control   — only the retained tail of the history is in the prompt;
 *   treatment — the tail plus the memex search/open evidence for the question.
 *
 * Providers (env keys required; nothing is hard-coded):
 *   anthropic  ANTHROPIC_API_KEY  [ANTHROPIC_MODEL=claude-sonnet-5-5]
 *   openai     OPENAI_API_KEY     [OPENAI_MODEL=gpt-6.1-sol]
 *   deepseek   DEEPSEEK_API_KEY   [DEEPSEEK_MODEL=deepseek-flash]
 *
 * Usage:
 *   node --import ./test/register.mjs scripts/live-ab.mjs --provider anthropic --probes 6 --out docs/assets/benchmarks/live-ab.json
 *   node scripts/live-ab.mjs --dry-run            # build prompts only, no network
 *
 * Live calls consume provider tokens. Providers not configured in a run are
 * reported and skipped rather than failing the whole run.
 */
import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { performance } from 'node:perf_hooks'
import { LocalStoreCore } from '../packages/memex-core/lib/store.js'
import { memoryWorkspaceKey } from '../packages/memex-core/index.js'
import { resolveModelProfile } from '../packages/memex-core/lib/model-profiles.js'
import { buildRecallInjection } from '../packages/memex-core/lib/manual.js'

const arg = (name, fallback) => {
  const index = process.argv.indexOf(`--${name}`)
  return index >= 0 ? process.argv[index + 1] : fallback
}
const PROVIDER = arg('provider', 'all')
const PROBES = Number(arg('probes', 6))
const OUT = arg('out', join(tmpdir(), 'memex-live-ab.json'))
const EMIT_DIR = arg('emit-prompts')
const SEED = Number(arg('seed', 1))
const TURNS = Number(arg('turns', 120))
const TAIL_RECORDS = Number(arg('tail', 20))
const DRY_RUN = process.argv.includes('--dry-run')
const MODEL_OVERRIDE = arg('model')

function mulberry32(seed) { let state = seed >>> 0; return () => { state = (state + 0x6D2B79F5) >>> 0; let t = state; t = Math.imul(t ^ (t >>> 15), t | 1); t ^= t + Math.imul(t ^ (t >>> 7), t | 61); return ((t ^ (t >>> 14)) >>> 0) / 4294967296 } }
const random = mulberry32(SEED)
const CWD = join(tmpdir(), 'memex-live-ws')
const SESSION = 'live-ab'
const WS = memoryWorkspaceKey(CWD, SESSION)
const ROOT = mkdtempSync(join(tmpdir(), 'memex-live-'))
const store = new LocalStoreCore({ root: ROOT, capacityTokens: 1_000_000_000, sessionCapacityTokens: 100_000_000, defaultLevels: { l2: false, l3: false } })

// Long history: many technical turns, a few facts deep inside.
const facts = []
const topics = ['gateway', 'parser', 'scheduler', 'ledger', 'cache', 'router', 'worker', 'indexer', 'bridge', 'harbor']
for (let index = 0; index < TURNS; index += 1) {
  const isFact = index % 15 === 0 && facts.length < 60
  const topic = topics[index % topics.length]
  const fact = isFact ? `FACT-${String(index).padStart(3, '0')}-${random().toString(36).slice(2, 7)}` : undefined
  const body = isFact
    ? `Turn ${index} (${topic}): the durable value is ${fact}; keep it for the ${topic} question. ` + 'technical notes '.repeat(120)
    : `Turn ${index} (${topic}): reviewed the ${topic} config, retried the job, adjusted backoff. ` + 'technical notes '.repeat(120)
  const card = store.write({ kind: isFact ? 'fact' : 'episode', title: isFact ? `${topic} value at turn ${index}` : `turn ${index} ${topic} work`, summary: isFact ? `the ${topic} value is ${fact}` : `work log for ${topic}`, useWhen: `read when continuing ${topic} work`, body, workspaceKey: WS, scope: 'workspace', tokens: Math.round(body.length / 4) })
  if (isFact) facts.push({ turn: index, topic, fact, id: card.id })
}
// Keep only the newest TAIL_RECORDS hot; archive everything older (simulates
// L1 eviction). list() clamps to 100 rows, so read all ids from the DB.
const allRows = store.database().prepare('SELECT id FROM records ORDER BY created_at ASC, id ASC').all()
for (const row of allRows.slice(0, Math.max(0, allRows.length - TAIL_RECORDS))) store.archiveCold(row.id)
// v0.7.2: record the exact tail membership instead of re-querying list() (whose
// ordering was not guaranteed to match the archived region). Tail ids are the
// newest TAIL_RECORDS by insertion order; the control prompt is built from
// exactly these rows and the plan records inTail/evicted for verification.
const tailIds = allRows.slice(-TAIL_RECORDS).map((row) => row.id)
const tailIdsSet = new Set(tailIds)
const tailRows = tailIds.map((id) => store.database().prepare('SELECT * FROM records WHERE id = ?').get(id)).filter(Boolean)
const tailText = tailRows.map((row) => `${row.title}\n${row.summary}`).join('\n')
store.close()
const evidenceCore = new LocalStoreCore({ root: ROOT, capacityTokens: 1_000_000_000, sessionCapacityTokens: 100_000_000, defaultLevels: { l2: false, l3: false } })

const probes = facts.slice(0, PROBES).map((probe) => ({ ...probe, inTail: tailIdsSet.has(probe.id), evicted: !tailIdsSet.has(probe.id) }))
const buildPrompt = (probe, withMemory) => {
  const control = `You are continuing a long software project. The earlier conversation is no longer in context; only the most recent tail is shown.\n\nRecent context:\n${tailText}\n\nQuestion: what durable value was recorded at turn ${probe.turn} for ${probe.topic}? Answer with the exact FACT id only.`
  if (!withMemory) return control
  const profile = resolveModelProfile(MODEL_OVERRIDE ?? 'claude-sonnet-5-5')
  const result = evidenceCore.search({ query: `turn ${probe.turn} ${probe.topic} durable value FACT`, workspaceKey: WS, scope: 'workspace', limit: 5, rerank: profile.rerank, maxTerms: profile.queryTerms?.maxTerms })
  const hit = result.hits.find((card) => card.id === probe.id)
  const opened = hit === undefined ? undefined : evidenceCore.get(hit.id)
  const evidence = buildRecallInjection(profile, result.hits, `memex evidence for turn ${probe.turn} (${probe.topic})`)
  return `You are continuing a long software project. Earlier context was evicted, but memex archived it verbatim and you have retrieval evidence.\n\nRecent context:\n${tailText}\n\n${evidence}\n\nOpened record:\n${opened?.body?.slice(0, 3000) ?? '(not found)'}\n\nQuestion: what durable value was recorded at turn ${probe.turn} for ${probe.topic}? Answer with the exact FACT id only.`
}

const providers = {
  anthropic: {
    key: process.env.ANTHROPIC_API_KEY,
    model: MODEL_OVERRIDE ?? process.env.ANTHROPIC_MODEL ?? 'claude-sonnet-5-5',
    call: async (prompt, model) => {
      const response = await fetch('https://api.anthropic.com/v1/messages', {
        method: 'POST',
        headers: { 'content-type': 'application/json', 'x-api-key': process.env.ANTHROPIC_API_KEY, 'anthropic-version': '2023-06-01' },
        body: JSON.stringify({ model, max_tokens: 100, messages: [{ role: 'user', content: prompt }] }),
      })
      const data = await response.json()
      return { text: data.content?.map((part) => part.text ?? '').join('') ?? '', usage: data.usage ?? null, error: data.error?.message }
    },
  },
  openai: {
    key: process.env.OPENAI_API_KEY,
    model: MODEL_OVERRIDE ?? process.env.OPENAI_MODEL ?? 'gpt-6.1-sol',
    call: async (prompt, model) => {
      const response = await fetch('https://api.openai.com/v1/responses', {
        method: 'POST',
        headers: { 'content-type': 'application/json', authorization: `Bearer ${process.env.OPENAI_API_KEY}` },
        body: JSON.stringify({ model, max_output_tokens: 100, input: prompt }),
      })
      const data = await response.json()
      const text = data.output?.flatMap((item) => item.content ?? []).map((part) => part.text ?? '').join('') ?? ''
      return { text, usage: data.usage ?? null, error: data.error?.message }
    },
  },
  deepseek: {
    key: process.env.DEEPSEEK_API_KEY,
    model: MODEL_OVERRIDE ?? process.env.DEEPSEEK_MODEL ?? 'deepseek-flash',
    call: async (prompt, model) => {
      const response = await fetch('https://api.deepseek.com/chat/completions', {
        method: 'POST',
        headers: { 'content-type': 'application/json', authorization: `Bearer ${process.env.DEEPSEEK_API_KEY}` },
        body: JSON.stringify({ model, max_tokens: 100, messages: [{ role: 'user', content: prompt }] }),
      })
      const data = await response.json()
      return { text: data.choices?.[0]?.message?.content ?? '', usage: data.usage ?? null, error: data.error?.message }
    },
  },
}

const requested = PROVIDER === 'all' ? Object.keys(providers) : [PROVIDER]
const buildBatchPrompt = (withMemory) => {
  const lines = probes.map((probe, index) => `Q${index} (turn ${probe.turn}, topic ${probe.topic}): what durable value was recorded then?`)
  if (!withMemory) {
    return [
      'You are continuing a long software project. The earlier conversation is no longer in context; only the most recent tail is shown.',
      '',
      'Recent context:',
      tailText,
      '',
      'Questions:',
      ...lines,
      '',
      'Answer each question on its own line exactly as "Q<index>: <FACT id>" (or "Q<index>: UNKNOWN" when the value is not present). Do not use tools. Do not explain.',
    ].join('\n')
  }
  const evidenceBlocks = []
  const openedBlocks = []
  for (const [index, probe] of probes.entries()) {
    const profile = resolveModelProfile(MODEL_OVERRIDE ?? 'deepseek-flash')
    const result = evidenceCore.search({ query: `turn ${probe.turn} ${probe.topic} durable value FACT`, workspaceKey: WS, scope: 'workspace', limit: 5, rerank: profile.rerank, maxTerms: profile.queryTerms?.maxTerms })
    const hit = result.hits.find((card) => card.id === probe.id)
    const opened = hit === undefined ? undefined : evidenceCore.get(hit.id)
    evidenceBlocks.push(`Evidence for Q${index}: ${buildRecallInjection(profile, result.hits, `turn ${probe.turn} ${probe.topic}`)}`)
    openedBlocks.push(`Record for Q${index} (memex ${opened?.id ?? 'not found'}):\n${String(opened?.body ?? '').slice(0, 1200)}`)
  }
  return [
    'You are continuing a long software project. Earlier context was evicted, but memex archived it verbatim and you have retrieval evidence.',
    '',
    'Recent context:',
    tailText,
    '',
    'Memory evidence:',
    ...evidenceBlocks,
    '',
    'Opened records:',
    ...openedBlocks,
    '',
    'Questions:',
    ...lines,
    '',
    'Answer each question on its own line exactly as "Q<index>: <FACT id>" from the evidence. Do not use tools. Do not explain.',
  ].join('\n')
}

if (EMIT_DIR !== undefined) {
  mkdirSync(EMIT_DIR, { recursive: true })
  writeFileSync(join(EMIT_DIR, 'control.txt'), buildBatchPrompt(false))
  writeFileSync(join(EMIT_DIR, 'treatment.txt'), buildBatchPrompt(true))
  writeFileSync(join(EMIT_DIR, 'plan.json'), JSON.stringify({ generatedAt: new Date().toISOString(), seed: SEED, turns: TURNS, tailCount: TAIL_RECORDS, tailIds, tailRecords: tailRows.map((row) => ({ id: row.id, title: row.title, summary: row.summary })), probes: probes.map((probe, index) => ({ index, turn: probe.turn, topic: probe.topic, expected: probe.fact, id: probe.id, inTail: probe.inTail, evicted: probe.evicted })) }, null, 2))
  console.log(JSON.stringify({ emitted: EMIT_DIR, probes: probes.length, controlBytes: buildBatchPrompt(false).length, treatmentBytes: buildBatchPrompt(true).length }, null, 2))
  evidenceCore.close()
  rmSync(ROOT, { recursive: true, force: true })
  process.exit(0)
}

const report = { generatedAt: new Date().toISOString(), dryRun: DRY_RUN, probes: probePlan(), providers: [] }
function probePlan() {
  return probes.map((probe) => ({ turn: probe.turn, topic: probe.topic, expected: probe.fact, inTail: probe.inTail, evicted: probe.evicted, controlChars: buildPrompt(probe, false).length, treatmentChars: buildPrompt(probe, true).length }))
}

if (DRY_RUN) {
  report.note = 'Dry run: prompts built, no provider calls made.'
  evidenceCore.close()
  writeFileSync(OUT, `${JSON.stringify(report, null, 2)}\n`)
  console.log(JSON.stringify({ out: OUT, probes: report.probes.length, note: report.note }, null, 2))
  rmSync(ROOT, { recursive: true, force: true })
  process.exit(0)
}

for (const name of requested) {
  const provider = providers[name]
  if (provider === undefined) { report.providers.push({ provider: name, skipped: 'unknown provider' }); continue }
  if (!provider.key) { report.providers.push({ provider: name, model: provider.model, skipped: 'not configured in this run (set ' + (name === 'anthropic' ? 'ANTHROPIC_API_KEY' : name === 'openai' ? 'OPENAI_API_KEY' : 'DEEPSEEK_API_KEY') + ' to include this provider)' }); continue }
  const rows = []
  for (const probe of probes) {
    const row = { turn: probe.turn, expected: probe.fact }
    for (const condition of ['control', 'treatment']) {
      const started = performance.now()
      try {
        const result = await provider.call(buildPrompt(probe, condition === 'treatment'), provider.model)
        row[condition] = { ms: Math.round(performance.now() - started), correct: typeof result.text === 'string' && result.text.includes(probe.fact), text: String(result.text).slice(0, 120), usage: result.usage, error: result.error }
      } catch (error) {
        row[condition] = { ms: Math.round(performance.now() - started), correct: false, error: error instanceof Error ? error.message : String(error) }
      }
    }
    rows.push(row)
  }
  const accuracy = (condition) => rows.filter((row) => row[condition]?.correct).length / rows.length
  report.providers.push({ provider: name, model: provider.model, accuracy: { control: accuracy('control'), treatment: accuracy('treatment') }, rows })
}
evidenceCore.close()
writeFileSync(OUT, `${JSON.stringify(report, null, 2)}\n`)
console.log(JSON.stringify({ out: OUT, providers: report.providers.map((entry) => ({ provider: entry.provider, model: entry.model, skipped: entry.skipped, accuracy: entry.accuracy })) }, null, 2))
rmSync(ROOT, { recursive: true, force: true })
