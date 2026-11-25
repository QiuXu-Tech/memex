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
import { chmodSync, cpSync, existsSync, lstatSync, mkdirSync, mkdtempSync, readdirSync, readFileSync, renameSync, statSync, unlinkSync, writeFileSync } from 'node:fs'
import { createHash, randomUUID } from 'node:crypto'
import { basename, dirname, isAbsolute, join, relative, resolve, sep } from 'node:path'
import { DatabaseSync } from 'node:sqlite'
import { recoverFileTransactions } from '../packages/memex-core/lib/file-transactions.js'
import { acquireStoreLease, storeCoordinationRoot } from '../packages/memex-core/lib/store-lease.js'

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

/** Byte integrity and database/reference restorability are checked separately. */
function validateBackup(dir) {
  const manifest = JSON.parse(readFileSync(join(dir, 'manifest.json'), 'utf8'))
  if (manifest.format !== 1 || !Array.isArray(manifest.files) || manifest.files.length === 0
    || typeof manifest.sourceRoot !== 'string' || !isAbsolute(manifest.sourceRoot)
    || manifest.db?.path !== 'index.db') throw new Error('backup FAILED: unsupported or incomplete manifest')
  const entries = new Map()
  for (const entry of manifest.files) {
    if (typeof entry.path !== 'string' || isAbsolute(entry.path) || !entry.path || entries.has(entry.path)
      || relative(dir, resolve(dir, entry.path)) !== entry.path || !/^[a-f0-9]{64}$/.test(entry.sha256)) throw new Error('backup FAILED: invalid manifest file')
    if (entry.path !== 'index.db' && !['records', 'cold', '.file-recovery'].includes(entry.path.split(sep)[0])) throw new Error('backup FAILED: unsupported manifest file: ' + entry.path)
    const file = resolve(dir, entry.path)
    if (!within(dir, file) || !lstatSync(file).isFile() || sha256(file) !== entry.sha256) throw new Error('backup FAILED: missing, unsafe or corrupt file: ' + entry.path)
    entries.set(entry.path, entry)
  }
  if (entries.get('index.db')?.sha256 !== manifest.db.sha256) throw new Error('backup FAILED: required database entry is missing or inconsistent')
  const actual = walk(dir).map(file => relative(dir, file)).filter(file => file !== 'manifest.json')
  if (actual.length !== entries.size || actual.some(file => !entries.has(file))) throw new Error('backup FAILED: file list is incomplete')
  if (actual.some(file => file.startsWith('.file-transactions' + sep))) throw new Error('backup FAILED: unresolved recovery journals need manual review')
  const db = new DatabaseSync(join(dir, 'index.db'), { readOnly: true })
  try {
    if (db.prepare('PRAGMA integrity_check').all().some(row => row.integrity_check !== 'ok')) throw new Error('backup FAILED: database integrity check')
    const records = db.prepare('SELECT id, path FROM records').all().map(row => {
      if (!isAbsolute(row.path)) throw new Error('backup FAILED: record path is not absolute')
      const rel = relative(resolve(manifest.sourceRoot), resolve(row.path))
      if (!rel || !['records', 'cold'].includes(rel.split(sep)[0])) throw new Error('restore FAILED: record path is outside the source store')
      if (!entries.has(rel)) throw new Error('backup FAILED: record body is missing from manifest')
      return { id: row.id, rel }
    })
    return { manifest, records }
  } finally { db.close() }
}

