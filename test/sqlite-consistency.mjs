import test from 'node:test'
import assert from 'node:assert/strict'
import { spawn, spawnSync } from 'node:child_process'
import { once } from 'node:events'
import { existsSync, mkdtempSync, readFileSync, readdirSync, renameSync, mkdirSync, rmSync, unlinkSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { isAbsolute, join, relative, sep } from 'node:path'
import { fileURLToPath } from 'node:url'
import { performance } from 'node:perf_hooks'
import { DatabaseSync } from 'node:sqlite'
import { createHash } from 'node:crypto'
import { LocalStoreCore } from '../packages/memex-core/lib/store.js'

async function withStore(fn) {
  const root = mkdtempSync(join(tmpdir(), 'memex-consistency-test-'))
  const store = new LocalStoreCore({ root, capacityTokens: 100000, defaultLevels: { l2: false, l3: false } })
  try {
    await fn(store, root)
    store.close()
    rmSync(root, { recursive: true, force: true })
  } catch (error) {
    store.close()
    error.message += ` (fixture retained: ${root})`
    throw error
  }
}

async function withWriteLock(store, fn) {
  store.database().exec('PRAGMA busy_timeout = 0')
  const source = `import { DatabaseSync } from 'node:sqlite';
    const db = new DatabaseSync(process.argv[1]); db.exec('BEGIN IMMEDIATE');
    process.stdout.write('READY\\n');
    process.stdin.once('data', () => { db.exec('ROLLBACK'); db.close(); process.exit(0) })`
  const child = spawn(process.execPath, ['--input-type=module', '-e', source, join(store.root, 'index.db')],
    { stdio: ['pipe', 'pipe', 'pipe'] })
  let stderr = ''
  child.stderr.on('data', (chunk) => { stderr += chunk })
  try {
    const [ready] = await once(child.stdout, 'data')
    assert.equal(String(ready).trim(), 'READY', stderr)
    await fn()
  } finally {
    child.stdin.end('release')
    const [status] = await once(child, 'exit')
    assert.equal(status, 0, stderr)
  }
}

const busy = (error) => error?.code === 'ERR_SQLITE_ERROR' && error?.errcode === 5
const write = (store, body = 'original body') => store.write({
  kind: 'fact', title: 'Concurrency fixture', summary: 'original summary',
  body, workspaceKey: 'wk-lock', scope: 'workspace',
})

test('a blocked update never changes the existing body or metadata', async () => {
  await withStore(async (store) => {
    const card = write(store)
    const before = readFileSync(card.path, 'utf8')
    await withWriteLock(store, async () => {
      assert.throws(() => store.write({ ...card, body: 'replacement body', summary: 'replacement summary' }), busy)
      assert.equal(readFileSync(card.path, 'utf8'), before)
    })
    assert.equal(store.get(card.id).body, 'original body')
    assert.equal(store.get(card.id).summary, 'original summary')
  })
})

test('a blocked new write leaves no unindexed record file', async () => {
  await withStore(async (store, root) => {
    write(store)
    const directory = join(root, 'records', 'wk-lock')
    const before = readdirSync(directory).sort()
    await withWriteLock(store, async () => {
      assert.throws(() => write(store, 'another body'), busy)
      assert.deepEqual(readdirSync(directory).sort(), before)
    })
    assert.equal(store.list({ workspaceKey: 'wk-lock' }).length, 1)
  })
})

test('a blocked archive leaves the hot body intact and a retry preserves it', async () => {
  await withStore(async (store) => {
    const card = write(store)
    await withWriteLock(store, async () => {
      assert.throws(() => store.archiveCold(card.id), busy)
      assert.equal(store.get(card.id).body, 'original body')
      assert.ok(existsSync(card.path))
    })
    store.archiveCold(card.id)
    assert.equal(store.get(card.id).body, 'original body')
    assert.equal(store.get(card.id).cold, true)
  })
})

test('a blocked restore and cold GC leave the cold body intact', async () => {
  await withStore(async (store) => {
    const card = write(store)
    const cold = store.archiveCold(card.id)
    await withWriteLock(store, async () => {
      assert.throws(() => store.restoreCold(card.id), busy)
      assert.ok(existsSync(cold.path))
      assert.throws(() => store.gcCold({ workspaceKey: 'wk-lock', keepTokens: 0 }), busy)
      assert.ok(existsSync(cold.path))
    })
    assert.equal(store.get(card.id).body, 'original body')
    assert.equal(store.get(card.id).cold, true)
  })
})

test('a legacy missing hot path never overwrites an existing cold file on retry', async () => {
  await withStore(async (store, root) => {
    const card = write(store)
    const coldDir = join(root, 'cold', 'wk-lock')
    mkdirSync(coldDir, { recursive: true })
    const coldPath = join(coldDir, `${card.id}.md`)
    renameSync(card.path, coldPath)
    const before = readFileSync(coldPath, 'utf8')
    assert.throws(() => store.get(card.id), /missing|unreadable/i)
    assert.throws(() => store.archiveCold(card.id), /missing|ENOENT/i)
    assert.equal(readFileSync(coldPath, 'utf8'), before)
    assert.equal(store.database().prepare('SELECT cold, path FROM records WHERE id = ?').get(card.id).path, card.path)
  })
})

test('an existing unrelated cold target is not overwritten', async () => {
  await withStore(async (store, root) => {
    const card = write(store)
    const coldDir = join(root, 'cold', 'wk-lock')
    mkdirSync(coldDir, { recursive: true })
    const existing = join(coldDir, card.id + '.md')
    writeFileSync(existing, 'unrelated file')
    const archived = store.archiveCold(card.id)
    assert.notEqual(archived.path, existing)
    assert.equal(readFileSync(existing, 'utf8'), 'unrelated file')
    assert.equal(store.get(card.id).body, 'original body')
  })
})

const worker = fileURLToPath(new URL('./sqlite-worker.mjs', import.meta.url))
const hook = fileURLToPath(new URL('./sqlite-fault-hook.mjs', import.meta.url))
function runWorker(action, root, id, fault) {
  return spawnSync(process.execPath, ['--import', hook, worker, action, root, id], {
    encoding: 'utf8', timeout: 15000, env: { ...process.env, MEMEX_TEST_FAULT: fault },
  })
}
function noPending(root) {
  const directory = join(root, '.file-transactions')
  if (!existsSync(directory)) return true
  return readdirSync(directory, { withFileTypes: true })
    .filter((entry) => entry.isDirectory())
    .every((entry) => !existsSync(join(directory, entry.name, 'manifest.json')))
}
function reopen(root) {
  return new LocalStoreCore({ root, capacityTokens: 100000, defaultLevels: { l2: false, l3: false } })
}
function isWithin(root, path) {
  const rel = relative(root, path)
  return rel !== '' && rel !== '..' && !rel.startsWith('..' + sep) && !isAbsolute(rel)
}

test('interrupted updates recover the old or committed new body and metadata', async () => {
  for (const fault of ['after-stage', 'after-target', 'after-commit']) {
    await withStore(async (store, root) => {
      const card = write(store)
      store.close()
      const child = runWorker('update', root, card.id, fault)
      assert.equal(child.signal, 'SIGKILL', child.stderr)
      const recovered = reopen(root)
      try {
        const record = recovered.get(card.id)
        const committed = fault === 'after-commit'
        assert.equal(record.body, committed ? 'new body and summary' : 'original body')
        assert.equal(record.summary, committed ? 'new body and summary' : 'original summary')
        const query = committed ? 'new body and summary' : 'original summary'
        assert.ok(recovered.search({ query, workspaceKey: 'wk-lock' }).hits.some((hit) => hit.id === card.id))
        assert.ok(existsSync(record.path))
        assert.ok(noPending(root))
        if (!committed) {
          const retained = join(root, '.file-recovery')
          assert.ok(existsSync(retained), 'the interrupted replacement is retained separately')
        }
      } finally { recovered.close() }
    })
  }
})

test('an interrupted new record leaves no indexed or active file and retains its staged body', async () => {
  await withStore(async (store, root) => {
    write(store)
    store.close()
    const id = 'mem_newrecord0'
    const child = runWorker('update', root, id, 'after-target')
    assert.equal(child.signal, 'SIGKILL', child.stderr)
    const recovered = reopen(root)
    try {
      assert.equal(recovered.get(id), undefined)
      assert.equal(existsSync(join(root, 'records', 'wk-lock', id + '.md')), false)
      const preserved = join(root, '.file-recovery')
      assert.ok(readdirSync(preserved).some((entry) => {
        const path = join(preserved, entry, 'uncommitted-stage.md')
        return existsSync(path) && readFileSync(path, 'utf8').includes('new body and summary')
      }))
      assert.ok(noPending(root))
    } finally { recovered.close() }
  })
})

test('recovery can itself be interrupted and resumed without losing either body', async () => {
  await withStore(async (store, root) => {
    const card = write(store)
    store.close()
    const first = runWorker('update', root, card.id, 'after-target')
    assert.equal(first.signal, 'SIGKILL', first.stderr)
    const second = runWorker('read', root, card.id, 'during-recovery')
    assert.equal(second.signal, 'SIGKILL', second.stderr)
    const recovered = reopen(root)
    try {
      assert.equal(recovered.get(card.id).body, 'original body')
      assert.equal(recovered.get(card.id).summary, 'original summary')
      assert.ok(existsSync(join(root, '.file-recovery')))
      assert.ok(noPending(root))
    } finally { recovered.close() }
  })
})

test('a changed old file is preserved during recovery after commit', async () => {
  await withStore(async (store, root) => {
    const card = write(store)
    store.close()
    const child = runWorker('update', root, card.id, 'after-commit')
    assert.equal(child.signal, 'SIGKILL', child.stderr)
    writeFileSync(card.path, 'external edit after interruption')
    const recovered = reopen(root)
    try {
      assert.equal(recovered.get(card.id).body, 'new body and summary')
      const directory = join(root, '.file-recovery')
      const preserved = readdirSync(directory).map((entry) => join(directory, entry, 'changed-old.md'))
      assert.ok(preserved.some((path) => existsSync(path) && readFileSync(path, 'utf8') === 'external edit after interruption'))
      assert.ok(noPending(root))
    } finally { recovered.close() }
  })
})

test('a committed target can be restored from its staged file after interruption', async () => {
  await withStore(async (store, root) => {
    const card = write(store)
    store.close()
    const child = runWorker('update', root, card.id, 'after-commit')
    assert.equal(child.signal, 'SIGKILL', child.stderr)
    const db = new DatabaseSync(join(root, 'index.db'))
    const path = db.prepare('SELECT path FROM records WHERE id = ?').get(card.id).path
    db.close()
    unlinkSync(path)
    const recovered = reopen(root)
    try {
      assert.equal(recovered.get(card.id).body, 'new body and summary')
      assert.ok(existsSync(path))
      assert.ok(noPending(root))
    } finally { recovered.close() }
  })
})

test('missing committed and staged files are reported while the old file is preserved', async () => {
  await withStore(async (store, root) => {
    const card = write(store)
    store.close()
    const child = runWorker('update', root, card.id, 'after-commit')
    assert.equal(child.signal, 'SIGKILL', child.stderr)
    const db = new DatabaseSync(join(root, 'index.db'))
    const path = db.prepare('SELECT path FROM records WHERE id = ?').get(card.id).path
    db.close()
    unlinkSync(path)
    const directory = join(root, '.file-transactions')
    const [entry] = readdirSync(directory)
    unlinkSync(join(directory, entry, 'stage.md'))
    const recovered = reopen(root)
    try {
      assert.throws(() => recovered.get(card.id), /committed record file is missing/i)
      assert.ok(existsSync(card.path))
      assert.ok(readFileSync(card.path, 'utf8').includes('original body'))
      assert.equal(noPending(root), false)
    } finally { recovered.close() }
  })
})

test('interrupted archive and restore recover the indexed tier and original body', async () => {
  for (const action of ['archive', 'restore']) {
    for (const fault of ['after-stage', 'after-target', 'after-commit']) {
      await withStore(async (store, root) => {
        const card = write(store)
        if (action === 'restore') store.archiveCold(card.id)
        store.close()
        const child = runWorker(action, root, card.id, fault)
        assert.equal(child.signal, 'SIGKILL', child.stderr)
        const recovered = reopen(root)
        try {
          const record = recovered.get(card.id)
          const committed = fault === 'after-commit'
          assert.equal(record.body, 'original body')
          assert.equal(record.cold, action === 'archive' ? committed : !committed)
          assert.ok(existsSync(record.path))
          assert.ok(noPending(root))
        } finally { recovered.close() }
      })
    }
  }
})

test('interrupted deletion preserves a rolled-back body or finishes a committed delete', async () => {
  for (const fault of ['after-journal', 'after-commit']) {
    await withStore(async (store, root) => {
      const card = write(store)
      store.close()
      const child = runWorker('forget', root, card.id, fault)
      assert.equal(child.signal, 'SIGKILL', child.stderr)
      const recovered = reopen(root)
      try {
        const record = recovered.get(card.id)
        if (fault === 'after-commit') {
          assert.equal(record, undefined)
          assert.equal(existsSync(card.path), false)
        } else {
          assert.equal(record.body, 'original body')
          assert.ok(existsSync(card.path))
        }
        assert.ok(noPending(root))
      } finally { recovered.close() }
    })
  }
})

test('interrupted cold GC preserves a rolled-back body or finishes a committed delete', async () => {
  for (const fault of ['after-journal', 'after-commit']) {
    await withStore(async (store, root) => {
      const card = write(store)
      const cold = store.archiveCold(card.id)
      store.close()
      const child = runWorker('gc', root, card.id, fault)
      assert.equal(child.signal, 'SIGKILL', child.stderr)
      const recovered = reopen(root)
      try {
        const record = recovered.get(card.id)
        if (fault === 'after-commit') {
          assert.equal(record, undefined)
          assert.equal(existsSync(cold.path), false)
        } else {
          assert.equal(record.body, 'original body')
          assert.equal(record.cold, true)
        }
        assert.ok(noPending(root))
      } finally { recovered.close() }
    })
  }
})

test('a file-install error rolls back without losing the old body', async () => {
  await withStore(async (store, root) => {
    const card = write(store)
    store.close()
    const child = runWorker('update', root, card.id, 'throw-after-target')
    assert.notEqual(child.status, 0)
    assert.match(child.stderr, /interrupted after file installation/)
    const recovered = reopen(root)
    try {
      assert.equal(recovered.get(card.id).body, 'original body')
      assert.equal(recovered.get(card.id).summary, 'original summary')
      assert.ok(noPending(root))
    } finally { recovered.close() }
  })
})

test('a staging error preserves the previous record and the staged replacement', async () => {
  await withStore(async (store, root) => {
    const card = write(store)
    store.close()
    const child = runWorker('update', root, card.id, 'throw-after-stage')
    assert.notEqual(child.status, 0)
    assert.match(child.stderr, /interrupted after staging/)
    const recovered = reopen(root)
    try {
      assert.equal(recovered.get(card.id).body, 'original body')
      assert.ok(existsSync(join(root, '.file-recovery')))
      assert.ok(noPending(root))
    } finally { recovered.close() }
  })
})

test('a target created during installation is never overwritten or deleted', async () => {
  await withStore(async (store, root) => {
    const card = write(store)
    store.close()
    const child = runWorker('archive', root, card.id, 'race-target')
    assert.notEqual(child.status, 0)
    const recovered = reopen(root)
    try {
      assert.equal(recovered.get(card.id).body, 'original body')
      assert.equal(readFileSync(join(root, 'cold', 'wk-lock', card.id + '.md'), 'utf8'), 'external file must survive')
      assert.ok(noPending(root))
    } finally { recovered.close() }
  })
})

test('a lost commit acknowledgement can be retried without overwriting the cold body', async () => {
  await withStore(async (store, root) => {
    const card = write(store)
    store.close()
    const child = runWorker('archive', root, card.id, 'throw-after-commit')
    assert.notEqual(child.status, 0)
    assert.match(child.stderr, /commit acknowledgement lost/)
    const recovered = reopen(root)
    try {
      const before = recovered.get(card.id)
      assert.equal(before.cold, true)
      assert.equal(before.body, 'original body')
      assert.equal(recovered.archiveCold(card.id).path, before.path)
      assert.equal(recovered.get(card.id).body, 'original body')
      assert.ok(noPending(root))
    } finally { recovered.close() }
  })
})

test('a lost acknowledgement for a generated ID reports the ID for inspection', async () => {
  await withStore(async (store, root) => {
    write(store)
    store.close()
    const child = runWorker('new', root, 'unused', 'throw-after-commit')
    assert.notEqual(child.status, 0)
    const match = child.stderr.match(/record-id=(mem_[0-9a-f]{10})/)
    assert.ok(match, child.stderr)
    const recovered = reopen(root)
    try {
      assert.equal(recovered.get(match[1]).body, 'generated body')
      assert.ok(noPending(root))
    } finally { recovered.close() }
  })
})

test('a committed operation survives deferred file cleanup and is reconciled on open', async () => {
  await withStore(async (store, root) => {
    const card = write(store)
    store.close()
    const child = runWorker('update', root, card.id, 'throw-cleanup-unlink')
    assert.equal(child.status, 0, child.stderr)
    assert.equal(noPending(root), false)
    const recovered = reopen(root)
    try {
      assert.equal(recovered.get(card.id).body, 'new body and summary')
      assert.equal(recovered.get(card.id).summary, 'new body and summary')
      assert.ok(noPending(root))
    } finally { recovered.close() }
  })
})

test('an already-open instance reconciles another process before its next mutation', async () => {
  await withStore(async (store, root) => {
    const card = write(store)
    const child = runWorker('update', root, card.id, 'throw-cleanup-unlink')
    assert.equal(child.status, 0, child.stderr)
    assert.equal(noPending(root), false)
    const cold = store.archiveCold(card.id)
    assert.equal(cold.cold, true)
    assert.equal(store.get(card.id).body, 'new body and summary')
    assert.ok(noPending(root))
  })
})

test('updating a cold record preserves its tier and searchable body', async () => {
  await withStore(async (store) => {
    const card = write(store)
    store.archiveCold(card.id)
    const cold = store.get(card.id)
    store.write({ ...cold, body: 'updated cold body with INC-70891', summary: 'updated cold summary' })
    const updated = store.get(card.id)
    assert.equal(updated.cold, true)
    assert.equal(updated.body, 'updated cold body with INC-70891')
    assert.ok(store.search({ query: 'INC-70891', workspaceKey: 'wk-lock' }).hits.some((hit) => hit.id === card.id))
  })
})

test('repeated updates and deletion do not accumulate empty revision directories', async () => {
  await withStore(async (store, root) => {
    const card = write(store)
    for (let index = 0; index < 8; index += 1) {
      store.write({ ...card, body: 'revision ' + index, summary: 'revision ' + index })
    }
    const revisions = join(root, 'records', 'wk-lock', '.revisions')
    assert.ok(readdirSync(revisions).length <= 1)
    assert.equal(store.forget(card.id), true)
    assert.equal(readdirSync(revisions).length, 0)
    assert.ok(noPending(root))
  })
})

test('updating by ID keeps the original creation time in the file and database', async () => {
  await withStore(async (store) => {
    const card = write(store)
    const updated = store.write({ id: card.id, kind: 'fact', title: 'updated',
      body: 'updated body', workspaceKey: 'wk-lock', scope: 'workspace' })
    const row = store.database().prepare('SELECT created_at, path FROM records WHERE id = ?').get(card.id)
    assert.equal(updated.createdAt, card.createdAt)
    assert.equal(row.created_at, card.createdAt)
    assert.ok(readFileSync(row.path, 'utf8').includes('created_at: ' + card.createdAt))
  })
})

test('changing status of a cold record does not change its tier or body', async () => {
  await withStore(async (store) => {
    const card = write(store)
    store.archiveCold(card.id)
    store.setStatus(card.id, 'pinned')
    const result = store.get(card.id)
    assert.equal(result.status, 'pinned')
    assert.equal(result.cold, true)
    assert.equal(result.body, 'original body')
  })
})

test('a stale status update cannot overwrite a concurrent body update', async () => {
  await withStore(async (store, root) => {
    const card = write(store)
    const other = reopen(root)
    const originalGet = store.get.bind(store)
    store.get = (id) => {
      const stale = originalGet(id)
      other.write({ id, kind: 'fact', title: 'Concurrency fixture', summary: 'concurrent summary',
        body: 'concurrent body', workspaceKey: 'wk-lock', scope: 'workspace' })
      return stale
    }
    try {
      assert.throws(() => store.setStatus(card.id, 'pinned'), /record changed during update/)
      assert.equal(other.get(card.id).body, 'concurrent body')
      assert.equal(other.get(card.id).summary, 'concurrent summary')
    } finally { other.close() }
  })
})

test('backup and restore retain recovered files and open independently of the source root', async () => {
  await withStore(async (store, root) => {
    const card = write(store)
    const updated = store.write({ ...card, body: 'restorable body', summary: 'restorable summary' })
    assert.notEqual(updated.path, card.path)
    store.close()
    const interrupted = runWorker('update', root, card.id, 'after-target')
    assert.equal(interrupted.signal, 'SIGKILL', interrupted.stderr)
    const backup = mkdtempSync(join(tmpdir(), 'memex-consistency-backup-'))
    const restoredRoot = mkdtempSync(join(tmpdir(), 'memex-consistency-restore-'))
    const script = fileURLToPath(new URL('../scripts/memory-backup.mjs', import.meta.url))
    const run = (...args) => spawnSync(process.execPath, [script, ...args], { encoding: 'utf8' })
    const saved = run('backup', '--root', root, '--out', backup)
    assert.equal(saved.status, 0, saved.stderr)
    const restored = run('restore', '--dir', backup, '--to', restoredRoot)
    assert.equal(restored.status, 0, restored.stderr)
    const hidden = root + '-source-hidden'
    renameSync(root, hidden)
    try {
      const reopened = reopen(restoredRoot)
      try {
        const result = reopened.get(card.id)
        assert.equal(result.body, 'restorable body')
        assert.equal(result.summary, 'restorable summary')
        assert.ok(isWithin(restoredRoot, result.path))
        const preserved = join(restoredRoot, '.file-recovery')
        assert.ok(readdirSync(preserved).some((entry) => {
          const path = join(preserved, entry, 'uncommitted-stage.md')
          return existsSync(path) && readFileSync(path, 'utf8').includes('new body and summary')
        }))
      } finally { reopened.close() }
    } finally {
      renameSync(hidden, root)
    }
    rmSync(backup, { recursive: true, force: true })
    rmSync(restoredRoot, { recursive: true, force: true })
  })
})

test('backup while another process writes captures matching body and metadata', async () => {
  await withStore(async (store, root) => {
    const card = write(store)
    store.close()
    const backup = mkdtempSync(join(tmpdir(), 'memex-concurrent-backup-'))
    const restoredRoot = mkdtempSync(join(tmpdir(), 'memex-concurrent-restore-'))
    const script = fileURLToPath(new URL('../scripts/memory-backup.mjs', import.meta.url))
    const source = "import { DatabaseSync } from 'node:sqlite'; const db = new DatabaseSync(process.argv[1]); db.exec('BEGIN IMMEDIATE'); process.stdout.write('READY\\n'); setTimeout(() => { db.exec('ROLLBACK'); db.close() }, 350)"
    const holder = spawn(process.execPath, ['--input-type=module', '-e', source, join(root, 'index.db')],
      { stdio: ['ignore', 'pipe', 'pipe'] })
    await once(holder.stdout, 'data')
    const holderDone = once(holder, 'exit')
    const child = spawn(process.execPath, [worker, 'loop', root, card.id, 'writer'],
      { stdio: ['ignore', 'pipe', 'pipe'] })
    let stderr = ''
    child.stderr.on('data', (chunk) => { stderr += chunk })
    const done = once(child, 'exit')
    const started = performance.now()
    const saved = spawnSync(process.execPath, [script, 'backup', '--root', root, '--out', backup], { encoding: 'utf8' })
    assert.equal(saved.status, 0, saved.stderr)
    assert.ok(performance.now() - started >= 150, 'backup should wait for the held writer lock')
    const [holderStatus] = await holderDone
    assert.equal(holderStatus, 0)
    const [status] = await done
    assert.equal(status, 0, stderr)
    const restored = spawnSync(process.execPath, [script, 'restore', '--dir', backup, '--to', restoredRoot], { encoding: 'utf8' })
    assert.equal(restored.status, 0, restored.stderr)
    const recovered = reopen(restoredRoot)
    try {
      const result = recovered.get(card.id)
      assert.ok(result.body === 'original body' || result.body.startsWith('writer:'))
      assert.equal(result.summary, result.body === 'original body' ? 'original summary' : result.body)
      assert.ok(isWithin(restoredRoot, result.path))
    } finally { recovered.close() }
    rmSync(backup, { recursive: true, force: true })
    rmSync(restoredRoot, { recursive: true, force: true })
  })
})

test('restore validates record paths before touching an existing target', async () => {
  await withStore(async (store, root) => {
    const card = write(store)
    store.close()
    const backup = mkdtempSync(join(tmpdir(), 'memex-invalid-backup-'))
    const target = mkdtempSync(join(tmpdir(), 'memex-existing-target-'))
    const script = fileURLToPath(new URL('../scripts/memory-backup.mjs', import.meta.url))
    const run = (...args) => spawnSync(process.execPath, [script, ...args], { encoding: 'utf8' })
    assert.equal(run('backup', '--root', root, '--out', backup).status, 0)
    const snapshot = new DatabaseSync(join(backup, 'index.db'))
    snapshot.prepare('UPDATE records SET path = ? WHERE id = ?').run('/outside/source/record.md', card.id)
    snapshot.close()
    const manifestPath = join(backup, 'manifest.json')
    const manifest = JSON.parse(readFileSync(manifestPath, 'utf8'))
    const digest = createHash('sha256').update(readFileSync(join(backup, 'index.db'))).digest('hex')
    manifest.db.sha256 = digest
    manifest.files.find((entry) => entry.path === 'index.db').sha256 = digest
    writeFileSync(manifestPath, JSON.stringify(manifest))
    const sentinel = join(target, 'sentinel.txt')
    writeFileSync(sentinel, 'do not remove')
    const rejected = run('restore', '--dir', backup, '--to', target, '--force')
    assert.notEqual(rejected.status, 0)
    assert.match(rejected.stderr, /outside the source store/)
    assert.equal(readFileSync(sentinel, 'utf8'), 'do not remove')
    const overlap = run('restore', '--dir', backup, '--to', backup, '--force')
    assert.notEqual(overlap.status, 0)
    assert.ok(existsSync(manifestPath))
    rmSync(backup, { recursive: true, force: true })
    rmSync(target, { recursive: true, force: true })
  })
})

test('filesystems without hard links use a safe exclusive copy', async () => {
  await withStore(async (store, root) => {
    const card = write(store)
    store.close()
    const child = runWorker('update', root, card.id, 'no-hardlink')
    assert.equal(child.status, 0, child.stderr)
    const recovered = reopen(root)
    try {
      assert.equal(recovered.get(card.id).body, 'new body and summary')
      assert.equal(recovered.get(card.id).summary, 'new body and summary')
      assert.ok(noPending(root))
    } finally { recovered.close() }
  })
})

test('a copied target survives interruption without replacing the old body', async () => {
  await withStore(async (store, root) => {
    const card = write(store)
    store.close()
    const child = runWorker('update', root, card.id, 'no-hardlink-after-target')
    assert.equal(child.signal, 'SIGKILL', child.stderr)
    const recovered = reopen(root)
    try {
      assert.equal(recovered.get(card.id).body, 'original body')
      assert.equal(recovered.get(card.id).summary, 'original summary')
      assert.ok(existsSync(join(root, '.file-recovery')))
      assert.ok(noPending(root))
    } finally { recovered.close() }
  })
})

test('a malformed recovery journal blocks mutation without deleting files', async () => {
  await withStore(async (store, root) => {
    const card = write(store)
    const journal = join(root, '.file-transactions', '11111111-1111-1111-1111-111111111111')
    mkdirSync(journal, { recursive: true })
    writeFileSync(join(journal, 'manifest.json'), '{invalid')
    assert.throws(() => store.archiveCold(card.id))
    assert.ok(existsSync(card.path))
    assert.equal(readFileSync(card.path, 'utf8').includes('original body'), true)
    assert.ok(existsSync(join(journal, 'manifest.json')))
  })
})

test('a competing writer is waited for before a mutation begins', async () => {
  await withStore(async (store) => {
    const card = write(store)
    const source = "import { DatabaseSync } from 'node:sqlite'; const db = new DatabaseSync(process.argv[1]); db.exec('BEGIN IMMEDIATE'); process.stdout.write('READY\\n'); setTimeout(() => { db.exec('ROLLBACK'); db.close() }, 350)"
    const child = spawn(process.execPath, ['--input-type=module', '-e', source, join(store.root, 'index.db')],
      { stdio: ['ignore', 'pipe', 'pipe'] })
    await once(child.stdout, 'data')
    const started = performance.now()
    const result = store.write({ ...card, body: 'waited body', summary: 'waited summary' })
    const elapsed = performance.now() - started
    const [status] = await once(child, 'exit')
    assert.equal(status, 0)
    assert.ok(elapsed >= 150, 'the writer should wait for the held lock')
    assert.equal(store.get(result.id).body, 'waited body')
    assert.equal(store.get(result.id).summary, 'waited summary')
  })
})

test('concurrent processes update one record without mixing body and metadata', async () => {
  await withStore(async (store, root) => {
    const card = write(store)
    store.close()
    const start = (label) => spawn(process.execPath, [worker, 'loop', root, card.id, label],
      { stdio: ['ignore', 'pipe', 'pipe'] })
    const children = [start('first'), start('second')]
    const outputs = children.map(() => '')
    children.forEach((child, index) => child.stderr.on('data', (chunk) => { outputs[index] += chunk }))
    const exits = await Promise.all(children.map((child) => once(child, 'exit')))
    exits.forEach(([status], index) => assert.equal(status, 0, outputs[index]))
    const recovered = reopen(root)
    try {
      const record = recovered.get(card.id)
      assert.match(record.body, /^(first|second):11$/)
      assert.equal(record.summary, record.body)
      assert.ok(existsSync(record.path))
      assert.ok(noPending(root))
    } finally { recovered.close() }
  })
})

test('concurrent archive and update preserve the latest body and cold state', async () => {
  await withStore(async (store, root) => {
    const card = write(store)
    store.close()
    const start = (action) => spawn(process.execPath, [worker, action, root, card.id],
      { stdio: ['ignore', 'pipe', 'pipe'] })
    const children = [start('update'), start('archive')]
    const outputs = ['', '']
    children.forEach((child, index) => child.stderr.on('data', (chunk) => { outputs[index] += chunk }))
    const exits = await Promise.all(children.map((child) => once(child, 'exit')))
    exits.forEach(([status], index) => assert.equal(status, 0, outputs[index]))
    const recovered = reopen(root)
    try {
      const record = recovered.get(card.id)
      assert.equal(record.body, 'new body and summary')
      assert.equal(record.summary, 'new body and summary')
      assert.equal(record.cold, true)
      assert.ok(existsSync(record.path))
      assert.ok(noPending(root))
    } finally { recovered.close() }
  })
})
