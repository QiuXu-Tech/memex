#!/usr/bin/env node
// Claude live A/B bridge over an OpenAI-compatible gateway (APIMaster).
//
// Generates the same 3-seed synthetic fixture as codex-ab (fixed tail
// membership), sends the control/treatment batch prompts to Claude, grades
// exact FACT ids, and writes a shareable JSON report with provider usage.
//
// Usage:
//   APIMASTER_API_KEY=... node scripts/claude-ab.mjs --model claude-sonnet-5-5
//   APIMASTER_API_KEY=... node scripts/claude-ab.mjs --model claude-opus-5-5 --seeds 1 --probes 20

import { spawnSync } from 'node:child_process'
import { mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const HERE = dirname(fileURLToPath(import.meta.url))
const REPO = resolve(HERE, '..')
const NODE = process.execPath
const arg = (name, fallback) => {
  const index = process.argv.indexOf(`--${name}`)
  return index >= 0 ? process.argv[index + 1] : fallback
}
const MODEL = arg('model', 'claude-sonnet-5-5')
const SEEDS = Number(arg('seeds', 3))
const PROBES = Number(arg('probes', 20))
const TURNS = Number(arg('turns', 300))
const BASE_URL = String(arg('base-url', process.env.APIMASTER_BASE_URL ?? 'https://apimaster.ai/v1')).replace(/\/$/, '')
const KEY = process.env.APIMASTER_API_KEY ?? process.env.OPENAI_API_KEY
const OUT = resolve(arg('out', join(tmpdir(), 'memex-claude-live-ab.json')))
if (!KEY) {
  console.error('APIMASTER_API_KEY (or OPENAI_API_KEY) is required')
  process.exit(1)
}
const parseAnswers = (text) => {
  const answers = {}
  for (const line of String(text ?? '').split('\n')) {
    const match = line.match(/^\s*Q(\d+)\s*:\s*(.+?)\s*$/)
    if (match !== null) answers[Number(match[1])] = match[2].replace(/^`|`$/g, '')
  }
  return answers
}
const grade = (answers, expected) => {
  const rows = expected.map((probe) => ({ ...probe, answer: answers[probe.index] ?? '', correct: answers[probe.index] === probe.expected }))
  return { rows, correct: rows.filter((row) => row.correct).length, total: rows.length }
}
const callClaude = async (prompt) => {
  let lastError
  for (let attempt = 1; attempt <= 3; attempt += 1) {
    try {
      const response = await fetch(`${BASE_URL}/chat/completions`, {
        method: 'POST',
        headers: { 'content-type': 'application/json', authorization: `Bearer ${KEY}` },
        body: JSON.stringify({ model: MODEL, messages: [{ role: 'user', content: prompt }], max_tokens: 500, temperature: 0 }),
        signal: AbortSignal.timeout(120_000),
      })
      const data = await response.json()
      if (!response.ok) throw new Error(`HTTP ${response.status}: ${data?.error?.message ?? JSON.stringify(data).slice(0, 300)}`)
      return { text: data.choices?.[0]?.message?.content ?? '', usage: data.usage ?? null }
    } catch (error) {
      lastError = error
      if (attempt < 3) await new Promise((resolveDelay) => setTimeout(resolveDelay, attempt * 1500))
    }
  }
  throw lastError
}
const report = {
  format: 1,
  kind: 'live-ab-claude-result',
  generatedAt: new Date().toISOString(),
  provider: 'apimaster',
  baseUrl: BASE_URL,
  model: MODEL,
  method: 'live-ab.mjs --emit-prompts batch prompts; OpenAI-compatible /chat/completions; exact-FACT grading; tail membership saved',
  seeds: [],
  aggregate: {},
  usage: { promptTokens: 0, completionTokens: 0, totalTokens: 0, calls: 0 },
  raw: [],
  caveats: [
    'Control/treatment prompts use synthetic fixtures; no private data is sent.',
    'Batch prompts ask the model to answer only from the supplied context; this is evidence-in-prompt, not a tool-calling loop.',
    'Usage comes from the gateway response; verify with your own APIMaster dashboard if needed.',
  ],
}
const all = { control: [], treatment: [], evictedControl: [], evictedTreatment: [] }
const tempRoot = mkdtempSync(join(tmpdir(), 'memex-claude-ab-'))
try {
  for (let seed = 1; seed <= SEEDS; seed += 1) {
    const promptsDir = join(tempRoot, `seed-${seed}`)
    const emit = spawnSync(NODE, ['--import', join(REPO, 'test/register.mjs'), join(REPO, 'scripts/live-ab.mjs'), '--emit-prompts', promptsDir, '--probes', String(PROBES), '--turns', String(TURNS), '--seed', String(seed), '--model', MODEL], { encoding: 'utf8' })
    if (emit.status !== 0) throw new Error(`fixture generation failed (seed ${seed}): ${emit.stderr.slice(-500)}`)
    const plan = JSON.parse(readFileSync(join(promptsDir, 'plan.json'), 'utf8'))
    if (!Array.isArray(plan.tailIds)) throw new Error('plan.json lacks tailIds; update live-ab.mjs before running')
    const evictedSet = new Set(plan.probes.filter((probe) => probe.evicted === true).map((probe) => probe.index))
    const controlPrompt = readFileSync(join(promptsDir, 'control.txt'), 'utf8')
    const treatmentPrompt = readFileSync(join(promptsDir, 'treatment.txt'), 'utf8')
    const controlReply = await callClaude(controlPrompt)
    const treatmentReply = await callClaude(treatmentPrompt)
    for (const [label, reply] of [['control', controlReply], ['treatment', treatmentReply]]) {
      if (reply.usage !== null) {
        report.usage.calls += 1
        report.usage.promptTokens += Number(reply.usage.prompt_tokens ?? reply.usage.input_tokens ?? 0)
        report.usage.completionTokens += Number(reply.usage.completion_tokens ?? reply.usage.output_tokens ?? 0)
        report.usage.totalTokens += Number(reply.usage.total_tokens ?? 0)
      }
      report.raw.push({ seed, label, textTail: reply.text.slice(-3000), usage: reply.usage })
    }
    const control = grade(parseAnswers(controlReply.text), plan.probes)
    const treatment = grade(parseAnswers(treatmentReply.text), plan.probes)
    all.control.push(...control.rows.map((row) => row.correct))
    all.treatment.push(...treatment.rows.map((row) => row.correct))
    all.evictedControl.push(...control.rows.filter((row) => evictedSet.has(row.index)).map((row) => row.correct))
    all.evictedTreatment.push(...treatment.rows.filter((row) => evictedSet.has(row.index)).map((row) => row.correct))
    report.seeds.push({ seed, turns: plan.turns, tailCount: plan.tailCount, tailIds: plan.tailIds, probes: plan.probes.length, evictedProbes: evictedSet.size, control, treatment })
  }
} catch (error) {
  console.error(`claude-ab failed: ${error.message}`)
  process.exit(1)
} finally {
  rmSync(tempRoot, { recursive: true, force: true })
}
const summary = (values) => ({ correct: values.filter(Boolean).length, n: values.length, accuracy: values.length === 0 ? 0 : Math.round((values.filter(Boolean).length / values.length) * 10000) / 10000 })
report.aggregate = { control: summary(all.control), treatment: summary(all.treatment), evictedControl: summary(all.evictedControl), evictedTreatment: summary(all.evictedTreatment) }
report.usage.totalTokens = report.usage.totalTokens || report.usage.promptTokens + report.usage.completionTokens
writeFileSync(OUT, JSON.stringify(report, null, 2) + '\n')
console.log(`\nClaude (${MODEL}) live A/B`)
console.log(`control:   ${report.aggregate.control.correct}/${report.aggregate.control.n}`)
console.log(`treatment: ${report.aggregate.treatment.correct}/${report.aggregate.treatment.n}`)
console.log(`evicted:   ${report.aggregate.evictedControl.correct}/${report.aggregate.evictedControl.n} → ${report.aggregate.evictedTreatment.correct}/${report.aggregate.evictedTreatment.n}`)
console.log(`usage:     prompt=${report.usage.promptTokens}, completion=${report.usage.completionTokens}, total=${report.usage.totalTokens} (${report.usage.calls} calls)`)
console.log(`\nReport: ${OUT}`)
