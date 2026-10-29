/**
 * `@qiuxu/memex-compress` — capacity compression for the extra-context
 * pools (L2 session-private, L3 workspace-shared).
 *
 * The user-visible protocol is: when a pool crosses the capacity-notice
 * threshold, the checkpoint policy injects a notice; the model must ASK THE
 * USER before compressing, then call `memory_compress`.
 *
 * Compression is designed for very large pools (10M/100M estimated tokens,
 * potentially thousands of records and gigabytes of raw files), where a single
 * "summarize everything" prompt is impossible. Two strategies compose:
 *
 * - `cold` (default, lossless, zero LLM): move the oldest, least recently
 *   touched, non-pinned records into the cold tier. Their files stay on disk
 *   and remain searchable/openable by id; only their hot prompt footprint is
 *   released. This is the guaranteed way to make room at any scale and costs
 *   O(records) filesystem renames.
 * - `digest` (bounded LLM): before a record goes cold, a map-reduce pass
 *   summarizes BATCHES (bounded records/characters per call, capped call
 *   count, per-run) into small digest records that preserve pointers to the
 *   cold originals. Each run is incremental and resumable: already-cold
 *   records are never selected again, digest ids are deterministic, and a
 *   failed batch only leaves its originals hot for the next run.
 *
 * Everything is scoped per level and per workspace/session; pinned records and
 * open threads are never compressed automatically.
 *
 * @module @qiuxu/memex-compress
 */
import z from '@deepseek-ai/schemastery'
import { defineTool } from '@deepseek-ai/dsh-tools'
import { estimateTokens, memoryVisibleScopes, memoryWorkspaceKey } from '@qiuxu/memex-seam'
import { createHash } from 'node:crypto'

export const name = 'memory-compress'
export const inject = ['memory', 'llm', 'tools']

export const Config = z.object({
  /** Records/characters per digest LLM call (bounded so one call never sees the whole pool). */
  batchRecords: z.number().step(1).min(1).max(200).default(20),
  batchChars: z.number().step(1).min(2_000).default(120_000),
  /** Maximum digest calls in one tool invocation; the rest resumes on the next call. */
  maxBatches: z.number().step(1).min(1).max(64).default(6),
  /** Newest record age that stays hot; very recent records are still being used. */
  minAgeMs: z.number().step(1).min(0).default(60 * 60 * 1000),
  /** Batches below this token size skip the LLM and go straight to the cold tier. */
  minDigestTokens: z.number().step(1).min(0).default(2000),
  /** Cold-tier token budget; above it, compression GCs the oldest cold records (0 = unlimited). */
  coldQuotaTokens: z.number().step(1).min(0).default(0),
})

const TEXT_OUTPUT = {
  schema: { type: 'string' },
  render: (_args, value) => [{ type: 'text', text: value }],
}

const LEVEL_META = {
  l2: { scope: 'session', label: 'L2 session-private', capacityField: 'sessionCapacityTokens' },
  l3: { scope: 'workspace', label: 'L3 workspace-shared', capacityField: 'capacityTokens' },
}

/** Resolve the caller workspace identity from a tool execution. */
function callerScope(exec) {
  const agent = exec?.agent
  const cwd = agent?.session?.header?.cwd
  const sessionId = agent?.session?.id
  if (typeof sessionId !== 'string' || sessionId.length === 0) {
    throw new Error('memory_compress: no calling session')
  }
  return { sessionId, cwd: typeof cwd === 'string' && cwd.length > 0 ? cwd : undefined, workspaceKey: memoryWorkspaceKey(cwd, sessionId) }
}

/** Enabled levels for the calling session. */
async function sessionLevels(memory, sessionId) {
  try {
    return await memory.getLevels(sessionId)
  } catch {
    return { l2: false, l3: false }
  }
}

/** Collect the visible text of a streamed model response. */
class TextAccumulator {
  constructor() {
    this.parts = new Map()
  }

  push(chunk) {
    if (chunk?.type === 'text-delta' && Number.isSafeInteger(chunk.index)) {
      if (!this.parts.has(chunk.index)) this.parts.set(chunk.index, chunk.text)
      else this.parts.set(chunk.index, this.parts.get(chunk.index) + chunk.text)
      return
    }
    if (chunk?.type === 'block-end' && chunk.block?.type === 'text' && Number.isSafeInteger(chunk.index)) {
      this.parts.set(chunk.index, chunk.block.text)
    }
  }

  text() {
    return [...this.parts.entries()].sort((a, b) => a[0] - b[0]).map(([, text]) => text).join('')
  }
}

/** Resolve the routed provider/model for digest calls. */
function routedTarget(exec) {
  const config = exec?.agent?.session?.requestHeader?.()?.config ?? {}
  const provider = config.provider ?? exec?.agent?.options?.provider
  const model = config.model ?? exec?.agent?.options?.model
  if (typeof provider !== 'string' || provider.length === 0 || typeof model !== 'string' || model.length === 0) return undefined
  return { provider, model }
}

