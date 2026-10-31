#!/usr/bin/env node
/**
 * memex MCP server (stdio, newline-delimited JSON-RPC 2.0).
 *
 * Works with any MCP-capable agent: Claude Code, OpenAI Codex, Gemini CLI,
 * Cursor, Cline, Windsurf, Zed, … It exposes the agent-agnostic memory core as
 * tools, a `memory://catalog` resource and model-tailored instructions.
 *
 *   node bin/server.mjs --root ~/.memex --agent claude-code --model claude-sonnet-4 --levels l2,l3
 *
 * stdout is reserved for protocol messages; diagnostics go to stderr.
 */
import { readFileSync } from 'node:fs'
import { randomUUID } from 'node:crypto'
import { resolve } from 'node:path'
import { AgentMemory, defaultMemoryRoot } from '@qiuxu/memex-core/engine'
import { buildCatalogInjection, buildMemoryManual } from '@qiuxu/memex-core/manual'
import { RECOMMENDED_PROFILES } from '@qiuxu/memex-core/model-profiles'
import { MEMORY_KINDS, MEMORY_STATUSES } from '@qiuxu/memex-core'

const VERSION = JSON.parse(readFileSync(new URL('../package.json', import.meta.url), 'utf8')).version
const PROTOCOL = '2024-11-05'

function parseArgs(argv) {
  const args = { root: defaultMemoryRoot(), levels: undefined, model: '', agent: 'mcp-client', session: undefined, cwd: process.cwd(), capacity: undefined, sessionCapacity: undefined }
  for (let index = 2; index < argv.length; index += 1) {
    const token = argv[index]
    const next = () => argv[++index]
    if (token === '--root') args.root = resolve(next())
    else if (token === '--levels') args.levels = next().split(',').map((level) => level.trim()).filter((level) => level === 'l2' || level === 'l3')
    else if (token === '--model') args.model = next()
    else if (token === '--agent') args.agent = next()
    else if (token === '--session') args.session = next()
    else if (token === '--cwd') args.cwd = resolve(next())
    else if (token === '--capacity') args.capacity = Number(next())
    else if (token === '--session-capacity') args.sessionCapacity = Number(next())
    else if (token === '--list-profiles') {
      process.stderr.write(`${RECOMMENDED_PROFILES.mcp.join('\n')}\n`)
      process.exit(0)
    }
    else if (token === '--help' || token === '-h') {
      process.stderr.write('Usage: memex-mcp [--root DIR] [--levels l2,l3] [--model ID] [--agent NAME] [--session ID] [--cwd DIR]\n')
      process.stderr.write(`Recommended --model values: ${RECOMMENDED_PROFILES.mcp.join(', ')}\n`)
      process.exit(0)
    }
  }
  return args
}

const args = parseArgs(process.argv)
const engine = new AgentMemory({
  root: args.root,
  cwd: args.cwd,
  sessionId: args.session ?? (process.env.MEMEX_SESSION || process.env.DSH_MEMORY_SESSION || `mcp-${randomUUID()}`),
  levels: args.levels,
  model: args.model,
  agent: args.agent,
  capacityTokens: args.capacity,
  sessionCapacityTokens: args.sessionCapacity,
})
const profile = engine.profile

process.stderr.write(`memex MCP server ${VERSION} · profile=${profile.id} · root=${engine.root} · levels=${JSON.stringify(engine.levels)}\n`)

