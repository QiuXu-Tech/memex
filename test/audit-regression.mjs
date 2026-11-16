import assert from 'node:assert/strict'
import { test } from 'node:test'
import fs from 'node:fs'
import { tmpdir } from 'node:os'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'
import { spawn, spawnSync } from 'node:child_process'
import { once } from 'node:events'
import { syncBuiltinESMExports } from 'node:module'
import { createHash } from 'node:crypto'
import { LocalStoreCore } from '../packages/memex-core/lib/store.js'
import { AgentMemory } from '../packages/memex-core/lib/engine.js'
import { canonicalEventsFromDsh } from '../packages/memex-core/lib/context-events.js'
import { materializeContext } from '../packages/memex-core/lib/context-materializer.js'
import { materializeStoreContext } from '../packages/memex-core/lib/context-pager.js'
import { materializeWithHost } from '../packages/memex-core/lib/context-kv.js'
import { PagedKvContextHost } from '../packages/memex-core/lib/context-kv-host.js'
import { DEFAULT_RERANK_WEIGHTS } from '../packages/memex-core/index.js'

const repo = resolve(dirname(fileURLToPath(import.meta.url)), '..')
function fixture(t) {
  const root = fs.mkdtempSync(join(tmpdir(), 'memex-audit-regression-'))
  const store = new LocalStoreCore({ root: join(root, 'store') })
  t.after(() => { store.close(); fs.rmSync(root, { recursive: true, force: true }) })
  return { root, store }
}
const record = (id, extra = {}) => ({ id, workspaceKey: 'audit', scope: 'workspace', kind: 'fact', title: 'ordinary words', body: 'ordinary natural words', ...extra })
function cli(args, options = {}) {
  return spawnSync(process.execPath, [join(repo, 'scripts/memory-backup.mjs'), ...args], { encoding: 'utf8', timeout: 10000, ...options })
}

test('F14: an empty manifest is not a restorable backup', t => {
  const { root } = fixture(t)
  fs.writeFileSync(join(root, 'manifest.json'), JSON.stringify({ format: 1, files: [], createdAt: 'synthetic' }))
  assert.notEqual(cli(['verify', '--dir', root]).status, 0)
})

test('F15: failed copy preserves the old restore target', t => {
  const { root, store } = fixture(t)
  store.write(record('saved')); store.close()
  const backup = join(root, 'backup'), target = join(root, 'target')
  assert.equal(cli(['backup', '--root', store.root, '--out', backup]).status, 0)
  fs.mkdirSync(target); fs.writeFileSync(join(target, 'keep'), 'old-state')
  const hook = join(root, 'copy-failure.mjs')
  fs.writeFileSync(hook, "import fs from 'node:fs';import{syncBuiltinESMExports}from'node:module';fs.cpSync=()=>{throw new Error('COPY_FAILURE')};syncBuiltinESMExports()")
  const result = spawnSync(process.execPath, ['--import', hook, join(repo, 'scripts/memory-backup.mjs'), 'restore', '--dir', backup, '--to', target, '--force'], { encoding: 'utf8', timeout: 10000 })
  assert.notEqual(result.status, 0)
  assert.match(result.stderr, /COPY_FAILURE/)
  assert.equal(fs.readFileSync(join(target, 'keep'), 'utf8'), 'old-state')
})

test('F14/F15: valid backup restores records and retains the previous target', t => {
  const { root, store } = fixture(t)
  store.write(record('saved', { body: 'keep full body' })); store.close()
  const backup = join(root, 'backup'), target = join(root, 'target')
  assert.equal(cli(['backup', '--root', store.root, '--out', backup]).status, 0)
  assert.equal(cli(['verify', '--dir', backup]).status, 0)
  fs.mkdirSync(target); fs.writeFileSync(join(target, 'keep'), 'old-state')
  const result = cli(['restore', '--dir', backup, '--to', target, '--force'])
  assert.equal(result.status, 0, result.stderr)
  const restored = new LocalStoreCore({ root: target })
  try { assert.equal(restored.get('saved').body, 'keep full body') } finally { restored.close() }
  const previous = fs.readdirSync(root).find(name => name.startsWith('target.previous-'))
  assert.ok(previous, 'keep a recoverable previous target')
  assert.equal(fs.readFileSync(join(root, previous, 'keep'), 'utf8'), 'old-state')
})

