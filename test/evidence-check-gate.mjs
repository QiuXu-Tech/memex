import assert from 'node:assert/strict'
import { spawn } from 'node:child_process'
import { createHash } from 'node:crypto'
import { createInterface } from 'node:readline'
import test from 'node:test'
import { fileURLToPath } from 'node:url'
import { checkEvidence } from '../scripts/evidence-check-gate.mjs'

const now = '2026-11-26T00:00:00.000Z'
const claim = { type: 'test_result', scope: 'workspace/release', entity: 'integration', version: 'commit-13' }
const current = { ...claim, type: 'current_version', entity: 'production' }
const authorization = { ...claim, type: 'operation_authorization', entity: 'deploy' }

function original(target, fields = {}) {
  const defaults = {
    test_result: { kind: 'test_receipt', status: 'passed', exitCode: 0 },
    current_version: { kind: 'version_readback', status: 'current' },
    operation_authorization: { kind: 'user_decision', status: 'granted' },
  }
  return {
    ...target, ...defaults[target.type], observedAt: '2026-11-25T00:00:00.000Z', complete: true,
    sourceRef: 'session-a/event-2', excerpt: 'Original event text.', ...fields,
  }
}

const opened = (source) => ({ source, opened: true })
const noRetrieval = { search() { assert.fail('sufficient original evidence triggered a search') } }

function retrieval(...batches) {
  const sources = new Map(batches.flat().map((source) => [source.sourceRef, source]))
  return {
    search(query) {
      return (batches[query.attempt - 1] ?? []).map(({ sourceRef }) => ({ sourceRef }))
    },
    open(hit) {
      return sources.get(hit.sourceRef)
    },
  }
}

test('sufficient opened evidence supports the claim without retrieval or injection', async () => {
  const result = await checkEvidence({ claim, now, currentEvidence: [opened(original(claim))] }, noRetrieval)
  assert.equal(result.outcome, 'supported')
  assert.equal(result.status, 'passed')
  assert.equal(result.triggered, false)
  assert.equal(result.injection, null)
  assert.equal(result.referenceTokens, 0)
  assert.equal(result.source.sourceRef, 'session-a/event-2')
})

test('search snippets cannot support a claim and the trace records actual source opening', async () => {
  const source = original(claim)
  const result = await checkEvidence({ claim, now, currentEvidence: [{ source, opened: false }] }, retrieval([source]))
  assert.deepEqual(result.trace.map(({ stage }) => stage), ['trigger', 'query', 'open', 'conclusion'])
  assert.equal(result.trace[0].reason, 'incomplete_source')
  assert.equal(result.trace[1].query.scope, 'workspace/release')
  assert.equal(result.trace[2].sourceRef, 'session-a/event-2')
  assert.equal(result.trace[2].outcome, 'opened')
  assert.equal(result.outcome, 'supported')
  assert.match(result.injection, /Original event text/)
})

test('irrelevant, incomplete, and assistant-sourced hits do not authorize an operation', async () => {
  const foreign = original(authorization, { scope: 'workspace/other', sourceRef: 'foreign' })
  const truncated = original(authorization, { complete: false, sourceRef: 'truncated' })
  const assistant = original(authorization, { kind: 'assistant_summary', sourceRef: 'summary' })
  const result = await checkEvidence({ claim: authorization, now }, retrieval([foreign, truncated], [assistant]))
  assert.equal(result.outcome, 'abstain')
  assert.equal(result.status, 'unknown')
  assert.equal(result.injection, null)
  assert.deepEqual(result.trace.filter(({ stage }) => stage === 'query').map(({ query }) => query.attempt), [1, 2])
  assert.deepEqual(result.trace.filter(({ stage }) => stage === 'open').map(({ outcome }) => outcome), ['wrong_scope_or_entity', 'incomplete_source', 'untrusted_source_kind'])
})

test('a stale local grant triggers recovery and the later user revocation takes precedence', async () => {
  const grant = original(authorization, { observedAt: '2026-11-24T00:00:00.000Z' })
  const revoke = original(authorization, { status: 'revoked', sourceRef: 'original-user-revocation' })
  const result = await checkEvidence({ claim: { ...authorization, maxAgeMs: 86_400_000 }, now, currentEvidence: [opened(grant)] }, retrieval([grant, revoke]))
  assert.equal(result.trace[0].reason, 'stale_receipt')
  assert.equal(result.outcome, 'supported')
  assert.equal(result.status, 'revoked')
  assert.equal(result.source.sourceRef, 'original-user-revocation')
})

