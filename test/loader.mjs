/**
 * ESM loader for the offline harness.
 *
 * Two jobs, both dependency-free:
 *  - redirect the DSH host packages (`@deepseek-ai/*`) to the stubs in
 *    `./stubs/`;
 *  - resolve this repo's own packages (`@qiuxu/memex-*`) directly to
 *    `packages/<name>/index.js`, so the harness needs no `node_modules`
 *    and no workspace-linking step (the bundle build creates its own
 *    internal @qiuxu links for runtime use).
 *
 * `shortCircuit: true` tells Node not to continue resolution after a redirect.
 */

/** Map bare specifier -> stub module URL. */
/** Map `@qiuxu/memex-*` package names to their source entries. */
const LOCAL_PACKAGES = {
  '@qiuxu/memex': new URL('../packages/memex/index.js', import.meta.url).href,
  '@qiuxu/memex-core': new URL('../packages/memex-core/index.js', import.meta.url).href,
  '@qiuxu/memex-core/store': new URL('../packages/memex-core/lib/store.js', import.meta.url).href,
  '@qiuxu/memex-core/model-profiles': new URL('../packages/memex-core/lib/model-profiles.js', import.meta.url).href,
  '@qiuxu/memex-core/manual': new URL('../packages/memex-core/lib/manual.js', import.meta.url).href,
  '@qiuxu/memex-core/engine': new URL('../packages/memex-core/lib/engine.js', import.meta.url).href,
  '@qiuxu/memex-seam': new URL('../packages/memex-seam/index.js', import.meta.url).href,
  '@qiuxu/memex-local': new URL('../packages/memex-local/index.js', import.meta.url).href,
  '@qiuxu/memex-checkpoint': new URL('../packages/memex-checkpoint/index.js', import.meta.url).href,
  '@qiuxu/memex-tool': new URL('../packages/memex-tool/index.js', import.meta.url).href,
  '@qiuxu/memex-command': new URL('../packages/memex-command/index.js', import.meta.url).href,
  '@qiuxu/memex-api': new URL('../packages/memex-api/index.js', import.meta.url).href,
  '@qiuxu/memex-ui': new URL('../packages/memex-ui/index.js', import.meta.url).href,
  '@qiuxu/memex-evict': new URL('../packages/memex-evict/index.js', import.meta.url).href,
  '@qiuxu/memex-compress': new URL('../packages/memex-compress/index.js', import.meta.url).href,
  // Bundle subpath exports point at the generated modules (run scripts/build-bundle.mjs first).
  '@qiuxu/memex/core': new URL('../packages/memex/modules/memory-core/index.js', import.meta.url).href,
  '@qiuxu/memex/local': new URL('../packages/memex/modules/memory-local/index.js', import.meta.url).href,
  '@qiuxu/memex/checkpoint': new URL('../packages/memex/modules/memory-checkpoint/index.js', import.meta.url).href,
  '@qiuxu/memex/tools': new URL('../packages/memex/modules/memory-tool/index.js', import.meta.url).href,
  '@qiuxu/memex/commands': new URL('../packages/memex/modules/memory-command/index.js', import.meta.url).href,
  '@qiuxu/memex/api': new URL('../packages/memex/modules/memory-api/index.js', import.meta.url).href,
  '@qiuxu/memex/ui': new URL('../packages/memex/modules/memory-ui/index.js', import.meta.url).href,
  '@qiuxu/memex/evict': new URL('../packages/memex/modules/memory-evict/index.js', import.meta.url).href,
  '@qiuxu/memex/compress': new URL('../packages/memex/modules/memory-compress/index.js', import.meta.url).href,
}

/** Package name -> generated module directory inside the built bundle. */
const BUNDLE_RUNTIME = {
  '@qiuxu/memex-core': 'memory-core',
  '@qiuxu/memex-seam': 'memory-seam',
  '@qiuxu/memex-local': 'memory-local',
  '@qiuxu/memex-checkpoint': 'memory-checkpoint',
  '@qiuxu/memex-tool': 'memory-tool',
  '@qiuxu/memex-command': 'memory-command',
  '@qiuxu/memex-api': 'memory-api',
  '@qiuxu/memex-ui': 'memory-ui',
  '@qiuxu/memex-evict': 'memory-evict',
  '@qiuxu/memex-compress': 'memory-compress',
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
  if (runtime !== undefined && parent.includes('/packages/memex/modules/')) {
    return {
      url: new URL(`../packages/memex/modules/${runtime}/index.js`, import.meta.url).href,
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