test('F14/F15: reject physically overlapping paths without changing a valid backup', t => {
  const { root, store } = fixture(t)
  store.write(record('saved')); store.close()
  const backup = join(root, 'backup'), alias = join(root, 'backup-alias')
  assert.equal(cli(['backup', '--root', store.root, '--out', backup]).status, 0)
  fs.symlinkSync(backup, alias, 'dir')
  const before = fs.readdirSync(backup, { recursive: true }).sort()
  const manifest = fs.readFileSync(join(backup, 'manifest.json'), 'utf8')
  for (const destination of [join(backup, 'nested'), join(alias, 'nested')]) {
    assert.notEqual(cli(['restore', '--dir', backup, '--to', destination, '--force']).status, 0)
    assert.deepEqual(fs.readdirSync(backup, { recursive: true }).sort(), before)
    assert.equal(fs.readFileSync(join(backup, 'manifest.json'), 'utf8'), manifest)
    assert.equal(cli(['verify', '--dir', backup]).status, 0)
  }
  const nested = join(fs.realpathSync(store.root), 'nested-backup')
  assert.notEqual(cli(['backup', '--root', store.root, '--out', nested]).status, 0)
  assert.equal(fs.existsSync(nested), false)
})

test('F14: backup rejects ancestor output and unsupported manifest files before claiming restorability', t => {
  const { root, store } = fixture(t)
  store.write(record('saved')); store.close()
  const alias = join(root, 'parent-alias'); fs.symlinkSync(root, alias, 'dir')
  const before = fs.readdirSync(root, { recursive: true }).sort()
  for (const out of [root, alias]) {
    assert.notEqual(cli(['backup', '--root', store.root, '--out', out]).status, 0)
    assert.deepEqual(fs.readdirSync(root, { recursive: true }).sort(), before)
  }
  const backup = join(root, 'valid-backup')
  assert.equal(cli(['backup', '--root', store.root, '--out', backup]).status, 0)
  const file = join(backup, 'unexpected.txt'); fs.writeFileSync(file, 'untracked output')
  const path = join(backup, 'manifest.json'), manifest = JSON.parse(fs.readFileSync(path, 'utf8'))
  manifest.files.push({ path: 'unexpected.txt', sha256: createHash('sha256').update(fs.readFileSync(file)).digest('hex') })
  fs.writeFileSync(path, JSON.stringify(manifest))
  assert.notEqual(cli(['verify', '--dir', backup]).status, 0)
  const occupied = join(root, 'occupied-output'); fs.mkdirSync(occupied); fs.writeFileSync(join(occupied, 'keep'), 'old output')
  assert.notEqual(cli(['backup', '--root', store.root, '--out', occupied]).status, 0)
  assert.deepEqual(fs.readdirSync(occupied), ['keep'])
})