/** Read the current hot usage for one level. */
async function levelUsage(memory, workspaceKey, sessionId, level) {
  const meta = LEVEL_META[level]
  const facets = await memory.facets({
    workspaceKey,
    scope: meta.scope,
    ...meta.scope === 'session' ? { sessionId } : {},
  })
  const capacity = meta.scope === 'session' ? (facets.sessionCapacityTokens ?? 10_000_000) : (facets.capacityTokens ?? 100_000_000)
  const hot = Number(facets.hotTokens ?? facets.tokens) || 0
  return { facets, capacity, hot, ratio: capacity > 0 ? hot / capacity : 0 }
}

/** Oldest, non-protected, still-hot candidates for one level. */
async function candidates(memory, workspaceKey, sessionId, level, minAgeMs) {
  const meta = LEVEL_META[level]
  const list = await memory.list({
    workspaceKey,
    scope: meta.scope,
    ...meta.scope === 'session' ? { sessionId } : {},
    cold: 0,
    sort: 'oldest',
    limit: 400,
  })
  const cutoff = Date.now() - minAgeMs
  return list.filter((card) => card.status !== 'pinned' && card.kind !== 'open-thread' && (card.updatedAt ?? 0) < cutoff)
}

/** Cold-spill candidates until the requested amount of hot tokens is freed. */
async function coldSpill(memory, records, neededTokens) {
  const moved = []
  let freed = 0
  for (const card of records) {
    if (freed >= neededTokens) break
    const updated = await memory.archiveCold(card.id)
    if (updated === undefined) continue
    moved.push(card.id)
    freed += card.tokens
  }
  return { moved, freed }
}

/** Summarize one batch of records into a digest body. */
async function digestBatch(ctx, exec, batch) {
  const target = routedTarget(exec)
  if (target === undefined) throw new Error('no routed provider/model for digest; run one request first')
  const lines = []
  for (const [index, card] of batch.entries()) {
    const record = await ctx.memory.get(card.id)
    const body = String(record?.body ?? card.summary ?? '').replace(/\s+/g, ' ').trim()
    lines.push(`[${index + 1}] id=${card.id} kind=${card.kind} title=${card.title}\nuse_when: ${card.useWhen}\nbody: ${body.slice(0, 6000)}`)
  }
  const prompt = [
    '你是额外上下文（长期记忆）的压缩器，目标是为超大规模归档生成可检索的摘要。',
    '把下面这批记录压缩成 1 段不超过 400 tokens 的中文摘要，必须保留：',
    '- 重要决策/事实/约束、关键文件路径、命令、错误码、待办；',
    '- 记录中出现的专有名词、项目名、人名；',
    '- 在摘要末尾另起一行用 `ids: id1, id2` 列出最关键的 record id（最多 5 个）。',
    '丢弃寒暄、重复内容与推理过程。直接输出摘要正文，不要思考过程、不要标题、不要 JSON。',
    '',
    '记录：',
    ...lines,
  ].join('\n')
  const accumulator = new TextAccumulator()
  let textChunks = 0
  let reasoningChars = 0
  for await (const chunk of ctx.llm.stream({
    provider: target.provider,
    model: target.model,
    purpose: 'memory-compress',
    messages: [{ role: 'user', content: [{ type: 'text', text: prompt }] }],
    maxTokens: 1600,
    sessionId: exec.agent?.session?.id,
  })) {
    if (chunk?.type === 'text-delta') textChunks += 1
    if (typeof chunk?.type === 'string' && chunk.type.startsWith('reasoning') && typeof chunk.text === 'string') reasoningChars += chunk.text.length
    accumulator.push(chunk)
  }
  const text = accumulator.text().trim()
  if (text.length === 0) {
    throw new Error(`digest response was empty (textChunks=${textChunks}, reasoningChars=${reasoningChars}, promptChars=${prompt.length})`)
  }
  return text
}

/**
 * Compress one level: cold-spill and, when requested, batch-digest first.
 * @returns {Promise<object>} Per-level report.
 */
