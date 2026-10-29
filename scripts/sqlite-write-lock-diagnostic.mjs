#!/usr/bin/env node
// Test an update under contention in a disposable synthetic store.
import { spawn } from 'node:child_process'
import { once } from 'node:events'
import { mkdtempSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { pathToFileURL } from 'node:url'

const { LocalStoreCore } = await import(pathToFileURL(join(process.cwd(), 'packages/memex-core/lib/store.js')))

const root = mkdtempSync(join(tmpdir(), 'memex-write-lock-diagnostic-'))
const store = new LocalStoreCore({ root, capacityTokens: 100000, defaultLevels: { l2: false, l3: false } })
const card = store.write({ kind: 'fact', title: 'Lock test', summary: 'old summary',
  body: 'OLD synthetic body', workspaceKey: 'test-lock', scope: 'workspace' })
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
  let error = null
  try {
    store.write({ id: card.id, kind: 'fact', title: 'Lock test', summary: 'new summary',
      body: 'NEW synthetic body', workspaceKey: 'test-lock', scope: 'workspace' })
  } catch (cause) { error = { code: cause.code, sqliteCode: cause.errcode, message: cause.errstr ?? cause.message } }
  child.stdin.end('release')
  const [exitCode] = await once(child, 'exit')
  const actual = store.get(card.id)
  console.log(JSON.stringify({ error, lockHolderExitCode: exitCode, storedSummary: actual.summary,
    bodyChangedDespiteFailedWrite: actual.body === 'NEW synthetic body', fixtureDirectory: root }, null, 2))
} finally {
  clearTimeout(timer)
  if (child.exitCode === null) child.kill()
  store.close()
}
