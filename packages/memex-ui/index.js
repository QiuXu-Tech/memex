/**
 * `@qiuxu/memex-ui` — Host entry for the memory panel's client half.
 *
 * The row exists only so the Web client module graph has an enabled Loader entry
 * to attach `dsh.client` to; it registers nothing on the Host. In the local
 * deployment the bundle addresses this module by a `file:` URL (see
 * packages/memex/cordis.patch.yml): DSH's client-modules host half
 * attributes a subpath specifier to the outer bundle manifest, so the row must
 * resolve directly to this package root. Upstream mounts the published package
 * by its bare name instead.
 *
 * @module @qiuxu/memex-ui
 */
export const name = 'memory-ui'

export function apply() {}