for (const phase of ['before-exchange', 'after-previous', 'after-install']) {
  test(`F15: process interruption ${phase} leaves a recoverable complete state`, t => {
    const { root, store } = fixture(t)
    store.write(record('saved', { body: 'new state' })); store.close()
    const backup = join(root, 'backup'), target = join(root, 'target')
    assert.equal(cli(['backup', '--root', store.root, '--out', backup]).status, 0)
    fs.mkdirSync(target); fs.writeFileSync(join(target, 'keep'), 'old-state')
    const physicalTarget = fs.realpathSync(target)
    const hook = join(root, 'interrupt.mjs')
    fs.writeFileSync(hook, `import fs from 'node:fs';import{syncBuiltinESMExports}from'node:module';const rename=fs.renameSync;fs.renameSync=(a,b)=>{if(${JSON.stringify(phase)}==='before-exchange'&&a===${JSON.stringify(physicalTarget)})process.exit(92);const result=rename(a,b);if((${JSON.stringify(phase)}==='after-previous'&&a===${JSON.stringify(physicalTarget)})||(${JSON.stringify(phase)}==='after-install'&&b===${JSON.stringify(physicalTarget)}))process.exit(92);return result};syncBuiltinESMExports()`)
    const result = spawnSync(process.execPath, ['--import', hook, join(repo, 'scripts/memory-backup.mjs'), 'restore', '--dir', backup, '--to', target, '--force'], { encoding: 'utf8', timeout: 10000 })
    assert.equal(result.status, 92)
    const guarded = new LocalStoreCore({ root: target })
    assert.throws(() => guarded.ensure(), /restore in progress/)
    const recovered = cli(['recover', '--to', target])
    assert.equal(recovered.status, 0, recovered.stderr)
    if (phase === 'after-install') {
      const reopened = new LocalStoreCore({ root: target })
      try { assert.equal(reopened.get('saved').body, 'new state') } finally { reopened.close() }
    } else assert.equal(fs.readFileSync(join(target, 'keep'), 'utf8'), 'old-state')
  })
}

test('F15: restore refuses any already-open Store, including an idle handle', t => {
  const { root, store } = fixture(t)
  store.write(record('saved')); store.close()
  const backup = join(root, 'backup'), target = join(root, 'target')
  assert.equal(cli(['backup', '--root', store.root, '--out', backup]).status, 0)
  const old = new LocalStoreCore({ root: target })
  old.write(record('old')); t.after(() => old.close())
  const result = cli(['restore', '--dir', backup, '--to', target, '--force'])
  assert.notEqual(result.status, 0)
  assert.equal(old.get('old').id, 'old')
  old.close()
  const retried = cli(['restore', '--dir', backup, '--to', target, '--force'])
  assert.equal(retried.status, 0, retried.stderr)
})

test('F15: a Store paused after guard validation excludes restore before BEGIN', async t => {
  const { root, store } = fixture(t)
  store.write(record('saved')); store.close()
  const backup = join(root, 'backup'), target = join(root, 'target'), release = join(root, 'release')
  assert.equal(cli(['backup', '--root', store.root, '--out', backup]).status, 0)
  const module = pathToFileURL(join(repo, 'packages/memex-core/lib/store.js')).href
  const code = `import{LocalStoreCore}from ${JSON.stringify(module)};import{DatabaseSync}from'node:sqlite';import{existsSync}from'node:fs';const s=new LocalStoreCore({root:${JSON.stringify(target)}});s.ensure();const exec=DatabaseSync.prototype.exec;let once=true;DatabaseSync.prototype.exec=function(sql){if(once&&sql==='BEGIN IMMEDIATE'){once=false;process.stdout.write('WAIT\\n');while(!existsSync(${JSON.stringify(release)}))Atomics.wait(new Int32Array(new SharedArrayBuffer(4)),0,0,10)}return exec.call(this,sql)};s.write({id:'paused',kind:'fact',title:'paused',body:'complete old state',workspaceKey:'audit'});s.close()`
  const child = spawn(process.execPath, ['--input-type=module', '-e', code], { stdio: ['ignore', 'pipe', 'pipe'] })
  const done = once(child, 'exit')
  await once(child.stdout, 'data')
  let result
  try { result = cli(['restore', '--dir', backup, '--to', target, '--force']) } finally { fs.writeFileSync(release, 'release') }
  assert.equal((await done)[0], 0)
  assert.notEqual(result.status, 0)
  const after = new LocalStoreCore({ root: target })
  try { assert.equal(after.get('paused').body, 'complete old state') } finally { after.close() }
})

