import assert from 'node:assert/strict'
import { test } from 'node:test'
import fs from 'node:fs'
import { tmpdir } from 'node:os'
import { join, resolve } from 'node:path'
import { spawnSync } from 'node:child_process'
import { pathToFileURL } from 'node:url'
import { createFakeContext } from './fake-ctx.mjs'
import LocalMemoryStore from '../packages/memex-local/index.js'
import { registerCheckpointPolicy } from '../packages/memex-checkpoint/lib/checkpoint.js'
import { apply as compress } from '../packages/memex-compress/index.js'
import { apply as api } from '../packages/memex-api/index.js'
import { apply as evict } from '../packages/memex-evict/index.js'
import { LocalStoreCore } from '../packages/memex-core/lib/store.js'
import { memoryWorkspaceKey } from '../packages/memex-core/index.js'

function fixture(t, llm) {
  const root = fs.mkdtempSync(join(tmpdir(), 'memex-audit-integration-'))
  const ctx = createFakeContext(llm ? { llm } : {})
  const memory = new LocalMemoryStore(ctx, { root: join(root, 'store'), capacityTokens: 100 })
  ctx.memory = memory
  t.after(async () => { await ctx.dispose(); fs.rmSync(root, { recursive: true, force: true }) })
  const session = { id: 'audit', header: { cwd: root }, requestHeader: () => ({ config: { provider: 'synthetic', model: 'synthetic' } }) }
  return { root, ctx, memory, session }
}

test('F11: the actual asynchronous checkpoint refinement cannot undo superseded', async t => {
  let release, entered
  const gate = new Promise(r => { release = r }), started = new Promise(r => { entered = r })
  const { ctx, memory, session } = fixture(t, { async *stream() { entered(); await gate; yield { type: 'text-delta', index: 0, text: '{"title":"new card"}' } } })
  await memory.enableLevel(session.id, 'l3')
  const policy = registerCheckpointPolicy(ctx, memory, { cardModel: 'auto' })
  t.after(() => { release(); policy.dispose() })
  await ctx.emit('session/event', session, { seq: 1, type: 'user/message', data: { role: 'user', content: [{ type: 'text', text: 'source' }] } })
  await ctx.emit('session/event', session, { seq: 2, type: 'compaction/summary', data: { compactionId: 'audit', shadowedSeqs: [1], summary: [{ type: 'text', text: 'summary' }], shadowedTokenCount: 10 } })
  await started
  const row = memory.core.list({ workspaceKey: memoryWorkspaceKey(session.header.cwd), limit: 10 })[0]
  await memory.setStatus(row.id, 'superseded')
  release(); await policy.drain()
  assert.equal((await memory.get(row.id)).status, 'superseded')
})

test('F09: a killed FTS migration is complete after the next open', t => {
  const { root } = fixture(t)
  const source = join(root, 'migration'), store = new LocalStoreCore({ root: source })
  store.write({ id: 'old', workspaceKey: 'audit', kind: 'fact', title: 'migration', body: 'body' })
  store.database().exec('DROP TABLE records_fts; CREATE VIRTUAL TABLE records_fts USING fts5(title,summary,use_when,tags,body)'); store.close()
  const hook = join(root, 'stop.mjs')
  fs.writeFileSync(hook, "import{DatabaseSync}from'node:sqlite';const exec=DatabaseSync.prototype.exec;DatabaseSync.prototype.exec=function(sql){const r=exec.call(this,sql);if(sql.startsWith('CREATE VIRTUAL TABLE records_fts USING fts5(title, summary, use_when, tags, abstract'))process.exit(91);return r}")
  const module = pathToFileURL(resolve('packages/memex-core/lib/store.js')).href
  const result = spawnSync(process.execPath, ['--import', hook, '--input-type=module', '-e', `import{LocalStoreCore}from ${JSON.stringify(module)};new LocalStoreCore({root:${JSON.stringify(source)}}).ensure()`], { encoding: 'utf8', timeout: 10000 })
  assert.equal(result.status, 91)
  store.ensure()
  assert.equal(store.database().prepare('SELECT count(*) n FROM records_fts').get().n, 1)
  assert.equal(store.get('old').body, 'body')
  store.close()
})

