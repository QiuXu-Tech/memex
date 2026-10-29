/**
 * Offline stub for `@deepseek-ai/dsh-home-paths`.
 *
 * The real helper resolves paths under the user's DSH home (`~/.dsh`). Tests
 * must never write there, so the stub joins everything under a throwaway temp
 * directory supplied through `DSH_STUB_HOME`. The path is resolved lazily so
 * the runner can set the env var before the package creates its store.
 */
import { join } from 'node:path'
import { tmpdir } from 'node:os'
import { mkdirSync } from 'node:fs'

/** @returns {string} The test-only DSH home root. */
export function stubHome() {
  return process.env.DSH_STUB_HOME ?? join(tmpdir(), `dsh-memory-stub-home-${process.pid}`)
}

/**
 * Resolve a path under the test-only DSH home.
 * @param {...string} segments - Path segments, e.g. `('memories')`.
 * @returns {string} Absolute path under the stub home.
 */
export function dshHomePath(...segments) {
  const root = stubHome()
  mkdirSync(root, { recursive: true })
  return join(root, ...segments.map(String))
}

export default { dshHomePath, stubHome }
