/** Cross-process lease outside the directory that restore exchanges. */
import { DatabaseSync } from 'node:sqlite'
import { chmodSync, closeSync, lstatSync, mkdirSync, openSync, readlinkSync, realpathSync, statSync } from 'node:fs'
import { basename, dirname, join, resolve } from 'node:path'

/** Resolve existing aliases, including the parent of a not-yet-created root. */
export function storeCoordinationRoot(root) {
  const absolute = resolve(root)
  try { return realpathSync(absolute) } catch (error) {
    if (error.code !== 'ENOENT' || dirname(absolute) === absolute) throw error
    if (lstatSync(absolute, { throwIfNoEntry: false })?.isSymbolicLink()) return storeCoordinationRoot(resolve(dirname(absolute), readlinkSync(absolute)))
    return join(storeCoordinationRoot(dirname(absolute)), basename(absolute))
  }
}

export function acquireStoreLease(root, { exclusive = false, timeoutMs = 5000 } = {}) {
  const file = storeCoordinationRoot(root) + '.store-lease.sqlite'
  mkdirSync(dirname(file), { recursive: true, mode: 0o700 })
  closeSync(openSync(file, 'a', 0o600))
  if (process.platform !== 'win32') chmodSync(file, statSync(file).mode & ~0o077)
  const db = new DatabaseSync(file)
  try {
    db.exec(`PRAGMA busy_timeout = ${Math.max(0, Math.floor(timeoutMs))}`)
    if (db.prepare('PRAGMA journal_mode').get().journal_mode !== 'delete') throw new Error('memory: store lease requires rollback-journal mode')
    db.exec('CREATE TABLE IF NOT EXISTS lease_marker (version INTEGER)')
    db.exec(exclusive ? 'BEGIN EXCLUSIVE' : 'BEGIN; SELECT count(*) FROM lease_marker')
  } catch (error) {
    db.close()
    throw error
  }
  let released = false
  return () => {
    if (released) return
    released = true
    try { db.exec('ROLLBACK') } finally { db.close() }
  }
}