const READ_ONLY_TOOLS = new Set(['memory_search', 'memory_open', 'memory_grep', 'memory_index', 'memory_list'])
const DESTRUCTIVE_TOOLS = new Set(['memory_forget', 'memory_set_status'])
const tool = (name, description, inputSchema) => ({
  name, description, inputSchema,
  annotations: { readOnlyHint: READ_ONLY_TOOLS.has(name), destructiveHint: DESTRUCTIVE_TOOLS.has(name), openWorldHint: false },
})
const TOOLS = [
  tool('memory_search', `Ranked card-level search over archived context (profile: ${profile.label}, top ${profile.maxSearchResults}). Returns ids, titles and "when to read" hints — open the record for the body.`, {
    type: 'object',
    properties: {
      query: { type: 'string', description: 'Natural-language question or concrete identifier/topic.' },
      limit: { type: 'integer', minimum: 1, maximum: 20 },
      kind: { type: 'string', enum: MEMORY_KINDS },
      status: { type: 'string', enum: MEMORY_STATUSES },
    },
    required: ['query'],
  }),
  tool('memory_open', 'Read a record by id. Use offset/limit for lines; when nextCharOffset is returned, continue the same line window with charOffset.', {
    type: 'object',
    properties: {
      id: { type: 'string' },
      offset: { type: 'integer', minimum: 1, description: '1-based first line.' },
      limit: { type: 'integer', minimum: 1, maximum: 400 },
      maxChars: { type: 'integer', minimum: 400, maximum: 240000 },
      charOffset: { type: 'integer', minimum: 0, description: '0-based character offset within the selected line window.' },
    },
    required: ['id'],
  }),
  tool('memory_grep', 'Literal or regex line search across stored record bodies. Useful for identifiers that search ranks late or for cold records.', {
    type: 'object',
    properties: {
      pattern: { type: 'string' },
      limit: { type: 'integer', minimum: 1, maximum: 100 },
      id: { type: 'string', description: 'Restrict the search to one record.' },
    },
    required: ['pattern'],
  }),
  tool('memory_write', 'Persist one durable memory record (decision, fact, procedure, incident, episode, open thread, artifact). Include title, summary, useWhen and the raw evidence in body.', {
    type: 'object',
    additionalProperties: false,
    properties: {
      kind: { type: 'string', enum: MEMORY_KINDS },
      title: { type: 'string' },
      body: { type: 'string' },
      summary: { type: 'string' },
      useWhen: { type: 'string' },
      tags: { type: 'object', additionalProperties: { type: 'array', items: { type: 'string' } } },
      scope: { type: 'string', enum: ['session', 'workspace'] },
      status: { type: 'string', enum: MEMORY_STATUSES },
    },
    required: ['kind', 'title', 'body'],
  }),
  tool('memory_index', 'Show the bounded memory catalog and hot/cold capacity accounting for the visible levels.', {
    type: 'object',
    properties: { maxChars: { type: 'integer', minimum: 400, maximum: 20000 } },
  }),
  tool('memory_list', 'List recent memory cards (hot pool) with optional kind/status filters. Use memory_search for ranked lookup instead.', {
    type: 'object',
    properties: {
      kind: { type: 'string', enum: MEMORY_KINDS },
      status: { type: 'string', enum: MEMORY_STATUSES },
      limit: { type: 'integer', minimum: 1, maximum: 50 },
      sort: { type: 'string', enum: ['newest', 'oldest'] },
    },
  }),
  tool('memory_forget', 'Delete one memory record permanently (hot or cold). Use for obsolete or wrongly captured records; prefer memory_set_status for history you may still need.', {
    type: 'object',
    properties: { id: { type: 'string' } },
    required: ['id'],
  }),
  tool('memory_set_status', 'Update a record lifecycle status (active/open/resolved/superseded/pinned). Pinned records always appear in the catalog.', {
    type: 'object',
    properties: { id: { type: 'string' }, status: { type: 'string', enum: MEMORY_STATUSES } },
    required: ['id', 'status'],
  }),
  tool('memory_restore', 'Move a cold record back into the hot prompt pool (回热).', {
    type: 'object',
    properties: { id: { type: 'string' } },
    required: ['id'],
  }),
  tool('memory_compress', 'Lossless cold-tier compression: move the oldest hot records into the verbatim cold archive to free capacity (no LLM). Ask the user first when the runtime requests consent.', {
    type: 'object',
    properties: {
      level: { type: 'string', enum: ['l2', 'l3'] },
      targetRatio: { type: 'number', minimum: 0.05, maximum: 0.95 },
      minAgeMs: { type: 'integer', minimum: 0, description: 'Minimum record age to cold-move (default 1h).' },
    },
  }),
]

