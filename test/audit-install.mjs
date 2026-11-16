import assert from 'node:assert/strict'
import { test } from 'node:test'
import fs from 'node:fs'
import { tmpdir } from 'node:os'
import { dirname, join, resolve, basename } from 'node:path'
import { fileURLToPath } from 'node:url'
import { spawn, spawnSync } from 'node:child_process'
import { createInterface } from 'node:readline'

const repo = resolve(dirname(fileURLToPath(import.meta.url)), '..')

function run(command, args, cwd, env) {
  const result = spawnSync(command, args, { cwd, env, encoding: 'utf8', timeout: 20000 })
  assert.equal(result.error, undefined)
  assert.equal(result.status, 0, result.stderr + result.stdout)
  return result.stdout
}

function isolatedEnv(home) {
  fs.mkdirSync(home, { recursive: true })
  // Allowlist rather than inheriting provider keys, NODE_OPTIONS or client homes.
  return { HOME: home, USERPROFILE: home, PATH: process.env.PATH,
    TMPDIR: home, LANG: 'C.UTF-8', npm_config_cache: join(home, 'npm-cache'),
    npm_config_userconfig: join(home, '.npmrc'), npm_config_offline: 'true',
    npm_config_audit: 'false', npm_config_update_notifier: 'false' }
}

function mcp(config, cwd, env) {
  assert.equal(config.command, process.execPath)
  assert.ok(config.args.every(arg => !arg.includes('test/register.mjs')))
  const child = spawn(config.command, config.args, { cwd, env, stdio: ['pipe', 'pipe', 'pipe'] })
  const pending = new Map()
  let sequence = 0, stderr = ''
  child.stderr.on('data', data => { stderr += data })
  const lines = createInterface({ input: child.stdout })
  lines.on('line', line => {
    try {
      const value = JSON.parse(line), waiter = pending.get(value.id)
      if (waiter) { pending.delete(value.id); clearTimeout(waiter.timer); waiter.resolve(value) }
    } catch (error) {
      for (const waiter of pending.values()) { clearTimeout(waiter.timer); waiter.reject(error) }
      pending.clear()
    }
  })
  child.on('exit', code => {
    for (const waiter of pending.values()) { clearTimeout(waiter.timer); waiter.reject(new Error(`MCP exited ${code}: ${stderr}`)) }
    pending.clear()
  })
  const exited = new Promise(resolve => child.once('exit', resolve))
  return {
    async request(method, params = {}) {
      const id = ++sequence
      const response = await new Promise((resolve, reject) => {
        const timer = setTimeout(() => { pending.delete(id); reject(new Error(`MCP timeout: ${method}: ${stderr}`)) }, 10000)
        pending.set(id, { resolve, reject, timer })
        child.stdin.write(JSON.stringify({ jsonrpc: '2.0', id, method, params }) + '\n')
      })
      assert.equal(response.error, undefined, JSON.stringify(response.error))
      return response.result
    },
    notify(method) { child.stdin.write(JSON.stringify({ jsonrpc: '2.0', method }) + '\n') },
    async close() {
      child.stdin.end()
      const timer = setTimeout(() => child.kill('SIGKILL'), 10000)
      try { assert.equal(await exited, 0, stderr) } finally { clearTimeout(timer); lines.close() }
    },
  }
}

async function roundTrip(config, project, env) {
  let client = mcp(config, project, env)
  async function initialize() {
    const result = await client.request('initialize', { protocolVersion: '2024-11-05', capabilities: {}, clientInfo: { name: 'synthetic-install-check', version: '1' } })
    assert.equal(result.serverInfo.name, 'memex')
    client.notify('notifications/initialized')
    const list = await client.request('tools/list')
    for (const name of ['memory_write', 'memory_search', 'memory_open', 'memory_set_status']) assert.ok(list.tools.some(tool => tool.name === name))
  }
  async function call(name, args) {
    const result = await client.request('tools/call', { name, arguments: args })
    assert.notEqual(result.isError, true, JSON.stringify(result))
    return result.content.map(part => part.text ?? '').join('\n')
  }
  let id
  try {
    await initialize()
    const written = await call('memory_write', { kind: 'fact', title: 'INSTALL_ORBIT_7329', body: 'Synthetic durable installation record INSTALL_ORBIT_7329.', scope: 'workspace' })
    id = written.match(/Stored (\S+) /)?.[1]
    assert.ok(id, written)
    assert.match(await call('memory_search', { query: 'INSTALL_ORBIT_7329' }), /INSTALL_ORBIT_7329/)
    assert.match(await call('memory_open', { id }), /Synthetic durable installation record/)
    assert.match(await call('memory_set_status', { id, status: 'resolved' }), /resolved/)
  } finally { await client.close() }
  client = mcp(config, project, env)
  try {
    await initialize()
    assert.match(await call('memory_open', { id }), /Synthetic durable installation record/)
    assert.match(await call('memory_search', { query: 'INSTALL_ORBIT_7329', status: 'resolved' }), /INSTALL_ORBIT_7329/)
  } finally { await client.close() }
}

