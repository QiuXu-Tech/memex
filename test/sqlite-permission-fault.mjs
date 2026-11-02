import fs from 'node:fs'
import { syncBuiltinESMExports } from 'node:module'

const original = fs.chmodSync
fs.chmodSync = function (path, mode) {
  if (String(path).endsWith('/index.db')) throw Object.assign(new Error('injected permission failure'), { code: 'EACCES' })
  return original.call(this, path, mode)
}
syncBuiltinESMExports()
