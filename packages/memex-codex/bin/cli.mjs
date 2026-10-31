#!/usr/bin/env node
/**
 * OpenAI Codex adapter for memex.
 *
 * Codex exposes MCP servers through `~/.codex/config.toml`
 * (`[mcp_servers.<name>] command/args`) and project instructions through
 * AGENTS.md; it has no hook surface, so the manual tells the agent when to
 * search/open/write memory.
 *
 *   node bin/cli.mjs init [--project DIR] [--root DIR] [--model ID] [--levels l2,l3] [--write-config]
 *   node bin/cli.mjs config [--root DIR] [--model ID]
 *   node bin/cli.mjs status [--project DIR]
 */
import { existsSync, readFileSync, writeFileSync, copyFileSync, mkdirSync } from 'node:fs'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { homedir } from 'node:os'
import { AgentMemory, defaultMemoryRoot } from '@qiuxu/memex-core/engine'
import { buildMemoryManual } from '@qiuxu/memex-core/manual'
import { RECOMMENDED_PROFILES, resolveModelProfile } from '@qiuxu/memex-core/model-profiles'

const HERE = dirname(fileURLToPath(import.meta.url))
const REPO_PACKAGES = resolve(HERE, '..', '..')
const MCP_SERVER = process.env.MEMEX_MCP_SERVER ?? process.env.DSH_MEMORY_MCP_SERVER ?? resolve(REPO_PACKAGES, 'memex-mcp', 'bin', 'server.mjs')
const VERSION = JSON.parse(readFileSync(new URL('../package.json', import.meta.url), 'utf8')).version

function parseArgs(argv) {
  const args = { _: [], root: defaultMemoryRoot(), model: process.env.MEMEX_MODEL ?? process.env.DSH_MEMORY_MODEL ?? 'gpt-6.1-sol', project: process.cwd(), levels: 'l3', writeConfig: false }
  for (let index = 0; index < argv.length; index += 1) {
    const token = argv[index]
    const next = () => argv[++index]
    if (token === '--root') args.root = resolve(next())
    else if (token === '--model') args.model = next()
    else if (token === '--project') args.project = resolve(next())
    else if (token === '--levels') args.levels = next()
    else if (token === '--write-config') args.writeConfig = true
    else if (token.startsWith('-')) continue
    else args._.push(token)
  }
  return args
}

const args = parseArgs(process.argv.slice(2))
const command = args._[0]
const levels = args.levels.split(',').map((level) => level.trim()).filter((level) => level === 'l2' || level === 'l3')

function tomlSnippet() {
  return `[mcp_servers.memex]
command = ${JSON.stringify(process.execPath)}
args = [${[MCP_SERVER, '--root', args.root, '--agent', 'codex', '--model', args.model, '--levels', levels.join(',')].map((value) => JSON.stringify(value)).join(', ')}]`
}

const CONFIG_DIR = process.env.CODEX_HOME !== undefined && process.env.CODEX_HOME.length > 0 ? resolve(process.env.CODEX_HOME) : join(homedir(), '.codex')
const CONFIG_PATH = join(CONFIG_DIR, 'config.toml')

function manualSection(profile) {
  const manual = buildMemoryManual(profile, { agent: 'OpenAI Codex', root: args.root, levels })
  return `<!-- memex:start -->
${manual}
<!-- memex:end -->`
}

function init() {
  const profile = resolveModelProfile(args.model)
  mkdirSync(args.project, { recursive: true })
  const agentsPath = join(args.project, 'AGENTS.md')
  const existing = existsSync(agentsPath) ? readFileSync(agentsPath, 'utf8') : ''
  const section = manualSection(profile)
  let next
  if (existing.includes('<!-- memex:start -->')) {
    next = existing.replace(/<!-- memex:start -->[\s\S]*?<!-- memex:end -->/, section)
  } else {
    next = `${existing.trimEnd()}${existing.length > 0 ? '\n\n' : ''}${section}\n`
  }
  writeFileSync(agentsPath, next)
  if (args.writeConfig) {
    mkdirSync(CONFIG_DIR, { recursive: true })
    const current = existsSync(CONFIG_PATH) ? readFileSync(CONFIG_PATH, 'utf8') : ''
    if (!current.includes('[mcp_servers.memex]')) {
      if (current.length > 0) copyFileSync(CONFIG_PATH, `${CONFIG_PATH}.bak`)
      writeFileSync(CONFIG_PATH, `${current.trimEnd()}${current.length > 0 ? '\n\n' : ''}${tomlSnippet()}\n`)
      console.log(`  Config:        ${CONFIG_PATH} (backup: ${CONFIG_PATH}.bak)`)
    } else {
      console.log(`  Config:        ${CONFIG_PATH} already has [mcp_servers.memex]`)
      console.log('  Review the existing entry: a fixed --cwd pins all sessions to that workspace.')
    }
  }
  console.log(`memex + Codex (${profile.id} profile) initialised in ${args.project}`)
  console.log(`  AGENTS.md:     ${agentsPath}`)
  console.log(`  Memory root:   ${args.root}`)
  console.log(`  Model profile: ${profile.id} (${profile.label})`)
  console.log(`  Recommended:   ${RECOMMENDED_PROFILES.codex.join(' · ')}`)
  console.log('')
  console.log('Register the MCP server once (or re-run with --write-config):')
  console.log(`  codex mcp add memex -- ${JSON.stringify(process.execPath)} ${JSON.stringify(MCP_SERVER)} --root ${JSON.stringify(args.root)} --agent codex --model ${JSON.stringify(args.model)} --levels ${levels.join(',')}`)
  console.log('')
  console.log('Equivalent ~/.codex/config.toml entry:')
  console.log(tomlSnippet())
}

function config() {
  console.log(tomlSnippet())
}

function status() {
  const engine = new AgentMemory({ root: args.root, cwd: args.project, levels, model: args.model, agent: 'codex' })
  try {
    console.log(JSON.stringify(engine.stats(), null, 2))
  } finally {
    engine.close()
  }
}

if (command === 'init') init()
else if (command === 'config') config()
else if (command === 'status') status()
else {
  console.log(`memex-codex ${VERSION}`)
  console.log('Commands: init | config | status')
  console.log(`Recommended --model values: ${RECOMMENDED_PROFILES.codex.join(', ')}`)
}
