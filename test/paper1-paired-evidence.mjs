import test from 'node:test'
import assert from 'node:assert/strict'
import { createHash } from 'node:crypto'
import { mkdtempSync, readFileSync, writeFileSync, rmSync, existsSync } from 'node:fs'
import { join, resolve } from 'node:path'
import { tmpdir } from 'node:os'
import { spawn } from 'node:child_process'
import { createInterface } from 'node:readline'
import { PairedEvidence } from '../scripts/paper1/paired_evidence.mjs'

const sha = value => createHash('sha256').update(value).digest('hex')
const NOW = '2026-11-28T10:00:00.000Z'
const REQUEST = 'Review the public patch. Require unit tests for artifact v1 before recommending release.\n'
const LIMITS = { maxSourceOpens: 6, maxSourceBytes: 24000, maxSourceBytesPerOpen: 4000 }
const source = { type: 'test_result', scope: 'real-project', entity: 'pytest unit', version: 'v1',
  eventId: 'recorded-test', sourceId: 'public-runner', sourceSequence: 1, observedAt: NOW,
  role: 'tool', kind: 'command_execution', status: 'failed', complete: true, command: 'pytest unit',
  completed: true, executed: true, exitCode: 1, testCount: 2, text: '1 failed, 1 passed. α\n' }
const claim = { type: 'test_result', scope: 'real-project', entity: 'pytest unit', version: 'v1',
  basis: { field: 'request', quote: 'Require unit tests for artifact v1' }, uncertainty: [] }

function fixture({ sources = [source], claims = [claim], authorizeOpen } = {}) {
  const root = mkdtempSync(join(tmpdir(), 'p1-paired-evidence-'))
  const archive = { schema: 1, taskId: 'generic-project-task', snapshot: { cutoff: NOW, watermark: 'recorded-public-head', complete: true }, sources }
  const archivePath = join(root, 'source-archive.json'), requestPath = join(root, 'request.txt')
  const archiveBytes = JSON.stringify(archive, null, 2) + '\n'
  writeFileSync(archivePath, archiveBytes); writeFileSync(requestPath, REQUEST)
  const admissions = []
  const config = { schema_version: 1, archivePath, archiveSha256: sha(archiveBytes), requestPath,
    requestSha256: sha(REQUEST), taskId: archive.taskId, output: join(root, 'evidence'),
    publicInput: { draft: 'The patch needs a review.', context: 'Public scope real-project; suite pytest unit; artifact v1.',
      toolDescriptions: ['run_current_tests: Run the configured public test suite.'] } }
  const approve = authorizeOpen ?? (async intent => {
    admissions.push(structuredClone(intent))
    return { allowed: true, operation_id: intent.operation_id, receipt: { operation_id: intent.operation_id, persisted: true } }
  })
  let evidence
  return { root, config, admissions, raw: JSON.stringify({ claims, unresolved: [] }),
    start() { evidence = new PairedEvidence(config, { authorizeOpen: approve }); return evidence },
    close() { evidence?.close(); rmSync(root, { recursive: true, force: true }) } }
}

async function install(f, e) { e.prepare(); assert.equal((await e.install(f.raw)).ok, true) }

test('generic task preparation uses bound request and observable fields only', async () => {
  const f = fixture(), e = f.start()
  try {
    const p = e.prepare()
    assert.equal(p.input.request, REQUEST)
    assert.deepEqual(Object.keys(p.input).sort(), ['context', 'draft', 'request', 'toolDescriptions'])
    assert.equal(p.archive_sha256, f.config.archiveSha256)
    assert.equal(p.original_request_sha256, f.config.requestSha256)
    assert.equal(p.task_id, 'generic-project-task')
    assert.equal(p.prompt_sha256, sha(p.prompt))
    for (const hidden of ['recorded-test', 'public-runner', 'sourceSequence', '1 failed']) assert.equal(p.prompt.includes(hidden), false)
    assert.equal((await e.install(f.raw)).ok, true)
    assert.throws(() => e.prepare(), /preparation_consumed/)
    await assert.rejects(e.install(f.raw), /preparation_consumed/)
  } finally { f.close() }
})

