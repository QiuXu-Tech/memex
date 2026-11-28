import assert from 'node:assert/strict'
import test from 'node:test'
import { verifyEvidence, digest, headCommitment } from '../scripts/paper1/verification.mjs'

const now = '2026-11-28T10:00:00.000Z'
const claim = { type: 'operation_authorization', scope: 'demo', entity: 'release', version: 'c1', actor: 'maintainer', action: 'publish' }
const source = (overrides = {}) => ({
  eventId: 'grant', sourceId: 'decisions', sourceSequence: 7, observedAt: '2026-11-28T09:00:00.000Z',
  type: claim.type, scope: claim.scope, entity: claim.entity, version: claim.version,
  role: 'user', kind: 'user_decision', actor: 'maintainer', action: 'publish', status: 'granted',
  complete: true, text: 'I approve publishing release c1 in demo.', ...overrides,
})
const view = (overrides = {}) => ({ key: JSON.stringify([claim.type, claim.scope, claim.entity]), epoch: 'archive-a', watermark: 'head-7', headCommitment: headCommitment([source()]), complete: true, headSequence: 7, headEventCount: 1, sourceId: 'decisions', ...overrides })

function archive(events, { state = view(), unavailable = false } = {}) {
  const committedState = { ...state, headCommitment: headCommitment(events.filter(e => e.sourceSequence === state.headSequence)) }
  return {
    reads: 0, searches: 0, opens: 0,
    async readView() { this.reads++; if (unavailable) throw new Error('offline'); return structuredClone(committedState) },
    async search(query) { this.searches++; assert.equal(query.entity, 'release'); return events.map(e => ({ eventId: e.eventId })) },
    async open(hit) { this.opens++; return structuredClone(events.find(e => e.eventId === hit.eventId)) },
  }
}

test('an unexpired cached grant cannot hide a later revocation', async () => {
  const old = source()
  const firstArchive = archive([old])
  const first = await verifyEvidence({ claim, now }, firstArchive)
  const revoked = source({ eventId: 'revoke', sourceSequence: 8, status: 'revoked', text: 'Approval for release c1 is revoked.' })
  const later = archive([old, revoked], { state: view({ watermark: 'head-8', headSequence: 8 }) })
  const result = await verifyEvidence({ claim, now, cached: first.receipt }, later)
  assert.equal(result.status, 'revoked')
  assert.equal(result.source.eventId, 'revoke')
  assert.equal(result.reused, false)
  assert.ok(later.searches > 0)
})

test('stable complete view allows reuse only after a fresh view read', async () => {
  const store = archive([source()])
  const first = await verifyEvidence({ claim, now }, store)
  const result = await verifyEvidence({ claim, now, cached: first.receipt }, store)
  assert.equal(result.status, 'granted')
  assert.equal(result.reused, true)
  assert.equal(store.searches, 1)
  assert.ok(store.reads >= 3)
})

test('unavailable or incomplete current view never falls back to a cached grant', async () => {
  const first = await verifyEvidence({ claim, now }, archive([source()]))
  const offline = await verifyEvidence({ claim, now, cached: first.receipt }, archive([], { unavailable: true }))
  assert.equal(offline.outcome, 'abstain')
  assert.equal(offline.reason, 'view_unavailable')
  const incomplete = await verifyEvidence({ claim, now, cached: first.receipt }, archive([], { state: view({ complete: false }) }))
  assert.equal(incomplete.outcome, 'abstain')
  assert.equal(incomplete.reason, 'incomplete_view')
})

test('a missed newer source cannot be certified by a matching older retrieval', async () => {
  const result = await verifyEvidence({ claim, now }, archive([source()], { state: view({ watermark: 'head-8', headSequence: 8 }) }))
  assert.equal(result.outcome, 'abstain')
  assert.equal(result.reason, 'head_not_opened')
})

test('opening only one of two same-head events cannot hide a conflict', async () => {
  const result = await verifyEvidence({ claim, now }, archive([source()], { state: view({ headEventCount: 2 }) }))
  assert.equal(result.outcome, 'abstain')
  assert.equal(result.reason, 'incomplete_head')
})

test('a changed view during source opening leaves the result unverified', async () => {
  const store = archive([source()])
  store.readView = async function () { return ++this.reads === 1 ? view() : view({ watermark: 'head-8', headSequence: 8 }) }
  const result = await verifyEvidence({ claim, now }, store)
  assert.equal(result.outcome, 'abstain')
  assert.equal(result.reason, 'view_changed')
})

test('out-of-order delivery follows the source sequence rather than ingestion order', async () => {
  const revoke = source({ eventId: 'revoke', sourceSequence: 8, status: 'revoked', text: 'Revoked.' })
  const result = await verifyEvidence({ claim, now }, archive([revoke, source()], { state: view({ watermark: 'head-8', headSequence: 8 }) }))
  assert.equal(result.status, 'revoked')
})

test('same-head contradiction and expired latest evidence cannot use an older grant', async () => {
  const denied = source({ eventId: 'denied', status: 'denied', text: 'Denied.' })
  const conflict = await verifyEvidence({ claim, now }, archive([source(), denied], { state: view({ headEventCount: 2 }) }))
  assert.equal(conflict.reason, 'conflict')
  const expired = source({ eventId: 'expired', sourceSequence: 8, expiresAt: now })
  const result = await verifyEvidence({ claim, now }, archive([source(), expired], { state: view({ watermark: 'head-8', headSequence: 8 }) }))
  assert.equal(result.reason, 'expired')
})

