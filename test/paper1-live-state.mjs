import assert from 'node:assert/strict'
import test from 'node:test'
import fs from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { EvidenceArchive } from '../scripts/paper1/archive.mjs'
import { verifyEvidence } from '../scripts/paper1/verification.mjs'
import * as live from '../scripts/paper1/live-state.mjs'

function workspace(t) {
  const parent = fs.mkdtempSync(join(tmpdir(), 'p1-live-state-'))
  const root = join(parent, 'workspace')
  fs.mkdirSync(root)
  fs.writeFileSync(join(root, 'unit.mjs'), 'abc')
  fs.writeFileSync(join(root, 'package-lock.json'), '{"lockfileVersion":3}\n')
  t.after(() => fs.rmSync(parent, { recursive: true, force: true }))
  return { parent, root, config: { root, files: ['unit.mjs'], environment: { cwd: '.', lockfiles: ['package-lock.json'], values: { NODE_ENV: 'test' } } } }
}

test('content-addressed snapshots are repeatable and include declared lockfiles and observed Node environment', async t => {
  const { config } = workspace(t)
  const first = await live.captureWorkspace(config)
  assert.equal(first.ok, true, first.reason)
  const second = await live.captureWorkspace(config)
  assert.equal(second.ok, true, second.reason)
  assert.equal(first.version, second.version)
  assert.match(first.version, /^[a-f0-9]{64}$/)
  assert.equal(first.manifest.files.find(x => x.path === 'unit.mjs').sha256,
    'ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad')
  assert.equal(first.manifest.environment.nodeVersion, process.version)
  assert.equal(first.manifest.environment.cwd, '.')
  assert.equal(first.manifest.environment.values.NODE_ENV, 'test')
  assert.deepEqual(first.manifest.files.map(x => x.path), ['package-lock.json', 'unit.mjs'])
  assert.equal(first.observation.passes, 2)
})

test('a same-size content mutation invalidates the version even when mtime is restored', async t => {
  const { root, config } = workspace(t)
  const before = await live.captureWorkspace(config)
  assert.equal(before.ok, true, before.reason)
  const path = join(root, 'unit.mjs')
  const old = fs.statSync(path)
  fs.writeFileSync(path, 'xyz')
  fs.utimesSync(path, old.atime, old.mtime)
  const after = await live.captureWorkspace(config)
  assert.equal(after.ok, true, after.reason)
  assert.notEqual(after.version, before.version)
})

test('adding a directory member and changing a declared lockfile both invalidate snapshots', async t => {
  const { root, config } = workspace(t)
  const before = await live.captureWorkspace(config)
  assert.equal(before.ok, true, before.reason)
  fs.writeFileSync(join(root, 'added.mjs'), 'new dependency')
  const added = await live.captureWorkspace(config)
  assert.equal(added.ok, true, added.reason)
  assert.notEqual(added.version, before.version)
  fs.unlinkSync(join(root, 'added.mjs'))
  const restored = await live.captureWorkspace(config)
  assert.equal(restored.ok, true, restored.reason)
  assert.equal(restored.version, before.version)
  fs.writeFileSync(join(root, 'package-lock.json'), '{"lockfileVersion":3,"packages":{"x":{}}}\n')
  const lockChanged = await live.captureWorkspace(config)
  assert.equal(lockChanged.ok, true, lockChanged.reason)
  assert.notEqual(lockChanged.version, before.version)
})

test('a missing declared artifact has no usable version', async t => {
  const { root, config } = workspace(t)
  fs.unlinkSync(join(root, 'unit.mjs'))
  const result = await live.captureWorkspace(config)
  assert.equal(result.ok, false)
  assert.equal(result.version, null)
  assert.equal(result.reason, 'file_missing')
})

test('noncanonical paths, traversal, and both leaf and parent symlinks are rejected', async t => {
  const { root, parent, config } = workspace(t)
  fs.writeFileSync(join(parent, 'outside.mjs'), 'outside')
  fs.symlinkSync(join(parent, 'outside.mjs'), join(root, 'link.mjs'))
  fs.symlinkSync(parent, join(root, 'linked-directory'))
  for (const path of ['../outside.mjs', './unit.mjs', 'a/../unit.mjs', '/etc/passwd', 'a//b', 'a\\b']) {
    const result = await live.captureWorkspace({ ...config, files: [path] })
    assert.equal(result.ok, false, path)
    assert.equal(result.reason, 'noncanonical_path', path)
    assert.equal(result.version, null)
  }
  for (const path of ['link.mjs', 'linked-directory/outside.mjs']) {
    const result = await live.captureWorkspace({ ...config, files: [path] })
    assert.equal(result.ok, false, path)
    assert.equal(result.reason, 'symlink', path)
  }
})

