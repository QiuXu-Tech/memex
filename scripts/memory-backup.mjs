/**
 * Backup / verify / restore for the extra-context memory store.
 *
 * The store is a SQLite index plus markdown files (hot: records/<ws>/,
 * cold: cold/<ws>/). A backup copies all three pieces and a sha256 manifest;
 * verify re-hashes everything; restore copies a verified backup into a fresh
 * root (refusing to overwrite a non-empty target without --force).
 *
 * Usage (from the subsystem root; test register provides host resolution):
 *   node --import ./test/register.mjs scripts/memory-backup.mjs backup [--out DIR]
 *   node --import ./test/register.mjs scripts/memory-backup.mjs verify --dir DIR
 *   node --import ./test/register.mjs scripts/memory-backup.mjs restore --dir DIR --to ROOT [--force]
 */
import { cpSync, existsSync, mkdirSync, readdirSync, readFileSync, rmSync, statSync, writeFileSync } from 'node:fs'
import { createHash } from 'node:crypto'
import { isAbsolute, join, relative, resolve, sep } from 'node:path'
import { DatabaseSync } from 'node:sqlite'
import { recoverFileTransactions } from '../packages/memex-core/lib/file-transactions.js'

const HOME = process.env.HOME
const DEFAULT_ROOT = join(HOME, '.dsh', 'memories')
const arg = (name, fallback) => {
  const index = process.argv.indexOf(`--${name}`)
  return index >= 0 && process.argv[index + 1] !== undefined && !process.argv[index + 1].startsWith('--') ? process.argv[index + 1] : fallback
}
const has = (flag) => process.argv.includes(`--${flag}`)
const command = process.argv[2] ?? 'backup'
const sha256 = (path) => createHash('sha256').update(readFileSync(path)).digest('hex')
const within = (parent, child) => {
  const path = relative(resolve(parent), resolve(child))
  return path === '' || (!isAbsolute(path) && path !== '..' && !path.startsWith('..' + sep))
}
const walk = (dir) => {
  const files = []
  const visit = (current) => {
    for (const entry of readdirSync(current, { withFileTypes: true })) {
      const path = join(current, entry.name)
      if (entry.isDirectory()) visit(path)
      else files.push(path)
    }
  }
  visit(dir)
  return files
}
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms))

if (command === 'backup') {
  const root = resolve(arg('root', DEFAULT_ROOT))
  const out = resolve(arg('out', join(HOME, '.dsh', 'memory-backups', new Date().toISOString().replace(/[:.]/g, '-'))))
  if (within(root, out)) throw new Error('backup output must be outside the source store')
  if (!existsSync(join(root, 'index.db'))) {
    console.error('no memory database at ' + join(root, 'index.db'))
    process.exit(1)
  }
  mkdirSync(out, { recursive: true })
  const lock = new DatabaseSync(join(root, 'index.db'))
  try {
    lock.exec('PRAGMA busy_timeout = 5000')
    lock.exec('BEGIN IMMEDIATE')
    try {
      // Hold the same writer lock as record mutations while taking the SQLite
      // snapshot and copying files; finish any interrupted file transaction.
      recoverFileTransactions(root, lock)
      const snapshot = new DatabaseSync(join(root, 'index.db'))
      try {
        snapshot.exec("VACUUM INTO '" + join(out, 'index.db').replaceAll("'", "''") + "'")
      } finally {
        snapshot.close()
      }
      for (const directory of ['records', 'cold', '.file-recovery']) {
        if (existsSync(join(root, directory))) cpSync(join(root, directory), join(out, directory), { recursive: true })
      }
      const files = walk(out).filter((path) => !path.endsWith('manifest.json'))
      const manifest = {
        format: 1,
        createdAt: new Date().toISOString(),
        sourceRoot: root,
        db: { path: 'index.db', sha256: sha256(join(out, 'index.db')) },
        files: files.map((path) => ({ path: relative(out, path), sha256: sha256(path) })),
      }
      writeFileSync(join(out, 'manifest.json'), JSON.stringify(manifest, null, 2) + '\n')
      lock.exec('COMMIT')
      console.log('backup: ' + out + ' (' + files.length + ' files, db ' + (statSync(join(out, 'index.db')).size / 1024).toFixed(0) + ' KiB)')
    } catch (error) {
      try { lock.exec('ROLLBACK') } catch {}
      throw error
    }
  } finally {
    lock.close()
  }
  process.exit(0)
}

