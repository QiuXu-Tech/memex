import assert from 'node:assert/strict'
import test from 'node:test'
import { cpSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { loadReplayInputs, runReplay } from '../scripts/paper1/replay_native.mjs'

const repositoryRoot = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const smokeRoot = join(repositoryRoot, 'docs/research/p1-evidence-verification/artifacts/native-smoke')
const json = path => JSON.parse(readFileSync(path, 'utf8'))

test('actual saved native executions survive archive roundtrip and failure is not reported as a pass', async () => {
  const temporary = mkdtempSync(join(tmpdir(), 'p1-native-replay-'))
  const outputDir = join(temporary, 'replay')
  try {
    const inputs = loadReplayInputs(smokeRoot)
    const report = await runReplay({ repositoryRoot, smokeRoot, outputDir })
    const exported = json(join(outputDir, 'source-archive.json'))
    assert.equal(report.modelCalls, 0)
    assert.equal(report.rawragExecuted, false)
    assert.equal(exported.sources.length, 2)
    for (const source of exported.sources) {
      const original = inputs.selected.find(x => x.row.item.id === source.eventId)
      assert.ok(original)
      assert.equal(source.text, original.row.item.aggregatedOutput)
      assert.equal(source.observedAt, original.row.utc)
      assert.equal(source.transport.independentLiveBeforeAfterMeasurements, false)
    }
    assert.deepEqual(report.decisions.map(x => [x.result.outcome, x.result.status, x.result.reused]), [
      ['supported', 'passed', false], ['supported', 'passed', true],
      ['abstain', 'unknown', false], ['supported', 'failed', false], ['abstain', 'unknown', false],
    ])
    assert.equal(report.decisions[2].result.reason, 'version_mismatch')
    assert.ok(report.decisions.every(x => !x.result.authorizesExecution))
    assert.ok(report.publicArchiveValidation.archives.every(x => x.valid))
    assert.ok(json(join(outputDir, 'archive-roundtrip.json')).every(x => x.exactOriginalPreserved))
    for (const row of json(join(outputDir, 'comparison-inputs.json')).snapshots) {
      assert.equal(row.B_rawrag.sourceArchive, row.D_typed.sourceArchive)
      assert.equal(row.B_rawrag.archiveSha256, row.D_typed.archiveSha256)
      assert.equal(row.B_rawrag.originalRequest, row.D_typed.originalRequest)
    }
    await assert.rejects(runReplay({ repositoryRoot, smokeRoot, outputDir }), /already exists/)
  } finally { rmSync(temporary, { recursive: true, force: true }) }
})

test('offline version mapping fails when controller metadata disagrees with logged artifact bytes', () => {
  const temporary = mkdtempSync(join(tmpdir(), 'p1-native-binding-'))
  try {
    for (const name of ['native-smoke-02', 'native-smoke-02-resumed-final']) {
      cpSync(join(smokeRoot, name, 'host'), join(temporary, name, 'host'), { recursive: true })
    }
    const summaryPath = join(temporary, 'native-smoke-02-resumed-final/summary.json')
    const summary = json(join(smokeRoot, 'native-smoke-02-resumed-final/summary.json'))
    summary.source_versions.find(x => x.stage === 'original').sha256 = 'f'.repeat(64)
    writeFileSync(summaryPath, JSON.stringify(summary))
    assert.throws(() => loadReplayInputs(temporary), /controller version\/content mismatch/)
  } finally { rmSync(temporary, { recursive: true, force: true }) }
})
