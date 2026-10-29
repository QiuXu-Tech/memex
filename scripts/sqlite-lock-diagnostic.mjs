#!/usr/bin/env node
// Reproduce archiveCold contention using a disposable synthetic store.
// Run with Node 24+: node --import ./test/register.mjs scripts/sqlite-lock-diagnostic.mjs
import { spawn } from 'node:child_process'
import { once } from 'node:events'
import { createHash } from 'node:crypto'
import { existsSync, mkdtempSync, readFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { performance } from 'node:perf_hooks'
import { pathToFileURL } from 'node:url'

const { LocalStoreCore } = await import(pathToFileURL(join(process.cwd(), 'packages/memex-core/lib/store.js')))

const root = mkdtempSync(join(tmpdir(), 'memex-lock-diagnostic-'))
const store = new LocalStoreCore({ root, capacityTokens: 100000, defaultLevels: { l2: false, l3: false } })
const card = store.write({ kind: 'fact', title: 'Lock test', summary: 'synthetic summary',
  body: 'Synthetic body preserved across lock contention.', workspaceKey: 'test-lock', scope: 'workspace' })
const db = store.database()
const row = db.prepare('SELECT id, path, workspace_key, cold FROM records WHERE id = ?').get(card.id)
const sha = (data) => createHash('sha256').update(data).digest('hex')
const originalHash = sha(readFileSync(row.path))
const target = join(root, 'cold', row.workspace_key, `${row.id}.md`)
const childSource = `import { DatabaseSync } from 'node:sqlite';
const db = new DatabaseSync(process.argv[1]); db.exec('BEGIN IMMEDIATE');
process.stdout.write('LOCKED\\n');
process.stdin.once('data', () => { db.exec('ROLLBACK'); db.close(); process.exit(0); });`
const child = spawn(process.execPath, ['--input-type=module', '-e', childSource, join(root, 'index.db')],
  { stdio: ['pipe', 'pipe', 'pipe'] })
let stderr = ''
child.stderr.on('data', (data) => { stderr += data })
let timer
try {
  await Promise.race([
    once(child.stdout, 'data').then(([data]) => { if (String(data).trim() !== 'LOCKED') throw Error('Unexpected lock handshake') }),
    once(child, 'exit').then(() => { throw Error('Lock holder exited before handshake: ' + stderr) }),
    new Promise((_, reject) => { timer = setTimeout(() => reject(Error('Lock handshake timed out')), 10000) }),
  ])
  clearTimeout(timer)
  const started = performance.now()
  let error = null
  try { store.archiveCold(card.id) } catch (cause) {
    error = { code: cause.code, sqliteCode: cause.errcode, message: cause.errstr ?? cause.message }
  }
  const elapsedMs = Math.round(performance.now() - started)
  const after = db.prepare('SELECT path, cold FROM records WHERE id = ?').get(card.id)
  const result = {
    sqliteBusyTimeoutMs: db.prepare('PRAGMA busy_timeout').get().timeout,
    error, elapsedMs,
    indexedBodyExistsAfterFailure: existsSync(after.path),
    databaseStillMarksHot: after.cold === 0,
    coldBodyMatchesOriginalAfterFailure: existsSync(target) && sha(readFileSync(target)) === originalHash,
  }
  child.stdin.end('release')
  const [exitCode] = await once(child, 'exit')
  result.lockHolderExitCode = exitCode
  result.readFallsBackToSummary = store.get(card.id)?.body === 'synthetic summary'
  // This retry only touches the synthetic store created by this script.
  store.archiveCold(card.id)
  result.coldBodyBytesAfterRetry = existsSync(target) ? readFileSync(target).length : null
  result.originalBodyPreservedAfterRetry = existsSync(target) && sha(readFileSync(target)) === originalHash
  result.fixtureDirectory = root
  console.log(JSON.stringify(result, null, 2))
} finally {
  clearTimeout(timer)
  if (child.exitCode === null) child.kill()
  store.close()
}
