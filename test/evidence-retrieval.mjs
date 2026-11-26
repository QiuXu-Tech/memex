import assert from 'node:assert/strict'
import { mkdtempSync, rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import test from 'node:test'
import { AgentMemory } from '../packages/memex-core/lib/engine.js'

test('evidence search checks identifiers, quotes, scopes and validity before returning candidates', () => {
  const root = mkdtempSync(join(tmpdir(), 'evidence-search-'))
  const reader = sessionId => new AgentMemory({ root, cwd: root, sessionId, levels: ['l2','l3'] })
  const engine = reader('reader')
  const foreign = reader('private')
  try {
    const source = 'fixture://receipts'
    const write = (target, id, revision, extra = {}) => target.write({
      id, kind: 'decision', scope: 'session', title: 'Orchid receipt ledger',
      body: 'Object delta-10 completed in 231 ms', ...extra,
      provenance: { evidence: { source, version: revision, ...extra.provenance?.evidence } },
    })
    write(engine, 'exact-id', 'v2')
    write(engine, 'prefix', 'v2', { body: 'Object delta-101 completed in 331 ms' })
    write(foreign, 'other-session', 'v2')
    write(engine, 'past', 'v1', { provenance: { evidence: { validUntil: '2020-01-01T00:00:00.000Z' } } })
    const ids = (query, options) => engine.search({ query, evidenceSearch: true, ...options }).hits.map(card => card.id)
    assert.deepEqual(ids('exact-id'), ['exact-id'])
    assert.deepEqual(ids('Find delta-10'), ['exact-id'])
    assert.deepEqual(ids('Orchid ledger "231 ms"'), ['exact-id'])
    assert.deepEqual(ids('Orchid ledger "231 ms"', { source, version: 'v1' }), [])
    assert.deepEqual(ids('Orchid ledger "231 ms"', { source, version: 'v1', includeExpired: true }), ['past'])
    assert.deepEqual(ids('Orchid ledger "447 ms"'), [])
    assert.deepEqual(ids('Orchid', { source, version: 'unknown' }), [])
  } finally {
    engine.close()
    foreign.close()
    rmSync(root, { recursive: true, force: true })
  }
})
