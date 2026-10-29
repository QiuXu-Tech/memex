/**
 * Copy-on-write record files coordinated with SQLite's writer lock.
 *
 * A manifest is written before a new file is installed. The old file remains
 * readable until the database commits its new path. On restart, the indexed
 * path decides whether to finish cleanup or preserve a rolled-back staged file.
 * This handles process interruption; it does not claim power-loss durability.
 */
import {
  constants, copyFileSync, existsSync, linkSync, mkdirSync, readFileSync,
  readdirSync, renameSync, rmdirSync, statSync, unlinkSync, writeFileSync,
} from 'node:fs'
import { basename, dirname, isAbsolute, join, relative, resolve, sep } from 'node:path'
import { createHash, randomUUID } from 'node:crypto'

const JOURNALS = '.file-transactions'
const RECOVERY = '.file-recovery'

function insideRoot(root, path) {
  if (path === null || path === undefined) return null
  const resolved = resolve(path)
  const rel = relative(resolve(root), resolved)
  if (!rel || rel === '..' || rel.startsWith('..' + sep) || isAbsolute(rel)) {
    throw new Error('memory: record path is outside its store root: ' + path)
  }
  return resolved
}

function recordPath(root, path, id) {
  const resolved = insideRoot(root, path)
  if (resolved === null) return null
  const parts = relative(resolve(root), resolved).split(sep)
  if (!['records', 'cold'].includes(parts[0]) || basename(resolved) !== String(id) + '.md') {
    throw new Error('memory: invalid record file path: ' + path)
  }
  return resolved
}

function hashFile(path) {
  return createHash('sha256').update(readFileSync(path)).digest('hex')
}

function statOrMissing(path) {
  try { return statSync(path) } catch (error) {
    if (error?.code === 'ENOENT') return undefined
    throw error
  }
}

function unlinkIfPresent(path) {
  try { unlinkSync(path) } catch (error) {
    if (error?.code !== 'ENOENT') throw error
  }
}

function removeEmptyRevision(path) {
  const directory = dirname(path)
  if (basename(dirname(directory)) !== '.revisions') return
  if (!/^[0-9a-f-]{36}$/i.test(basename(directory))) return
  try { rmdirSync(directory) } catch (error) {
    if (!['ENOENT', 'ENOTEMPTY'].includes(error?.code)) throw error
  }
}

function sameFile(first, second) {
  const a = statOrMissing(first)
  const b = statOrMissing(second)
  return a !== undefined && b !== undefined && a.ino !== 0 && b.ino !== 0 && a.dev === b.dev && a.ino === b.ino
}

function preserve(root, opId, path, label) {
  if (statOrMissing(path) === undefined) return
  const directory = join(root, RECOVERY, opId)
  mkdirSync(directory, { recursive: true, mode: 0o700 })
  let target = join(directory, label)
  if (existsSync(target)) target = join(directory, label + '-' + randomUUID())
  renameSync(path, target)
}

function writeManifest(directory, manifest) {
  const temporary = join(directory, 'manifest.tmp')
  writeFileSync(temporary, JSON.stringify(manifest) + '\n', { mode: 0o600 })
  renameSync(temporary, join(directory, 'manifest.json'))
}

function mayCopy(error) {
  return ['EXDEV', 'ENOTSUP', 'EOPNOTSUPP', 'EPERM', 'ENOSYS'].includes(error?.code)
}

function copyOrLink(source, target) {
  try { linkSync(source, target) } catch (error) {
    if (!mayCopy(error)) throw error
    copyFileSync(source, target, constants.COPYFILE_EXCL)
  }
}

function versionPath(preferred, opId) {
  const parent = join(dirname(preferred), '.revisions')
  mkdirSync(parent, { recursive: true, mode: 0o700 })
  const directory = join(parent, opId)
  mkdirSync(directory, { mode: 0o700 })
  return join(directory, basename(preferred))
}

function installStage(directory, manifest) {
  const stage = join(directory, 'stage.md')
  mkdirSync(dirname(manifest.newPath), { recursive: true, mode: 0o700 })
  try {
    linkSync(stage, manifest.newPath)
  } catch (error) {
    if (!mayCopy(error)) throw error
    // A private, unique directory makes a copied target distinguishable from
    // a pre-existing external file if the process stops during the copy.
    if (!manifest.ownedTarget) {
      manifest.newPath = versionPath(manifest.newPath, manifest.opId)
      manifest.ownedTarget = true
      writeManifest(directory, manifest)
    }
    copyFileSync(stage, manifest.newPath, constants.COPYFILE_EXCL)
  }
  return manifest.newPath
}

function referenced(db, path) {
  return path !== null && db.prepare('SELECT 1 AS found FROM records WHERE path = ? LIMIT 1').get(path) !== undefined
}

/**
 * Reconcile manifests while holding BEGIN IMMEDIATE. Never remove an unknown
 * file or overwrite an existing target; failed write content is preserved.
 */
