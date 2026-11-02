#!/usr/bin/env node
/**
 * Claude Code adapter for memex.
 *
 *   node bin/cli.mjs init [--project DIR] [--user] [--root DIR] [--model ID] [--levels l2,l3]
 *   node bin/cli.mjs hook <session-start|user-prompt|pre-compact|session-end> [options]   (reads hook JSON on stdin)
 *   node bin/cli.mjs status [options]
 *   node bin/cli.mjs print-manual [--model ID]
 *
 * `init` writes/merges:
 *   .mcp.json                       — memex MCP server (tools for the agent)
 *   .claude/settings.json           — SessionStart / UserPromptSubmit / PreCompact hooks
 *   CLAUDE.md                       — model-tailored memory manual (marked section)
 *
 * Hooks never break a session: failures are reported on stderr and the exit
 * code stays 0. stdout carries the hook JSON only.
 */
import { existsSync, mkdirSync, readFileSync, writeFileSync, copyFileSync, lstatSync, statSync, realpathSync, renameSync, unlinkSync } from 'node:fs'
import { createHash, randomUUID } from 'node:crypto'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { AgentMemory, defaultMemoryRoot } from '@qiuxu/memex-core/engine'
import { MEMORY_TEXT_LIMITS, containsSensitive } from '@qiuxu/memex-core'
import { buildCatalogInjection, buildMemoryManual, buildRecallInjection } from '@qiuxu/memex-core/manual'
import { RECOMMENDED_PROFILES, resolveModelProfile } from '@qiuxu/memex-core/model-profiles'

const HERE = dirname(fileURLToPath(import.meta.url))
const CLAUDE_PKG = resolve(HERE, '..')
const REPO_PACKAGES = resolve(CLAUDE_PKG, '..')
const MCP_SERVER = process.env.MEMEX_MCP_SERVER ?? process.env.DSH_MEMORY_MCP_SERVER ?? resolve(REPO_PACKAGES, 'memex-mcp', 'bin', 'server.mjs')
const VERSION = JSON.parse(readFileSync(new URL('../package.json', import.meta.url), 'utf8')).version

function parseArgs(argv) {
  const args = { _: [], root: defaultMemoryRoot(), model: process.env.MEMEX_MODEL ?? process.env.DSH_MEMORY_MODEL ?? 'claude-sonnet-5-5', project: process.cwd(), levels: 'l2,l3', session: undefined, user: false }
  for (let index = 0; index < argv.length; index += 1) {
    const token = argv[index]
    const next = () => argv[++index]
    if (token === '--root') args.root = resolve(next())
    else if (token === '--model') args.model = next()
    else if (token === '--project') args.project = resolve(next())
    else if (token === '--levels') args.levels = next()
    else if (token === '--session') args.session = next()
    else if (token === '--user') args.user = true
    else if (token.startsWith('-')) continue
    else args._.push(token)
  }
  return args
}

const args = parseArgs(process.argv.slice(2))
const command = args._[0]
const levels = args.levels.split(',').map((level) => level.trim()).filter((level) => level === 'l2' || level === 'l3')

function engineFor(cwd, session) {
  return new AgentMemory({ root: args.root, cwd: cwd ?? args.project, sessionId: session ?? args.session, levels, model: args.model, agent: 'claude-code' })
}

function readJson(path, fallback) {
  try {
    const value = JSON.parse(readFileSync(path, 'utf8'))
    if (value === null || typeof value !== 'object' || Array.isArray(value)) throw new Error('expected a JSON object')
    return value
  } catch (error) {
    if (error?.code === 'ENOENT') return fallback
    throw new Error(`cannot read configuration ${path}: ${error.message}`)
  }
}

function writeAtomic(path, value) {
  mkdirSync(dirname(path), { recursive: true })
  let info
  let mode = 0o600
  try {
    info = lstatSync(path)
  } catch (error) {
    if (error?.code !== 'ENOENT') throw error
  }
  const target = info?.isSymbolicLink() ? realpathSync(path) : path
  if (info) mode = statSync(target).mode & 0o777
  const temporary = join(dirname(target), `.memex-init-${randomUUID()}.tmp`)
  try {
    writeFileSync(temporary, value, { flag: 'wx', mode })
    renameSync(temporary, target)
  } finally {
    try { unlinkSync(temporary) } catch (error) { if (error?.code !== 'ENOENT') throw error }
  }
}

function writeJson(path, value) {
  writeAtomic(path, `${JSON.stringify(value, null, 2)}\n`)
}

