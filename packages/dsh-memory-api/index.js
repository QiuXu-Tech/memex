/**
 * `@qiuxu/dsh-memory/api` — read/pin HTTP API for the memory panel.
 *
 * The Web client cannot reach `ctx.memory` directly, so this row exposes a
 * small, owner-authenticated Fetch route family under `/api/memory.*` backed by
 * the `ctx.memory` service. It is read-mostly by design: only lifecycle status
 * (pin/unpin) is writable; archiving, recall and tool writes stay in their own
 * rows.
 *
 * Identity comes from the session id the client is viewing: the workspace key
 * is derived from that live session's working directory, so a panel can never
 * read another workspace's memory by passing a forged key.
 *
 * @module @qiuxu/dsh-memory-api
 */
import { memoryCaptureScope, memoryVisibleScopes, memoryWorkspaceKey } from '@qiuxu/dsh-memory-seam'

export const name = 'memory-api'

export const inject = ['memory', 'connection', 'sessions']

/** Route family root; the client addresses the same paths document-relatively. */
const ROUTES = Object.freeze({
  index: '/api/memory.index',
  record: '/api/memory.record',
  search: '/api/memory.search',
  status: '/api/memory.status',
  level: '/api/memory.level',
  compress: '/api/memory.compress',
  restore: '/api/memory.restore',
  gc: '/api/memory.gc',
  metrics: '/api/memory.metrics',
})

/** Slice a UTF-8 string to at most `maxBytes` bytes without breaking the budget. */
function bufferSlice(text, maxBytes) {
  const buffer = Buffer.from(text, 'utf8')
  if (buffer.length <= maxBytes) return text
  return buffer.subarray(0, maxBytes).toString('utf8')
}

/** JSON response helper. */
function json(value, status = 200) {
  return new Response(JSON.stringify(value), {
    status,
    headers: { 'content-type': 'application/json; charset=utf-8' },
  })
}

/** JSON error helper. */
function fail(status, code, message) {
  return json({ ok: false, code, message }, status)
}

/** Clamp a numeric query parameter; absent or blank values take the fallback. */
function clamp(value, fallback, min, max) {
  if (value === null || value === undefined) return fallback
  const text = String(value).trim()
  if (text.length === 0) return fallback
  const number = Number(text)
  if (!Number.isFinite(number)) return fallback
  return Math.min(Math.max(Math.trunc(number), min), max)
}

/**
 * Build the visibility filter for one effective mode.
 * @param {{workspaceKey: string, sessionId: string}} scope - Caller workspace.
 * @param {'off' | 'session' | 'workspace'} mode - Effective mode.
 * @returns {{workspaceKey: string, scope?: string, sessionId?: string}} Store filter.
 */
function visibleFilter(scope, levels) {
  const scopes = memoryVisibleScopes(levels)
  if (scopes.length === 0) return { workspaceKey: scope.workspaceKey }
  return { workspaceKey: scope.workspaceKey, scopes, sessionId: scope.sessionId }
}

/** Whether one record belongs to the caller's enabled levels. */
function recordVisible(record, workspaceKey, sessionId, levels) {
  if (record.workspaceKey !== workspaceKey) return false
  if (record.scope === 'workspace') return levels.l3 === true
  if (record.scope === 'session') return levels.l2 === true && record.sessionId === sessionId
  return false
}

/** Serialize one record card for the panel (no body, no internal paths). */
function card(card) {
  return {
    id: card.id,
    scope: card.scope,
    cold: card.cold === true,
    kind: card.kind,
    status: card.status,
    title: card.title,
    summary: card.summary,
    useWhen: card.useWhen,
    tags: card.tags,
    tokens: card.tokens,
    trust: card.trust,
    createdAt: card.createdAt,
    updatedAt: card.updatedAt,
    readCount: card.readCount,
    sessionId: card.sessionId,
    provenance: card.provenance,
  }
}

/**
 * Resolve the caller's workspace from the live session (or a cwd that belongs
 * to one live session). No workspace key is accepted from the caller directly.
 */