async function compressLevel(ctx, exec, args, policy, workspaceKey, sessionId, level) {
  const meta = LEVEL_META[level]
  const scopeFilter = { workspaceKey, scope: meta.scope, ...meta.scope === 'session' ? { sessionId } : {} }
  const usage = await levelUsage(ctx.memory, workspaceKey, sessionId, level)
  const targetRatio = Math.min(Math.max(Number(args.targetRatio) || 0.6, 0.1), 0.95)
  const targetTokens = Math.floor(usage.capacity * targetRatio)
  const needed = Math.max(0, usage.hot - targetTokens)
  const report = {
    level,
    before: { hot: usage.hot, capacity: usage.capacity, ratio: usage.ratio },
    targetTokens,
    needed,
    coldMoved: [],
    digests: 0,
    llmCalls: 0,
    errors: [],
    gc: undefined,
    afterHot: usage.hot,
    history: undefined,
  }

  if (needed > 0 && args.strategy !== 'digest') {
    const result = await ctx.memory.compressCold({ ...scopeFilter, targetRatio, minAgeMs: policy.minAgeMs })
    report.coldMoved = [...result.coldMoved]
  } else if (needed > 0) {
    const pool = await candidates(ctx.memory, workspaceKey, sessionId, level, policy.minAgeMs)
    const remaining = [...pool]
    let freed = 0
    let batches = 0
    const buildBatch = () => {
      const batch = []
      let chars = 0
      while (remaining.length > 0 && batch.length < policy.batchRecords) {
        const card = remaining[0]
        // Prompt-side excerpt budget (body is sliced to 6k chars by digestBatch).
        const estimate = 300 + Math.min(6000, (card.tokens ?? 0) * 4 + 200)
        if (chars + estimate > policy.batchChars && batch.length > 0) break
        batch.push(card)
        remaining.shift()
        chars += estimate
      }
      return batch
    }
    const runBatch = async (batch) => {
      const batchTokens = batch.reduce((sum, card) => sum + (card.tokens ?? 0), 0)
      if (batchTokens < policy.minDigestTokens) {
        const spill = await coldSpill(ctx.memory, batch, Number.MAX_SAFE_INTEGER)
        return { moved: spill.moved, freed: spill.freed, digest: false, llmCalls: 0 }
      }
      let summary
      let lastError
      let llmCalls = 0
      for (let attempt = 0; attempt < 2 && summary === undefined; attempt += 1) {
        try {
          summary = await digestBatch(ctx, exec, batch)
          llmCalls += 1
          if (!/ids\s*[:：]/i.test(summary)) {
            lastError = new Error('digest response missing the required `ids:` line')
            summary = undefined
            ctx.logger.warn('memory_compress: digest missing ids line; retrying')
          }
        } catch (error) {
          lastError = error
          ctx.logger.warn(`memory_compress: digest attempt failed: ${String(error?.message ?? error)}`)
        }
      }
      if (summary === undefined) {
        const spill = await coldSpill(ctx.memory, batch, Number.MAX_SAFE_INTEGER)
        return { moved: spill.moved, freed: spill.freed, digest: false, llmCalls, error: `digest batch fell back to cold spill: ${String(lastError?.message ?? lastError)}` }
      }
      const digestId = `dig_${createHash('sha256').update(`${sessionId}\u0000${level}\u0000${batch.map((card) => card.id).join(',')}`).digest('hex').slice(0, 10)}`
      const digestTokens = estimateTokens(summary)
      try {
        await ctx.memory.write({
          id: digestId,
          kind: 'episode',
          title: `冷摘要 · ${batch.length} 条记录`,
          summary: summary.slice(0, 2000),
          useWhen: '需要回顾已冷存批次时先读这条摘要，再用其中的 record id 打开原文。',
          body: summary,
          scope: meta.scope,
          workspace: exec.agent?.session?.header?.cwd ?? '',
          workspaceKey,
          sessionId,
          tags: { digest: ['cold-batch'] },
          provenance: { strategy: 'digest', digestOf: batch.map((card) => card.id), level },
        })
      } catch (error) {
        const spill = await coldSpill(ctx.memory, batch, Number.MAX_SAFE_INTEGER)
        return { moved: spill.moved, freed: spill.freed, digest: false, llmCalls, error: `digest write failed, fell back to cold spill: ${String(error?.message ?? error)}` }
      }
      const spill = await coldSpill(ctx.memory, batch, Number.MAX_SAFE_INTEGER)
      return { moved: spill.moved, freed: spill.freed - digestTokens, digest: true, llmCalls }
    }

    // Digest up to two batches concurrently: each run stays bounded while large
    // pools drain faster; every batch keeps its own retry/fallback semantics.
    while (remaining.length > 0 && freed < needed && batches < policy.maxBatches) {
      const groups = []
      while (groups.length < 2 && remaining.length > 0 && batches + groups.length < policy.maxBatches) {
        const batch = buildBatch()
        if (batch.length === 0) break
        groups.push(batch)
      }
      if (groups.length === 0) break
      const results = await Promise.all(groups.map((batch) => runBatch(batch)))
      for (const result of results) {
        freed += result.freed
        report.coldMoved.push(...result.moved)
        report.digests += result.digest ? 1 : 0
        report.llmCalls += result.llmCalls
        if (result.error !== undefined) report.errors.push(result.error)
      }
      batches += groups.length
    }
  }

  // Cold-tier quota: drop the oldest cold records above the configured budget.
  if (policy.coldQuotaTokens > 0) {
    const coldFacets = await ctx.memory.facets(scopeFilter)
    if ((coldFacets.coldTokens ?? 0) > policy.coldQuotaTokens) {
      report.gc = await ctx.memory.gcCold({ ...scopeFilter, keepTokens: policy.coldQuotaTokens })
    }
  }

  const after = await ctx.memory.facets(scopeFilter)
  report.afterHot = Number(after.hotTokens ?? after.tokens)
  await ctx.memory.recordCompression({
    sessionId,
    level,
    strategy: args.strategy,
    beforeHot: report.before.hot,
    afterHot: report.afterHot,
    coldMoved: report.coldMoved.length,
    digests: report.digests,
    llmCalls: report.llmCalls,
    errors: report.errors,
  })
  report.history = await ctx.memory.compressionStats(sessionId, 3)
  return report
}