if (command === 'backup') {
  const root = resolve(arg('root', DEFAULT_ROOT))
  const out = resolve(arg('out', join(HOME, '.dsh', 'memory-backups', new Date().toISOString().replace(/[:.]/g, '-'))))
  const source = storeCoordinationRoot(root), destination = storeCoordinationRoot(out)
  if (within(source, destination) || within(destination, source)) throw new Error('backup output must be outside the source store and must not contain it')
  if (existsSync(out) && readdirSync(out).length > 0) throw new Error('backup output must be empty')
  const releaseLease = acquireStoreLease(root)
  process.once('exit', releaseLease)
  if (existsSync(storeCoordinationRoot(root) + '.restore-lock')) throw new Error('backup FAILED: complete interrupted restore recovery first')
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
      const files = walk(out).filter((path) => path !== join(out, 'manifest.json'))
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
  const dir = resolve(arg('dir'))
  try {
    const { manifest, records } = validateBackup(dir)
    console.log(`verify: OK; integrity OK (${manifest.files.length} files); restorability OK (${records.length} record references); format ${manifest.format}`)
  } catch (error) {
    console.error('verify FAILED: ' + error.message)
    process.exit(1)
  }
  process.exit(0)
}

if (command === 'restore') {
  const dir = resolve(arg('dir'))
  const requestedTarget = resolve(arg('to'))
  if (existsSync(requestedTarget) && lstatSync(requestedTarget).isSymbolicLink()) throw new Error('restore FAILED: target must be a directory, not a symlink')
  const to = storeCoordinationRoot(requestedTarget)
  const source = storeCoordinationRoot(dir)
  if (within(source, to) || within(to, source)) throw new Error('restore FAILED: backup and target paths overlap')
  const releaseLease = acquireStoreLease(to, { exclusive: true, timeoutMs: 0 })
  process.once('exit', releaseLease)
  const { manifest, records } = validateBackup(dir)
  if (existsSync(to) && (!lstatSync(to).isDirectory() || lstatSync(to).isSymbolicLink())) throw new Error('restore FAILED: target must be a directory, not a symlink')
  if (existsSync(to) && readdirSync(to).length > 0 && !has('force')) {
    console.error('restore target ' + to + ' is not empty; pass --force to overwrite')
    process.exit(1)
  }
  mkdirSync(dirname(to), { recursive: true })
  const lockPath = to + '.restore-lock'
  if (existsSync(lockPath)) throw new Error('restore FAILED: an existing restore guard requires explicit recovery')
  const stage = mkdtempSync(join(dirname(to), basename(to) + '.restore-'))
  const previous = to + '.previous-' + randomUUID()
  const state = { format: 1, to, stage, previous, phase: 'preparing' }
  const saveState = () => {
    const temporary = lockPath + '.state-' + randomUUID()
    writeFileSync(temporary, JSON.stringify(state) + '\n', { flag: 'wx', mode: 0o600 })
    renameSync(temporary, lockPath)
  }
  saveState()
  try {
    cpSync(join(dir, 'index.db'), join(stage, 'index.db'))
    chmodSync(join(stage, 'index.db'), 0o600)
    for (const directory of ['records', 'cold', '.file-recovery']) {
      if (existsSync(join(dir, directory))) cpSync(join(dir, directory), join(stage, directory), { recursive: true })
    }
    for (const entry of manifest.files) {
      if (sha256(join(stage, entry.path)) !== entry.sha256) throw new Error('restore FAILED: staged file checksum mismatch: ' + entry.path)
    }
    const db = new DatabaseSync(join(stage, 'index.db'))
    try {
      db.exec('BEGIN IMMEDIATE')
      const update = db.prepare('UPDATE records SET path = ? WHERE id = ?')
      for (const record of records) update.run(join(requestedTarget, record.rel), record.id)
      db.exec('COMMIT; PRAGMA wal_checkpoint(TRUNCATE)')
      if (db.prepare('PRAGMA integrity_check').all().some(row => row.integrity_check !== 'ok')) throw new Error('restore FAILED: staged database integrity')
    } finally { db.close() }
    // Refuse an active writer. All Memex processes must be stopped for restore;
    // the sibling guard also blocks new Store operations during the exchange.
    if (existsSync(join(to, 'index.db'))) {
      const old = new DatabaseSync(join(to, 'index.db'))
      try { old.exec('PRAGMA busy_timeout = 0; BEGIN IMMEDIATE; ROLLBACK') } finally { old.close() }
    }
    state.phase = 'prepared'; saveState()
    if (existsSync(to)) renameSync(to, previous)
    state.phase = 'previous-retained'; saveState()
    renameSync(stage, to)
    state.phase = 'installed'; saveState()
    unlinkSync(lockPath)
  } catch (error) {
    // Leave the staged candidate and previous state for explicit recovery.
    if (!existsSync(to) && existsSync(previous)) renameSync(previous, to)
    if (existsSync(to) && existsSync(stage)) unlinkSync(lockPath)
    error.message += `; staged data preserved at ${stage}; recovery: node scripts/memory-backup.mjs recover --to ${JSON.stringify(to)}`
    throw error
  }
  console.log('restore: ' + dir + ' -> ' + to + '; previous state retained at ' + previous + ' (' + manifest.files.length + ' files)')
  process.exit(0)
}

