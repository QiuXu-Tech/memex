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
import { constants, readFileSync, writeFileSync, copyFileSync, mkdirSync, lstatSync, statSync, realpathSync, renameSync, unlinkSync } from 'node:fs'
import { randomUUID } from 'node:crypto'
import { basename, dirname, join, resolve } from 'node:path'
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

function readExisting(path) {
  let info
  try { info = lstatSync(path) } catch (error) { if (error?.code === 'ENOENT') return ''; throw error }
  if (info.isSymbolicLink()) realpathSync(path)
  return readFileSync(path, 'utf8')
}

function writeAtomic(path, value) {
  mkdirSync(dirname(path), { recursive: true })
  let info
  try { info = lstatSync(path) } catch (error) { if (error?.code !== 'ENOENT') throw error }
  const target = info?.isSymbolicLink() ? realpathSync(path) : path
  const mode = info ? statSync(target).mode & 0o777 : 0o600
  const temporary = join(dirname(target), `.memex-codex-${basename(path)}-${randomUUID()}.tmp`)
  try {
    writeFileSync(temporary, value, { flag: 'wx', mode })
    renameSync(temporary, target)
  } finally {
    try { unlinkSync(temporary) } catch (error) { if (error?.code !== 'ENOENT') throw error }
  }
}

// Conservatively avoid appending to a TOML table that may already define memex.
function hasMemexServer(config) {
  const parent = '(?:mcp_servers|"mcp_servers"|\'mcp_servers\')'
  const key = '(?:memex|"memex"|\'memex\')'
  const table = new RegExp(`^\\s*\\[{1,2}\\s*${parent}\\s*\\.\\s*${key}\\s*(?:\\.|\\])`)
  const dotted = new RegExp(`^\\s*${parent}\\s*\\.\\s*${key}\\s*(?:\\.|=)`)
  const parentTable = new RegExp(`^\\s*\\[\\s*${parent}\\s*\\]\\s*(?:#.*)?$`)
  const parentInline = new RegExp(`^\\s*${parent}\\s*=\\s*\\{`)
  const member = new RegExp(`^\\s*${key}\\s*=`)
  let inParent = false
  for (const line of config.split('\n')) {
    if (/^\s*#/.test(line)) continue
    if (table.test(line) || dotted.test(line) || parentInline.test(line)) return true
    if (/^\s*\[/.test(line)) inParent = parentTable.test(line)
    else if (inParent && member.test(line)) return true
  }
  return false
}

function init() {
  const profile = resolveModelProfile(args.model)
  mkdirSync(args.project, { recursive: true })
  const agentsPath = join(args.project, 'AGENTS.md')
  const existing = readExisting(agentsPath)
  const section = manualSection(profile)
  let next
  const starts = existing.match(/<!-- memex:start -->/g) ?? []
  const ends = existing.match(/<!-- memex:end -->/g) ?? []
  if (starts.length !== ends.length || starts.length > 1 || (starts.length === 1 && !/<!-- memex:start -->[\s\S]*?<!-- memex:end -->/.test(existing))) throw new Error(`${agentsPath}: incomplete or duplicate memex manual markers`)
  if (starts.length === 1) {
    next = existing.replace(/<!-- memex:start -->[\s\S]*?<!-- memex:end -->/, section)
  } else {
    next = existing ? `${existing}${existing.endsWith('\n') ? '' : '\n'}\n${section}\n` : `${section}\n`
  }
  let configMessage
  if (args.writeConfig) {
    mkdirSync(CONFIG_DIR, { recursive: true })
    const current = readExisting(CONFIG_PATH)
    if (!hasMemexServer(current)) {
      const backup = current ? `${CONFIG_PATH}.memex-${randomUUID()}.bak` : undefined
      if (backup) copyFileSync(CONFIG_PATH, backup, constants.COPYFILE_EXCL)
      const prefix = current ? `${current}${current.endsWith('\n') ? '' : '\n'}\n` : ''
      writeAtomic(CONFIG_PATH, `${prefix}${tomlSnippet()}\n`)
      configMessage = `  Config:        ${CONFIG_PATH}${backup ? ` (backup: ${backup})` : ''}`
    } else {
      configMessage = `  Config:        ${CONFIG_PATH} may already define memex; left unchanged.\n  Review the existing entry: a fixed --cwd pins all sessions to that workspace.`
    }
  }
  if (next !== existing) writeAtomic(agentsPath, next)
  if (configMessage) console.log(configMessage)
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