test('F15: a Store waiting for a lease rechecks an interrupted restore guard', async t => {
  const { root } = fixture(t), target = join(root, 'waiting-target')
  const leaseModule = pathToFileURL(join(repo, 'packages/memex-core/lib/store-lease.js')).href
  const code = `import{acquireStoreLease}from ${JSON.stringify(leaseModule)};import{writeFileSync}from'node:fs';const release=acquireStoreLease(${JSON.stringify(target)},{exclusive:true});process.stdout.write('LOCKED\\n');setTimeout(()=>{writeFileSync(${JSON.stringify(target + '.restore-lock')},'{}');release()},200)`
  const child = spawn(process.execPath, ['--input-type=module', '-e', code], { stdio: ['ignore', 'pipe', 'pipe'] })
  const done = once(child, 'exit')
  await once(child.stdout, 'data')
  const waiting = new LocalStoreCore({ root: target })
  try { assert.throws(() => waiting.ensure(), /restore in progress/) } finally { waiting.close() }
  assert.equal((await done)[0], 0)
})

test('F15: physical root aliases share restore exclusion and interrupted guards', async t => {
  const { root, store } = fixture(t)
  store.write(record('saved')); store.close()
  const backup = join(root, 'backup'), target = join(root, 'target'), alias = join(root, 'alias'), parentAlias = join(root, 'parent-alias')
  assert.equal(cli(['backup', '--root', store.root, '--out', backup]).status, 0)
  fs.mkdirSync(target); fs.symlinkSync(target, alias, 'dir'); fs.symlinkSync(root, parentAlias, 'dir')
  const byAlias = new LocalStoreCore({ root: alias })
  byAlias.write(record('old'))
  try { assert.notEqual(cli(['restore', '--dir', backup, '--to', target, '--force']).status, 0) } finally { byAlias.close() }
  const normal = new LocalStoreCore({ root: target }); normal.ensure()
  try { assert.notEqual(cli(['restore', '--dir', backup, '--to', join(parentAlias, 'target'), '--force']).status, 0) } finally { normal.close() }
  fs.writeFileSync(target + '.restore-lock', '{}')
  const blocked = new LocalStoreCore({ root: alias })
  try { assert.throws(() => blocked.ensure(), /restore in progress/) } finally { blocked.close() }
  fs.unlinkSync(target + '.restore-lock')
  const hook = join(root, 'alias-interrupt.mjs')
  fs.writeFileSync(hook, "import fs from 'node:fs';import{syncBuiltinESMExports}from'node:module';const rename=fs.renameSync;fs.renameSync=(a,b)=>{const result=rename(a,b);if(String(b).includes('.previous-'))process.exit(92);return result};syncBuiltinESMExports()")
  const interrupted = spawnSync(process.execPath, ['--import', hook, join(repo, 'scripts/memory-backup.mjs'), 'restore', '--dir', backup, '--to', join(parentAlias, 'target'), '--force'], { encoding: 'utf8', timeout: 10000 })
  assert.equal(interrupted.status, 92, interrupted.stderr)
  const absent = new LocalStoreCore({ root: target })
  try { assert.throws(() => absent.ensure(), /restore in progress/) } finally { absent.close() }
  const danglingAlias = new LocalStoreCore({ root: alias })
  try { assert.throws(() => danglingAlias.ensure(), /restore in progress/) } finally { danglingAlias.close() }
  const recovered = cli(['recover', '--to', alias])
  assert.equal(recovered.status, 0, recovered.stderr)
  const reopened = new LocalStoreCore({ root: alias })
  try { assert.equal(reopened.get('old').id, 'old') } finally { reopened.close() }
})

