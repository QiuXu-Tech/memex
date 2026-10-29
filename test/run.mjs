#!/usr/bin/env node
/**
 * Offline integration harness for `@qiuxu/memex`.
 *
 * The subsystem source is eight sibling packages: seam / local backend /
 * checkpoint / tools / commands / HTTP api / web ui client / **memory-evict**
 * (L1 eviction policy), plus the `@qiuxu/memex` bundle artifact (generated
 * `modules/`). The cache-level model is L1 = native context window, L2 =
 * session-private archive (10M), L3 = workspace-shared archive (100M); L2/L3
 * are independent **sticky** switches (enable-only, no disable) and L1 overflow
 * is transferred verbatim by the memory-evict row (no LLM).
 * `withInstance()` mounts the four host rows in Loader order; K1–K5 pin row
 * wiring, K6 mounts the generated bundle artifact, K7 executes the
 * classic-script client half in a `node:vm` sandbox, K8 pins the seven-row
 * bundle patch, L1 exercises the `/api/memory.*` Fetch routes with real
 * Request/Response, M1–M9 cover the sticky levels/visibility/capacities/client,
 * and N1–N6 cover the level model end-to-end incl. the L1 eviction policy and
 * bundle artifact. The cold-tier/capacity wave adds C1–C6: `archiveCold()` and
 * the hot/cold facets split, `memory_compress` (lossless `cold` tier move and
 * bounded map-reduce `digest` batches), the `[EXTRA CONTEXT CAPACITY]` notice
 * with cooldown, eviction hardening (images/oversized events/captureLevel) and
 * the ninth bundle module. The round-2 improvements add R1–R7 (R7 was a sentinel: bodyTruncated contract, now fixed): body-less FTS
 * (card fields only + hot-file body fallback + legacy migration),
 * `restoreCold`/`gcCold`, `compressCold`, per-session compression history,
 * the eight `/api/memory.*` routes (incl. compress/restore/gc + record body
 * pagination), the sixth model tool `memory_restore` (seven total with
 * `memory_compress`), `recallTerms()` extraction, the bilingual capacity
 * notice and the client 压缩/回热/⚠ UI. Phase 1+2 adds S1–S5: `memoryQueryTerms`
 * extraction, hybrid search with cold abstracts, the ninth `/api/memory.metrics`
 * route, `sensitivePolicy` eviction (secrets stay in L2 / never reach L3) and
 * the `memory-backup` backup/verify/restore round-trip. A–J remain the behavior
 * specs. Runs with the bundled Node (24.x, `node:sqlite` + FTS5) and the custom
 * ESM loader in `./register.mjs`. Nothing installs, nothing touches `~/.dsh`,
 * and every case gets its own `mkdtemp` root under `os.tmpdir()`.
 *
 * Usage (from `memory-subsystem/`):
 *
 *   NODE="/Applications/DeepSeek Harness.app/Contents/Resources/runtime/primary-runtime/dependencies/node/bin/node"
 *   "$NODE" --import ./test/register.mjs ./test/run.mjs
 *
 * Exit code is 1 when any test fails. Each test prints exactly one line:
 * `ok <id> <title>` or `FAIL <id> <title> — <message>`.
 */

import assert from 'node:assert/strict'
import { existsSync, mkdtempSync, readdirSync, readFileSync, realpathSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { spawnSync } from 'node:child_process'
import { runInNewContext } from 'node:vm'
import { DatabaseSync } from 'node:sqlite'

// Must be set before the package (its `dsh-home-paths` stub) resolves a path.
// The whole suite is offline: this directory is throwaway and never `~/.dsh`.
const stubHomeRoot = mkdtempSync(join(tmpdir(), 'memex-stub-home-'))
process.env.DSH_STUB_HOME = stubHomeRoot

// `@qiuxu/*` resolves natively through ./node_modules/@qiuxu symlinks created by
// scripts/link-workspace.sh; the loader only stubs `@deepseek-ai/*`.
const seam = await import('@qiuxu/memex-seam')
const { archiveRecordId, MEMORY_TEXT_LIMITS } = seam
const { default: LocalMemoryStore } = await import('@qiuxu/memex-local')
const checkpointRow = await import('@qiuxu/memex-checkpoint')
const toolsRow = await import('@qiuxu/memex-tool')
const commandsRow = await import('@qiuxu/memex-command')
const apiRow = await import('@qiuxu/memex-api')
// NOTE: `scripts/link-workspace.sh` has not been updated with memex-evict,
// so the workspace @qiuxu symlink is missing; import the source package directly.
const evictRow = await import('../packages/memex-evict/index.js')
// `scripts/link-workspace.sh` also lacks memex-compress; import by path.
const compressRow = await import('../packages/memex-compress/index.js')
const { LocalStoreCore } = await import('../packages/memex-local/lib/store.js')
const { buildCard } = await import('../packages/memex-checkpoint/lib/render.js')
const { createFakeContext, createLlmMock, createSessionQueryMock, formatLogs } = await import('./fake-ctx.mjs')
const {
  createSession,
  createSurfaceEvents,
  createCompactionEvent,
  workspaceKeyFor,
  createPreStepDecision,
  terminalNext,
} = await import('./fixtures.mjs')

// ── tiny runner ──────────────────────────────────────────────────────────────

/** @type {{id: string, title: string, ok: boolean, error?: Error}[]} */
const results = []
/** @type {string[]} */
const tempDirs = []
// Track the throwaway DSH home so it is removed with every other temp dir.
tempDirs.push(stubHomeRoot)

/**
 * Create a throwaway directory under the OS temp dir.
 * @param {string} label - Short label included in the directory name.
 * @returns {string} Absolute temp directory path.
 */
function makeRoot(label) {
  const root = mkdtempSync(join(tmpdir(), `memex-${label}-`))
  tempDirs.push(root)
  return root
}

/** Remove every temp directory created by this run (best effort). */
function cleanupTempDirs() {
  for (const dir of tempDirs.splice(0)) {
    try {
      rmSync(dir, { recursive: true, force: true })
    } catch {
      // Cleanup is best-effort; a leftover temp dir never fails the suite.
    }
  }
}

process.on('exit', cleanupTempDirs)

/** Thrown by a test to report a clean skip; counted as passing, printed as `ok … skipped`. */
class Skip extends Error {}

/** Run one named test, print one line and record the result. */
async function test(id, title, fn) {
  try {
    await fn()
    results.push({ id, title, ok: true })
    console.log(`ok ${id} ${title}`)
  } catch (error) {
    if (error instanceof Skip) {
      results.push({ id, title, ok: true, skipped: true })
      console.log(`ok ${id} skipped (${error.message})`)
      return
    }
    results.push({ id, title, ok: false, error })
    console.log(`FAIL ${id} ${title} — ${String(error?.message ?? error).split('\n')[0]}`)
  }
}

/** Assert that `text` contains `needle`, with a useful failure message. */
function assertIncludes(text, needle, message = '') {
  assert.ok(
    typeof text === 'string' && text.includes(needle),
    `${message || 'text must include the needle'}: expected ${JSON.stringify(needle)} in ${JSON.stringify(text)}`,
  )
}

/** Fail when the package logged unexpected warnings/errors during a test. */
function assertNoWarnings(ctx) {
  const bad = ctx.logs.filter((entry) => entry.level === 'warn' || entry.level === 'error')
  assert.equal(bad.length, 0, `unexpected package log output:\n${formatLogs(bad)}`)
}

// ── isolation helpers ────────────────────────────────────────────────────────

/**
 * Run `fn` against a fresh `LocalStoreCore` root; always closes and cleans up.
 * @param {string} label - Temp-dir label.
 * @param {(core: LocalStoreCore, root: string) => unknown} fn - Test body.
 */
async function withCore(label, fn) {
  const root = makeRoot(label)
  const core = new LocalStoreCore({ root, capacityTokens: 100_000 })
  try {
    return await fn(core, root)
  } finally {
    core.close()
    rmSync(root, { recursive: true, force: true })
  }
}

/**
 * Poll `probe` until it returns a truthy value or the timeout expires.
 *
 * The seam split removed the in-process `policy.drain()` test hook, so archive
 * completion is observed through the public async service (`wasArchived` /
 * `get`) instead of internal policy state.
 *
 * @param {() => unknown} probe - Async predicate; truthy result ends the wait.
 * @param {{timeoutMs?: number, intervalMs?: number, label?: string}} [options] - Tuning.
 * @returns {Promise<unknown>} The truthy value the probe returned.
 */
async function waitUntil(probe, options = {}) {
  const timeoutMs = options.timeoutMs ?? 3000
  const intervalMs = options.intervalMs ?? 10
  const label = options.label ?? 'condition'
  const startedAt = Date.now()
  let lastError
  while (Date.now() - startedAt < timeoutMs) {
    try {
      const value = await probe()
      if (value) return value
    } catch (error) {
      lastError = error
    }
    await new Promise((resolve) => setTimeout(resolve, intervalMs))
  }
  throw new Error(`timed out after ${timeoutMs}ms waiting for ${label}${lastError ? `: ${lastError.message}` : ''}`)
}

/** Let pending microtasks/timers settle (used to prove a negative like "nothing archived"). */
function settle(ms = 40) {
  return new Promise((resolve) => setTimeout(resolve, ms))
}

/** Wait until the backend reports a compaction archived, then let the receipt land. */
async function waitForArchive(instance, sessionId, compactionId, timeoutMs = 3000) {
  const recordId = await waitUntil(
    async () => instance.wasArchived(sessionId, compactionId),
    { timeoutMs, label: `archive ${sessionId}/${compactionId}` },
  )
  // The idempotency marker is written before the receipt is pushed; one timer
  // tick flushes the archive continuation's microtasks deterministically.
  await new Promise((resolve) => setTimeout(resolve, 10))
  return recordId
}

/**
 * Mount the four plugin rows on a fake context in the same order the Cordis
 * Loader would: backend service first, then checkpoint, tools and commands.
 *
 * @param {object} ctx - Fake context.
 * @param {{root?: string, backend?: object, checkpoint?: object, tools?: object, commands?: object}} options - Row configs.
 * @returns {{instance: object, commands: unknown}} The backend instance and the commands apply result.
 */
function mountRows(ctx, options = {}) {
  const instance = new LocalMemoryStore(ctx, {
    root: options.root,
    // Existing behavioral tests exercise archiving/injection/API, so they run
    // with L3 (workspace-shared) on by default; level tests override this to
    // 'none' / 'l2' / 'both'.
    defaultLevels: 'l3',
    ...(options.backend ?? {}),
  })
  // A real cordis `Service` registers itself as `ctx[name]`; our Service stub
  // stays minimal, so the test mounts the service explicitly right after the row.
  ctx.provideService('memory', instance)
  checkpointRow.apply(ctx, options.checkpoint ?? {})
  toolsRow.apply(ctx, options.tools ?? {})
  const commands = commandsRow.apply(ctx, options.commands ?? {})
  return { instance, commands }
}

/**
 * Run `fn` against the full four-row stack wired to a fake context.
 * @param {string} label - Temp-dir label.
 * @param {{ctx?: object, backend?: object, checkpoint?: object, tools?: object, commands?: object}} options - Fake-context and row config options.
 * @param {(context: {instance: object, ctx: object, root: string}) => unknown} fn - Test body.
 */
async function withInstance(label, options, fn) {
  const root = makeRoot(label)
  const ctx = createFakeContext(options.ctx ?? {})
  const mounted = mountRows(ctx, {
    root,
    backend: options.backend,
    checkpoint: options.checkpoint,
    tools: options.tools,
    commands: options.commands,
  })
  try {
    return await fn({ instance: mounted.instance, ctx, root })
  } finally {
    await ctx.dispose()
    rmSync(root, { recursive: true, force: true })
  }
}

/**
 * Feed the buffered live-event path: three surface events, then the compaction
 * summary, then poll the public API until the archive is visible. Returns the
 * archived record id.
 */
async function seedCompaction(instance, ctx, session, compaction = createCompactionEvent()) {
  for (const event of createSurfaceEvents()) {
    await ctx.emit('session/event', session, event)
  }
  await ctx.emit('session/event', session, compaction)
  return waitForArchive(instance, session.id, compaction.data.compactionId)
}


// ── L1 eviction fixtures (N5) ────────────────────────────────────────────────

/**
 * Create a fake session for the memory-evict row: event surface, derived
 * messages, append capture and a controllable tool-pairing balance predicate.
 */
function createEvictSession(options = {}) {
  const events = new Map()
  const appended = []
  let nextSeq = options.nextSeq ?? 100
  const eventsById = options.events ?? new Map()
  const session = {
    id: options.sessionId ?? 'sess-evict',
    header: { cwd: options.cwd ?? '/tmp/ws-evict' },
    requestHeader: () => ({ config: { provider: 'p', model: 'm' } }),
    eventAt: (seq) => eventsById.get(seq) ?? events.get(seq),
    deriveEventMessage: options.deriveEventMessage ?? ((event) => ({
      role: 'user',
      content: [{ type: 'text', text: event?.data?.text ?? event?.text ?? `event ${event?.seq}` }],
    })),
    append(type, data, appendOptions) {
      const event = { seq: nextSeq, type, data, ...(appendOptions?.data ?? {}) }
      appended.push({ type, data, options: appendOptions, seq: nextSeq })
      events.set(nextSeq, event)
      nextSeq += 1
      return { seq: nextSeq - 1 }
    },
    /** Balance predicate consumed by the dsh-compaction stub. */
    __balancedCalls: [],
    __appended: appended,
    __events: events,
  }
  const balanced = options.balancedBefore ?? (() => true)
  session.__balancedBefore = (seq) => {
    session.__balancedCalls.push(seq)
    return balanced(seq)
  }
  return session
}

/** Fake `ctx.llm` for the digest strategy: streams text, can fail on a chosen call. */
function createCompressLlm(options = {}) {
  const text = typeof options.text === 'string' ? options.text : '摘要内容\nids: mem_digest0001'
  const failAt = Number.isSafeInteger(options.failAt) ? options.failAt : Number.POSITIVE_INFINITY
  const calls = []
  return {
    calls,
    stream(streamOptions) {
      calls.push(streamOptions)
      const callNumber = calls.length
      async function* generate() {
        if (callNumber >= failAt) throw new Error('llm unavailable')
        yield { type: 'text-delta', index: 0, text: text.slice(0, Math.ceil(text.length / 2)) }
        yield { type: 'text-delta', index: 0, text: text.slice(Math.ceil(text.length / 2)) }
        yield { type: 'block-end', index: 0, block: { type: 'text', text } }
        yield { type: 'finish', usage: { inputTokens: 1, outputTokens: 1 } }
      }
      return generate()
    },
  }
}

/** Build `{nodes, totalTokens}` from `[seq, tokens, type?]` triples. */
function createMeasurement(entries) {
  const nodes = entries.map(([seq, tokens]) => ({ seq, tokens, heuristicTokens: tokens }))
  const totalTokens = nodes.reduce((sum, node) => sum + node.tokens, 0)
  return { nodes, totalTokens }
}

/**
 * Mount the real memory-evict row against a fake ctx whose `memory`,
 * `tokenMeter` and `llm` services are all captured/spied.
 */
function createEvictHarness(options = {}) {
  const listeners = []
  const writes = []
  const evictions = []
  const warnings = []
  const levels = options.levels ?? { l2: false, l3: true }
  const measurement = options.measurement ?? createMeasurement([])
  const contextWindow = options.contextWindow ?? 1000
  const memory = {
    async getLevels() {
      return { ...levels }
    },
    async write(record) {
      writes.push(record)
      return { ...record, id: record.id ?? 'l1_test' }
    },
    async recordEviction(entry) {
      evictions.push(entry)
    },
  }
  const ctx = {
    memory,
    tokenMeter: {
      measure: () => measurement,
      estimateMessage: (message) => {
        const text = (message?.content ?? []).map((block) => block.text ?? '').join('')
        return Math.max(1, Math.ceil(text.length / 4))
      },
    },
    llm: {
      async resolveModelInfo() {
        return { context: { contextWindow } }
      },
    },
    logger: {
      info() {},
      warn(message) {
        warnings.push(String(message))
      },
    },
    on(name, listener) {
      if (name === 'agent/pre-step') listeners.push(listener)
      return () => {}
    },
    effect(factory) {
      return factory()
    },
  }
  evictRow.apply(ctx, options.config ?? {})
  assert.equal(listeners.length, 1, 'memory-evict must register exactly one agent/pre-step listener')
  return {
    ctx,
    memory,
    writes,
    evictions,
    warnings,
    handler: listeners[0],
    levels,
    measurement,
    contextWindow,
  }
}

/** Run the captured pre-step listener with a terminal `next()` decision. */
function runEvictHandler(harness, session) {
  const decision = { kind: 'enter', messages: [{ role: 'user', content: [] }] }
  return harness.handler({ agent: { session }, signal: undefined }, async () => decision).then(() => decision)
}

// ── memory API fixtures (L1) ─────────────────────────────────────────────────

/** Two live sessions over distinct workspaces, as `ctx.sessions.list()` would report. */
function apiSessions() {
  return [
    { id: 'session-a', header: { cwd: '/tmp/ws-a' } },
    { id: 'session-b', header: { cwd: '/tmp/ws-b' } },
  ]
}

/**
 * Mount the local backend + the memory-api row against a fake ctx that captures
 * the four Fetch route registrations. Cleans up the temp root and context.
 */
async function withApiStack(label, optionsOrFn, maybeFn) {
  const options = typeof optionsOrFn === 'function' ? {} : (optionsOrFn ?? {})
  const fn = typeof optionsOrFn === 'function' ? optionsOrFn : maybeFn
  const root = makeRoot(label)
  const routes = []
  const sessions = options.sessions ?? apiSessions()
  const ctx = createFakeContext({
    services: {
      llm: undefined,
      connection: {
        fetch: {
          register(route) {
            routes.push(route)
            return () => {
              route.disposed = true
            }
          },
        },
      },
      sessions: { list: () => sessions },
      ...(options.services ?? {}),
    },
  })
  try {
    const backend = new LocalMemoryStore(ctx, {
      root,
      defaultLevels: 'l3',
      ...(options.backend ?? {}),
    })
    ctx.provideService('memory', backend)
    const disposersBefore = ctx.disposers.length
    apiRow.apply(ctx)
    if (options.checkpoint === true) checkpointRow.apply(ctx, options.checkpointConfig ?? {})
    if (options.tools !== false) toolsRow.apply(ctx, options.toolsConfig ?? {})
    const routeEffects = ctx.disposers.length - disposersBefore
    return await fn({ backend, ctx, routes, sessions, routeEffects, root })
  } finally {
    await ctx.dispose()
    rmSync(root, { recursive: true, force: true })
  }
}

/** Mock `commands` service that captures the registered `/memory` definition. */
function createCommandsMock() {
  const definitions = []
  return {
    definitions,
    service: {
      register(definition) {
        definitions.push(definition)
        return () => {}
      },
    },
  }
}

/** Find one registered route by its exact path. */
function apiRoute(routes, path) {
  const route = routes.find((candidate) => candidate.path === path)
  assert.ok(route, `memory API must register ${path}`)
  return route
}

/** Call one registered route with a real Node Request and parse its JSON body. */
async function apiRequest(routes, pathWithQuery, init) {
  const path = pathWithQuery.split('?')[0]
  const route = apiRoute(routes, path)
  const response = await route.fetch(new Request(`http://memory.test${pathWithQuery}`, init))
  const text = await response.text()
  let data
  try {
    data = text.length === 0 ? undefined : JSON.parse(text)
  } catch {
    throw new Error(`${path} returned non-JSON: ${text.slice(0, 120)}`)
  }
  return { response, data, text, contentType: response.headers.get('content-type') ?? '' }
}

/** POST a JSON body (or a raw string) to the status route. */
function apiPost(routes, path, payload) {
  return apiRequest(routes, path, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: typeof payload === 'string' ? payload : JSON.stringify(payload),
  })
}

/** Write `count` fact records into one workspace and return them. */
async function seedApiRecords(backend, workspaceKey, sessionId, count = 3, prefix = 'API record', scope = 'workspace') {
  const written = []
  for (let index = 0; index < count; index += 1) {
    written.push(await backend.write({
      kind: 'fact',
      title: `${prefix} ${index + 1}`,
      summary: `${prefix} summary ${index + 1}`,
      useWhen: `Read when testing ${prefix} ${index + 1}`,
      body: `alpha body ${index + 1} for ${prefix}`,
      scope,
      workspaceKey,
      sessionId,
    }))
  }
  return written
}

/** Create the search fixture: one CJK-titled record plus one ASCII-short-term record. */
function seedSearchFixture(core) {
  const smoke = core.write({
    kind: 'fact',
    title: 'Memory 子系统冒烟测试记录',
    summary: '冒烟测试摘要',
    useWhen: '当需要冒烟测试时读这条',
    body: '本记录用于冒烟测试，并包含额外上下文。',
    workspaceKey: 'wk-smoke',
    sessionId: 'sess-smoke',
  })
  const ai = core.write({
    kind: 'decision',
    title: 'AI 部署决策',
    summary: 'AI 相关决策',
    body: '决定采用 SQLite FTS5 作为索引。',
    workspaceKey: 'wk-smoke',
    sessionId: 'sess-smoke',
  })
  return { smoke, ai }
}

/** Create the filter fixture: fact, decision and open incident records in one workspace. */
function seedFilterFixture(core) {
  const fact = core.write({
    kind: 'fact',
    title: 'Memory 子系统冒烟测试记录',
    summary: '冒烟测试摘要',
    useWhen: '当需要冒烟测试时读这条',
    body: '本记录用于冒烟测试，并包含额外上下文。',
    tags: { user: ['memory', 'smoke'] },
    workspaceKey: 'wk-d',
    workspace: '/tmp/ws-d',
    sessionId: 'sess-d',
  })
  const decision = core.write({
    kind: 'decision',
    title: 'AI 决策记录',
    summary: 'AI 相关决策',
    body: '决定采用 SQLite FTS5 作为索引。',
    tags: { user: ['architecture'] },
    workspaceKey: 'wk-d',
    workspace: '/tmp/ws-d',
    sessionId: 'sess-d',
  })
  const incident = core.write({
    kind: 'incident',
    status: 'open',
    title: '端口 8787 不可用',
    body: 'ECONNREFUSED 8787 无人监听。',
    tags: { user: ['ops'] },
    workspaceKey: 'wk-d',
    workspace: '/tmp/ws-d',
    sessionId: 'sess-d',
  })
  return { fact, decision, incident }
}

/** Build one deterministic archived compaction input for case E. */
function archiveFixture(core) {
  const events = createSurfaceEvents()
  const card = buildCard({
    events,
    summaryBlocks: [{ type: 'text', text: 'Investigated ECONNREFUSED on port 8787.' }],
    shadowedTokenCount: 321,
    seqStart: 1,
    seqEnd: 3,
    sessionId: 'sess-e',
    compactionId: 'cmp-e',
    cwd: '/tmp/ws-e',
  })
  const id = archiveRecordId('sess-e', 'cmp-e')
  return {
    id,
    card,
    input: {
      sessionId: 'sess-e',
      compactionId: 'cmp-e',
      record: {
        ...card,
        id,
        workspaceKey: 'wk-e',
        workspace: '/tmp/ws-e',
        sessionId: 'sess-e',
        tokens: 321,
        trust: 'derived',
        status: 'active',
      },
    },
  }
}

// ── suite ────────────────────────────────────────────────────────────────────

console.log(`# @qiuxu/memex offline harness · Node ${process.version} · 9 source packages + bundle + 9 /api/memory.* routes + web client + sticky L2/L3 + L1 eviction + cold tier/compression + hybrid recall/cold abstracts + sensitive evict + backup · stubs: cordis, schemastery, dsh-home-paths, dsh-llm, dsh-tools, dsh-compaction`)

// A. write / get ─────────────────────────────────────────────────────────────

await test('A1', 'write then get returns the stored card fields', async () => {
  await withCore('a1', (core) => {
    const body = '# 中文事实\n\n额外上下文：端口 8787 的排查结论。'
    const stored = core.write({
      kind: 'fact',
      title: '中文事实记录',
      summary: '一条中文摘要。',
      useWhen: '需要回看中文事实时读这条。',
      body,
      tags: { user: ['中文', 'fact'] },
      workspaceKey: 'wk-a',
      workspace: '/tmp/ws-a',
      sessionId: 'sess-a',
      trust: 'trusted',
    })
    assert.match(stored.id, /^mem_[0-9a-f]{10}$/)
    assert.equal(stored.body, body)
    const record = core.get(stored.id)
    assert.ok(record, 'stored record must be readable')
    assert.equal(record.id, stored.id)
    assert.equal(record.kind, 'fact')
    assert.equal(record.title, '中文事实记录')
    assert.equal(record.summary, '一条中文摘要。')
    assert.equal(record.useWhen, '需要回看中文事实时读这条。')
    assert.deepEqual(record.tags, { user: ['中文', 'fact'] })
    assert.equal(record.trust, 'trusted')
    assert.equal(record.status, 'active')
    assert.equal(record.workspace, '/tmp/ws-a')
    assert.equal(record.sessionId, 'sess-a')
    assert.equal(typeof record.createdAt, 'number')
    assert.equal(typeof record.updatedAt, 'number')
    assert.ok(record.tokens > 0, 'token estimate must be recorded')
  })
})

await test('A2', 'record file exists on disk with YAML frontmatter', async () => {
  await withCore('a2', (core) => {
    const stored = core.write({
      kind: 'fact',
      title: '中文事实记录',
      summary: '一条中文摘要。',
      body: '# 中文事实\n\n额外上下文：端口 8787 的排查结论。',
      tags: { user: ['memory'] },
      workspaceKey: 'wk-a',
    })
    assert.ok(existsSync(stored.path), `record file must exist: ${stored.path}`)
    assert.ok(stored.path.endsWith(`${stored.id}.md`))
    assert.ok(stored.path.includes(join('records', 'wk-a')), 'record file must live under records/<workspaceKey>/')
    const text = readFileSync(stored.path, 'utf8')
    assert.ok(text.startsWith('---\n'), 'file must start with frontmatter')
    assert.match(text, /\nid: "mem_[0-9a-f]{10}"\n/)
    assert.match(text, /\nkind: "fact"\n/)
    assert.match(text, /\ntitle: "中文事实记录"\n/)
    assert.match(text, /\ntags: \{"user":\["memory"\]\}\n/)
    const closing = text.indexOf('\n---\n', 4)
    assert.ok(closing > 0, 'frontmatter must have a closing delimiter')
    assertIncludes(text.slice(closing + 5), '额外上下文', 'markdown body must follow the frontmatter')
  })
})

await test('A3', 'get returns the exact body that was written', async () => {
  await withCore('a3', (core) => {
    const body = '第一行\n\n额外上下文：端口 8787。'
    const stored = core.write({ kind: 'fact', title: '中文事实记录', body, workspaceKey: 'wk-a' })
    const record = core.get(stored.id)
    assert.ok(record)
    // Regression guard for FINDINGS.md #1 (fixed during the seam split:
    // recordBodyFromFile now strips the renderer's single trailing newline).
    assert.equal(record.body, body, 'body must round-trip byte-for-byte')
  })
})

// B. search: CJK + short terms ───────────────────────────────────────────────

await test('B1', 'search finds a 4-char CJK term in the title', async () => {
  await withCore('b1', (core) => {
    const { smoke } = seedSearchFixture(core)
    const result = core.search({ query: '冒烟测试', workspaceKey: 'wk-smoke' })
    assert.equal(result.total, 1)
    assert.equal(result.hits[0].id, smoke.id)
  })
})

await test('B2', 'search finds a 4-char CJK term that only exists in the body', async () => {
  await withCore('b2', (core) => {
    const { smoke } = seedSearchFixture(core)
    const result = core.search({ query: '额外上下文', workspaceKey: 'wk-smoke' })
    assert.equal(result.total, 1)
    assert.equal(result.hits[0].id, smoke.id)
  })
})

await test('B3', 'search falls back to LIKE for the 2-char term AI', async () => {
  await withCore('b3', (core) => {
    const { ai } = seedSearchFixture(core)
    const result = core.search({ query: 'AI', workspaceKey: 'wk-smoke' })
    assert.equal(result.total, 1, 'exactly one record contains AI')
    assert.equal(result.hits[0].id, ai.id)
  })
})

await test('B4', 'search returns no hits for nonsense', async () => {
  await withCore('b4', (core) => {
    seedSearchFixture(core)
    const result = core.search({ query: 'zzqqxx', workspaceKey: 'wk-smoke' })
    assert.equal(result.total, 0)
    assert.deepEqual(result.hits, [])
  })
})

