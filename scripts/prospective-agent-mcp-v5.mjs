#!/usr/bin/env node
// Expose a preassigned pilot worker to an MCP agent without exposing a shell.
import { appendFileSync, readFileSync } from 'node:fs'
import { spawn } from 'node:child_process'
import { createInterface } from 'node:readline'

const separator = process.argv.indexOf('--')
const options = process.argv.slice(2, separator < 0 ? undefined : separator)
const command = separator < 0 ? [] : process.argv.slice(separator + 1)
let archivePath = '', tracePath = '', workerTimeoutMs = 120000
for (let i = 0; i < options.length; i += 1) {
  if (options[i] === '--archive') archivePath = options[++i]
  else if (options[i] === '--trace') tracePath = options[++i]
  else if (options[i] === '--worker-timeout-ms') {
    workerTimeoutMs = Number(options[++i])
    if (!Number.isInteger(workerTimeoutMs) || workerTimeoutMs <= 0 || workerTimeoutMs > 2147483647) throw new Error('Invalid worker timeout')
  }
  else throw new Error(`Unknown option: ${options[i]}`)
}
if (!command.length) throw new Error('A trusted worker command is required after --')
const archive = archivePath ? JSON.parse(readFileSync(archivePath, 'utf8')) : []
if (!Array.isArray(archive) || archive.some((x) => !x || typeof x.id !== 'string' || typeof x.text !== 'string')) {
  throw new Error('Archive must be an array of id/text records')
}
const worker = spawn(command[0], command.slice(1), {
  stdio: ['pipe', 'pipe', 'inherit'],
  env: { HOME: process.env.HOME || '', PATH: process.env.PATH || '/usr/bin:/bin', LANG: 'C.UTF-8' },
})
let pending
let stopped = false
const lines = createInterface({ input: worker.stdout })
lines.on('line', (line) => {
  if (!pending) return
  const current = pending
  pending = undefined
  try { current.resolve(JSON.parse(line)) } catch { current.reject(new Error('Worker returned invalid JSON')) }
})
worker.on('error', (error) => {
  stopped = true
  if (pending) { pending.reject(error); pending = undefined }
})
worker.on('exit', () => {
  stopped = true
  if (pending) { pending.reject(new Error('Worker exited')); pending = undefined }
})
let queue = Promise.resolve()
function workerCall(request) {
  const call = queue.then(() => new Promise((resolve, reject) => {
    if (stopped) { reject(new Error('Worker is unavailable')); return }
    const current = {
      resolve(value) { clearTimeout(timer); resolve(value) },
      reject(error) { clearTimeout(timer); reject(error) },
    }
    const timer = setTimeout(() => {
      if (pending !== current) return
      stopped = true
      pending = undefined
      current.reject(new Error('Worker timed out; outcome unknown; not retried'))
      worker.kill('SIGKILL')
    }, workerTimeoutMs)
    pending = current
    worker.stdin.write(`${JSON.stringify(request)}\n`, (error) => {
      if (error && pending === current) { pending = undefined; current.reject(error) }
    })
  }))
  queue = call.catch(() => {})
  return call
}