test('possible new version outranks an older expected-version readback', async () => {
  const old = original(current, { observedAt: '2026-11-24T00:00:00.000Z' })
  const next = original(current, { version: 'commit-14', sourceRef: 'latest-readback' })
  const result = await checkEvidence({ claim: current, now }, retrieval([old, next]))
  assert.equal(result.outcome, 'abstain')
  assert.equal(result.reason, 'version_mismatch')
  assert.equal(result.injection, null)
  assert.equal(result.trace.find(({ sourceRef }) => sourceRef === 'latest-readback')?.outcome, 'opened')
})

test('same-time contradictory version readbacks remain unresolved', async () => {
  const expected = original(current)
  const other = original(current, { version: 'commit-14', sourceRef: 'same-time-version' })
  const result = await checkEvidence({ claim: current, now, currentEvidence: [opened(expected), opened(other)] }, retrieval([]))
  assert.equal(result.triggered, true)
  assert.equal(result.reason, 'conflict')
})

test('a later failed run takes precedence over a passing older run', async () => {
  const passing = original(claim, { observedAt: '2026-11-24T00:00:00.000Z' })
  const failed = original(claim, { status: 'failed', exitCode: 1, sourceRef: 'failing-execution' })
  const result = await checkEvidence({ claim, now }, retrieval([passing, failed]))
  assert.equal(result.outcome, 'supported')
  assert.equal(result.status, 'failed')
  assert.equal(result.source.sourceRef, 'failing-execution')
})

test('exit status is necessary for a passing run and an explicit not-run record stays not_run', async () => {
  const falsePass = original(claim, { exitCode: null })
  const uncertain = await checkEvidence({ claim, now }, retrieval([falsePass]))
  assert.equal(uncertain.outcome, 'abstain')
  const skip = original(claim, { status: 'not_run', executed: false, exitCode: null })
  const skipped = await checkEvidence({ claim, now }, retrieval([skip]))
  assert.equal(skipped.outcome, 'supported')
  assert.equal(skipped.status, 'not_run')
})

test('wrong receipt version and ambiguous current authorization stay unknown', async () => {
  const other = original(claim, { version: 'commit-12' })
  const wrongVersion = await checkEvidence({ claim, now }, retrieval([other]))
  assert.equal(wrongVersion.reason, 'version_mismatch')
  const uncertain = original(authorization, { status: 'unknown' })
  const unknown = await checkEvidence({ claim: authorization, now }, retrieval([uncertain]))
  assert.equal(unknown.reason, 'unknown_status')
})

test('an exact-version miss broadens the second query without accepting a different version', async () => {
  const other = original(claim, { version: 'commit-12' })
  const result = await checkEvidence({ claim, now }, {
    search(query) {
      return query.matchVersion ? [] : [{ sourceRef: other.sourceRef }]
    },
    open() { return other },
  })
  assert.equal(result.outcome, 'abstain')
  assert.equal(result.reason, 'version_mismatch')
  assert.equal(result.injection, null)
})

test('a match with a different original locator cannot substitute the event', async () => {
  const result = await checkEvidence({ claim, now }, {
    search: () => [{ sourceRef: 'expected' }],
    open: () => original(claim, { sourceRef: 'substituted' }),
  })
  assert.equal(result.outcome, 'abstain')
  assert.ok(result.trace.some(({ outcome }) => outcome === 'source_mismatch'))
})

test('an indexed original excerpt digest prevents substitution at the same locator', async () => {
  const excerptSha256 = createHash('sha256').update('Unaltered original.').digest('hex')
  const result = await checkEvidence({ claim, now }, {
    search: () => [{ sourceRef: 'session-a/event-2', excerptSha256 }],
    open: () => original(claim),
  })
  assert.equal(result.outcome, 'abstain')
  assert.ok(result.trace.some(({ outcome }) => outcome === 'source_mismatch'))
})

