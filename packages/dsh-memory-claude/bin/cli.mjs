#!/usr/bin/env node
/**
 * Claude Code adapter for dsh-memory.
 *
 *   node bin/cli.mjs init [--project DIR] [--user] [--root DIR] [--model ID] [--levels l2,l3]
 *   node bin/cli.mjs hook <session-start|user-prompt|pre-compact|session-end> [options]   (reads hook JSON on stdin)
 *   node bin/cli.mjs status [options]
 *   node bin/cli.mjs print-manual [--model ID]
 *
 * `init` writes/merges:
 *   .mcp.json                       — dsh-memory MCP server (tools for the agent)
 *   .claude/settings.json           — SessionStart / UserPromptSubmit / PreCompact hooks
 *   CLAUDE.md                       — model-tailored memory manual (marked section)
 *
 * Hooks never break a session: failures are reported on stderr and the exit
 * code stays 0. stdout carries the hook JSON only.
 */
import { existsSync, mkdirSync, readFileSync, writeFileSync, copyFileSync } from 'node:fs'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { AgentMemory, defaultMemoryRoot } from '@qiuxu/dsh-memory-core/engine'
import { buildCatalogInjection, buildMemoryManual, buildRecallInjection, buildReceipt } from '@qiuxu/dsh-memory-core/manual'
import { resolveModelProfile } from '@qiuxu/dsh-memory-core/model-profiles'

const HERE = dirname(fileURLToPath(import.meta.url))
const CLAUDE_PKG = resolve(HERE, '..')
const REPO_PACKAGES = resolve(CLAUDE_PKG, '..')
const MCP_SERVER = process.env.DSH_MEMORY_MCP_SERVER ?? resolve(REPO_PACKAGES, 'dsh-memory-mcp', 'bin', 'server.mjs')
const VERSION = '0.2.0'

function parseArgs(argv) {
  const args = { _: [], root: defaultMemoryRoot(), model: process.env.DSH_MEMORY_MODEL ?? 'claude', project: process.cwd(), levels: 'l2,l3', session: undefined, user: false }
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
    return JSON.parse(readFileSync(path, 'utf8'))
  } catch {
    return fallback
  }
}

function writeJson(path, value) {
  mkdirSync(dirname(path), { recursive: true })
  writeFileSync(path, `${JSON.stringify(value, null, 2)}\n`)
}

function hookEntry(command, matcher) {
  return matcher === undefined ? { hooks: [{ type: 'command', command }] } : { matcher, hooks: [{ type: 'command', command }] }
}

/** Replace this adapter's hook entries while keeping user hooks intact. */
function mergeHooks(settings, hookCommandFor, events) {
  settings.hooks = settings.hooks ?? {}
  const marker = 'dsh-memory-claude/bin/cli.mjs'
  for (const [event, matcher] of events) {
    const existing = Array.isArray(settings.hooks[event]) ? settings.hooks[event] : []
    const kept = existing.filter((entry) => !JSON.stringify(entry).includes(marker))
    kept.push(hookEntry(hookCommandFor(event), matcher))
    settings.hooks[event] = kept
  }
  return settings
}

function manualSection(profile, root) {
  const manual = buildMemoryManual(profile, { agent: 'Claude Code', root, levels })
  return `<!-- dsh-memory:start -->\n${manual}\n<!-- dsh-memory:end -->`
}

