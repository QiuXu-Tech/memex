/**
 * `@qiuxu/dsh-memory/tools` — model-facing memory tools and the static manual.
 *
 * Depends on the `memory` service row and registers five tools plus one stable
 * system-prompt section. The section deliberately never changes at runtime; the
 * changing index lives in the bounded catalog message from the checkpoint row.
 *
 * @module @qiuxu/dsh-memory-tool
 */
import z from '@deepseek-ai/schemastery'
import { MEMORY_MANUAL, registerMemoryTools } from './lib/tools.js'

export const name = 'memory-tools'

export const inject = ['tools', 'systemPrompt', 'memory']

export const Config = z.object({
  /** Maximum characters one tool result may inline before it is clipped with a pointer. */
  maxInlineChars: z.number().step(1).min(400).default(14_000),
})

/** Prompt position: after file-reference guidance (900), before shell-tool guidance (1000). */
const SECTION_ORDER = 950

export function apply(ctx, config = {}) {
  ctx.systemPrompt.section({
    name: 'tool:memory',
    order: SECTION_ORDER,
    text: MEMORY_MANUAL,
  })
  registerMemoryTools(ctx, ctx.memory, { maxInlineChars: config.maxInlineChars ?? 14_000 })
}
