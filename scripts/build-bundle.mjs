/**
 * Build the self-contained runtime modules of the `@qiuxu/dsh-memory` bundle.
 *
 * The subsystem's source is nine sibling packages under `packages/` (the
 * upstream-shaped layout). A DSH profile installs one linked bundle, and Node
 * module resolution for a linked package does not install that package's local
 * dependencies, so the bundle must carry its runtime modules itself.
 *
 * This script copies each source package into `packages/dsh-memory/modules/`
 * (keeping its package.json, so peer declarations stay visible to the host's
 * linked-package resolver) and links the package names under
 * `packages/dsh-memory/node_modules/@qiuxu/`. The resulting paths live inside
 * the linked bundle root, which is exactly what the host's resolver requires to
 * route `@deepseek-ai/*` imports of those modules to the installation copy.
 *
 * The bundle patch addresses the modules through the bundle's own subpath
 * exports (`@qiuxu/dsh-memory/local`, …), so a row's module is `./modules/...`
 * and everything it imports stays inside the same linked root.
 *
 * Usage: node scripts/build-bundle.mjs
 */
import { cpSync, mkdirSync, readFileSync, rmSync, symlinkSync, writeFileSync, existsSync } from 'node:fs'
import { join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const here = resolve(fileURLToPath(new URL('..', import.meta.url)))
const packages = join(here, 'packages')
const bundle = join(packages, 'dsh-memory')
const modules = join(bundle, 'modules')
const bundleNodeModules = join(bundle, 'node_modules', '@qiuxu')

/** Source package directory → runtime module directory inside the bundle. */
const MODULES = [
  ['dsh-memory-core', 'memory-core'],
  ['dsh-memory-seam', 'memory-seam'],
  ['dsh-memory-local', 'memory-local'],
  ['dsh-memory-checkpoint', 'memory-checkpoint'],
  ['dsh-memory-tool', 'memory-tool'],
  ['dsh-memory-command', 'memory-command'],
  ['dsh-memory-api', 'memory-api'],
  ['dsh-memory-ui', 'memory-ui'],
  ['dsh-memory-evict', 'memory-evict'],
  ['dsh-memory-compress', 'memory-compress'],
]

/**
 * Copy one package's runtime files (no tests, no node_modules, no docs).
 *
 * The generated manifest drops `dependencies`: they point at sibling *source*
 * directories that do not exist in this layout, and runtime resolution inside
 * the bundle goes through `bundle/node_modules/@qiuxu/*` links instead. Peer
 * declarations are kept — the host's linked-package resolver reads them to
 * route `@deepseek-ai/*` imports to the installation copy.
 */
function copyRuntime(from, to) {
  mkdirSync(to, { recursive: true })
  for (const entry of ['index.js', 'lib', 'package.json', 'client.js']) {
    const source = join(from, entry)
    if (!existsSync(source)) continue
    cpSync(source, join(to, entry), {
      recursive: true,
      filter: (path) => !path.includes('/node_modules/') && !path.endsWith('.test.js'),
    })
  }
  const manifestPath = join(to, 'package.json')
  if (existsSync(manifestPath)) {
    const manifest = JSON.parse(readFileSync(manifestPath, 'utf8'))
    delete manifest.dependencies
    writeFileSync(manifestPath, `${JSON.stringify(manifest, null, 2)}\n`)
  }
}

rmSync(modules, { recursive: true, force: true })
rmSync(bundleNodeModules, { recursive: true, force: true })
mkdirSync(modules, { recursive: true })
mkdirSync(bundleNodeModules, { recursive: true })

for (const [source, runtime] of MODULES) {
  const from = join(packages, source)
  if (!existsSync(join(from, 'package.json'))) throw new Error(`missing source package: ${from}`)
  copyRuntime(from, join(modules, runtime))
  // `bundle/node_modules/@qiuxu/<full-name>` → `bundle/modules/<runtime>`; both
  // ends live inside the linked bundle root.
  symlinkSync(`../../modules/${runtime}`, join(bundleNodeModules, source), 'dir')
}

writeFileSync(join(modules, '.gitignore'), '*\n')
console.log(`bundle modules built: ${MODULES.map(([, runtime]) => runtime).join(', ')}`)
console.log(`bundle root: ${bundle}`)