test('F12: failed dispatches are counted and request budget includes retries', async t => {
  let attempts = 0
  const { ctx, memory, session } = fixture(t, { async *stream() { attempts++; throw new Error('SYNTHETIC_FAILURE') } })
  await memory.enableLevel('audit', 'l3')
  await memory.write({ id: 'input', workspaceKey: memoryWorkspaceKey(session.header.cwd), scope: 'workspace', kind: 'fact', title: 'input', body: 'word '.repeat(500), createdAt: 1 })
  compress(ctx, { minAgeMs: 0, minDigestTokens: 1, maxBatches: 1, maxLlmCalls: 1 })
  await ctx.tool('memory_compress').execute({ level: 'l3', strategy: 'digest' }, { agent: { session } })
  const stats = await memory.compressionStats('audit', 3)
  assert.equal(attempts, 1)
  assert.equal(stats.last.llmCalls, 1)
  assert.equal(stats.last.attempts[0].status, 'failed')
  assert.equal(stats.last.attempts[0].charge, 'UNKNOWN')
  assert.equal((await memory.get('input')).body, 'word '.repeat(500))
})

test('F12: cancellation retains reported partial usage and unknown charges', async t => {
  const { ctx, memory, session } = fixture(t, { async *stream() { yield { type: 'finish', usage: { inputTokens: 7 } }; throw new DOMException('cancelled', 'AbortError') } })
  await memory.enableLevel('audit', 'l3')
  await memory.write({ id: 'partial', workspaceKey: memoryWorkspaceKey(session.header.cwd), scope: 'workspace', kind: 'fact', title: 'input', body: 'word '.repeat(500), createdAt: 1 })
  compress(ctx, { minAgeMs: 0, minDigestTokens: 1, maxBatches: 1 })
  await ctx.tool('memory_compress').execute({ level: 'l3', strategy: 'digest' }, { agent: { session } })
  const last = (await memory.compressionStats('audit')).last
  assert.equal(last.llmCalls, 1)
  assert.equal(last.attempts[0].status, 'cancelled')
  assert.equal(last.attempts[0].usage.inputTokens, 7)
  assert.equal(last.attempts[0].charge, 'UNKNOWN')
})

test('F13: paginated HTTP bodies concatenate exactly across byte and surrogate boundaries', async t => {
  const { ctx, memory, session } = fixture(t)
  await memory.enableLevel('audit', 'l3')
  const body = '汉😀e\u0301'.repeat(30000)
  const row = await memory.write({ id: 'unicode', workspaceKey: memoryWorkspaceKey(session.header.cwd), scope: 'workspace', kind: 'fact', title: 'unicode', body })
  const routes = []
  ctx.sessions = { list: () => [session] }
  ctx.connection = { fetch: { register: route => { routes.push(route); return () => {} } } }
  api(ctx)
  const route = routes.find(x => x.path === '/api/memory.record')
  let offset = 0, read = ''
  for (let page = 0; page < 10; page++) {
    const response = await route.fetch(new Request(`http://example.invalid/api/memory.record?sessionId=audit&id=${row.id}&offset=${offset}`))
    assert.equal(response.status, 200)
    const data = await response.json()
    assert.ok(!data.body.includes('\uFFFD'))
    assert.ok(Buffer.byteLength(data.body, 'utf8') <= 256 * 1024)
    assert.equal(data.consumedChars, data.body.length)
    read += data.body
    if (data.nextCharOffset === null) break
    assert.ok(data.nextCharOffset > offset)
    offset = data.nextCharOffset
  }
  assert.equal(read, body)
  const bad = await route.fetch(new Request(`http://example.invalid/api/memory.record?sessionId=audit&id=${row.id}&offset=2`))
  assert.equal(bad.status, 400, 'offset inside an emoji is refused')
})

