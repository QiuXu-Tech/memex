import test from 'node:test'
import assert from 'node:assert/strict'
import { chmodSync, lstatSync, mkdtempSync, mkdirSync, readFileSync, readdirSync, renameSync, rmSync, statSync, symlinkSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { spawnSync } from 'node:child_process'
import { fileURLToPath } from 'node:url'
import { LocalStoreCore } from '../packages/memex-core/lib/store.js'
import { AgentMemory } from '../packages/memex-core/lib/engine.js'
import { MEMORY_TEXT_LIMITS, archiveRecordId, memoryWorkspaceKey } from '../packages/memex-core/index.js'
import { canonicalEventsFromDsh } from '../packages/memex-core/lib/context-events.js'
import LocalMemoryStore from '../packages/memex-local/index.js'
import * as checkpoint from '../packages/memex-checkpoint/index.js'
import * as toolsRow from '../packages/memex-tool/index.js'
import { createFakeContext, createSessionQueryMock } from './fake-ctx.mjs'
import { createSession, createSurfaceEvents, createCompactionEvent, createPreStepDecision, terminalNext } from './fixtures.mjs'

const register = fileURLToPath(new URL('./register.mjs', import.meta.url))
const cli = fileURLToPath(new URL('../packages/memex-claude/bin/cli.mjs', import.meta.url))
const codexCli = fileURLToPath(new URL('../packages/memex-codex/bin/cli.mjs', import.meta.url))
const mcp = fileURLToPath(new URL('../packages/memex-mcp/bin/server.mjs', import.meta.url))
const initFault = fileURLToPath(new URL('./claude-init-fault.mjs', import.meta.url))
const codexInitFault = fileURLToPath(new URL('./codex-init-fault.mjs', import.meta.url))
const sqlitePermissionFault = fileURLToPath(new URL('./sqlite-permission-fault.mjs', import.meta.url))
const tracePermissionFault = fileURLToPath(new URL('./trace-permission-fault.mjs', import.meta.url))
const root = () => mkdtempSync(join(tmpdir(), 'memex-integrity-test-'))
const node = (args, input = '', env = {}) => spawnSync(process.execPath, ['--import', register, cli, ...args], { input, encoding: 'utf8', timeout: 60000, env: { ...process.env, ...env } })
const codexNode = (args, env = {}) => spawnSync(process.execPath, ['--import', register, codexCli, ...args], { encoding: 'utf8', timeout: 60000, env: { ...process.env, ...env } })
const pause = () => new Promise((resolve) => setTimeout(resolve, 100))
const mcpCall = (dir, project, requests, extra = []) => {
  const result = spawnSync(process.execPath, ['--import', register, mcp, '--root', dir, '--cwd', project, '--session', 'evidence-test', '--levels', 'l3', ...extra],
    { input: requests.map((request) => JSON.stringify(request)).join('\n') + '\n', encoding: 'utf8', timeout: 60000 })
  assert.equal(result.status, 0, result.stderr)
  return result.stdout.trim().split('\n').filter(Boolean).map((line) => JSON.parse(line))
}
const rpc = (id, method, params = {}) => ({ jsonrpc: '2.0', id, method, params })

test('read-only pilot bridge hides and rejects editing and test execution', () => {
  const bridge = fileURLToPath(new URL('../scripts/prospective-agent-mcp-v5.mjs', import.meta.url))
  const requests = [rpc(1, 'tools/list'), rpc(2, 'tools/call', { name: 'repo_edit', arguments: { path: 'x.js', old: 'x', new: 'y' } }), rpc(3, 'tools/call', { name: 'repo_test', arguments: {} })]
  const result = spawnSync(process.execPath, [bridge, '--read-only', '--', process.execPath, '-e', 'process.stdin.resume()'], { input: requests.map(JSON.stringify).join('\n') + '\n', encoding: 'utf8', timeout: 10000 })
  assert.equal(result.status, 0, result.stderr)
  const responses = result.stdout.trim().split('\n').map(JSON.parse)
  assert.deepEqual(responses[0].result.tools.map((tool) => tool.name).sort(), ['archive_open', 'archive_search', 'repo_read', 'repo_search'])
  assert.equal(responses[1].result.isError, true)
  assert.equal(responses[2].result.isError, true)
})

test('MCP defaults to a small memory interface and retains explicit advanced tools', () => {
  const dir = root(), project = '/tmp/memex-interface-regression'
  try {
    const names = (extra = []) => mcpCall(dir, project, [rpc(1, 'tools/list')], extra)[0].result.tools.map((tool) => tool.name).sort()
    assert.deepEqual(names(), ['memory_open', 'memory_search', 'memory_set_status', 'memory_write'])
    assert.ok(names(['--all-tools']).includes('memory_forget'))
    assert.ok(names(['--all-tools']).includes('memory_grep'))
  } finally { rmSync(dir, { recursive: true, force: true }) }
})

test('MCP source, version and validity survive reopen and govern normal recall', () => {
  const dir = root(), project = '/tmp/memex-evidence-regression'
  const evidence = { source: 'src/deploy.json', version: 'commit-abc', observedAt: '2025-01-01T00:00:00Z', validUntil: '2999-01-01T00:00:00Z' }
  try {
    const write = mcpCall(dir, project, [rpc(1, 'tools/call', { name: 'memory_write', arguments: { kind: 'decision', title: 'Sprocket deploy target', summary: 'Sprocket deploy target', body: 'Use staging', evidence } })])[0]
    assert.equal(write.result.isError, false)
    const id = write.result.content[0].text.match(/mem_[a-f0-9]+/)[0]
    const responses = mcpCall(dir, project, [
      rpc(2, 'tools/call', { name: 'memory_search', arguments: { query: 'Sprocket deploy target', source: evidence.source, version: evidence.version } }),
      rpc(3, 'tools/call', { name: 'memory_search', arguments: { query: 'Sprocket deploy target', source: evidence.source, version: 'commit-wrong' } }),
      rpc(4, 'tools/call', { name: 'memory_open', arguments: { id } }),
      rpc(6, 'tools/call', { name: 'memory_set_status', arguments: { id, status: 'superseded' } }),
      rpc(7, 'tools/call', { name: 'memory_search', arguments: { query: 'Sprocket deploy target' } }),
      rpc(8, 'tools/call', { name: 'memory_search', arguments: { query: 'Sprocket deploy target', status: 'superseded' } }),
    ])
    const text = (index) => responses[index].result.content[0].text
    assert.match(text(0), new RegExp(id)); assert.doesNotMatch(text(1), new RegExp(id))
    assert.match(text(0), /src\/deploy\.json/); assert.match(text(0), /commit-abc/)
    assert.match(text(2), /src\/deploy\.json/); assert.match(text(2), /commit-abc/); assert.match(text(2), /2999-01-01/)
    assert.doesNotMatch(text(4), new RegExp(id)); assert.match(text(5), /\[superseded\]/)
    const invalid = mcpCall(dir, project, [rpc(5, 'tools/call', { name: 'memory_write', arguments: { kind: 'fact', title: 'bad expiry', body: 'bad', evidence: { source: 'x', validUntil: '2025-02-30T00:00:00Z' } } })])[0]
    assert.equal(invalid.result.isError, true)
  } finally { rmSync(dir, { recursive: true, force: true }) }
})

test('legacy arbitrary provenance remains visible and can change status', () => {
  const dir = root(), store = new LocalStoreCore({ root: dir })
  try {
    const original = store.write({ id: 'mem_legacy_evidence', kind: 'fact', title: 'Sprocket legacy', body: 'Original body', workspaceKey: 'wk', provenance: { source: 'legacy' } })
    const legacy = { source: 'legacy', evidence: { description: 'Old caller metadata', validUntil: '0' } }
    store.database().prepare('UPDATE records SET provenance_json = ? WHERE id = ?').run(JSON.stringify(legacy), original.id)
    const file = readFileSync(original.path, 'utf8').replace(/^provenance: .*$/m, `provenance: ${JSON.stringify(legacy)}`)
    writeFileSync(original.path, file)
    assert.equal(store.search({ query: 'Sprocket legacy', workspaceKey: 'wk' }).hits[0]?.id, original.id)
    const updated = store.setStatus(original.id, 'resolved', { workspaceKey: 'wk' })
    assert.deepEqual(updated.provenance, legacy)
    store.close()
    const reopened = new LocalStoreCore({ root: dir })
    try {
      const record = reopened.get(original.id)
      assert.deepEqual(record.provenance, legacy); assert.equal(record.body, 'Original body')
      assert.throws(() => reopened.write({ ...record, provenance: { ...legacy, evidence: { ...legacy.evidence, validUntil: '1' } } }), /unsupported field/)
      assert.deepEqual(reopened.get(original.id).provenance, legacy)
    } finally { reopened.close() }
    assert.throws(() => store.write({ kind: 'fact', title: 'invalid', body: '', provenance: { evidence: { source: 'new', validUntil: '0' } } }), /valid UTC ISO/)
  } finally { store.close(); rmSync(dir, { recursive: true, force: true }) }
})

test('expired evidence stays available by id but is excluded from normal search and paging', () => {
  const dir = root(), project = '/tmp/memex-expiry-regression'
  const engine = new AgentMemory({ root: dir, cwd: project, sessionId: 'evidence-test', levels: ['l3'] })
  try {
    const expired = engine.write({ kind: 'decision', title: 'Sprocket expired deploy', summary: 'Sprocket expired deploy', body: 'old deploy', status: 'pinned', provenance: { evidence: { source: 'src/deploy.json', version: 'old', validUntil: '2025-01-01T00:00:00Z' } } })
    assert.equal(engine.search({ query: 'Sprocket expired deploy' }).hits.length, 0)
    assert.equal(engine.search({ query: 'Sprocket expired deploy', includeExpired: true }).hits[0].id, expired.id)
    assert.equal(engine.grep({ pattern: 'old deploy' }).length, 0)
    assert.equal(engine.grep({ pattern: 'old deploy', id: expired.id })[0].id, expired.id)
    assert.equal(engine.open({ id: expired.id }).id, expired.id)
    assert.ok(!engine.materializeContext({ query: 'Sprocket expired deploy', budgetTokens: 1800 }).includedIds.includes(expired.id))
    const replies = mcpCall(dir, project, [
      rpc(1, 'tools/call', { name: 'memory_search', arguments: { query: 'Sprocket expired deploy' } }),
      rpc(2, 'tools/call', { name: 'memory_search', arguments: { query: 'Sprocket expired deploy', includeExpired: true } }),
      rpc(3, 'tools/call', { name: 'memory_open', arguments: { id: expired.id } }),
    ])
    assert.doesNotMatch(replies[0].result.content[0].text, new RegExp(expired.id))
    assert.match(replies[1].result.content[0].text, /validity=expired/)
    assert.match(replies[2].result.content[0].text, /validity=expired/)
    const hook = node(['hook', 'UserPromptSubmit', '--root', dir, '--project', project, '--session', 'evidence-test', '--levels', 'l3'], JSON.stringify({ session_id: 'evidence-test', prompt: 'What is the Sprocket expired deploy?' }))
    assert.equal(hook.status, 0, hook.stderr); assert.doesNotMatch(hook.stdout, new RegExp(expired.id))
  } finally { engine.close(); rmSync(dir, { recursive: true, force: true }) }
})

test('DSH tools persist source metadata and expose it on a later session read', async () => {
  const dir = root(), ctx = createFakeContext()
  const backend = new LocalMemoryStore(ctx, { root: dir, defaultLevels: 'l3' })
  ctx.provideService('memory', backend); toolsRow.apply(ctx, {})
  const first = createSession({ id: 'evidence-dsh-first', cwd: '/tmp/memex-evidence-dsh' })
  const second = createSession({ id: 'evidence-dsh-second', cwd: '/tmp/memex-evidence-dsh' })
  try {
    const saved = await ctx.tool('memory_write').execute({ kind: 'decision', title: 'Sprocket source decision', body: 'use staging', source: 'deploy.yml', source_version: 'rev-123', observed_at: '2025-01-01T00:00:00Z', valid_until: '2999-01-01T00:00:00Z' }, { agent: { session: first } })
    const id = saved.match(/mem_[a-f0-9]+/)[0]
    const opened = await ctx.tool('memory_open').execute({ id }, { agent: { session: second } })
    assert.match(opened, /deploy\.yml/); assert.match(opened, /rev-123/); assert.match(opened, /2999-01-01/)
    const match = await ctx.tool('memory_search').execute({ query: 'Sprocket source decision', source: 'deploy.yml', version: 'rev-123' }, { agent: { session: second } })
    const miss = await ctx.tool('memory_search').execute({ query: 'Sprocket source decision', source: 'deploy.yml', version: 'other' }, { agent: { session: second } })
    assert.match(match, new RegExp(id)); assert.doesNotMatch(miss, new RegExp(id))
    assert.equal((await backend.get(id)).trust, 'untrusted')
  } finally { await ctx.dispose(); rmSync(dir, { recursive: true, force: true }) }
})

test('failed metadata update keeps the old source/version and succeeds after retry', () => {
  const dir = root(), store = new LocalStoreCore({ root: dir })
  try {
    const old = store.write({ id: 'mem_evidence_retry', kind: 'decision', title: 'deploy', body: 'v1', workspaceKey: 'wk', provenance: { evidence: { source: 'deploy.yml', version: 'v1' } } })
    store.database().exec("CREATE TRIGGER injected_evidence_failure BEFORE UPDATE ON records BEGIN SELECT RAISE(ABORT, 'injected evidence failure'); END")
    assert.throws(() => store.write({ ...old, body: 'v2', provenance: { evidence: { source: 'deploy.yml', version: 'v2' } } }), /injected evidence failure/)
    store.close()
    const reopened = new LocalStoreCore({ root: dir })
    try {
      assert.equal(reopened.get(old.id).body, 'v1'); assert.equal(reopened.get(old.id).provenance.evidence.version, 'v1')
      reopened.database().exec('DROP TRIGGER injected_evidence_failure')
      reopened.write({ ...reopened.get(old.id), body: 'v2', provenance: { evidence: { source: 'deploy.yml', version: 'v2' } } })
      assert.equal(reopened.get(old.id).body, 'v2'); assert.equal(reopened.get(old.id).provenance.evidence.version, 'v2')
    } finally { reopened.close() }
  } finally { store.close(); rmSync(dir, { recursive: true, force: true }) }
})

test('superseded memories stay out of default MCP search and Claude auto-recall', () => {
  const dir = root(), project = '/tmp/memex-status-regression'
  const engine = new AgentMemory({ root: dir, cwd: project, sessionId: 'status-test', levels: ['l3'] })
  try {
    const old = engine.write({ kind: 'decision', title: 'Sprocket deployment target', summary: 'Sprocket deployment target', body: 'old target' })
    engine.setStatus(old.id, 'superseded')
    assert.equal(engine.search({ query: 'Sprocket deployment target' }).hits.length, 0)
    assert.equal(engine.search({ query: 'Sprocket deployment target', status: 'superseded' }).hits[0].id, old.id)
    assert.equal(engine.grep({ pattern: 'old target' }).length, 0)
    assert.equal(engine.grep({ pattern: 'old target', id: old.id })[0].status, 'superseded')
    const request = JSON.stringify({ jsonrpc: '2.0', id: 1, method: 'tools/call', params: { name: 'memory_search', arguments: { query: 'Sprocket deployment target' } } }) + '\n'
    const result = spawnSync(process.execPath, ['--import', register, mcp, '--root', dir, '--cwd', project, '--session', 'status-test', '--levels', 'l3'], { input: request, encoding: 'utf8' })
    assert.equal(result.status, 0, result.stderr)
    assert.doesNotMatch(result.stdout, new RegExp(old.id))
    const hook = node(['hook', 'UserPromptSubmit', '--root', dir, '--project', project, '--session', 'status-test', '--levels', 'l3'], JSON.stringify({ session_id: 'status-test', prompt: 'What is the Sprocket deployment target?' }))
    assert.equal(hook.status, 0, hook.stderr)
    assert.doesNotMatch(hook.stdout, new RegExp(old.id))
  } finally { engine.close(); rmSync(dir, { recursive: true, force: true }) }
})

test('materialization trace keeps only metadata and protects an existing file', { skip: process.platform === 'win32' }, async () => {
  const dir = root(), ctx = createFakeContext()
  const trace = join(dir, 'materializer-trace.jsonl')
  chmodSync(dir, 0o755)
  writeFileSync(trace, 'legacy trace preserved\n', { mode: 0o644 }); chmodSync(trace, 0o644)
  const backend = new LocalMemoryStore(ctx, { root: dir })
  try {
    const record = await backend.write({ kind: 'fact', title: 'trace sentinel', body: 'PRIVATE_TRACE_SENTINEL', workspaceKey: 'wk' })
    assert.equal(await backend.recordMaterialization({ sessionId: 's', workspaceKey: 'wk', form: 'materialized-context', text: 'PRIVATE_TRACE_SENTINEL' }), true)
    assert.equal(await backend.forget(record.id), true)
    const text = readFileSync(trace, 'utf8')
    assert.match(text, /^legacy trace preserved\n/)
    assert.doesNotMatch(text, /PRIVATE_TRACE_SENTINEL/)
    assert.equal(statSync(trace).mode & 0o077, 0)
  } finally { await ctx.dispose(); rmSync(dir, { recursive: true, force: true }) }
})

test('opening DSH memory secures a legacy trace before any new injection', { skip: process.platform === 'win32' }, async () => {
  const dir = root(), trace = join(dir, 'materializer-trace.jsonl'), ctx = createFakeContext()
  chmodSync(dir, 0o755); writeFileSync(trace, 'legacy text\n', { mode: 0o644 }); chmodSync(trace, 0o644)
  try {
    new LocalMemoryStore(ctx, { root: dir })
    assert.equal(statSync(trace).mode & 0o077, 0)
    assert.equal(readFileSync(trace, 'utf8'), 'legacy text\n')
  } finally { await ctx.dispose(); rmSync(dir, { recursive: true, force: true }) }
})

test('trace permission failure preserves the old file and a retry writes metadata only', { skip: process.platform === 'win32' }, async () => {
  const dir = root(), trace = join(dir, 'materializer-trace.jsonl')
  writeFileSync(trace, 'old trace\n', { mode: 0o644 }); chmodSync(trace, 0o644)
  try {
    const local = new URL('../packages/memex-local/index.js', import.meta.url).href
    const script = `import LocalMemoryStore from ${JSON.stringify(local)}; try { new LocalMemoryStore({effect(){}}, {root:process.env.MEMEX_TEST_ROOT}); console.log('unexpected') } catch (error) { console.log(error.message) }`
    const child = spawnSync(process.execPath, ['--import', register, '--import', tracePermissionFault, '--input-type=module', '-e', script], { encoding: 'utf8', env: { ...process.env, MEMEX_TEST_ROOT: dir } })
    assert.equal(child.status, 0, child.stderr); assert.match(child.stdout, /injected trace permission failure/)
    assert.equal(readFileSync(trace, 'utf8'), 'old trace\n')
    const ctx = createFakeContext(), backend = new LocalMemoryStore(ctx, { root: dir })
    try {
      assert.equal(await backend.recordMaterialization({ text: 'SENSITIVE_FIXTURE' }), true)
      assert.doesNotMatch(readFileSync(trace, 'utf8'), /SENSITIVE_FIXTURE/)
      assert.equal(statSync(trace).mode & 0o077, 0)
    } finally { await ctx.dispose() }
  } finally { rmSync(dir, { recursive: true, force: true }) }
})

test('configured session-settings TTL is applied when a store reopens', async () => {
  const dir = root(), ctx = createFakeContext()
  const backend = new LocalMemoryStore(ctx, { root: dir, settingsTtlDays: 7 })
  try {
    assert.equal(backend.core.settingsTtlMs, 7 * 86400000)
    const db = backend.core.database()
    const insert = db.prepare("INSERT INTO session_settings (session_id, mode, l2, l3, updated_at) VALUES (?, 'off', 0, 1, ?)")
    insert.run('old', Date.now() - 8 * 86400000); insert.run('recent', Date.now() - 6 * 86400000)
    backend.core.close()
    const reopened = new LocalMemoryStore(ctx, { root: dir, settingsTtlDays: 7 })
    const rows = reopened.core.database().prepare('SELECT session_id FROM session_settings ORDER BY session_id').all()
    assert.deepEqual(rows.map((row) => row.session_id), ['recent'])
  } finally { await ctx.dispose(); rmSync(dir, { recursive: true, force: true }) }
})

test('disabling automatic archives leaves configured recall active', async () => {
  const dir = root(), ctx = createFakeContext()
  const backend = new LocalMemoryStore(ctx, { root: dir, defaultLevels: 'l3' })
  ctx.provideService('memory', backend)
  checkpoint.apply(ctx, { autoArchive: false, autoRecall: true, materializer: 'off', cardModel: 'off' })
  const session = createSession({ id: 'recall-only', cwd: '/tmp/memex-recall-only' })
  try {
    const record = await backend.write({ kind: 'decision', title: 'Sprocket target', summary: 'Sprocket target', body: 'Sprocket uses staging', workspaceKey: memoryWorkspaceKey(session.header.cwd, session.id), scope: 'workspace' })
    const decision = createPreStepDecision(session, 'What is the Sprocket target?')
    const result = await ctx.emit('agent/pre-step', { agent: { session } }, terminalNext(decision))
    assert.ok(result.messages.some((message) => message.source?.form === 'recall' && message.source.recordIds.includes(record.id)))
    let eventSequenceReads = 0
    const ordinaryEvent = { type: 'message', get seq() { eventSequenceReads += 1; return 1 } }
    await ctx.emit('session/event', session, ordinaryEvent)
    assert.equal(eventSequenceReads, 0, 'disabled automatic archiving must not buffer conversation events')
    await ctx.emit('session/event', session, createCompactionEvent())
    await pause()
    assert.equal(await backend.wasArchived(session.id, 'cmp-1'), undefined)
  } finally { await ctx.dispose(); rmSync(dir, { recursive: true, force: true }) }
})

test('new SQLite database and sidecars remain private under a permissive existing root', { skip: process.platform === 'win32' }, () => {
  const dir = root(), previousMask = process.umask(0o022)
  chmodSync(dir, 0o755)
  const store = new LocalStoreCore({ root: dir })
  try {
    store.database()
    for (const name of ['index.db', 'index.db-wal', 'index.db-shm']) {
      assert.equal(statSync(join(dir, name)).mode & 0o077, 0, `${name} must not be group/world accessible`)
    }
    assert.equal(statSync(dir).mode & 0o777, 0o755, 'existing root permissions must not be changed')
  } finally { store.close(); process.umask(previousMask); rmSync(dir, { recursive: true, force: true }) }
})

test('reopening an existing store restricts database and active sidecars without losing records', { skip: process.platform === 'win32' }, () => {
  const dir = root()
  const first = new LocalStoreCore({ root: dir }), second = new LocalStoreCore({ root: dir })
  try {
    first.write({ id: 'mem_permissions', kind: 'fact', title: 'permission fixture', body: 'preserved', workspaceKey: 'wk' })
    for (const name of ['index.db', 'index.db-wal', 'index.db-shm']) chmodSync(join(dir, name), 0o644)
    assert.equal(second.get('mem_permissions').body, 'preserved')
    for (const name of ['index.db', 'index.db-wal', 'index.db-shm']) assert.equal(statSync(join(dir, name)).mode & 0o077, 0, name)
  } finally { second.close(); first.close(); rmSync(dir, { recursive: true, force: true }) }
})

test('a failed SQLite permission repair stops opening and a later retry keeps the record', { skip: process.platform === 'win32' }, () => {
  const dir = root()
  const store = new LocalStoreCore({ root: dir })
  try {
    store.write({ id: 'mem_permission_retry', kind: 'fact', title: 'permission retry', body: 'keep this record', workspaceKey: 'wk' })
    store.close()
    chmodSync(join(dir, 'index.db'), 0o644)
    const script = `import { LocalStoreCore } from ${JSON.stringify(new URL('../packages/memex-core/lib/store.js', import.meta.url).href)}; new LocalStoreCore({ root: process.env.MEMEX_TEST_ROOT }).database()`
    const failed = spawnSync(process.execPath, ['--import', sqlitePermissionFault, '--input-type=module', '-e', script], { encoding: 'utf8', env: { ...process.env, MEMEX_TEST_ROOT: dir } })
    assert.notEqual(failed.status, 0)
    assert.match(failed.stderr, /injected permission failure/)
    const retry = new LocalStoreCore({ root: dir })
    try { assert.equal(retry.get('mem_permission_retry').body, 'keep this record') } finally { retry.close() }
    assert.equal(statSync(join(dir, 'index.db')).mode & 0o077, 0)
  } finally { store.close(); rmSync(dir, { recursive: true, force: true }) }
})

test('compaction record, canonical events and marker roll back together and can be retried', () => {
  const dir = root()
  const store = new LocalStoreCore({ root: dir, capacityTokens: 10000 })
  const input = { sessionId: 's', compactionId: 'c', record: { id: 'mem_fixture', kind: 'episode', title: 'fixture', body: 'original body', workspaceKey: 'wk' }, events: [{ id: 'event-a', sequence: 1, content: 'original event' }] }
  try {
    store.database().exec("CREATE TRIGGER injected_failure BEFORE INSERT ON context_events BEGIN SELECT RAISE(ABORT, 'injected failure'); END")
    assert.throws(() => store.archiveRegion(input), /injected failure/)
    assert.equal(store.wasArchived('s', 'c'), undefined)
    assert.equal(store.get('mem_fixture'), undefined)
    store.database().exec('DROP TRIGGER injected_failure')
    store.archiveRegion(input)
    assert.equal(store.wasArchived('s', 'c'), 'mem_fixture')
    assert.equal(store.listContextEvents('mem_fixture')[0].content, 'original event')
  } finally { store.close(); rmSync(dir, { recursive: true, force: true }) }
})

test('a partial compaction is never marked complete and can be retried when missing events arrive', async () => {
  const dir = root()
  const events = createSurfaceEvents()
  const source = { session: events.slice(0, 2) }
  const ctx = createFakeContext({ sessionQuery: createSessionQueryMock(source) })
  const backend = new LocalMemoryStore(ctx, { root: dir, defaultLevels: 'l3' })
  ctx.provideService('memory', backend)
  checkpoint.apply(ctx, { cardModel: 'off' })
  const session = createSession({ id: 'session', cwd: '/tmp/memex-test' })
  const compaction = createCompactionEvent()
  try {
    await ctx.emit('session/event', session, compaction)
    await pause()
    assert.equal(await backend.wasArchived(session.id, 'cmp-1'), undefined)
    source.session = events
    await ctx.emit('session/event', session, compaction)
    await pause()
    const id = await backend.wasArchived(session.id, 'cmp-1')
    assert.ok(id)
    const saved = backend.core.listContextEvents(id)
    assert.deepEqual([...new Set(saved.map((event) => event.sequence))], [1, 2, 3])
    assert.deepEqual(saved.filter((event) => event.attachments.some((part) => part.rawEvent)).map((event) => event.attachments[0].rawEvent), events)
  } finally { await ctx.dispose(); rmSync(dir, { recursive: true, force: true }) }
})

test('a partial persisted query can be completed by the live event buffer', async () => {
  const dir = root()
  const events = createSurfaceEvents()
  const ctx = createFakeContext({ sessionQuery: createSessionQueryMock({ session: events.slice(0, 2) }) })
  const backend = new LocalMemoryStore(ctx, { root: dir, defaultLevels: 'l3' })
  ctx.provideService('memory', backend)
  checkpoint.apply(ctx, { cardModel: 'off' })
  const session = createSession({ id: 'session', cwd: '/tmp/memex-test' })
  try {
    await ctx.emit('session/event', session, events[2])
    await ctx.emit('session/event', session, createCompactionEvent())
    await pause()
    const id = await backend.wasArchived(session.id, 'cmp-1')
    assert.ok(id)
    assert.deepEqual([...new Set(backend.core.listContextEvents(id).map((event) => event.sequence))], [1, 2, 3])
  } finally { await ctx.dispose(); rmSync(dir, { recursive: true, force: true }) }
})

test('a legacy completion marker is repaired from the original complete source', async () => {
  const dir = root()
  const events = createSurfaceEvents()
  const session = createSession({ id: 'session', cwd: '/tmp/memex-test' })
  const ctx = createFakeContext({ sessionQuery: createSessionQueryMock({ session: events }) })
  const backend = new LocalMemoryStore(ctx, { root: dir, defaultLevels: 'l3' })
  ctx.provideService('memory', backend)
  checkpoint.apply(ctx, { cardModel: 'off' })
  const id = archiveRecordId('session', 'cmp-1')
  try {
    await backend.archiveRegion({ sessionId: 'session', compactionId: 'cmp-1', record: { id, kind: 'episode', title: 'legacy partial', body: 'partial', workspaceKey: 'wk', provenance: { sessionId: 'session', compactionId: 'cmp-1' } } })
    assert.equal(await backend.wasArchived('session', 'cmp-1'), id)
    assert.equal(await backend.wasArchived('session', 'cmp-1', { requireComplete: true }), undefined)
    await ctx.emit('session/event', session, createCompactionEvent())
    await pause()
    assert.equal(await backend.wasArchived('session', 'cmp-1', { requireComplete: true }), id)
    assert.equal(backend.core.listContextEvents(id).filter((event) => event.attachments.some((part) => part.rawEvent)).length, 3)
  } finally { await ctx.dispose(); rmSync(dir, { recursive: true, force: true }) }
})

test('canonical event identities do not collide across archives with the same sequence', () => {
  const dir = root()
  const store = new LocalStoreCore({ root: dir, capacityTokens: 10000 })
  try {
    for (const id of ['mem_one', 'mem_two']) {
      store.archiveRegion({ sessionId: id, compactionId: 'c', record: { id, kind: 'episode', title: id, body: id, workspaceKey: 'wk' }, events: canonicalEventsFromDsh([{ seq: 1, message: { role: 'user', content: [{ type: 'text', text: id }] } }], { sessionId: id, recordId: id }) })
    }
    assert.equal(store.listContextEvents('mem_one')[0].content, 'mem_one')
    assert.equal(store.listContextEvents('mem_two')[0].content, 'mem_two')
  } finally { store.close(); rmSync(dir, { recursive: true, force: true }) }
})

test('detected credentials in DSH compaction stay in L2 or are not archived', async () => {
  for (const levels of ['both', 'l3']) {
    const dir = root()
    const ctx = createFakeContext()
    const backend = new LocalMemoryStore(ctx, { root: dir, defaultLevels: levels })
    ctx.provideService('memory', backend)
    checkpoint.apply(ctx, { cardModel: 'off' })
    const session = createSession({ id: 'private-session', cwd: '/tmp/memex-test' })
    const events = createSurfaceEvents()
    events[0].data.content[0].text = 'password=synthetic-private-value'
    try {
      for (const event of events) await ctx.emit('session/event', session, event)
      await ctx.emit('session/event', session, createCompactionEvent())
      await pause()
      const id = await backend.wasArchived(session.id, 'cmp-1')
      if (levels === 'both') {
        assert.ok(id)
        assert.equal((await backend.get(id)).scope, 'session')
      } else assert.equal(id, undefined)
    } finally { await ctx.dispose(); rmSync(dir, { recursive: true, force: true }) }
  }
})

test('explicit levels limit sticky levels rather than re-enabling workspace visibility', () => {
  const dir = root()
  try {
    let engine = new AgentMemory({ root: dir, cwd: dir, sessionId: 's', levels: ['l2', 'l3'] })
    engine.close()
    engine = new AgentMemory({ root: dir, cwd: dir, sessionId: 's', levels: ['l2'] })
    try {
      assert.deepEqual(engine.levels, { l2: true, l3: false })
      assert.equal(engine.write({ kind: 'fact', title: 'private', body: 'secret' }).scope, 'session')
    } finally { engine.close() }
  } finally { rmSync(dir, { recursive: true, force: true }) }
})

test('implicit agent sessions never share the same private L2 namespace', () => {
  const dir = root()
  const saved = [process.env.MEMEX_SESSION, process.env.DSH_MEMORY_SESSION]
  delete process.env.MEMEX_SESSION
  delete process.env.DSH_MEMORY_SESSION
  try {
    const first = new AgentMemory({ root: dir, cwd: dir, levels: ['l2'] })
    const second = new AgentMemory({ root: dir, cwd: dir, levels: ['l2'] })
    try {
      assert.notEqual(first.sessionId, second.sessionId)
      first.write({ kind: 'fact', title: 'private', body: 'private session record' })
      assert.equal(second.list({ limit: 10 }).length, 0)
    } finally { first.close(); second.close() }
  } finally {
    if (saved[0] !== undefined) process.env.MEMEX_SESSION = saved[0]
    if (saved[1] !== undefined) process.env.DSH_MEMORY_SESSION = saved[1]
    rmSync(dir, { recursive: true, force: true })
  }
})

test('an absent index with existing files fails closed without deleting the archive', () => {
  const dir = root()
  let store = new LocalStoreCore({ root: dir, capacityTokens: 10000 })
  try {
    const record = store.write({ kind: 'fact', title: 'fixture', body: 'archive contents', workspaceKey: 'wk' })
    store.close()
    renameSync(join(dir, 'index.db'), join(dir, 'index.saved'))
    store = new LocalStoreCore({ root: dir, capacityTokens: 10000 })
    assert.throws(() => store.database(), /index.*missing/i)
    assert.match(readFileSync(record.path, 'utf8'), /archive contents/)
  } finally { store.close(); rmSync(dir, { recursive: true, force: true }) }
})

test('record bodies preserve leading and trailing newlines', () => {
  const dir = root()
  const store = new LocalStoreCore({ root: dir, capacityTokens: 10000 })
  try {
    const body = '\n\nfirst line\nlast line\n'
    const card = store.write({ kind: 'fact', title: 'newlines', body, workspaceKey: 'wk' })
    assert.equal(store.get(card.id).body, body)
  } finally { store.close(); rmSync(dir, { recursive: true, force: true }) }
})

test('Claude init preserves malformed configuration and co-located user hooks', () => {
  const dir = root()
  try {
    const project = join(dir, 'project')
    mkdirSync(join(project, '.claude'), { recursive: true })
    const mcpPath = join(project, '.mcp.json')
    const settingsPath = join(project, '.claude', 'settings.json')
    const initialMcp = '{"mcpServers":{"other":{"command":"other"}}}\n'
    const invalidSettings = '{not valid json\n'
    writeFileSync(mcpPath, initialMcp)
    writeFileSync(settingsPath, invalidSettings)
    const failed = node(['init', '--project', project, '--root', join(dir, 'memory')])
    assert.notEqual(failed.status, 0)
    assert.equal(readFileSync(mcpPath, 'utf8'), initialMcp)
    assert.equal(readFileSync(settingsPath, 'utf8'), invalidSettings)
    const userHook = { type: 'command', command: 'my-own-hook' }
    writeFileSync(settingsPath, JSON.stringify({ hooks: { PreCompact: [{ matcher: 'manual|auto', hooks: [userHook, { type: 'command', command: 'node /old/memex-claude/bin/cli.mjs hook PreCompact' }] }] } }))
    const ok = node(['init', '--project', project, '--root', join(dir, 'memory')])
    assert.equal(ok.status, 0, ok.stderr)
    const settings = JSON.parse(readFileSync(settingsPath, 'utf8'))
    assert.ok(settings.hooks.PreCompact.flatMap((entry) => entry.hooks).some((hook) => hook.command === 'my-own-hook'))
  } finally { rmSync(dir, { recursive: true, force: true }) }
})

test('an interrupted Claude config write leaves existing configuration intact', () => {
  const dir = root()
  try {
    const project = join(dir, 'project')
    mkdirSync(join(project, '.claude'), { recursive: true })
    const mcpPath = join(project, '.mcp.json')
    const settingsPath = join(project, '.claude/settings.json')
    const mcpText = '{"mcpServers":{"other":{"command":"keep"}}}\n'
    const settingsText = '{"hooks":{}}\n'
    writeFileSync(mcpPath, mcpText)
    writeFileSync(settingsPath, settingsText)
    const result = node(['init', '--project', project, '--root', join(dir, 'memory')], '', { NODE_OPTIONS: `--import=${initFault}` })
    assert.notEqual(result.status, 0)
    assert.equal(readFileSync(mcpPath, 'utf8'), mcpText)
    assert.equal(readFileSync(settingsPath, 'utf8'), settingsText)
  } finally { rmSync(dir, { recursive: true, force: true }) }
})

test('Claude init keeps an existing configuration symlink and its unrelated server', () => {
  const dir = root()
  const project = join(dir, 'project')
  const target = join(dir, 'shared-config.json')
  mkdirSync(project)
  writeFileSync(target, '{"mcpServers":{"other":{"command":"keep"}}}\n')
  symlinkSync(target, join(project, '.mcp.json'))
  try {
    const result = node(['init', '--project', project, '--root', join(dir, 'memory')])
    assert.equal(result.status, 0, result.stderr)
    assert.ok(lstatSync(join(project, '.mcp.json')).isSymbolicLink())
    const config = JSON.parse(readFileSync(target, 'utf8'))
    assert.equal(config.mcpServers.other.command, 'keep')
    assert.ok(config.mcpServers.memex)
  } finally { rmSync(dir, { recursive: true, force: true }) }
})

test('Claude init refuses to replace a dangling configuration symlink', () => {
  const dir = root()
  const project = join(dir, 'project')
  mkdirSync(project)
  const link = join(project, '.mcp.json')
  symlinkSync(join(dir, 'missing.json'), link)
  try {
    const result = node(['init', '--project', project, '--root', join(dir, 'memory')])
    assert.notEqual(result.status, 0)
    assert.ok(lstatSync(link).isSymbolicLink())
  } finally { rmSync(dir, { recursive: true, force: true }) }
})

test('Codex init preserves existing backup and instructions when adding configuration', () => {
  const dir = root()
  const project = join(dir, 'project')
  const codexHome = join(dir, 'codex')
  mkdirSync(project); mkdirSync(codexHome)
  const agents = join(project, 'AGENTS.md')
  const config = join(codexHome, 'config.toml')
  const oldInstructions = '# Existing instructions\n\n  \n'
  const oldConfig = 'model = "existing"\n\n  \n'
  writeFileSync(agents, oldInstructions)
  writeFileSync(config, oldConfig)
  writeFileSync(`${config}.bak`, 'older backup must survive\n')
  try {
    const args = ['init', '--project', project, '--root', join(dir, 'memory'), '--write-config']
    const first = codexNode(args, { CODEX_HOME: codexHome })
    assert.equal(first.status, 0, first.stderr)
    assert.ok(readFileSync(agents, 'utf8').startsWith(oldInstructions))
    assert.ok(readFileSync(config, 'utf8').startsWith(oldConfig))
    assert.equal(readFileSync(`${config}.bak`, 'utf8'), 'older backup must survive\n')
    const backups = readdirSync(codexHome).filter((name) => /^config\.toml\.memex-.*\.bak$/.test(name))
    assert.equal(backups.length, 1)
    assert.equal(readFileSync(join(codexHome, backups[0]), 'utf8'), oldConfig)
    const updatedAgents = readFileSync(agents, 'utf8')
    const updatedConfig = readFileSync(config, 'utf8')
    const second = codexNode(args, { CODEX_HOME: codexHome })
    assert.equal(second.status, 0, second.stderr)
    assert.equal(readFileSync(agents, 'utf8'), updatedAgents)
    assert.equal(readFileSync(config, 'utf8'), updatedConfig)
    assert.equal(readdirSync(codexHome).filter((name) => /^config\.toml\.memex-.*\.bak$/.test(name)).length, 1)
  } finally { rmSync(dir, { recursive: true, force: true }) }
})

test('an interrupted Codex config write preserves the old configuration', () => {
  const dir = root(), project = join(dir, 'project'), codexHome = join(dir, 'codex')
  mkdirSync(project); mkdirSync(codexHome)
  const config = join(codexHome, 'config.toml')
  const original = 'model = "preserve"\n'
  writeFileSync(config, original)
  try {
    const result = codexNode(['init', '--project', project, '--root', join(dir, 'memory'), '--write-config'], { CODEX_HOME: codexHome, NODE_OPTIONS: `--import=${codexInitFault}` })
    assert.notEqual(result.status, 0)
    assert.equal(readFileSync(config, 'utf8'), original)
    assert.throws(() => readFileSync(join(project, 'AGENTS.md'), 'utf8'), { code: 'ENOENT' })
    const retry = codexNode(['init', '--project', project, '--root', join(dir, 'memory'), '--write-config'], { CODEX_HOME: codexHome })
    assert.equal(retry.status, 0, retry.stderr)
    assert.ok(readFileSync(config, 'utf8').startsWith(original))
    assert.ok(readFileSync(config, 'utf8').includes('[mcp_servers.memex]'))
    const backups = readdirSync(codexHome).filter((name) => /^config\.toml\.memex-.*\.bak$/.test(name))
    assert.equal(backups.length, 2)
    for (const backup of backups) assert.equal(readFileSync(join(codexHome, backup), 'utf8'), original)
  } finally { rmSync(dir, { recursive: true, force: true }) }
})

test('Codex init rejects incomplete manual markers before changing configuration', () => {
  const dir = root(), project = join(dir, 'project'), codexHome = join(dir, 'codex')
  mkdirSync(project); mkdirSync(codexHome)
  const agents = join(project, 'AGENTS.md'), config = join(codexHome, 'config.toml')
  writeFileSync(agents, '# existing\n<!-- memex:start -->\nunfinished\n')
  writeFileSync(config, 'model = "keep"\n')
  try {
    const result = codexNode(['init', '--project', project, '--root', join(dir, 'memory'), '--write-config'], { CODEX_HOME: codexHome })
    assert.notEqual(result.status, 0)
    assert.equal(readFileSync(agents, 'utf8'), '# existing\n<!-- memex:start -->\nunfinished\n')
    assert.equal(readFileSync(config, 'utf8'), 'model = "keep"\n')
  } finally { rmSync(dir, { recursive: true, force: true }) }
})

test('Codex init respects an existing quoted memex server table', () => {
  const dir = root(), project = join(dir, 'project'), codexHome = join(dir, 'codex')
  mkdirSync(project); mkdirSync(codexHome)
  const config = join(codexHome, 'config.toml'), original = '[mcp_servers."memex"]\ncommand = "other"\n'
  writeFileSync(config, original)
  try {
    const result = codexNode(['init', '--project', project, '--root', join(dir, 'memory'), '--write-config'], { CODEX_HOME: codexHome })
    assert.equal(result.status, 0, result.stderr)
    assert.equal(readFileSync(config, 'utf8'), original)
  } finally { rmSync(dir, { recursive: true, force: true }) }
})

test('Codex init respects inline memex entries but ignores a commented table', () => {
  const dir = root()
  try {
    for (const [name, original, shouldChange] of [
      ['inline', '[mcp_servers]\nmemex = { command = "other" }\n', false],
      ['array', '[[mcp_servers.memex]]\ncommand = "other"\n', false],
      ['comment', '# [mcp_servers.memex]\nmodel = "existing"\n', true],
    ]) {
      const project = join(dir, `${name}-project`), codexHome = join(dir, `${name}-codex`)
      mkdirSync(project); mkdirSync(codexHome)
      const config = join(codexHome, 'config.toml')
      writeFileSync(config, original)
      const result = codexNode(['init', '--project', project, '--root', join(dir, 'memory'), '--write-config'], { CODEX_HOME: codexHome })
      assert.equal(result.status, 0, result.stderr)
      const current = readFileSync(config, 'utf8')
      assert.equal(current !== original, shouldChange)
      if (shouldChange) assert.ok(current.startsWith(original) && current.includes('\n[mcp_servers.memex]\n'))
    }
  } finally { rmSync(dir, { recursive: true, force: true }) }
})

test('Codex init retains an existing configuration symlink', () => {
  const dir = root(), project = join(dir, 'project'), codexHome = join(dir, 'codex')
  mkdirSync(project); mkdirSync(codexHome)
  const config = join(codexHome, 'config.toml'), target = join(dir, 'shared.toml')
  writeFileSync(target, 'model = "existing"\n')
  symlinkSync(target, config)
  try {
    const result = codexNode(['init', '--project', project, '--root', join(dir, 'memory'), '--write-config'], { CODEX_HOME: codexHome })
    assert.equal(result.status, 0, result.stderr)
    assert.ok(lstatSync(config).isSymbolicLink())
    assert.ok(readFileSync(target, 'utf8').includes('[mcp_servers.memex]'))
  } finally { rmSync(dir, { recursive: true, force: true }) }
})

test('Claude project namespace stays fixed and raw transcripts use the actual client session', () => {
  const dir = root()
  const project = join(dir, 'project')
  const child = join(project, 'child')
  const memory = join(dir, 'memory')
  mkdirSync(child, { recursive: true })
  const transcript = join(project, 'transcript.jsonl')
  writeFileSync(transcript, 'private transcript')
  try {
    const result = node(['hook', 'PreCompact', '--root', memory, '--project', project, '--levels', 'l2,l3', '--session', 'shared-id'], JSON.stringify({ session_id: 'real-client-id', cwd: child, transcript_path: transcript }))
    assert.equal(result.status, 0, result.stderr)
    const actual = new AgentMemory({ root: memory, cwd: project, sessionId: 'real-client-id', levels: ['l2'] })
    const shared = new AgentMemory({ root: memory, cwd: project, sessionId: 'shared-id', levels: ['l2'] })
    const nested = new AgentMemory({ root: memory, cwd: child, sessionId: 'real-client-id', levels: ['l2'] })
    try {
      assert.equal(actual.list({ limit: 10 }).length, 1)
      assert.equal(shared.list({ limit: 10 }).length, 0)
      assert.equal(nested.list({ limit: 10 }).length, 0)
    } finally { actual.close(); shared.close(); nested.close() }
  } finally { rmSync(dir, { recursive: true, force: true }) }
})

test('Claude user initialization registers the user MCP server without forcing the home workspace', () => {
  const dir = root()
  try {
    writeFileSync(join(dir, 'CLAUDE.md'), 'existing home instructions\n')
    const result = node(['init', '--user', '--root', join(dir, 'memory')], '', { HOME: dir })
    assert.equal(result.status, 0, result.stderr)
    const config = JSON.parse(readFileSync(join(dir, '.claude.json'), 'utf8'))
    assert.ok(!config.mcpServers.memex.args.includes('--cwd'))
    const hooks = JSON.parse(readFileSync(join(dir, '.claude/settings.json'), 'utf8')).hooks
    assert.match(hooks.PreCompact[0].hooks[0].command, /--user/)
    assert.match(readFileSync(join(dir, '.claude/CLAUDE.md'), 'utf8'), /memex:start/)
    assert.equal(readFileSync(join(dir, 'CLAUDE.md'), 'utf8'), 'existing home instructions\n')
  } finally { rmSync(dir, { recursive: true, force: true }) }
})

test('user-level Claude hooks use the original project identity after a cwd change', () => {
  const dir = root()
  const project = join(dir, 'project')
  const child = join(project, 'child')
  const memory = join(dir, 'memory')
  mkdirSync(child, { recursive: true })
  try {
    const result = node(['hook', 'Stop', '--user', '--root', memory, '--project', dir, '--levels', 'l3'], JSON.stringify({ session_id: 's', cwd: child, last_assistant_message: 'The original project identity should remain stable after a working-directory change.' }), { CLAUDE_PROJECT_DIR: project })
    assert.equal(result.status, 0, result.stderr)
    const projectEngine = new AgentMemory({ root: memory, cwd: project, sessionId: 'other', levels: ['l3'] })
    const childEngine = new AgentMemory({ root: memory, cwd: child, sessionId: 'other', levels: ['l3'] })
    try {
      assert.equal(projectEngine.list({ limit: 10 }).length, 1)
      assert.equal(childEngine.list({ limit: 10 }).length, 0)
    } finally { projectEngine.close(); childEngine.close() }
  } finally { rmSync(dir, { recursive: true, force: true }) }
})

test('generated Claude hook commands quote special characters in project paths', () => {
  const dir = root()
  const marker = join(dir, 'unexpected')
  const project = join(dir, "project ' quote $(touch unexpected)")
  mkdirSync(project)
  try {
    const result = node(['init', '--project', project, '--root', join(dir, 'memory'), '--levels', 'l2'])
    assert.equal(result.status, 0, result.stderr)
    const hooks = JSON.parse(readFileSync(join(project, '.claude/settings.json'), 'utf8')).hooks
    const command = hooks.SessionStart[0].hooks[0].command
    const invoked = spawnSync('/bin/sh', ['-c', command], { cwd: dir, input: JSON.stringify({ session_id: 's', cwd: project }), encoding: 'utf8', timeout: 60000, env: { ...process.env, NODE_OPTIONS: `--import=${register}` } })
    assert.equal(invoked.status, 0, invoked.stderr)
    assert.throws(() => readFileSync(marker), /ENOENT/)
  } finally { rmSync(dir, { recursive: true, force: true }) }
})

test('Claude leaves a transcript in place when only workspace sharing is enabled', () => {
  const dir = root()
  const transcript = join(dir, 'transcript.jsonl')
  writeFileSync(transcript, 'private transcript')
  try {
    const result = node(['hook', 'PreCompact', '--root', join(dir, 'memory'), '--project', dir, '--levels', 'l3'], JSON.stringify({ session_id: 's', cwd: dir, transcript_path: transcript }))
    assert.equal(result.status, 0, result.stderr)
    assert.match(result.stderr, /skipped.*L2/)
    assert.equal(readFileSync(transcript, 'utf8'), 'private transcript')
    const other = new AgentMemory({ root: join(dir, 'memory'), cwd: dir, sessionId: 'other', levels: ['l3'] })
    try { assert.equal(other.list({ limit: 10 }).length, 0) } finally { other.close() }
  } finally { rmSync(dir, { recursive: true, force: true }) }
})

test('a non-UTF-8 transcript is not silently rewritten with replacement characters', () => {
  const dir = root()
  const transcript = join(dir, 'transcript.jsonl')
  const bytes = Buffer.from([0x66, 0x80, 0x6f])
  writeFileSync(transcript, bytes)
  try {
    const result = node(['hook', 'PreCompact', '--root', join(dir, 'memory'), '--project', dir, '--levels', 'l2'], JSON.stringify({ session_id: 's', cwd: dir, transcript_path: transcript }))
    assert.match(result.stderr, /hook failed/i)
    assert.deepEqual(readFileSync(transcript), bytes)
    const owner = new AgentMemory({ root: join(dir, 'memory'), cwd: dir, sessionId: 's', levels: ['l2'] })
    try { assert.equal(owner.list({ limit: 10 }).length, 0) } finally { owner.close() }
  } finally { rmSync(dir, { recursive: true, force: true }) }
})

test('Claude long transcript is complete, untrusted and private to its actual session', () => {
  const dir = root()
  const project = join(dir, 'project')
  const memory = join(dir, 'memory')
  mkdirSync(project)
  const transcriptPath = join(project, 'transcript.jsonl')
  const prefix = '\uFEFFpassword=synthetic-private-value\n'
  const text = `${prefix}${'x'.repeat(MEMORY_TEXT_LIMITS.body - prefix.length - 1)}😀end-of-transcript`
  writeFileSync(transcriptPath, text)
  try {
    const result = node(['hook', 'PreCompact', '--root', memory, '--project', project, '--levels', 'l2,l3'], JSON.stringify({ session_id: 'session-a', cwd: project, transcript_path: transcriptPath }))
    assert.equal(result.status, 0, result.stderr)
    assert.doesNotMatch(result.stderr, /failed/i)
    const owner = new AgentMemory({ root: memory, cwd: project, sessionId: 'session-a', levels: ['l2', 'l3'] })
    const other = new AgentMemory({ root: memory, cwd: project, sessionId: 'session-b', levels: ['l2', 'l3'] })
    try {
      const cards = owner.list({ limit: 20 }).filter((card) => card.provenance?.source === 'claude-precompact').sort((a, b) => a.provenance.part - b.provenance.part)
      assert.ok(cards.length >= 2)
      assert.ok(cards.every((card) => card.scope === 'session' && card.trust === 'untrusted'))
      assert.equal(cards.map((card) => owner.store.get(card.id).body).join(''), text)
      assert.equal(other.list({ limit: 20 }).length, 0)
    } finally { owner.close(); other.close() }
  } finally { rmSync(dir, { recursive: true, force: true }) }
})

test('an interrupted multi-part Claude transcript can be retried without losing or duplicating parts', () => {
  const dir = root()
  const memory = join(dir, 'memory')
  const transcript = join(dir, 'transcript.jsonl')
  const text = 'x'.repeat(MEMORY_TEXT_LIMITS.body) + '\nlast part'
  writeFileSync(transcript, text)
  const store = new LocalStoreCore({ root: memory, capacityTokens: 10000 })
  try {
    store.database().exec("CREATE TRIGGER fail_second_part BEFORE INSERT ON records WHEN NEW.title LIKE '%part 2/%' BEGIN SELECT RAISE(ABORT, 'injected failure'); END")
    store.close()
    const invoke = () => node(['hook', 'PreCompact', '--root', memory, '--project', dir, '--levels', 'l2'], JSON.stringify({ session_id: 's', cwd: dir, transcript_path: transcript }))
    const failed = invoke()
    assert.match(failed.stderr, /injected failure/)
    assert.equal(readFileSync(transcript, 'utf8'), text)
    store.database().exec('DROP TRIGGER fail_second_part')
    store.close()
    assert.doesNotMatch(invoke().stderr, /failed/i)
    assert.doesNotMatch(invoke().stderr, /failed/i)
    const engine = new AgentMemory({ root: memory, cwd: dir, sessionId: 's', levels: ['l2'] })
    try {
      const cards = engine.list({ limit: 10 }).filter((card) => card.provenance?.source === 'claude-precompact').sort((a, b) => a.provenance.part - b.provenance.part)
      assert.equal(cards.length, 2)
      assert.equal(cards.map((card) => engine.store.get(card.id).body).join(''), text)
    } finally { engine.close() }
  } finally { store.close(); rmSync(dir, { recursive: true, force: true }) }
})

test('DSH and MCP can page an entire raw event without exposing another session', async () => {
  const dir = root()
  const ctx = createFakeContext()
  const backend = new LocalMemoryStore(ctx, { root: dir, defaultLevels: 'l2' })
  ctx.provideService('memory', backend)
  checkpoint.apply(ctx, { cardModel: 'off' })
  toolsRow.apply(ctx, { maxInlineChars: 1500 })
  const session = createSession({ id: 'owner-session', cwd: '/tmp/memex-event-paging' })
  const events = createSurfaceEvents()
  events[0].data.content[0].text = `${'x😀'.repeat(5000)}RAW_EVENT_TAIL`
  try {
    for (const event of events) await ctx.emit('session/event', session, event)
    await ctx.emit('session/event', session, createCompactionEvent())
    await pause()
    const id = await backend.wasArchived(session.id, 'cmp-1', { requireComplete: true })
    assert.ok(id)
    const open = ctx.tool('memory_open')
    let offset = 0
    let restored = ''
    do {
      const text = await open.execute({ id, eventIndex: 1, charOffset: offset, maxChars: 2000 }, { agent: { session } })
      assert.ok(text.length <= 1500)
      const page = JSON.parse(text)
      assert.equal(page.sequence, 1)
      restored += page.content
      offset = page.nextCharOffset
    } while (offset !== null)
    assert.deepEqual(JSON.parse(restored), events[0])
    const denied = await open.execute({ id, eventIndex: 1 }, { agent: { session: createSession({ id: 'other', cwd: session.header.cwd }) } })
    assert.match(denied, /No memory record/)
    const request = JSON.stringify({ jsonrpc: '2.0', id: 1, method: 'tools/call', params: { name: 'memory_open', arguments: { id, eventIndex: 1, maxChars: 60000 } } }) + '\n'
    const result = spawnSync(process.execPath, ['--import', register, mcp, '--root', dir, '--cwd', session.header.cwd, '--levels', 'l2', '--session', session.id], { input: request, encoding: 'utf8', timeout: 60000 })
    assert.equal(result.status, 0, result.stderr)
    const page = JSON.parse(JSON.parse(result.stdout.trim()).result.content[0].text)
    assert.equal(page.nextCharOffset, null)
    assert.deepEqual(JSON.parse(page.content), events[0])
  } finally { await ctx.dispose(); rmSync(dir, { recursive: true, force: true }) }
})

test('DSH can continue within one oversized record line', async () => {
  const dir = root()
  const ctx = createFakeContext()
  const backend = new LocalMemoryStore(ctx, { root: dir, defaultLevels: 'l2' })
  ctx.provideService('memory', backend)
  toolsRow.apply(ctx, { maxInlineChars: 1500 })
  const session = createSession({ id: 'owner-session', cwd: '/tmp/memex-long-line' })
  try {
    const card = await backend.write({ kind: 'fact', title: 'long line', body: `${'x😀'.repeat(5000)}BODY_TAIL`, scope: 'session', sessionId: session.id, workspaceKey: memoryWorkspaceKey(session.header.cwd, session.id) })
    const open = ctx.tool('memory_open')
    let offset = 0
    let sawTail = false
    for (let pages = 0; pages < 50; pages += 1) {
      const text = await open.execute({ id: card.id, offset: 1, limit: 1, charOffset: offset, maxChars: 2000 }, { agent: { session } })
      assert.ok(text.length <= 1500)
      sawTail ||= text.includes('BODY_TAIL')
      const match = text.match(/nextCharOffset=(\d+)/)
      if (!match) break
      assert.ok(Number(match[1]) > offset)
      offset = Number(match[1])
    }
    assert.ok(sawTail, 'a long line must remain reachable through the advertised continuation')
  } finally { await ctx.dispose(); rmSync(dir, { recursive: true, force: true }) }
})
