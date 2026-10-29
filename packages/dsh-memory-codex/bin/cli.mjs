#!/usr/bin/env node
/**
 * OpenAI Codex adapter for dsh-memory.
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
import { AgentMemory, defaultMemoryRoot } from '@qiuxu/dsh-memory-core/engine'
import { buildMemoryManual } from '@qiuxu/dsh-memory-core/manual'
import { resolveModelProfile } from '@qiuxu/dsh-memory-core/model-profiles'

const HERE = dirname(fileURLToPath(import.meta.url))
const REPO_PACKAGES = resolve(HERE, '..', '..')
const MCP_SERVER = process.env.DSH_MEMORY_MCP_SERVER ?? resolve(REPO_PACKAGES, 'dsh-memory-mcp', 'bin', 'server.mjs')
const VERSION = '0.2.0'

function parseArgs(argv) {
  const args = { _: [], root: defaultMemoryRoot(), model: process.env.DSH_MEMORY_MODEL ?? 'gpt-5-codex', project: process.cwd(), levels: 'l3', writeConfig: false }
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
  return `[mcp_servers.dsh-memory]
command = ${JSON.stringify(process.execPath)}
args = [${[MCP_SERVER, '--root', args.root, '--agent', 'codex', '--model', args.model, '--levels', levels.join(','), '--cwd', args.project].map((value) => JSON.stringify(value)).join(', ')}]`
}

const CONFIG_PATH = join(homedir(), '.codex', 'config.toml')

function manualSection(profile) {
  const manual = buildMemoryManual(profile, { agent: 'OpenAI Codex', root: args.root, levels })
  return `<!-- dsh-memory:start -->
${manual}
<!-- dsh-memory:end -->`
}

function init() {
  const profile = resolveModelProfile(args.model)
  const agentsPath = join(args.project, 'AGENTS.md')
  const existing = existsSync(agentsPath) ? readFileSync(agentsPath, 'utf8') : ''
  const section = manualSection(profile)
  let next
  if (existing.includes('<!-- dsh-memory:start -->')) {
    next = existing.replace(/<!-- dsh-memory:start -->[\s\S]*?<!-- dsh-memory:end -->/, section)
  } else {
    next = `${existing.trimEnd()}${existing.length > 0 ? '\n\n' : ''}${section}\n`
  }
  writeFileSync(agentsPath, next)
  if (args.writeConfig) {
    mkdirSync(dirname(CONFIG_PATH), { recursive: true })
    const current = existsSync(CONFIG_PATH) ? readFileSync(CONFIG_PATH, 'utf8') : ''
    if (!current.includes('[mcp_servers.dsh-memory]')) {
      if (current.length > 0) copyFileSync(CONFIG_PATH, `${CONFIG_PATH}.bak`)
      writeFileSync(CONFIG_PATH, `${current.trimEnd()}${current.length > 0 ? '\n\n' : ''}${tomlSnippet()}\n`)
      console.log(`  Config:        ${CONFIG_PATH} (backup: ${CONFIG_PATH}.bak)`)
    } else {
      console.log(`  Config:        ${CONFIG_PATH} already has [mcp_servers.dsh-memory]`)
    }
  }
  console.log(`dsh-memory + Codex (${profile.id} profile) initialised in ${args.project}`)
  console.log(`  AGENTS.md:     ${agentsPath}`)
  console.log(`  Memory root:   ${args.root}`)
  console.log('')
  console.log('Register the MCP server once (or re-run with --write-config):')
  console.log(`  codex mcp add dsh-memory -- ${JSON.stringify(process.execPath)} ${JSON.stringify(MCP_SERVER)} --root ${JSON.stringify(args.root)} --agent codex --model ${JSON.stringify(args.model)} --levels ${levels.join(',')}`)
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
  console.log(`dsh-memory-codex ${VERSION}`)
  console.log('Commands: init | config | status')
}
