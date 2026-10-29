/**
 * `@qiuxu/memex/commands` — human `/memory` command row.
 *
 * Optional by composition: when no `commands` service is mounted the plugin
 * does nothing, so the same bundle works in headless and minimal deployments.
 *
 * @module @qiuxu/memex-command
 */
import { registerMemoryCommands } from './lib/commands.js'

export const name = 'memory-commands'

export const inject = ['memory']

export function apply(ctx) {
  const dispose = registerMemoryCommands(ctx, ctx.memory)
  // The command registry scopes its own registrations to the calling fiber when
  // it can, but keep the returned disposer under the plugin's effect so
  // unloading this row can never leave a stale `/memory` command behind.
  if (typeof dispose === 'function') ctx.effect(() => dispose)
}
