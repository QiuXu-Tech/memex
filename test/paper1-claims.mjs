import assert from 'node:assert/strict'
import test from 'node:test'
import { extractClaims } from '../scripts/paper1/claims.mjs'

const input = { request: 'Can we publish the release?', draft: 'The maintainer approved publishing commit c1.',
  context: 'Workspace demo; target release; current artifact commit c1.', toolDescriptions: ['read logs', 'read versions'] }
const output = { claims: [{ type: 'operation_authorization', scope: 'demo', entity: 'release', version: 'c1',
  actor: 'maintainer', action: 'publish', basis: { field: 'draft', quote: 'approved publishing commit c1' }, uncertainty: [] }], unresolved: [] }

test('automatic extraction sees only observable input and validates a grounded proposal', async () => {
  let observed
  const result = await extractClaims(input, async prompt => { observed = prompt; return JSON.stringify(output) })
  assert.equal(result.ok, true)
  assert.equal(result.claims[0].entity, 'release')
  assert.match(observed, /Can we publish the release/)
  assert.equal(result.claims[0].sourceRef, undefined)
})

test('gold fields never reach the extractor, including innocuous-looking unknown keys', async () => {
  for (const key of ['claims', 'gold', 'expectedSource', 'answer', 'metadata']) {
    let called = false
    await assert.rejects(() => extractClaims({ ...input, [key]: output }, async () => { called = true; return '{}' }), /observable input/)
    assert.equal(called, false)
  }
})

test('source IDs and hidden event positions cannot be returned as claim hints', async () => {
  for (const field of ['sourceRef', 'eventIndex', 'correctSourceId']) {
    const candidate = structuredClone(output)
    candidate.claims[0][field] = 'evt-answer'
    const result = await extractClaims(input, async () => JSON.stringify(candidate))
    assert.equal(result.ok, false)
    assert.equal(result.reason, 'invalid_extraction')
  }
})

test('hallucinated grounding, missing actor and malformed model output are counted failures', async () => {
  const badQuote = structuredClone(output); badQuote.claims[0].basis.quote = 'not present in the observable text'
  const badActor = structuredClone(output); delete badActor.claims[0].actor
  for (const bad of [JSON.stringify(badQuote), JSON.stringify(badActor), 'not json']) {
    const result = await extractClaims(input, async () => bad)
    assert.equal(result.ok, false)
    assert.equal(result.reason, 'invalid_extraction')
    assert.equal(result.claims.length, 0)
  }
})

test('empty extraction does not assert that all hidden obligations were covered', async () => {
  const result = await extractClaims(input, async () => JSON.stringify({ claims: [], unresolved: ['ambiguous target'] }))
  assert.equal(result.ok, true)
  assert.equal(result.coverageEstablished, false)
  assert.equal(result.unresolved[0], 'ambiguous target')
})

test('a null model response is retained as an extraction failure', async () => {
  const result = await extractClaims(input, async () => null)
  assert.equal(result.ok, false)
  assert.equal(result.reason, 'invalid_extraction')
})