if (command === 'recover') {
  const to = storeCoordinationRoot(arg('to')), lockPath = to + '.restore-lock'
  const releaseLease = acquireStoreLease(to, { exclusive: true, timeoutMs: 0 })
  process.once('exit', releaseLease)
  let state
  try { state = JSON.parse(readFileSync(lockPath, 'utf8')) } catch (error) {
    if (error?.code === 'ENOENT') { console.log('restore recovery: no guard remains'); process.exit(0) }
    if (!(error instanceof SyntaxError)) throw error
    if (!existsSync(to)) throw new Error('restore recovery: incomplete guard and absent target; inspect retained previous/staged directories; nothing was changed')
    if (existsSync(join(to, 'index.db'))) {
      const db = new DatabaseSync(join(to, 'index.db'), { readOnly: true })
      try {
        if (db.prepare('PRAGMA integrity_check').all().some(row => row.integrity_check !== 'ok')) throw new Error('restore recovery: incomplete guard and damaged target; nothing was changed')
        for (const row of db.prepare('SELECT path FROM records').all()) if (!within(to, storeCoordinationRoot(row.path)) || !existsSync(row.path)) throw new Error('restore recovery: incomplete guard and missing body; nothing was changed')
      } finally { db.close() }
    } else if (['records', 'cold', '.file-transactions', '.file-recovery'].some(directory => existsSync(join(to, directory)) && walk(join(to, directory)).length > 0)) {
      throw new Error('restore recovery: archive files exist without their matching database; nothing was changed')
    }
    unlinkSync(lockPath)
    console.log('restore recovery: inactive incomplete guard cleared; existing target and candidates retained')
    process.exit(0)
  }
  if (state.format !== 1 || state.to !== to || dirname(state.stage) !== dirname(to) || !basename(state.stage).startsWith(basename(to) + '.restore-')
    || dirname(state.previous) !== dirname(to) || !basename(state.previous).startsWith(basename(to) + '.previous-')) throw new Error('restore recovery: invalid state')
  if (!existsSync(to) && existsSync(state.previous)) renameSync(state.previous, to)
  if (existsSync(to) && !existsSync(state.stage)) {
    const db = new DatabaseSync(join(to, 'index.db'), { readOnly: true })
    try {
      if (db.prepare('PRAGMA integrity_check').all().some(row => row.integrity_check !== 'ok')) throw new Error('restore recovery: database integrity failed')
      for (const row of db.prepare('SELECT path FROM records').all()) {
        if (!within(to, storeCoordinationRoot(row.path)) || !existsSync(row.path)) throw new Error('restore recovery: record reference failed')
      }
    } finally { db.close() }
  } else if (!existsSync(to) && state.phase !== 'preparing' && state.phase !== 'prepared') {
    throw new Error('restore recovery: target missing; staged and previous states preserved')
  }
  unlinkSync(lockPath)
  console.log('restore recovery: guard cleared; candidate and previous directories retained for review')
  process.exit(0)
}

console.error(`unknown command "${command}" (expected backup | verify | restore)`)
process.exit(1)