if (command === 'verify') {
  const dir = arg('dir')
  if (!existsSync(join(dir, 'manifest.json'))) {
    console.error(`no manifest in ${dir}`)
    process.exit(1)
  }
  const manifest = JSON.parse(readFileSync(join(dir, 'manifest.json'), 'utf8'))
  let checked = 0
  for (const entry of manifest.files) {
    const path = join(dir, entry.path)
    if (!existsSync(path) || sha256(path) !== entry.sha256) {
      console.error(`verify FAILED: ${entry.path}`)
      process.exit(1)
    }
    checked += 1
  }
  console.log(`verify: OK (${checked} files, ${manifest.files.length} in manifest, created ${manifest.createdAt})`)
  process.exit(0)
}

if (command === 'restore') {
  const dir = resolve(arg('dir'))
  const to = resolve(arg('to'))
  if (!existsSync(join(dir, 'manifest.json'))) {
    console.error('no manifest in ' + dir)
    process.exit(1)
  }
  const manifest = JSON.parse(readFileSync(join(dir, 'manifest.json'), 'utf8'))
  if (within(dir, to) || within(to, dir)) throw new Error('restore FAILED: backup and target paths overlap')
  for (const entry of manifest.files) {
    const source = resolve(dir, entry.path)
    if (!within(dir, source)) throw new Error('restore FAILED: backup file path escapes the backup')
    if (!existsSync(source) || sha256(source) !== entry.sha256) {
      console.error('restore FAILED: backup file ' + entry.path + ' is missing or corrupt')
      process.exit(1)
    }
  }
  if (existsSync(to) && readdirSync(to).length > 0 && !has('force')) {
    console.error('restore target ' + to + ' is not empty; pass --force to overwrite')
    process.exit(1)
  }
  if (typeof manifest.sourceRoot !== 'string' || !isAbsolute(manifest.sourceRoot)) {
    throw new Error('restore FAILED: backup source root is missing or not absolute')
  }
  const manifestFiles = new Set(manifest.files.map((entry) => entry.path))
  const snapshot = new DatabaseSync(join(dir, 'index.db'), { readOnly: true })
  let records
  try {
    records = snapshot.prepare('SELECT id, path FROM records').all().map((row) => {
      if (!isAbsolute(row.path)) throw new Error('restore FAILED: record path is not absolute')
      const rel = relative(resolve(manifest.sourceRoot), resolve(row.path))
      if (!rel || rel === '..' || rel.startsWith('..' + sep) || isAbsolute(rel)
        || !['records', 'cold'].includes(rel.split(sep)[0])) {
        throw new Error('restore FAILED: record path is outside the source store')
      }
      if (!manifestFiles.has(rel) || !existsSync(join(dir, rel))) {
        throw new Error('restore FAILED: backup record file is missing or not in the manifest: ' + rel)
      }
      return { id: row.id, rel }
    })
  } finally {
    snapshot.close()
  }
  rmSync(to, { recursive: true, force: true })
  mkdirSync(to, { recursive: true })
  cpSync(join(dir, 'index.db'), join(to, 'index.db'))
  for (const directory of ['records', 'cold', '.file-recovery']) {
    if (existsSync(join(dir, directory))) cpSync(join(dir, directory), join(to, directory), { recursive: true })
  }
  // The snapshot stores absolute source paths. Rebase each one to the copied
  // record file, refusing paths that escape the source or do not exist.
  const db = new DatabaseSync(join(to, 'index.db'))
  try {
    db.exec('BEGIN IMMEDIATE')
    try {
      const update = db.prepare('UPDATE records SET path = ? WHERE id = ?')
      for (const record of records) {
        const target = join(to, record.rel)
        if (!existsSync(target)) throw new Error('restore FAILED: copied record file is missing: ' + record.rel)
        update.run(target, record.id)
      }
      db.exec('COMMIT')
    } catch (error) {
      try { db.exec('ROLLBACK') } catch {}
      throw error
    }
  } finally {
    db.close()
  }
  console.log('restore: ' + dir + ' -> ' + to + ' (' + manifest.files.length + ' files, source snapshot sha256 ' + manifest.db.sha256.slice(0, 12) + '…)')
  process.exit(0)
}

console.error(`unknown command "${command}" (expected backup | verify | restore)`)
process.exit(1)
