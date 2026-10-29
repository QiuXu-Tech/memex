/**
 * `@qiuxu/memex-evict` — L1 eviction policy row.
 *
 * When at least one extra-context cache level (L2 session-private, L3
 * workspace-shared) is enabled, this row watches step-boundary pressure and
 * moves the oldest balanced span of the native context window (L1) into the
 * enabled level's archive. The move uses the same supported seam as the shipped
 * tool-result pruner — a `compaction/prune` shadow-price event immediately
 * followed by a `surfaceOp: "replace"` user message carrying a short receipt —
 * so the session surface genuinely shrinks (`tokenMeter.measure()` drops), the
 * client gauge follows, and the shipped compaction backend no longer crosses
 * its own threshold. The replaced span is stored verbatim; nothing is
 * summarized and no LLM call is made.
 *
 * It runs in the `agent/pre-step` waterfall with `{ prepend: true }`, i.e.
 * before the automatic compaction listener, so eviction wins the race and
 * compaction stays a last-resort safety net (e.g. for context-overflow
 * recovery). Every level-off session and every pre-route step is a no-op.
 *
 * @module @qiuxu/memex-evict
 */
import z from '@deepseek-ai/schemastery'
import { toolPairingBalancedBefore } from '@deepseek-ai/dsh-compaction'
import { contentHasImage } from '@deepseek-ai/dsh-llm'
import { memoryCaptureScope, memoryMessage, memoryWorkspaceKey } from '@qiuxu/memex-seam'
import { createHash } from 'node:crypto'

export const name = 'memory-evict'

export const inject = ['memory', 'tokenMeter', 'llm']

export const Config = z.object({
  /** Fraction of the routed window above which L1 eviction runs. */
  evictAtRatio: z.number().min(0.1).max(0.95).default(0.6),
  /** Fraction of the routed window kept verbatim as the recent tail after eviction. */
  retainRatio: z.number().min(0.05).max(0.9).default(0.35),
  /** Maximum characters of one eviction batch (large spans split across steps). */
  maxChars: z.number().step(1).min(20_000).default(250_000),
  /**
   * Capture level for evicted L1 content: `deepest` follows the cache capture
   * policy (L3 wins when both levels are on); `l2` keeps eviction private to the
   * session store while L3 remains read-only for shared recall.
   */
  captureLevel: z.string().default('deepest'),
  /**
   * Sensitive-content policy for evicted L1 spans: `auto` keeps secrets out of
   * the workspace-shared L3 (forces the private L2, or skips eviction when only
   * L3 is available); `off` disables the scan.
   */
  sensitivePolicy: z.string().default('auto'),
})

