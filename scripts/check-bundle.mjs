/**
 * Verify that the generated bundle modules match their source packages.
 *
 * The bundle under `packages/memex/modules/` is a copy produced by
 * `scripts/build-bundle.mjs`; editing a source package without rebuilding the
 * bundle would make the deployed rows run stale code. This check compares every
 * runtime file and exits non-zero on drift, so it can run before a redeploy.
 *
 * Usage: node scripts/check-bundle.mjs
 */
import { readFileSync, existsSync, readdirSync, statSync } from 'node:fs'
import { join, resolve, relative } from 'node:path'
import { fileURLToPath } from 'node:url'

const here = resolve(fileURLToPath(new URL('..', import.meta.url)))
const packages = join(here, 'packages')
const modules = join(packages, 'memex', 'modules')

/** Source package directory → runtime module directory inside the bundle. */
const MODULES = [
  ['memex-core', 'memory-core'],
  ['memex-seam', 'memory-seam'],
  ['memex-local', 'memory-local'],
  ['memex-checkpoint', 'memory-checkpoint'],
  ['memex-tool', 'memory-tool'],
  ['memex-command', 'memory-command'],
  ['memex-api', 'memory-api'],
  ['memex-ui', 'memory-ui'],
  ['memex-evict', 'memory-evict'],
  ['memex-compress', 'memory-compress'],
]

/** List runtime files (index.js, lib/**, package.json) of one package directory. */
function runtimeFiles(directory) {
  const files = []
  const walk = (current) => {
    for (const entry of readdirSync(current)) {
      const path = join(current, entry)
      if (statSync(path).isDirectory()) {
        if (entry === 'node_modules' || entry === 'test') continue
        walk(path)
      } else if (entry === 'index.js' || entry === 'client.js' || entry === 'package.json' || path.includes('/lib/')) {
        files.push(path)
      }
    }
  }
  walk(directory)
  return files.sort()
}

if (!existsSync(join(modules, 'memory-local'))) {
  console.error('bundle modules are not built; run: node scripts/build-bundle.mjs')
  process.exit(1)
}

/**
 * Comparable content for one runtime file.
 *
 * Generated manifests intentionally drop `dependencies` (they point at sibling
 * source directories that do not exist in the bundle layout; runtime resolution
 * uses `bundle/node_modules/@qiuxu/*` links instead), so the comparison ignores
 * that field and compares every other manifest field.
 */
function comparable(path) {
  const bytes = readFileSync(path)
  if (!path.endsWith('package.json')) return bytes
  const manifest = JSON.parse(bytes.toString('utf8'))
  delete manifest.dependencies
  return Buffer.from(JSON.stringify(manifest, null, 2))
}

let drift = 0
for (const [source, runtime] of MODULES) {
  const sourceDir = join(packages, source)
  const runtimeDir = join(modules, runtime)
  const sourceFiles = runtimeFiles(sourceDir).map((path) => relative(sourceDir, path))
  const runtimeFilesList = runtimeFiles(runtimeDir).map((path) => relative(runtimeDir, path))
  for (const file of sourceFiles) {
    const sourcePath = join(sourceDir, file)
    const runtimePath = join(runtimeDir, file)
    if (!existsSync(runtimePath)) {
      console.error(`drift: missing ${relative(here, runtimePath)} (source ${relative(here, sourcePath)} changed)`)
      drift += 1
      continue
    }
    if (!comparable(sourcePath).equals(comparable(runtimePath))) {
      console.error(`drift: ${relative(here, runtimePath)} differs from ${relative(here, sourcePath)}`)
      drift += 1
    }
  }
  for (const file of runtimeFilesList) {
    if (!sourceFiles.includes(file)) {
      console.error(`drift: stale ${relative(here, join(runtimeDir, file))} has no source counterpart`)
      drift += 1
    }
  }
}

if (drift > 0) {
  console.error(`\n${drift} drift item(s). Run: node scripts/build-bundle.mjs`)
  process.exit(1)
}
console.log('bundle modules match their source packages')