// C. workspace isolation ─────────────────────────────────────────────────────

await test('C0a', 'search only returns records of the requested workspace (A)', async () => {
  await withCore('c1', (core) => {
    const one = core.write({ kind: 'fact', title: '共享标题 隔离测试记录', body: '隔离测试 内容 A', workspaceKey: 'wk-one', workspace: '/ws/one' })
    core.write({ kind: 'fact', title: '共享标题 隔离测试记录', body: '隔离测试 内容 B', workspaceKey: 'wk-two', workspace: '/ws/two' })
    const result = core.search({ query: '隔离测试', workspaceKey: 'wk-one' })
    assert.equal(result.total, 1)
    assert.equal(result.hits[0].id, one.id)
    assert.equal(result.hits[0].workspace, '/ws/one')
  })
})

await test('C0b', 'search only returns records of the requested workspace (B)', async () => {
  await withCore('c2', (core) => {
    core.write({ kind: 'fact', title: '共享标题 隔离测试记录', body: '隔离测试 内容 A', workspaceKey: 'wk-one', workspace: '/ws/one' })
    const two = core.write({ kind: 'fact', title: '共享标题 隔离测试记录', body: '隔离测试 内容 B', workspaceKey: 'wk-two', workspace: '/ws/two' })
    const result = core.search({ query: '隔离测试', workspaceKey: 'wk-two' })
    assert.equal(result.total, 1)
    assert.equal(result.hits[0].id, two.id)
    assert.equal(result.hits[0].workspace, '/ws/two')
  })
})

// D. filters, grep, facets, catalog, lifecycle ───────────────────────────────

await test('D1', 'list filters by kind', async () => {
  await withCore('d1', (core) => {
    const { decision } = seedFilterFixture(core)
    const listed = core.list({ workspaceKey: 'wk-d', kind: 'decision' })
    assert.deepEqual(listed.map((card) => card.id), [decision.id])
    assert.ok(listed.every((card) => card.kind === 'decision'))
  })
})

await test('D1b', 'search applies the kind filter to every hit path', async () => {
  await withCore('d1b', (core) => {
    seedFilterFixture(core)
    const { hits } = core.search({ query: '冒烟测试', workspaceKey: 'wk-d', kind: 'decision' })
    const leaked = hits.filter((hit) => hit.kind !== 'decision').map((hit) => `${hit.id}:${hit.kind}`)
    // Regression guard for FINDINGS.md #2 (fixed during the seam split: the
    // body-only fallback now forwards kind/status/sessionId to list()).
    assert.deepEqual(leaked, [], 'search kind filter must never return a different kind')
  })
})

await test('D2', 'list filters by status', async () => {
  await withCore('d2', (core) => {
    const { incident } = seedFilterFixture(core)
    const listed = core.list({ workspaceKey: 'wk-d', status: 'open' })
    assert.deepEqual(listed.map((card) => card.id), [incident.id])
    assert.equal(listed[0].status, 'open')
  })
})

await test('D2b', 'search applies the status filter to every hit path', async () => {
  await withCore('d2b', (core) => {
    seedFilterFixture(core)
    const { hits } = core.search({ query: '冒烟测试', workspaceKey: 'wk-d', status: 'open' })
    const leaked = hits.filter((hit) => hit.status !== 'open').map((hit) => `${hit.id}:${hit.status}`)
    // Regression guard for FINDINGS.md #2, see D1b.
    assert.deepEqual(leaked, [], 'search status filter must never return a different status')
  })
})

await test('D3', 'search filters by tag', async () => {
  await withCore('d3', (core) => {
    const { fact } = seedFilterFixture(core)
    const matching = core.search({ query: '冒烟', workspaceKey: 'wk-d', tags: ['smoke'] })
    assert.equal(matching.total, 1)
    assert.equal(matching.hits[0].id, fact.id)
    const wrongTag = core.search({ query: '冒烟', workspaceKey: 'wk-d', tags: ['architecture'] })
    assert.equal(wrongTag.total, 0)
  })
})

await test('D4', 'grep finds literal lines inside stored files', async () => {
  await withCore('d4', (core) => {
    const { decision, incident } = seedFilterFixture(core)
    const matches = core.grep({ pattern: 'ECONNREFUSED', workspaceKey: 'wk-d' })
    assert.equal(matches.length, 1)
    assert.equal(matches[0].id, incident.id)
    assertIncludes(matches[0].text, 'ECONNREFUSED')
    assert.ok(matches[0].line >= 1)
    const fts = core.grep({ pattern: 'sqlite', workspaceKey: 'wk-d' })
    assert.equal(fts.length, 1)
    assert.equal(fts[0].id, decision.id)
  })
})

await test('D5', 'facets reports counts, kinds, statuses and capacity', async () => {
  await withCore('d5', (core) => {
    seedFilterFixture(core)
    const facets = core.facets({ workspaceKey: 'wk-d' })
    assert.equal(facets.count, 3)
    assert.equal(facets.capacityTokens, 100_000)
    assert.equal(facets.byKind.fact, 1)
    assert.equal(facets.byKind.decision, 1)
    assert.equal(facets.byKind.incident, 1)
    assert.equal(facets.byStatus.active, 2)
    assert.equal(facets.byStatus.open, 1)
    assert.deepEqual(Object.keys(facets.byKindTokens).sort(), ['decision', 'fact', 'incident'])
    assert.equal(
      Object.values(facets.byKindTokens).reduce((sum, tokens) => sum + tokens, 0),
      facets.tokens,
      'per-kind token totals must add up to the pool total',
    )
    assert.ok(facets.tokens > 0)
    assert.ok(facets.bytes > 0)
    assert.equal(typeof facets.oldest, 'number')
    assert.equal(typeof facets.newest, 'number')
  })
})

await test('D6', 'catalog renders a bounded markdown catalog', async () => {
  await withCore('d6', (core) => {
    const { fact, incident } = seedFilterFixture(core)
    const catalog = core.catalog({ workspaceKey: 'wk-d' })
    assert.ok(catalog.startsWith('## Memory catalog'), 'catalog must start with its header')
    assert.match(catalog, /Recent:/)
    assertIncludes(catalog, fact.id)
    assertIncludes(catalog, incident.id)
    assert.match(catalog, /Capacity \(hot\): \d+ \/ 100000 tokens across 3 records \(L3 workspace-shared\)\./)
    const empty = core.catalog({ workspaceKey: 'wk-empty' })
    assert.match(empty, /no archived records in the enabled extra-context levels yet/)
  })
})

await test('D7', 'forget removes the row, the FTS entry and the markdown file', async () => {
  await withCore('d7', (core) => {
    const { decision } = seedFilterFixture(core)
    const before = core.get(decision.id)
    assert.ok(before && existsSync(before.path))
    assert.equal(core.forget(decision.id), true)
    assert.equal(core.get(decision.id), undefined)
    assert.equal(existsSync(before.path), false)
    assert.equal(core.search({ query: 'SQLite', workspaceKey: 'wk-d' }).total, 0)
    assert.equal(core.forget('mem_missing00'), false)
  })
})

await test('D8', 'setStatus updates lifecycle state and catalog pinning', async () => {
  await withCore('d8', (core) => {
    const { fact, decision } = seedFilterFixture(core)
    const pinned = core.setStatus(fact.id, 'pinned')
    assert.equal(pinned.status, 'pinned')
    const catalog = core.catalog({ workspaceKey: 'wk-d' })
    assert.match(catalog, /Pinned:/)
    assertIncludes(catalog, fact.id)
    const superseded = core.setStatus(decision.id, 'superseded')
    assert.equal(superseded.status, 'superseded')
    const listed = core.list({ workspaceKey: 'wk-d' }).map((card) => card.id)
    assert.ok(!listed.includes(decision.id), 'default list must hide superseded records')
    assert.deepEqual(core.list({ workspaceKey: 'wk-d', status: 'superseded' }).map((card) => card.id), [decision.id])
    assert.throws(() => core.setStatus(fact.id, 'nonsense'), /memory: unknown status "nonsense"/)
  })
})

await test('D9', 'markRead records read usage', async () => {
  await withCore('d9', (core) => {
    const { fact, decision } = seedFilterFixture(core)
    assert.equal(core.markRead([fact.id, decision.id]), 2)
    assert.equal(core.get(fact.id).readCount, 1)
    assert.equal(core.get(decision.id).readCount, 1)
    assert.equal(core.markRead([fact.id]), 1)
    assert.equal(core.get(fact.id).readCount, 2)
    assert.equal(typeof core.get(fact.id).lastReadAt, 'number')
    assert.equal(core.markRead(['mem_missing00']), 0)
  })
})

// E. archiveRegion idempotency ───────────────────────────────────────────────

await test('E1', 'archiveRegion persists the card, file and idempotency marker', async () => {
  await withCore('e1', (core) => {
    const { id, input, card } = archiveFixture(core)
    assert.equal(card.kind, 'episode')
    assertIncludes(card.body, '## Archived context')
    assert.match(card.title, /ECONNREFUSED/)
    const stored = core.archiveRegion(input)
    assert.equal(stored.id, id)
    assert.match(id, /^mem_[0-9a-f]{10}$/)
    assert.ok(existsSync(stored.path))
    assert.equal(core.wasArchived('sess-e', 'cmp-e'), id)
    const record = core.get(id)
    assert.ok(record)
    assert.equal(record.kind, 'episode')
    assert.equal(record.trust, 'derived')
    assert.equal(record.workspace, '/tmp/ws-e')
    assertIncludes(record.body, 'ECONNREFUSED')
    assert.equal(core.facets({ workspaceKey: 'wk-e' }).count, 1)
  })
})

await test('E2', 'archiveRegion is idempotent for the same session and compaction', async () => {
  await withCore('e2', (core) => {
    const { id, input } = archiveFixture(core)
    const first = core.archiveRegion(input)
    const second = core.archiveRegion(input)
    assert.equal(first.id, id)
    assert.equal(second.id, id)
    assert.equal(core.wasArchived('sess-e', 'cmp-e'), id)
    assert.equal(core.facets({ workspaceKey: 'wk-e' }).count, 1, 'a retried compaction must not create a second record')
    assert.equal(core.list({ workspaceKey: 'wk-e', limit: 10 }).length, 1)
    assert.ok(existsSync(first.path))
    assert.equal(core.search({ query: 'ECONNREFUSED', workspaceKey: 'wk-e' }).total, 1, 'FTS must not contain duplicate rows')
  })
})

// F. checkpoint archive + receipt injection ───────────────────────────────────

await test('F1', 'checkpoint archive creates one record for the workspace key', async () => {
  await withInstance('f1', { ctx: { services: { llm: undefined } } }, async ({ instance, ctx }) => {
    const session = createSession({ id: 'sess-1', cwd: '/tmp/ws' })
    const compaction = createCompactionEvent()
    const id = await seedCompaction(instance, ctx, session, compaction)
    assert.equal(await instance.wasArchived(session.id, compaction.data.compactionId), id)
    const record = await instance.get(id)
    assert.ok(record, 'archived record must exist')
    assert.equal(record.kind, 'episode')
    assert.equal(record.trust, 'derived')
    assert.equal(record.workspace, '/tmp/ws')
    assert.equal(record.sessionId, 'sess-1')
    assert.ok(existsSync(record.path), 'record markdown file must exist')
    assert.match(record.path, /records[\\/][0-9a-f]{16}[\\/]mem_[0-9a-f]{10}\.md$/)
    const workspaceKey = workspaceKeyFor(session)
    assert.match(workspaceKey, /^[0-9a-f]{16}$/)
    assert.equal((await instance.facets({ workspaceKey })).count, 1, 'record must belong to the session workspace key')
    assertNoWarnings(ctx)
  })
})

await test('F2', 'memory_open-style tool read returns the archived body', async () => {
  await withInstance('f2', { ctx: { services: { llm: undefined } } }, async ({ instance, ctx }) => {
    const session = createSession({ id: 'sess-1', cwd: '/tmp/ws' })
    const compaction = createCompactionEvent()
    const id = await seedCompaction(instance, ctx, session, compaction)
    const openTool = ctx.tool('memory_open')
    assert.ok(openTool, 'memory_open tool must be registered')
    const output = await openTool.execute({ id }, { agent: { session } })
    assertIncludes(output, id)
    assert.match(output, /ECONNREFUSED/)
    assert.match(output, /kind=episode/)
    assert.match(output, /when: /)
    assertNoWarnings(ctx)
  })
})

await test('F3', 'pre-step injects a checkpoint receipt for the archived record', async () => {
  await withInstance('f3', { ctx: { services: { llm: undefined } } }, async ({ instance, ctx }) => {
    const session = createSession({ id: 'sess-1', cwd: '/tmp/ws' })
    const compaction = createCompactionEvent()
    const id = await seedCompaction(instance, ctx, session, compaction)
    const decision = createPreStepDecision(session, '继续')
    const result = await ctx.emit('agent/pre-step', { agent: { session } }, terminalNext(decision))
    assert.equal(result.messages[0], decision.messages[0], 'the original decision messages come first')
    const receipts = result.messages.filter((message) => message.source?.kind === 'memory-recall' && message.source?.form === 'checkpoint')
    assert.equal(receipts.length, 1, 'exactly one checkpoint receipt must be injected')
    const receipt = receipts[0]
    assert.equal(receipt.role, 'user')
    assert.deepEqual(receipt.source.recordIds, [id])
    const text = receipt.content.filter((block) => block.type === 'text').map((block) => block.text).join('\n')
    assertIncludes(text, id)
    assert.match(text, /MEMORY CHECKPOINT/)
    assert.match(text, /memory_open/)
    assertNoWarnings(ctx)
  })
})

await test('F4', 'pre-step injects the memory catalog message', async () => {
  await withInstance('f4', { ctx: { services: { llm: undefined } } }, async ({ instance, ctx }) => {
    const session = createSession({ id: 'sess-1', cwd: '/tmp/ws' })
    await seedCompaction(instance, ctx, session, createCompactionEvent())
    const decision = createPreStepDecision(session, '继续')
    const result = await ctx.emit('agent/pre-step', { agent: { session } }, terminalNext(decision))
    const catalogs = result.messages.filter((message) => message.source?.form === 'catalog')
    assert.equal(catalogs.length, 1, 'exactly one catalog message must be injected')
    const catalog = catalogs[0]
    assert.equal(catalog.role, 'user')
    assert.equal(catalog.source.kind, 'memory-recall')
    assert.equal(catalog.source.workspaceKey, workspaceKeyFor(session))
    const text = catalog.content.filter((block) => block.type === 'text').map((block) => block.text).join('\n')
    assertIncludes(text, '## Memory catalog')
    assertNoWarnings(ctx)
  })
})

await test('F5', 'pre-step catalog is deduped by digest on the second run', async () => {
  await withInstance('f5', { ctx: { services: { llm: undefined } } }, async ({ instance, ctx }) => {
    const session = createSession({ id: 'sess-1', cwd: '/tmp/ws' })
    await seedCompaction(instance, ctx, session, createCompactionEvent())
    const decision = createPreStepDecision(session, '继续')
    const first = await ctx.emit('agent/pre-step', { agent: { session } }, terminalNext(decision))
    assert.ok(first.messages.length > decision.messages.length, 'first pre-step must inject something')
    const second = await ctx.emit('agent/pre-step', { agent: { session } }, terminalNext(decision))
    assert.equal(second.messages.length, decision.messages.length, 'second pre-step must not inject duplicates')
    assert.ok(!second.messages.some((message) => message.source?.form === 'catalog'), 'catalog must not repeat for the same digest')
    assert.ok(!second.messages.some((message) => message.source?.kind === 'memory-recall'), 'no memory message must repeat on an unchanged state')
  })
})

await test('F6', 'reconcile archives a persisted compaction discovered through sessionQuery', async () => {
  const session = createSession({ id: 'sess-r', cwd: '/tmp/ws-r' })
  const compaction = createCompactionEvent({ compactionId: 'cmp-r' })
  const ctxOptions = {
    services: { llm: undefined },
    sessionQuery: createSessionQueryMock({ 'sess-r': [...createSurfaceEvents(), compaction] }),
  }
  await withInstance('f6', { ctx: ctxOptions }, async ({ instance, ctx }) => {
    const decision = createPreStepDecision(session, '继续')
    const result = await ctx.emit('agent/pre-step', { agent: { session } }, terminalNext(decision))
    assert.equal(result.messages.length, decision.messages.length, 'nothing archived yet at injection time')
    const id = archiveRecordId(session.id, 'cmp-r')
    assert.equal(await waitUntil(async () => instance.wasArchived(session.id, 'cmp-r'), { label: 'reconciled archive' }), id)
    assert.ok(await instance.get(id), 'reconciled compaction must be archived')
    assertNoWarnings(ctx)
  })
})

// G. auto-recall ─────────────────────────────────────────────────────────────

const RECALL_QUERY = 'ECONNREFUSED 排查一下 8787 端口'

await test('G1', 'pre-step auto-recalls a relevant record for the current user text', async () => {
  await withInstance('g1', { ctx: { services: { llm: undefined } } }, async ({ instance, ctx }) => {
    const session = createSession({ id: 'sess-g', cwd: '/tmp/ws-g' })
    const record = await instance.write({
      kind: 'incident',
      title: 'ECONNREFUSED 端口 8787 排查',
      body: '连接 8787 端口被拒绝，需要排查监听进程。',
      useWhen: 'Read when ECONNREFUSED appears',
      workspaceKey: workspaceKeyFor(session),
      sessionId: session.id,
    })
    const decision = createPreStepDecision(session, RECALL_QUERY)
    const result = await ctx.emit('agent/pre-step', { agent: { session } }, terminalNext(decision))
    const recalls = result.messages.filter((message) => message.source?.form === 'recall')
    assert.equal(recalls.length, 1, 'exactly one recall message must be injected')
    const recall = recalls[0]
    assert.equal(recall.role, 'user')
    assert.equal(recall.source.kind, 'memory-recall')
    assert.deepEqual(recall.source.recordIds, [record.id])
    const text = recall.content.filter((block) => block.type === 'text').map((block) => block.text).join('\n')
    assertIncludes(text, record.id)
    assert.match(text, /MEMORY RECALL/)
  })
})

await test('G2', 'pre-step does not repeat the recall for identical user text', async () => {
  await withInstance('g2', { ctx: { services: { llm: undefined } } }, async ({ instance, ctx }) => {
    const session = createSession({ id: 'sess-g', cwd: '/tmp/ws-g' })
    const record = await instance.write({
      kind: 'incident',
      title: 'ECONNREFUSED 端口 8787 排查',
      body: '连接 8787 端口被拒绝，需要排查监听进程。',
      workspaceKey: workspaceKeyFor(session),
      sessionId: session.id,
    })
    const decision = createPreStepDecision(session, RECALL_QUERY)
    const first = await ctx.emit('agent/pre-step', { agent: { session } }, terminalNext(decision))
    assert.ok(first.messages.some((message) => message.source?.form === 'recall' && message.source.recordIds?.includes(record.id)))
    const second = await ctx.emit('agent/pre-step', { agent: { session } }, terminalNext(decision))
    assert.equal(second.messages.length, decision.messages.length, 'second pre-step must not inject a duplicate recall')
    assert.ok(!second.messages.some((message) => message.source?.form === 'recall'), 'recall must not repeat for identical text')
  })
})

// H. LLM card refinement ─────────────────────────────────────────────────────

const REFINED_CARD = {
  title: 'Better title',
  summary: 'Better summary',
  use_when: 'Read when testing',
  tags: ['a', 'b'],
  kind: 'fact',
}

await test('H1', 'llm refinement replaces the deterministic card', async () => {
  const llm = createLlmMock({ text: JSON.stringify(REFINED_CARD) })
  await withInstance('h1', { ctx: { services: { llm } }, checkpoint: { cardModel: 'auto' } }, async ({ instance, ctx }) => {
    const session = createSession({ id: 'sess-h', cwd: '/tmp/ws-h' })
    const id = await seedCompaction(instance, ctx, session, createCompactionEvent())
    // The refinement write happens after the archive marker, so poll the public
    // API for the refined card instead of reading internal policy state.
    const record = await waitUntil(
      async () => {
        const current = await instance.get(id)
        return current?.title === 'Better title' ? current : undefined
      },
      { label: 'refined card title' },
    )
    assert.ok(record)
    assert.equal(record.title, 'Better title')
    assert.equal(record.summary, 'Better summary')
    assert.equal(record.useWhen, 'Read when testing')
    assert.equal(record.kind, 'fact')
    assert.deepEqual(record.tags.card, ['a', 'b'])
    assert.equal(llm.calls.length, 1, 'exactly one refinement request must be made')
    assert.equal(llm.calls[0].provider, 'p')
    assert.equal(llm.calls[0].model, 'm')
    assert.equal(llm.calls[0].maxTokens, 600)
    assertNoWarnings(ctx)
  })
})

await test('H2', 'cardModel off keeps the deterministic card', async () => {
  const llm = createLlmMock({ text: JSON.stringify(REFINED_CARD) })
  await withInstance('h2', { ctx: { services: { llm } }, checkpoint: { cardModel: 'off' } }, async ({ instance, ctx }) => {
    const session = createSession({ id: 'sess-h2', cwd: '/tmp/ws-h2' })
    const id = await seedCompaction(instance, ctx, session, createCompactionEvent())
    const record = await instance.get(id)
    assert.ok(record)
    assert.equal(record.title, 'Fix the ECONNREFUSED failure on port 8787', 'deterministic card title must be kept')
    assert.equal(record.summary, 'Investigated ECONNREFUSED on port 8787 and found no listener.')
    assert.equal(llm.calls.length, 0, 'cardModel=off must not call the model')
    assertNoWarnings(ctx)
  })
})

// I. persistence across restart ──────────────────────────────────────────────

await test('I1', 'a second LocalStoreCore on the same root still searches and gets', async () => {
  const root = makeRoot('i1')
  const first = new LocalStoreCore({ root, capacityTokens: 50_000 })
  const written = first.write({
    kind: 'procedure',
    title: '重启后仍可检索的记录',
    summary: '持久化验证',
    body: '持久化验证 SQLite FTS5 索引。',
    workspaceKey: 'wk-i',
  })
  first.close()
  const second = new LocalStoreCore({ root, capacityTokens: 50_000 })
  try {
    const result = second.search({ query: '重启后仍可检索', workspaceKey: 'wk-i' })
    assert.equal(result.total, 1)
    assert.equal(result.hits[0].id, written.id)
    const record = second.get(written.id)
    assert.ok(record)
    assert.equal(record.title, '重启后仍可检索的记录')
    assertIncludes(record.body, '持久化验证')
    assert.equal(second.facets({ workspaceKey: 'wk-i' }).count, 1)
  } finally {
    second.close()
    rmSync(root, { recursive: true, force: true })
  }
})

// J. corrupt / oversized input guards ───────────────────────────────────────

await test('J1', 'unknown record kind throws', async () => {
  await withCore('j1', (core) => {
    assert.throws(
      () => core.write({ kind: 'bogus', title: 'x', body: 'y' }),
      (error) => error instanceof TypeError && /memory: unknown record kind "bogus"/.test(error.message),
    )
  })
})

await test('J2', 'non-string body is coerced to a string', async () => {
  await withCore('j2', (core) => {
    const stored = core.write({ kind: 'fact', title: 'non-string body', body: 12345, workspaceKey: 'wk-j' })
    const record = core.get(stored.id)
    assert.ok(record)
    // The seam split fixed the extra trailing newline (see FINDINGS.md #1).
    assert.equal(record.body, '12345', 'coerced body must round-trip exactly')
    assert.ok(record.tokens >= 1)
  })
})

await test('J2b', 'body size guard is published as 8 MiB (oversize allocation intentionally skipped)', async () => {
  assert.equal(MEMORY_TEXT_LIMITS.body, 8 * 1024 * 1024)
  // Per the harness brief we do not allocate an 8 MiB+1 string just to prove
  // the throw; the guard is `String(input.body).length > MEMORY_TEXT_LIMITS.body`
  // in LocalStoreCore.normalize (lib/store.js).
})

await test('J3', 'grep rejects invalid patterns with a clear message', async () => {
  await withCore('j3', (core) => {
    assert.throws(() => core.grep({ pattern: '[' }), (error) => /memory: invalid grep pattern/.test(error.message))
    assert.throws(() => core.grep({}), /memory: grep requires a pattern/)
  })
})

await test('J4', 'corrupt record input throws', async () => {
  await withCore('j4', (core) => {
    assert.throws(() => core.write(null), (error) => error instanceof TypeError && /memory: record must be an object/.test(error.message))
    assert.throws(() => core.write({ kind: 'fact', title: '   ', body: 'x' }), /memory: record requires a non-empty title/)
    assert.throws(() => core.setStatus('mem_missing00', 'bogus'), /memory: unknown status "bogus"/)
  })
})


// K. row wiring (source packages) + generated bundle artifact ────────────────
//
// K1–K5 mount rows from their own source packages and pin what each owns.
// K6 mounts the four rows from the generated bundle artifact (copies under
// `packages/memex/modules/`, gitignored), which is the layer the host
// loads; it skips cleanly when `node scripts/build-bundle.mjs` has not run.

const MEMORY_TOOL_NAMES = ['memory_grep', 'memory_index', 'memory_open', 'memory_restore', 'memory_search', 'memory_write']

await test('K1', 'backend row alone owns ctx.memory and registers no surfaces', async () => {
  const root = makeRoot('k1')
  const ctx = createFakeContext({ services: { llm: undefined } })
  try {
    assert.equal(typeof LocalMemoryStore, 'function', 'memex-local default export must be the backend plugin class')
    assert.equal(LocalMemoryStore.name, 'LocalMemoryStore')
    assert.match(import.meta.resolve('@qiuxu/memex-local'), /memex-local/)
    assert.match(import.meta.resolve('@qiuxu/memex-seam'), /memex-seam/)
    assert.deepEqual(LocalMemoryStore.inject, [], 'backend row must not inject other services')
    assert.deepEqual(Object.keys(LocalMemoryStore.Config.properties), ['root', 'capacityTokens', 'sessionCapacityTokens', 'defaultLevels', 'settingsTtlDays'])
    const instance = new LocalMemoryStore(ctx, { root })
    ctx.provideService('memory', instance)
    assert.equal(ctx.get('memory'), instance, 'backend must own the memory service')
    assert.equal(ctx.memory, instance, 'ctx.memory property must expose the service')
    assert.equal(instance.root, root)
    assert.equal(instance.config.root, root)
    for (const method of ['write', 'get', 'search', 'list', 'grep', 'facets', 'catalog', 'forget', 'setStatus', 'markRead', 'getLevels', 'enableLevel', 'getMode', 'setMode', 'archiveCold', 'restoreCold', 'compressCold', 'gcCold', 'recordCompression', 'compressionStats', 'recordEviction', 'evictionStats', 'wasArchived', 'archiveRegion', 'flush']) {
      assert.equal(LocalMemoryStore.prototype[method].constructor.name, 'AsyncFunction', `${method} must be async on the ctx.memory seam`)
    }
    assert.deepEqual(ctx.defs, [], 'backend row must register no tools')
    assert.deepEqual(ctx.sections, [], 'backend row must register no prompt sections')
    assert.equal(Object.keys(ctx.listeners).length, 0, 'backend row must register no event listeners')
  } finally {
    await ctx.dispose()
    rmSync(root, { recursive: true, force: true })
  }
})

await test('K2', 'checkpoint row alone registers the policy listeners and no surfaces', async () => {
  const ctx = createFakeContext({ services: { llm: undefined } })
  try {
    ctx.provideService('memory', {}) // injected dependency; policy methods are not called here
    checkpointRow.apply(ctx, {})
    assert.deepEqual(
      Object.keys(ctx.listeners).sort(),
      ['agent/pre-step', 'session/disposed', 'session/event'],
      'checkpoint row must register exactly the three policy listeners',
    )
    for (const eventName of ['agent/pre-step', 'session/disposed', 'session/event']) {
      assert.equal(ctx.listeners[eventName].length, 1, `${eventName} listener count`)
    }
    assert.deepEqual(ctx.defs, [], 'checkpoint row must register no tools')
    assert.deepEqual(ctx.sections, [], 'checkpoint row must register no prompt sections')
    assert.equal(checkpointRow.name, 'memory-checkpoint')
    assert.deepEqual(checkpointRow.inject, ['memory'])
    assert.deepEqual(Object.keys(checkpointRow.Config.properties), ['autoArchive', 'autoRecall', 'catalogMaxChars', 'recallMaxChars', 'cardModel', 'capacityNoticeRatio', 'capacityNoticeCooldownMs'])
  } finally {
    await ctx.dispose()
  }

  // autoArchive: false disables the whole policy row (no listeners at all).
  const disabledCtx = createFakeContext({ services: { llm: undefined } })
  try {
    disabledCtx.provideService('memory', {})
    checkpointRow.apply(disabledCtx, { autoArchive: false })
    assert.equal(Object.keys(disabledCtx.listeners).length, 0, 'autoArchive:false must not register listeners')
  } finally {
    await disabledCtx.dispose()
  }
})