/** High-confidence secret patterns; a hit keeps the batch session-private. */
const SENSITIVE_PATTERNS = [
  /-----BEGIN [A-Z ]*PRIVATE KEY-----/,
  /\b(?:sk-[A-Za-z0-9]{16,}|ghp_[A-Za-z0-9]{20,}|AKIA[A-Z0-9]{16})\b/,
  /(?:password|passwd|secret|api[_-]?key|access[_-]?token|authorization)\s*[:=]\s*["']?[^\s"']{6,}/i,
]

/** Whether a rendered batch looks like it contains credentials. */
function containsSensitive(body) {
  return SENSITIVE_PATTERNS.some((pattern) => pattern.test(body))
}

/**
 * Resolve the routed window capacity, or undefined before the first routed request.
 * @param {import('@deepseek-ai/cordis').Context} ctx - Owning context.
 * @param {object} agent - Live agent.
 * @param {AbortSignal|undefined} signal - Turn signal.
 * @returns {Promise<number|undefined>} Context window in tokens.
 */
async function resolveContextWindow(ctx, agent, signal) {
  const config = agent.session.requestHeader()?.config
  const provider = config?.provider ?? agent.options?.provider
  const model = config?.model ?? agent.options?.model
  if (typeof provider !== 'string' || provider.length === 0 || typeof model !== 'string' || model.length === 0) return undefined
  const info = await ctx.llm.resolveModelInfo(provider, model, signal)
  return info?.context?.contextWindow
}

/**
 * Serialize one surface event's derived message for the archive body.
 * Image-bearing messages are reported but never evicted: the archive is text
 * only, so dropping the image would lose content irreversibly.
 * @param {object} session - Session owning the event.
 * @param {object} event - Session event.
 * @returns {{text: string, hasImage: boolean}} Rendered block and image flag.
 */
function renderEvent(session, event) {
  let message
  try {
    message = session.deriveEventMessage(event)
  } catch {
    message = undefined
  }
  const header = `## seq ${event.seq} · ${event.type}`
  if (message === undefined) return { text: `${header}\n(no derived message)`, hasImage: false }
  let hasImage = false
  try {
    hasImage = contentHasImage(message.content ?? [])
  } catch {
    hasImage = (message.content ?? []).some((block) => typeof block?.type === 'string' && block.type.startsWith('image'))
  }
  const blocks = []
  for (const block of message.content ?? []) {
    if (block.type === 'text') blocks.push(block.text)
    else if (block.type === 'tool-call') blocks.push(`tool-call ${block.name ?? ''} ${JSON.stringify(block.arguments ?? {})}`)
    else if (block.type === 'tool-result') blocks.push(`tool-result ${JSON.stringify(block.content ?? block.output ?? '')}`)
    else blocks.push(`[${block.type}]`)
  }
  return { text: `${header}\n${blocks.join('\n')}`, hasImage }
}

/**
 * Select the oldest balanced surface span to move out of L1.
 * @param {object} session - Session whose surface is trimmed.
 * @param {{nodes: Array<{seq: number, tokens: number, heuristicTokens: number}>, totalTokens: number}} measurement - Token-meter measurement.
 * @param {number} retainTokens - Recent tail budget kept verbatim.
 * @param {number} maxChars - Character budget of one batch.
 * @returns {{start: number, end: number, shadowedSeqs: number[], shadowedTokens: number, body: string, keptBytes: number}|undefined} Selection.
 */
function selectRange(session, tokenMeter, measurement, retainTokens, maxChars) {
  const nodes = measurement.nodes
  if (nodes.length === 0) return undefined
  const head = nodes[0] === undefined ? undefined : session.eventAt(nodes[0].seq)
  const firstIdx = head?.type === 'system/message' ? 1 : 0
  let accumulated = 0
  let keepFrom = nodes.length
  for (let index = nodes.length - 1; index >= firstIdx; index -= 1) {
    accumulated += nodes[index].tokens
    keepFrom = index
    if (accumulated >= retainTokens) break
  }
  if (keepFrom <= firstIdx) return undefined
  while (keepFrom > firstIdx && !toolPairingBalancedBefore(session, nodes[keepFrom].seq)) keepFrom -= 1
  if (keepFrom <= firstIdx) return undefined
  // Walk forward from the first evictable node, bounded by the batch character budget.
  const shadowedSeqs = []
  const bodyParts = []
  let chars = 0
  for (let index = firstIdx; index < keepFrom; index += 1) {
    const node = nodes[index]
    const event = session.eventAt(node.seq)
    const rendered = renderEvent(session, event)
    // Never evict image-bearing content: the archive is text-only.
    if (rendered.hasImage) break
    // A single oversized event cannot be archived safely in one batch.
    if (rendered.text.length > maxChars) break
    if (shadowedSeqs.length > 0 && chars + rendered.text.length > maxChars) break
    shadowedSeqs.push(node.seq)
    bodyParts.push(rendered.text)
    chars += rendered.text.length
  }
  if (shadowedSeqs.length === 0) return undefined
  // Never end the range on an unbalanced cut (a split tool-call/result pair).
  while (shadowedSeqs.length > 0 && !toolPairingBalancedBefore(session, nodes[firstIdx + shadowedSeqs.length].seq)) {
    shadowedSeqs.pop()
    bodyParts.pop()
  }
  if (shadowedSeqs.length === 0) return undefined
  // Shadow price must use the same metric the surface projection prices the
  // replacement with (estimateMessage), or the O(1) gauge would drift.
  let shadowedTokens = 0
  for (const seq of shadowedSeqs) {
    const event = session.eventAt(seq)
    let message
    try {
      message = session.deriveEventMessage(event)
    } catch {
      message = undefined
    }
    if (message !== undefined) shadowedTokens += tokenMeter.estimateMessage(message)
  }
  return {
    start: shadowedSeqs[0],
    end: shadowedSeqs[shadowedSeqs.length - 1],
    shadowedSeqs,
    shadowedTokens,
    body: bodyParts.join('\n\n'),
  }
}

/**
 * Move one batch of L1 context into the enabled extra-context level.
 * @param {import('@deepseek-ai/cordis').Context} ctx - Owning context.
 * @param {object} agent - Live agent.
 * @param {AbortSignal|undefined} signal - Turn signal.
 * @param {object} policy - Resolved config.
 * @returns {Promise<any>} Eviction result or undefined.
 */
async function evictOnce(ctx, agent, signal, policy) {
  const session = agent.session
  const levels = await ctx.memory.getLevels(session.id)
  let scope = policy.captureLevel === 'l2' && levels.l2 === true ? 'session' : memoryCaptureScope(levels)
  if (scope === undefined) return undefined
  const contextWindow = await resolveContextWindow(ctx, agent, signal)
  if (typeof contextWindow !== 'number' || contextWindow <= 0) return undefined
  const measurement = ctx.tokenMeter.measure(session)
  const threshold = Math.floor(contextWindow * policy.evictAtRatio)
  if (measurement.totalTokens < threshold) return undefined
  const retainTokens = Math.floor(contextWindow * policy.retainRatio)
  const selection = selectRange(session, ctx.tokenMeter, measurement, retainTokens, policy.maxChars)
  if (selection === undefined) return undefined

  // Sensitive spans never reach the workspace-shared tier.
  if (policy.sensitivePolicy !== 'off' && containsSensitive(selection.body)) {
    if (levels.l2 === true) {
      scope = 'session'
    } else {
      ctx.logger.warn('memory-evict: skipped eviction (sensitive content and only L3 is enabled)')
      return undefined
    }
  }

  // 1. Archive verbatim FIRST: never evict context the store failed to keep.
  const cwd = session.header?.cwd
  const workspaceKey = memoryWorkspaceKey(cwd, session.id)
  const hash = createHash('sha256').update(`${session.id}\u0000${selection.start}\u0000${selection.end}`).digest('hex').slice(0, 10)
  const recordId = `l1_${hash}`
  const levelLabel = scope === 'workspace' ? 'L3（工作区共享）' : 'L2（本会话私有）'
  const record = await ctx.memory.write({
    id: recordId,
    kind: 'episode',
    title: `L1 归档 ${selection.shadowedSeqs.length} 条事件（约 ${selection.shadowedTokens} tokens）`,
    summary: `从模型原生上下文（L1）转移到 ${levelLabel} 的原始记录；surface seq ${selection.start}…${selection.end}（surface 顺序）。`,
    useWhen: '需要找回被移出 L1 的早期对话、工具调用或结果时打开。',
    body: selection.body,
    scope,
    workspace: typeof cwd === 'string' ? cwd : '',
    workspaceKey,
    sessionId: session.id,
    tags: { level: [scope === 'workspace' ? 'l3' : 'l2'], source: ['l1-evict'], ...policy.sensitivePolicy !== 'off' && containsSensitive(selection.body) ? { sensitive: ['true'] } : {} },
    provenance: { source: 'l1-eviction', sessionId: session.id, start: selection.start, end: selection.end, shadowedTokens: selection.shadowedTokens },
  })
  const receipt = memoryMessage({
    form: 'l1-eviction',
    text: `<l1-eviction>已将较早的 ${selection.shadowedSeqs.length} 条上下文（seq ${selection.start}–${selection.end}，约 ${selection.shadowedTokens} tokens）从 L1 转移到额外上下文 ${levelLabel}，记录 id 为 ${record.id}。需要原文时用 memory_search / memory_open 取回。</l1-eviction>`,
    meta: { recordId: record.id, start: selection.start, end: selection.end },
  })

  // 2. Shadow-price event immediately followed by the replacement that shrinks
  // L1. If the append is rejected, forget the just-written archive so a failed
  // eviction never leaves a duplicate record behind.
  let prune
  let replacement
  try {
    prune = session.append('compaction/prune', {
      shadowedRange: { start: selection.start, end: selection.end },
      shadowedSeqs: [...selection.shadowedSeqs],
      shadowedTokenCount: selection.shadowedTokens,
    })
    replacement = session.append('user/message', receipt, {
      surfaceOp: { op: 'replace', startSeq: selection.start, endSeq: selection.end },
      sourceEventSeqs: [...selection.shadowedSeqs],
    })
  } catch (error) {
    try {
      await ctx.memory.forget(record.id)
    } catch {
      // Best-effort rollback: the original append failure stays authoritative.
    }
    throw error
  }
  await ctx.memory.recordEviction({
    sessionId: session.id,
    start: selection.start,
    end: selection.end,
    recordId: record.id,
    shadowedTokens: selection.shadowedTokens,
  })
  ctx.logger.info(`memory-evict: moved seq ${selection.start}-${selection.end} (~${selection.shadowedTokens} tokens) from L1 to ${scope} (record ${record.id}, prune seq ${prune.seq}, replacement seq ${replacement.seq})`)
  return { record, scope, shadowedSeqs: selection.shadowedSeqs.length, shadowedTokens: selection.shadowedTokens }
}

export function apply(ctx, config = {}) {
  const policy = {
    evictAtRatio: config.evictAtRatio ?? 0.6,
    retainRatio: config.retainRatio ?? 0.35,
    maxChars: config.maxChars ?? 250_000,
    captureLevel: config.captureLevel === 'l2' ? 'l2' : 'deepest',
    sensitivePolicy: config.sensitivePolicy === 'off' ? 'off' : 'auto',
  }
  if (policy.retainRatio >= policy.evictAtRatio) throw new TypeError('memory-evict: retainRatio must be lower than evictAtRatio')
  let warned = false
  ctx.effect(() => ctx.on('agent/pre-step', async ({ agent, signal }, next) => {
    try {
      await evictOnce(ctx, agent, signal, policy)
    } catch (error) {
      if (!warned) {
        warned = true
        ctx.logger.warn(`memory-evict: eviction skipped: ${String(error?.message ?? error)}`)
      }
    }
    return next()
  }, { prepend: true }), 'memory-evict: L1 → extra-context eviction')
}
