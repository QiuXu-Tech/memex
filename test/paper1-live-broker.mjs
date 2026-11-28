import test from 'node:test'
import assert from 'node:assert/strict'
import { createHash } from 'node:crypto'
import { mkdtempSync, readFileSync, writeFileSync, rmSync, mkdirSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { LiveBroker, CURRENT_REQUEST } from '../scripts/paper1/live-broker.mjs'

const GOOD = 'export const sum = (a, b) => a + b;\n'
const BAD = 'export const sum = (a, b) => a + b + 1;\n'
const CHECK = "import test from 'node:test';\nimport assert from 'node:assert/strict';\nimport { sum } from './sum.mjs';\ntest('sum', () => assert.equal(sum(20, 22), 42));\n"
const sha = value => createHash('sha256').update(value).digest('hex')
function fixture() {
  const root = mkdtempSync(join(tmpdir(), 'p1-broker-test-'))
  const workspace = join(root, 'workspace'); mkdirSync(workspace)
  writeFileSync(join(workspace, 'sum.mjs'), GOOD); writeFileSync(join(workspace, 'checks.test.mjs'), CHECK)
  const config = { workspace, files: ['sum.mjs', 'checks.test.mjs'], testFile: 'checks.test.mjs', scope: 'demo',
    sessionId: 'test', archiveRoot: join(root, 'archive'), outputRoot: join(root, 'output'),
    allowedContentHashes: { 'sum.mjs': [sha(GOOD), sha(BAD)], 'checks.test.mjs': [sha(CHECK)] } }
  return { root, workspace, config, close: () => rmSync(root, { recursive: true, force: true }) }
}
async function install(broker) {
  const prepared = await broker.prepareExtraction(CURRENT_REQUEST)
  const raw = JSON.stringify({ claims: [{ type: 'test_result', scope: 'demo',
    entity: 'node --test --test-reporter=tap checks.test.mjs', version: null,
    basis: { field: 'request', quote: 'test command' }, uncertainty: [] }], unresolved: [] })
  const accepted = await broker.installExtraction({ input: prepared.input, rawOutput: raw })
  assert.equal(accepted.ok, true)
}

test('real execution, live binding, archive and unchanged reuse form one persistent broker session', async () => {
  const f = fixture(); const broker = new LiveBroker(f.config)
  try {
    const first = await broker.runTests()
    assert.equal(first.source.status, 'passed')
    assert.equal(first.source.transport.liveState.beforeVersion, first.source.transport.liveState.afterVersion)
    await install(broker)
    const checked = await broker.verify({ mode: 'selective' })
    const reused = await broker.verify({ mode: 'selective' })
    assert.equal(checked.results[0].status, 'passed')
    assert.equal(reused.results[0].reused, true)
    assert.equal(reused.packet.results[0].source.text, first.source.text)
    writeFileSync(join(f.workspace, 'sum.mjs'), BAD)
    const stale = await broker.verify({ mode: 'selective' })
    assert.equal(stale.results[0].outcome, 'abstain')
    const current = await broker.runTests()
    assert.equal(current.source.status, 'failed')
    const failed = await broker.verify({ mode: 'selective' })
    assert.equal(failed.results[0].status, 'failed')
    assert.equal(failed.results[0].authorizesExecution, false)
  } finally { broker.close(); f.close() }
})

test('the execution broker refuses source bytes outside the approved development program set', async () => {
  const f = fixture(); const broker = new LiveBroker(f.config)
  try {
    writeFileSync(join(f.workspace, 'sum.mjs'), "throw new Error('unexpected program');\n")
    await assert.rejects(broker.runTests(), /execution_allowlist/)
    assert.equal(broker.metrics.testExecutions, 0)
  } finally { broker.close(); f.close() }
})

test('public tool dispatcher cannot invoke controller operations or accept arbitrary paths', async () => {
  const f = fixture(); const broker = new LiveBroker(f.config)
  try {
    await assert.rejects(broker.publicCall('install_extraction', {}), /unknown_public_tool/)
    await assert.rejects(broker.publicCall('workspace_inspect', { path: '../secret' }), /unexpected_tool_arguments/)
    const view = await broker.publicCall('workspace_inspect', {})
    assert.deepEqual(view.files.map(x => x.path).sort(), ['checks.test.mjs', 'sum.mjs'])
    assert.equal(JSON.stringify(view).includes(f.root), false)
  } finally { broker.close(); f.close() }
})

test('unknown or empty model claims cannot silently become a successful verification packet', async () => {
  const f = fixture(); const broker = new LiveBroker(f.config)
  try {
    const p = await broker.prepareExtraction(CURRENT_REQUEST)
    const result = await broker.installExtraction({ input: p.input, rawOutput: null })
    assert.equal(result.ok, false)
    const packet = await broker.verify({ mode: 'selective' })
    assert.equal(packet.packet.verificationAvailable, false)
    assert.equal(packet.packet.coverageEstablished, false)
  } finally { broker.close(); f.close() }
})

test('broker refuses used session state instead of restarting its sequence and budgets', async () => {
  const f = fixture(); const broker = new LiveBroker(f.config)
  try {
    await broker.runTests()
    broker.close()
    assert.throws(() => new LiveBroker(f.config), /fresh_broker_state_required/)
  } finally { f.close() }
})

test('current-only extraction rejects historical requests, altered inputs and consumed preparations', async () => {
  const f = fixture(); const broker = new LiveBroker(f.config)
  try {
    await assert.rejects(broker.prepareExtraction('Did tests pass yesterday for an older workspace?'), /unsupported_current_request/)
    const prepared = await broker.prepareExtraction(CURRENT_REQUEST)
    await assert.rejects(broker.installExtraction({ input: { ...prepared.input, request: 'old request' }, rawOutput: '{}' }), /unbound_extraction_input/)
    const result = await broker.installExtraction({ input: prepared.input, rawOutput: '{"claims":[],"unresolved":[]}' })
    assert.equal(result.ok, true)
    await assert.rejects(broker.installExtraction({ input: prepared.input, rawOutput: '{}' }), /unbound_extraction_input/)
    const changed = await broker.prepareExtraction(CURRENT_REQUEST)
    const pending = await broker.verify({ mode: 'selective' })
    assert.equal(pending.packet.verificationAvailable, false)
    writeFileSync(join(f.workspace, 'sum.mjs'), BAD)
    await assert.rejects(broker.installExtraction({ input: changed.input, rawOutput: '{}' }), /extraction_workspace_changed/)
  } finally { broker.close(); f.close() }
})

test('starting a new extraction invalidates the previous installed proposals', async () => {
  const f = fixture(); const broker = new LiveBroker(f.config)
  try {
    await broker.runTests(); await install(broker)
    assert.equal((await broker.verify()).packet.verificationAvailable, true)
    await broker.prepareExtraction(CURRENT_REQUEST)
    assert.equal((await broker.verify()).packet.verificationAvailable, false)
  } finally { broker.close(); f.close() }
})

test('combined delivery budget is checked and does not silently truncate original evidence', async () => {
  const f = fixture(); const broker = new LiveBroker(f.config)
  try {
    await broker.runTests(); await install(broker)
    const result = await broker.verify({ mode: 'selective', maxPacketBytes: 20 })
    assert.equal(result.deliveryBlocked, true)
    assert.equal(result.packet.verificationAvailable, false)
    assert.equal(result.packet.results.length, 0)
  } finally { broker.close(); f.close() }
})

test('simulated decisions are recorded as attempts without the broker declaring their correctness', async () => {
  const f = fixture(); const broker = new LiveBroker(f.config)
  try {
    const r = await broker.publicCall('record_decision', { decision: 'release', evidenceEventIds: [], explanation: 'No evidence.' })
    assert.equal(r.recorded, true)
    assert.equal(r.simulated, true)
    assert.equal(r.correct, undefined)
    const rows = readFileSync(join(f.config.outputRoot, 'decisions.jsonl'), 'utf8').trim().split('\n').map(JSON.parse)
    assert.equal(rows[0].decision, 'release')
    assert.equal(rows[0].evidenceEventIds.length, 0)
  } finally { broker.close(); f.close() }
})