function resolveWorkspace(ctx, sessionId, cwd) {
  const sessions = ctx.sessions.list()
  let session
  if (typeof sessionId === 'string' && sessionId.length > 0) {
    session = sessions.find((candidate) => candidate.id === sessionId)
  } else if (typeof cwd === 'string' && cwd.length > 0) {
    session = sessions.find((candidate) => candidate.header?.cwd === cwd)
  }
  if (session === undefined) return undefined
  return { session, cwd: session.header?.cwd, sessionId: session.id }
}

/** Build the route handlers bound to one context. */
function handlers(ctx) {
  const memory = () => ctx.memory

  return {
    async index(request) {
      const url = new URL(request.url)
      const scope = resolveWorkspace(ctx, url.searchParams.get('sessionId'), url.searchParams.get('cwd'))
      if (scope === undefined) return fail(404, 'MEMORY_UNKNOWN_SESSION', 'no live session for this memory panel')
      const workspaceKey = memoryWorkspaceKey(scope.cwd, scope.sessionId)
      const limit = clamp(url.searchParams.get('limit'), 100, 1, 300)
      const levels = await memory().getLevels(scope.sessionId)
      const sessionFacets = await memory().facets({ workspaceKey, scope: 'session', sessionId: scope.sessionId })
      const workspaceFacets = await memory().facets({ workspaceKey, scope: 'workspace' })
      const activeFilter = visibleFilter({ workspaceKey, sessionId: scope.sessionId }, levels)
      const enabled = levels.l2 === true || levels.l3 === true
      const activeFacets = enabled
        ? await memory().facets(activeFilter)
        : {
            count: 0,
            tokens: 0,
            bytes: 0,
            hotTokens: 0,
            coldTokens: 0,
            hotCount: 0,
            coldCount: 0,
            capacityTokens: 0,
            sessionCapacityTokens: sessionFacets.sessionCapacityTokens,
            byKind: {},
            byKindTokens: {},
            byStatus: {},
            oldest: undefined,
            newest: undefined,
          }
      const records = enabled ? await memory().list({ ...activeFilter, limit }) : []
      const evictions = await memory().evictionStats(scope.sessionId)
      const compression = await memory().compressionStats(scope.sessionId, 3)
      return json({
        ok: true,
        levels,
        compression,
        captureScope: memoryCaptureScope(levels) ?? null,
        scope: { sessionId: scope.sessionId, cwd: scope.cwd ?? '', workspaceKey },
        l2: {
          enabled: levels.l2 === true,
          tokens: sessionFacets.tokens,
          hotTokens: sessionFacets.hotTokens,
          coldTokens: sessionFacets.coldTokens,
          coldCount: sessionFacets.coldCount,
          count: sessionFacets.count,
          capacityTokens: sessionFacets.sessionCapacityTokens,
        },
        l3: {
          enabled: levels.l3 === true,
          tokens: workspaceFacets.tokens,
          hotTokens: workspaceFacets.hotTokens,
          coldTokens: workspaceFacets.coldTokens,
          coldCount: workspaceFacets.coldCount,
          count: workspaceFacets.count,
          capacityTokens: workspaceFacets.capacityTokens,
        },
        l1Evicted: evictions,
        // Backward-compatible active-pool fields (ring/panel read these).
        capacityTokens: activeFacets.capacityTokens,
        tokens: activeFacets.tokens,
        hotTokens: activeFacets.hotTokens,
        coldTokens: activeFacets.coldTokens,
        coldCount: activeFacets.coldCount,
        byKind: activeFacets.byKind,
        byKindTokens: activeFacets.byKindTokens,
        byStatus: activeFacets.byStatus,
        count: activeFacets.count,
        records: records.map(card),
      })
    },

    async record(request) {
      const url = new URL(request.url)
      const scope = resolveWorkspace(ctx, url.searchParams.get('sessionId'), url.searchParams.get('cwd'))
      if (scope === undefined) return fail(404, 'MEMORY_UNKNOWN_SESSION', 'no live session for this memory panel')
      const id = url.searchParams.get('id')
      if (typeof id !== 'string' || id.length === 0) return fail(400, 'MEMORY_INVALID_ID', 'id is required')
      const record = await memory().get(id)
      if (record === undefined) return fail(404, 'MEMORY_NOT_FOUND', 'no such memory record')
      const workspaceKey = memoryWorkspaceKey(scope.cwd, scope.sessionId)
      const levels = await memory().getLevels(scope.sessionId)
      if (!recordVisible(record, workspaceKey, scope.sessionId, levels)) {
        return fail(404, 'MEMORY_NOT_FOUND', 'no such memory record in the enabled extra-context levels')
      }
      const fullBody = String(record.body ?? '')
      const offset = clamp(url.searchParams.get('offset'), 0, 0, Math.max(0, fullBody.length - 1))
      const limit = clamp(url.searchParams.get('limit'), 200_000, 1, 1_000_000)
      const totalChars = fullBody.length
      const window = fullBody.slice(offset, offset + limit)
      const maxBytes = 256 * 1024
      const truncated = Buffer.byteLength(window, 'utf8') > maxBytes || offset + limit < totalChars
      return json({
        ok: true,
        record: card(record),
        body: truncated && Buffer.byteLength(window, 'utf8') > maxBytes ? `${bufferSlice(window, maxBytes)}\n…[truncated]` : window,
        truncated,
        bodyOffset: offset,
        bodyLimit: limit,
        bodyTotalChars: totalChars,
        bodyTruncated: truncated,
        path: record.path,
      })
    },

    async search(request) {
      const url = new URL(request.url)
      const scope = resolveWorkspace(ctx, url.searchParams.get('sessionId'), url.searchParams.get('cwd'))
      if (scope === undefined) return fail(404, 'MEMORY_UNKNOWN_SESSION', 'no live session for this memory panel')
      const query = String(url.searchParams.get('q') ?? '').trim()
      const limit = clamp(url.searchParams.get('limit'), 30, 1, 100)
      const workspaceKey = memoryWorkspaceKey(scope.cwd, scope.sessionId)
      const levels = await memory().getLevels(scope.sessionId)
      if (levels.l2 !== true && levels.l3 !== true) return json({ ok: true, levels, records: [] })
      const filter = visibleFilter({ workspaceKey, sessionId: scope.sessionId }, levels)
      if (query.length === 0) {
        const records = await memory().list({ ...filter, limit })
        return json({ ok: true, levels, records: records.map(card) })
      }
      const { hits } = await memory().search({ ...filter, query, limit })
      return json({
        ok: true,
        levels,
        records: hits.map((hit) => ({
          ...card(hit),
          snippet: hit.snippet,
        })),
      })
    },

    async level(request) {
      let body
      try {
        body = await request.json()
      } catch {
        return fail(400, 'MEMORY_INVALID_BODY', 'body must be JSON')
      }
      const { sessionId, cwd, level } = body ?? {}
      const scope = resolveWorkspace(ctx, sessionId, cwd)
      if (scope === undefined) return fail(404, 'MEMORY_UNKNOWN_SESSION', 'no live session for this memory panel')
      if (level !== 'l2' && level !== 'l3') {
        return fail(400, 'MEMORY_LEVEL_STICKY', 'levels are sticky: send level l2 or l3 to enable; disabling is not supported')
      }
      const levels = await memory().enableLevel(scope.sessionId, level)
      return json({ ok: true, levels, captureScope: memoryCaptureScope(levels) ?? null })
    },

    async compress(request) {
      let body
      try {
        body = await request.json()
      } catch {
        return fail(400, 'MEMORY_INVALID_BODY', 'body must be JSON')
      }
      const { sessionId, cwd, level, strategy, targetRatio, minAgeMs } = body ?? {}
      const scope = resolveWorkspace(ctx, sessionId, cwd)
      if (scope === undefined) return fail(404, 'MEMORY_UNKNOWN_SESSION', 'no live session for this memory panel')
      const levels = await memory().getLevels(scope.sessionId)
      const workspaceKey = memoryWorkspaceKey(scope.cwd, scope.sessionId)
      const requested = level === 'auto' || level === undefined
        ? ['l2', 'l3'].filter((candidate) => levels[candidate] === true)
        : [level]
      if (requested.length === 0) return fail(400, 'MEMORY_LEVELS_OFF', 'no extra-context level is enabled')
      if (strategy !== undefined && strategy !== 'cold') {
        return fail(400, 'MEMORY_DIGEST_REQUIRES_MODEL', 'digest requires the model tool; the panel compresses with the lossless cold strategy')
      }
      const reports = []
      for (const candidate of requested) {
        if (levels[candidate] !== true) return fail(400, 'MEMORY_LEVEL_STICKY', `${candidate.toUpperCase()} is not enabled`)
        const levelScope = candidate === 'l2' ? 'session' : 'workspace'
        const result = await memory().compressCold({
          workspaceKey,
          scope: levelScope,
          ...levelScope === 'session' ? { sessionId: scope.sessionId } : {},
          targetRatio: Number(targetRatio) || 0.6,
          minAgeMs: Number.isFinite(Number(minAgeMs)) ? Number(minAgeMs) : undefined,
        })
        const after = await memory().facets({
          workspaceKey,
          scope: levelScope,
          ...levelScope === 'session' ? { sessionId: scope.sessionId } : {},
        })
        await memory().recordCompression({
          sessionId: scope.sessionId,
          level: candidate,
          strategy: 'cold',
          beforeHot: result.before.hot,
          afterHot: Number(after.hotTokens ?? after.tokens) || 0,
          coldMoved: result.coldMoved.length,
          digests: 0,
          llmCalls: 0,
          errors: [],
        })
        reports.push({ level: candidate, targetTokens: result.targetTokens, beforeHot: result.before.hot, coldMoved: result.coldMoved.length, freedTokens: result.freedTokens })
      }
      const compression = await memory().compressionStats(scope.sessionId, 3)
      return json({ ok: true, reports, compression })
    },

    async metrics(request) {
      const url = new URL(request.url)
      const scope = resolveWorkspace(ctx, url.searchParams.get('sessionId'), url.searchParams.get('cwd'))
      if (scope === undefined) return fail(404, 'MEMORY_UNKNOWN_SESSION', 'no live session for this memory panel')
      const workspaceKey = memoryWorkspaceKey(scope.cwd, scope.sessionId)
      const levels = await memory().getLevels(scope.sessionId)
      const sessionFacets = await memory().facets({ workspaceKey, scope: 'session', sessionId: scope.sessionId })
      const workspaceFacets = await memory().facets({ workspaceKey, scope: 'workspace' })
      const visible = await memory().facets(visibleFilter({ workspaceKey, sessionId: scope.sessionId }, levels))
      const evictions = await memory().evictionStats(scope.sessionId)
      const compression = await memory().compressionStats(scope.sessionId, 5)
      return json({
        ok: true,
        generatedAt: Date.now(),
        levels,
        l2: { hotTokens: sessionFacets.hotTokens, coldTokens: sessionFacets.coldTokens, hotCount: sessionFacets.hotCount, coldCount: sessionFacets.coldCount, capacityTokens: sessionFacets.sessionCapacityTokens },
        l3: { hotTokens: workspaceFacets.hotTokens, coldTokens: workspaceFacets.coldTokens, hotCount: workspaceFacets.hotCount, coldCount: workspaceFacets.coldCount, capacityTokens: workspaceFacets.capacityTokens },
        visible: { hotTokens: visible.hotTokens, coldTokens: visible.coldTokens, count: visible.count, byKind: visible.byKind },
        l1Evicted: evictions,
        compression,
      })
    },

    async restore(request) {
      let body
      try {
        body = await request.json()
      } catch {
        return fail(400, 'MEMORY_INVALID_BODY', 'body must be JSON')
      }
      const { sessionId, cwd, id } = body ?? {}
      const scope = resolveWorkspace(ctx, sessionId, cwd)
      if (scope === undefined) return fail(404, 'MEMORY_UNKNOWN_SESSION', 'no live session for this memory panel')
      if (typeof id !== 'string' || id.length === 0) return fail(400, 'MEMORY_INVALID_ID', 'id is required')
      const record = await memory().get(id)
      const workspaceKey = memoryWorkspaceKey(scope.cwd, scope.sessionId)
      const levels = await memory().getLevels(scope.sessionId)
      if (record === undefined || !recordVisible(record, workspaceKey, scope.sessionId, levels)) {
        return fail(404, 'MEMORY_NOT_FOUND', 'no such memory record in the enabled extra-context levels')
      }
      if (record.cold !== true) return fail(400, 'MEMORY_NOT_COLD', 'record is already hot')
      const restored = await memory().restoreCold(id)
      return json({ ok: true, record: card(restored) })
    },

    async gc(request) {
      let body
      try {
        body = await request.json()
      } catch {
        return fail(400, 'MEMORY_INVALID_BODY', 'body must be JSON')
      }
      const { sessionId, cwd, keepTokens } = body ?? {}
      const scope = resolveWorkspace(ctx, sessionId, cwd)
      if (scope === undefined) return fail(404, 'MEMORY_UNKNOWN_SESSION', 'no live session for this memory panel')
      if (!Number.isFinite(Number(keepTokens)) || Number(keepTokens) < 0) {
        return fail(400, 'MEMORY_INVALID_QUOTA', 'keepTokens must be a non-negative number')
      }
      const levels = await memory().getLevels(scope.sessionId)
      const workspaceKey = memoryWorkspaceKey(scope.cwd, scope.sessionId)
      const reports = []
      if (levels.l2 === true) {
        const result = await memory().gcCold({ workspaceKey, scope: 'session', sessionId: scope.sessionId, keepTokens: Number(keepTokens) })
        reports.push({ level: 'l2', removed: result.removed.length, freedTokens: result.freedTokens })
      }
      if (levels.l3 === true) {
        const result = await memory().gcCold({ workspaceKey, scope: 'workspace', keepTokens: Number(keepTokens) })
        reports.push({ level: 'l3', removed: result.removed.length, freedTokens: result.freedTokens })
      }
      return json({ ok: true, reports })
    },

    async status(request) {
      let body
      try {
        body = await request.json()
      } catch {
        return fail(400, 'MEMORY_INVALID_BODY', 'body must be JSON')
      }
      const { sessionId, cwd, id, status } = body ?? {}
      const scope = resolveWorkspace(ctx, sessionId, cwd)
      if (scope === undefined) return fail(404, 'MEMORY_UNKNOWN_SESSION', 'no live session for this memory panel')
      if (typeof id !== 'string' || id.length === 0) return fail(400, 'MEMORY_INVALID_ID', 'id is required')
      if (status !== 'pinned' && status !== 'active' && status !== 'resolved' && status !== 'superseded') {
        return fail(400, 'MEMORY_INVALID_STATUS', 'status must be pinned, active, resolved or superseded')
      }
      const existing = await memory().get(id)
      const workspaceKey = memoryWorkspaceKey(scope.cwd, scope.sessionId)
      const levels = await memory().getLevels(scope.sessionId)
      if (existing === undefined || !recordVisible(existing, workspaceKey, scope.sessionId, levels)) {
        return fail(404, 'MEMORY_NOT_FOUND', 'no such memory record in the enabled extra-context levels')
      }
      const updated = await memory().setStatus(id, status)
      return json({ ok: true, record: card(updated) })
    },
  }
}