export function recoverFileTransactions(root, db) {
  const journalRoot = join(root, JOURNALS)
  if (!existsSync(journalRoot)) return
  for (const entry of readdirSync(journalRoot, { withFileTypes: true })) {
    if (!entry.isDirectory()) continue
    const directory = join(journalRoot, entry.name)
    const manifestPath = join(directory, 'manifest.json')
    if (!existsSync(manifestPath)) continue // an interrupted manifest write has not installed a record file
    const manifest = JSON.parse(readFileSync(manifestPath, 'utf8'))
    if (manifest.version !== 1 || manifest.opId !== entry.name || !/^[0-9a-f-]{36}$/i.test(entry.name)
      || !['write', 'move', 'delete'].includes(manifest.kind) || typeof manifest.id !== 'string') {
      throw new Error('memory: invalid file transaction manifest: ' + manifestPath)
    }
    const oldPath = recordPath(root, manifest.oldPath, manifest.id)
    const newPath = recordPath(root, manifest.newPath, manifest.id)
    if ((manifest.kind === 'delete') !== (newPath === null) || (manifest.kind === 'move' && oldPath === null)) {
      throw new Error('memory: invalid file transaction paths: ' + manifestPath)
    }
    if (manifest.ownedTarget && newPath !== null) {
      const parts = relative(resolve(root), newPath).split(sep)
      const revision = parts.lastIndexOf('.revisions')
      if (revision < 0 || parts[revision + 1] !== manifest.opId) {
        throw new Error('memory: invalid owned transaction target: ' + manifestPath)
      }
    }
    const stage = join(directory, 'stage.md')
    const row = db.prepare('SELECT path FROM records WHERE id = ?').get(manifest.id)
    const committed = manifest.kind === 'delete' ? row === undefined : row?.path === newPath

    if (committed) {
      if (newPath !== null && statOrMissing(newPath) === undefined) {
        if (statOrMissing(stage) === undefined) throw new Error('memory: committed record file is missing: ' + newPath)
        mkdirSync(dirname(newPath), { recursive: true, mode: 0o700 })
        copyOrLink(stage, newPath)
      }
      if (oldPath !== null && oldPath !== newPath && !referenced(db, oldPath) && statOrMissing(oldPath) !== undefined) {
        if (manifest.oldHash === null || hashFile(oldPath) !== manifest.oldHash) {
          preserve(root, manifest.opId, oldPath, 'changed-old.md')
        } else {
          unlinkIfPresent(oldPath)
        }
        removeEmptyRevision(oldPath)
      }
      unlinkIfPresent(stage)
    } else {
      if (newPath !== null && !referenced(db, newPath) && statOrMissing(newPath) !== undefined) {
        if (sameFile(stage, newPath)) unlinkIfPresent(newPath)
        else if (manifest.ownedTarget) preserve(root, manifest.opId, newPath, 'uncommitted-target.md')
        // A non-owned, different file may have been created by another actor.
      }
      if (manifest.ownedTarget && newPath !== null) removeEmptyRevision(newPath)
      if (statOrMissing(stage) !== undefined) {
        if (manifest.kind === 'write' || oldPath === null || statOrMissing(oldPath) === undefined) {
          preserve(root, manifest.opId, stage, 'uncommitted-stage.md')
        } else {
          unlinkIfPresent(stage)
        }
      }
    }
    unlinkIfPresent(manifestPath)
    unlinkIfPresent(join(directory, 'manifest.tmp'))
    try { rmdirSync(directory) } catch (error) {
      if (!['ENOENT', 'ENOTEMPTY'].includes(error?.code)) throw error
    }
  }
}

function createChange(root, kind, id, oldPath, preferred, text) {
  const opId = randomUUID()
  oldPath = recordPath(root, oldPath, id)
  preferred = recordPath(root, preferred, id)
  const oldHash = oldPath !== null && statOrMissing(oldPath) !== undefined ? hashFile(oldPath) : null
  const journalRoot = join(root, JOURNALS)
  mkdirSync(journalRoot, { recursive: true, mode: 0o700 })
  const directory = join(journalRoot, opId)
  mkdirSync(directory, { mode: 0o700 })
  let newPath = preferred
  let ownedTarget = false
  if (preferred !== null && existsSync(preferred)) {
    newPath = versionPath(preferred, opId)
    ownedTarget = true
  }
  const manifest = { version: 1, opId, kind, id, oldPath, oldHash, newPath, ownedTarget }
  writeManifest(directory, manifest)
  if (kind === 'delete') return { path: null }
  const stage = join(directory, 'stage.md')
  if (kind === 'write') {
    writeFileSync(stage, text, { mode: 0o600, flag: 'wx' })
  } else {
    if (oldPath === null || statOrMissing(oldPath) === undefined) {
      throw new Error('memory: record file missing; original and candidate files were preserved: ' + oldPath)
    }
    copyOrLink(oldPath, stage)
  }
  return { path: installStage(directory, manifest) }
}

function reportCleanup(onCleanupError, error) {
  try { onCleanupError?.(error) } catch {}
}

function recoverWithLock(root, db) {
  db.exec('BEGIN IMMEDIATE')
  try {
    recoverFileTransactions(root, db)
    db.exec('COMMIT')
  } catch (error) {
    try { db.exec('ROLLBACK') } catch {}
    throw error
  }
}

/** Run a single file-backed record mutation, serialized across processes. */
export function withFileTransaction(root, db, work, onCleanupError) {
  db.exec('BEGIN IMMEDIATE')
  let staged = false
  let result
  try {
    recoverFileTransactions(root, db)
    const stage = (kind, id, oldPath, preferred, text) => {
      staged = true
      return createChange(root, kind, id, oldPath, preferred, text)
    }
    result = work(stage)
    db.exec('COMMIT')
  } catch (error) {
    try { db.exec('ROLLBACK') } catch {}
    if (staged) {
      try { recoverWithLock(root, db) } catch (recoveryError) {
        reportCleanup(onCleanupError, recoveryError)
      }
    }
    throw error
  }
  if (staged) {
    try { recoverWithLock(root, db) } catch (error) {
      // The database and new file are committed; leave the manifest for the
      // next writer/open rather than reporting failure after a successful commit.
      reportCleanup(onCleanupError, error)
    }
  }
  return result
}

/** Recover a prior interrupted mutation on open, when any journal exists. */
export function recoverOnOpen(root, db) {
  const directory = join(root, JOURNALS)
  if (existsSync(directory) && readdirSync(directory).some((entry) => entry !== '.DS_Store')) {
    recoverWithLock(root, db)
  }
}