test('same live archive epoch supplies prime originals, C reopens, and D reuses exact prime receipt', async () => {
  const f = fixture(), e = f.start()
  try {
    let actualPages = 0
    const open = e.archive.engine.openEvent.bind(e.archive.engine)
    e.archive.engine.openEvent = (...args) => { actualPages++; return open(...args) }
    await install(f, e)
    const prime = await e.prime({ limits: LIMITS })
    const always = await e.verify({ mode: 'always', unitId: 'unit-C', limits: LIMITS })
    const selective = await e.verify({ mode: 'selective', unitId: 'unit-D', limits: LIMITS })
    assert.equal(actualPages, 2)
    assert.equal(prime.results[0].source.text, source.text)
    assert.equal(prime.counts.source_open_calls, 1)
    assert.equal(prime.counts.source_open_bytes, Buffer.byteLength(JSON.stringify(source)))
    assert.equal(always.counts.source_open_calls, 1)
    assert.equal(selective.counts.source_open_calls, 0)
    assert.equal(selective.results[0].reused, true)
    assert.equal(selective.receipts[0].view.epoch, prime.archive_epoch)
    assert.equal(always.archive_epoch, prime.archive_epoch)
    assert.deepEqual(always.packet, selective.packet)
    assert.equal(selective.tokenizerMeasurement, false)
    assert.equal(selective.referenceTokenCount, null)
    assert.equal(selective.results[0].tokenCountMethod, 'utf8_bytes_upper_bound')
    assert.equal(f.admissions.length, 2)
    for (const ref of selective.trace_refs) assert.equal(sha(readFileSync(join(f.config.output, ref.path))), ref.sha256)
    assert.equal(existsSync(join(f.config.output, 'memex-l2')), true)
  } finally { f.close() }
})

test('later units clone the original prime cache and never inherit receipts from an earlier arm', async () => {
  let permit = false
  const f = fixture({ authorizeOpen: async intent => ({ allowed: permit, operation_id: intent.operation_id }) }), e = f.start()
  try {
    await install(f, e)
    const prime = await e.prime({ limits: LIMITS })
    assert.deepEqual(prime.receipts, [null])
    permit = true
    const first = await e.verify({ mode: 'selective', unitId: 'first-D', limits: LIMITS })
    const second = await e.verify({ mode: 'selective', unitId: 'second-D', limits: LIMITS })
    assert.equal(first.counts.source_open_calls, 1)
    assert.equal(second.counts.source_open_calls, 1)
    assert.equal(second.results[0].reused, false)
    await assert.rejects(e.verify({ mode: 'selective', unitId: 'first-D', limits: LIMITS }), /unit_already_consumed/)
  } finally { f.close() }
})

test('oversize originals abstain before admission or any actual original open', async () => {
  const f = fixture({ sources: [{ ...source, text: 'x'.repeat(5000) }] }), e = f.start()
  try {
    e.archive.engine.openEvent = () => { throw new Error('actual original must not be read') }
    await install(f, e)
    const result = await e.prime({ limits: LIMITS })
    assert.equal(result.results[0].outcome, 'abstain')
    assert.deepEqual(result.receipts, [null])
    assert.equal(result.counts.source_open_calls, 0)
    assert.equal(f.admissions.length, 0)
    assert.equal(result.open_events[0].reason, 'source_metadata_byte_bound')
  } finally { f.close() }
})

test('prime source-open cap is enforced against actual originals and cannot reset', async () => {
  const sources = Array.from({ length: 7 }, (_, i) => ({ ...source, eventId: `test-${i}`, entity: `suite-${i}` }))
  const claims = sources.map(s => ({ ...claim, entity: s.entity }))
  const f = fixture({ sources, claims }), e = f.start()
  try {
    await install(f, e)
    const result = await e.prime({ limits: LIMITS })
    assert.equal(result.counts.source_open_calls, 6)
    assert.equal(result.receipts.filter(Boolean).length, 6)
    assert.equal(result.results[6].outcome, 'abstain')
    await assert.rejects(e.prime({ limits: LIMITS }), /prime_already_consumed/)
  } finally { f.close() }
})

test('bound archive or request changes cannot be silently reinterpreted', async () => {
  const f = fixture(), e = f.start()
  try {
    await install(f, e)
    writeFileSync(f.config.requestPath, REQUEST + 'different instruction')
    await assert.rejects(e.prime({ limits: LIMITS }), /request_digest_mismatch/)
  } finally { f.close() }
  const g = fixture()
  try {
    assert.throws(() => new PairedEvidence({ ...g.config, taskId: 'another-task' }, { authorizeOpen: async () => ({ allowed: true }) }), /archive_task_mismatch/)
    assert.throws(() => new PairedEvidence({ ...g.config, archiveSha256: '0'.repeat(64) }, { authorizeOpen: async () => ({ allowed: true }) }), /archive_digest_mismatch/)
    assert.throws(() => new PairedEvidence({ ...g.config, publicInput: { ...g.config.publicInput, gold: 'forbidden' } }, { authorizeOpen: async () => ({ allowed: true }) }), /observable_input/)
  } finally { g.close() }
})

test('unmatched admission proof yields no actual open; empty extraction remains empty', async () => {
  const f = fixture({ authorizeOpen: async () => ({ allowed: true, operation_id: 'wrong' }) }), e = f.start()
  try {
    await install(f, e)
    const p = await e.prime({ limits: LIMITS })
    assert.equal(p.counts.source_open_calls, 0)
    assert.deepEqual(p.receipts, [null])
  } finally { f.close() }
  const g = fixture({ claims: [] }), a = g.start()
  try {
    await install(g, a)
    const p = await a.prime({ limits: LIMITS })
    assert.deepEqual(p.results, [])
    assert.deepEqual(p.receipts, [])
    assert.equal(p.packet.verificationAvailable, false)
    assert.equal(p.packet.coverageEstablished, false)
  } finally { g.close() }
})

