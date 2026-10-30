/**
 * Context pager (context-materialization step 2).
 *
 * Selects a resident set from the store (pinned/open/recent hot pages), uses
 * canonical events when they exist, and hands the set to the deterministic
 * materializer. The pager never invents content; it either replays canonical
 * events or falls back to the rendered record body.
 */
import { materializeContext, resolveContextVariant } from './context-materializer.js'
import { eventsToMaterializerPages } from './context-events.js'

export const CONTEXT_PAGER_VERSION = '0.12.0'

const byId = (rows) => {
  const map = new Map()
  for (const row of rows) if (row !== undefined && row !== null && typeof row.id === 'string') map.set(row.id, row)
  return [...map.values()]
}

/**
 * @param {object} input
 * @param {import('./store.js').LocalStoreCore} input.store
 * @param {string} input.workspaceKey
 * @param {string[]} [input.scopes]
 * @param {string} [input.sessionId]
 * @param {number} [input.budgetTokens]
 * @param {string} [input.variant]
 * @param {string[]} [input.pinnedIds]
 * @param {string} [input.query] - Current user query for optional learned reranking.
 * @param {object} [input.learnedRerank] - Optional learned reranker weights.
 * @param {boolean} [input.includeCanonicalEvents=true]
 */
export function materializeStoreContext(input = {}) {
  const store = input.store
  if (store === undefined || typeof store.list !== 'function') throw new TypeError('materializeStoreContext: store is required')
  const filter = {
    workspaceKey: input.workspaceKey,
    scopes: input.scopes,
    sessionId: input.sessionId,
    kind: input.kind,
    status: undefined,
  }
  const rows = byId([
    ...store.list({ ...filter, status: 'pinned', limit: 24, includeStatus: true }),
    ...store.list({ ...filter, status: 'open', limit: 16 }),
    ...store.list({ ...filter, limit: 40 }),
  ])
  const pinnedIds = new Set(Array.isArray(input.pinnedIds) ? input.pinnedIds : rows.filter((row) => row.status === 'pinned').map((row) => row.id))
  const pages = []
  const sources = []
  for (const row of rows) {
    const canonical = input.includeCanonicalEvents === false || typeof store.listContextEvents !== 'function' ? [] : store.listContextEvents(row.id)
    if (canonical.length > 0) {
      sources.push({ recordId: row.id, source: 'canonical', events: canonical.length })
      for (const page of eventsToMaterializerPages(canonical)) pages.push({ ...page, id: `${row.id}:${page.id}`, recordId: row.id, pinned: pinnedIds.has(row.id) })
    } else {
      sources.push({ recordId: row.id, source: 'record', events: 0 })
      pages.push({
        id: row.id,
        title: row.title,
        summary: row.summary,
        useWhen: row.useWhen,
        body: row.body ?? row.summary ?? '',
        sequence: Number(row.createdAt ?? 0),
        createdAt: Number(row.createdAt ?? 0),
        pinned: pinnedIds.has(row.id),
      })
    }
  }
  const variant = resolveContextVariant(input.variant)
  const materialized = materializeContext({
    pages,
    budgetTokens: input.budgetTokens,
    variant: variant.id,
    pinnedIds: pages.filter((page) => page.pinned === true).map((page) => page.id),
    reserveTokens: input.reserveTokens,
    query: input.query,
    learnedRerank: input.learnedRerank,
  })
  return { ...materialized, sources, pages: pages.length, pager: CONTEXT_PAGER_VERSION }
}
