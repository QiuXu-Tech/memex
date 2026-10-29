/**
 * Checkpoint policy for the extra-context memory subsystem.
 *
 * This layer owns everything time- and prompt-shaped: it watches for the
 * compaction marker pair, archives the region that compaction just shadowed,
 * injects a bounded checkpoint receipt, maintains a catalog of record cards,
 * and recalls likely-relevant cards for the current user message.
 *
 * It deliberately does not replace `ctx.compaction` and does not mutate the
 * session log beyond ordinary user messages with a memory source. The shipped
 * compaction backend keeps working unchanged; the archive is the lossless
 * counterpart to its lossy summary.
 *
 * @module @qiuxu/memex-checkpoint/checkpoint
 */
import { createHash } from 'node:crypto'
import { archiveRecordId, canonicalEventsFromDsh, memoryCaptureScope, memoryMessage, memoryQueryTerms, memoryVisibleScopes, memoryWorkspaceKey } from '@qiuxu/memex-seam'
import { buildCard } from './render.js'

/** Bound on buffered live events per session (fallback when no query service exists). */
const BUFFER_LIMIT = 4000
/** Bound on remembered record ids per session to avoid repeating the same card. */
const SHOWN_LIMIT = 80
/** Maximum receipts held for one session before older ones are dropped. */
const RECEIPT_LIMIT = 4

/**
 * Collect the visible text of a streamed model response.
 *
 * Deltas may arrive without block boundaries; a closing `block-end` wins over
 * accumulated deltas for the same index, mirroring the harness assembler.
 */
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

/** One identified, frozen memory message for the model surface. */
function createMemoryMessage(form, text, meta = {}) {
  return memoryMessage({ form, text, meta })
}

/** Clip text to a code-point budget with an explicit marker. */
function clip(text, max) {
  const value = String(text ?? '')
  return value.length <= max ? value : `${value.slice(0, max)}…`
}

/** Extract the plain text of one user message. */
function messageText(message) {
  return (message.content ?? [])
    .filter((block) => block?.type === 'text')
    .map((block) => block.text)
    .join('\n')
    .trim()
}

/**
 * Register the checkpoint policy on one memory service context.
 *
 * @param {import('@deepseek-ai/cordis').Context} ctx - Owning context.
 * @param {{ store: import('./store.js').LocalStoreCore, config: object }} memory - Memory service.
 * @returns {{ dispose: () => void }} Disposer for the policy's own state (plugin teardown).
 */
/**
 * Register the checkpoint policy on one context.
 *
 * @param {import('@deepseek-ai/cordis').Context} ctx - Owning context.
 * @param {import('./seam.js').MemoryStore} memory - The `ctx.memory` service.
 * @param {{cardModel?: 'auto'|'off', catalogMaxChars?: number, recallMaxChars?: number, autoRecall?: boolean}} config - Policy config from the plugin row.
 * @returns {{dispose: () => void, drain: () => Promise<void>}} Policy handle.
 */
