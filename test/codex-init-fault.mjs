import fs from 'node:fs'
import { syncBuiltinESMExports } from 'node:module'

const original = fs.writeFileSync
fs.writeFileSync = function (path, data, options) {
  const name = String(path)
  if (name.endsWith('/config.toml') || name.includes('/.memex-codex-config.toml-')) {
    original.call(this, path, String(data).slice(0, 8), options)
    throw new Error('injected partial Codex configuration write')
  }
  return original.call(this, path, data, options)
}
syncBuiltinESMExports()