test('F15: incomplete guards are recoverable only without an active restore lease', async t => {
  const { root } = fixture(t), target = join(root, 'target')
  fs.mkdirSync(target); fs.writeFileSync(join(target, 'keep'), 'untouched')
  fs.writeFileSync(target + '.restore-lock', '')
  const { acquireStoreLease } = await import('../packages/memex-core/lib/store-lease.js')
  const release = acquireStoreLease(target, { exclusive: true, timeoutMs: 0 })
  try {
    assert.notEqual(cli(['recover', '--to', target]).status, 0)
    assert.ok(fs.existsSync(target + '.restore-lock'))
  } finally { release() }
  assert.equal(cli(['recover', '--to', target]).status, 0)
  assert.equal(fs.readFileSync(join(target, 'keep'), 'utf8'), 'untouched')
  fs.writeFileSync(target + '.restore-lock', '{"truncated":')
  assert.equal(cli(['recover', '--to', target]).status, 0)
})

test('F15: incomplete-guard recovery accepts legacy alias paths but rejects missing and escaping bodies', t => {
  const { root } = fixture(t), target = join(root, 'alias-target'), alias = join(root, 'legacy-alias')
  fs.mkdirSync(target); fs.symlinkSync(target, alias, 'dir')
  const old = new LocalStoreCore({ root: alias })
  const saved = old.write(record('alias-record')); old.close()
  const guard = target + '.restore-lock'
  fs.writeFileSync(guard, '')
  assert.equal(cli(['recover', '--to', alias]).status, 0)
  fs.renameSync(saved.path, saved.path + '.saved')
  fs.writeFileSync(guard, '')
  assert.notEqual(cli(['recover', '--to', target]).status, 0)
  assert.ok(fs.existsSync(guard))
  const outside = join(root, 'outside.md'); fs.writeFileSync(outside, 'unrelated body')
  fs.symlinkSync(outside, saved.path)
  assert.notEqual(cli(['recover', '--to', alias]).status, 0)
  assert.ok(fs.existsSync(guard))
  assert.equal(fs.readFileSync(outside, 'utf8'), 'unrelated body')
  fs.unlinkSync(saved.path); fs.renameSync(saved.path + '.saved', saved.path)
  assert.equal(cli(['recover', '--to', target]).status, 0)
  const absent = join(root, 'absent-target'); fs.writeFileSync(absent + '.restore-lock', '')
  assert.notEqual(cli(['recover', '--to', absent]).status, 0)
  assert.ok(fs.existsSync(absent + '.restore-lock'))
})

test('F15: incomplete-guard recovery retains archive files without their matching database', t => {
  const { root } = fixture(t), target = join(root, 'missing-index')
  const old = new LocalStoreCore({ root: target }), saved = old.write(record('keep-archive'))
  old.close(); fs.unlinkSync(join(target, 'index.db'))
  fs.writeFileSync(target + '.restore-lock', '')
  const before = fs.readFileSync(saved.path, 'utf8')
  assert.notEqual(cli(['recover', '--to', target]).status, 0)
  assert.ok(fs.existsSync(target + '.restore-lock'))
  assert.equal(fs.readFileSync(saved.path, 'utf8'), before)
  assert.equal(fs.existsSync(join(target, 'index.db')), false)
})

test('F07: enabling one level cannot undo an interleaved level enable', t => {
  const { store } = fixture(t), other = new LocalStoreCore({ root: store.root })
  t.after(() => other.close())
  store.ensure(); other.ensure()
  const get = store.getLevels.bind(store)
  let once = true
  store.getLevels = id => { const levels = get(id); if (once) { once = false; other.enableLevel(id, 'l3') }; return levels }
  store.enableLevel('session', 'l2')
  assert.deepEqual(other.getLevels('session'), { l2: true, l3: true })
})

test('F07: multiple processes retain both enabled levels', async t => {
  const { store } = fixture(t)
  store.ensure()
  const module = pathToFileURL(join(repo, 'packages/memex-core/lib/store.js')).href
  const children = Array.from({ length: 6 }, (_, i) => {
    const code = `import{LocalStoreCore}from ${JSON.stringify(module)};const s=new LocalStoreCore({root:${JSON.stringify(store.root)}});s.enableLevel('shared',${JSON.stringify(i % 2 ? 'l2' : 'l3')});s.close()`
    return spawn(process.execPath, ['--input-type=module', '-e', code], { stdio: ['ignore', 'ignore', 'pipe'] })
  })
  const exits = await Promise.all(children.map(child => once(child, 'exit')))
  assert.ok(exits.every(([code]) => code === 0))
  assert.deepEqual(store.getLevels('shared'), { l2: true, l3: true })
})

