#!/usr/bin/env node
// Claude real tool-calling loop over the memex MCP server.
//
// Unlike the batch evidence-in-prompt bridge, this lets the model decide when
// to call memory_search / memory_open. The harness executes the requested MCP
// JSON-RPC calls against the real server, appends results to the conversation,
// and grades the final exact FACT id.
//
// Usage:
//   APIMASTER_API_KEY=... node scripts/claude-tool-loop.mjs --model claude-sonnet-5-5

import { spawnSync } from 'node:child_process'
import { mkdtempSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { LocalStoreCore } from '../packages/memex-core/lib/store.js'
import { memoryWorkspaceKey } from '../packages/memex-core/index.js'

const HERE = dirname(fileURLToPath(import.meta.url))
const REPO = resolve(HERE, '..')
const arg = (name, fallback) => {
  const index = process.argv.indexOf(`--${name}`)
  return index >= 0 ? process.argv[index + 1] : fallback
}
const MODEL = arg('model', 'claude-sonnet-5-5')
const BASE_URL = String(arg('base-url', process.env.APIMASTER_BASE_URL ?? 'https://apimaster.ai/v1')).replace(/\/$/, '')
const KEY = process.env.APIMASTER_API_KEY ?? process.env.OPENAI_API_KEY
const OUT = resolve(arg('out', join(tmpdir(), 'memex-claude-tool-loop.json')))
if (!KEY) {
  console.error('APIMASTER_API_KEY (or OPENAI_API_KEY) is required')
  process.exit(1)
}
const MCP_SERVER = join(REPO, 'packages/memex-mcp/bin/server.mjs')
const REGISTER = join(REPO, 'test/register.mjs')
const NODE = process.execPath
const CWD = '/tmp/memex-tool-ws'
const SESSION = 'claude-tool-loop'
const WORKSPACE = memoryWorkspaceKey(CWD, SESSION)
const ROOT = mkdtempSync(join(tmpdir(), 'memex-tool-loop-'))
const tools = [
  {
    type: 'function',
    function: {
      name: 'memory_search',
      description: 'Search archived context pages (ids/titles/useWhen; not full bodies).',
      parameters: { type: 'object', properties: { query: { type: 'string' }, limit: { type: 'integer' } }, required: ['query'] },
    },
  },
  {
    type: 'function',
    function: {
      name: 'memory_open',
      description: 'Read one context page by id (full body).',
      parameters: { type: 'object', properties: { id: { type: 'string' } }, required: ['id'] },
    },
  },
]

const mcpCall = (tool, args) => {
  const messages = [
    { jsonrpc: '2.0', id: 1, method: 'initialize', params: {} },
    { jsonrpc: '2.0', id: 2, method: 'tools/call', params: { name: tool, arguments: args } },
  ]
  const result = spawnSync(NODE, ['--import', REGISTER, MCP_SERVER, '--root', ROOT, '--agent', 'claude-tool-loop', '--model', MODEL, '--levels', 'l3', '--cwd', CWD, '--session', SESSION], { input: messages.map((m) => JSON.stringify(m)).join('\n') + '\n', encoding: 'utf8', timeout: 60_000 })
  if (result.status !== 0) return `MCP error: ${String(result.stderr).slice(-500)}`
  const replies = String(result.stdout).trim().split('\n').filter(Boolean).map((line) => JSON.parse(line))
  const reply = replies.find((item) => item.id === 2)
  if (reply?.error !== undefined) return `MCP error: ${JSON.stringify(reply.error)}`
  return reply?.result?.content?.[0]?.text ?? JSON.stringify(reply?.result ?? {})
}
const callClaude = async (messages) => {
  let lastError
  for (let attempt = 1; attempt <= 3; attempt += 1) {
    try {
      const response = await fetch(`${BASE_URL}/chat/completions`, {
        method: 'POST',
        headers: { 'content-type': 'application/json', authorization: `Bearer ${KEY}` },
        body: JSON.stringify({ model: MODEL, messages, tools, tool_choice: 'auto', max_tokens: 600, temperature: 0 }),
        signal: AbortSignal.timeout(120_000),
      })
      const data = await response.json()
      if (!response.ok) throw new Error(`HTTP ${response.status}: ${data?.error?.message ?? JSON.stringify(data).slice(0, 300)}`)
      return { message: data.choices?.[0]?.message ?? {}, usage: data.usage ?? null }
    } catch (error) {
      lastError = error
      if (attempt < 3) await new Promise((resolveDelay) => setTimeout(resolveDelay, attempt * 1500))
    }
  }
  throw lastError
}
const extractFact = (text) => {
  const match = String(text ?? '').match(/FACT-[A-Z0-9-]+/i)
  return match === null ? undefined : match[0].toUpperCase()
}
const systemPrompt = 'You are a coding agent with a persistent extra-context layer. You may call memory_search to find archived context pages and memory_open to page a record body into context. Use the tools when the recent context is insufficient. When you have the value, answer with the exact FACT id only (for example FACT-ABC-123). If the value is not available, answer UNKNOWN. Never guess or invent a FACT id.'
const userPrompt = (tail, question) => `Recent context:\n${tail}\n\nQuestion: ${question}\n\nAnswer with the exact FACT id once you have it.`

// Fixture: cold body-only decisions with generic cards, plus a recent work-log tail.
const store = new LocalStoreCore({ root: ROOT, capacityTokens: 1_000_000_000, sessionCapacityTokens: 100_000_000, defaultLevels: { l2: false, l3: false } })
const decisions = [
  { topic: 'billing retry policy', fact: 'FACT-BILL-OK', question: 'what did we decide about the billing retry policy?' },
  { topic: 'auth token rotation', fact: 'FACT-AUTH-30D', question: 'what did we decide about auth token rotation schedule?' },
  { topic: 'cache eviction policy', fact: 'FACT-CACHE-LRU', question: 'which way did we go on the cache eviction policy?' },
]
const tailLines = []
for (let index = 0; index < 80; index += 1) {
  const decision = index >= 20 && index < 20 + decisions.length ? decisions[index - 20] : undefined
  const title = decision === undefined ? `work note ${index}` : `decision record ${index}`
  const summary = decision === undefined ? `weekly log ${index}` : 'decision record'
  const body = decision === undefined ? `Routine weekly note ${index}.` : `The ${decision.topic} decision is ${decision.fact}; keep it. `
  store.write({ kind: 'episode', title, summary, useWhen: 'read when continuing work', body, workspaceKey: WORKSPACE, scope: 'workspace', tokens: 30 })
  if (index >= 70) tailLines.push(`work note ${index}\nweekly log ${index}`)
}
const rows = store.database().prepare('SELECT id FROM records ORDER BY created_at ASC, id ASC').all()
for (const row of rows.slice(0, rows.length - 20)) store.archiveCold(row.id)
store.close()
const tail = tailLines.join('\n')
const report = { format: 1, kind: 'live-ab-claude-tool-loop-result', generatedAt: new Date().toISOString(), provider: 'apimaster', baseUrl: BASE_URL, model: MODEL, method: 'native OpenAI-style tool_calls against the real memex MCP server; control has no tools', usage: { promptTokens: 0, completionTokens: 0, totalTokens: 0, calls: 0 }, probes: [], caveats: ['Synthetic fixture; tool results are from the real MCP server; one model/one run.', 'Usage from gateway response.'] }
try {
  for (const [index, decision] of decisions.entries()) {
    const controlCall = await callClaude([{ role: 'system', content: systemPrompt.replace('You may call memory_search to find archived context pages and memory_open to page a record body into context. Use the tools when the recent context is insufficient. ', 'No memory tools are available in this run. ') }, { role: 'user', content: userPrompt(tail, decision.question) }])
    const controlAnswer = extractFact(controlCall.message.content) ?? (String(controlCall.message.content ?? '').trim().toUpperCase() === 'UNKNOWN' ? 'UNKNOWN' : String(controlCall.message.content ?? '').trim())
    if (controlCall.usage !== null) { report.usage.calls += 1; report.usage.totalTokens += Number(controlCall.usage.total_tokens ?? 0); report.usage.promptTokens += Number(controlCall.usage.prompt_tokens ?? 0); report.usage.completionTokens += Number(controlCall.usage.completion_tokens ?? 0) }
    const messages = [{ role: 'system', content: systemPrompt }, { role: 'user', content: userPrompt(tail, decision.question) }]
    const steps = []
    let treatmentAnswer = ''
    for (let turn = 1; turn <= 6; turn += 1) {
      const { message, usage } = await callClaude(messages)
      if (usage !== null) { report.usage.calls += 1; report.usage.totalTokens += Number(usage.total_tokens ?? 0); report.usage.promptTokens += Number(usage.prompt_tokens ?? 0); report.usage.completionTokens += Number(usage.completion_tokens ?? 0) }
      messages.push({ role: 'assistant', content: message.content ?? '', ...(message.tool_calls === undefined ? {} : { tool_calls: message.tool_calls }) })
      if (Array.isArray(message.tool_calls) && message.tool_calls.length > 0) {
        for (const call of message.tool_calls) {
          let args = {}
          try { args = JSON.parse(call.function?.arguments ?? '{}') } catch { args = {} }
          const name = call.function?.name
          const result = name === 'memory_search' || name === 'memory_open' ? mcpCall(name, args) : `Unknown tool: ${name}`
          steps.push({ turn, tool: name, arguments: args, resultTail: result.slice(-1200) })
          messages.push({ role: 'tool', tool_call_id: call.id, content: result })
        }
        continue
      }
      treatmentAnswer = String(message.content ?? '').trim()
      treatmentAnswer = extractFact(treatmentAnswer) ?? (treatmentAnswer.toUpperCase() === 'UNKNOWN' ? 'UNKNOWN' : treatmentAnswer)
      break
    }
    report.probes.push({ index, question: decision.question, expected: decision.fact, control: { answer: controlAnswer, correct: controlAnswer === decision.fact }, treatment: { answer: treatmentAnswer, correct: treatmentAnswer === decision.fact, steps, turns: steps.length > 0 ? steps[steps.length - 1].turn + 1 : 1 } })
  }
} finally {
  rmSync(ROOT, { recursive: true, force: true })
}
const summarize = (rows_) => ({ correct: rows_.filter((row) => row.correct).length, n: rows_.length, accuracy: rows_.length === 0 ? 0 : Math.round(rows_.filter((row) => row.correct).length / rows_.length * 10000) / 10000 })
report.aggregate = { control: summarize(report.probes.map((probe) => probe.control)), treatment: summarize(report.probes.map((probe) => probe.treatment)) }
writeFileSync(OUT, JSON.stringify(report, null, 2) + '\n')
console.log(`\nClaude tool loop (${MODEL})`)
console.log(`control:   ${report.aggregate.control.correct}/${report.aggregate.control.n}`)
console.log(`treatment: ${report.aggregate.treatment.correct}/${report.aggregate.treatment.n}`)
console.log(`usage:     total=${report.usage.totalTokens} (${report.usage.calls} calls)`)
console.log(`\nReport: ${OUT}`)