test('file-count and byte budgets fail before returning an incomplete digest', async t => {
  const { config } = workspace(t)
  const files = await live.captureWorkspace({ ...config, limits: { maxFiles: 1 } })
  assert.equal(files.ok, false)
  assert.equal(files.reason, 'file_count_limit')
  const bytes = await live.captureWorkspace({ ...config, limits: { maxTotalBytes: 2 } })
  assert.equal(bytes.ok, false)
  assert.equal(bytes.reason, 'byte_limit')
  assert.equal(bytes.version, null)
})

test('a real mutation during an open file read is rejected rather than sealed', async t => {
  const { root, config } = workspace(t)
  const file = join(root, 'unit.mjs')
  const open = fs.promises.open.bind(fs.promises)
  let changed = false
  t.mock.method(fs.promises, 'open', async (...args) => {
    const handle = await open(...args)
    if (args[0] === file && !changed) {
      const read = handle.read.bind(handle)
      handle.read = async (...readArgs) => {
        const result = await read(...readArgs)
        if (!changed) { changed = true; fs.writeFileSync(file, 'xyz') }
        return result
      }
    }
    return handle
  })
  const result = await live.captureWorkspace(config)
  assert.equal(changed, true, 'race must actually occur against a real file')
  assert.equal(result.ok, false)
  assert.equal(result.reason, 'workspace_changed')
  assert.equal(result.version, null)
})

const proposal = () => ({ type: 'test_result', scope: 'live-project', entity: 'node --test unit.test.mjs', version: 'a proposed old version' })
const execution = snapshot => ({ eventId: 'test-run-1', sourceId: 'node-tests', sourceSequence: 1,
  type: 'test_result', scope: 'live-project', entity: 'node --test unit.test.mjs', version: snapshot.version,
  observedAt: '2026-11-28T00:00:00Z', role: 'tool', kind: 'command_execution', complete: true,
  completed: true, executed: true, command: 'node --test unit.test.mjs', exitCode: 0,
  status: 'passed', testCount: 1, text: 'TAP version 13\n# tests 1\n# pass 1\n# fail 0\n' })
const check = (claim, cached, adapter) => verifyEvidence({ claim, cached, now: '2026-11-28T00:00:01Z',
  maxEvidenceBytes: 16384, maxReferenceTokens: 16384 }, adapter)

test('current-workspace claim binding retains the proposal and refuses implicit or historical retargeting', async t => {
  const { config } = workspace(t)
  const snapshot = await live.captureWorkspace(config)
  assert.equal(typeof live.bindObservedClaim, 'function', 'live claim binding is not implemented')
  const raw = proposal()
  const bound = live.bindObservedClaim(raw, snapshot, { target: 'current_workspace' })
  assert.equal(bound.version, snapshot.version)
  assert.equal(bound.proposedVersion, 'a proposed old version')
  assert.equal(raw.version, 'a proposed old version')
  assert.equal(bound.versionBinding.source, 'live_workspace_snapshot')
  assert.throws(() => live.bindObservedClaim(raw, snapshot), { code: 'current_workspace_target_required' })
  assert.throws(() => live.bindObservedClaim(raw, snapshot, { target: 'historical' }), { code: 'current_workspace_target_required' })
  assert.throws(() => live.bindObservedClaim({ ...raw, asOf: '2026-01-01T00:00:00Z' }, snapshot,
    { target: 'current_workspace' }), { code: 'historical_query' })
})

test('execution sources bind only equal successful observations and cannot relabel an unrelated version', async t => {
  const { root, config } = workspace(t)
  const before = await live.captureWorkspace(config)
  const after = await live.captureWorkspace(config)
  assert.equal(typeof live.bindExecutionSource, 'function', 'execution binding is not implemented')
  const source = live.bindExecutionSource(execution(before), { before, after })
  assert.equal(source.version, before.version)
  assert.equal(source.transport.liveState.beforeVersion, source.transport.liveState.afterVersion)
  assert.equal(source.transport.liveState.manifest.environment.nodeVersion, process.version)
  assert.throws(() => live.bindExecutionSource({ ...execution(before), version: 'unrelated' }, { before, after }),
    { code: 'source_version_mismatch' })
  assert.throws(() => live.bindExecutionSource(execution(before), { before, after: { ok: false, version: null } }),
    { code: 'capture_unavailable' })
  fs.writeFileSync(join(root, 'unit.mjs'), 'xyz')
  const changed = await live.captureWorkspace(config)
  assert.throws(() => live.bindExecutionSource(execution(before), { before, after: changed }),
    { code: 'execution_state_changed' })
})

test('equal content hashes do not hide metadata changes observed across an execution boundary', async t => {
  const { root, config } = workspace(t)
  const before = await live.captureWorkspace(config)
  const file = join(root, 'unit.mjs')
  const previous = fs.statSync(file)
  fs.writeFileSync(file, 'xyz')
  fs.writeFileSync(file, 'abc')
  fs.utimesSync(file, previous.atime, new Date(previous.mtimeMs + 5000))
  const after = await live.captureWorkspace(config)
  assert.equal(after.version, before.version, 'the content manifest has really returned to its old value')
  assert.throws(() => live.bindExecutionSource(execution(before), { before, after }),
    { code: 'execution_state_changed' })
})

