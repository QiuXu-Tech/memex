import fs from 'node:fs'
import { syncBuiltinESMExports } from 'node:module'

const original = fs.writeFileSync
fs.writeFileSync = function (path, data, options) {
  const name = String(path)
  if (name.endsWith('/.mcp.json') || name.includes('/.memex-init-')) {
    original.call(this, path, String(data).slice(0, 8), options)
    throw new Error('injected partial configuration write')
  }
  return original.call(this, path, data, options)
}
syncBuiltinESMExports()