const RESOURCES = [
  { uri: 'memory://catalog', name: 'Memory catalog', description: 'Bounded catalog of archived memory cards for the visible levels.', mimeType: 'text/markdown' },
]

const send = (message) => process.stdout.write(`${JSON.stringify(message)}\n`)
const reply = (id, result) => send({ jsonrpc: '2.0', id, result })
const fail = (id, code, message) => send({ jsonrpc: '2.0', id, error: { code, message } })
const textResult = (text, isError = false) => ({ content: [{ type: 'text', text }], isError })

function callTool(name, input = {}) {
  switch (name) {
    case 'memory_search': {
      if (typeof input.query !== 'string' || input.query.trim().length === 0) throw new Error('memory_search requires a non-empty query')
      const result = engine.search({ query: input.query, limit: input.limit, kind: input.kind, status: input.status })
      const header = result.hits.length === 0 ? 'No matching memory records. Try memory_grep or memory_index.' : `Memory search "${input.query}" (${result.hits.length} hits, +${result.total - result.hits.length} more)`
      const lines = result.hits.map((card, index) => `${index + 1}. ${card.id} · ${card.title} · ${card.useWhen || card.summary || ''}`)
      return textResult(`${header}\n${lines.join('\n')}`)
    }
    case 'memory_open': {
      const record = engine.open({ id: input.id, offset: input.offset, limit: input.limit, maxChars: input.maxChars, charOffset: input.charOffset })
      if (record === undefined) throw new Error(`memory_open: no record ${input.id}`)
      const continuation = record.bodyNextCharOffset === undefined ? '' : ` · nextCharOffset=${record.bodyNextCharOffset}`
      const meta = `# ${record.title} (${record.id})\nkind=${record.kind} · scope=${record.scope} · status=${record.status} · tokens=${record.tokens} · body lines ${record.bodyOffset}-${record.bodyOffset + record.bodyLimit - 1} of ${record.bodyTotalLines}${record.bodyTruncated ? ' (truncated)' : ''}${continuation}\n`
      return textResult(`${meta}\n${record.body}`)
    }
    case 'memory_grep': {
      if (typeof input.pattern !== 'string' || input.pattern.length === 0) throw new Error('memory_grep requires a pattern')
      const result = engine.grep({ pattern: input.pattern, limit: input.limit, id: input.id })
      const lines = result.hits.map((hit) => `${hit.id}:${hit.line}: ${hit.text}`)
      return textResult(lines.length === 0 ? `No lines matching /${input.pattern}/.` : lines.join('\n'))
    }
    case 'memory_write': {
      if (typeof input.title !== 'string' || typeof input.body !== 'string') throw new Error('memory_write requires title and body')
      const allowed = new Set(['kind', 'title', 'body', 'summary', 'useWhen', 'tags', 'scope', 'status'])
      if (Object.keys(input).some((key) => !allowed.has(key))) throw new Error('memory_write received an unsupported field')
      const record = engine.write(input)
      return textResult(`Stored ${record.id} (${record.kind}, scope=${record.scope}, ~${record.tokens} tokens). Path: ${record.path}`)
    }
    case 'memory_index': {
      const result = engine.index({ maxChars: input.maxChars })
      return textResult(buildCatalogInjection(profile, result.catalog))
    }
    case 'memory_list': {
      const cards = engine.list({ kind: input.kind, status: input.status, limit: input.limit, sort: input.sort, includeStatus: true })
      const lines = cards.map((card) => `${card.id} · ${card.kind} · ${card.status} · ${card.title}${card.cold ? ' · cold' : ''}`)
      return textResult(lines.length === 0 ? 'No memory records in the visible levels.' : lines.join('\n'))
    }
    case 'memory_forget': {
      const removed = engine.forget(input.id)
      return textResult(removed ? `Deleted ${input.id}.` : `No record ${input.id}; nothing deleted.`)
    }
    case 'memory_set_status': {
      const record = engine.setStatus(input.id, input.status)
      if (record === undefined) throw new Error(`memory_set_status: no record ${input.id}`)
      return textResult(`Updated ${record.id} status to ${record.status}.`)
    }
    case 'memory_restore': {
      const record = engine.restore(input.id)
      if (record === undefined) throw new Error(`memory_restore: no cold record ${input.id}`)
      return textResult(`Restored ${input.id} to the hot pool (${record.tokens} tokens).`)
    }
    case 'memory_compress': {
      const report = engine.compress({ level: input.level, targetRatio: input.targetRatio, minAgeMs: input.minAgeMs })
      return textResult(`cold-moved ${report.coldMoved.length} records; freed ${report.freedTokens} tokens (hot ${report.before.hot} → target ${report.targetTokens}). Cold records stay searchable/openable by id.`)
    }
    default:
      throw new Error(`unknown tool: ${name}`)
  }
}