test('file ordering is canonical by code unit rather than host locale', async t => {
  const { root, config } = workspace(t)
  fs.writeFileSync(join(root, 'Z.mjs'), 'Z')
  fs.writeFileSync(join(root, 'a.mjs'), 'a')
  const snapshot = await live.captureWorkspace({ ...config, files: ['a.mjs', 'unit.mjs', 'Z.mjs'] })
  assert.equal(snapshot.ok, true, snapshot.reason)
  assert.deepEqual(snapshot.manifest.files.map(x => x.path), ['Z.mjs', 'a.mjs', 'package-lock.json', 'unit.mjs'])
})

async function archiveFixture(t) {
  const fixture = workspace(t)
  const before = await live.captureWorkspace(fixture.config)
  const after = await live.captureWorkspace(fixture.config)
  assert.equal(typeof live.withLiveState, 'function', 'live archive wrapper is not implemented')
  const archive = new EvidenceArchive({ root: join(fixture.parent, 'archive'), cwd: fixture.root,
    sessionId: 'live-state-test', pageChars: 200 })
  t.after(() => archive.close())
  archive.ingest([live.bindExecutionSource(execution(before), { before, after })])
  archive.setSynchronized(true)
  const adapter = live.withLiveState(archive, fixture.config)
  const claim = await adapter.bindClaim(proposal(), { target: 'current_workspace' })
  return { ...fixture, archive, adapter, claim }
}

test('live mutation defeats cached success even while the archive catalog is unchanged', async t => {
  const { root, archive, adapter, claim } = await archiveFixture(t)
  const initial = await check(claim, null, adapter)
  assert.equal(initial.outcome, 'supported')
  assert.equal(initial.status, 'passed')
  const reused = await check(claim, initial.receipt, adapter)
  assert.equal(reused.reused, true)
  const catalogBefore = await archive.readView(claim)
  fs.writeFileSync(join(root, 'unit.mjs'), 'xyz')
  const staleClaim = await check(claim, initial.receipt, adapter)
  assert.equal(staleClaim.outcome, 'abstain')
  assert.equal(staleClaim.reused, false)
  assert.equal((await archive.readView(claim)).watermark, catalogBefore.watermark)
  const current = await adapter.bindClaim(proposal(), { target: 'current_workspace' })
  assert.notEqual(current.version, claim.version)
  const staleEvidence = await check(current, initial.receipt, adapter)
  assert.equal(staleEvidence.outcome, 'abstain')
  assert.equal(staleEvidence.reason, 'version_mismatch')
  assert.ok(adapter.metrics.captures > 0)
  assert.ok(adapter.metrics.bytesRead > 0)
})

test('a file change inside the archive view read cannot become a stable live view', async t => {
  const { root, archive, adapter, claim } = await archiveFixture(t)
  const read = archive.readView.bind(archive)
  let changed = false
  t.mock.method(archive, 'readView', async input => {
    const value = await read(input)
    if (!changed) { changed = true; fs.writeFileSync(join(root, 'unit.mjs'), 'xyz') }
    return value
  })
  const result = await check(claim, null, adapter)
  assert.equal(changed, true)
  assert.equal(result.outcome, 'abstain')
  assert.equal(result.trace[0].bindingIssue, 'live_state_changed')
})

test('a change at the final cached-delivery check rejects the would-be reused result', async t => {
  const { root, archive, adapter, claim } = await archiveFixture(t)
  const initial = await check(claim, null, adapter)
  assert.equal(initial.status, 'passed')
  const read = archive.readView.bind(archive)
  let calls = 0
  t.mock.method(archive, 'readView', async input => {
    const value = await read(input)
    if (++calls === 2) fs.writeFileSync(join(root, 'unit.mjs'), 'xyz')
    return value
  })
  const result = await check(claim, initial.receipt, adapter)
  assert.equal(calls, 2)
  assert.equal(result.outcome, 'abstain')
  assert.equal(result.reason, 'view_changed')
  assert.equal(result.reused, false)
})

test('an execution without before/after binding is rejected even if its version equals the live digest', async t => {
  const { parent, root, config } = workspace(t)
  const snapshot = await live.captureWorkspace(config)
  assert.equal(typeof live.withLiveState, 'function', 'live archive wrapper is not implemented')
  const archive = new EvidenceArchive({ root: join(parent, 'archive'), cwd: root, sessionId: 'unbound-test' })
  t.after(() => archive.close())
  archive.ingest([execution(snapshot)])
  archive.setSynchronized(true)
  const adapter = live.withLiveState(archive, config)
  const claim = await adapter.bindClaim(proposal(), { target: 'current_workspace' })
  const result = await check(claim, null, adapter)
  assert.equal(result.outcome, 'abstain')
  assert.equal(result.trace[0].bindingIssue, 'unbound_execution_source')
})
