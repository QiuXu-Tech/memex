import assert from 'node:assert/strict'
import { mkdtempSync, rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import test from 'node:test'
import { EvidenceArchive } from '../scripts/paper1/archive.mjs'
import { verifyEvidence } from '../scripts/paper1/verification.mjs'

const now = '2026-11-28T10:00:00.000Z'
const claim = { type: 'test_result', scope: 'project', entity: 'unit', version: 'commit-a' }
const pass = { ...claim, eventId: 'test-pass', sourceId: 'runner', sourceSequence: 3,
  observedAt: '2026-11-28T09:00:00.000Z', role: 'tool', kind: 'command_execution',
  status: 'passed', complete: true, command: 'node --test', completed: true, executed: true, exitCode: 0, testCount: 4,
  text: 'TAP version 13\n# tests 4\n# pass 4\n# fail 0\n' }
const note = { ...pass, eventId: 'unrelated', type: 'note', entity: 'notes', sourceSequence: 1, text: 'Unrelated work log.' }

test('Memex opens the discovered original index, including multi-page content', async () => {
  const root = mkdtempSync(join(tmpdir(), 'p1-archive-'))
  const archive = new EvidenceArchive({ root, cwd: root, sessionId: 'test', pageChars: 400 })
  try {
    archive.ingest([note, { ...pass, text: pass.text + 'detail '.repeat(170) }], { recordId: 'batch-a' })
    archive.setSynchronized(true)
    const hits = await archive.search({ ...claim, query: 'project unit test_result', limit: 10 })
    assert.equal(hits.length, 1)
    assert.equal(hits[0].eventIndex, 2)
    const opened = await archive.open(hits[0])
    assert.equal(opened.eventId, 'test-pass')
    assert.equal(opened.text, pass.text + 'detail '.repeat(170))
    const other = new EvidenceArchive({ root, cwd: root, sessionId: 'different-session' })
    try { assert.equal((await other.search({ ...claim, query: 'project unit', limit: 10 })).length, 0) }
    finally { other.close() }
  } finally { archive.close(); rmSync(root, { recursive: true, force: true }) }
})

test('an incomplete ingestion is explicit and restart invalidates an old reuse certificate', async () => {
  const root = mkdtempSync(join(tmpdir(), 'p1-restart-'))
  let archive = new EvidenceArchive({ root, cwd: root, sessionId: 'test' })
  try {
    archive.ingest([pass])
    const unsealed = await verifyEvidence({ claim, now }, archive)
    assert.equal(unsealed.reason, 'incomplete_view')
    archive.setSynchronized(true)
    const first = await verifyEvidence({ claim, now }, archive)
    assert.equal(first.status, 'passed')
    archive.close()
    archive = new EvidenceArchive({ root, cwd: root, sessionId: 'test' })
    const reopened = await verifyEvidence({ claim, now, cached: first.receipt }, archive)
    assert.equal(reopened.status, 'passed')
    assert.equal(reopened.reused, false)
    assert.ok(reopened.metrics.opens > 0)
  } finally { archive.close(); rmSync(root, { recursive: true, force: true }) }
})

test('view reads observe another writer even when no invalidation notification was received', async () => {
  const root = mkdtempSync(join(tmpdir(), 'p1-writer-'))
  const reader = new EvidenceArchive({ root, cwd: root, sessionId: 'test' })
  const writer = new EvidenceArchive({ root, cwd: root, sessionId: 'test' })
  try {
    reader.ingest([pass]); reader.setSynchronized(true)
    const old = await verifyEvidence({ claim, now }, reader)
    writer.ingest([{ ...pass, eventId: 'test-fail', sourceSequence: 4, status: 'failed', exitCode: 1, text: 'AssertionError: expected 42, received 41.' }])
    writer.setSynchronized(true)
    const result = await verifyEvidence({ claim, now, cached: old.receipt }, reader)
    assert.equal(result.status, 'failed')
    assert.equal(result.source.eventId, 'test-fail')
  } finally { reader.close(); writer.close(); rmSync(root, { recursive: true, force: true }) }
})

test('immutable event identity and source-order ambiguity fail conservatively', async () => {
  const root = mkdtempSync(join(tmpdir(), 'p1-identity-'))
  const archive = new EvidenceArchive({ root, cwd: root, sessionId: 'test' })
  try {
    archive.ingest([pass])
    assert.throws(() => archive.ingest([{ ...pass, text: 'changed in place' }]), /immutable/)
    archive.ingest([{ ...pass, eventId: 'other-runner', sourceId: 'independent-runner', sourceSequence: 1 }])
    archive.setSynchronized(true)
    const result = await verifyEvidence({ claim, now }, archive)
    assert.equal(result.reason, 'ambiguous_source_order')
  } finally { archive.close(); rmSync(root, { recursive: true, force: true }) }
})
