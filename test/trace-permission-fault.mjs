import fs from 'node:fs'
import { syncBuiltinESMExports } from 'node:module'

fs.fchmodSync = function () {
  throw Object.assign(new Error('injected trace permission failure'), { code: 'EACCES' })
}
syncBuiltinESMExports()