function hookEntry(command, matcher) {
  return matcher === undefined ? { hooks: [{ type: 'command', command }] } : { matcher, hooks: [{ type: 'command', command }] }
}

function shellQuote(value) {
  return `'${String(value).replace(/'/g, `'\\''`)}'`
}

/** Replace this adapter's hook entries while keeping user hooks intact. */
function mergeHooks(settings, hookCommandFor, events) {
  settings.hooks = settings.hooks ?? {}
  const marker = 'memex-claude/bin/cli.mjs'
  for (const [event, matcher] of events) {
    if (settings.hooks[event] !== undefined && !Array.isArray(settings.hooks[event])) throw new Error(`hooks.${event} must be an array`)
    const existing = Array.isArray(settings.hooks[event]) ? settings.hooks[event] : []
    const kept = existing.flatMap((entry) => {
      if (!Array.isArray(entry?.hooks)) return [entry]
      const hooks = entry.hooks.filter((hook) => typeof hook?.command !== 'string' || !hook.command.includes(marker))
      return hooks.length > 0 ? [{ ...entry, hooks }] : []
    })
    kept.push(hookEntry(hookCommandFor(event), matcher))
    settings.hooks[event] = kept
  }
  return settings
}

function manualSection(profile, root) {
  const manual = buildMemoryManual(profile, { agent: 'Claude Code', root, levels })
  return `<!-- memex:start -->\n${manual}\n<!-- memex:end -->`
}

function init() {
  const projectDir = args.user ? '~' : args.project
  const base = args.user ? resolve(process.env.HOME ?? process.env.USERPROFILE ?? process.cwd()) : args.project
  const profile = resolveModelProfile(args.model)
  const settingsPath = join(base, '.claude', 'settings.json')
  const mcpPath = join(base, args.user ? '.claude.json' : '.mcp.json')
  const claudeMdPath = args.user ? join(base, '.claude', 'CLAUDE.md') : join(base, 'CLAUDE.md')
  const nodeBin = process.execPath
  const hookCommandFor = (event) => `${shellQuote(nodeBin)} ${shellQuote(resolve(HERE, 'cli.mjs'))} hook ${event} --root ${shellQuote(args.root)} --project ${shellQuote(base)} --model ${shellQuote(args.model)} --levels ${shellQuote(levels.join(','))}${args.session ? ` --session ${shellQuote(args.session)}` : ''}${args.user ? ' --user' : ''}`
  // .mcp.json — register the stdio server for this project.
  const mcp = readJson(mcpPath, {})
  const settings = readJson(settingsPath, {})
  if (mcp.mcpServers !== undefined && (mcp.mcpServers === null || typeof mcp.mcpServers !== 'object' || Array.isArray(mcp.mcpServers))) throw new Error(`${mcpPath}: mcpServers must be an object`)
  if (settings.hooks !== undefined && (settings.hooks === null || typeof settings.hooks !== 'object' || Array.isArray(settings.hooks))) throw new Error(`${settingsPath}: hooks must be an object`)
  mcp.mcpServers = mcp.mcpServers ?? {}
  const previous = mcp.mcpServers.memex
  if (previous !== undefined && !Array.isArray(previous?.args)) throw new Error(`${mcpPath}: existing memex server is not managed by this adapter`)
  if (previous !== undefined && !previous.args.some((arg) => typeof arg === 'string' && arg.includes('memex-mcp/bin/server.mjs'))) throw new Error(`${mcpPath}: existing memex server is not managed by this adapter`)
  mcp.mcpServers['memex'] = {
    ...previous,
    command: nodeBin,
    args: [MCP_SERVER, '--root', args.root, '--agent', 'claude-code', '--model', args.model, '--levels', levels.join(','), ...(args.session ? ['--session', args.session] : []), ...(args.user ? [] : ['--cwd', base])],
  }
  // .claude/settings.json — hooks.
  mergeHooks(settings, hookCommandFor, [['SessionStart', undefined], ['UserPromptSubmit', undefined], ['PreCompact', 'manual|auto'], ['Stop', undefined], ['SessionEnd', undefined]])
  // CLAUDE.md — model-tailored manual (idempotent section).
  const marker = '<!-- memex:start -->'
  const existing = existsSync(claudeMdPath) ? readFileSync(claudeMdPath, 'utf8') : ''
  const section = manualSection(profile, args.root)
  let next = existing
  if (existing.includes(marker)) {
    if (!/<!-- memex:start -->[\s\S]*?<!-- memex:end -->/.test(existing)) throw new Error(`${claudeMdPath}: incomplete memex manual markers`)
    next = existing.replace(/<!-- memex:start -->[\s\S]*?<!-- memex:end -->/, section)
  } else {
    next = existing ? `${existing}${existing.endsWith('\n') ? '' : '\n'}\n${section}\n` : `${section}\n`
  }
  writeJson(mcpPath, mcp)
  writeJson(settingsPath, settings)
  writeAtomic(claudeMdPath, next)
  console.log(`memex + Claude Code (${profile.id} profile) initialised in ${base}`)
  console.log(`  MCP server:    ${mcpPath} -> ${MCP_SERVER}`)
  console.log(`  Hooks:         ${settingsPath}`)
  console.log(`  Memory manual: ${claudeMdPath}`)
  console.log(`  Memory root:   ${args.root}`)
  console.log(`  Model profile: ${profile.id} (${profile.label})`)
  console.log(`  Recommended:   ${RECOMMENDED_PROFILES['claude-code'].join(' · ')}`)
  if (levels.includes('l2') && !args.session) {
    console.log('  Note: hooks use the client session id; MCP uses a separate session unless --session is provided.')
    console.log('        An explicit --session is a shared namespace; do not reuse it across private sessions.')
  }
  console.log('Next: restart Claude Code in this project; run `claude` once and approve')
  console.log('      the MCP server when prompted, or check with `claude mcp list`.')
}

function emitHook(eventName, additionalContext) {
  if (!additionalContext) return
  process.stdout.write(`${JSON.stringify({ hookSpecificOutput: { hookEventName: eventName, additionalContext } })}\n`)
}

async function hook() {
  const eventName = args._[1] ?? 'session-start'
  const event = { SessionStart: 'session-start', UserPromptSubmit: 'user-prompt', PreCompact: 'pre-compact', Stop: 'stop', SessionEnd: 'session-end' }[eventName] ?? eventName
  let payload = {}
  try {
    const input = readFileSync(0, 'utf8')
    if (input.trim().length > 0) payload = JSON.parse(input)
  } catch {
    payload = {}
  }
  const cwd = args.user ? (process.env.CLAUDE_PROJECT_DIR || payload.cwd || process.cwd()) : args.project
  const session = args.session ?? payload.session_id
  // A stable --session selects the storage namespace; the real client session
  // still identifies which automatic checkpoints are already in context.
  const clientSession = payload.session_id || session
  const engine = engineFor(cwd, session)
  try {
    if (event === 'session-start') {
      const facets = engine.store.facets({ workspaceKey: engine.workspaceKey, scopes: engine.scopes, sessionId: engine.sessionId })
      if ((facets.hotCount ?? 0) + (facets.coldCount ?? 0) === 0) return
      // UserPromptSubmit supplies relevant previews; don't inject the same
      // record titles again at the start of every session.
      emitHook('SessionStart', buildCatalogInjection(engine.profile, 'Earlier context is available. Relevant previews may be recalled automatically; use memory_search when needed.'))
      return
    }
    if (event === 'user-prompt') {
      const prompt = String(payload.prompt ?? '')
      if (prompt.trim().length < 8) return
      const recallLimit = engine.profile.maxSearchResults ?? 8
      const result = engine.search({ query: prompt, limit: Math.min(100, Math.max(32, recallLimit * 4)) })
      const hits = result.hits.filter((card) => !(card.provenance?.source === 'claude-stop' && card.provenance?.sourceSession === clientSession)).slice(0, recallLimit)
      if (hits.length === 0) return
      emitHook('UserPromptSubmit', buildRecallInjection(engine.profile, hits))
      return
    }
    if (event === 'pre-compact') {
      const transcriptPath = payload.transcript_path
      if (typeof transcriptPath !== 'string' || !existsSync(transcriptPath)) return
      if (!levels.includes('l2') || typeof payload.session_id !== 'string' || !payload.session_id) {
        console.error('memex-claude: transcript archive skipped: a client session id and L2 are required; the source transcript was left in place')
        return
      }
      const raw = new TextDecoder('utf-8', { fatal: true, ignoreBOM: true }).decode(readFileSync(transcriptPath))
      const digest = createHash('sha256').update(raw).digest('hex')
      const parts = []
      for (let start = 0; start < raw.length;) {
        let end = Math.min(start + MEMORY_TEXT_LIMITS.body, raw.length)
        if (end < raw.length && /[\uD800-\uDBFF]/.test(raw[end - 1])) end -= 1
        parts.push(raw.slice(start, end))
        start = end
      }
      if (parts.length === 0) parts.push('')
      const privateEngine = payload.session_id === session ? engine : engineFor(cwd, payload.session_id)
      try {
        for (const [index, body] of parts.entries()) {
          const id = `mem_${createHash('sha256').update(`claude-precompact\0${privateEngine.workspaceKey}\0${payload.session_id}\0${digest}\0${index}`).digest('hex').slice(0, 10)}`
          const existing = privateEngine.store.get(id)
          if (existing !== undefined) {
            if (existing.workspaceKey !== privateEngine.workspaceKey || existing.scope !== 'session' || existing.sessionId !== payload.session_id || existing.body !== body || existing.provenance?.source !== 'claude-precompact') throw new Error('memory: transcript archive id already belongs to a different record')
            continue
          }
          privateEngine.write({
            id, kind: 'episode', scope: 'session', trust: 'untrusted',
            title: `Claude Code transcript ${payload.session_id.slice(0, 8)} · part ${index + 1}/${parts.length}`,
            summary: body.slice(0, 900).replace(/\s+/g, ' ').trim(),
            useWhen: 'read when recovering context that Claude Code compacted or when earlier turns matter',
            body, status: 'open',
            tags: { 'claude-code': ['compaction', String(payload.trigger ?? 'auto')] },
            provenance: { source: 'claude-precompact', sourceSession: payload.session_id, sha256: digest, part: index + 1, parts: parts.length },
          })
        }
      } finally { if (privateEngine !== engine) privateEngine.close() }
      return
    }
    if (event === 'stop') {
      const answer = typeof payload.last_assistant_message === 'string' ? payload.last_assistant_message.trim() : ''
      if (typeof clientSession !== 'string' || !clientSession || answer.length < 32) return
      if (/^(?:i (?:cannot|can't|am unable to) (?:help|assist)\b|(?:抱歉[，, ]*)?我(?:无法|不能)(?:帮助|协助))/i.test(answer)) return
      // Match the eviction adapter's high-confidence credential patterns before
      // automatically copying assistant output into a potentially shared level.
      const sensitive = containsSensitive(answer)
      if (sensitive) return
      const marker = '\n… (assistant answer clipped at the memory body limit)'
      let body = answer
      if (answer.length > MEMORY_TEXT_LIMITS.body - marker.length) {
        let prefix = answer.slice(0, MEMORY_TEXT_LIMITS.body - marker.length)
        if (/[\uD800-\uDBFF]$/.test(prefix)) prefix = prefix.slice(0, -1)
        body = `${prefix}${marker}`
      }
      const digest = createHash('sha256').update(`claude-stop\0${engine.workspaceKey}\0${session}\0${clientSession}\0${body}`).digest('hex')
      const id = `mem_${digest.slice(0, 10)}`
      const existing = engine.store.get(id)
      if (existing !== undefined) {
        if (existing.workspaceKey !== engine.workspaceKey || existing.body !== body || existing.provenance?.sourceSession !== clientSession) {
          throw new Error('memory: automatic checkpoint id already belongs to a different record')
        }
        return
      }
      const firstLine = body.split('\n').find((line) => line.trim())?.replace(/^#+\s*/, '').trim() ?? 'Assistant response'
      engine.write({
        id, kind: 'episode', title: `Claude Code: ${firstLine.slice(0, 120)}`,
        summary: body.replace(/\s+/g, ' ').slice(0, 900),
        useWhen: 'Earlier assistant response; verify decisions against current source and tests.',
        body, trust: 'untrusted', status: 'active',
        provenance: { source: 'claude-stop', sourceSession: clientSession },
      })
      return
    }
    // session-end: nothing to inject; keep the store healthy.
  } finally {
    engine.close()
  }
}

function status() {
  const engine = engineFor(args.project, args.session)
  try {
    console.log(JSON.stringify(engine.stats(), null, 2))
  } finally {
    engine.close()
  }
}

function printManual() {
  console.log(buildMemoryManual(resolveModelProfile(args.model), { agent: 'Claude Code', root: args.root, levels }))
}

if (command === 'init') init()
else if (command === 'hook') {
  try { await hook() } catch (error) { console.error(`memex-claude hook failed: ${error instanceof Error ? error.message : String(error)}`) }
}
else if (command === 'status') status()
else if (command === 'print-manual') printManual()
else if (command === undefined || command === 'help' || command === '--help') {
  console.log(`memex-claude ${VERSION}`)
  console.log('Commands: init | hook <event> | status | print-manual')
  console.log(`Recommended --model values: ${RECOMMENDED_PROFILES['claude-code'].join(', ')}`)
  console.log('  init: MCP server + Claude Code hooks + CLAUDE.md manual (use --project DIR or --user)')
}