test('combined delivery cap withholds the packet and keeps full original traces', async () => {
  const f = fixture(), e = f.start()
  try {
    await install(f, e)
    await e.prime({ limits: LIMITS })
    const p = await e.verify({ mode: 'always', unitId: 'capped-C', limits: LIMITS, maxPacketBytes: 30 })
    assert.equal(p.deliveryBlocked, true)
    assert.deepEqual(p.packet.results, [])
    assert.equal(p.results[0].source.text, source.text)
    assert.ok(p.completePacketBytes > 30)
    assert.ok(p.trace_refs.some(ref => ref.path.startsWith('verifications/')))
  } finally { f.close() }
})

test('a restarted helper cannot import prime receipts or claim the previous archive epoch', async () => {
  const f = fixture(), e = f.start()
  let replacement
  try {
    await install(f, e)
    const prime = await e.prime({ limits: LIMITS })
    e.close()
    assert.throws(() => new PairedEvidence(f.config, { authorizeOpen: async () => ({ allowed: true }) }), /fresh_evidence_state_required/)
    replacement = new PairedEvidence({ ...f.config, output: join(f.root, 'second-process-state') }, {
      authorizeOpen: async intent => ({ allowed: true, operation_id: intent.operation_id }) })
    await install(f, replacement)
    assert.notEqual(replacement.archive.epoch, prime.archive_epoch)
    await assert.rejects(replacement.verify({ mode: 'selective', unitId: 'D', limits: LIMITS }), /prime_required_in_same_process/)
  } finally { replacement?.close(); f.close() }
})

test('admission cannot change request identity while verification is awaiting it', async () => {
  let f
  f = fixture({ authorizeOpen: async intent => {
    writeFileSync(f.config.requestPath, 'changed during admission')
    return { allowed: true, operation_id: intent.operation_id }
  } })
  const e = f.start()
  try {
    await install(f, e)
    await assert.rejects(e.prime({ limits: LIMITS }), /request_digest_mismatch/)
    assert.equal(existsSync(join(f.config.output, 'prime.json')), false)
    assert.equal(existsSync(join(f.config.output, 'opens/000001-admission.json')), true)
  } finally { f.close() }
})

test('real persistent JSON-lines helper waits for controller proof before opening sources', async () => {
  const f = fixture()
  const configPath = join(f.root, 'config.json')
  writeFileSync(configPath, JSON.stringify(f.config))
  const child = spawn(process.execPath, [resolve('scripts/paper1/paired_evidence.mjs'), configPath], { stdio: ['pipe', 'pipe', 'pipe'] })
  const lines = createInterface({ input: child.stdout })
  const iterator = lines[Symbol.asyncIterator]()
  let errors = ''
  child.stderr.on('data', chunk => { errors += chunk })
  const next = async () => {
    let timer
    try {
      const item = await Promise.race([iterator.next(), new Promise((_, reject) => { timer = setTimeout(() => reject(new Error('RPC timeout: ' + errors)), 5000) })])
      assert.equal(item.done, false, errors)
      return JSON.parse(item.value)
    } finally { clearTimeout(timer) }
  }
  const send = value => child.stdin.write(JSON.stringify(value) + '\n')
  try {
    send({ id: 'prepare', op: 'prepare' })
    const prepared = await next()
    assert.equal(prepared.ok, true)
    send({ id: 'install', op: 'install', rawOutput: f.raw })
    assert.equal((await next()).ok, true)
    send({ id: 'prime', op: 'prime', limits: LIMITS })
    const admission = await next()
    assert.equal(admission.kind, 'operation_admission_required')
    assert.equal(admission.intent.kind, 'source_open')
    assert.equal(admission.intent.archive_epoch, prepared.result.archive_epoch)
    assert.equal(admission.intent.source_bytes_upper_bound, Buffer.byteLength(JSON.stringify(source)))
    send({ kind: 'operation_admission_response', id: admission.id, allowed: true,
      operation_id: admission.intent.operation_id, receipt: { operation_id: admission.intent.operation_id, persisted: true } })
    const prime = await next()
    assert.equal(prime.id, 'prime')
    assert.equal(prime.result.counts.source_open_calls, 1)
    send({ id: 'D', op: 'verify', unitId: 'rpc-D', mode: 'selective', limits: LIMITS })
    const d = await next()
    assert.equal(d.kind, undefined)
    assert.equal(d.result.results[0].reused, true)
    assert.equal(d.result.archive_epoch, prime.result.archive_epoch)
    child.stdin.end()
    const code = await new Promise(done => child.once('exit', done))
    assert.equal(code, 0, errors)
  } finally { child.kill(); lines.close(); f.close() }
})