function init() {
  const projectDir = args.user ? '~' : args.project
  const base = args.user ? resolve(process.env.HOME ?? process.env.USERPROFILE ?? process.cwd()) : args.project
  const profile = resolveModelProfile(args.model)
  const settingsPath = join(base, '.claude', 'settings.json')
  const mcpPath = join(base, '.mcp.json')
  const claudeMdPath = join(base, 'CLAUDE.md')
  const nodeBin = process.execPath
  const hookCommandFor = (event) => `"${nodeBin}" "${resolve(HERE, 'cli.mjs')}" hook ${event} --root "${args.root}" --project "${base}" --model "${args.model}" --levels ${levels.join(',')}`
  // .mcp.json — register the stdio server for this project.
  const mcp = readJson(mcpPath, {})
  mcp.mcpServers = mcp.mcpServers ?? {}
  mcp.mcpServers['dsh-memory'] = {
    command: nodeBin,
    args: [MCP_SERVER, '--root', args.root, '--agent', 'claude-code', '--model', args.model, '--levels', levels.join(','), '--cwd', base],
  }
  writeJson(mcpPath, mcp)
  // .claude/settings.json — hooks.
  const settings = readJson(settingsPath, {})
  mergeHooks(settings, hookCommandFor, [['SessionStart', undefined], ['UserPromptSubmit', undefined], ['PreCompact', 'manual|auto'], ['SessionEnd', undefined]])
  writeJson(settingsPath, settings)
  // CLAUDE.md — model-tailored manual (idempotent section).
  const marker = '<!-- dsh-memory:start -->'
  const existing = existsSync(claudeMdPath) ? readFileSync(claudeMdPath, 'utf8') : ''
  const section = manualSection(profile, args.root)
  let next = existing
  if (existing.includes(marker)) {
    next = existing.replace(/<!-- dsh-memory:start -->[\s\S]*?<!-- dsh-memory:end -->/, section)
  } else {
    next = `${existing.trimEnd()}\n\n${section}\n`
  }
  writeFileSync(claudeMdPath, next.startsWith('\n') ? next.slice(1) : next)
  console.log(`dsh-memory + Claude Code (${profile.id} profile) initialised in ${base}`)
  console.log(`  MCP server:    ${mcpPath} -> ${MCP_SERVER}`)
  console.log(`  Hooks:         ${settingsPath}`)
  console.log(`  Memory manual: ${claudeMdPath}`)
  console.log(`  Memory root:   ${args.root}`)
  console.log('Restart Claude Code in this project to load the MCP server and hooks.')
}

function emitHook(eventName, additionalContext) {
  if (!additionalContext) return
  process.stdout.write(`${JSON.stringify({ hookSpecificOutput: { hookEventName: eventName, additionalContext } })}\n`)
}

async function hook() {
  const event = args._[1] ?? 'session-start'
  let payload = {}
  try {
    const input = readFileSync(0, 'utf8')
    if (input.trim().length > 0) payload = JSON.parse(input)
  } catch {
    payload = {}
  }
  const cwd = payload.cwd ?? args.project
  const session = payload.session_id ?? args.session
  const engine = engineFor(cwd, session)
  try {
    if (event === 'session-start') {
      const index = engine.index()
      const facets = index.facets
      if ((facets.hotCount ?? 0) + (facets.coldCount ?? 0) === 0) return
      emitHook('SessionStart', buildCatalogInjection(engine.profile, index.catalog))
      return
    }
    if (event === 'user-prompt') {
      const prompt = String(payload.prompt ?? '')
      if (prompt.trim().length < 8) return
      const result = engine.search({ query: prompt })
      if (result.hits.length === 0) return
      emitHook('UserPromptSubmit', buildRecallInjection(engine.profile, result.hits))
      return
    }
    if (event === 'pre-compact') {
      const transcriptPath = payload.transcript_path
      if (typeof transcriptPath !== 'string' || !existsSync(transcriptPath)) return
      const raw = readFileSync(transcriptPath, 'utf8')
      const body = raw.length > 8 * 1024 * 1024 ? `${raw.slice(0, 8 * 1024 * 1024)}\n… (transcript clipped at 8MB)` : raw
      const record = engine.write({
        kind: 'episode',
        title: `Claude Code transcript ${String(payload.session_id ?? session ?? '').slice(0, 8)} · ${new Date().toISOString()}`,
        summary: 'Verbatim Claude Code transcript archived before compaction.',
        useWhen: 'read when recovering context that Claude Code compacted or when earlier turns matter',
        body,
        status: 'open',
        tags: { 'claude-code': ['compaction', String(payload.trigger ?? 'auto')] },
      })
      emitHook('PreCompact', buildReceipt(engine.profile, [record.id], 'Claude Code context archived verbatim before compaction'))
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
else if (command === 'hook') await hook()
else if (command === 'status') status()
else if (command === 'print-manual') printManual()
else if (command === undefined || command === 'help' || command === '--help') {
  console.log(`dsh-memory-claude ${VERSION}`)
  console.log('Commands: init | hook <event> | status | print-manual')
  console.log('  init: MCP server + Claude Code hooks + CLAUDE.md manual (use --project DIR or --user)')
}
