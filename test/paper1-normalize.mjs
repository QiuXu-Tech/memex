import assert from 'node:assert/strict'
import { mkdtempSync, rmSync, writeFileSync, readFileSync } from 'node:fs'
import { createHash } from 'node:crypto'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { spawnSync } from 'node:child_process'
import test from 'node:test'
import { normalizeNodeTestEvent } from '../scripts/paper1/normalize-node.mjs'

const capture = { threadId: 'thread-public', scope: 'demo', sourceSequence: 1,
  observedAt: '2026-11-28T10:00:00Z', artifactBefore: 'a'.repeat(64), artifactAfter: 'a'.repeat(64) }
const event = { type: 'commandExecution', id: 'item-public', command: 'node --test --test-reporter=tap sum.test.mjs',
  status: 'completed', exitCode: 0, aggregatedOutput: 'TAP version 13\n1..1\n# tests 1\n# pass 1\n# fail 0\n# cancelled 0\n# skipped 0\n' }

test('an actual Node execution produces evidence without manually supplied status or entity', () => {
  const root = mkdtempSync(join(tmpdir(), 'p1-node-source-'))
  try {
    const path = join(root, 'sum.test.mjs')
    writeFileSync(path, "import test from 'node:test'; import assert from 'node:assert/strict'; test('sum', () => assert.equal(20+22,42));\n")
    // The child is a real separate test runner, not a recursive test worker.
    const childEnv = { ...process.env }
    delete childEnv.NODE_TEST_CONTEXT
    const run = spawnSync(process.execPath, ['--test', '--test-reporter=tap', 'sum.test.mjs'], { cwd: root, encoding: 'utf8', env: childEnv })
    const sha = createHash('sha256').update(readFileSync(path)).digest('hex')
    const result = normalizeNodeTestEvent({ ...event, exitCode: run.status, aggregatedOutput: run.stdout },
      { ...capture, artifactBefore: sha, artifactAfter: sha })
    assert.equal(result.issue, null, JSON.stringify({ issue: result.issue, status: run.status, stdout: run.stdout, stderr: run.stderr }))
    assert.equal(result.source.status, 'passed')
    assert.equal(result.source.entity, event.command)
    assert.equal(result.source.testCount, 1)
    assert.equal(result.source.version, sha)
    assert.equal(result.source.text, run.stdout)
    assert.equal(result.invalidatesView, false)
  } finally { rmSync(root, { recursive: true, force: true }) }
})

test('echoed TAP, assistant statements and shell chains do not become execution evidence', () => {
  for (const fields of [{ command: 'echo passed' }, { type: 'agentMessage' }, { command: 'node --test; true' }]) {
    const result = normalizeNodeTestEvent({ ...event, ...fields }, capture)
    assert.equal(result.source, null)
    assert.equal(result.invalidatesView, true)
  }
})

test('zero assertions, cancelled tests and missing completion footer cannot establish pass', () => {
  const outputs = [event.aggregatedOutput.replace('# tests 1', '# tests 0').replace('# pass 1', '# pass 0'),
    event.aggregatedOutput.replace('# cancelled 0', '# cancelled 1'), 'TAP version 13\nok 1 - first test\n']
  for (const aggregatedOutput of outputs) {
    const result = normalizeNodeTestEvent({ ...event, aggregatedOutput }, capture)
    assert.equal(result.source, null)
    assert.equal(result.invalidatesView, true)
  }
})

test('artifact changes during a test and incomplete native events invalidate normalization', () => {
  const changed = normalizeNodeTestEvent(event, { ...capture, artifactAfter: 'b'.repeat(64) })
  assert.equal(changed.issue, 'artifact_changed_during_execution')
  const cancelled = normalizeNodeTestEvent({ ...event, status: 'inProgress', exitCode: null }, capture)
  assert.equal(cancelled.source, null)
})

test('the native shell envelope can contain one standalone Node command', () => {
  const result = normalizeNodeTestEvent({ ...event, command: "/bin/zsh -lc 'node --test --test-reporter=tap sum.test.mjs'" }, capture)
  assert.equal(result.source?.status, 'passed')
  assert.equal(result.source?.entity, event.command)
})

test('native failed-completion events can provide a genuine failing-test receipt', () => {
  const result = normalizeNodeTestEvent({ ...event, status: 'failed', exitCode: 1,
    aggregatedOutput: event.aggregatedOutput.replace('# pass 1', '# pass 0').replace('# fail 0', '# fail 1') }, capture)
  assert.equal(result.source?.status, 'failed')
})

test('native TAP with an explicit test plan may omit the version header', () => {
  const result = normalizeNodeTestEvent({ ...event, aggregatedOutput: event.aggregatedOutput.replace('TAP version 13\n', 'ok 1 - sums\n') }, capture)
  assert.equal(result.source?.status, 'passed')
})

test('script arguments, eval mode and an arbitrary binary named node cannot impersonate Node test mode', () => {
  for (const command of ['node fixture-printer.js --test', 'node --eval code --test', '/opt/fake/node --test', 'node --test --import printer.mjs']) {
    const result = normalizeNodeTestEvent({ ...event, command }, capture)
    assert.equal(result.source, null)
    assert.equal(result.invalidatesView, true)
  }
})