test('F08: default event IDs do not move events between records', t => {
  const { store } = fixture(t)
  for (const id of ['a', 'b']) store.write(record(id))
  store.appendContextEvents({ recordId: 'a', events: [{ sequence: 1, content: 'first' }] })
  store.appendContextEvents({ recordId: 'b', events: [{ sequence: 1, content: 'second' }] })
  assert.equal(store.listContextEvents('a')[0]?.content, 'first')
  assert.equal(store.listContextEvents('b')[0]?.content, 'second')
  store.appendContextEvents({ recordId: 'a', events: [{ id: 'explicit', sequence: 2, content: 'owned' }] })
  assert.throws(() => store.appendContextEvents({ recordId: 'b', events: [{ id: 'explicit', sequence: 2, content: 'stolen' }] }), /owner|belong/)
  assert.equal(store.listContextEvents('a').find(x => x.id === 'explicit').content, 'owned')
})

test('F03: canonical blocks retain numeric source order after reopening', t => {
  const { store } = fixture(t)
  store.write(record('blocks'))
  const expected = Array.from({ length: 100 }, (_, i) => `block-${i}`)
  store.appendContextEvents({ recordId: 'blocks', events: canonicalEventsFromDsh([{ seq: 1, time: 100, type: 'user/message', data: { role: 'user', content: expected.map(text => ({ type: 'text', text })) } }], { recordId: 'blocks', sessionId: 's' }) })
  store.close()
  assert.deepEqual(store.listContextEvents('blocks').map(x => x.content), expected)
})

test('F03: legacy event checksums remain readable after the schema upgrade', t => {
  const { store } = fixture(t)
  store.write(record('legacy'))
  const event = { id: 'legacy:1:10', role: 'assistant', type: 'message', sequence: 1, sessionId: 's', recordId: 'legacy', content: 'preserved', contentFormat: 'text', attachments: [], createdAt: 100 }
  const checksum = createHash('sha256').update(JSON.stringify(event)).digest('hex')
  store.database().prepare('INSERT INTO context_events (event_id,record_id,session_id,sequence,role,type,content,content_format,attachments_json,checksum,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)').run(event.id, 'legacy', 's', 1, event.role, event.type, event.content, event.contentFormat, '[]', checksum, 100)
  store.close()
  assert.equal(store.listContextEvents('legacy')[0].content, 'preserved')
})

test('F03: source sequence survives clock skew and tool dependencies are selected together', () => {
  const pages = [{ id: 'call', sessionId: 's', sequence: 1, createdAt: 2000, type: 'tool_call', toolCallId: 'c', body: 'call '.repeat(100) }, { id: 'result', sessionId: 's', sequence: 2, createdAt: 1000, type: 'tool_result', toolCallId: 'c', body: 'result' }]
  const all = materializeContext({ pages, budgetTokens: 1000 })
  assert.deepEqual(all.order, ['call', 'result'])
  assert.equal(all.orderingUncertain, true)
  assert.deepEqual(materializeContext({ pages, budgetTokens: 60, enforceTotalBudget: true }).includedIds, [])
  const orphan = materializeContext({ pages: [pages[1]], budgetTokens: 1000 })
  assert.equal(orphan.omittedReasons.result, 'missing-tool-call')
  assert.equal(materializeContext({ pages: [pages[0]], budgetTokens: 1000 }).omittedReasons.call, 'missing-tool-result')
})