test('restart and tampered cache force opening rather than trusting the old receipt', async () => {
  const first = await verifyEvidence({ claim, now }, archive([source()]))
  const restarted = archive([source()], { state: view({ epoch: 'archive-b' }) })
  const result = await verifyEvidence({ claim, now, cached: first.receipt }, restarted)
  assert.equal(result.reused, false)
  const corrupt = structuredClone(first.receipt)
  corrupt.source.text = 'A substituted grant.'
  const store = archive([source()])
  const repaired = await verifyEvidence({ claim, now, cached: corrupt }, store)
  assert.equal(repaired.reused, false)
  assert.equal(repaired.source.text, 'I approve publishing release c1 in demo.')
})

test('wrong actor, wrong action and assistant summaries cannot prove authorization', async () => {
  for (const fields of [{ actor: 'other' }, { action: 'delete' }, { role: 'assistant', kind: 'assistant_summary' }]) {
    const result = await verifyEvidence({ claim, now }, archive([source(fields)]))
    assert.equal(result.outcome, 'abstain')
    assert.equal(result.reason, fields.role ? 'source_kind' : 'authorization_scope')
  }
})

test('always-verify uses the same source path even when reuse is possible', async () => {
  const store = archive([source()])
  const first = await verifyEvidence({ claim, now }, store)
  const result = await verifyEvidence({ claim, now, cached: first.receipt, mode: 'always' }, store)
  assert.equal(result.status, 'granted')
  assert.equal(result.reused, false)
  assert.equal(store.searches, 2)
})

test('a supported historical grant never becomes an instruction to execute', async () => {
  const result = await verifyEvidence({ claim, now }, archive([source()]))
  assert.equal(result.outcome, 'supported')
  assert.equal(result.authorizesExecution, false)
})

test('serialized evidence is bounded and is not silently truncated', async () => {
  const result = await verifyEvidence({ claim, now, maxEvidenceBytes: 100 }, archive([source({ text: 'large '.repeat(300) })]))
  assert.equal(result.reason, 'evidence_budget')
  assert.equal(result.receipt, null)
})

test('current-version discovery accepts an unknown candidate version', async () => {
  const question = { type: 'current_version', scope: 'demo', entity: 'release', version: null }
  const latest = source({ ...question, version: 'c2', kind: 'version_readback', role: 'tool', authoritative: true, status: 'current' })
  const store = archive([latest], { state: view({ key: JSON.stringify([question.type, question.scope, question.entity]) }) })
  const result = await verifyEvidence({ claim: question, now }, store)
  assert.equal(result.outcome, 'supported')
  assert.equal(result.source.version, 'c2')
})

test('unresolved artifact binding abstains rather than taking a version from hidden labels', async () => {
  const result = await verifyEvidence({ claim: { ...claim, version: null }, now }, archive([source()]))
  assert.equal(result.reason, 'unresolved_version')
})

test('a future-effective decision is not active merely because it was already ingested', async () => {
  const future = source({ effectiveAt: '2026-11-29T00:00:00.000Z' })
  const result = await verifyEvidence({ claim, now }, archive([future]))
  assert.equal(result.reason, 'not_yet_effective')
  const later = await verifyEvidence({ claim, now: '2026-11-29T01:00:00.000Z' }, archive([future]))
  assert.equal(later.status, 'granted')
})

test('reuse rechecks the view after asynchronous evidence preparation', async () => {
  const first = await verifyEvidence({ claim, now }, archive([source()]))
  let changed = false
  const store = archive([source()])
  store.readView = async () => changed ? view({ watermark: 'new', headSequence: 8 }) : view()
  store.countTokens = async () => { changed = true; return 100 }
  const result = await verifyEvidence({ claim, now, cached: first.receipt }, store)
  assert.equal(result.reason, 'view_changed')
})

test('zero-test success and wrong-artifact receipts cannot certify a passing suite', async () => {
  const target = { type: 'test_result', scope: 'demo', entity: 'release', version: 'c1' }
  const run = source({ ...target, kind: 'command_execution', role: 'tool', command: 'node --test', completed: true,
    executed: true, exitCode: 0, status: 'passed', testCount: 0 })
  const state = view({ key: JSON.stringify([target.type, target.scope, target.entity]) })
  const empty = await verifyEvidence({ claim: target, now }, archive([run], { state }))
  assert.equal(empty.reason, 'no_tests_executed')
  const wrong = await verifyEvidence({ claim: target, now }, archive([{ ...run, testCount: 4, version: 'c0' }], { state }))
  assert.equal(wrong.reason, 'version_mismatch')
})

test('rewriting a cache source and its own hash cannot forge an archive receipt', async () => {
  const first = await verifyEvidence({ claim, now }, archive([source()]))
  const forged = structuredClone(first.receipt)
  forged.source.status = 'revoked'
  forged.sourceDigest = digest(forged.source)
  const result = await verifyEvidence({ claim, now, cached: forged }, archive([source()]))
  assert.equal(result.status, 'granted')
  assert.equal(result.reused, false)
})

test('a half-written cache is a miss, not an uncaught verification exception', async () => {
  const first = await verifyEvidence({ claim, now }, archive([source()]))
  delete first.receipt.view
  const result = await verifyEvidence({ claim, now, cached: first.receipt }, archive([source()]))
  assert.equal(result.status, 'granted')
  assert.equal(result.reused, false)
})

test('opened content must match the complete trusted head commitment', async () => {
  const store = archive([source()])
  store.open = async () => source({ status: 'revoked', text: 'substitution at the same ID' })
  const result = await verifyEvidence({ claim, now }, store)
  assert.equal(result.reason, 'head_commitment_mismatch')
})