const str = { type: 'string' }
const path = { type: 'string', minLength: 1, maxLength: 500 }
const tool = (name, description, properties, required, readOnlyHint) => ({
  name, description, inputSchema: { type: 'object', properties, required, additionalProperties: false },
  annotations: { readOnlyHint, destructiveHint: false, openWorldHint: false },
})
const tools = [
  tool('repo_read', 'Read a line window from an existing repository-relative file; count 1–250. A fully repeated window is summarized; use refresh=true if its text is needed again.', { path, start: { type: 'integer', minimum: 1 }, count: { type: 'integer', minimum: 1, maximum: 250 }, refresh: { type: 'boolean' } }, ['path'], true),
  tool('repo_search', 'Search source files: literal line matches first; otherwise multiword terms may match anywhere in one file or path. Repeated snippets are summarized; set refresh=true to show them again. Limit 1–30.', { query: { type: 'string', minLength: 2, maxLength: 100 }, limit: { type: 'integer', minimum: 1, maximum: 30 }, refresh: { type: 'boolean' } }, ['query'], true),
  tool('repo_edit', 'Replace one exact occurrence in an allowed source file in the isolated repository.', { path, old: { type: 'string', minLength: 1, maxLength: 12000 }, new: { type: 'string', maxLength: 16000 } }, ['path', 'old', 'new'], false),
  tool('repo_test', 'Run the assigned acceptance checks inside the network-disabled test sandbox.', {}, [], true),
  tool('archive_search', 'Search earlier project-history records for relevant evidence.', { query: str }, ['query'], true),
  tool('archive_open', 'Read an earlier project-history record by ID.', { id: str }, ['id'], true),
]
const definitions = new Map(tools.map((x) => [x.name, x]))
const operations = { repo_read: 'read', repo_search: 'search', repo_edit: 'edit', repo_test: 'public_test' }
const readWindows = new Map()
const seenArchiveRecords = new Set()
const seenSearchHits = new Set()
function audit(event) {
  if (tracePath) appendFileSync(tracePath, `${JSON.stringify({ at: new Date().toISOString(), ...event })}\n`, { mode: 0o600 })
}
async function callTool(name, input) {
  const definition = definitions.get(name)
  if (!definition || !input || typeof input !== 'object' || Array.isArray(input)) throw new Error('Invalid tool call')
  const schema = definition.inputSchema
  if (Object.keys(input).some((key) => !(key in schema.properties)) || schema.required.some((key) => !(key in input))) throw new Error('Invalid tool arguments')
  for (const [key, value] of Object.entries(input)) {
    const type = schema.properties[key].type
    if (typeof value !== (type === 'integer' ? 'number' : type) || (type === 'integer' && !Number.isInteger(value))) throw new Error('Invalid tool argument type')
  }
  if (name === 'archive_open') {
    const record = archive.find((x) => x.id === input.id)
    if (record) seenArchiveRecords.add(record.id)
    return record ? { id: record.id, text: record.text } : { error: 'Record not found' }
  }
  if (name === 'archive_search') {
    const terms = input.query.toLowerCase().match(/[a-z0-9_]{3,}|[\u4e00-\u9fff]{2,}/g) || []
    const matches = archive.map((x) => ({ record: x, score: terms.slice(0, 20).filter((t) => x.text.toLowerCase().includes(t)).length }))
      .filter((x) => x.score > 0).sort((a, b) => b.score - a.score).slice(0, 5)
      .map(({ record }) => {
        if (seenArchiveRecords.has(record.id)) return { id: record.id, previouslyReturned: true }
        seenArchiveRecords.add(record.id)
        return { id: record.id, excerpt: record.text.slice(0, 240) }
      })
    return { matches, ...(matches.length && matches.every((x) => x.previouslyReturned) ? { note: 'No new record IDs; open an ID if its full text is needed.' } : {}) }
  }
  if (name === 'repo_read' && !input.refresh) {
    const start = input.start ?? 1, end = start + (input.count ?? 100) - 1
    if ((readWindows.get(input.path) ?? []).some((window) => start >= window.start && start <= window.totalLines && Math.min(end, window.totalLines) <= window.end)) {
      return { path: input.path, start, count: input.count ?? 100, alreadyRead: true, note: 'This window was already supplied in this session. Use refresh=true to receive it again.' }
    }
  }
  const { refresh, ...workerInput } = input
  const response = await workerCall({ op: operations[name], ...workerInput })
  if (!response.ok) throw new Error(response.error || 'Worker rejected request')
  if (name === 'repo_edit') { readWindows.delete(input.path); seenSearchHits.clear() }
  if (name === 'repo_read' && typeof response.result?.text === 'string' && response.result.text.length < 24000 && Number.isInteger(response.result.totalLines)) {
    const start = input.start ?? 1, end = Math.min(response.result.totalLines, start + (input.count ?? 100) - 1)
    if (end >= start) readWindows.set(input.path, [...(readWindows.get(input.path) ?? []), { start, end, totalLines: response.result.totalLines }])
  }
  if (name === 'repo_search' && Array.isArray(response.result?.matches)) {
    const matches = response.result.matches.map((hit) => {
      const key = JSON.stringify(hit)
      const repeated = seenSearchHits.has(key)
      seenSearchHits.add(key)
      return repeated && !refresh ? { path: hit.path, line: hit.line, previouslyReturned: true } : hit
    })
    return { ...response.result, matches, ...(matches.length && matches.every((hit) => hit.previouslyReturned) ? { note: 'All snippets were already supplied; use repo_read or refresh=true if needed.' } : {}) }
  }
  return response.result
}
const send = (message) => process.stdout.write(`${JSON.stringify(message)}\n`)
async function handle(message) {
  const { id, method, params } = message
  if (id === undefined) return
  try {
    if (method === 'initialize') send({ jsonrpc: '2.0', id, result: { protocolVersion: '2024-11-05', capabilities: { tools: {} }, serverInfo: { name: 'prospective-agent', version: '1.0.0' } } })
    else if (method === 'ping') send({ jsonrpc: '2.0', id, result: {} })
    else if (method === 'tools/list') send({ jsonrpc: '2.0', id, result: { tools } })
    else if (method === 'tools/call') {
      const name = params?.name, args = params?.arguments ?? {}
      try {
        const result = await callTool(name, args)
        audit({ name, arguments: args, status: 'ok', result })
        send({ jsonrpc: '2.0', id, result: { content: [{ type: 'text', text: JSON.stringify(result) }], isError: false } })
      } catch (error) {
        const detail = error instanceof Error ? error.message : String(error)
        audit({ name, arguments: args, status: 'error', error: detail })
        send({ jsonrpc: '2.0', id, result: { content: [{ type: 'text', text: detail }], isError: true } })
      }
    } else send({ jsonrpc: '2.0', id, error: { code: -32601, message: `Method not found: ${method}` } })
  } catch (error) { send({ jsonrpc: '2.0', id, error: { code: -32603, message: String(error) } }) }
}
const input = createInterface({ input: process.stdin })
input.on('line', (line) => {
  try { handle(JSON.parse(line)) } catch { send({ jsonrpc: '2.0', id: null, error: { code: -32700, message: 'Invalid JSON' } }) }
})
input.on('close', () => { worker.stdin.end() })
process.stdout.on('error', (error) => { if (error.code === 'EPIPE') process.exit(0) })
