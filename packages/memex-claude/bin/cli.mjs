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
import { existsSync, mkdirSync, readFileSync, writeFileSync, copyFileSync } from 'node:fs'
import { createHash } from 'node:crypto'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { AgentMemory, defaultMemoryRoot } from '@qiuxu/memex-core/engine'
import { MEMORY_TEXT_LIMITS } from '@qiuxu/memex-core'
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
  const marker = 'memex-claude/bin/cli.mjs'
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
  return `<!-- memex:start -->\n${manual}\n<!-- memex:end -->`
}

function init() {
  const projectDir = args.user ? '~' : args.project
  const base = args.user ? resolve(process.env.HOME ?? process.env.USERPROFILE ?? process.cwd()) : args.project
  const profile = resolveModelProfile(args.model)
  const settingsPath = join(base, '.claude', 'settings.json')
  const mcpPath = join(base, '.mcp.json')
  const claudeMdPath = join(base, 'CLAUDE.md')
  const nodeBin = process.execPath
  const hookCommandFor = (event) => `"${nodeBin}" "${resolve(HERE, 'cli.mjs')}" hook ${event} --root "${args.root}" --project "${base}" --model "${args.model}" --levels ${levels.join(',')}${args.session ? ` --session "${args.session}"` : ''}`
  // .mcp.json — register the stdio server for this project.
  const mcp = readJson(mcpPath, {})
  mcp.mcpServers = mcp.mcpServers ?? {}
  mcp.mcpServers['memex'] = {
    command: nodeBin,
    args: [MCP_SERVER, '--root', args.root, '--agent', 'claude-code', '--model', args.model, '--levels', levels.join(','), ...(args.session ? ['--session', args.session] : []), '--cwd', base],
  }
  writeJson(mcpPath, mcp)
  // .claude/settings.json — hooks.
  const settings = readJson(settingsPath, {})
  mergeHooks(settings, hookCommandFor, [['SessionStart', undefined], ['UserPromptSubmit', undefined], ['PreCompact', 'manual|auto'], ['Stop', undefined], ['SessionEnd', undefined]])
  writeJson(settingsPath, settings)
  // CLAUDE.md — model-tailored manual (idempotent section).
  const marker = '<!-- memex:start -->'
  const existing = existsSync(claudeMdPath) ? readFileSync(claudeMdPath, 'utf8') : ''
  const section = manualSection(profile, args.root)
  let next = existing
  if (existing.includes(marker)) {
    next = existing.replace(/<!-- memex:start -->[\s\S]*?<!-- memex:end -->/, section)
  } else {
    next = `${existing.trimEnd()}\n\n${section}\n`
  }
  writeFileSync(claudeMdPath, next.startsWith('\n') ? next.slice(1) : next)
  console.log(`memex + Claude Code (${profile.id} profile) initialised in ${base}`)
  console.log(`  MCP server:    ${mcpPath} -> ${MCP_SERVER}`)
  console.log(`  Hooks:         ${settingsPath}`)
  console.log(`  Memory manual: ${claudeMdPath}`)
  console.log(`  Memory root:   ${args.root}`)
  console.log(`  Model profile: ${profile.id} (${profile.label})`)
  console.log(`  Recommended:   ${RECOMMENDED_PROFILES['claude-code'].join(' · ')}`)
  if (levels.includes('l2') && !args.session) {
    console.log('  Note: hooks use the client session id while MCP tools use default-session.')
    console.log('        Pass --session <stable-project-id> to init so hooks and MCP share one')
    console.log('        L2 namespace, or use --levels l3 for shared project memory.')
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
  const cwd = payload.cwd ?? args.project
  const session = args.session ?? payload.session_id
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
      const recallLimit = engine.profile.maxSearchResults ?? 8
      const result = engine.search({ query: prompt, limit: Math.min(100, Math.max(32, recallLimit * 4)) })
      const hits = result.hits.filter((card) => !(card.provenance?.source === 'claude-stop' && card.provenance?.sourceSession === session)).slice(0, recallLimit)
      if (hits.length === 0) return
      emitHook('UserPromptSubmit', buildRecallInjection(engine.profile, hits))
      return
    }
    if (event === 'pre-compact') {
      const transcriptPath = payload.transcript_path
      if (typeof transcriptPath !== 'string' || !existsSync(transcriptPath)) return
      const raw = readFileSync(transcriptPath, 'utf8')
      // The store accepts at most MEMORY_TEXT_LIMITS.body code units; leave
      // room for the explicit clipping marker so an oversized transcript never
      // fails the hook.
      const marker = '\n… (transcript clipped at the memory body limit)'
      const body = raw.length > MEMORY_TEXT_LIMITS.body - marker.length
        ? `${raw.slice(0, MEMORY_TEXT_LIMITS.body - marker.length)}${marker}`
        : raw
      // Keep a bounded, searchable summary of the transcript head: the raw
      // body is verbatim but only card fields are indexed, so a generic summary
      // would make this archive nearly unsearchable.
      const summaryText = raw.replace(/\s+/g, ' ').trim().slice(0, 900)
      engine.write({
        kind: 'episode',
        title: `Claude Code transcript ${String(payload.session_id ?? session ?? '').slice(0, 8)} · ${new Date().toISOString()}`,
        summary: summaryText,
        useWhen: 'read when recovering context that Claude Code compacted or when earlier turns matter',
        body,
        status: 'open',
        tags: { 'claude-code': ['compaction', String(payload.trigger ?? 'auto')] },
      })
      return
    }
    if (event === 'stop') {
      const answer = typeof payload.last_assistant_message === 'string' ? payload.last_assistant_message.trim() : ''
      if (typeof session !== 'string' || !session || answer.length < 32) return
      if (/^(?:i (?:cannot|can't|am unable to) (?:help|assist)\b|(?:抱歉[，, ]*)?我(?:无法|不能)(?:帮助|协助))/i.test(answer)) return
      // Match the eviction adapter's high-confidence credential patterns before
      // automatically copying assistant output into a potentially shared level.
      const sensitive = /-----BEGIN [A-Z ]*PRIVATE KEY-----/.test(answer) ||
        /\b(?:sk-[A-Za-z0-9]{16,}|ghp_[A-Za-z0-9]{20,}|AKIA[A-Z0-9]{16})\b/.test(answer) ||
        /(?:password|passwd|secret|api[_-]?key|access[_-]?token|authorization)\s*[:=]\s*["']?[^\s"']{6,}/i.test(answer)
      if (sensitive) return
      const marker = '\n… (assistant answer clipped at the memory body limit)'
      let body = answer
      if (answer.length > MEMORY_TEXT_LIMITS.body - marker.length) {
        let prefix = answer.slice(0, MEMORY_TEXT_LIMITS.body - marker.length)
        if (/[\uD800-\uDBFF]$/.test(prefix)) prefix = prefix.slice(0, -1)
        body = `${prefix}${marker}`
      }
      const digest = createHash('sha256').update(`claude-stop\0${engine.workspaceKey}\0${session}\0${body}`).digest('hex')
      const id = `mem_${digest.slice(0, 10)}`
      const existing = engine.store.get(id)
      if (existing !== undefined) {
        if (existing.workspaceKey !== engine.workspaceKey || existing.body !== body || existing.provenance?.sourceSession !== session) {
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
        provenance: { source: 'claude-stop', sourceSession: session },
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