test('F02/F03: hard budgets include forced-page formatting and use chronological units', () => {
  const pages = [{ id: 'old', sequence: 1000, createdAt: 1000, body: 'old' }, { id: 'new', sequence: 1, createdAt: 2000, body: 'new' }]
  assert.deepEqual(materializeContext({ pages, budgetTokens: 1000 }).order, ['old', 'new'])
  for (const budgetTokens of [0, 1, 100]) {
    const result = materializeContext({ pages: [{ id: 'forced', body: '汉😀'.repeat(2000) }], budgetTokens, pinnedIds: ['forced'], enforceTotalBudget: true, tokenCounter: text => Array.from(text).length })
    assert.ok(result.tokens <= budgetTokens)
    assert.ok(result.omittedIds.includes('forced'))
  }
  assert.throws(() => materializeContext({ budgetTokens: NaN }), /budget/)
})

test('F04: required old records enter the candidate set and canonical IDs map to pages', t => {
  const { store } = fixture(t)
  store.write(record('old', { createdAt: 1 }))
  for (let i = 0; i < 45; i++) store.write(record(`new-${i}`, { createdAt: 100 + i }))
  const args = { store, workspaceKey: 'audit', scopes: ['workspace'], sessionId: 's', alwaysIncludeIds: ['old'], budgetTokens: 50000 }
  assert.ok(materializeStoreContext(args).includedIds.includes('old'))
  store.appendContextEvents({ recordId: 'old', events: [{ id: 'event', sequence: 1, content: 'canonical' }] })
  assert.ok(materializeStoreContext(args).forcedIds.includes('old:event'))
  store.setStatus('old', 'superseded')
  assert.ok(!materializeStoreContext(args).includedIds.includes('old:event'))
})

test('F05: reference KV host keeps materialized content and misses incomplete prefixes', () => {
  const host = new PagedKvContextHost()
  materializeWithHost({ text: 'data' }, host, { prefixKey: 'fixture', spans: [{ id: 's', text: 'ACTUAL-CONTENT' }] })
  assert.equal(host.blocks.get('fixture:block:0')?.text, 'ACTUAL-CONTENT')
  assert.equal(materializeWithHost({ text: 'data' }, { capabilities: ['paged-kv', 'token-spans'] }).mode, 'text-fallback')
})

test('F06: grep line coordinates can be passed directly to open', t => {
  const { root } = fixture(t), engine = new AgentMemory({ root: join(root, 'engine'), levels: ['l3'], cwd: root })
  t.after(() => engine.close())
  const r = engine.write({ kind: 'fact', title: 'lines', body: 'first\nTARGET_MARKER\nlast' })
  const hit = engine.grep({ pattern: 'TARGET_MARKER', id: r.id })[0]
  assert.equal(hit.line, 2)
  assert.equal(engine.open({ id: r.id, offset: hit.line, limit: 1 }).body, 'TARGET_MARKER')
})

test('F10: legitimate empty term postings are not rebuilt on every open', t => {
  const { store } = fixture(t)
  const r = store.write(record('natural')); store.close()
  const read = fs.readFileSync
  let reads = 0
  fs.readFileSync = function (p, ...args) { if (String(p) === r.path) reads++; return read(p, ...args) }
  syncBuiltinESMExports()
  try { store.ensure(); store.close(); store.ensure(); assert.equal(reads, 0) } finally { fs.readFileSync = read; syncBuiltinESMExports() }
})

test('F11: a stale enrichment patch cannot overwrite or resurrect a record', t => {
  const { store } = fixture(t)
  const original = store.write(record('patch'))
  store.setStatus('patch', 'superseded')
  assert.equal(store.patchCard('patch', { title: 'late' }, { expectedRevision: original.revision }).status, 'conflict')
  assert.equal(store.get('patch').status, 'superseded')
  store.forget('patch')
  assert.equal(store.patchCard('patch', { title: 'late' }, { expectedRevision: original.revision }).status, 'missing')
  assert.equal(store.get('patch'), undefined)
  store.write(record('patch', { body: 'new incarnation' }))
  assert.equal(store.patchCard('patch', { title: 'late' }, { expectedRevision: original.revision }).status, 'conflict')
  assert.equal(store.get('patch').body, 'new incarnation')
})