const handlers = {
  initialize: (id, params) => reply(id, {
    protocolVersion: PROTOCOL,
    capabilities: { tools: {}, resources: {}, prompts: {} },
    serverInfo: { name: 'memex', version: VERSION },
    instructions: buildMemoryManual(profile, { agent: args.agent, root: engine.root, levels: Object.entries(engine.levels).filter(([, on]) => on).map(([level]) => level) }),
  }),
  'notifications/initialized': () => {},
  'notifications/cancelled': () => {},
  ping: (id) => reply(id, {}),
  'tools/list': (id) => reply(id, { tools: TOOLS }),
  'tools/call': (id, params) => {
    try {
      const result = callTool(params?.name, params?.arguments ?? {})
      reply(id, result)
    } catch (error) {
      reply(id, textResult(`Error: ${error instanceof Error ? error.message : String(error)}`, true))
    }
  },
  'resources/list': (id) => reply(id, { resources: RESOURCES }),
  'resources/read': (id, params) => {
    if (params?.uri === 'memory://catalog') {
      const result = engine.index()
      reply(id, { contents: [{ uri: 'memory://catalog', mimeType: 'text/markdown', text: result.catalog }] })
      return
    }
    fail(id, -32602, `unknown resource: ${params?.uri}`)
  },
  'prompts/list': (id) => reply(id, { prompts: [] }),
}

let buffer = ''
process.stdin.setEncoding('utf8')
process.stdin.on('data', (chunk) => {
  buffer += chunk
  let newline = buffer.indexOf('\n')
  while (newline >= 0) {
    const line = buffer.slice(0, newline).trim()
    buffer = buffer.slice(newline + 1)
    newline = buffer.indexOf('\n')
    if (line.length === 0) continue
    let message
    try {
      message = JSON.parse(line)
    } catch (error) {
      fail(null, -32700, `parse error: ${error instanceof Error ? error.message : String(error)}`)
      continue
    }
    const { id, method, params } = message
    if (method === undefined) continue
    const handler = handlers[method]
    if (handler === undefined) {
      if (id !== undefined) fail(id, -32601, `method not found: ${method}`)
      continue
    }
    try {
      handler(id, params)
    } catch (error) {
      if (id !== undefined) fail(id, -32603, error instanceof Error ? error.message : String(error))
    }
  }
})
process.stdin.on('end', () => {
  // Let buffered stdout flush; the process exits once stdin and the store close.
  engine.close()
})
process.stdout.on('error', (error) => {
  if (error.code === 'EPIPE') process.exit(0)
})
process.on('SIGTERM', () => {
  engine.close()
})
