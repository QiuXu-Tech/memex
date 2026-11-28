import test from 'node:test'
import assert from 'node:assert/strict'
import { mkdtempSync, readFileSync, rmSync } from 'node:fs'
import { join, resolve } from 'node:path'
import { tmpdir } from 'node:os'
import { ReadonlyReplay, ARCHIVE_SHA256 } from '../scripts/paper1/readonly_replay.mjs'

const source = resolve('docs/research/p1-evidence-verification/artifacts/replay/native-smoke-02/source-archive.json')
function fixture() {
  const root = mkdtempSync(join(tmpdir(), 'p1-readonly-test-'))
  const replay = new ReadonlyReplay({ archivePath: source, output: join(root, 'state'), expectedSha256: ARCHIVE_SHA256 })
  const latest = JSON.parse(readFileSync(source)).sources.at(-1)
  const raw = JSON.stringify({ claims: [{ type: 'test_result', scope: latest.scope, entity: latest.entity,
    version: latest.version, basis: { field: 'request', quote: 'configured tests pass' }, uncertainty: [] }], unresolved: [] })
  return { root, replay, latest, raw, close() { replay.close(); rmSync(root, { recursive: true, force: true }) } }
}

test('extraction preparation contains only observable task input and no receipt selection', () => {
  const f = fixture()
  try {
    const prepared = f.replay.prepare()
    assert.deepEqual(Object.keys(prepared.input).sort(), ['context', 'draft', 'request', 'toolDescriptions'])
    for (const forbidden of ['eventId', 'sourceId', 'expected', 'failed', 'passed', 'exec-'])
      assert.equal(JSON.stringify(prepared.input).includes(forbidden), false, forbidden)
  } finally { f.close() }
})

test('same actual extraction feeds C and D; D reuses a real source and C reopens it', async () => {
  const f = fixture()
  try {
    f.replay.prepare()
    assert.equal((await f.replay.install(f.raw)).ok, true)
    const prime = await f.replay.verify('selective')
    const always = await f.replay.verify('always')
    const selective = await f.replay.verify('selective')
    assert.equal(prime.results[0].status, 'failed')
    assert.ok(always.results[0].metrics.opens > 0)
    assert.equal(selective.results[0].metrics.opens, 0)
    assert.equal(selective.results[0].reused, true)
    assert.equal(selective.packet.results[0].source.text, f.latest.text)
    assert.deepEqual(always.packet, selective.packet)
    assert.equal(selective.packet.authorizesExecution, false)
    assert.equal(selective.packet.coverageEstablished, false)
  } finally { f.close() }
})

test('empty or invalid actual extraction is retained without manually supplied claims', async () => {
  const f = fixture()
  try {
    f.replay.prepare()
    assert.equal((await f.replay.install('not JSON')).ok, false)
    await assert.rejects(f.replay.verify('selective'), /no_accepted_extraction/)
    await assert.rejects(f.replay.install(f.raw), /preparation_consumed/)
  } finally { f.close() }
})

test('an oversized combined packet is withheld, never silently truncated', async () => {
  const f = fixture()
  try {
    f.replay.prepare(); await f.replay.install(f.raw)
    const result = await f.replay.verify('always', 30)
    assert.equal(result.deliveryBlocked, true)
    assert.deepEqual(result.packet.results, [])
    assert.equal(result.packet.verificationAvailable, false)
  } finally { f.close() }
})

test('a wrong pinned source digest cannot be reinterpreted as the known replay', () => {
  const root = mkdtempSync(join(tmpdir(), 'p1-readonly-hash-'))
  try { assert.throws(() => new ReadonlyReplay({ archivePath: source, output: join(root, 'state'), expectedSha256: '0'.repeat(64) }), /archive_digest/) }
  finally { rmSync(root, { recursive: true, force: true }) }
})
