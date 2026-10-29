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
import { join, relative } from 'node:path'
import { DatabaseSync } from 'node:sqlite'

const HOME = process.env.HOME
const DEFAULT_ROOT = join(HOME, '.dsh', 'memories')
const arg = (name, fallback) => {
  const index = process.argv.indexOf(`--${name}`)
  return index >= 0 && process.argv[index + 1] !== undefined && !process.argv[index + 1].startsWith('--') ? process.argv[index + 1] : fallback
}
const has = (flag) => process.argv.includes(`--${flag}`)
const command = process.argv[2] ?? 'backup'
const sha256 = (path) => createHash('sha256').update(readFileSync(path)).digest('hex')
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
  const root = arg('root', DEFAULT_ROOT)
  const out = arg('out', join(HOME, '.dsh', 'memory-backups', new Date().toISOString().replace(/[:.]/g, '-')))
  if (!existsSync(join(root, 'index.db'))) {
    console.error(`no memory database at ${join(root, 'index.db')}`)
    process.exit(1)
  }
  mkdirSync(out, { recursive: true })
  // VACUUM INTO produces a consistent single-file snapshot even with the live
  // plugin connected (WAL mode).
  const db = new DatabaseSync(join(root, 'index.db'))
  db.exec(`VACUUM INTO '${join(out, 'index.db').replaceAll("'", "''")}'`)
  db.close()
  for (const directory of ['records', 'cold']) {
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
  writeFileSync(join(out, 'manifest.json'), `${JSON.stringify(manifest, null, 2)}\n`)
  console.log(`backup: ${out} (${files.length} files, db ${(statSync(join(out, 'index.db')).size / 1024).toFixed(0)} KiB)`)
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
  const dir = arg('dir')
  const to = arg('to')
  if (!existsSync(join(dir, 'manifest.json'))) {
    console.error(`no manifest in ${dir}`)
    process.exit(1)
  }
  const manifest = JSON.parse(readFileSync(join(dir, 'manifest.json'), 'utf8'))
  for (const entry of manifest.files) {
    const source = join(dir, entry.path)
    if (!existsSync(source) || sha256(source) !== entry.sha256) {
      console.error(`restore FAILED: backup file ${entry.path} is missing or corrupt`)
      process.exit(1)
    }
  }
  if (existsSync(to) && readdirSync(to).length > 0 && !has('force')) {
    console.error(`restore target ${to} is not empty; pass --force to overwrite`)
    process.exit(1)
  }
  rmSync(to, { recursive: true, force: true })
  mkdirSync(to, { recursive: true })
  cpSync(join(dir, 'index.db'), join(to, 'index.db'))
  for (const directory of ['records', 'cold']) {
    if (existsSync(join(dir, directory))) cpSync(join(dir, directory), join(to, directory), { recursive: true })
  }
  console.log(`restore: ${dir} -> ${to} (${manifest.files.length} files, db sha256 ${manifest.db.sha256.slice(0, 12)}…)`)
  process.exit(0)
}

console.error(`unknown command "${command}" (expected backup | verify | restore)`)
process.exit(1)