test('F16: real search preserves the ordering of different negative BM25 scores', t => {
  const { store } = fixture(t)
  store.write(record('strong', { title: 'alpha alpha alpha alpha', body: 'ordinary' }))
  store.write(record('weak', { title: 'alpha beta gamma delta', body: 'ordinary' }))
  store.database().prepare('UPDATE records SET updated_at = ? WHERE id = ?').run(Date.now() + 1000, 'weak')
  const rerank = Object.fromEntries(Object.keys(DEFAULT_RERANK_WEIGHTS).map(key => [key, key === 'bm25' ? 1 : 0]))
  assert.equal(store.search({ workspaceKey: 'audit', query: 'alpha', rerank }).hits[0].id, 'strong')
})

test('F01: bootstrap enables a real no-loader MCP round trip', t => {
  const { root } = fixture(t)
  const linked = spawnSync('sh', [join(repo, 'scripts/link-workspace.sh')], { encoding: 'utf8', timeout: 10000 })
  assert.equal(linked.status, 0, linked.stderr)
  const messages = [
    { jsonrpc: '2.0', id: 1, method: 'initialize', params: {} },
    { jsonrpc: '2.0', id: 2, method: 'tools/list', params: {} },
    { jsonrpc: '2.0', id: 3, method: 'tools/call', params: { name: 'memory_write', arguments: { kind: 'fact', title: 'ROUNDTRIP_713', body: 'persisted evidence' } } },
    { jsonrpc: '2.0', id: 4, method: 'tools/call', params: { name: 'memory_search', arguments: { query: 'ROUNDTRIP_713' } } },
  ]
  const childEnv = { PATH: process.env.PATH, HOME: root, TMPDIR: root }
  const result = spawnSync(process.execPath, [join(repo, 'packages/memex-mcp/bin/server.mjs'), '--root', join(root, 'memory'), '--cwd', root, '--levels', 'l3'], { input: messages.map(x => JSON.stringify(x)).join('\n') + '\n', encoding: 'utf8', timeout: 10000, env: childEnv })
  assert.equal(result.status, 0, result.stderr)
  const replies = result.stdout.trim().split('\n').map(x => JSON.parse(x))
  assert.ok(replies.find(x => x.id === 2).result.tools.some(x => x.name === 'memory_write'))
  assert.match(JSON.stringify(replies.find(x => x.id === 4).result), /ROUNDTRIP_713/)
  const written = { id: replies.find(x => x.id === 3).result.content[0].text.match(/^Stored (\S+)/)?.[1] }
  assert.ok(written.id)
  const resumed = spawnSync(process.execPath, [join(repo, 'packages/memex-mcp/bin/server.mjs'), '--root', join(root, 'memory'), '--cwd', root, '--levels', 'l3'], { input: [
    { jsonrpc: '2.0', id: 5, method: 'tools/call', params: { name: 'memory_open', arguments: { id: written.id } } },
    { jsonrpc: '2.0', id: 6, method: 'tools/call', params: { name: 'memory_set_status', arguments: { id: written.id, status: 'superseded' } } },
  ].map(x => JSON.stringify(x)).join('\n') + '\n', encoding: 'utf8', timeout: 10000, env: childEnv })
  assert.equal(resumed.status, 0, resumed.stderr)
  assert.match(resumed.stdout, /persisted evidence/)
  assert.match(resumed.stdout, /superseded/)
  for (const pkg of ['memex-claude', 'memex-codex']) {
    const run = spawnSync(process.execPath, [join(repo, 'packages', pkg, 'bin/cli.mjs'), pkg === 'memex-claude' ? 'print-manual' : 'config', '--project', root, '--root', join(root, 'memory')], { encoding: 'utf8', timeout: 10000, env: childEnv })
    assert.equal(run.status, 0, run.stderr)
  }
})