test('F01: bootstrap a source copy without node_modules; run generated client MCP configurations without a loader', { timeout: 120000 }, async t => {
  const temp = fs.mkdtempSync(join(tmpdir(), 'memex-install-'))
  t.after(() => fs.rmSync(temp, { recursive: true, force: true }))
  const source = join(temp, 'source with spaces')
  fs.mkdirSync(join(source, 'scripts'), { recursive: true })
  fs.copyFileSync(join(repo, 'package.json'), join(source, 'package.json'))
  fs.copyFileSync(join(repo, 'scripts/link-workspace.sh'), join(source, 'scripts/link-workspace.sh'))
  fs.cpSync(join(repo, 'packages'), join(source, 'packages'), { recursive: true,
    filter: path => !['node_modules', 'modules', '.git'].includes(basename(path)) })
  function noInstalledModules(directory) {
    for (const entry of fs.readdirSync(directory, { withFileTypes: true })) {
      assert.notEqual(entry.name, 'node_modules')
      if (entry.isDirectory()) noInstalledModules(join(directory, entry.name))
    }
  }
  noInstalledModules(source)
  const bootstrapEnv = isolatedEnv(join(temp, 'bootstrap-home'))
  run('npm', ['run', 'bootstrap'], source, bootstrapEnv)
  run('npm', ['run', 'bootstrap'], source, bootstrapEnv)
  assert.ok(fs.existsSync(join(source, 'node_modules/@qiuxu/memex-core/package.json')))
  await t.test('generic MCP entry', async () => {
    const project = join(temp, 'generic-project'); fs.mkdirSync(project)
    await roundTrip({ command: process.execPath, args: [join(source, 'packages/memex-mcp/bin/server.mjs'), '--root', join(temp, 'generic-store'), '--levels', 'l3'] }, project, isolatedEnv(join(temp, 'generic-home')))
  })
  for (const adapter of ['claude', 'codex']) await t.test(`${adapter}: init, preserved unrelated settings, config launch and restart`, async () => {
    const home = join(temp, `${adapter}-home`), env = isolatedEnv(home)
    assert.deepEqual(fs.readdirSync(home), [])
    const project = join(temp, `${adapter} project`); fs.mkdirSync(project)
    const cli = join(source, `packages/memex-${adapter}/bin/cli.mjs`)
    const args = ['init', '--project', project, '--root', join(temp, `${adapter}-store`), '--levels', 'l3', ...(adapter === 'codex' ? ['--write-config'] : [])]
    run(process.execPath, [cli, ...args], project, env)
    const manual = join(project, adapter === 'claude' ? 'CLAUDE.md' : 'AGENTS.md')
    fs.writeFileSync(manual, '# Existing project instructions\n' + fs.readFileSync(manual, 'utf8'))
    let config
    if (adapter === 'claude') {
      const path = join(project, '.mcp.json'), value = JSON.parse(fs.readFileSync(path, 'utf8'))
      value.mcpServers.synthetic = { command: 'synthetic-unused', args: [] }; fs.writeFileSync(path, JSON.stringify(value))
      const settings = join(project, '.claude/settings.json'), hooks = JSON.parse(fs.readFileSync(settings, 'utf8'))
      hooks.hooks.Stop.push({ hooks: [{ type: 'command', command: 'echo SYNTHETIC_HOOK' }] }); fs.writeFileSync(settings, JSON.stringify(hooks))
      run(process.execPath, [cli, ...args], project, env)
      const merged = JSON.parse(fs.readFileSync(path, 'utf8'))
      assert.deepEqual(merged.mcpServers.synthetic, value.mcpServers.synthetic)
      assert.match(fs.readFileSync(settings, 'utf8'), /SYNTHETIC_HOOK/)
      config = merged.mcpServers.memex
    } else {
      const path = join(home, '.codex/config.toml')
      const existing = fs.readFileSync(path, 'utf8')
      fs.writeFileSync(path, '# retained\n' + existing + '\n[mcp_servers.synthetic]\ncommand = "synthetic-unused"\n')
      const before = fs.readFileSync(path, 'utf8')
      run(process.execPath, [cli, ...args], project, env)
      assert.equal(fs.readFileSync(path, 'utf8'), before)
      // Parse only this adapter's emitted JSON-compatible TOML fields.
      const section = before.split('[mcp_servers.memex]')[1].split('\n[')[0]
      config = { command: JSON.parse(section.match(/^command = (.+)$/m)[1]), args: JSON.parse(section.match(/^args = (.+)$/m)[1]) }
    }
    const before = fs.readFileSync(manual, 'utf8')
    run(process.execPath, [cli, ...args], project, env)
    assert.equal(fs.readFileSync(manual, 'utf8'), before)
    assert.match(before, /^# Existing project instructions/)
    assert.equal(before.match(/<!-- memex:start -->/g).length, 1)
    await roundTrip(config, project, env)
    assert.equal(typeof JSON.parse(run(process.execPath, [cli, 'status', '--project', project, '--root', join(temp, `${adapter}-store`), '--levels', 'l3'], project, env)), 'object')
  })
})