/** Register the four exact Fetch routes, owned by this plugin's fiber. */
export function apply(ctx) {
  const api = handlers(ctx)
  const routes = [
    { path: ROUTES.index, methods: ['GET'], requestBody: 'buffered', fetch: (request) => api.index(request) },
    { path: ROUTES.record, methods: ['GET'], requestBody: 'buffered', fetch: (request) => api.record(request) },
    { path: ROUTES.search, methods: ['GET'], requestBody: 'buffered', fetch: (request) => api.search(request) },
    { path: ROUTES.status, methods: ['POST'], requestBody: 'buffered', fetch: (request) => api.status(request) },
    { path: ROUTES.level, methods: ['POST'], requestBody: 'buffered', fetch: (request) => api.level(request) },
    { path: ROUTES.compress, methods: ['POST'], requestBody: 'buffered', fetch: (request) => api.compress(request) },
    { path: ROUTES.restore, methods: ['POST'], requestBody: 'buffered', fetch: (request) => api.restore(request) },
    { path: ROUTES.gc, methods: ['POST'], requestBody: 'buffered', fetch: (request) => api.gc(request) },
    { path: ROUTES.metrics, methods: ['GET'], requestBody: 'buffered', fetch: (request) => api.metrics(request) },
  ]
  for (const route of routes) {
    ctx.effect(() => ctx.connection.fetch.register(route), `memory-api: ${route.path}`)
  }
}