const tool = (ctx, policy) => defineTool({
  name: 'memory_compress',
  description: 'Release capacity in the extra-context pools (L2/L3) when they are near full. Ask the user first. Strategies: cold (default) moves the oldest non-pinned records to the lossless cold tier (files stay on disk, retrievable by memory_open; zero LLM); digest additionally runs bounded map-reduce summary batches first (resumable, never one huge prompt). Designed for very large pools: each run processes a bounded number of records/calls and can be repeated.',
  parameters: {
    level: { type: 'string', enum: ['l2', 'l3', 'auto'], description: 'Which pool to compress; auto = every enabled level.' },
    strategy: { type: 'string', enum: ['cold', 'digest'], description: 'cold = lossless tier move (no LLM); digest = batched summaries + cold move.' },
    targetRatio: { type: 'number', description: 'Target hot usage as capacity ratio, 0.1-0.95. Defaults to 0.6.' },
  },
  async execute(args, exec) {
    const scope = callerScope(exec)
    const levels = await sessionLevels(ctx.memory, scope.sessionId)
    if (levels.l2 !== true && levels.l3 !== true) return 'Extra context is off for this session; enable L2/L3 before compressing.'
    const requested = args.level === 'auto' || args.level === undefined
      ? ['l2', 'l3'].filter((level) => levels[level] === true)
      : [args.level]
    for (const level of requested) {
      if (levels[level] !== true) return `memory_compress: ${level.toUpperCase()} is not enabled for this session (levels are sticky; enable it first).`
    }
    const strategy = args.strategy === 'digest' ? 'digest' : 'cold'
    const lines = [`memory_compress (${strategy}${args.level && args.level !== 'auto' ? `, ${args.level}` : ', auto'})`]
    for (const level of requested) {
      const report = await compressLevel(ctx, exec, { ...args, strategy }, policy, scope.workspaceKey, scope.sessionId, level)
      const fmt = (value) => value >= 1_000_000 ? `${(value / 1_000_000).toFixed(2)}M` : value >= 1_000 ? `${(value / 1_000).toFixed(1)}K` : String(value)
      const pct = (value) => fmt(value)
      lines.push(`- ${LEVEL_META[level].label}: hot ${pct(report.before.hot)}/${pct(report.before.capacity)} (${Math.round(report.before.ratio * 100)}%) → target ${pct(report.targetTokens)}`)
      lines.push(`  cold-moved ${report.coldMoved.length} records; digests ${report.digests}; LLM calls ${report.llmCalls}; hot now ${pct(report.afterHot)}`)
      if (report.gc !== undefined && report.gc.removed.length > 0) lines.push(`  cold quota GC removed ${report.gc.removed.length} records (~${pct(report.gc.freedTokens)} tokens)`)
      if (report.errors.length > 0) lines.push(`  errors: ${report.errors.join('; ')}`)
      if (report.history?.last !== undefined) lines.push(`  history: ${report.history.count} runs; last ${new Date(report.history.last.createdAt).toISOString()}`)
    }
    lines.push('Cold records stay searchable/openable via memory_open. Ask the user before running again.')
    return lines.join('\n')
  },
  output: TEXT_OUTPUT,
  isConcurrencySafe: () => false,
})

export function apply(ctx, config = {}) {
  const policy = {
    batchRecords: config.batchRecords ?? 20,
    batchChars: config.batchChars ?? 120_000,
    maxBatches: config.maxBatches ?? 6,
    minAgeMs: config.minAgeMs ?? 60 * 60 * 1000,
    minDigestTokens: config.minDigestTokens ?? 2000,
    coldQuotaTokens: config.coldQuotaTokens ?? 0,
  }
  ctx.effect(() => ctx.tools.register(tool(ctx, policy)), 'memory-compress: tool')
}

/** Re-exported for tests: level metadata used by the report. */
export { LEVEL_META }
