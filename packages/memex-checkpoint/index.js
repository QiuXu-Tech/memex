/**
 * `@qiuxu/memex/checkpoint` — compaction checkpoint policy plugin row.
 *
 * Depends on the `memory` service row (backend) and owns everything time- and
 * prompt-shaped: archiving the region compaction shadowed, the checkpoint
 * receipt, the catalog message, auto-recall and resume reconciliation.
 *
 * @module @qiuxu/memex-checkpoint
 */
import z from '@deepseek-ai/schemastery'
import { registerCheckpointPolicy } from './lib/checkpoint.js'

export const name = 'memory-checkpoint'

export const inject = ['memory']

export const Config = z.object({
  /** Archive every compaction into this workspace's memory. */
  autoArchive: z.boolean().default(true),
  /** Inject pointer cards recalled from the current user message. */
  autoRecall: z.boolean().default(true),
  /** Maximum characters of catalog injected into one message. */
  catalogMaxChars: z.number().step(1).min(600).default(2400),
  /** Maximum characters of one auto-recall message. */
  recallMaxChars: z.number().step(1).min(200).default(600),
  /** `auto` asks the routed model for higher-quality cards; `off` keeps deterministic cards. */
  cardModel: z.string().default('auto'),
  /** Hot-pool usage ratio at which the model is told to ask the user about compression. */
  capacityNoticeRatio: z.number().min(0.05).max(0.99).default(0.8),
  /** Minimum time between capacity notices for one session, in ms. */
  capacityNoticeCooldownMs: z.number().step(1).min(1000).default(10 * 60 * 1000),
})

export function apply(ctx, config = {}) {
  const resolved = {
    autoArchive: config.autoArchive ?? true,
    autoRecall: config.autoRecall ?? true,
    catalogMaxChars: config.catalogMaxChars ?? 2400,
    recallMaxChars: config.recallMaxChars ?? 600,
    cardModel: config.cardModel ?? 'auto',
    capacityNoticeRatio: config.capacityNoticeRatio ?? 0.8,
    capacityNoticeCooldownMs: config.capacityNoticeCooldownMs ?? 10 * 60 * 1000,
  }
  if (resolved.cardModel !== 'auto' && resolved.cardModel !== 'off') {
    throw new TypeError(`memory-checkpoint: cardModel must be "auto" or "off", got ${JSON.stringify(resolved.cardModel)}`)
  }
  if (!resolved.autoArchive) return
  const policy = registerCheckpointPolicy(ctx, ctx.memory, resolved)
  ctx.effect(() => () => policy.dispose())
}
