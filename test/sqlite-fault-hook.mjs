// Test-only fault injection at file-install and SQLite commit boundaries.
import fs from 'node:fs'
import { syncBuiltinESMExports } from 'node:module'
import { DatabaseSync } from 'node:sqlite'

const fault = process.env.MEMEX_TEST_FAULT
let armed = false
const stop = () => process.kill(process.pid, 'SIGKILL')
const normalized = (path) => String(path).replace(/\\/g, '/')
const stageFile = (path) => normalized(path).endsWith('/stage.md')
const targetFile = (path) => normalized(path).endsWith('.md') && !normalized(path).includes('/.file-transactions/')

const write = fs.writeFileSync
fs.writeFileSync = function(path, ...args) {
  const result = write.call(this, path, ...args)
  if (stageFile(path) && fault === 'after-stage') stop()
  if (stageFile(path) && fault === 'throw-after-stage') throw new Error('test: interrupted after staging')
  return result
}
const link = fs.linkSync
fs.linkSync = function(source, target) {
  if (fault === 'no-hardlink' || fault === 'no-hardlink-after-target') {
    const error = new Error('test: hard links unavailable')
    error.code = 'ENOTSUP'
    throw error
  }
  if (targetFile(target) && fault === 'race-target') {
    write.call(fs, target, 'external file must survive', { flag: 'wx' })
  }
  const result = link.call(this, source, target)
  if (stageFile(target) && fault === 'after-stage') stop()
  if (stageFile(target) && fault === 'throw-after-stage') throw new Error('test: interrupted after staging')
  if (targetFile(target)) {
    armed = true
    if (fault === 'after-target') stop()
    if (fault === 'throw-after-target') throw new Error('test: interrupted after file installation')
  }
  return result
}
const copy = fs.copyFileSync
fs.copyFileSync = function(source, target, ...args) {
  const result = copy.call(this, source, target, ...args)
  if (targetFile(target) && fault === 'no-hardlink-after-target') stop()
  return result
}
const unlink = fs.unlinkSync
fs.unlinkSync = function(path) {
  if (targetFile(path) && fault === 'throw-cleanup-unlink') {
    const error = new Error('test: cleanup temporarily unavailable')
    error.code = 'EIO'
    throw error
  }
  const result = unlink.call(this, path)
  if (targetFile(path) && fault === 'during-recovery') stop()
  return result
}
const rename = fs.renameSync
fs.renameSync = function(source, target) {
  const result = rename.call(this, source, target)
  if (normalized(target).endsWith('/manifest.json') && normalized(target).includes('/.file-transactions/')) {
    armed = true
    if (fault === 'after-journal') stop()
  }
  return result
}
syncBuiltinESMExports()

const exec = DatabaseSync.prototype.exec
DatabaseSync.prototype.exec = function(sql) {
  const result = exec.call(this, sql)
  if (sql === 'COMMIT' && armed && fault === 'after-commit') stop()
  if (sql === 'COMMIT' && armed && fault === 'throw-after-commit') {
    throw new Error('test: commit acknowledgement lost')
  }
  return result
}