export function registerCheckpointPolicy(ctx, memory, config = {}) {
  const policyConfig = {
    cardModel: config.cardModel ?? 'auto',
    capacityNoticeRatio: config.capacityNoticeRatio ?? 0.8,
    capacityNoticeCooldownMs: config.capacityNoticeCooldownMs ?? 10 * 60 * 1000,
    catalogMaxChars: config.catalogMaxChars ?? 2400,
    recallMaxChars: config.recallMaxChars ?? 600,
    autoRecall: config.autoRecall ?? true,
    autoArchive: config.autoArchive ?? true,
    materializer: config.materializer ?? 'off',
    materializerMaxTokens: Number.isSafeInteger(config.materializerMaxTokens) ? config.materializerMaxTokens : 1800,
  }
  /** sessionId -> Map<seq, event>, bounded live fallback. */
  const buffers = new Map()
  /** sessionId -> {recordId, title, text}[] pending receipt lines. */
  const receipts = new Map()
  /** sessionId -> last catalog digest injected. */
  const catalogDigest = new Map()
  /** sessionId -> last materialized-window digest injected. */
  const materializerDigest = new Map()
  /** sessionId -> Set<recordId> already shown to this session. */
  const shown = new Map()
  /** sessionId -> last recall query, avoiding duplicate recall messages. */
  const lastRecall = new Map()
  /** sessionIds already reconciled against persisted compactions. */
  const reconciled = new Set()
  /** In-flight archive jobs (drained by the disposer). */
  const jobs = new Set()
  let disposed = false

  const query = () => {
    try {
      return ctx.get('sessionQuery')
    } catch {
      return undefined
    }
  }
  const warn = (message) => {
    try {
      ctx.logger?.warn?.(`memory-checkpoint: ${message}`)
    } catch {
      // A warning sink must never break the archive path.
    }
  }

  /**
   * Resolve one session's enabled cache levels. No level enabled means the
   * whole feature is dormant for that conversation: no archive, no injection.
   * @param {object} session - Live session.
   * @returns {Promise<{l2: boolean, l3: boolean} | undefined>} Levels, or undefined when off.
   */
  async function sessionLevels(session) {
    try {
      const levels = await memory.getLevels(session.id)
      if (levels.l2 === true || levels.l3 === true) return levels
    } catch {
      // A store failure must not inject or archive anything.
    }
    return undefined
  }

  /** Track one live session event for the fallback path. */
  function bufferEvent(session, event) {
    let map = buffers.get(session.id)
    if (map === undefined) {
      map = new Map()
      buffers.set(session.id, map)
    }
    map.set(event.seq, event)
    if (map.size > BUFFER_LIMIT) {
      const oldest = map.keys().next().value
      map.delete(oldest)
    }
  }

  /** Read the raw events behind a set of shadowed sequence numbers. */
  async function readShadowedEvents(session, seqs) {
    const queryService = query()
    if (queryService !== undefined) {
      try {
        const { events } = await queryService.readSession(session.id)
        const bySeq = new Map(events.map((event) => [event.seq, event]))
        const selected = seqs.map((seq) => bySeq.get(seq)).filter((event) => event !== undefined)
        if (selected.length === seqs.length) return selected
        warn(`session query returned ${selected.length}/${seqs.length} shadowed events for ${session.id}`)
        return selected
      } catch (error) {
        warn(`readSession failed, falling back to the live buffer: ${String(error?.message ?? error)}`)
      }
    }
    const buffered = buffers.get(session.id) ?? new Map()
    return seqs.map((seq) => buffered.get(seq)).filter((event) => event !== undefined)
  }

  /** Mark these record ids as already shown to one session. */
  function markShown(sessionId, ids) {
    let set = shown.get(sessionId)
    if (set === undefined) {
      set = new Set()
      shown.set(sessionId, set)
    }
    for (const id of ids) set.add(id)
    while (set.size > SHOWN_LIMIT) set.delete(set.values().next().value)
  }

  /** Ask the routed model for a higher-quality card; keep the deterministic one on any failure. */
  async function refineCard(session, record, attempt = 1) {
    if (policyConfig.cardModel === 'off') return
    const llm = (() => {
      try {
        return ctx.get('llm')
      } catch {
        return undefined
      }
    })()
    if (llm === undefined) return
    const target = session.requestHeader?.()?.config
    if (target?.provider === undefined || target?.model === undefined) return
    const prompt = [
      'You are writing an index card for a memory record that stores archived conversation context.',
      'Return ONLY a JSON object with these fields:',
      '{"title": string (<=80 chars, names the work), "summary": string (2-3 sentences, what was done and what remains), "use_when": string (one sentence starting with "Read when", says exactly when a future reader should open this record), "tags": string[] (2-6 short lowercase keywords: domain, files, tools), "kind": one of episode|decision|fact|procedure|open-thread|incident|artifact}',
      'Write in the dominant language of the material.',
      '',
      'Existing deterministic card:',
      `title: ${record.title}`,
      `use_when: ${record.useWhen}`,
      '',
      'Compaction summary of the archived region:',
      clip(record.summary, 2400),
    ].join('\n')
    try {
      const accumulator = new TextAccumulator()
      const stream = llm.stream({
        provider: target.provider,
        model: target.model,
        messages: [{ role: 'user', content: [{ type: 'text', text: prompt }] }],
        maxTokens: 600,
        sessionId: session.id,
      })
      for await (const chunk of stream) accumulator.push(chunk)
      const text = accumulator.text()
      const start = text.indexOf('{')
      const end = text.lastIndexOf('}')
      if (start < 0 || end <= start) throw new Error('card response had no JSON object')
      const parsed = JSON.parse(text.slice(start, end + 1))
      if (typeof parsed.title !== 'string' || parsed.title.trim().length === 0) throw new Error('card response missing title')
      const updated = await memory.write({
        ...record,
        id: record.id,
        title: parsed.title,
        summary: typeof parsed.summary === 'string' && parsed.summary.length > 0 ? parsed.summary : record.summary,
        useWhen: typeof parsed.use_when === 'string' && parsed.use_when.length > 0 ? parsed.use_when : record.useWhen,
        kind: typeof parsed.kind === 'string' ? parsed.kind : record.kind,
        tags: {
          ...record.tags,
          card: Array.isArray(parsed.tags) ? parsed.tags.filter((tag) => typeof tag === 'string').slice(0, 6) : [],
        },
        tokens: record.tokens,
      })
      if (updated !== undefined) {
        record.title = updated.title
        record.summary = updated.summary
        record.useWhen = updated.useWhen
        record.kind = updated.kind
        record.tags = updated.tags
      }
    } catch (error) {
      if (attempt < 2 && !disposed) {
        warn(`card refinement attempt ${attempt} failed, retrying: ${String(error?.message ?? error)}`)
        await new Promise((resolve) => setTimeout(resolve, 1500))
        return refineCard(session, record, attempt + 1)
      }
      warn(`card refinement skipped: ${String(error?.message ?? error)}`)
    }
  }

  /** Archive one completed compaction; idempotent by (session, compaction) id. */
  async function archiveCompaction(session, summaryEvent) {
    if (disposed || policyConfig.autoArchive === false) return
    const levels = await sessionLevels(session)
    const scope = memoryCaptureScope(levels)
    if (scope === undefined) return
    const data = summaryEvent.data ?? {}
    const compactionId = data.compactionId
    const seqs = Array.isArray(data.shadowedSeqs) ? data.shadowedSeqs : []
    if (typeof compactionId !== 'string' || seqs.length === 0) return
    const existing = await memory.wasArchived(session.id, compactionId)
    if (existing !== undefined) return
    const cwd = session.header?.cwd
    const workspaceKey = memoryWorkspaceKey(cwd, session.id)
    const events = await readShadowedEvents(session, seqs)
    if (events.length === 0) {
      warn(`no readable events for compaction ${compactionId} of ${session.id}`)
      return
    }
    const record = {
      ...buildCard({
        events,
        summaryBlocks: data.summary,
        shadowedTokenCount: Number.isSafeInteger(data.shadowedTokenCount) ? data.shadowedTokenCount : undefined,
        seqStart: seqs[0],
        seqEnd: seqs[seqs.length - 1],
        sessionId: session.id,
        compactionId,
        cwd,
      }),
      id: archiveRecordId(session.id, compactionId),
      scope,
      workspaceKey,
      workspace: typeof cwd === 'string' ? cwd : '',
      sessionId: session.id,
      tokens: Number.isSafeInteger(data.shadowedTokenCount) ? data.shadowedTokenCount : undefined,
      trust: 'derived',
      status: 'active',
      provenance: {
        source: 'compaction-archive',
        sessionId: session.id,
        compactionId,
        seqStart: seqs[0],
        seqEnd: seqs[seqs.length - 1],
        shadowedEventCount: events.length,
        shadowedTokenCount: data.shadowedTokenCount,
        provider: data.provider,
        model: data.model,
        cwd: cwd ?? '',
      },
    }
    const stored = await memory.archiveRegion({ sessionId: session.id, compactionId, record })
    // Context-materialization step 1: keep the exact role/tool/sequence
    // envelope alongside the rendered card. A backend without support no-ops.
    try {
      await memory.appendContextEvents({ recordId: stored.id, events: canonicalEventsFromDsh(events, { sessionId: session.id, recordId: stored.id }) })
    } catch (error) {
      warn(`canonical context-event capture skipped: ${String(error?.message ?? error)}`)
    }
    const list = receipts.get(session.id) ?? []
    list.push({
      recordId: stored.id,
      title: stored.title,
      text: `[MEMORY CHECKPOINT] The context that just left the window (seq #${seqs[0]}–#${seqs[seqs.length - 1]}, ~${record.tokens ?? '?'} tokens) is archived losslessly as ${stored.id} (${stored.kind}) "${stored.title}". The checkpoint above is a lossy summary; call memory_open ${stored.id} when you need exact details, or memory_grep a distinctive string.`,
    })
    while (list.length > RECEIPT_LIMIT) list.shift()
    receipts.set(session.id, list)
    markShown(session.id, [stored.id])
    await refineCard(session, stored)
  }

  /** Enqueue one archive job on a serial queue so overlapping compactions cannot race. */
  let chain = Promise.resolve()
  function enqueue(session, event) {
    const job = chain
      .then(() => archiveCompaction(session, event))
      .catch((error) => {
        warn(`archive failed: ${String(error?.message ?? error?.stack ?? error)}`)
      })
      .finally(() => {
        jobs.delete(job)
      })
    jobs.add(job)
    chain = job
  }

  /** Archive any persisted compactions this process never saw (resume/crash recovery). */
  async function reconcile(session) {
    const queryService = query()
    if (queryService === undefined) return
    try {
      const records = await queryService.listEvents(session.id)
      for (const record of records) {
        if (record.type !== 'compaction/summary') continue
        const observed = await queryService.readEvent({ sessionId: session.id, seq: record.seq })
        const target = observed.target
        if (target?.type !== 'compaction/summary') continue
        if (await memory.wasArchived(session.id, target.data?.compactionId) !== undefined) continue
        await archiveCompaction(session, target)
      }
    } catch (error) {
      warn(`reconcile failed for ${session.id}: ${String(error?.message ?? error)}`)
    }
  }

  /** Build a materialized resident window message, or undefined. */
  async function materializedMessage(session, workspaceKey, levels) {
    if (policyConfig.materializer === 'off') return undefined
    if (typeof memory.materializeContext !== 'function') return undefined
    const filter = { workspaceKey, scopes: memoryVisibleScopes(levels), sessionId: session.id }
    const result = await memory.materializeContext({
      ...filter,
      budgetTokens: policyConfig.materializerMaxTokens,
      variant: policyConfig.materializer,
    })
    if (result === undefined || typeof result.text !== 'string' || result.text.length === 0) return undefined
    const digest = createHash('sha256').update(result.text).digest('hex')
    if (materializerDigest.get(session.id) === digest) return undefined
    materializerDigest.set(session.id, digest)
    return createMemoryMessage('materialized-context', result.text, { workspaceKey, levels, recordIds: result.includedIds ?? [] })
  }

  /** Build the bounded catalog message for one session, or undefined when unchanged/empty. */
  async function catalogMessage(session, workspaceKey, levels) {
    const maxChars = Math.max(600, Number.isSafeInteger(policyConfig.catalogMaxChars) ? policyConfig.catalogMaxChars : 2200)
    const filter = { workspaceKey, scopes: memoryVisibleScopes(levels), sessionId: session.id }
    const text = await memory.catalog({ ...filter, maxChars })
    const digest = createHash('sha256').update(text).digest('hex')
    if (catalogDigest.get(session.id) === digest) return undefined
    if ((await memory.facets(filter)).count === 0) return undefined
    catalogDigest.set(session.id, digest)
    return createMemoryMessage('catalog', text, { workspaceKey, levels })
  }

  /**
   * Build a recall query from a user message using the shared extractor so
   * memory_search and auto-recall agree on retrieval terms.
   * @param {string} text - Direct user message text.
   * @returns {string} Search query with distinctive terms.
   */
  function recallTerms(text) {
    const query = memoryQueryTerms(text, 12).join(' ')
    return query.length >= 3 ? query : text.slice(0, 120)
  }

  /** Build a recall message for the newest direct user message, or undefined. */
  async function recallMessage(session, workspaceKey, directText, levels) {
    if (policyConfig.autoRecall === false) return undefined
    const text = directText.trim()
    if (text.length < 3) return undefined
    if (lastRecall.get(session.id) === text) return undefined
    const filter = { workspaceKey, scopes: memoryVisibleScopes(levels), sessionId: session.id }
    const query = recallTerms(text)
    let { hits } = await memory.search({ ...filter, query, limit: 3 })
    if (hits.length === 0 && query !== text.slice(0, 120)) {
      ({ hits } = await memory.search({ ...filter, query: text.slice(0, 120), limit: 3 }))
    }
    const alreadyShown = shown.get(session.id) ?? new Set()
    const fresh = hits.filter((hit) => !alreadyShown.has(hit.id))
    if (fresh.length === 0) return undefined
    lastRecall.set(session.id, text)
    const maxChars = Math.max(200, Number.isSafeInteger(policyConfig.recallMaxChars) ? policyConfig.recallMaxChars : 600)
    const lines = fresh.map((hit) => `- ${hit.id} · ${hit.title}${hit.useWhen.length > 0 ? ` · ${clip(hit.useWhen, 120)}` : ''}`)
    const body = clip([
      '[MEMORY RECALL] Earlier records in this workspace may be relevant to the current request:',
      ...lines,
      'Call memory_open <id> to read one; ignore these if they are unrelated.',
    ].join('\n'), maxChars)
    markShown(session.id, fresh.map((hit) => hit.id))
    await memory.markRead(fresh.map((hit) => hit.id))
    return createMemoryMessage('recall', body, { recordIds: fresh.map((hit) => hit.id) })
  }

  // ── live event tracking ────────────────────────────────────────────────────
  ctx.on('session/event', (session, event) => {
    try {
      bufferEvent(session, event)
      if (event.type === 'compaction/summary') enqueue(session, event)
    } catch (error) {
      warn(`session event handling failed: ${String(error?.message ?? error)}`)
    }
  })

  /** Last capacity notice time per session (cooldown). */
  const capacityNoticed = new Map()

  /**
   * Build one capacity notice when an enabled hot pool is near its capacity.
   * The model is told to ask the user BEFORE compressing; the actual
   * compression is the `memory_compress` tool (cold tier first, batch digests
   * after consent).
   * @returns {Promise<object|undefined>} Memory message or undefined.
   */
  async function capacityNotice(session, workspaceKey, levels) {
    const last = capacityNoticed.get(session.id) ?? 0
    if (Date.now() - last < policyConfig.capacityNoticeCooldownMs) return undefined
    const lines = []
    const scopes = { l2: ['session', 10_000_000], l3: ['workspace', 100_000_000] }
    for (const level of ['l2', 'l3']) {
      if (levels[level] !== true) continue
      const [scope, fallbackCapacity] = scopes[level]
      const facets = await memory.facets({
        workspaceKey,
        scope,
        ...scope === 'session' ? { sessionId: session.id } : {},
      })
      const capacity = scope === 'session' ? (facets.sessionCapacityTokens ?? fallbackCapacity) : (facets.capacityTokens ?? fallbackCapacity)
      const hot = Number(facets.hotTokens ?? facets.tokens) || 0
      const ratio = capacity > 0 ? hot / capacity : 0
      if (ratio < policyConfig.capacityNoticeRatio) continue
      lines.push(`- ${level.toUpperCase()}=${Math.round(ratio * 100)}% hot (${hot} / ${capacity} tokens, ${facets.coldCount ?? 0} cold records)`)
    }
    if (lines.length === 0) return undefined
    capacityNoticed.set(session.id, Date.now())
    const text = [
      '[EXTRA CONTEXT CAPACITY / 额外上下文容量] The enabled extra-context pool is close to full / 已接近容量上限：',
      ...lines,
      'Ask the user once whether to compress the extra context before continuing; do NOT compress without their consent.',
      '请先询问用户是否需要压缩额外上下文；未经用户同意不要压缩。',
      'If the user agrees, call the `memory_compress` tool: strategy=cold is lossless (records move to the cold tier, still openable by id, no LLM cost); strategy=digest additionally runs bounded map-reduce summary batches first. Both are incremental and resumable, so design for very large pools and never summarize the whole pool in one prompt.',
      '用户同意后调用 `memory_compress`：strategy=cold 无损下沉冷层（可按 id 取回，零 LLM）；strategy=digest 先做有界批量摘要；两者增量可续跑，不要一次摘要整个池。',
      'If the user declines, continue working and ignore this notice. 用户拒绝则继续工作并忽略本提示。',
    ].join('\n')
    return createMemoryMessage('capacity-notice', clip(text, 1400), { levels })
  }

  // ── per-step injection: receipts, catalog, recall ──────────────────────────
  ctx.on('agent/pre-step', async ({ agent }, next) => {
    const decision = await next()
    if (decision.kind === 'reject' || disposed) return decision
    try {
      const session = agent.session
      const sessionId = session.id
      const cwd = session.header?.cwd
      const workspaceKey = memoryWorkspaceKey(cwd, sessionId)
      const levels = await sessionLevels(session)
      const additions = []

      // Extra context is opt-in per cache level. With both levels off the
      // conversation stays completely transparent: no catalog, no receipts, no
      // recall, no archive.
      if (levels === undefined) {
        receipts.delete(sessionId)
        return decision
      }

      if (!reconciled.has(sessionId)) {
        reconciled.add(sessionId)
        // Recovery runs in the background so a resumed session never blocks its
        // first step on historical log reads.
        const job = reconcile(session).catch(() => {}).finally(() => jobs.delete(job))
        jobs.add(job)
      }

      const pending = receipts.get(sessionId)
      if (pending !== undefined && pending.length > 0) {
        receipts.delete(sessionId)
        const text = pending.map((receipt) => receipt.text).join('\n')
        additions.push(createMemoryMessage('checkpoint', clip(text, 1600), { recordIds: pending.map((receipt) => receipt.recordId) }))
      }

      let materialized = false
      if (policyConfig.materializer !== 'off') {
        const window = await materializedMessage(session, workspaceKey, levels)
        if (window !== undefined) {
          additions.push(window)
          materialized = true
        }
      }
      if (!materialized) {
        const catalog = await catalogMessage(session, workspaceKey, levels)
        if (catalog !== undefined) additions.push(catalog)
      }

      const capacity = await capacityNotice(session, workspaceKey, levels)
      if (capacity !== undefined) additions.push(capacity)

      const direct = [...decision.messages].reverse().find((message) => message.role === 'user' && (message.source?.kind === 'user' || message.source?.kind === 'user-rpc'))
      if (!materialized && direct !== undefined) {
        const recall = await recallMessage(session, workspaceKey, messageText(direct), levels)
        if (recall !== undefined) additions.push(recall)
      }

      if (additions.length === 0) return decision
      return { ...decision, messages: [...decision.messages, ...additions] }
    } catch (error) {
      warn(`pre-step injection failed: ${String(error?.message ?? error)}`)
      return decision
    }
  }, { prepend: true })

  // ── lifecycle ──────────────────────────────────────────────────────────────
  ctx.on('session/disposed', (session) => {
    const sessionId = typeof session === 'string' ? session : session?.id
    if (sessionId === undefined) return
    buffers.delete(sessionId)
    receipts.delete(sessionId)
    catalogDigest.delete(sessionId)
    materializerDigest.delete(sessionId)
    capacityNoticed.delete(sessionId)
    shown.delete(sessionId)
    lastRecall.delete(sessionId)
    reconciled.delete(sessionId)
  })

  return {
    /** Registered for symmetry with other policy plugins; the fiber owns event disposal. */
    dispose() {
      disposed = true
      buffers.clear()
      receipts.clear()
      catalogDigest.clear()
      shown.clear()
      lastRecall.clear()
    },
    /** Wait for in-flight archive jobs; used by teardown and tests. */
    async drain() {
      await Promise.allSettled([...jobs])
    },
  }
}