await test('K3', 'tools row registers exactly six memory_* tools and one tool:memory section', async () => {
  const ctx = createFakeContext({ services: { llm: undefined } })
  try {
    ctx.provideService('memory', {}) // tool bodies are not executed here
    toolsRow.apply(ctx, { maxInlineChars: 5000 })
    assert.deepEqual(ctx.defs.map((definition) => definition.name).sort(), MEMORY_TOOL_NAMES)
    assert.ok(ctx.defs.every((definition) => typeof definition.execute === 'function'), 'every tool needs an execute function')
    assert.equal(ctx.sections.length, 1, 'tools row registers exactly one prompt section')
    assert.equal(ctx.sections[0].name, 'tool:memory')
    assert.equal(ctx.sections[0].order, 950)
    assertIncludes(ctx.sections[0].text, '## Memory')
    assert.equal(Object.keys(ctx.listeners).length, 0, 'tools row must register no listeners')
    assert.equal(toolsRow.name, 'memory-tools')
    assert.deepEqual(toolsRow.inject, ['tools', 'systemPrompt', 'memory'])
    assert.deepEqual(Object.keys(toolsRow.Config.properties), ['maxInlineChars'])
  } finally {
    await ctx.dispose()
  }
})

await test('K4', 'commands row registers /memory with sticky-level control and is inert without one', async () => {
  let commandDisposed = 0
  const registered = []
  const commandsService = {
    register(definition) {
      registered.push(definition)
      return () => {
        commandDisposed += 1
      }
    },
  }
  let levels = { l2: false, l3: false }
  const enabled = []
  const memoryStub = {
    root: '/tmp/memory-root',
    async getLevels() {
      return { ...levels }
    },
    async enableLevel(_sessionId, level) {
      enabled.push(level)
      levels = { ...levels, [level]: true }
      return { ...levels }
    },
    async evictionStats() {
      return { count: 2, tokens: 1234 }
    },
    async compressionStats() {
      return { count: 0, recent: [] }
    },
    async facets() {
      return { count: 0, tokens: 0, capacityTokens: 100_000_000, sessionCapacityTokens: 10_000_000, bytes: 0, byKind: {}, byKindTokens: {}, byStatus: {} }
    },
  }
  const ctx = createFakeContext({ services: { llm: undefined, commands: commandsService } })
  try {
    ctx.provideService('memory', memoryStub)
    commandsRow.apply(ctx)
    assert.equal(registered.length, 1, 'commands row must register exactly one command')
    assert.equal(registered[0].name, 'memory')
    assert.equal(registered[0].definitionId, '@qiuxu/memex/commands/memory')
    assert.equal(typeof registered[0].handler, 'function')
    const invocation = { agent: { session: { id: 'sess-k', header: { cwd: '/tmp/ws-k' } } } }
    const status = await registered[0].handler({ ...invocation, rawInput: 'status' })
    assert.equal(status.kind, 'success')
    assertIncludes(status.text, 'Cache levels: L1 = model context window')
    assertIncludes(status.text, 'L2: off — 0 hot / 0 cold records, ~0 hot + 0 cold / 10000000 capacity tokens.')
    assertIncludes(status.text, 'L3: off — 0 hot / 0 cold records, ~0 hot + 0 cold / 100000000 capacity tokens.')
    assertIncludes(status.text, 'L1 evicted to L2/L3: 2 batches, ~1234 tokens.')
    assertIncludes(status.text, 'Compression runs: 0')
    assertIncludes(status.text, 'Store: /tmp/memory-root')

    const onL2 = await registered[0].handler({ ...invocation, rawInput: 'on l2' })
    assert.equal(onL2.kind, 'success')
    assertIncludes(onL2.text, 'Enabled: L2 (session-private), sticky')
    assertIncludes(onL2.text, 'cannot be disabled')
    assert.deepEqual(enabled, ['l2'])
    const statusAfter = await registered[0].handler({ ...invocation, rawInput: 'status' })
    assertIncludes(statusAfter.text, 'L2: ON (sticky)')

    const onBoth = await registered[0].handler({ ...invocation, rawInput: 'on both' })
    assert.equal(onBoth.kind, 'success')
    assertIncludes(onBoth.text, 'L2 (session) + L3 (workspace)')
    assert.deepEqual(enabled, ['l2', 'l2', 'l3'])

    const off = await registered[0].handler({ ...invocation, rawInput: 'off' })
    assert.equal(off.kind, 'error')
    assertIncludes(off.text, 'sticky')
    const badOn = await registered[0].handler({ ...invocation, rawInput: 'on everything' })
    assert.equal(badOn.kind, 'error')
    assertIncludes(badOn.text, 'Usage: /memory on l2|l3|both')

    assert.deepEqual(ctx.defs, [], 'commands row must register no model tools')
    assert.deepEqual(ctx.sections, [], 'commands row must register no prompt sections')
    assert.equal(commandsRow.name, 'memory-commands')
    assert.deepEqual(commandsRow.inject, ['memory'])
    assert.equal(ctx.disposers.length, 1, 'commands row must register its command disposer through ctx.effect')
  } finally {
    await ctx.dispose()
  }
  assert.equal(commandDisposed, 1, 'unloading the commands row must dispose the registered command')

  // Without a commands service the row is a documented no-op.
  const headlessCtx = createFakeContext({ services: { llm: undefined } })
  try {
    headlessCtx.provideService('memory', memoryStub)
    assert.equal(commandsRow.apply(headlessCtx), undefined, 'commands row must no-op without a commands service')
    assert.equal(Object.keys(headlessCtx.listeners).length, 0)
    assert.deepEqual(headlessCtx.defs, [])
  } finally {
    await headlessCtx.dispose()
  }
})

await test('K5', 'consumer modules use ctx.memory only, and the loader stubs only @deepseek-ai/*', async () => {
  const consumerFiles = [
    'memex-tool/lib/tools.js',
    'memex-tool/index.js',
    'memex-checkpoint/lib/checkpoint.js',
    'memex-checkpoint/index.js',
    'memex-command/lib/commands.js',
    'memex-command/index.js',
    'memex-evict/index.js',
    'memex-compress/index.js',
  ]
  for (const fileName of consumerFiles) {
    const url = new URL(`../packages/${fileName}`, import.meta.url)
    const text = readFileSync(url, 'utf8')
    assert.doesNotMatch(text, /\.store\b/, `${fileName} must not reference .store (ctx.memory seam only)`)
    assert.doesNotMatch(text, /\.core\b/, `${fileName} must not reference .core (ctx.memory seam only)`)
    assert.ok(text.includes('memory'), `${fileName} should reference the memory service`)
  }
  // The public repo has no node_modules: the loader resolves @qiuxu/* to the
  // source/generated entries, and must keep stubbing only the DSH packages.
  const loaderSource = readFileSync(new URL('./loader.mjs', import.meta.url), 'utf8')
  assert.ok(loaderSource.includes("'@qiuxu/memex-seam':"), 'loader must resolve @qiuxu packages without node_modules')
  const stubsBlock = loaderSource.slice(loaderSource.indexOf('const STUBS = {'), loaderSource.indexOf('}', loaderSource.indexOf('const STUBS = {')))
  const stubbed = [...stubsBlock.matchAll(/'(?<specifier>@[^']+)'\s*:/g)].map((match) => match.groups.specifier)
  assert.ok(stubbed.length >= 6, 'loader must define the six DSH stubs')
  assert.ok(stubbed.every((specifier) => specifier.startsWith('@deepseek-ai/')), `loader may only stub @deepseek-ai/*, got ${stubbed.join(', ')}`)

  // memory-api row: service-mediated only; it must not reach into the store.
  const apiSource = readFileSync(new URL('../packages/memex-api/index.js', import.meta.url), 'utf8')
  const apiImports = [...apiSource.matchAll(/^import .* from '([^']+)'/gm)].map((match) => match[1])
  assert.deepEqual(apiImports, ['@qiuxu/memex-seam'], 'memory-api may only import the seam package')
  assert.doesNotMatch(apiSource, /lib\/store|LocalStoreCore/, 'memory-api must not import the store implementation')
  const evictSource = readFileSync(new URL('../packages/memex-evict/index.js', import.meta.url), 'utf8')
  const evictImports = [...evictSource.matchAll(/^import .* from '([^']+)'/gm)].map((match) => match[1])
  assert.deepEqual(evictImports.sort(), [
    '@deepseek-ai/dsh-compaction',
    '@deepseek-ai/dsh-llm',
    '@deepseek-ai/schemastery',
    '@qiuxu/memex-seam',
    'node:crypto',
  ].sort(), 'memory-evict may only import the seam, the compaction/llm helpers and node:crypto')
  assert.doesNotMatch(evictSource, /lib\/store|LocalStoreCore|\.store\b/, 'memory-evict must not reach into the store')
  assert.match(apiSource, /ctx\.connection\.fetch\.register/, 'memory-api must register through ctx.connection.fetch')
  assert.match(apiSource, /ctx\.sessions\.list/, 'memory-api must resolve identity through ctx.sessions.list')
  assert.match(apiSource, /ctx\.memory\b/, 'memory-api must talk to ctx.memory only')

  // memory-ui client half: classic module id matches the package name, and the
  // manifest declares a web client + the ./client export.
  const uiManifest = JSON.parse(readFileSync(new URL('../packages/memex-ui/package.json', import.meta.url), 'utf8'))
  assert.equal(uiManifest.name, '@qiuxu/memex-ui')
  assert.equal(uiManifest.dsh?.client?.platform, 'web', 'memory-ui must declare dsh.client.platform=web')
  assert.equal(uiManifest.exports['./client'], './client.js')
  const uiClientSource = readFileSync(new URL('../packages/memex-ui/client.js', import.meta.url), 'utf8')
  assertIncludes(uiClientSource, `id: '${uiManifest.name}'`, 'client module id must match the package name')
  const uiHostSource = readFileSync(new URL('../packages/memex-ui/index.js', import.meta.url), 'utf8')
  assert.match(uiHostSource, /export function apply\(\)/, 'memory-ui host entry must stay a no-op apply')
})


// Bundle artifact: `packages/memex` is a pure bundle whose runtime modules
// are generated copies of the seven source packages under `modules/`. The
// directory is gitignored, so a fresh checkout skips K6/K8's artifact checks
// instead of failing.
const bundleRootUrl = new URL('../packages/memex/', import.meta.url)
const bundleModulesUrl = new URL('modules/', bundleRootUrl)
const bundleBuilt = existsSync(new URL('memory-local/index.js', bundleModulesUrl))

await test('K6', 'generated bundle modules mount as four rows end-to-end', async () => {
  if (!bundleBuilt) {
    throw new Skip('bundle not built')
  }

  const bundleExpectations = [
    ['memory-core', '@qiuxu/memex-core'],
    ['memory-seam', '@qiuxu/memex-seam'],
    ['memory-local', '@qiuxu/memex-local'],
    ['memory-checkpoint', '@qiuxu/memex-checkpoint'],
    ['memory-tool', '@qiuxu/memex-tool'],
    ['memory-command', '@qiuxu/memex-command'],
    ['memory-api', '@qiuxu/memex-api'],
    ['memory-ui', '@qiuxu/memex-ui'],
    ['memory-evict', '@qiuxu/memex-evict'],
    ['memory-compress', '@qiuxu/memex-compress'],
  ]

  // The bundle root itself is code-free: it only carries patch/locale/icon.
  const bundleRootModule = await import('@qiuxu/memex')
  assert.deepEqual(Object.keys(bundleRootModule), [], 'bundle index.js must be code-free (export {})')

  for (const [dir, packageName] of bundleExpectations) {
    const moduleDir = new URL(`${dir}/`, bundleModulesUrl)
    assert.ok(existsSync(new URL('index.js', moduleDir)), `${dir}/index.js must exist in the generated bundle`)
    const manifest = JSON.parse(readFileSync(new URL('package.json', moduleDir), 'utf8'))
    assert.equal(manifest.name, packageName, `${dir}/package.json must keep the source package name`)
    const symlinkUrl = new URL(`node_modules/${packageName}/`, bundleRootUrl)
    assert.ok(existsSync(symlinkUrl), `bundle symlink for ${packageName} must resolve`)
    const real = realpathSync(symlinkUrl).replaceAll('\\', '/')
    assert.ok(real.includes(`/modules/${dir}`), `${packageName} symlink must point at modules/${dir} (got ${real})`)
    assert.equal(manifest.dependencies, undefined, `${dir}/package.json must drop source file: deps inside the bundle`)
    if (dir === 'memory-ui') {
      assert.ok(existsSync(new URL('client.js', moduleDir)), 'memory-ui/client.js must be copied into the bundle')
    }
  }

  // The bundle manifest routes the two new rows through package subpaths.
  const bundleManifest = JSON.parse(readFileSync(new URL('package.json', bundleRootUrl), 'utf8'))
  assert.equal(bundleManifest.exports['./api'], './modules/memory-api/index.js')
  assert.equal(bundleManifest.exports['./ui'], './modules/memory-ui/index.js')
  assert.equal(bundleManifest.exports['./evict'], './modules/memory-evict/index.js')
  assert.equal(bundleManifest.exports['./compress'], './modules/memory-compress/index.js')

  // Import the generated runtime modules by their bundle paths: these are the
  // copies a host would load, resolving @qiuxu/* inside the bundle root.
  const bundleSeam = await import(new URL('memory-seam/index.js', bundleModulesUrl).href)
  const bundleLocal = await import(new URL('memory-local/index.js', bundleModulesUrl).href)
  const bundleCheckpoint = await import(new URL('memory-checkpoint/index.js', bundleModulesUrl).href)
  const bundleTool = await import(new URL('memory-tool/index.js', bundleModulesUrl).href)
  const bundleCommand = await import(new URL('memory-command/index.js', bundleModulesUrl).href)
  assert.equal(typeof bundleLocal.default, 'function', 'bundle backend module default export must be the plugin class')
  assert.equal(bundleCheckpoint.name, 'memory-checkpoint')
  assert.equal(bundleTool.name, 'memory-tools')
  assert.equal(bundleCommand.name, 'memory-commands')
  const bundleApi = await import(new URL('memory-api/index.js', bundleModulesUrl).href)
  const bundleUiHost = await import(new URL('memory-ui/index.js', bundleModulesUrl).href)
  const bundleEvict = await import(new URL('memory-evict/index.js', bundleModulesUrl).href)
  assert.equal(bundleEvict.name, 'memory-evict')
  assert.deepEqual(bundleEvict.inject, ['memory', 'tokenMeter', 'llm'])
  assert.deepEqual(Object.keys(bundleEvict.Config.properties), ['evictAtRatio', 'retainRatio', 'maxChars', 'captureLevel', 'sensitivePolicy'])
  assert.equal(typeof bundleEvict.apply, 'function')
  const bundleCompress = await import(new URL('memory-compress/index.js', bundleModulesUrl).href)
  assert.equal(bundleCompress.name, 'memory-compress')
  assert.deepEqual(bundleCompress.inject, ['memory', 'llm', 'tools'])
  assert.deepEqual(Object.keys(bundleCompress.Config.properties), ['batchRecords', 'batchChars', 'maxBatches', 'minAgeMs', 'minDigestTokens', 'coldQuotaTokens'])
  assert.equal(typeof bundleCompress.apply, 'function')
  assert.equal(bundleApi.name, 'memory-api')
  assert.deepEqual(bundleApi.inject, ['memory', 'connection', 'sessions'])
  assert.equal(typeof bundleApi.apply, 'function')
  assert.equal(bundleUiHost.name, 'memory-ui')
  assert.equal(typeof bundleUiHost.apply, 'function')
  assertIncludes(readFileSync(new URL('memory-ui/client.js', bundleModulesUrl), 'utf8'), "id: '@qiuxu/memex-ui'")
  // The bundle carries its own seam copy: internal @qiuxu imports must resolve
  // inside the bundle root, not back to the workspace source packages.
  assert.notEqual(bundleSeam.MemoryStore, seam.MemoryStore, 'bundle modules must resolve their own seam copy')
  // The package subpath exports must point at those same generated modules.
  const viaSubpath = await import('@qiuxu/memex/local')
  assert.equal(viaSubpath.default, bundleLocal.default, 'bundle ./local subpath must export the generated module')

  // Mount the four generated rows like the Loader would, then prove the
  // end-to-end checkpoint flow (archive → receipt → catalog) works on the
  // bundle layer, not just on the source packages.
  const root = makeRoot('k6')
  const ctx = createFakeContext({ services: { llm: undefined } })
  try {
    const instance = new bundleLocal.default(ctx, { root, defaultMode: 'workspace' })
    ctx.provideService('memory', instance)
    assert.ok(instance instanceof bundleSeam.MemoryStore, 'bundle backend must extend the bundle seam MemoryStore')
    bundleCheckpoint.apply(ctx, {})
    bundleTool.apply(ctx, {})
    bundleCommand.apply(ctx, {})
    assert.deepEqual(ctx.defs.map((definition) => definition.name).sort(), MEMORY_TOOL_NAMES)
    assert.equal(ctx.sections.length, 1)
    assert.equal(ctx.sections[0].name, 'tool:memory')

    const session = createSession({ id: 'sess-k6', cwd: '/tmp/ws-k6' })
    const compaction = createCompactionEvent({ compactionId: 'cmp-k6' })
    const id = await seedCompaction(instance, ctx, session, compaction)
    assert.equal(await instance.wasArchived(session.id, 'cmp-k6'), id)
    const record = await instance.get(id)
    assert.ok(record, 'bundle rows must archive one record')
    assert.ok(existsSync(record.path), 'bundle archive must write the markdown file')
    assertIncludes(record.body, 'ECONNREFUSED')

    const decision = createPreStepDecision(session, '继续')
    const result = await ctx.emit('agent/pre-step', { agent: { session } }, terminalNext(decision))
    const receipts = result.messages.filter((message) => message.source?.form === 'checkpoint')
    assert.equal(receipts.length, 1, 'bundle checkpoint row must inject one receipt')
    assert.deepEqual(receipts[0].source.recordIds, [id])
    const catalog = result.messages.find((message) => message.source?.form === 'catalog')
    assert.ok(catalog, 'bundle checkpoint row must inject the catalog')
    const catalogText = catalog.content.filter((block) => block.type === 'text').map((block) => block.text).join('\n')
    assertIncludes(catalogText, '## Memory catalog')
    assertIncludes(catalogText, id)

    const openTool = ctx.tool('memory_open')
    const output = await openTool.execute({ id }, { agent: { session } })
    assertIncludes(output, id)
    assertIncludes(output, 'ECONNREFUSED')
    assertNoWarnings(ctx)
  } finally {
    await ctx.dispose()
    rmSync(root, { recursive: true, force: true })
  }
})


// K7. web client half: classic script → Slots + style + context-ring bridge ──
//
// `client.js` is a browser classic script handed to `window.__ModuleLoader__`;
// there is no build step in this harness, so it is executed verbatim in a
// `node:vm` sandbox with a minimal React/document/fetch/DOM surface.

const uiPackageUrl = new URL('../packages/memex-ui/', import.meta.url)
const uiPackageManifest = JSON.parse(readFileSync(new URL('package.json', uiPackageUrl), 'utf8'))
const uiClientSource = readFileSync(new URL('client.js', uiPackageUrl), 'utf8')

/**
 * Execute the client module once in a `node:vm` sandbox and apply the returned
 * plugin against a fake slots/uiSession context.
 * @param {object} indexPayload - `/api/memory.index` JSON the fake fetch returns.
 * @returns {object} Harness handles for assertions.
 */
function runClientPlugin(indexPayload) {
  let definition
  const appended = []
  const appendedArc = []
  const removed = []
  const meterButton = {
    dataset: {},
    getAttribute(name) {
      if (name === 'aria-label') return '上下文已用 42%'
      if (name === 'aria-expanded') return 'false'
      return null
    },
    setAttribute(name, value) {
      this.dataset[`attr:${name}`] = value
    },
  }
  const meterSvg = {
    querySelector() { return null },
    appendChild(node) { appendedArc.push(node) },
  }
  meterButton.querySelector = (selector) => (selector.includes('svg') ? meterSvg : null)
  const documentStub = {
    baseURI: 'http://127.0.0.1:60197/',
    createElement(tagName) {
      return {
        tagName,
        dataset: {},
        textContent: '',
        style: {},
        setAttribute(name, value) { this.dataset[`attr:${name}`] = value },
        remove() { removed.push(this.tagName) },
      }
    },
    createElementNS(namespace, tagName) {
      return {
        namespace,
        tagName,
        dataset: {},
        style: {},
        attrs: {},
        setAttribute(name, value) { this.attrs[name] = value },
        remove() { removed.push(tagName) },
      }
    },
    querySelectorAll(selector) {
      if (selector === 'button[aria-haspopup="dialog"]') return [meterButton]
      return []
    },
    head: { appendChild(element) { appended.push(element) } },
    addEventListener() {},
    removeEventListener() {},
  }
  const keydownListeners = new Map()
  const fetchCalls = []
  const windowStub = {
    __ModuleLoader__: { load(captured) { definition = captured } },
    addEventListener(name, listener) { keydownListeners.set(name, listener) },
    removeEventListener(name) { keydownListeners.delete(name) },
    setInterval() { return 1 },
    clearInterval() {},
    setTimeout(callback, delay) { return setTimeout(callback, delay) },
    clearTimeout(id) { clearTimeout(id) },
  }
  const reactMock = {
    createElement(type, props, ...children) { return { type, props, children } },
    Fragment: Symbol('React.Fragment'),
    useState(initial) { return [initial, () => {}] },
    useEffect() {},
    useRef(value) { return { current: value } },
    useLayoutEffect() {},
  }
  const fetchMock = async (url, init) => {
    fetchCalls.push({ url: String(url), init })
    if (String(url).startsWith('api/memory.level')) {
      const requested = init?.body !== undefined ? JSON.parse(init.body).level : 'l2'
      const levels = { ...indexPayload.levels, [requested]: true }
      const captureScope = levels.l3 === true ? 'workspace' : levels.l2 === true ? 'session' : null
      return new Response(JSON.stringify({ ok: true, levels, captureScope }), { headers: { 'content-type': 'application/json' } })
    }
    return new Response(JSON.stringify(indexPayload), { headers: { 'content-type': 'application/json' } })
  }
  const sandbox = {
    window: windowStub,
    document: documentStub,
    fetch: fetchMock,
    console,
    setTimeout,
    clearTimeout,
  }
  runInNewContext(uiClientSource, sandbox)

  assert.ok(definition, 'client.js must call window.__ModuleLoader__.load')
  const required = []
  const plugin = definition.factory((specifier) => {
    required.push(specifier)
    assert.equal(specifier, 'react', 'the client module may only require react')
    return reactMock
  })
  const slotInjects = []
  const slotRegistrations = []
  const effects = []
  const fakeCtx = {
    uiSession: {
      adapter: {
        current: {
          getSnapshot: () => ({ key: 'session-k7' }),
          subscribe: () => () => {},
        },
      },
    },
    effect(factory, label) {
      const dispose = factory()
      effects.push({ label, dispose })
      return dispose
    },
    slots: {
      inject(name, register) {
        slotInjects.push(name)
        register()
      },
      register(slotDefinition, component) {
        slotRegistrations.push({ definition: slotDefinition, component })
      },
    },
  }
  plugin.apply(fakeCtx)
  return {
    definition,
    plugin,
    required,
    document: documentStub,
    window: windowStub,
    meterButton,
    appended,
    appendedArc,
    removed,
    fetchCalls,
    effects,
    slotInjects,
    slotRegistrations,
    reactMock,
  }
}

/** The `/api/memory.index` shape the panel/ring expect for one sticky-level set. */
function indexPayloadForLevels(levels, tokens = 1000, capacityTokens = 100_000_000) {
  const l2 = levels?.l2 === true
  const l3 = levels?.l3 === true
  const captureScope = l3 ? 'workspace' : l2 ? 'session' : null
  return {
    ok: true,
    levels: { l2, l3 },
    captureScope,
    tokens,
    capacityTokens,
    count: 1,
    byKind: { fact: 1 },
    byKindTokens: { fact: tokens },
    byStatus: { active: 1 },
    l1Evicted: { count: 2, tokens: 3456 },
    l2: { enabled: l2, tokens: l2 ? tokens : 0, count: l2 ? 1 : 0, capacityTokens: 10_000_000 },
    l3: { enabled: l3, tokens: l3 ? tokens : 0, count: l3 ? 1 : 0, capacityTokens: 100_000_000 },
    scope: { sessionId: 'session-k7', cwd: '/tmp/ws-k7', workspaceKey: 'wk-k7' },
    records: [],
  }
}