test('A01: a hung enhancement cannot block another session archive or bounded drain', async t => {
  let calls = 0
  const { ctx, memory, session, root } = fixture(t, { async *stream() { calls++; await new Promise(() => {}) } })
  const policy = registerCheckpointPolicy(ctx, memory, { cardModel: 'auto', cardTimeoutMs: 25, maxEnrichmentJobs: 1 })
  t.after(() => policy.dispose())
  for (const id of ['first', 'second']) {
    const current = { ...session, id }
    await memory.enableLevel(id, 'l3')
    await ctx.emit('session/event', current, { seq: 1, type: 'user/message', data: { role: 'user', content: [{ type: 'text', text: id }] } })
    await ctx.emit('session/event', current, { seq: 2, type: 'compaction/summary', data: { compactionId: id, shadowedSeqs: [1], summary: [{ type: 'text', text: id }], shadowedTokenCount: 1 } })
  }
  const started = Date.now()
  await policy.drain()
  assert.ok(Date.now() - started < 1000)
  assert.equal(memory.core.list({ workspaceKey: memoryWorkspaceKey(root), limit: 10 }).length, 2)
  assert.equal(calls, 1, 'enhancements are capped and timeouts do not trigger more model attempts')
})

test('A01: disposal interrupts drain without waiting for an uncooperative provider', async t => {
  let started
  const entered = new Promise(r => { started = r })
  const { ctx, memory, session } = fixture(t, { async *stream() { started(); await new Promise(() => {}) } })
  await memory.enableLevel('audit', 'l3')
  const policy = registerCheckpointPolicy(ctx, memory, { cardTimeoutMs: 10000 })
  await ctx.emit('session/event', session, { seq: 1, type: 'user/message', data: { role: 'user', content: [{ type: 'text', text: 'source' }] } })
  await ctx.emit('session/event', session, { seq: 2, type: 'compaction/summary', data: { compactionId: 'dispose', shadowedSeqs: [1], summary: [{ type: 'text', text: 'summary' }] } })
  await entered
  const start = Date.now()
  policy.dispose(); await policy.drain()
  assert.ok(Date.now() - start < 1000)
})

for (const unsupported of [true, false]) {
  test(`A02: eviction ${unsupported ? 'retains unknown blocks in L1' : 'stores tool identities and original envelopes'}`, async t => {
    const { ctx, memory, session } = fixture(t, { resolveModelInfo: async () => ({ context: { contextWindow: 1000 } }) })
    await memory.enableLevel('audit', 'l3')
    const source = new Map(Array.from({ length: 8 }, (_, i) => [i + 1, { seq: i + 1, type: i === 0 ? 'system/message' : 'user/message', data: { role: 'user', content: [{ type: 'text', text: `event ${i + 1}` }] } }]))
    source.get(2).data = unsupported ? { role: 'assistant', content: [{ type: 'future-block', payload: 'KEEP_ME' }] } : { role: 'assistant', content: [{ type: 'tool-call', id: 'call-17', name: 'read', arguments: { path: 'fixture' } }] }
    source.get(3).data = { role: 'tool', content: [{ type: 'tool-result', id: 'call-17', content: 'result' }] }
    const appended = []
    session.eventAt = seq => source.get(seq)
    session.deriveEventMessage = event => event.data
    session.append = (type, data, options) => { appended.push({ type, data, options }); return { seq: 100 + appended.length } }
    ctx.tokenMeter = { measure: () => ({ totalTokens: 1600, nodes: [...source.keys()].map(seq => ({ seq, tokens: 200 })) }), estimateMessage: () => 200 }
    evict(ctx)
    await ctx.emit('agent/pre-step', { agent: { session } }, async () => ({ kind: 'enter', messages: [] }))
    if (unsupported) {
      assert.equal(appended.length, 0)
      assert.equal(memory.core.list({ limit: 10 }).length, 0)
    } else {
      assert.equal(appended.length, 2)
      const row = memory.core.list({ limit: 10 })[0]
      const body = (await memory.get(row.id)).body
      const captures = body.split('Source event JSON:\n').slice(1).map(part => JSON.parse(part.split('\n')[0]))
      assert.deepEqual(captures[0].event, source.get(2))
      assert.deepEqual(captures[1].message, source.get(3).data)
    }
  })
}