test('forced positive control actually uses the same search and open path', async () => {
  const source = original(claim)
  const result = await checkEvidence({ claim, now, currentEvidence: [opened(source)], mode: 'forced' }, retrieval([source]))
  assert.deepEqual(result.trace.map(({ stage }) => stage), ['trigger', 'query', 'open', 'conclusion'])
  assert.equal(result.trace[0].reason, 'forced_control')
  assert.equal(result.triggered, true)
  assert.equal(result.outcome, 'supported')
  assert.match(result.injection, /Original event text/)
})

test('an unread matching hit triggers a second lookup even when another hit supports a grant', async () => {
  const grant = original(authorization, { observedAt: '2026-11-24T00:00:00.000Z' })
  const revoke = original(authorization, { status: 'revoked', sourceRef: 'open-retry' })
  let attempts = 0
  const result = await checkEvidence({ claim: authorization, now }, {
    search({ attempt }) {
      return (attempt === 1 ? [grant, revoke] : [revoke]).map(({ sourceRef }) => ({ sourceRef }))
    },
    open({ sourceRef }) {
      if (sourceRef === grant.sourceRef) return grant
      if (attempts++ === 0) throw new Error('original store temporarily unavailable')
      return revoke
    },
  })
  assert.equal(result.status, 'revoked')
  assert.equal(result.source.sourceRef, 'open-retry')
  assert.equal(result.trace.filter(({ stage }) => stage === 'query').length, 2)
  assert.ok(result.trace.some(({ error }) => error === 'original store temporarily unavailable'))
})

test('a permanently unread matching hit leaves a possible contradictory grant unverified', async () => {
  const grant = original(authorization)
  const result = await checkEvidence({ claim: authorization, now }, {
    search: () => [{ sourceRef: grant.sourceRef }, { sourceRef: 'unread' }],
    open: ({ sourceRef }) => sourceRef === 'unread' ? null : grant,
  })
  assert.equal(result.outcome, 'abstain')
  assert.equal(result.reason, 'missing_receipt')
  assert.equal(result.injection, null)
})

test('an expired latest grant cannot fall back to an earlier grant', async () => {
  const older = original(authorization, { observedAt: '2026-11-24T00:00:00.000Z' })
  const expired = original(authorization, { expiresAt: now, sourceRef: 'expired-current-decision' })
  const result = await checkEvidence({ claim: authorization, now }, retrieval([older, expired]))
  assert.equal(result.outcome, 'abstain')
  assert.equal(result.reason, 'stale_receipt')
})

test('the serialized complete injection obeys the 1200 reference-token cap', async () => {
  const source = original(claim)
  const exact = await checkEvidence({ claim, now }, {
    ...retrieval([source]),
    countTokens(injection) {
      assert.match(injection, /session-a\/event-2/)
      assert.match(injection, /Original event text/)
      return 1200
    },
  })
  assert.equal(exact.referenceTokens, 1200)
  const overflow = await checkEvidence({ claim, now }, { ...retrieval([source]), countTokens: () => 1201 })
  assert.equal(overflow.reason, 'token_budget')
  assert.equal(overflow.injection, null)
  assert.equal(overflow.referenceTokens, 0)
  assert.equal(overflow.trace.at(-1).candidateReferenceTokens, 1201)
})

test('JSON-lines bridges a real search, source open, and tokenizer interaction', async () => {
  const script = fileURLToPath(new URL('../scripts/evidence-check-gate.mjs', import.meta.url))
  const child = spawn(process.execPath, [script], { stdio: ['pipe', 'pipe', 'inherit'] })
  const messages = createInterface({ input: child.stdout })[Symbol.asyncIterator]()
  const next = async () => JSON.parse((await messages.next()).value)
  const send = (value) => child.stdin.write(`${JSON.stringify(value)}\n`)
  try {
    send({ claim, now, countReferenceTokens: true })
    const search = await next()
    assert.equal(search.op, 'search')
    send({ value: [{ sourceRef: 'session-a/event-2' }] })
    const open = await next()
    assert.equal(open.op, 'open')
    send({ value: original(claim) })
    const count = await next()
    assert.equal(count.op, 'count_tokens')
    assert.match(count.injection, /Original event text/)
    send({ value: 37 })
    const result = await next()
    assert.equal(result.op, 'result')
    assert.equal(result.result.outcome, 'supported')
    assert.equal(result.result.referenceTokens, 37)
  } finally {
    child.stdin.end()
  }
})