await test('K7', 'client module registers composer trigger + shell overlay panel slots', async () => {
  const harness = runClientPlugin(indexPayloadForLevels({ l2: false, l3: true }, 1_000_000, 100_000_000))
  const sourceText = uiClientSource

  // Classic-script shape: no ESM statements, no top-level JSX, loader handoff.
  assert.doesNotMatch(sourceText, /^\s*import\b/m, 'client.js must not use ESM import statements')
  assert.doesNotMatch(sourceText, /^\s*export\b/m, 'client.js must not use ESM export statements')
  assert.doesNotMatch(sourceText, /^\s*</m, 'client.js must not contain top-level JSX')
  assert.match(sourceText, /window\.__ModuleLoader__\.load\(/)

  assert.equal(harness.definition.id, '@qiuxu/memex-ui')
  assert.equal(harness.definition.id, uiPackageManifest.name, 'client module id must match its package name')
  assert.equal(typeof harness.definition.factory, 'function')
  assert.deepEqual(harness.required, ['react'])
  assert.deepEqual([...harness.plugin.inject], ['slots', 'uiSession'])
  assert.equal(typeof harness.plugin.apply, 'function')

  assert.deepEqual(harness.slotInjects, ['conversation.input.left', 'shell.overlay'])
  assert.equal(harness.slotRegistrations.length, 2, 'apply must register exactly two slots')
  const [trigger, panel] = harness.slotRegistrations
  assert.deepEqual({ ...trigger.definition }, { name: 'conversation.input.left', id: 'memory-panel-trigger', order: 30 })
  assert.equal(typeof trigger.component, 'function', 'trigger slot needs a React component')
  assert.deepEqual({ ...panel.definition }, { name: 'shell.overlay', id: 'memory-panel', order: 10 })
  assert.equal(typeof panel.component, 'function', 'panel slot needs a React component')

  assert.deepEqual(harness.effects.map((entry) => entry.label), ['memory-panel: styles', 'memory-panel: context ring bridge'])
  assert.equal(harness.appended.length, 1, 'the style effect must append one <style> tag')
  assert.equal(harness.appended[0].tagName, 'style')
  assert.equal(harness.appended[0].dataset.plugin, '@qiuxu/memex-ui')
  assertIncludes(harness.appended[0].textContent, '.memex-panel')

  // The ring bridge fetches the archive reading asynchronously, then decorates
  // the fake composer ContextMeter: an inner memory arc inside its 14px ring
  // plus a level suffix on the meter's aria-label.
  await settle(15)
  assert.equal(harness.fetchCalls.length >= 1, true, 'the bridge must read /api/memory.index')
  assert.ok(harness.fetchCalls[0].url.startsWith('api/memory.index?sessionId=session-k7'))
  assert.equal(harness.appendedArc.length, 1, 'the bridge must add exactly one inner memory arc')
  assert.equal(harness.appendedArc[0].namespace, 'http://www.w3.org/2000/svg')
  assert.equal(harness.appendedArc[0].attrs['data-memex-arc'], '')
  assert.equal(harness.appendedArc[0].attrs.stroke, 'var(--dsw-alias-brand-primary, #4c6fff)', 'L3 capture paints the brand-blue arc')
  const innerCircumference = 2 * Math.PI * 3.2
  const percent = (1_000_000 / 100_000_000) * 100
  assert.equal(
    harness.appendedArc[0].attrs['stroke-dasharray'],
    `${(innerCircumference * percent) / 100} ${innerCircumference}`,
  )
  assertIncludes(String(harness.meterButton.dataset['attr:aria-label']), '（L3）')
  assertIncludes(String(harness.meterButton.dataset['attr:aria-label']), '额外上下文')

  // Both effects must dispose cleanly (intervals cleared, injected nodes removed).
  assert.doesNotThrow(() => harness.effects[1].dispose())
  harness.effects[0].dispose()
  assert.deepEqual(harness.removed, ['style'], 'disposing the style effect must remove the <style> tag')

  // The panel talks to the host through document-relative API paths (no leading slash).
  for (const route of ['api/memory.index', 'api/memory.record', 'api/memory.search', 'api/memory.status', 'api/memory.level']) {
    assertIncludes(sourceText, route)
  }
  assert.doesNotMatch(sourceText, /['"]\/api\/memory\./, 'client fetch paths must stay document-relative')
})

// K8. bundle patch: eight rows, client half addressed by a file: module URL ──

await test('K8', 'bundle patch declares eight rows including memory-compress', async () => {
  const patchText = readFileSync(new URL('../packages/memex/cordis.patch.yml', import.meta.url), 'utf8')
  const rows = [...patchText.matchAll(/^\s*-\s+id:\s*([\w-]+)\s*\n\s+name:\s*'([^']+)'/gm)]
    .map((match) => ({ id: match[1], name: match[2] }))
  assert.equal(rows.length, 8, `bundle patch must insert eight rows (got ${rows.map((row) => row.id).join(', ')})`)
  assert.deepEqual(
    rows.map((row) => row.id),
    ['memory', 'memory-checkpoint', 'memory-tools', 'memory-evict', 'memory-compress', 'memory-api', 'memory-ui', 'memory-commands'],
  )
  const byId = Object.fromEntries(rows.map((row) => [row.id, row.name]))
  assert.equal(byId.memory, '@qiuxu/memex/local')
  assert.equal(byId['memory-checkpoint'], '@qiuxu/memex/checkpoint')
  assert.equal(byId['memory-tools'], '@qiuxu/memex/tools')
  assert.equal(byId['memory-evict'], '@qiuxu/memex/evict')
  assert.equal(byId['memory-compress'], '@qiuxu/memex/compress')
  assert.equal(byId['memory-api'], '@qiuxu/memex/api')
  assert.equal(byId['memory-commands'], '@qiuxu/memex/commands')
  const uiName = byId['memory-ui']
  // The public repo addresses the client half through the bundle's own
  // subpath export. (Some local DSH builds want a `file:` URL instead; see
  // docs/install.md for that fallback.)
  assert.equal(uiName, '@qiuxu/memex/ui')
  if (bundleBuilt) {
    const target = new URL('modules/memory-ui/index.js', bundleRootUrl)
    assert.ok(existsSync(target), `memory-ui module must exist in the built bundle: ${target}`)
  }
})

// L. memory HTTP API (/api/memory.*) ─────────────────────────────────────────

await test('L1a', 'memory API registers eight exact Fetch routes through ctx.effect', async () => {
  await withApiStack('l1a', async ({ routes, routeEffects, ctx }) => {
    assert.equal(apiRow.name, 'memory-api')
    assert.deepEqual(apiRow.inject, ['memory', 'connection', 'sessions'])
    const expected = [
      ['/api/memory.index', 'GET'],
      ['/api/memory.record', 'GET'],
      ['/api/memory.search', 'GET'],
      ['/api/memory.status', 'POST'],
      ['/api/memory.level', 'POST'],
      ['/api/memory.compress', 'POST'],
      ['/api/memory.restore', 'POST'],
      ['/api/memory.gc', 'POST'],
      ['/api/memory.metrics', 'GET'],
    ]
    assert.equal(routes.length, 9, 'memory-api must register nine routes (incl metrics)')
    assert.deepEqual(routes.map((route) => route.path), expected.map(([path]) => path))
    for (const [path, method] of expected) {
      const route = apiRoute(routes, path)
      assert.deepEqual(route.methods, [method], `${path} methods`)
      assert.equal(route.requestBody, 'buffered', `${path} requestBody`)
      assert.equal(typeof route.fetch, 'function', `${path} fetch handler`)
    }
    assert.equal(routeEffects, 9, 'each route must be registered through ctx.effect')
    assert.equal(ctx.disposers.length, 10, 'backend effect + nine route effects must be registered')
  })
})

await test('L1b', 'index route returns levels, both pools, evictions and the active fields', async () => {
  await withApiStack('l1b', async ({ backend, routes }) => {
    const keyA = seam.memoryWorkspaceKey('/tmp/ws-a', 'session-a')
    const keyB = seam.memoryWorkspaceKey('/tmp/ws-b', 'session-b')
    await seedApiRecords(backend, keyA, 'session-a', 3, 'Alpha')
    await backend.write({ kind: 'fact', title: 'Bravo other workspace', body: 'bravo body', workspaceKey: keyB, sessionId: 'session-b' })

    const { response, data, contentType } = await apiRequest(routes, '/api/memory.index?sessionId=session-a&limit=2')
    assert.equal(response.status, 200)
    assert.match(contentType, /application\/json/)
    assert.equal(data.ok, true)
    assert.deepEqual(data.levels, { l2: false, l3: true }, 'the harness mounts the API with defaultLevels=l3')
    assert.equal(data.captureScope, 'workspace')
    assert.deepEqual(data.scope, { sessionId: 'session-a', cwd: '/tmp/ws-a', workspaceKey: keyA })
    assert.deepEqual(data.l2, {
      enabled: false,
      tokens: 0,
      hotTokens: 0,
      coldTokens: 0,
      coldCount: 0,
      count: 0,
      capacityTokens: 10_000_000,
    })
    assert.equal(data.l3.enabled, true)
    assert.equal(data.l3.count, 3)
    assert.equal(data.l3.hotTokens, data.l3.tokens)
    assert.equal(data.l3.coldCount, 0)
    assert.equal(data.l3.capacityTokens, 100_000_000)
    assert.deepEqual(data.l1Evicted, { count: 0, tokens: 0 })
    assert.equal(data.count, 3)
    assert.equal(data.records.length, 2, 'limit=2 must clamp the listing')
    assert.ok(data.records.every((card) => card.scope === 'workspace'))
    assert.ok(data.records.every((card) => card.body === undefined && card.path === undefined), 'panel cards must omit bodies and internal paths')
    assert.equal(data.capacityTokens, 100_000_000)
    assert.equal(data.tokens, data.l3.tokens)
    assert.deepEqual(data.byKind, { fact: 3 })
    assert.deepEqual(data.byKindTokens, { fact: data.l3.tokens })

    // `cwd` alone resolves the live session (no sessionId parameter).
    const byCwd = await apiRequest(routes, '/api/memory.index?cwd=%2Ftmp%2Fws-a&limit=5')
    assert.equal(byCwd.response.status, 200)
    assert.equal(byCwd.data.scope.sessionId, 'session-a')
    assert.equal(byCwd.data.count, 3)

    // Workspace isolation: session-b (different cwd) never sees session-a's records.
    const workspaceB = await apiRequest(routes, '/api/memory.index?sessionId=session-b&limit=5')
    assert.equal(workspaceB.response.status, 200)
    assert.equal(workspaceB.data.count, 1)
    assert.equal(workspaceB.data.records[0].title, 'Bravo other workspace')
  })
})

await test('L1c', 'record route returns records visible through the enabled levels only', async () => {
  await withApiStack('l1c', async ({ backend, routes }) => {
    const keyA = seam.memoryWorkspaceKey('/tmp/ws-a', 'session-a')
    const keyB = seam.memoryWorkspaceKey('/tmp/ws-b', 'session-b')
    const [workspaceRecord] = await seedApiRecords(backend, keyA, 'session-a', 1, 'Alpha')
    const sessionRecord = await backend.write({ kind: 'fact', title: 'Session only', body: 'session body', scope: 'session', sessionId: 'session-a', workspaceKey: keyA })
    const foreign = await backend.write({ kind: 'fact', title: 'Foreign record', body: 'foreign body', workspaceKey: keyB, sessionId: 'session-b' })

    const read = await apiRequest(routes, `/api/memory.record?sessionId=session-a&id=${encodeURIComponent(workspaceRecord.id)}`)
    assert.equal(read.response.status, 200)
    assert.match(read.contentType, /application\/json/)
    assert.equal(read.data.ok, true)
    assert.equal(read.data.record.scope, 'workspace')
    assertIncludes(read.data.body, 'alpha body 1')
    assert.equal(read.data.truncated, false)

    const sessionReadL3 = await apiRequest(routes, `/api/memory.record?sessionId=session-a&id=${encodeURIComponent(sessionRecord.id)}`)
    assert.equal(sessionReadL3.response.status, 404, 'L2 records are invisible while only L3 is enabled')
    assert.equal(sessionReadL3.data.code, 'MEMORY_NOT_FOUND')
    await backend.enableLevel('session-a', 'l2')
    const sessionReadL2 = await apiRequest(routes, `/api/memory.record?sessionId=session-a&id=${encodeURIComponent(sessionRecord.id)}`)
    assert.equal(sessionReadL2.response.status, 200)
    assertIncludes(sessionReadL2.data.body, 'session body')

    const foreignRead = await apiRequest(routes, `/api/memory.record?sessionId=session-a&id=${encodeURIComponent(foreign.id)}`)
    assert.equal(foreignRead.response.status, 404)
    assert.equal(foreignRead.data.code, 'MEMORY_NOT_FOUND')

    const missing = await apiRequest(routes, '/api/memory.record?sessionId=session-a&id=mem_missing00')
    assert.equal(missing.response.status, 404)
    assert.equal(missing.data.code, 'MEMORY_NOT_FOUND')

    const noId = await apiRequest(routes, '/api/memory.record?sessionId=session-a')
    assert.equal(noId.response.status, 400)
    assert.equal(noId.data.code, 'MEMORY_INVALID_ID')
  })
})

await test('L1d', 'search route returns ranked snippets over the visible-level union', async () => {
  await withApiStack('l1d', async ({ backend, routes }) => {
    const keyA = seam.memoryWorkspaceKey('/tmp/ws-a', 'session-a')
    const keyB = seam.memoryWorkspaceKey('/tmp/ws-b', 'session-b')
    await seedApiRecords(backend, keyA, 'session-a', 3, 'Alpha')
    await backend.write({ kind: 'fact', title: 'Alpha foreign', body: 'alpha body only in B', workspaceKey: keyB, sessionId: 'session-b' })

    // L3 only: the workspace pool is searchable, other workspaces are not.
    const searchL3 = await apiRequest(routes, '/api/memory.search?sessionId=session-a&q=alpha&limit=10')
    assert.equal(searchL3.response.status, 200)
    assert.match(searchL3.contentType, /application\/json/)
    assert.equal(searchL3.data.ok, true)
    assert.deepEqual(searchL3.data.levels, { l2: false, l3: true })
    assert.equal(searchL3.data.records.length, 3, 'L3 workspace records only; other workspaces excluded')
    assert.ok(searchL3.data.records.every((record) => typeof record.snippet === 'string' && record.snippet.length > 0))

    // Union: enabling L2 keeps the deployment-default L3 on (sticky levels are
    // additive), so the visible set becomes workspace records + own-private hit.
    const sessionRecord = await backend.write({ kind: 'fact', title: 'Alpha session', body: 'alpha body private', scope: 'session', sessionId: 'session-a', workspaceKey: keyA })
    await backend.enableLevel('session-a', 'l2')
    const searchL2 = await apiRequest(routes, '/api/memory.search?sessionId=session-a&q=alpha&limit=10')
    assert.deepEqual(searchL2.data.levels, { l2: true, l3: true })
    assert.equal(searchL2.data.records.length, 4, 'L3 workspace records + own L2 record')
    assert.ok(searchL2.data.records.some((record) => record.id === sessionRecord.id))

    const listFallback = await apiRequest(routes, '/api/memory.search?sessionId=session-a&q=&limit=10')
    assert.equal(listFallback.response.status, 200)
    assert.equal(listFallback.data.records.length, 4)
  })
})

await test('L1e', 'status route pins and unpins records visible in the enabled levels', async () => {
  await withApiStack('l1e', async ({ backend, routes }) => {
    const keyA = seam.memoryWorkspaceKey('/tmp/ws-a', 'session-a')
    const keyB = seam.memoryWorkspaceKey('/tmp/ws-b', 'session-b')
    const [record] = await seedApiRecords(backend, keyA, 'session-a', 1, 'Alpha')
    const sessionRecord = await backend.write({ kind: 'fact', title: 'Session only', body: 'session body', scope: 'session', sessionId: 'session-a', workspaceKey: keyA })
    const foreign = await backend.write({ kind: 'fact', title: 'Foreign record', body: 'foreign body', workspaceKey: keyB, sessionId: 'session-b' })

    const pin = await apiPost(routes, '/api/memory.status', { sessionId: 'session-a', id: record.id, status: 'pinned' })
    assert.equal(pin.response.status, 200)
    assert.equal(pin.data.ok, true)
    assert.equal(pin.data.record.status, 'pinned')
    assert.equal((await backend.get(record.id)).status, 'pinned')
    const unpin = await apiPost(routes, '/api/memory.status', { sessionId: 'session-a', id: record.id, status: 'active' })
    assert.equal(unpin.response.status, 200)
    assert.equal(unpin.data.record.status, 'active')

    const sessionStatusL3 = await apiPost(routes, '/api/memory.status', { sessionId: 'session-a', id: sessionRecord.id, status: 'pinned' })
    assert.equal(sessionStatusL3.response.status, 404, 'L2 records are invisible while only L3 is enabled')
    await backend.enableLevel('session-a', 'l2')
    const sessionStatusL2 = await apiPost(routes, '/api/memory.status', { sessionId: 'session-a', id: sessionRecord.id, status: 'pinned' })
    assert.equal(sessionStatusL2.response.status, 200)
    assert.equal(sessionStatusL2.data.record.status, 'pinned')

    const foreignStatus = await apiPost(routes, '/api/memory.status', { sessionId: 'session-a', id: foreign.id, status: 'pinned' })
    assert.equal(foreignStatus.response.status, 404)
    assert.equal(foreignStatus.data.code, 'MEMORY_NOT_FOUND')
    const badStatus = await apiPost(routes, '/api/memory.status', { sessionId: 'session-a', id: record.id, status: 'nonsense' })
    assert.equal(badStatus.response.status, 400)
    assert.equal(badStatus.data.code, 'MEMORY_INVALID_STATUS')
    const noId = await apiPost(routes, '/api/memory.status', { sessionId: 'session-a', status: 'pinned' })
    assert.equal(noId.response.status, 400)
    assert.equal(noId.data.code, 'MEMORY_INVALID_ID')
    const badBody = await apiPost(routes, '/api/memory.status', 'not-json')
    assert.equal(badBody.response.status, 400)
    assert.equal(badBody.data.code, 'MEMORY_INVALID_BODY')
  })
})

await test('L1f', 'API returns coded JSON errors for unknown sessions', async () => {
  await withApiStack('l1f', async ({ routes, backend }) => {
    const keyA = seam.memoryWorkspaceKey('/tmp/ws-a', 'session-a')
    await seedApiRecords(backend, keyA, 'session-a', 1, 'Alpha')
    const requests = [
      '/api/memory.index?sessionId=no-such-session',
      '/api/memory.record?sessionId=no-such-session&id=mem_x',
      '/api/memory.search?cwd=%2Ftmp%2Fno-such-ws&q=alpha',
    ]
    for (const url of requests) {
      const result = await apiRequest(routes, url)
      assert.equal(result.response.status, 404, url)
      assert.match(result.contentType, /application\/json/, url)
      assert.equal(result.data.ok, false, url)
      assert.equal(result.data.code, 'MEMORY_UNKNOWN_SESSION', url)
      assert.equal(typeof result.data.message, 'string', url)
    }
    const status = await apiPost(routes, '/api/memory.status', { sessionId: 'no-such-session', id: 'mem_x', status: 'pinned' })
    assert.equal(status.response.status, 404)
    assert.equal(status.data.code, 'MEMORY_UNKNOWN_SESSION')
    const level = await apiPost(routes, '/api/memory.level', { sessionId: 'no-such-session', level: 'l2' })
    assert.equal(level.response.status, 404)
    assert.equal(level.data.code, 'MEMORY_UNKNOWN_SESSION')
    const bare = await apiRequest(routes, '/api/memory.index')
    assert.equal(bare.response.status, 404)
    assert.equal(bare.data.code, 'MEMORY_UNKNOWN_SESSION')
  })
})

await test('L1g', 'index/search limit fallbacks apply when ?limit is absent', async () => {
  await withApiStack('l1g', async ({ backend, routes }) => {
    const keyA = seam.memoryWorkspaceKey('/tmp/ws-a', 'session-a')
    await seedApiRecords(backend, keyA, 'session-a', 3, 'Alpha')
    const index = await apiRequest(routes, '/api/memory.index?sessionId=session-a')
    assert.equal(index.response.status, 200)
    assert.equal(index.data.count, 3)
    assert.equal(index.data.records.length, 3, 'absent limit must use the route fallback (100)')
    const search = await apiRequest(routes, '/api/memory.search?sessionId=session-a&q=alpha')
    assert.equal(search.data.records.length, 3, 'absent limit on search must use the fallback (30)')
  })
})

// M. sticky cache levels (L2 session / L3 workspace) ─────────────────────────

await test('M1', 'default levels none archive nothing, inject nothing and gate tools/commands', async () => {
  const commands = createCommandsMock()
  await withInstance('m1', {
    ctx: { services: { llm: undefined, commands: commands.service } },
    backend: { defaultLevels: 'none' },
  }, async ({ instance, ctx }) => {
    assert.deepEqual([...seam.MEMORY_LEVELS], ['l2', 'l3'])
    assert.deepEqual([...seam.MEMORY_MODES], ['off', 'session', 'workspace'], 'legacy modes stay for migration')
    const session = createSession({ id: 'sess-m1', cwd: '/tmp/ws-m1' })
    assert.deepEqual(await instance.getLevels(session.id), { l2: false, l3: false })

    for (const event of createSurfaceEvents()) await ctx.emit('session/event', session, event)
    const compaction = createCompactionEvent({ compactionId: 'cmp-m1' })
    await ctx.emit('session/event', session, compaction)
    await settle(120)
    assert.equal(await instance.wasArchived(session.id, 'cmp-m1'), undefined, 'no level must archive nothing')
    assert.equal((await instance.facets({ workspaceKey: workspaceKeyFor(session) })).count, 0)

    const decision = createPreStepDecision(session, '继续')
    const result = await ctx.emit('agent/pre-step', { agent: { session } }, terminalNext(decision))
    assert.equal(result.messages.length, decision.messages.length, 'no level must inject nothing')

    const exec = { agent: { session } }
    for (const [toolName, args] of [
      ['memory_search', { query: 'anything' }],
      ['memory_open', { id: 'mem_x' }],
      ['memory_grep', { pattern: 'x' }],
      ['memory_write', { kind: 'fact', title: 't', body: 'b' }],
    ]) {
      assertIncludes(await ctx.tool(toolName).execute(args, exec), 'Extra context is off', `${toolName} must be gated`)
    }
    const index = await ctx.tool('memory_index').execute({}, exec)
    assertIncludes(index, 'L2 session-private: OFF')
    assertIncludes(index, 'L3 workspace-shared: OFF')

    const memoryCommand = commands.definitions[0]
    const status = await memoryCommand.handler({ rawInput: 'status', agent: { session } })
    assertIncludes(status.text, 'L2: off')
    assertIncludes(status.text, 'L3: off')
    assertIncludes(status.text, 'L1 evicted to L2/L3: 0 batches')
    assertIncludes(status.text, 'Cache levels: L1 = model context window')

    // Sticky enable: once on, the level stays on for every later read.
    assert.deepEqual(await instance.enableLevel(session.id, 'l2'), { l2: true, l3: false })
    assert.deepEqual(await instance.getLevels(session.id), { l2: true, l3: false })
    assert.deepEqual(await instance.enableLevel(session.id, 'l2'), { l2: true, l3: false }, 'enable is idempotent')
    assert.equal(await instance.getMode(session.id), 'session', 'legacy mode derives from levels')
  })
})

await test('M2', 'L2 archives privately and stays invisible to another session in the same workspace', async () => {
  await withInstance('m2', {
    ctx: { services: { llm: undefined } },
    backend: { defaultLevels: 'none' },
  }, async ({ instance, ctx }) => {
    const sessionA = createSession({ id: 'sess-m2-a', cwd: '/tmp/ws-m2' })
    const sessionB = createSession({ id: 'sess-m2-b', cwd: '/tmp/ws-m2' })
    assert.equal(workspaceKeyFor(sessionA), workspaceKeyFor(sessionB))
    await instance.enableLevel(sessionA.id, 'l2')
    assert.equal(await instance.getMode(sessionA.id), 'session')

    const id = await seedCompaction(instance, ctx, sessionA, createCompactionEvent({ compactionId: 'cmp-m2' }))
    const record = await instance.get(id)
    assert.equal(record.scope, 'session', 'L2 captures are session-scoped')
    assert.equal(record.sessionId, sessionA.id)
    const workspaceKey = workspaceKeyFor(sessionA)
    assert.equal((await instance.list({ workspaceKey, scopes: ['session'], sessionId: sessionA.id })).length, 1)
    assert.equal((await instance.facets({ workspaceKey, scope: 'workspace' })).count, 0)
    assert.deepEqual((await instance.facets({ workspaceKey, scopes: ['session'], sessionId: sessionA.id })).levels, { l2: { count: 1, tokens: record.tokens } })

    const execA = { agent: { session: sessionA } }
    const execB = { agent: { session: sessionB } }
    assertIncludes(await ctx.tool('memory_open').execute({ id }, execA), id)
    assertIncludes(await ctx.tool('memory_open').execute({ id }, execB), 'Extra context is off')
    await instance.enableLevel(sessionB.id, 'l2')
    assertIncludes(await ctx.tool('memory_open').execute({ id }, execB), 'No memory record with id')
    assertIncludes(await ctx.tool('memory_search').execute({ query: 'ECONNREFUSED' }, execB), 'No matching records')
  })
})

await test('M2b', 'record route exposes L2 records only to their own session', async () => {
  const sessions = [
    { id: 'session-a', header: { cwd: '/tmp/ws-m2b' } },
    { id: 'session-b', header: { cwd: '/tmp/ws-m2b' } },
  ]
  await withApiStack('m2b', { sessions, backend: { defaultLevels: 'none' } }, async ({ backend, routes }) => {
    const workspaceKey = seam.memoryWorkspaceKey('/tmp/ws-m2b', 'session-a')
    assert.equal(workspaceKey, seam.memoryWorkspaceKey('/tmp/ws-m2b', 'session-b'))
    const enabled = await apiPost(routes, '/api/memory.level', { sessionId: 'session-a', level: 'l2' })
    assert.deepEqual({ ...enabled.data }, { ok: true, levels: { l2: true, l3: false }, captureScope: 'session' })
    const record = await backend.write({ kind: 'fact', title: 'session private', body: 'session body', scope: 'session', sessionId: 'session-a', workspaceKey })
    const own = await apiRequest(routes, `/api/memory.record?sessionId=session-a&id=${encodeURIComponent(record.id)}`)
    assert.equal(own.response.status, 200)
    assertIncludes(own.data.body, 'session body')
    const other = await apiRequest(routes, `/api/memory.record?sessionId=session-b&id=${encodeURIComponent(record.id)}`)
    assert.equal(other.response.status, 404)
    assert.equal(other.data.code, 'MEMORY_NOT_FOUND')
    await apiPost(routes, '/api/memory.level', { sessionId: 'session-b', level: 'l2' })
    const otherLevel = await apiRequest(routes, `/api/memory.record?sessionId=session-b&id=${encodeURIComponent(record.id)}`)
    assert.equal(otherLevel.response.status, 404, 'L2 stays private even after the other session enables L2')
  })
})

await test('M3', 'L3 shares archives across sessions and keeps L2 records private', async () => {
  const sessions = [
    { id: 'session-a', header: { cwd: '/tmp/ws-m3' } },
    { id: 'session-b', header: { cwd: '/tmp/ws-m3' } },
  ]
  await withApiStack('m3', { sessions, checkpoint: true, backend: { defaultLevels: 'none' } }, async ({ backend, ctx, routes, sessions: liveSessions }) => {
    const workspaceKey = seam.memoryWorkspaceKey('/tmp/ws-m3', 'session-a')
    assert.equal(workspaceKey, seam.memoryWorkspaceKey('/tmp/ws-m3', 'session-b'))
    for (const sessionId of ['session-a', 'session-b']) {
      const response = await apiPost(routes, '/api/memory.level', { sessionId, level: 'l3' })
      assert.deepEqual({ ...response.data }, { ok: true, levels: { l2: false, l3: true }, captureScope: 'workspace' })
    }
    const archivedId = await seedCompaction(backend, ctx, liveSessions[1], createCompactionEvent({ compactionId: 'cmp-m3' }))
    const archived = await backend.get(archivedId)
    assert.equal(archived.scope, 'workspace', 'L3 wins the capture scope')
    assert.equal(archived.workspaceKey, workspaceKey)

    // B's private L2 record must stay invisible to A's L3-only view.
    await apiPost(routes, '/api/memory.level', { sessionId: 'session-b', level: 'l2' })
    const privateRecord = await backend.write({ kind: 'fact', title: 'old private', body: 'old private ECONNREFUSED needle', scope: 'session', sessionId: 'session-b', workspaceKey })

    const indexA = await apiRequest(routes, '/api/memory.index?sessionId=session-a&limit=10')
    assert.deepEqual(indexA.data.levels, { l2: false, l3: true })
    assert.equal(indexA.data.captureScope, 'workspace')
    assert.equal(indexA.data.l3.count, 1)
    assert.equal(indexA.data.l2.count, 0, 'A did not enable L2')
    assert.deepEqual(indexA.data.records.map((record) => record.id), [archivedId])

    const readShared = await apiRequest(routes, `/api/memory.record?sessionId=session-a&id=${encodeURIComponent(archivedId)}`)
    assert.equal(readShared.response.status, 200)
    assertIncludes(readShared.data.body, 'ECONNREFUSED')
    const readPrivate = await apiRequest(routes, `/api/memory.record?sessionId=session-a&id=${encodeURIComponent(privateRecord.id)}`)
    assert.equal(readPrivate.response.status, 404)

    const searchA = await apiRequest(routes, '/api/memory.search?sessionId=session-a&q=ECONNREFUSED&limit=10')
    assert.equal(searchA.data.records.some((record) => record.id === privateRecord.id), false)
    assert.equal(searchA.data.records.some((record) => record.id === archivedId), true)

    const indexB = await apiRequest(routes, '/api/memory.index?sessionId=session-b&limit=10')
    assert.deepEqual(indexB.data.levels, { l2: true, l3: true })
    assert.equal(indexB.data.l2.count, 1)
    assert.equal(indexB.data.l3.count, 1)
    assert.equal(indexB.data.records.length, 2, 'B sees its own L2 record plus the shared L3 record')
  })
})

await test('M4', 'facets, /memory status and the index API expose both pools and L1 evictions', async () => {
  const commands = createCommandsMock()
  await withInstance('m4', {
    ctx: { services: { llm: undefined, commands: commands.service } },
    backend: { defaultLevels: 'none' },
  }, async ({ instance }) => {
    const session = createSession({ id: 'sess-m4', cwd: '/tmp/ws-m4' })
    const facets = await instance.facets({ workspaceKey: workspaceKeyFor(session) })
    assert.equal(facets.capacityTokens, 100_000_000)
    assert.equal(facets.sessionCapacityTokens, 10_000_000)
    assert.deepEqual(facets.levels, {})
    const status = await commands.definitions[0].handler({ rawInput: 'status', agent: { session } })
    assertIncludes(status.text, 'L2: off — 0 hot / 0 cold records, ~0 hot + 0 cold / 10000000 capacity tokens.')
    assertIncludes(status.text, 'L3: off — 0 hot / 0 cold records, ~0 hot + 0 cold / 100000000 capacity tokens.')
    assertIncludes(status.text, 'L1 evicted to L2/L3: 0 batches, ~0 tokens.')
    await instance.enableLevel(session.id, 'l2')
    const after = await commands.definitions[0].handler({ rawInput: 'status', agent: { session } })
    assertIncludes(after.text, 'L2: ON (sticky)')
    assertIncludes(after.text, 'L3: off')
  })

  await withApiStack('m4-api', async ({ backend, routes }) => {
    const workspaceKey = seam.memoryWorkspaceKey('/tmp/ws-a', 'session-a')
    const [record] = await seedApiRecords(backend, workspaceKey, 'session-a', 2, 'Alpha')
    await backend.enableLevel('session-a', 'l2')
    await backend.enableLevel('session-a', 'l3')
    const index = await apiRequest(routes, '/api/memory.index?sessionId=session-a&limit=10')
    assert.deepEqual(index.data.levels, { l2: true, l3: true })
    assert.equal(index.data.captureScope, 'workspace')
    assert.equal(index.data.l2.capacityTokens, 10_000_000)
    assert.equal(index.data.l3.capacityTokens, 100_000_000)
    assert.equal(index.data.l3.count, 2)
    assert.equal(index.data.l2.count, 0)
    assert.equal(index.data.count, 2)
    assert.equal(index.data.records.length, 2)
    assert.deepEqual(index.data.byKindTokens, { fact: index.data.tokens })
    assert.equal(index.data.records.some((card) => card.id === record.id), true)
  })
})

await test('M5', 'level API enables sticky levels and immediately gates the visible pool', async () => {
  await withApiStack('m5', { backend: { defaultLevels: 'none' } }, async ({ backend, routes, ctx, sessions }) => {
    const workspaceKey = seam.memoryWorkspaceKey('/tmp/ws-a', 'session-a')
    const [workspaceRecord] = await seedApiRecords(backend, workspaceKey, 'session-a', 1, 'Alpha')
    const sessionRecord = await backend.write({ kind: 'fact', title: 'session only', body: 'session body', scope: 'session', sessionId: 'session-a', workspaceKey })
    const session = sessions[0]
    const exec = { agent: { session } }
    assertIncludes(await ctx.tool('memory_search').execute({ query: 'alpha' }, exec), 'Extra context is off')

    const l2 = await apiPost(routes, '/api/memory.level', { sessionId: 'session-a', level: 'l2' })
    assert.equal(l2.response.status, 200)
    assert.deepEqual({ ...l2.data }, { ok: true, levels: { l2: true, l3: false }, captureScope: 'session' })
    assert.deepEqual(await backend.getLevels('session-a'), { l2: true, l3: false })
    const sessionIndex = await apiRequest(routes, '/api/memory.index?sessionId=session-a&limit=10')
    assert.equal(sessionIndex.data.l2.enabled, true)
    assert.equal(sessionIndex.data.l3.enabled, false)
    assert.deepEqual(sessionIndex.data.records.map((card) => card.id), [sessionRecord.id], 'L3 workspace records are not visible yet')
    assertIncludes(await ctx.tool('memory_open').execute({ id: workspaceRecord.id }, exec), 'No memory record', 'L3 records are invisible while only L2 is enabled')
    const workspaceReadL2 = await apiRequest(routes, `/api/memory.record?sessionId=session-a&id=${encodeURIComponent(workspaceRecord.id)}`)
    assert.equal(workspaceReadL2.response.status, 404)

    const l3 = await apiPost(routes, '/api/memory.level', { sessionId: 'session-a', level: 'l3' })
    assert.deepEqual({ ...l3.data }, { ok: true, levels: { l2: true, l3: true }, captureScope: 'workspace' })
    const workspaceIndex = await apiRequest(routes, '/api/memory.index?sessionId=session-a&limit=10')
    assert.equal(workspaceIndex.data.l2.count, 1)
    assert.equal(workspaceIndex.data.l3.count, 1)
    assert.equal(workspaceIndex.data.records.length, 2)
    assertIncludes(await ctx.tool('memory_open').execute({ id: workspaceRecord.id }, exec), workspaceRecord.id)
    assertIncludes(await ctx.tool('memory_open').execute({ id: sessionRecord.id }, exec), sessionRecord.id)

    const sticky = await apiPost(routes, '/api/memory.level', { sessionId: 'session-a', level: 'off' })
    assert.equal(sticky.response.status, 400)
    assert.equal(sticky.data.code, 'MEMORY_LEVEL_STICKY')
    assert.deepEqual(await backend.getLevels('session-a'), { l2: true, l3: true }, 'no request can disable a level')
  })
})

await test('M6a', 'client ring bridge hides the arc and labels extra context off', async () => {
  const harness = runClientPlugin(indexPayloadForLevels({ l2: false, l3: false }, 0, 0))
  await settle(15)
  assert.equal(harness.appendedArc.length, 1)
  assert.ok(String(harness.appendedArc[0].attrs['stroke-dasharray']).startsWith('0 '), 'off must draw an empty arc')
  const label = String(harness.meterButton.dataset['attr:aria-label'])
  assert.ok(label.endsWith('额外上下文 关'), `off label must end with 额外上下文 关, got ${label}`)
  assert.doesNotThrow(() => harness.effects[1].dispose())
})

await test('M6b', 'client ring bridge colors and labels the L2 vs L3 capture target', async () => {
  const l2 = runClientPlugin(indexPayloadForLevels({ l2: true, l3: false }, 1_000_000, 10_000_000))
  await settle(15)
  assert.equal(l2.appendedArc[0].attrs.stroke, 'var(--dsw-static-teal-450, #14b8a6)', 'L2 captures paint the teal arc')
  assertIncludes(String(l2.meterButton.dataset['attr:aria-label']), '（L2）')
  assert.equal(String(l2.appendedArc[0].attrs['stroke-dasharray']).startsWith('0 '), false)
  assert.doesNotThrow(() => l2.effects[1].dispose())

  const l3 = runClientPlugin(indexPayloadForLevels({ l2: false, l3: true }, 1_000_000, 100_000_000))
  await settle(15)
  assert.equal(l3.appendedArc[0].attrs.stroke, 'var(--dsw-alias-brand-primary, #4c6fff)', 'L3 captures paint the brand-blue arc')
  assertIncludes(String(l3.meterButton.dataset['attr:aria-label']), '（L3）')
  assert.doesNotThrow(() => l3.effects[1].dispose())

  const both = runClientPlugin(indexPayloadForLevels({ l2: true, l3: true }, 1_000_000, 100_000_000))
  await settle(15)
  assert.equal(both.appendedArc[0].attrs.stroke, 'var(--dsw-alias-brand-primary, #4c6fff)', 'L3 wins the capture color')
  assertIncludes(String(both.meterButton.dataset['attr:aria-label']), '（L2+L3）')
  assert.doesNotThrow(() => both.effects[1].dispose())
})

await test('M6c', 'client panel source exposes the sticky level switches and L1 eviction footer', async () => {
  assertIncludes(uiClientSource, 'api/memory.level')
  assertIncludes(uiClientSource, 'data-memex-meter-mode')
  for (const label of ['L2 本会话', 'L3 工作区', '🔒']) assertIncludes(uiClientSource, label)
  assertIncludes(uiClientSource, 'L1 额外上下文当前关闭')
  assertIncludes(uiClientSource, 'data-memex-panel')
  assertIncludes(uiClientSource, 'L1 已转移')
  assert.match(uiClientSource, /disabled: searching \|\| !anyLevel/)
})

await test('M7', 'grep applies the enabled-level visibility union', async () => {
  await withInstance('m7', {
    ctx: { services: { llm: undefined } },
    backend: { defaultLevels: 'none' },
  }, async ({ instance, ctx }) => {
    const sessionA = createSession({ id: 'sess-m7-a', cwd: '/tmp/ws-m7' })
    const sessionB = createSession({ id: 'sess-m7-b', cwd: '/tmp/ws-m7' })
    await instance.enableLevel(sessionA.id, 'l2')
    await instance.enableLevel(sessionA.id, 'l3')
    await instance.enableLevel(sessionB.id, 'l2')
    await instance.enableLevel(sessionB.id, 'l3')
    const workspaceKey = workspaceKeyFor(sessionA)
    const shared = await instance.write({ kind: 'fact', title: 'B shared', body: 'shared-needle ECONNREFUSED', scope: 'workspace', sessionId: sessionB.id, workspaceKey })
    const privateRecord = await instance.write({ kind: 'fact', title: 'B private', body: 'private-needle', scope: 'session', sessionId: sessionB.id, workspaceKey })
    const output = await ctx.tool('memory_grep').execute({ pattern: 'needle' }, { agent: { session: sessionA } })
    // FINDINGS: LocalStoreCore.grep() does not consume `filter.scopes`, so the
    // L3 workspace record invented by another session is missing from the union.
    assert.match(output, new RegExp(shared.id), 'L3 records from other sessions must be greppable')
    assert.doesNotMatch(output, new RegExp(privateRecord.id), 'L2 records of other sessions must stay private')
  })
})

await test('M8', 'search body fallback respects the enabled-level scopes', async () => {
  await withInstance('m8', {
    ctx: { services: { llm: undefined } },
    backend: { defaultLevels: 'none' },
  }, async ({ instance, ctx }) => {
    const session = createSession({ id: 'sess-m8', cwd: '/tmp/ws-m8' })
    await instance.enableLevel(session.id, 'l2')
    const workspaceKey = workspaceKeyFor(session)
    // Same session, but a workspace-scoped record while only L2 is enabled.
    await instance.write({ kind: 'fact', title: 'workspace only note', body: 'hidden-needle in a workspace record', scope: 'workspace', sessionId: session.id, workspaceKey })
    const output = await ctx.tool('memory_search').execute({ query: 'hidden-needle' }, { agent: { session } })
    // FINDINGS: LocalStoreCore.search()'s body-only fallback passes only
    // `sessionId` (not `scopes`) to list(), so a workspace record is returned
    // even though L3 is disabled.
    assertIncludes(output, 'No matching records', 'workspace records must stay invisible while L3 is off')
  })
})

await test('M9', 'search works with L2 and L3 both enabled', async () => {
  await withInstance('m9', {
    ctx: { services: { llm: undefined } },
    backend: { defaultLevels: 'none' },
  }, async ({ instance, ctx }) => {
    const session = createSession({ id: 'sess-m9', cwd: '/tmp/ws-m9' })
    await instance.enableLevel(session.id, 'l2')
    await instance.enableLevel(session.id, 'l3')
    assert.deepEqual(await instance.getLevels(session.id), { l2: true, l3: true })
    const workspaceKey = workspaceKeyFor(session)
    await instance.write({ kind: 'fact', title: 'shared note', body: 'union-needle', scope: 'workspace', sessionId: session.id, workspaceKey })
    // FINDINGS: search() prefixes every workspaceClause fragment with `r.`, but
    // the scopes-union clause is a parenthesized expression, so both levels on
    // yields invalid SQL (`r.(scope = 'workspace' OR ...)`) and the search throws.
    const result = await instance.search({ workspaceKey, scopes: ['session', 'workspace'], sessionId: session.id, query: 'union-needle' })
    assert.equal(result.hits.length, 1, 'both-level search must return the visible workspace record')
  })
})

// N. level model, L1 eviction and bundle artifact ───────────────────────────

await test('N1', 'fresh backend defaults to no levels and L2/L3 are sticky once enabled', async () => {
  await withInstance('n1', {
    ctx: { services: { llm: undefined } },
    backend: { defaultLevels: 'none' },
  }, async ({ instance, ctx }) => {
    const session = createSession({ id: 'sess-n1', cwd: '/tmp/ws-n1' })
    assert.deepEqual(await instance.getLevels(session.id), { l2: false, l3: false })
    assert.equal(await instance.getMode(session.id), 'off')
    assert.deepEqual(seam.memoryVisibleScopes({ l2: false, l3: false }), [])
    assert.equal(seam.memoryCaptureScope({ l2: false, l3: false }), undefined)
    assert.equal(seam.memoryCaptureScope({ l2: true, l3: true }), 'workspace', 'L3 wins capture')

    for (const event of createSurfaceEvents()) await ctx.emit('session/event', session, event)
    await ctx.emit('session/event', session, createCompactionEvent({ compactionId: 'cmp-n1' }))
    await settle(120)
    assert.equal(await instance.wasArchived(session.id, 'cmp-n1'), undefined)
    const result = await ctx.emit('agent/pre-step', { agent: { session } }, terminalNext(createPreStepDecision(session, '继续')))
    assert.equal(result.messages.length, 1, 'no injection while both levels are off')

    await instance.enableLevel(session.id, 'l2')
    assert.deepEqual(await instance.getLevels(session.id), { l2: true, l3: false })
    assert.deepEqual(await instance.getLevels(session.id), { l2: true, l3: false }, 'L2 is sticky across reads')
    await instance.enableLevel(session.id, 'l3')
    assert.deepEqual(await instance.getLevels(session.id), { l2: true, l3: true })
    // The legacy setter cannot disable levels.
    assert.equal(await instance.setMode(session.id, 'off'), 'workspace', 'legacy setMode(off) cannot disable sticky levels')
    assert.deepEqual(await instance.getLevels(session.id), { l2: true, l3: true })
  })
})

await test('N2', 'level API enables idempotently and rejects disabling', async () => {
  await withApiStack('n2', { backend: { defaultLevels: 'none' } }, async ({ backend, routes }) => {
    const first = await apiPost(routes, '/api/memory.level', { sessionId: 'session-a', level: 'l2' })
    assert.equal(first.response.status, 200)
    assert.match(first.contentType, /application\/json/)
    assert.deepEqual({ ...first.data }, { ok: true, levels: { l2: true, l3: false }, captureScope: 'session' })
    const second = await apiPost(routes, '/api/memory.level', { sessionId: 'session-a', level: 'l2' })
    assert.equal(second.response.status, 200, 'repeat enable is idempotent')
    assert.deepEqual({ ...second.data }, { ok: true, levels: { l2: true, l3: false }, captureScope: 'session' })
    assert.deepEqual(await backend.getLevels('session-a'), { l2: true, l3: false })

    for (const invalidLevel of ['off', 'l1', 'both']) {
      const response = await apiPost(routes, '/api/memory.level', { sessionId: 'session-a', level: invalidLevel })
      assert.equal(response.response.status, 400, `level ${invalidLevel} must be rejected`)
      assert.equal(response.data.code, 'MEMORY_LEVEL_STICKY')
    }
    const unknown = await apiPost(routes, '/api/memory.level', { sessionId: 'no-such-session', level: 'l3' })
    assert.equal(unknown.response.status, 404)
    assert.equal(unknown.data.code, 'MEMORY_UNKNOWN_SESSION')
    const badBody = await apiPost(routes, '/api/memory.level', 'not-json')
    assert.equal(badBody.response.status, 400)
    assert.equal(badBody.data.code, 'MEMORY_INVALID_BODY')
    assert.deepEqual(await backend.getLevels('session-a'), { l2: true, l3: false }, 'invalid requests cannot change levels')
  })
})

await test('N3', 'L2 stays private end-to-end (archive, index, record, tools)', async () => {
  const sessions = [
    { id: 'session-a', header: { cwd: '/tmp/ws-n3' } },
    { id: 'session-b', header: { cwd: '/tmp/ws-n3' } },
  ]
  await withApiStack('n3', { sessions, checkpoint: true, backend: { defaultLevels: 'none' } }, async ({ backend, ctx, routes, sessions: liveSessions }) => {
    await apiPost(routes, '/api/memory.level', { sessionId: 'session-a', level: 'l2' })
    const id = await seedCompaction(backend, ctx, liveSessions[0], createCompactionEvent({ compactionId: 'cmp-n3' }))
    const record = await backend.get(id)
    assert.equal(record.scope, 'session')
    const indexA = await apiRequest(routes, '/api/memory.index?sessionId=session-a&limit=10')
    assert.equal(indexA.data.l2.count, 1)
    assert.equal(indexA.data.l3.count, 0)
    assert.deepEqual(indexA.data.records.map((card) => card.id), [id])
    const indexB = await apiRequest(routes, '/api/memory.index?sessionId=session-b&limit=10')
    assert.equal(indexB.data.records.length, 0, 'session B sees nothing')
    assert.equal(indexB.data.l2.count, 0)
    const readB = await apiRequest(routes, `/api/memory.record?sessionId=session-b&id=${encodeURIComponent(id)}`)
    assert.equal(readB.response.status, 404)
    const openA = await ctx.tool('memory_open').execute({ id }, { agent: { session: liveSessions[0] } })
    assertIncludes(openA, id)
    await apiPost(routes, '/api/memory.level', { sessionId: 'session-b', level: 'l2' })
    const openB = await ctx.tool('memory_open').execute({ id }, { agent: { session: liveSessions[1] } })
    assertIncludes(openB, 'No memory record', 'a second L2 session cannot read another session archive')
  })
})

await test('N4', 'L3 wins the capture scope while L2 records stay session-private', async () => {
  await withApiStack('n4', { backend: { defaultLevels: 'none' } }, async ({ backend, ctx, routes, sessions }) => {
    const workspaceKey = seam.memoryWorkspaceKey('/tmp/ws-a', 'session-a')
    const sessionA = sessions[0]
    const execA = { agent: { session: sessionA } }
    // Only L2 on: writes capture the session scope.
    await apiPost(routes, '/api/memory.level', { sessionId: 'session-a', level: 'l2' })
    const sessionWrite = await ctx.tool('memory_write').execute({ kind: 'fact', title: 'L2 note', body: 'l2 private body' }, execA)
    const sessionId = sessionWrite.match(/mem_[a-f0-9]+/)?.[0]
    assert.ok(sessionId, sessionWrite)
    assert.equal((await backend.get(sessionId)).scope, 'session')
    // Both levels on: new captures target L3 (workspace) because L3 wins.
    await apiPost(routes, '/api/memory.level', { sessionId: 'session-a', level: 'l3' })
    const workspaceWrite = await ctx.tool('memory_write').execute({ kind: 'fact', title: 'L3 note', body: 'l3 shared body' }, execA)
    const workspaceId = workspaceWrite.match(/mem_[a-f0-9]+/)?.[0]
    assert.ok(workspaceId, workspaceWrite)
    assert.equal((await backend.get(workspaceId)).scope, 'workspace')
    assert.equal((await backend.get(workspaceId)).workspaceKey, workspaceKey)

    const index = await apiRequest(routes, '/api/memory.index?sessionId=session-a&limit=10')
    assert.deepEqual(index.data.levels, { l2: true, l3: true })
    assert.equal(index.data.captureScope, 'workspace')
    assert.equal(index.data.l2.count, 1)
    assert.equal(index.data.l3.count, 1)
    assert.equal(index.data.records.length, 2)
    // Both an L2 and an L3 record are openable by their own session.
    assertIncludes(await ctx.tool('memory_open').execute({ id: sessionId }, execA), sessionId)
    assertIncludes(await ctx.tool('memory_open').execute({ id: workspaceId }, execA), workspaceId)
  })
})

await test('N5', 'memory-evict moves the oldest balanced L1 span into the enabled level', async () => {
  assert.equal(evictRow.name, 'memory-evict')
  assert.deepEqual(evictRow.inject, ['memory', 'tokenMeter', 'llm'])
  assert.deepEqual(Object.keys(evictRow.Config.properties), ['evictAtRatio', 'retainRatio', 'maxChars', 'captureLevel', 'sensitivePolicy'])

  const events = new Map()
  events.set(1, { seq: 1, type: 'system/message', data: { text: 'system head' } })
  for (let seq = 2; seq <= 8; seq += 1) {
    events.set(seq, { seq, type: seq % 2 === 0 ? 'user/message' : 'assistant/message', data: { text: `evictable-${seq} ${'x'.repeat(80)}` } })
  }
  const tokensBySeq = { 1: 10, 2: 150, 3: 150, 4: 150, 5: 150, 6: 100, 7: 100, 8: 100 }
  const measurement = createMeasurement(Object.entries(tokensBySeq).map(([seq, tokens]) => [Number(seq), tokens]))

  // Both levels off: no-op even under pressure.
  const disabled = createEvictHarness({ levels: { l2: false, l3: false }, measurement, contextWindow: 1000 })
  const disabledSession = createEvictSession({ events })
  const disabledDecision = await disabled.handler({ agent: { session: disabledSession }, signal: undefined }, async () => ({ kind: 'enter', messages: [] }))
  assert.deepEqual(disabledDecision, { kind: 'enter', messages: [] }, 'the original decision must be returned')
  assert.equal(disabled.writes.length, 0)
  assert.equal(disabledSession.__appended.length, 0)

  // Below the eviction threshold: no-op.
  const belowMeasurement = createMeasurement(Array.from({ length: 8 }, (_, index) => [index + 1, 50]))
  const below = createEvictHarness({ levels: { l2: false, l3: true }, measurement: belowMeasurement, contextWindow: 1000 })
  const belowSession = createEvictSession({ events })
  await runEvictHandler(below, belowSession)
  assert.equal(below.writes.length, 0, 'below evictAtRatio nothing is moved')
  assert.equal(belowSession.__appended.length, 0)

  // L3 enabled above the threshold: move the oldest balanced span.
  const l3 = createEvictHarness({ levels: { l2: false, l3: true }, measurement, contextWindow: 1000 })
  const session = createEvictSession({ events, balancedBefore: (seq) => seq !== 5 && seq !== 6 })
  await runEvictHandler(l3, session)
  assert.equal(l3.writes.length, 1, 'one raw record per eviction batch')
  const record = l3.writes[0]
  assert.equal(record.scope, 'workspace', 'L3 capture scope')
  assert.ok(String(record.id).startsWith('l1_'))
  assertIncludes(record.title, 'L1 归档')
  assertIncludes(record.body, 'evictable-2')
  assert.deepEqual(record.tags.level, ['l3'])
  assert.equal(record.provenance.source, 'l1-eviction')

  const appended = session.__appended
  assert.equal(appended.length, 2, 'exactly a prune + a replacement')
  assert.equal(appended[0].type, 'compaction/prune')
  assert.equal(appended[1].type, 'user/message')
  const prune = appended[0].data
  assert.deepEqual(prune.shadowedSeqs, [2, 3], 'balanced cut keeps the tail and drops the split pair')
  assert.deepEqual(prune.shadowedRange, { start: 2, end: 3 })
  assert.equal(prune.shadowedTokenCount, 46, 'shadow price comes from tokenMeter.estimateMessage')
  assert.equal(appended[0].seq < appended[1].seq, true, 'prune precedes the replacement')
  assert.deepEqual(appended[1].options.surfaceOp, { op: 'replace', startSeq: 2, endSeq: 3 })
  assert.deepEqual(appended[1].options.sourceEventSeqs, [2, 3])
  const receipt = appended[1].data
  assert.equal(receipt.role, 'user')
  assert.equal(receipt.source.form, 'l1-eviction')
  assertIncludes(receipt.content[0].text, '<l1-eviction>')
  assert.equal(l3.evictions.length, 1)
  assert.equal(l3.evictions[0].recordId, record.id)
  assert.equal(l3.evictions[0].start, 2)
  assert.equal(l3.evictions[0].end, 3)
  assert.ok(session.__balancedCalls.length > 0, 'tool-pairing balance must be consulted')

  // L2-only: capture scope session; L2+L3: L3 wins.
  const l2 = createEvictHarness({ levels: { l2: true, l3: false }, measurement, contextWindow: 1000 })
  const l2Session = createEvictSession({ events })
  await runEvictHandler(l2, l2Session)
  assert.equal(l2.writes[0].scope, 'session')
  assert.deepEqual(l2.writes[0].tags.level, ['l2'])
  const both = createEvictHarness({ levels: { l2: true, l3: true }, measurement, contextWindow: 1000 })
  const bothSession = createEvictSession({ events })
  await runEvictHandler(both, bothSession)
  assert.equal(both.writes[0].scope, 'workspace', 'L3 wins the capture scope')

  // maxChars: an oversized first event now stops the batch (no eviction).
  const bounded = createEvictHarness({ levels: { l2: false, l3: true }, measurement, contextWindow: 1000, config: { maxChars: 60 } })
  const boundedSession = createEvictSession({ events })
  await runEvictHandler(bounded, boundedSession)
  assert.equal(bounded.writes.length, 0, 'a single oversized event must not be archived')
  assert.equal(boundedSession.__appended.length, 0)
})

await test('N6', 'bundle artifact ships the memory-evict/compress modules and eight-row patch', async () => {
  const patchText = readFileSync(new URL('../packages/memex/cordis.patch.yml', import.meta.url), 'utf8')
  const rows = [...patchText.matchAll(/^\s*-\s+id:\s*([\w-]+)\s*\n\s+name:\s*'([^']+)'/gm)]
    .map((match) => ({ id: match[1], name: match[2] }))
  assert.equal(rows.length, 8)
  assert.deepEqual(rows.map((row) => row.id), ['memory', 'memory-checkpoint', 'memory-tools', 'memory-evict', 'memory-compress', 'memory-api', 'memory-ui', 'memory-commands'])
  assert.equal(rows.find((row) => row.id === 'memory-evict').name, '@qiuxu/memex/evict')
  assert.equal(rows.find((row) => row.id === 'memory-compress').name, '@qiuxu/memex/compress')
  if (!bundleBuilt) throw new Skip('bundle not built')
  const moduleDirs = readdirSync(bundleModulesUrl).filter((entry) => entry !== '.gitignore').sort()
  assert.deepEqual(moduleDirs, [
    'memory-api',
    'memory-checkpoint',
    'memory-command',
    'memory-compress',
    'memory-core',
    'memory-evict',
    'memory-local',
    'memory-seam',
    'memory-tool',
    'memory-ui',
  ], 'generated bundle must carry ten runtime modules')
  for (const directory of moduleDirs) {
    assert.ok(existsSync(new URL(`${directory}/package.json`, bundleModulesUrl)), `${directory}/package.json must exist`)
  }
  const evictModule = await import(new URL('memory-evict/index.js', bundleModulesUrl).href)
  assert.equal(evictModule.name, 'memory-evict')
  assert.deepEqual(evictModule.inject, ['memory', 'tokenMeter', 'llm'])
  assert.equal(typeof evictModule.apply, 'function')
  const evictManifest = JSON.parse(readFileSync(new URL('memory-evict/package.json', bundleModulesUrl), 'utf8'))
  assert.equal(evictManifest.name, '@qiuxu/memex-evict')
  assert.ok(existsSync(new URL('node_modules/@qiuxu/memex-evict/', bundleRootUrl)), 'bundle symlink for the evict module must resolve')
  const compressModule = await import(new URL('memory-compress/index.js', bundleModulesUrl).href)
  assert.equal(compressModule.name, 'memory-compress')
  assert.equal(typeof compressModule.apply, 'function')
  const compressManifest = JSON.parse(readFileSync(new URL('memory-compress/package.json', bundleModulesUrl), 'utf8'))
  assert.equal(compressManifest.name, '@qiuxu/memex-compress')
  assert.ok(existsSync(new URL('node_modules/@qiuxu/memex-compress/', bundleRootUrl)), 'bundle symlink for the compress module must resolve')
})


// C. cold tier, capacity compression, capacity notices, eviction hardening ───

await test('C1', 'cold tier releases hot capacity while keeping records retrievable', async () => {
  await withCore('c1', (core) => {
    const hot = core.write({ kind: 'fact', title: 'hot tier record', body: 'hot body', workspaceKey: 'wk-c1', tokens: 40 })
    const cold = core.write({ kind: 'fact', title: 'cold tier record', body: 'cold body needle', workspaceKey: 'wk-c1', tokens: 60 })
    let facets = core.facets({ workspaceKey: 'wk-c1' })
    assert.equal(facets.count, 2)
    assert.equal(facets.hotCount, 2)
    assert.equal(facets.hotTokens, 100)
    assert.equal(facets.coldCount, 0)
    assert.equal(facets.coldTokens, 0)

    const archived = core.archiveCold(cold.id)
    assert.ok(archived, 'archiveCold returns the updated card')
    assert.match(archived.path, /[\\/]cold[\\/]wk-c1[\\/]mem_[0-9a-f]{10}\.md$/, 'the raw file moves under <root>/cold/<workspaceKey>/')
    assert.ok(existsSync(archived.path))
    assert.equal(existsSync(core.recordPath('wk-c1', cold.id)), false, 'the hot-pool path is gone')

    facets = core.facets({ workspaceKey: 'wk-c1' })
    assert.equal(facets.count, 2, 'cold records still count in the archived total')
    assert.equal(facets.hotCount, 1)
    assert.equal(facets.hotTokens, 40)
    assert.equal(facets.coldCount, 1)
    assert.equal(facets.coldTokens, 60)

    const reread = core.get(cold.id)
    assert.ok(reread)
    assert.equal(reread.body, 'cold body needle', 'cold records stay readable')
    // Cold card fields stay in FTS, but the body is dropped from the index on
    // archiveCold (it stays on disk and is reachable via get/grep).
    assert.equal(core.search({ query: 'cold', workspaceKey: 'wk-c1' }).total, 1, 'cold records stay searchable by card fields')
    // Cold bodies are not fully indexed, but archiveCold keeps a bounded
    // abstract (first ~1k chars) so natural-language body terms stay searchable.
    assert.equal(core.search({ query: 'needle', workspaceKey: 'wk-c1' }).total, 1, 'cold bodies are searchable through the bounded cold abstract')
    assert.equal(core.grep({ pattern: 'needle', workspaceKey: 'wk-c1' }).length, 1, 'grep still reaches cold bodies on disk')
    assert.deepEqual(core.list({ workspaceKey: 'wk-c1', cold: 0 }).map((card) => card.id), [hot.id])
    assert.deepEqual(core.list({ workspaceKey: 'wk-c1', cold: 1 }).map((card) => card.id), [cold.id])

    const catalog = core.catalog({ workspaceKey: 'wk-c1' })
    assertIncludes(catalog, hot.id)
    assert.equal(catalog.includes(cold.id), false, 'the catalog only lists hot records')
    assert.match(catalog, /Capacity \(hot\): 40 \/ 100000 tokens across 1 records, 1 cold records \(60 tokens, retrievable via memory_open\) \(L3 workspace-shared\)\./)
    assert.equal(core.archiveCold(cold.id).path, archived.path, 'archiveCold is idempotent')

    core.archiveCold(hot.id)
    const allCold = core.catalog({ workspaceKey: 'wk-c1' })
    assertIncludes(allCold, '## Memory catalog')
    assert.match(allCold, /Capacity \(hot\): 0 \/ 100000 tokens across 0 records, 2 cold records \(100 tokens, retrievable via memory_open\)/)
  })
})

await test('C1b', 'catalog footer reports the cold tier', async () => {
  await withCore('c1b', (core) => {
    const hot = core.write({ kind: 'fact', title: 'hot one', body: 'hot body', workspaceKey: 'wk-c1b', tokens: 40 })
    const cold = core.write({ kind: 'fact', title: 'cold one', body: 'cold body', workspaceKey: 'wk-c1b', tokens: 60 })
    core.archiveCold(cold.id)
    const catalog = core.catalog({ workspaceKey: 'wk-c1b' })
    assertIncludes(catalog, hot.id)
    // Regression guard for the fixed defect: the footer facets must be computed
    // without the cold:0 listing filter, so cold records are reported.
    assert.match(catalog, /Capacity \(hot\): 40 \/ 100000 tokens across 1 records, 1 cold records/)
  })
})

await test('C2', 'memory_compress cold strategy releases hot capacity losslessly', async () => {
  await withInstance('c2', {
    ctx: { services: { llm: undefined } },
    backend: { defaultLevels: 'l3', capacityTokens: 1000 },
  }, async ({ instance, ctx }) => {
    const session = createSession({ id: 'sess-c2', cwd: '/tmp/ws-c2' })
    const workspaceKey = workspaceKeyFor(session)
    const normal = []
    for (let index = 0; index < 6; index += 1) {
      normal.push(await instance.write({ kind: 'fact', title: `normal ${index}`, body: `body ${index}`, tokens: 100, workspaceKey, sessionId: session.id }))
    }
    const pinned = await instance.write({ kind: 'fact', status: 'pinned', title: 'pinned', body: 'pinned', tokens: 100, workspaceKey, sessionId: session.id })
    const thread = await instance.write({ kind: 'open-thread', status: 'open', title: 'thread', body: 'thread', tokens: 100, workspaceKey, sessionId: session.id })
    assert.equal((await instance.facets({ workspaceKey, scope: 'workspace' })).hotTokens, 800)

    compressRow.apply(ctx, { minAgeMs: 0 })
    const tool = ctx.tool('memory_compress')
    assert.ok(tool, 'memory-compress row must register the memory_compress tool')
    const exec = { agent: { session } }
    const report = await tool.execute({ level: 'l3', strategy: 'cold', targetRatio: 0.5 }, exec)
    assertIncludes(report, 'memory_compress (cold, l3)')
    assertIncludes(report, 'cold-moved 3 records')
    assertIncludes(report, 'LLM calls 0')
    assertIncludes(report, 'target')
    assertIncludes(report, 'hot')

    const after = await instance.facets({ workspaceKey, scope: 'workspace' })
    assert.equal(after.hotTokens, 500)
    assert.equal(after.coldCount, 3)
    const coldIds = (await instance.list({ workspaceKey, scope: 'workspace', cold: 1 })).map((card) => card.id)
    assert.equal(coldIds.length, 3)
    assert.equal(coldIds.includes(pinned.id), false, 'pinned records stay hot')
    assert.equal(coldIds.includes(thread.id), false, 'open threads stay hot')
    assert.ok(coldIds.every((id) => normal.some((card) => card.id === id)))
    for (const id of coldIds) {
      assert.ok(await instance.get(id), `cold record ${id} stays retrievable`)
    }

    const again = await tool.execute({ level: 'l3', strategy: 'cold', targetRatio: 0.5 }, exec)
    assertIncludes(again, 'cold-moved 0 records', 'a second run at target is a no-op')
  })
})

await test('C2b', 'memory_compress gates off sessions and disabled levels', async () => {
  await withInstance('c2b-off', {
    ctx: { services: { llm: undefined } },
    backend: { defaultLevels: 'none' },
  }, async ({ ctx }) => {
    compressRow.apply(ctx, { minAgeMs: 0 })
    const session = createSession({ id: 'sess-c2b-off', cwd: '/tmp/ws-c2b' })
    const report = await ctx.tool('memory_compress').execute({ level: 'l3', strategy: 'cold' }, { agent: { session } })
    assertIncludes(report, 'Extra context is off')
  })
  await withInstance('c2b-level', {
    ctx: { services: { llm: undefined } },
    backend: { defaultLevels: 'l3', capacityTokens: 1000 },
  }, async ({ ctx }) => {
    compressRow.apply(ctx, { minAgeMs: 0 })
    const session = createSession({ id: 'sess-c2b-level', cwd: '/tmp/ws-c2b' })
    const report = await ctx.tool('memory_compress').execute({ level: 'l2', strategy: 'cold' }, { agent: { session } })
    assertIncludes(report, 'L2 is not enabled')
    assertIncludes(report, 'sticky')
  })
})

await test('C2c', 'memory_compress respects minAgeMs for very recent records', async () => {
  await withInstance('c2c', {
    ctx: { services: { llm: undefined } },
    backend: { defaultLevels: 'l3', capacityTokens: 1000 },
  }, async ({ instance, ctx }) => {
    const session = createSession({ id: 'sess-c2c', cwd: '/tmp/ws-c2c' })
    const workspaceKey = workspaceKeyFor(session)
    for (let index = 0; index < 8; index += 1) {
      await instance.write({ kind: 'fact', title: `recent ${index}`, body: 'body', tokens: 100, workspaceKey, sessionId: session.id })
    }
    // Default minAgeMs is one hour: freshly written records must stay hot.
    compressRow.apply(ctx)
    const report = await ctx.tool('memory_compress').execute({ level: 'l3', strategy: 'cold', targetRatio: 0.5 }, { agent: { session } })
    assertIncludes(report, 'cold-moved 0 records')
    assert.equal((await instance.facets({ workspaceKey, scope: 'workspace' })).coldCount, 0)
  })
})

await test('C3a', 'memory_compress digest runs bounded llm batches and cold-moves originals', async () => {
  const llm = createCompressLlm({ text: '摘要内容\nids: mem_digest0001' })
  await withInstance('c3a', {
    ctx: { services: { llm } },
    backend: { defaultLevels: 'l3', capacityTokens: 1000 },
  }, async ({ instance, ctx }) => {
    const session = createSession({ id: 'sess-c3a', cwd: '/tmp/ws-c3a' })
    const workspaceKey = workspaceKeyFor(session)
    const originals = []
    for (let index = 0; index < 8; index += 1) {
      originals.push(await instance.write({ kind: 'fact', title: `digest ${index}`, body: `body ${index}`, tokens: 100, workspaceKey, sessionId: session.id }))
    }
    compressRow.apply(ctx, { minAgeMs: 0, batchRecords: 2, maxBatches: 2, minDigestTokens: 0 })
    const report = await ctx.tool('memory_compress').execute({ level: 'l3', strategy: 'digest', targetRatio: 0.5 }, { agent: { session } })
    assertIncludes(report, 'cold-moved 4 records')
    assertIncludes(report, 'digests 2')
    assertIncludes(report, 'LLM calls 2')
    assert.equal(llm.calls.length, 2)
    assert.ok(llm.calls.every((call) => call.purpose === 'memory-compress'))
    assert.equal(llm.calls[0].provider, 'p')
    assert.equal(llm.calls[0].model, 'm')

    const workspaceCards = await instance.list({ workspaceKey, scope: 'workspace', limit: 50 })
    const digests = workspaceCards.filter((card) => card.id.startsWith('dig_'))
    assert.equal(digests.length, 2, 'one digest record per batch')
    const digest = await instance.get(digests[0].id)
    assert.ok(digest)
    assert.equal(digest.kind, 'episode')
    assert.equal(digest.scope, 'workspace')
    assert.equal(digest.body, '摘要内容\nids: mem_digest0001')
    assert.equal(digest.provenance.strategy, 'digest')
    assert.equal(Array.isArray(digest.provenance.digestOf), true)
    assert.equal(digest.provenance.digestOf.length, 2)
    assert.equal(digest.tags.digest[0], 'cold-batch')
    assert.equal(digest.title.startsWith('冷摘要'), true)

    const facets = await instance.facets({ workspaceKey, scope: 'workspace' })
    assert.equal(facets.coldCount, 4, 'the digested originals move cold')
    const coldIds = (await instance.list({ workspaceKey, scope: 'workspace', cold: 1 })).map((card) => card.id)
    assert.equal(coldIds.length, 4)
    assert.ok(coldIds.every((id) => originals.some((card) => card.id === id)))
  })
})

await test('C3b', 'memory_compress digest is bounded and leaves originals hot on failure', async () => {
  const boundedLlm = createCompressLlm({ text: '摘要内容\nids: mem_digest0001' })
  await withInstance('c3b-bounded', {
    ctx: { services: { llm: boundedLlm } },
    backend: { defaultLevels: 'l3', capacityTokens: 1000 },
  }, async ({ instance, ctx }) => {
    const session = createSession({ id: 'sess-c3b-bounded', cwd: '/tmp/ws-c3b' })
    const workspaceKey = workspaceKeyFor(session)
    for (let index = 0; index < 8; index += 1) {
      await instance.write({ kind: 'fact', title: `bounded ${index}`, body: 'body', tokens: 100, workspaceKey, sessionId: session.id })
    }
    compressRow.apply(ctx, { minAgeMs: 0, batchRecords: 2, maxBatches: 1, minDigestTokens: 0 })
    const report = await ctx.tool('memory_compress').execute({ level: 'l3', strategy: 'digest', targetRatio: 0.5 }, { agent: { session } })
    assertIncludes(report, 'LLM calls 1')
    assertIncludes(report, 'cold-moved 2 records')
    assert.equal(boundedLlm.calls.length, 1, 'maxBatches caps one run')
    assert.equal((await instance.facets({ workspaceKey, scope: 'workspace' })).coldCount, 2)
  })

  const failingLlm = createCompressLlm({ text: '摘要内容\nids: mem_digest0001', failAt: 1 })
  await withInstance('c3b-fail', {
    ctx: { services: { llm: failingLlm } },
    backend: { defaultLevels: 'l3', capacityTokens: 1000 },
  }, async ({ instance, ctx }) => {
    const session = createSession({ id: 'sess-c3b-fail', cwd: '/tmp/ws-c3b-fail' })
    const workspaceKey = workspaceKeyFor(session)
    for (let index = 0; index < 8; index += 1) {
      await instance.write({ kind: 'fact', title: `failing ${index}`, body: 'body', tokens: 100, workspaceKey, sessionId: session.id })
    }
    compressRow.apply(ctx, { minAgeMs: 0, batchRecords: 2, maxBatches: 2, minDigestTokens: 0 })
    const report = await ctx.tool('memory_compress').execute({ level: 'l3', strategy: 'digest', targetRatio: 0.5 }, { agent: { session } })
    assertIncludes(report, 'errors:')
    // A digest that keeps failing falls back to the lossless cold tier so the
    // run still makes progress; no digest record is written.
    assertIncludes(report, 'fell back to cold spill')
    assertIncludes(report, 'cold-moved 4 records')
    assert.equal((await instance.facets({ workspaceKey, scope: 'workspace' })).coldCount, 4, 'fallback moved originals cold')
    assert.equal((await instance.list({ workspaceKey, scope: 'workspace', limit: 50 })).filter((card) => card.id.startsWith('dig_')).length, 0)
  })
})

await test('C4a', 'capacity notice fires above the hot ratio and stays silent below it', async () => {
  await withInstance('c4a-hot', {
    ctx: { services: { llm: undefined } },
    backend: { defaultLevels: 'l3', capacityTokens: 1000 },
    checkpoint: { capacityNoticeRatio: 0.8, capacityNoticeCooldownMs: 600_000 },
  }, async ({ instance, ctx }) => {
    const session = createSession({ id: 'sess-c4a-hot', cwd: '/tmp/ws-c4a' })
    await instance.write({ kind: 'fact', title: 'hot pool', body: 'x', tokens: 900, workspaceKey: workspaceKeyFor(session), sessionId: session.id })
    const result = await ctx.emit('agent/pre-step', { agent: { session } }, terminalNext(createPreStepDecision(session, '继续')))
    const notices = result.messages.filter((message) => message.source?.form === 'capacity-notice')
    assert.equal(notices.length, 1, 'exactly one capacity notice must be injected')
    const text = notices[0].content[0].text
    assertIncludes(text, '[EXTRA CONTEXT CAPACITY')
    assertIncludes(text, '额外上下文容量')
    assertIncludes(text, 'L3=90% hot')
    assertIncludes(text, 'Ask the user once')
    assertIncludes(text, '请先询问用户是否需要压缩')
    assertIncludes(text, '未经用户同意不要压缩')
    assertIncludes(text, 'memory_compress')
    assertIncludes(text, 'consent')
  })
  await withInstance('c4a-below', {
    ctx: { services: { llm: undefined } },
    backend: { defaultLevels: 'l3', capacityTokens: 1000 },
    checkpoint: { capacityNoticeRatio: 0.8, capacityNoticeCooldownMs: 600_000 },
  }, async ({ instance, ctx }) => {
    const session = createSession({ id: 'sess-c4a-below', cwd: '/tmp/ws-c4a-below' })
    await instance.write({ kind: 'fact', title: 'cool pool', body: 'x', tokens: 100, workspaceKey: workspaceKeyFor(session), sessionId: session.id })
    const result = await ctx.emit('agent/pre-step', { agent: { session } }, terminalNext(createPreStepDecision(session, '继续')))
    assert.equal(result.messages.filter((message) => message.source?.form === 'capacity-notice').length, 0)
  })
})

await test('C4b', 'capacity notice lists both hot levels and respects the cooldown', async () => {
  await withInstance('c4b', {
    ctx: { services: { llm: undefined } },
    backend: { defaultLevels: 'both', capacityTokens: 1000, sessionCapacityTokens: 1000 },
    checkpoint: { capacityNoticeRatio: 0.8, capacityNoticeCooldownMs: 600_000 },
  }, async ({ instance, ctx }) => {
    const session = createSession({ id: 'sess-c4b', cwd: '/tmp/ws-c4b' })
    const workspaceKey = workspaceKeyFor(session)
    await instance.write({ kind: 'fact', title: 'L2 hot', body: 'x', tokens: 900, scope: 'session', workspaceKey, sessionId: session.id })
    await instance.write({ kind: 'fact', title: 'L3 hot', body: 'x', tokens: 900, scope: 'workspace', workspaceKey, sessionId: session.id })
    const first = await ctx.emit('agent/pre-step', { agent: { session } }, terminalNext(createPreStepDecision(session, '继续')))
    const notices = first.messages.filter((message) => message.source?.form === 'capacity-notice')
    assert.equal(notices.length, 1)
    assertIncludes(notices[0].content[0].text, 'L2=90% hot')
    assertIncludes(notices[0].content[0].text, 'L3=90% hot')
    const second = await ctx.emit('agent/pre-step', { agent: { session } }, terminalNext(createPreStepDecision(session, '继续')))
    assert.equal(second.messages.filter((message) => message.source?.form === 'capacity-notice').length, 0, 'the cooldown suppresses repeats')
  })
})

await test('C5a', 'L1 eviction never crosses an image-bearing event', async () => {
  const events = new Map()
  events.set(1, { seq: 1, type: 'system/message', data: { text: 'system head' } })
  for (let seq = 2; seq <= 8; seq += 1) {
    events.set(seq, { seq, type: seq % 2 === 0 ? 'user/message' : 'assistant/message', data: { text: `evictable-${seq}` } })
  }
  const measurement = createMeasurement([[1, 10], [2, 150], [3, 150], [4, 150], [5, 150], [6, 150], [7, 150], [8, 150]])
  const deriveEventMessage = (event) => (event.seq === 3
    ? { role: 'user', content: [{ type: 'image', source: { kind: 'file' } }, { type: 'text', text: 'image message' }] }
    : { role: 'user', content: [{ type: 'text', text: event?.data?.text ?? `event ${event?.seq}` }] })
  const harness = createEvictHarness({
    levels: { l2: false, l3: true },
    measurement,
    contextWindow: 1000,
    config: { evictAtRatio: 0.6, retainRatio: 0.1, maxChars: 250_000 },
  })
  const session = createEvictSession({ events, deriveEventMessage })
  await runEvictHandler(harness, session)
  assert.equal(harness.writes.length, 1, 'the text prefix before the image is still evictable')
  const prune = session.__appended[0].data
  assert.deepEqual(prune.shadowedSeqs, [2], 'selection stops before the image-bearing event')
  assertIncludes(harness.writes[0].body, '## seq 2')
  assert.equal(harness.writes[0].body.includes('## seq 3'), false)
})

await test('C5b', 'a single oversized event stops the eviction batch', async () => {
  const events = new Map()
  events.set(1, { seq: 1, type: 'system/message', data: { text: 'system head' } })
  for (let seq = 2; seq <= 8; seq += 1) {
    events.set(seq, { seq, type: seq % 2 === 0 ? 'user/message' : 'assistant/message', data: { text: `${'x'.repeat(200)}` } })
  }
  const measurement = createMeasurement([[1, 10], [2, 150], [3, 150], [4, 150], [5, 150], [6, 150], [7, 150], [8, 150]])
  const harness = createEvictHarness({
    levels: { l2: false, l3: true },
    measurement,
    contextWindow: 1000,
    config: { evictAtRatio: 0.6, retainRatio: 0.1, maxChars: 60 },
  })
  const session = createEvictSession({ events })
  await runEvictHandler(harness, session)
  assert.equal(harness.writes.length, 0, 'an oversized single event must not be archived')
  assert.equal(session.__appended.length, 0)
})

await test('C5c', 'captureLevel l2 keeps L1 evictions session-private with L3 enabled', async () => {
  const events = new Map()
  events.set(1, { seq: 1, type: 'system/message', data: { text: 'system head' } })
  for (let seq = 2; seq <= 8; seq += 1) {
    events.set(seq, { seq, type: seq % 2 === 0 ? 'user/message' : 'assistant/message', data: { text: `evictable-${seq}` } })
  }
  const measurement = createMeasurement([[1, 10], [2, 150], [3, 150], [4, 150], [5, 150], [6, 150], [7, 150], [8, 150]])
  const harness = createEvictHarness({
    levels: { l2: true, l3: true },
    measurement,
    contextWindow: 1000,
    config: { evictAtRatio: 0.6, retainRatio: 0.1, maxChars: 250_000, captureLevel: 'l2' },
  })
  const session = createEvictSession({ events })
  await runEvictHandler(harness, session)
  assert.equal(harness.writes.length, 1)
  assert.equal(harness.writes[0].scope, 'session', 'captureLevel=l2 overrides the deepest-level default')
  assert.deepEqual(harness.writes[0].tags.level, ['l2'])
})

await test('C6', 'bundle/module/client/manual cover the compress + cold-tier wave', async () => {
  const patchText = readFileSync(new URL('../packages/memex/cordis.patch.yml', import.meta.url), 'utf8')
  const rows = [...patchText.matchAll(/^\s*-\s+id:\s*([\w-]+)\s*\n\s+name:\s*'([^']+)'/gm)]
    .map((match) => ({ id: match[1], name: match[2] }))
  assert.equal(rows.length, 8)
  assert.deepEqual(rows.map((row) => row.id), ['memory', 'memory-checkpoint', 'memory-tools', 'memory-evict', 'memory-compress', 'memory-api', 'memory-ui', 'memory-commands'])
  assert.equal(rows.find((row) => row.id === 'memory-compress').name, '@qiuxu/memex/compress')
  if (!bundleBuilt) throw new Skip('bundle not built')
  const moduleDirs = readdirSync(bundleModulesUrl).filter((entry) => entry !== '.gitignore').sort()
  assert.deepEqual(moduleDirs, [
    'memory-api',
    'memory-checkpoint',
    'memory-command',
    'memory-compress',
    'memory-core',
    'memory-evict',
    'memory-local',
    'memory-seam',
    'memory-tool',
    'memory-ui',
  ], 'generated bundle must carry ten runtime modules')
  assertIncludes(uiClientSource, '冷存')
  assertIncludes(uiClientSource, '接近容量时模型会先询问')
  assertIncludes(uiClientSource, 'hotTokens')
  const toolsSource = readFileSync(new URL('../packages/memex-tool/lib/tools.js', import.meta.url), 'utf8')
  assertIncludes(toolsSource, 'memory_compress')
  assertIncludes(toolsSource, '[EXTRA CONTEXT CAPACITY]')
  assertIncludes(toolsSource, 'ask the user')
})


// R. round-2 improvements: body-less FTS, restore/GC, compressCold, history,
//    new routes, client strings, recallTerms + bilingual capacity notice ──────

await test('R1', 'FTS indexes card fields only; body search uses the hot-file fallback and grep', async () => {
  await withCore('r1', (core, root) => {
    const record = core.write({
      kind: 'fact',
      title: 'card title alpha',
      summary: 'card summary alpha',
      useWhen: 'when alpha',
      body: 'BODYSECRETZZ extra raw body text',
      workspaceKey: 'wk-r1',
    })
    const columns = core.database().prepare('PRAGMA table_info(records_fts)').all().map((row) => row.name)
    assert.deepEqual(columns, ['title', 'summary', 'use_when', 'tags', 'abstract'], 'FTS must index card fields plus a bounded cold abstract')
    assert.equal(columns.includes('body'), false, 'record bodies must not be in the FTS index')

    const cardHit = core.search({ query: 'alpha', workspaceKey: 'wk-r1' })
    assert.equal(cardHit.total, 1, 'card fields are FTS-searchable')
    assertIncludes(cardHit.hits[0].snippet, 'alpha')
    const bodyHit = core.search({ query: 'BODYSECRETZZ', workspaceKey: 'wk-r1' })
    assert.equal(bodyHit.total, 1, 'a body-only term is found by the bounded hot-file fallback')
    assert.equal(bodyHit.hits[0].id, record.id)
    assert.equal(core.grep({ pattern: 'BODYSECRETZZ', workspaceKey: 'wk-r1' }).length, 1)

    // Migration: reopen a database whose FTS still indexes the body.
    core.close()
    const legacy = new DatabaseSync(join(root, 'index.db'))
    legacy.exec("DROP TABLE records_fts")
    legacy.exec("CREATE VIRTUAL TABLE records_fts USING fts5(title, summary, use_when, tags, body, tokenize = 'trigram')")
    legacy.close()
    const reopened = new LocalStoreCore({ root, capacityTokens: 100_000 })
    try {
      const migrated = reopened.database().prepare('PRAGMA table_info(records_fts)').all().map((row) => row.name)
      assert.deepEqual(migrated, ['title', 'summary', 'use_when', 'tags', 'abstract'], 'ensure() migrates a body-indexed FTS')
      assert.equal(reopened.search({ query: 'alpha', workspaceKey: 'wk-r1' }).total, 1, 'card fields are reindexed')
      assert.equal(reopened.search({ query: 'BODYSECRETZZ', workspaceKey: 'wk-r1' }).total, 1, 'the hot-file body fallback still works after migration')
    } finally {
      reopened.close()
    }
  })
})

await test('R2', 'restoreCold moves files back hot and gcCold deletes the oldest cold records', async () => {
  await withCore('r2', (core) => {
    const first = core.write({ kind: 'fact', title: 'cold a', body: 'body a', tokens: 60, workspaceKey: 'wk-r2' })
    const second = core.write({ kind: 'fact', title: 'cold b', body: 'body b', tokens: 40, workspaceKey: 'wk-r2' })
    core.archiveCold(first.id)
    core.archiveCold(second.id)
    const coldFacets = core.facets({ workspaceKey: 'wk-r2' })
    assert.equal(coldFacets.coldCount, 2)

    const restored = core.restoreCold(first.id)
    assert.equal(restored.cold, false, 'restoreCold flips the record back to hot')
    assert.match(restored.path, /[\\/]records[\\/]wk-r2[\\/]mem_[0-9a-f]{10}\.md$/, 'the raw file moves back under records/')
    assert.ok(existsSync(restored.path))
    assert.equal(core.restoreCold(first.id).path, restored.path, 'restoreCold is idempotent for hot records')
    assert.equal(core.facets({ workspaceKey: 'wk-r2' }).coldCount, 1)

    const coldCard = core.get(second.id)
    const gcReport = core.gcCold({ workspaceKey: 'wk-r2', keepTokens: 10 })
    assert.deepEqual(gcReport.removed, [second.id], 'gcCold removes cold records above the budget, oldest first')
    assert.equal(gcReport.freedTokens, 40)
    assert.equal(core.get(second.id), undefined)
    assert.equal(existsSync(coldCard.path), false, 'the cold file is deleted')
    assert.equal(core.facets({ workspaceKey: 'wk-r2' }).coldCount, 0)
    assert.deepEqual(core.gcCold({ workspaceKey: 'wk-r2', keepTokens: 1000 }).removed, [], 'a sufficient budget removes nothing')
  })
})

await test('R3', 'compressCold cold-spills the oldest eligible records to the target ratio', async () => {
  await withCore('r3', (core) => {
    const write = (index, tokens, extra = {}) => core.write({
      kind: extra.kind ?? 'fact',
      status: extra.status,
      title: `r3 record ${index}`,
      body: 'body',
      tokens,
      workspaceKey: 'wk-r3',
    })
    for (let index = 0; index < 6; index += 1) write(index, 10_000)
    const pinned = write(6, 10_000, { status: 'pinned' })
    const thread = write(7, 10_000, { kind: 'open-thread', status: 'open' })
    assert.equal(core.facets({ workspaceKey: 'wk-r3' }).hotTokens, 80_000)

    const report = core.compressCold({ workspaceKey: 'wk-r3', scope: 'workspace', targetRatio: 0.5, minAgeMs: -1 })
    assert.equal(report.before.hot, 80_000)
    assert.equal(report.targetTokens, 50_000)
    assert.equal(report.coldMoved.length, 3, 'three 10K records release the 30K over target')
    assert.equal(report.freedTokens, 30_000)
    assert.equal(core.facets({ workspaceKey: 'wk-r3' }).hotTokens, 50_000)
    const coldIds = core.list({ workspaceKey: 'wk-r3', cold: 1 }).map((card) => card.id)
    assert.equal(coldIds.includes(pinned.id), false, 'pinned records are never auto-compressed')
    assert.equal(coldIds.includes(thread.id), false, 'open threads are never auto-compressed')
    const noop = core.compressCold({ workspaceKey: 'wk-r3', scope: 'workspace', targetRatio: 0.5, minAgeMs: -1 })
    assert.deepEqual(noop.coldMoved, [], 'a second run at target is a no-op')
  })
})

await test('R4a', 'recordCompression/compressionStats persist per-session history', async () => {
  await withCore('r4a', async (core) => {
    assert.deepEqual(core.compressionStats('sess-r4').recent, [])
    assert.equal(core.compressionStats('sess-r4').last, undefined)
    core.recordCompression({ sessionId: 'sess-r4', level: 'l3', strategy: 'cold', beforeHot: 900, afterHot: 500, coldMoved: 4, digests: 0, llmCalls: 0 })
    await settle(5)
    core.recordCompression({ sessionId: 'sess-r4', level: 'l2', strategy: 'digest', beforeHot: 700, afterHot: 300, coldMoved: 2, digests: 1, llmCalls: 1, errors: ['one batch retried'] })
    core.recordCompression({ sessionId: 'other', level: 'l3', strategy: 'cold', beforeHot: 1, afterHot: 1, coldMoved: 0, digests: 0, llmCalls: 0 })
    const stats = core.compressionStats('sess-r4')
    assert.equal(stats.count, 2)
    assert.equal(stats.last.strategy, 'digest', 'last is the newest run')
    assert.equal(stats.recent[1].strategy, 'cold')
    assert.equal(stats.last.level, 'l2')
    assert.equal(stats.last.beforeHot, 700)
    assert.equal(stats.last.errors, 'one batch retried')
    assert.equal(typeof stats.last.createdAt, 'number')
    assert.equal(stats.recent.length, 2)
    assert.equal(core.compressionStats().count, 3, 'no session filter returns the whole workspace')
  })
})

await test('R4b', 'history surfaces in /memory status, memory_index and the index API', async () => {
  const commands = createCommandsMock()
  await withInstance('r4b', {
    ctx: { services: { llm: undefined, commands: commands.service } },
    backend: { defaultLevels: 'l3', capacityTokens: 1000 },
  }, async ({ instance, ctx }) => {
    const session = createSession({ id: 'sess-r4b', cwd: '/tmp/ws-r4b' })
    await instance.write({ kind: 'fact', title: 'history record', body: 'x', tokens: 100, workspaceKey: workspaceKeyFor(session), sessionId: session.id })
    await instance.recordCompression({ sessionId: session.id, level: 'l3', strategy: 'cold', beforeHot: 900, afterHot: 500, coldMoved: 4, digests: 0, llmCalls: 0 })
    const status = await commands.definitions[0].handler({ rawInput: 'status', agent: { session } })
    assertIncludes(status.text, 'Compression runs: 1; last cold l3')
    const index = await ctx.tool('memory_index').execute({}, { agent: { session } })
    assertIncludes(index, 'Compression runs: 1; last cold l3')
  })
  await withApiStack('r4b-api', async ({ backend, routes }) => {
    const workspaceKey = seam.memoryWorkspaceKey('/tmp/ws-a', 'session-a')
    const [record] = await seedApiRecords(backend, workspaceKey, 'session-a', 1, 'Alpha')
    await backend.recordCompression({ sessionId: 'session-a', level: 'l3', strategy: 'cold', beforeHot: 100, afterHot: 50, coldMoved: 1, digests: 0, llmCalls: 0 })
    const index = await apiRequest(routes, '/api/memory.index?sessionId=session-a&limit=10')
    assert.equal(index.data.compression.count, 1)
    assert.equal(index.data.compression.last.strategy, 'cold')
    assert.equal(index.data.compression.recent.length, 1)
    assert.equal(index.data.records.some((card) => card.id === record.id), true)
  })
})

await test('R5', 'new API routes: compress, restore and gc', async () => {
  await withApiStack('r5', { backend: { defaultLevels: 'l3', capacityTokens: 1000 } }, async ({ backend, routes }) => {
    const workspaceKey = seam.memoryWorkspaceKey('/tmp/ws-a', 'session-a')
    for (let index = 0; index < 8; index += 1) {
      await backend.write({ kind: 'fact', title: `Alpha ${index}`, body: `alpha body ${index}`, tokens: 100, workspaceKey, sessionId: 'session-a' })
    }
    const compress = await apiPost(routes, '/api/memory.compress', { sessionId: 'session-a', level: 'l3', targetRatio: 0.5, minAgeMs: -1 })
    assert.equal(compress.response.status, 200)
    assert.deepEqual(compress.data.reports.map((report) => report.level), ['l3'])
    assert.equal(compress.data.reports[0].beforeHot, 800)
    assert.equal(compress.data.reports[0].coldMoved, 3)
    assert.equal(compress.data.reports[0].targetTokens, 500)
    const digest = await apiPost(routes, '/api/memory.compress', { sessionId: 'session-a', level: 'l3', strategy: 'digest' })
    assert.equal(digest.response.status, 400)
    assert.equal(digest.data.code, 'MEMORY_DIGEST_REQUIRES_MODEL')

    const coldId = (await backend.list({ workspaceKey, cold: 1 }))[0].id
    const restored = await apiPost(routes, '/api/memory.restore', { sessionId: 'session-a', id: coldId })
    assert.equal(restored.response.status, 200)
    assert.equal(restored.data.record.cold, false)
    const hotRestore = await apiPost(routes, '/api/memory.restore', { sessionId: 'session-a', id: coldId })
    assert.equal(hotRestore.response.status, 400)
    assert.equal(hotRestore.data.code, 'MEMORY_NOT_COLD')

    const gc = await apiPost(routes, '/api/memory.gc', { sessionId: 'session-a', keepTokens: 0 })
    assert.equal(gc.response.status, 200)
    assert.deepEqual(gc.data.reports.map((report) => report.level), ['l3'])
    assert.equal(gc.data.reports[0].removed, 2, 'the two remaining cold records are deleted')
    assert.equal((await backend.facets({ workspaceKey })).coldCount, 0)
  })

  await withApiStack('r5-off', { backend: { defaultLevels: 'none' } }, async ({ routes }) => {
    const compress = await apiPost(routes, '/api/memory.compress', { sessionId: 'session-a' })
    assert.equal(compress.response.status, 400)
    assert.equal(compress.data.code, 'MEMORY_LEVELS_OFF')
  })
})

await test('R6a', 'client source carries the compression / restore / capacity-warning UI', async () => {
  for (const needle of ['api/memory.compress', 'api/memory.restore', 'api/memory.level', '压缩', '回热', '⚠ 热池 ', '⚠ 接近容量', '冷存']) {
    assertIncludes(uiClientSource, needle)
  }
})

await test('R6b', 'recallTerms builds the search query and the capacity notice is bilingual', async () => {
  const root = makeRoot('r6b')
  const ctx = createFakeContext({ services: { llm: undefined } })
  const backend = new LocalMemoryStore(ctx, { root, defaultLevels: 'l3', capacityTokens: 1000 })
  const searches = []
  const memoryProxy = new Proxy(backend, {
    get(target, property, receiver) {
      if (property === 'search') {
        return async (query) => {
          searches.push(query)
          return target.search(query)
        }
      }
      const value = Reflect.get(target, property, receiver)
      return typeof value === 'function' ? value.bind(target) : value
    },
  })
  ctx.provideService('memory', memoryProxy)
  checkpointRow.apply(ctx, {})
  try {
    const session = createSession({ id: 'sess-r6b', cwd: '/tmp/ws-r6b' })
    await backend.write({ kind: 'fact', title: 'capacity filler', body: 'x', tokens: 900, workspaceKey: workspaceKeyFor(session), sessionId: session.id })
    const message = '请排查 ECONNREFUSED 端口 8787，检查 `src/api/auth.ts` 和 127.0.0.1:8787'
    const result = await ctx.emit('agent/pre-step', { agent: { session } }, terminalNext(createPreStepDecision(session, message)))
    assert.ok(searches.length >= 1, 'the checkpoint must search with the extracted recall terms')
    const recallQuery = searches[0].query
    assertIncludes(recallQuery, 'ECONNREFUSED', 'latin identifiers are extracted')
    assertIncludes(recallQuery, 'src/api/auth.ts', 'quoted spans are extracted')
    assert.ok(recallQuery.split(' ').length <= 12, 'the recall query is capped')
    const notices = result.messages.filter((entry) => entry.source?.form === 'capacity-notice')
    assert.equal(notices.length, 1)
    const noticeText = notices[0].content[0].text
    assertIncludes(noticeText, '额外上下文容量')
    assertIncludes(noticeText, '请先询问用户是否需要压缩')
    assertIncludes(noticeText, '未经用户同意不要压缩')

    searches.length = 0
    await ctx.emit('agent/pre-step', { agent: { session } }, terminalNext(createPreStepDecision(session, '?!。')))
    assert.equal(searches[0]?.query, '?!。', 'a query with no distinctive terms falls back to the first 120 chars')
  } finally {
    await ctx.dispose()
    rmSync(root, { recursive: true, force: true })
  }
})

await test('R7', 'record route paginates the body and reports truncation flags', async () => {
  await withApiStack('r7', async ({ backend, routes }) => {
    const workspaceKey = seam.memoryWorkspaceKey('/tmp/ws-a', 'session-a')
    const body = 'abcdefghij'.repeat(30)
    const record = await backend.write({ kind: 'fact', title: 'long body', body, workspaceKey, sessionId: 'session-a' })
    const page = await apiRequest(routes, `/api/memory.record?sessionId=session-a&id=${encodeURIComponent(record.id)}&offset=10&limit=50`)
    assert.equal(page.response.status, 200)
    assert.equal(page.data.bodyOffset, 10)
    assert.equal(page.data.bodyLimit, 50)
    assert.equal(page.data.bodyTotalChars, body.length)
    assert.equal(page.data.body, body.slice(10, 60), 'body is sliced by the offset/limit window')
    assert.equal(page.data.truncated, true, 'a partial window is reported as truncated')
    // FINDINGS: the API contract named `bodyTruncated`; the implementation only
    // returns `truncated`.
    assert.equal(typeof page.data.bodyTruncated, 'boolean', 'the record route must expose bodyTruncated')
  })
})


// S. phase 1+2: query terms, hybrid recall, metrics, sensitive eviction, backup ─

await test('S1', 'memoryQueryTerms extracts identifiers, quoted spans and CJK n-grams', async () => {
  const terms = seam.memoryQueryTerms('Fix ECONNREFUSED in `src/api/auth.ts` and 额外上下文容量压缩, the and 需要 how to')
  assertIncludes(terms.join(' '), 'ECONNREFUSED', 'latin identifiers are kept verbatim')
  assertIncludes(terms.join(' '), 'src/api/auth.ts', 'quoted paths are kept whole')
  assert.equal(terms.filter((term) => term.toLowerCase() === 'econnrefused').length, 1, 'latin terms are deduplicated case-insensitively')
  assertIncludes(terms.join(' '), '额外上下文容量压缩', 'a CJK run contributes its capped full run')
  assertIncludes(terms.join(' '), '上下文', 'CJK trigrams are extracted')
  assertIncludes(terms.join(' '), '额外', 'CJK bigrams are extracted')
  for (const stopword of ['the', 'and', '需要', 'how', 'to']) {
    assert.equal(terms.includes(stopword), false, `stopword ${stopword} must be filtered`)
  }
  const repeated = seam.memoryQueryTerms('ECONNREFUSED ECONNREFUSED econnrefused')
  assert.equal(repeated.filter((term) => term.toLowerCase() === 'econnrefused').length, 1, 'terms are deduplicated')
  const longText = Array.from({ length: 60 }, (_, index) => `identifier${index}`).join(' ')
  assert.ok(seam.memoryQueryTerms(longText).length <= 20, 'the default term budget is 20')
  assert.equal(seam.memoryQueryTerms(longText, 3).length, 3, 'maxTerms caps the result')
  assert.deepEqual(seam.memoryQueryTerms(''), [], 'empty text yields no terms')
  assert.deepEqual(seam.memoryQueryTerms('the and 需要'), [], 'stopword-only text yields no terms')
})

await test('S2', 'hybrid search recalls cold abstracts, hot bodies and ranks field matches', async () => {
  await withCore('s2', (core) => {
    const titleHit = core.write({ kind: 'fact', title: 'ranking needle title', summary: 'plain', body: 'plain body', workspaceKey: 'wk-s2' })
    const summaryHit = core.write({ kind: 'fact', title: 'plain title', summary: 'ranking needle summary', body: 'plain body', workspaceKey: 'wk-s2' })
    const tagHit = core.write({ kind: 'fact', title: 'plain title two', summary: 'plain', body: 'plain body', tags: { topic: ['ranking'] }, workspaceKey: 'wk-s2' })
    const ranked = core.search({ query: 'ranking needle', workspaceKey: 'wk-s2', limit: 10 })
    assert.equal(ranked.total, 3, 'title, summary and tag matches are all retrieved')
    assert.equal(ranked.hits[0].id, titleHit.id, 'title matches rank above summary/tag matches')
    const positions = new Map(ranked.hits.map((hit, index) => [hit.id, index]))
    assert.ok(positions.get(titleHit.id) < positions.get(summaryHit.id), 'title beats summary')
    assert.ok(positions.get(tagHit.id) !== undefined)

    const bodyOnly = core.write({ kind: 'fact', title: 'hot only', summary: 'plain', body: 'ZZBODYSECRET unique body identifier', workspaceKey: 'wk-s2' })
    const fallback = core.search({ query: 'ZZBODYSECRET', workspaceKey: 'wk-s2' })
    assert.equal(fallback.total, 1, 'a hot body-only identifier is found by the body fallback')
    assert.equal(fallback.hits[0].id, bodyOnly.id)

    const cold = core.write({ kind: 'fact', title: 'cold archive', summary: 'plain', body: 'PHASE2COLDTERM archived cold body natural language content '.repeat(20), tokens: 80, workspaceKey: 'wk-s2' })
    core.archiveCold(cold.id)
    const abstract = core.database().prepare('SELECT abstract FROM records WHERE id = ?').get(cold.id).abstract
    assert.ok(abstract.length > 0 && abstract.length <= 1000, 'archiveCold stores a bounded abstract')
    assertIncludes(abstract, 'PHASE2COLDTERM')
    const coldHit = core.search({ query: 'PHASE2COLDTERM', workspaceKey: 'wk-s2' })
    assert.equal(coldHit.total, 1, 'a cold body term is searchable through the bounded abstract')
    assert.equal(coldHit.hits[0].id, cold.id)

    const cjk = core.write({ kind: 'fact', title: '额外上下文容量压缩策略', summary: '额外上下文容量摘要', body: 'plain', workspaceKey: 'wk-s2' })
    const natural = core.search({ query: '额外上下文容量压缩怎么做', workspaceKey: 'wk-s2' })
    assert.ok(natural.total >= 1, 'natural CJK queries recall card matches')
    assert.equal(natural.hits[0].id, cjk.id)
  })
})

await test('S3', 'GET /api/memory.metrics reports pool/cold/eviction/compression metrics', async () => {
  await withApiStack('s3', async ({ backend, routes }) => {
    const workspaceKey = seam.memoryWorkspaceKey('/tmp/ws-a', 'session-a')
    const records = []
    for (let index = 0; index < 3; index += 1) {
      records.push(await backend.write({ kind: 'fact', title: `metric ${index}`, body: 'x', tokens: 100, workspaceKey, sessionId: 'session-a' }))
    }
    await backend.archiveCold(records[2].id)
    await backend.recordEviction({ sessionId: 'session-a', start: 1, end: 2, recordId: 'l1_metric', shadowedTokens: 150 })
    await backend.recordCompression({ sessionId: 'session-a', level: 'l3', strategy: 'cold', beforeHot: 300, afterHot: 200, coldMoved: 1, digests: 0, llmCalls: 0 })
    const metrics = await apiRequest(routes, '/api/memory.metrics?sessionId=session-a')
    assert.equal(metrics.response.status, 200)
    const data = metrics.data
    assert.equal(data.ok, true)
    assert.equal(typeof data.generatedAt, 'number')
    assert.deepEqual(data.levels, { l2: false, l3: true })
    assert.deepEqual(Object.keys(data.l2).sort(), ['capacityTokens', 'coldCount', 'coldTokens', 'hotCount', 'hotTokens'].sort())
    assert.equal(data.l2.hotCount, 0)
    assert.equal(data.l3.hotCount, 2)
    assert.equal(data.l3.hotTokens, 200)
    assert.equal(data.l3.coldCount, 1)
    assert.equal(data.l3.coldTokens, 100)
    assert.equal(data.l3.capacityTokens, 100_000_000)
    assert.deepEqual(Object.keys(data.visible).sort(), ['byKind', 'coldTokens', 'count', 'hotTokens'].sort())
    assert.equal(data.visible.count, 3)
    assert.equal(data.visible.hotTokens, 200)
    assert.equal(data.visible.coldTokens, 100)
    assert.equal(data.visible.byKind.fact, 3)
    assert.deepEqual(data.l1Evicted, { count: 1, tokens: 150 })
    assert.equal(data.compression.count, 1)
    assert.equal(data.compression.last.strategy, 'cold')
    assert.equal(routes.length, 9, 'the metrics route is the ninth Fetch route')
  })
})

await test('S4', 'sensitive eviction forces L2, skips under L3-only and honors sensitivePolicy:off', async () => {
  const secret = 'api_key: DUMMY-SECRET-VALUE-1234'
  const events = new Map()
  events.set(1, { seq: 1, type: 'system/message', data: { text: 'system head' } })
  events.set(2, { seq: 2, type: 'user/message', data: { text: `deployment credential ${secret}` } })
  for (let seq = 3; seq <= 7; seq += 1) {
    events.set(seq, { seq, type: seq % 2 === 0 ? 'user/message' : 'assistant/message', data: { text: `normal context ${seq}` } })
  }
  const measurement = createMeasurement([[1, 10], [2, 120], [3, 120], [4, 120], [5, 120], [6, 120], [7, 120]])
  const both = createEvictHarness({ levels: { l2: true, l3: true }, measurement, contextWindow: 1000 })
  await runEvictHandler(both, createEvictSession({ events }))
  assert.equal(both.writes.length, 1)
  assert.equal(both.writes[0].scope, 'session', 'sensitive content is forced into the private L2')
  assert.deepEqual(both.writes[0].tags.sensitive, ['true'])
  assert.deepEqual(both.writes[0].tags.level, ['l2'])

  const l3Only = createEvictHarness({ levels: { l2: false, l3: true }, measurement, contextWindow: 1000 })
  const l3Session = createEvictSession({ events })
  await runEvictHandler(l3Only, l3Session)
  assert.equal(l3Only.writes.length, 0, 'sensitive content must not be archived into shared L3')
  assert.equal(l3Session.__appended.length, 0)
  assert.ok(l3Only.warnings.some((line) => line.includes('sensitive content and only L3 is enabled')), 'the skip is warned')

  const off = createEvictHarness({ levels: { l2: false, l3: true }, measurement, contextWindow: 1000, config: { sensitivePolicy: 'off' } })
  await runEvictHandler(off, createEvictSession({ events }))
  assert.equal(off.writes.length, 1)
  assert.equal(off.writes[0].scope, 'workspace', 'sensitivePolicy:off restores the default capture scope')
  assert.equal(off.writes[0].tags.sensitive, undefined)
})

await test('S5', 'memory-backup backup/verify/restore round-trips a store with a tamper check', async () => {
  const root = makeRoot('s5-root')
  const backupDir = makeRoot('s5-backup')
  const restoreDir = makeRoot('s5-restore')
  const core = new LocalStoreCore({ root, capacityTokens: 100_000 })
  const hot = core.write({ kind: 'fact', title: 'backup hot', body: 'backup hot body', tokens: 40, workspaceKey: 'wk-s5' })
  const cold = core.write({ kind: 'fact', title: 'backup cold', body: 'BACKUPCOLDNEEDLE archived detail', tokens: 60, workspaceKey: 'wk-s5' })
  core.archiveCold(cold.id)
  core.close()

  const script = fileURLToPath(new URL('../scripts/memory-backup.mjs', import.meta.url))
  const register = fileURLToPath(new URL('./register.mjs', import.meta.url))
  const runBackup = (...args) => spawnSync(process.execPath, ['--import', register, script, ...args], { encoding: 'utf8' })

  const backup = runBackup('backup', '--root', root, '--out', backupDir)
  assert.equal(backup.status, 0, backup.stderr)
  assertIncludes(backup.stdout, 'backup:')
  const manifest = JSON.parse(readFileSync(join(backupDir, 'manifest.json'), 'utf8'))
  assert.equal(manifest.format, 1)
  assert.equal(manifest.sourceRoot, root)
  assert.match(manifest.db.sha256, /^[0-9a-f]{64}$/)
  assert.ok(manifest.files.some((entry) => entry.path.startsWith('records/')), 'hot record files are backed up')
  assert.ok(manifest.files.some((entry) => entry.path.startsWith('cold/')), 'cold record files are backed up')

  const verify = runBackup('verify', '--dir', backupDir)
  assert.equal(verify.status, 0, verify.stderr)
  assertIncludes(verify.stdout, 'verify: OK')

  const restore = runBackup('restore', '--dir', backupDir, '--to', restoreDir)
  assert.equal(restore.status, 0, restore.stderr)
  assertIncludes(restore.stdout, 'restore:')
  const restored = new LocalStoreCore({ root: restoreDir, capacityTokens: 100_000 })
  try {
    const restoredHot = restored.get(hot.id)
    assert.ok(restoredHot, 'hot records survive the restore')
    assert.equal(restoredHot.body, 'backup hot body')
    const restoredCold = restored.get(cold.id)
    assert.equal(restoredCold.cold, true, 'cold flags survive the restore')
    assert.equal(restored.search({ query: 'BACKUPCOLDNEEDLE', workspaceKey: 'wk-s5' }).total, 1, 'cold abstracts survive the restore')
  } finally {
    restored.close()
  }

  const nonEmpty = join(makeRoot('s5-nonempty'), 'sentinel.txt')
  writeFileSync(nonEmpty, 'x')
  const refused = runBackup('restore', '--dir', backupDir, '--to', join(nonEmpty, '..'))
  assert.equal(refused.status, 1)
  assertIncludes(refused.stderr, 'not empty')

  const copiedRecord = manifest.files.find((entry) => entry.path.startsWith('records/')).path
  writeFileSync(join(backupDir, copiedRecord), 'tampered')
  const tampered = runBackup('verify', '--dir', backupDir)
  assert.equal(tampered.status, 1)
  assertIncludes(tampered.stderr, 'verify FAILED')
})


// ── v0.2.0: agent-agnostic core, MCP server, Claude Code / Codex adapters ───

const core = await import('@qiuxu/memex-core')
const profiles = await import('@qiuxu/memex-core/model-profiles')
const manual = await import('@qiuxu/memex-core/manual')
const { AgentMemory } = await import('@qiuxu/memex-core/engine')
const REGISTER = fileURLToPath(new URL('./register.mjs', import.meta.url))
const MCP_SERVER = fileURLToPath(new URL('../packages/memex-mcp/bin/server.mjs', import.meta.url))
const CLAUDE_CLI = fileURLToPath(new URL('../packages/memex-claude/bin/cli.mjs', import.meta.url))
const CODEX_CLI = fileURLToPath(new URL('../packages/memex-codex/bin/cli.mjs', import.meta.url))

/** Run a Node CLI with the offline loader so `@qiuxu/*` resolves without node_modules. */
function runNode(script, args, options = {}) {
  return spawnSync(process.execPath, ['--import', REGISTER, script, ...args], {
    input: options.input ?? '',
    encoding: 'utf8',
    timeout: 60000,
    env: { ...process.env, ...(options.env ?? {}) },
  })
}

/** Send newline-delimited JSON-RPC messages to the MCP server; return parsed replies keyed by id. */
function mcpExchange(root, args, messages) {
  const result = runNode(MCP_SERVER, ['--root', root, ...args], { input: `${messages.map((message) => JSON.stringify(message)).join('\n')}\n` })
  assert.equal(result.status, 0, `MCP server must exit 0 (stderr: ${result.stderr})`)
  assert.ok(result.stdout.trim().length > 0, `MCP server produced no stdout (stderr: ${result.stderr}, status: ${result.status}, signal: ${result.signal})`)
  const replies = new Map()
  for (const line of result.stdout.split('\n')) {
    if (line.trim().length === 0) continue
    const message = JSON.parse(line)
    if (message.id !== undefined) replies.set(message.id, message)
  }
  return replies
}

await test('U1', 'agent-agnostic core has no host dependencies and the DSH seam re-exports it', async () => {
  const coreFiles = ['index.js', 'lib/store.js', 'lib/model-profiles.js', 'lib/manual.js', 'lib/engine.js']
  for (const file of coreFiles) {
    const source = readFileSync(new URL(`../packages/memex-core/${file}`, import.meta.url), 'utf8')
    assert.doesNotMatch(source, /@deepseek-ai\//, `core/${file} must not import DSH host packages`)
  }
  assert.equal(core.MemoryStore, undefined, 'the core exposes vocabulary/helpers, not the Cordis service')
  assert.equal(typeof seam.MemoryStore, 'function', 'the DSH seam still exposes the Service subclass')
  assert.equal(seam.MEMORY_LEVELS, core.MEMORY_LEVELS, 'the seam re-exports the core bindings')
  assert.deepEqual(seam.memoryQueryTerms('如何恢复额外上下文 memory_search'), core.memoryQueryTerms('如何恢复额外上下文 memory_search'))
  const bundlePkg = JSON.parse(readFileSync(new URL('../packages/memex/package.json', import.meta.url), 'utf8'))
  assert.equal(bundlePkg.exports['./core'], './modules/memory-core/index.js', 'bundle must expose the core module')
})

await test('U2', 'model profiles resolve per family and tune injection, budgets and digest prompts', async () => {
  const cases = [
    ['claude-sonnet-4-20250514', 'claude'],
    ['gpt-5-codex', 'openai'],
    ['gemini-2.5-pro', 'gemini'],
    ['deepseek-chat', 'deepseek'],
    ['qwen-max', 'qwen'],
    ['kimi-k2', 'kimi'],
    ['glm-4.6', 'glm'],
    ['llama-3.1-70b', 'llama'],
    ['grok-4', 'xai'],
    ['command-r-plus', 'cohere'],
    ['gemma-3-27b', 'gemma'],
    ['phi-4', 'phi'],
    ['nova-pro', 'generic'],
    ['some-unknown-7b', 'generic'],
  ]
  for (const [modelId, expected] of cases) {
    const profile = profiles.resolveModelProfile(modelId)
    assert.equal(profile.id, expected, `${modelId} must resolve to ${expected}`)
    assert.ok(profile.windowTokens > 0 && profile.catalogTokens > 0, `${modelId} profile must carry budgets`)
  }
  const claude = profiles.resolveModelProfile('claude-sonnet-4')
  assert.equal(claude.injectionStyle, 'xml')
  assert.equal(profiles.profileTokens('x'.repeat(3600), claude), 1000, 'claude profile estimates 3.6 chars/token')
  assert.ok(profiles.formatMemoryInjection(claude, 'catalog', 'hello').startsWith('<memory-catalog>'))
  const gpt = profiles.resolveModelProfile('gpt-5')
  assert.equal(gpt.injectionStyle, 'markdown')
  assert.ok(profiles.formatMemoryInjection(gpt, 'recall', 'hit').includes('## Memory recall'))
  const llama = profiles.resolveModelProfile('llama-3.1')
  assert.ok(profiles.formatMemoryInjection(llama, 'catalog', 'x').startsWith('[MEMORY CATALOG]'))
  const digest = profiles.digestPrompt(claude, { ids: ['mem_a', 'mem_b'], maxTokens: 200, text: 'batch' })
  assert.ok(digest.system.includes('ids:'), 'digest prompt must require an ids line')
  assert.ok(digest.system.includes('200'), 'digest prompt must carry the token budget')
  assert.ok(digest.user.includes('mem_a'))
  const overridden = profiles.resolveModelProfile('claude', { windowTokens: 12345 })
  assert.equal(overridden.windowTokens, 12345)
  const claudeManual = manual.buildMemoryManual(claude, { agent: 'Claude Code', root: '/tmp/mem', levels: ['l2', 'l3'] })
  assertIncludes(claudeManual, 'Anthropic Claude profile')
  assertIncludes(claudeManual, 'memory_search')
  assertIncludes(claudeManual, 'data')
  assertIncludes(claudeManual, String(claude.catalogTokens))
  assertIncludes(claudeManual, 'Claude Code')
})

await test('U3', 'generic MCP server speaks JSON-RPC: tools list/call, search, open, index', async () => {
  const root = makeRoot('u3')
  const replies = mcpExchange(root, ['--agent', 'test', '--model', 'claude-sonnet-4', '--levels', 'l2,l3', '--session', 'u3-session'], [
    { jsonrpc: '2.0', id: 1, method: 'initialize', params: {} },
    { jsonrpc: '2.0', method: 'notifications/initialized' },
    { jsonrpc: '2.0', id: 2, method: 'tools/list' },
    { jsonrpc: '2.0', id: 3, method: 'tools/call', params: { name: 'memory_write', arguments: { kind: 'fact', title: 'MCP smoke fact', body: 'The deploy id is FOO-42 and the retry budget is 3.', summary: 'deploy id FOO-42', useWhen: 'read when continuing the deployment work' } } },
    { jsonrpc: '2.0', id: 4, method: 'tools/call', params: { name: 'memory_search', arguments: { query: 'deploy id FOO-42' } } },
    { jsonrpc: '2.0', id: 5, method: 'tools/call', params: { name: 'memory_index', arguments: {} } },
    { jsonrpc: '2.0', id: 6, method: 'resources/read', params: { uri: 'memory://catalog' } },
    { jsonrpc: '2.0', id: 7, method: 'ping' },
  ])
  const init = replies.get(1).result
  assert.equal(init.serverInfo.name, 'memex')
  assert.equal(init.protocolVersion, '2024-11-05')
  assertIncludes(init.instructions, 'Anthropic Claude')
  const tools = replies.get(2).result.tools.map((tool) => tool.name).sort()
  assert.deepEqual(tools, ['memory_compress', 'memory_forget', 'memory_grep', 'memory_index', 'memory_list', 'memory_open', 'memory_restore', 'memory_search', 'memory_set_status', 'memory_write'])
  const writeText = replies.get(3).result.content[0].text
  assertIncludes(writeText, 'Stored mem_')
  const recordId = writeText.match(/mem_[0-9a-f]{10}/)[0]
  const searchText = replies.get(4).result.content[0].text
  assertIncludes(searchText, recordId)
  assertIncludes(searchText, 'MCP smoke fact')
  assertIncludes(replies.get(5).result.content[0].text, 'Memory catalog')
  assertIncludes(replies.get(6).result.contents[0].text, 'Memory catalog')
  assert.deepEqual(replies.get(7).result, {})
  const files = readdirSync(join(root, 'records'), { recursive: true }).filter((entry) => String(entry).endsWith('.md'))
  assert.equal(files.length, 1, 'the MCP write must persist one markdown record')
  // open returns the body and paging metadata.
  const opened = mcpExchange(root, ['--agent', 'test', '--model', 'claude-sonnet-4', '--levels', 'l2,l3', '--session', 'u3-session'], [
    { jsonrpc: '2.0', id: 1, method: 'tools/call', params: { name: 'memory_open', arguments: { id: recordId, maxChars: 500 } } },
  ]).get(1).result.content[0].text
  assertIncludes(opened, 'FOO-42')
  assertIncludes(opened, 'body')
})

await test('U4', 'MCP cold compression frees capacity and cold records remain openable', async () => {
  const root = makeRoot('u4')
  const writes = [1, 2, 3].map((index) => ({ jsonrpc: '2.0', id: index, method: 'tools/call', params: { name: 'memory_write', arguments: { kind: 'episode', title: `Cold note ${index}`, body: `${'detail '.repeat(200)}cold-note-${index}`, useWhen: 'read when testing cold compression' } } }))
  const replies = mcpExchange(root, ['--agent', 'test', '--model', 'deepseek-chat', '--levels', 'l3', '--session', 'u4-session', '--capacity', '120'], [
    ...writes,
    { jsonrpc: '2.0', id: 9, method: 'tools/call', params: { name: 'memory_compress', arguments: { level: 'l3', targetRatio: 0.3, minAgeMs: 0 } } },
    { jsonrpc: '2.0', id: 10, method: 'tools/call', params: { name: 'memory_index', arguments: {} } },
  ])
  assert.match(replies.get(9).result.content[0].text, /cold-moved [1-9]/)
  assertIncludes(replies.get(10).result.content[0].text, 'cold records')
})

await test('U5', 'Claude Code init writes .mcp.json, hooks, and a model-tailored CLAUDE.md', async () => {
  const project = makeRoot('u5-project')
  const root = makeRoot('u5-mem')
  const result = runNode(CLAUDE_CLI, ['init', '--project', project, '--root', root, '--model', 'claude-sonnet-4', '--levels', 'l2,l3'])
  assert.equal(result.status, 0, result.stderr)
  const mcp = JSON.parse(readFileSync(join(project, '.mcp.json'), 'utf8'))
  const server = mcp.mcpServers['memex']
  assert.equal(server.command, process.execPath)
  assert.ok(server.args[0].endsWith('memex-mcp/bin/server.mjs'))
  assert.deepEqual(server.args.slice(1, 3), ['--root', root])
  assertIncludes(server.args.join(' '), '--agent claude-code')
  const settings = JSON.parse(readFileSync(join(project, '.claude', 'settings.json'), 'utf8'))
  for (const event of ['SessionStart', 'UserPromptSubmit', 'PreCompact', 'SessionEnd']) {
    assert.ok(Array.isArray(settings.hooks[event]) && settings.hooks[event].length > 0, `${event} hook must be registered`)
    assertIncludes(settings.hooks[event][0].hooks[0].command, 'memex-claude/bin/cli.mjs')
    assertIncludes(settings.hooks[event][0].hooks[0].command, `hook ${event}`)
  }
  const claudeMd = readFileSync(join(project, 'CLAUDE.md'), 'utf8')
  assertIncludes(claudeMd, '<!-- memex:start -->')
  assertIncludes(claudeMd, 'Anthropic Claude profile')
  assertIncludes(claudeMd, 'memory_search')
  // Idempotent: re-running init must not duplicate the manual or the hooks.
  const again = runNode(CLAUDE_CLI, ['init', '--project', project, '--root', root, '--model', 'claude-sonnet-4', '--levels', 'l2,l3'])
  assert.equal(again.status, 0, again.stderr)
  assert.equal((readFileSync(join(project, 'CLAUDE.md'), 'utf8').match(/memex:start/g) ?? []).length, 1)
  assert.equal(JSON.parse(readFileSync(join(project, '.claude', 'settings.json'), 'utf8')).hooks.PreCompact.length, 1)
})

await test('U6', 'Claude Code hooks inject catalog/recall and archive transcripts before compaction', async () => {
  const project = makeRoot('u6-project')
  const root = makeRoot('u6-mem')
  const session = 'u6-session'
  const engine = new AgentMemory({ root, cwd: project, sessionId: session, levels: ['l2', 'l3'], model: 'claude-sonnet-4', agent: 'test' })
  try {
    engine.write({ kind: 'fact', title: 'Deployment identifier fact', body: 'DEPLOY_ID=abc123; rollback keeps the previous deployment id.', summary: 'deploy id abc123', useWhen: 'read when continuing deployment work' })
  } finally {
    engine.close()
  }
  const start = runNode(CLAUDE_CLI, ['hook', 'session-start', '--root', root, '--project', project, '--model', 'claude-sonnet-4', '--levels', 'l2,l3'], { input: JSON.stringify({ session_id: session, cwd: project }) })
  assert.equal(start.status, 0, start.stderr)
  const startPayload = JSON.parse(start.stdout.trim())
  assertIncludes(startPayload.hookSpecificOutput.additionalContext, '<memory-catalog>')
  assertIncludes(startPayload.hookSpecificOutput.additionalContext, 'Deployment identifier fact')
  const prompt = runNode(CLAUDE_CLI, ['hook', 'user-prompt', '--root', root, '--project', project, '--model', 'claude-sonnet-4', '--levels', 'l2,l3'], { input: JSON.stringify({ session_id: session, cwd: project, prompt: 'what is the deployment id we must keep?' }) })
  assert.equal(prompt.status, 0, prompt.stderr)
  const recall = JSON.parse(prompt.stdout.trim()).hookSpecificOutput.additionalContext
  assertIncludes(recall, '<memory-recall>')
  assertIncludes(recall, 'Deployment identifier fact')
  const transcript = join(project, 'transcript.jsonl')
  writeFileSync(transcript, [JSON.stringify({ type: 'user', message: { role: 'user', content: 'remember DEPLOY_ID=abc123' } }), JSON.stringify({ type: 'assistant', message: { role: 'assistant', content: 'noted' } })].join('\n'))
  const compact = runNode(CLAUDE_CLI, ['hook', 'pre-compact', '--root', root, '--project', project, '--model', 'claude-sonnet-4', '--levels', 'l2,l3'], { input: JSON.stringify({ session_id: session, cwd: project, transcript_path: transcript, trigger: 'auto' }) })
  assert.equal(compact.status, 0, compact.stderr)
  const receipt = JSON.parse(compact.stdout.trim()).hookSpecificOutput.additionalContext
  assertIncludes(receipt, 'ids:')
  const check = new AgentMemory({ root, cwd: project, sessionId: session, levels: ['l2', 'l3'], model: 'claude-sonnet-4', agent: 'test' })
  try {
    const found = check.search({ query: 'Claude Code transcript' })
    assert.ok(found.hits.length >= 1, 'the pre-compact hook must archive the transcript')
    const contentSearch = check.search({ query: 'remember DEPLOY_ID abc123' })
    assert.ok(contentSearch.hits.length >= 1, 'the transcript head must remain searchable through the archived summary')
  } finally {
    check.close()
  }
})

await test('U7', 'Codex init writes AGENTS.md and prints a working MCP config snippet', async () => {
  const project = makeRoot('u7-project')
  const root = makeRoot('u7-mem')
  const result = runNode(CODEX_CLI, ['init', '--project', project, '--root', root, '--model', 'gpt-5-codex', '--levels', 'l3'])
  assert.equal(result.status, 0, result.stderr)
  assertIncludes(result.stdout, 'mcp_servers.memex')
  assertIncludes(result.stdout, 'codex mcp add')
  const agents = readFileSync(join(project, 'AGENTS.md'), 'utf8')
  assertIncludes(agents, '<!-- memex:start -->')
  assertIncludes(agents, 'OpenAI Codex ·')
  assertIncludes(agents, 'memory_search')
  const snippet = runNode(CODEX_CLI, ['config', '--project', project, '--root', root, '--model', 'gpt-5-codex', '--levels', 'l3'])
  assert.equal(snippet.status, 0, snippet.stderr)
  assertIncludes(snippet.stdout, '[mcp_servers.memex]')
  assertIncludes(snippet.stdout, 'memex-mcp/bin/server.mjs')
  assertIncludes(snippet.stdout, '--agent')
  assertIncludes(snippet.stdout, 'codex')
})

await test('U8', 'DSH seam and core stay one vocabulary: engine writes are visible to DSH search', async () => {
  const root = makeRoot('u8')
  const cwd = '/tmp/u8-workspace'
  const engine = new AgentMemory({ root, cwd, sessionId: 'u8-session', levels: ['l2', 'l3'], model: 'deepseek-chat', agent: 'test' })
  let record
  try {
    record = engine.write({ kind: 'decision', title: 'Core/DSH vocabulary parity decision', body: 'The agent-agnostic core and the DSH seam share one record vocabulary.', summary: 'shared vocabulary', useWhen: 'read when checking adapter parity' })
    const hit = engine.search({ query: 'shared vocabulary parity' })
    assert.ok(hit.hits.some((card) => card.id === record.id))
    const index = engine.index()
    assert.ok(index.catalog.includes(record.id))
    const opened = engine.open({ id: record.id })
    assertIncludes(opened.body, 'agent-agnostic core')
  } finally {
    engine.close()
  }
  const reload = new AgentMemory({ root, cwd, sessionId: 'u8-session', levels: ['l2', 'l3'], model: 'deepseek-chat', agent: 'dsh-test' })
  try {
    assert.equal(reload.open({ id: record.id }).title, 'Core/DSH vocabulary parity decision')
  } finally {
    reload.close()
  }
})


await test('U9', 'per-model rerank weights tune ranking and merge over defaults', async () => {
  assert.deepEqual(core.DEFAULT_RERANK_WEIGHTS, { title: 3, summary: 1.4, useWhen: 1.2, tags: 1.6, abstract: 0.9, body: 4.5, recency: 0.4, coldPenalty: 0.1, bm25: 0.8 })
  assert.equal(profiles.resolveModelProfile('claude').rerank.title, 3.2)
  assert.equal(profiles.resolveModelProfile('gemini').rerank.tags, 2)
  assert.equal(profiles.resolveModelProfile('deepseek-chat').rerank.abstract, 1.3)
  assert.equal(profiles.resolveModelProfile('llama-3.1').rerank.abstract, 0.7)
  assert.equal(profiles.resolveModelProfile('unknown').rerank.title, 3)
  const { LocalStoreCore } = await import('../packages/memex-core/lib/store.js')
  const root = makeRoot('u9')
  const store = new LocalStoreCore({ root, capacityTokens: 1_000_000, sessionCapacityTokens: 100_000, defaultLevels: { l2: false, l3: false } })
  try {
    const titleRecord = store.write({ kind: 'fact', title: 'Needle title record', body: 'title asks about needle', workspaceKey: 'wk-u9' })
    const tagRecord = store.write({ kind: 'fact', title: 'Tag match record', body: 'tagged evidence', tags: { needle: ['true'] }, workspaceKey: 'wk-u9' })
    const byDefault = store.search({ query: 'needle', workspaceKey: 'wk-u9', scope: 'workspace', limit: 5 })
    assert.equal(byDefault.hits[0].id, titleRecord.id, 'default weights prefer the title hit')
    const byTags = store.search({ query: 'needle', workspaceKey: 'wk-u9', scope: 'workspace', limit: 5, rerank: { tags: 6, title: 0.2 } })
    assert.equal(byTags.hits[0].id, tagRecord.id, 'tag-boosted rerank prefers the tag hit')
  } finally {
    store.close()
    rmSync(root, { recursive: true, force: true })
  }
})

await test('U10', 'engine applies the model profile rerank and accepts per-integration overrides', async () => {
  const root = makeRoot('u10')
  const writer = new AgentMemory({ root, cwd: '/tmp/u10-ws', sessionId: 'u10', levels: ['l3'], model: 'claude-sonnet-4', agent: 'test' })
  let titleId
  let tagId
  try {
    titleId = writer.write({ kind: 'fact', title: 'Needle title record', body: 'title asks about needle', workspaceKey: 'wk-u10' }).id
    tagId = writer.write({ kind: 'fact', title: 'Tag match record', body: 'tagged evidence', tags: { needle: ['true'] }, workspaceKey: 'wk-u10' }).id
  } finally {
    writer.close()
  }
  const defaultEngine = new AgentMemory({ root, cwd: '/tmp/u10-ws', sessionId: 'u10', levels: ['l3'], model: 'claude-sonnet-4', agent: 'test' })
  try {
    assert.equal(defaultEngine.search({ query: 'needle' }).hits[0].id, titleId, 'claude profile keeps title-first ranking')
  } finally {
    defaultEngine.close()
  }
  const overridden = new AgentMemory({ root, cwd: '/tmp/u10-ws', sessionId: 'u10', levels: ['l3'], model: 'gpt-5', agent: 'test', profileOverrides: { rerank: { tags: 6, title: 0.2 } } })
  try {
    const hits = overridden.search({ query: 'needle' }).hits
    assert.equal(hits[0].id, tagId, 'profileOverrides.rerank reaches store.search')
    assert.equal(overridden.profile.id, 'openai')
    assert.equal(overridden.profile.rerank.tags, 6)
  } finally {
    overridden.close()
  }
})


await test('U11', 'PreCompact archives transcripts larger than the store body limit instead of failing', async () => {
  const project = makeRoot('u11-project')
  const root = makeRoot('u11-mem')
  const transcript = join(project, 'transcript-big.jsonl')
  const line = JSON.stringify({ type: 'assistant', message: { role: 'assistant', content: 'x'.repeat(180) } })
  const targetBytes = MEMORY_TEXT_LIMITS.body + 1024
  writeFileSync(transcript, Array.from({ length: Math.ceil(targetBytes / line.length) }, () => line).join('\n'))
  const result = runNode(CLAUDE_CLI, ['hook', 'pre-compact', '--root', root, '--project', project, '--model', 'claude-sonnet-4', '--levels', 'l3'], { input: JSON.stringify({ session_id: 'u11-session', cwd: project, transcript_path: transcript, trigger: 'auto' }) })
  assert.equal(result.status, 0, result.stderr)
  const payload = JSON.parse(result.stdout.trim())
  const receipt = payload.hookSpecificOutput.additionalContext
  assertIncludes(receipt, 'ids:')
  const recordId = receipt.match(/mem_[0-9a-f]{10}/)[0]
  const engine = new AgentMemory({ root, cwd: project, sessionId: 'u11-session', levels: ['l3'], model: 'claude-sonnet-4', agent: 'test' })
  try {
    const record = engine.store.get(recordId)
    assert.ok(record !== undefined, 'the oversized transcript must still be archived')
    assert.ok(record.body.length <= MEMORY_TEXT_LIMITS.body, 'archived body must respect the store limit')
    assert.ok(record.body.includes('clipped at the memory body limit'), 'the archive must be explicitly clipped')
  } finally {
    engine.close()
  }
})

await test('U12', 'injected catalog/recall blocks stay inside each profile budget (wrapper included)', async () => {
  const hugeCatalog = `## Memory catalog\n${'- mem_abc · a title · when to read\n'.repeat(400)}`
  for (const profileId of ['claude', 'openai', 'gemini', 'deepseek', 'qwen', 'kimi', 'glm', 'llama', 'generic', 'gpt-6.1', 'claude-opus-5-5', 'claude-sonnet-5-5', 'deepseek-flash', 'gpt-6.1-terra', 'gpt-6-astra', 'claude-fable-5-1', 'claude-haiku-5-5']) {
    const profile = profiles.resolveModelProfile(profileId)
    const catalog = manual.buildCatalogInjection(profile, hugeCatalog)
    const recall = manual.buildRecallInjection(profile, Array.from({ length: 40 }, (_, i) => ({ id: `mem_${i}`, title: 'title '.repeat(10), useWhen: 'when '.repeat(10) })))
    assert.ok(profiles.profileTokens(catalog, profile) <= profile.catalogTokens, `${profileId} catalog ${profiles.profileTokens(catalog, profile)} > ${profile.catalogTokens}`)
    assert.ok(profiles.profileTokens(recall, profile) <= profile.recallTokens, `${profileId} recall ${profiles.profileTokens(recall, profile)} > ${profile.recallTokens}`)
  }
  const pkg = JSON.parse(readFileSync(new URL('../packages/memex-mcp/package.json', import.meta.url), 'utf8'))
  const replies = mcpExchange(makeRoot('u12'), ['--agent', 'test', '--model', 'claude-sonnet-4'], [{ jsonrpc: '2.0', id: 1, method: 'initialize', params: {} }])
  assert.equal(replies.get(1).result.serverInfo.version, pkg.version, 'MCP server version must follow its package.json')
})


await test('U13', 'body-term rescue recovers facts that live only in hot bodies', async () => {
  const { LocalStoreCore } = await import('../packages/memex-core/lib/store.js')
  const root = makeRoot('u13')
  const store = new LocalStoreCore({ root, capacityTokens: 1_000_000_000, sessionCapacityTokens: 100_000_000, defaultLevels: { l2: false, l3: false } })
  try {
    for (let index = 0; index < 120; index += 1) {
      store.write({ kind: 'episode', title: `deployment retry budget incident INC-${index} report`, summary: `deployment retry budget incident INC-${index} review`, useWhen: 'read when continuing deployment retry budget work', body: 'generic retrospective notes with no answer token', workspaceKey: 'wk-u13', scope: 'workspace', tokens: 30 })
    }
    const answers = []
    for (let index = 0; index < 120; index += 1) {
      answers.push(store.write({ kind: 'fact', title: `turn ${index} note`, body: `The retry budget for incident INC-${index} is ANSWER-${index}-zq. Deployment retry budget context follows.`, workspaceKey: 'wk-u13', scope: 'workspace', tokens: 30 }))
    }
    let hit1 = 0
    let hit5 = 0
    for (let index = 0; index < 30; index += 1) {
      const hits = store.search({ query: `incident INC-${index} deployment retry budget answer token`, workspaceKey: 'wk-u13', scope: 'workspace', limit: 5 }).hits
      const rank = hits.findIndex((card) => card.id === answers[index].id)
      if (rank === 0) hit1 += 1
      if (rank >= 0) hit5 += 1
    }
    assert.ok(hit5 / 30 >= 0.9, `body rescue must recover hot-body facts (hit@5 ${hit5}/30)`)
    assert.ok(hit1 / 30 >= 0.8, `body rescue must rank them first (hit@1 ${hit1}/30)`)
    // IDs must not be treated as prefixes: INC-1 must not match INC-161.
    const prefixHits = store.search({ query: 'incident INC-1 deployment retry budget answer', workspaceKey: 'wk-u13', scope: 'workspace', limit: 5 }).hits
    assert.equal(prefixHits[0].id, answers[1].id, 'identifier matching must be boundary-aware')
  } finally {
    store.close()
    rmSync(root, { recursive: true, force: true })
  }
})


await test('U14', 'MCP parity tools: list, set-status and forget operate on the shared store', async () => {
  const root = makeRoot('u14')
  const write = mcpExchange(root, ['--agent', 'test', '--model', 'claude-sonnet-4', '--levels', 'l3'], [
    { jsonrpc: '2.0', id: 1, method: 'tools/call', params: { name: 'memory_write', arguments: { kind: 'fact', title: 'Parity record', body: 'parity body content', useWhen: 'read when testing parity tools' } } },
  ])
  const recordId = write.get(1).result.content[0].text.match(/mem_[0-9a-f]{10}/)[0]
  const replies = mcpExchange(root, ['--agent', 'test', '--model', 'claude-sonnet-4', '--levels', 'l3'], [
    { jsonrpc: '2.0', id: 1, method: 'tools/call', params: { name: 'memory_list', arguments: { limit: 10 } } },
    { jsonrpc: '2.0', id: 2, method: 'tools/call', params: { name: 'memory_set_status', arguments: { id: recordId, status: 'pinned' } } },
    { jsonrpc: '2.0', id: 3, method: 'tools/call', params: { name: 'memory_list', arguments: { status: 'pinned' } } },
    { jsonrpc: '2.0', id: 4, method: 'tools/call', params: { name: 'memory_forget', arguments: { id: recordId } } },
    { jsonrpc: '2.0', id: 5, method: 'tools/call', params: { name: 'memory_list', arguments: {} } },
  ])
  assertIncludes(replies.get(1).result.content[0].text, recordId)
  assertIncludes(replies.get(2).result.content[0].text, 'pinned')
  assertIncludes(replies.get(3).result.content[0].text, recordId)
  assertIncludes(replies.get(4).result.content[0].text, 'Deleted')
  assertIncludes(replies.get(5).result.content[0].text, 'No memory records')
})


await test('U16', 'dedicated GPT-6.1 / Opus 5.5 / Sonnet 5.5 / DeepSeek Flash profiles win over family bases', async () => {
  assert.equal(profiles.MODEL_VARIANTS.length, 8)
  const cases = [
    ['gpt-6.1-sol', 'gpt-6.1', 1_050_000, 4.0],
    ['gpt-6.1', 'gpt-6.1', 1_050_000, 4.0],
    ['claude-opus-5-5', 'claude-opus-5-5', 1_000_000, 2.6],
    ['claude-opus-5.5', 'claude-opus-5-5', 1_000_000, 2.6],
    ['claude-sonnet-5-5', 'claude-sonnet-5-5', 1_000_000, 2.6],
    ['claude-sonnet-5.5', 'claude-sonnet-5-5', 1_000_000, 2.6],
    ['deepseek-flash', 'deepseek-flash', 1_048_576, 3.0],
    ['deepseek-v4-flash', 'deepseek-flash', 1_048_576, 3.0],
    ['gpt-6.1-terra', 'gpt-6.1-terra', 1_050_000, 4.0],
    ['gpt-6-astra', 'gpt-6-astra', 1_050_000, 4.0],
    ['gpt-6.1-astra', 'gpt-6-astra', 1_050_000, 4.0],
    ['claude-fable-5-1', 'claude-fable-5-1', 1_000_000, 2.6],
    ['claude-haiku-5-5', 'claude-haiku-5-5', 1_000_000, 2.6],
  ]
  for (const [modelId, expectedId, window, ratio] of cases) {
    const profile = profiles.resolveModelProfile(modelId)
    assert.equal(profile.id, expectedId, `${modelId} must resolve to the dedicated profile`)
    assert.equal(profile.windowTokens, window, `${modelId} window`)
    assert.equal(profile.charsPerToken, ratio, `${modelId} tokenizer estimate`)
    assert.equal(typeof profile.manualStyle, 'string')
    assert.ok(profile.catalogTokens >= 800 && profile.recallTokens >= 300, `${modelId} budgets`)
  }
  // Variants must not swallow older family ids.
  assert.equal(profiles.resolveModelProfile('gpt-5-codex').id, 'openai')
  assert.equal(profiles.resolveModelProfile('claude-opus-4-1').id, 'claude')
  assert.equal(profiles.resolveModelProfile('deepseek-reasoner').id, 'deepseek')
  // Model-specific tuning is real: dedicated manual + digest prompt + budgets.
  const opus = profiles.resolveModelProfile('claude-opus-5-5')
  assert.equal(opus.injectionStyle, 'xml')
  assert.equal(opus.digestStyle, 'bullet-ids')
  assert.equal(opus.rerank.title, 3.4)
  assert.ok(manual.buildMemoryManual(opus, { agent: 'Claude Code' }).includes('Opus 5.5'))
  const flash = profiles.resolveModelProfile('deepseek-flash')
  assert.equal(flash.digestStyle, 'bilingual')
  assert.ok(manual.buildMemoryManual(flash, { agent: 'MCP' }).includes('DeepSeek Flash'))
  assert.ok(profiles.digestPrompt(flash, { ids: ['a'], text: 'x' }).system.includes('ids:'))
  // Specific variant matches must win over the broader GPT-6.1 family variant.
  assert.equal(profiles.resolveModelProfile('gpt-6.1-terra').id, 'gpt-6.1-terra')
  assert.equal(profiles.resolveModelProfile('gpt-6-astra').id, 'gpt-6-astra')
  assert.equal(profiles.resolveModelProfile('claude-fable-5-1').id, 'claude-fable-5-1')
  assert.equal(profiles.resolveModelProfile('claude-haiku-5-5').id, 'claude-haiku-5-5')
  assert.equal(profiles.resolveModelProfile('claude-haiku-5-5').catalogTokens, 900)
  assert.equal(profiles.resolveModelProfile('gpt-6-astra').catalogTokens, 2200)
  // Overrides still win, including on a dedicated variant.
  assert.equal(profiles.resolveModelProfile('gpt-6.1-sol', { windowTokens: 500_000 }).windowTokens, 500_000)
})


await test('U17', 'adapter CLIs default to recommended dedicated profiles and advertise them', async () => {
  const project = makeRoot('u17-claude')
  const root = makeRoot('u17-mem')
  const init = runNode(CLAUDE_CLI, ['init', '--project', project, '--root', root])
  assert.equal(init.status, 0, init.stderr)
  const mcp = JSON.parse(readFileSync(join(project, '.mcp.json'), 'utf8'))
  const args = mcp.mcpServers['memex'].args
  const modelIndex = args.indexOf('--model')
  assert.equal(args[modelIndex + 1], 'claude-sonnet-5-5', 'Claude init default model must be claude-sonnet-5-5')
  assertIncludes(init.stdout, 'claude-sonnet-5-5')
  assertIncludes(init.stdout, 'claude-opus-5-5')
  assertIncludes(init.stdout, 'Model profile: claude-sonnet-5-5')
  const help = runNode(CLAUDE_CLI, ['help'])
  assertIncludes(help.stdout, 'claude-fable-5-1')
  assertIncludes(help.stdout, 'claude-haiku-5-5')

  const project2 = makeRoot('u17-codex')
  const root2 = makeRoot('u17-mem2')
  const codex = runNode(CODEX_CLI, ['init', '--project', project2, '--root', root2])
  assert.equal(codex.status, 0, codex.stderr)
  assertIncludes(codex.stdout, '"gpt-6.1-sol"')
  assertIncludes(codex.stdout, 'gpt-6.1-terra')
  assertIncludes(codex.stdout, 'gpt-6-astra')
  assertIncludes(codex.stdout, 'Model profile: gpt-6.1')
  const codexHelp = runNode(CODEX_CLI, ['help'])
  assertIncludes(codexHelp.stdout, 'gpt-6-astra')

  const mcpList = runNode(MCP_SERVER, ['--list-profiles'])
  assert.equal(mcpList.status, 0)
  const listing = `${mcpList.stdout}${mcpList.stderr}`
  for (const profileId of ['deepseek-flash', 'claude-sonnet-5-5', 'gpt-6.1-sol']) assertIncludes(listing, profileId)
})

// ── summary ──────────────────────────────────────────────────────────────────

cleanupTempDirs()

const failed = results.filter((result) => result.ok === false)
if (failed.length > 0) {
  console.error(`\n${failed.length} failing test(s):`)
  for (const { id, title, error } of failed) {
    console.error(`\n--- FAIL ${id} ${title}\n${error?.stack ?? String(error)}`)
  }
  console.log(`\n# ${results.length - failed.length}/${results.length} passed, ${failed.length} failed`)
  process.exitCode = 1
} else {
  const skipped = results.filter((result) => result.skipped === true).length
  console.log(`\n# ${results.length}/${results.length} passed${skipped > 0 ? ` (${skipped} skipped: bundle not built)` : ''}`)
}
