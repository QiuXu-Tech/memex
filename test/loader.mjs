/**
 * ESM loader for the offline harness.
 *
 * Two jobs, both dependency-free:
 *  - redirect the DSH host packages (`@deepseek-ai/*`) to the stubs in
 *    `./stubs/`;
 *  - resolve this repo's own packages (`@qiuxu/dsh-memory-*`) directly to
 *    `packages/<name>/index.js`, so the harness needs no `node_modules`
 *    and no workspace-linking step (the bundle build creates its own
 *    internal @qiuxu links for runtime use).
 *
 * `shortCircuit: true` tells Node not to continue resolution after a redirect.
 */

/** Map bare specifier -> stub module URL. */
/** Map `@qiuxu/dsh-memory-*` package names to their source entries. */
const LOCAL_PACKAGES = {
  '@qiuxu/dsh-memory': new URL('../packages/dsh-memory/index.js', import.meta.url).href,
  '@qiuxu/dsh-memory-core': new URL('../packages/dsh-memory-core/index.js', import.meta.url).href,
  '@qiuxu/dsh-memory-core/store': new URL('../packages/dsh-memory-core/lib/store.js', import.meta.url).href,
  '@qiuxu/dsh-memory-core/model-profiles': new URL('../packages/dsh-memory-core/lib/model-profiles.js', import.meta.url).href,
  '@qiuxu/dsh-memory-core/manual': new URL('../packages/dsh-memory-core/lib/manual.js', import.meta.url).href,
  '@qiuxu/dsh-memory-core/engine': new URL('../packages/dsh-memory-core/lib/engine.js', import.meta.url).href,
  '@qiuxu/dsh-memory-seam': new URL('../packages/dsh-memory-seam/index.js', import.meta.url).href,
  '@qiuxu/dsh-memory-local': new URL('../packages/dsh-memory-local/index.js', import.meta.url).href,
  '@qiuxu/dsh-memory-checkpoint': new URL('../packages/dsh-memory-checkpoint/index.js', import.meta.url).href,
  '@qiuxu/dsh-memory-tool': new URL('../packages/dsh-memory-tool/index.js', import.meta.url).href,
  '@qiuxu/dsh-memory-command': new URL('../packages/dsh-memory-command/index.js', import.meta.url).href,
  '@qiuxu/dsh-memory-api': new URL('../packages/dsh-memory-api/index.js', import.meta.url).href,
  '@qiuxu/dsh-memory-ui': new URL('../packages/dsh-memory-ui/index.js', import.meta.url).href,
  '@qiuxu/dsh-memory-evict': new URL('../packages/dsh-memory-evict/index.js', import.meta.url).href,
  '@qiuxu/dsh-memory-compress': new URL('../packages/dsh-memory-compress/index.js', import.meta.url).href,
  // Bundle subpath exports point at the generated modules (run scripts/build-bundle.mjs first).
  '@qiuxu/dsh-memory/core': new URL('../packages/dsh-memory/modules/memory-core/index.js', import.meta.url).href,
  '@qiuxu/dsh-memory/local': new URL('../packages/dsh-memory/modules/memory-local/index.js', import.meta.url).href,
  '@qiuxu/dsh-memory/checkpoint': new URL('../packages/dsh-memory/modules/memory-checkpoint/index.js', import.meta.url).href,
  '@qiuxu/dsh-memory/tools': new URL('../packages/dsh-memory/modules/memory-tool/index.js', import.meta.url).href,
  '@qiuxu/dsh-memory/commands': new URL('../packages/dsh-memory/modules/memory-command/index.js', import.meta.url).href,
  '@qiuxu/dsh-memory/api': new URL('../packages/dsh-memory/modules/memory-api/index.js', import.meta.url).href,
  '@qiuxu/dsh-memory/ui': new URL('../packages/dsh-memory/modules/memory-ui/index.js', import.meta.url).href,
  '@qiuxu/dsh-memory/evict': new URL('../packages/dsh-memory/modules/memory-evict/index.js', import.meta.url).href,
  '@qiuxu/dsh-memory/compress': new URL('../packages/dsh-memory/modules/memory-compress/index.js', import.meta.url).href,
}

/** Package name -> generated module directory inside the built bundle. */
const BUNDLE_RUNTIME = {
  '@qiuxu/dsh-memory-core': 'memory-core',
  '@qiuxu/dsh-memory-seam': 'memory-seam',
  '@qiuxu/dsh-memory-local': 'memory-local',
  '@qiuxu/dsh-memory-checkpoint': 'memory-checkpoint',
  '@qiuxu/dsh-memory-tool': 'memory-tool',
  '@qiuxu/dsh-memory-command': 'memory-command',
  '@qiuxu/dsh-memory-api': 'memory-api',
  '@qiuxu/dsh-memory-ui': 'memory-ui',
  '@qiuxu/dsh-memory-evict': 'memory-evict',
  '@qiuxu/dsh-memory-compress': 'memory-compress',
}

const STUBS = {
  '@deepseek-ai/cordis': new URL('./stubs/cordis.mjs', import.meta.url).href,
  '@deepseek-ai/schemastery': new URL('./stubs/schemastery.mjs', import.meta.url).href,
  '@deepseek-ai/dsh-home-paths': new URL('./stubs/dsh-home-paths.mjs', import.meta.url).href,
  '@deepseek-ai/dsh-llm': new URL('./stubs/dsh-llm.mjs', import.meta.url).href,
  '@deepseek-ai/dsh-tools': new URL('./stubs/dsh-tools.mjs', import.meta.url).href,
  '@deepseek-ai/dsh-compaction': new URL('./stubs/dsh-compaction.mjs', import.meta.url).href,
}

/**
 * Resolve hook: redirect the package's bare imports to stubs.
 * @param {string} specifier - Requested specifier.
 * @param {object} context - Node resolution context.
 * @param {Function} nextResolve - Default resolver.
 * @returns {Promise<object>} Resolution result.
 */
export async function resolve(specifier, context, nextResolve) {
  // Bundle modules carry their own copies of the sibling packages; imports
  // emitted from inside the generated bundle must resolve to those copies
  // (not to the workspace source packages), mirroring the published bundle.
  const parent = String(context.parentURL ?? '')
  const runtime = BUNDLE_RUNTIME[specifier]
  if (runtime !== undefined && parent.includes('/packages/dsh-memory/modules/')) {
    return {
      url: new URL(`../packages/dsh-memory/modules/${runtime}/index.js`, import.meta.url).href,
      format: 'module',
      shortCircuit: true,
    }
  }
  const url = STUBS[specifier] ?? LOCAL_PACKAGES[specifier]
  if (url !== undefined) {
    return { url, format: 'module', shortCircuit: true }
  }
  return nextResolve(specifier, context)
}
