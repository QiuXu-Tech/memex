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
import { memoryQueryTerms } from '../index.js'

export const CONTEXT_PAGER_VERSION = '0.14.0'

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
 * @param {string} [input.query] - Current query used for bounded search and optional learned reranking.
 * @param {object} [input.learnedRerank] - Optional learned reranker weights.
 * @param {string[]} [input.alwaysIncludeIds] - Core-fact records always included.
 * @param {number} [input.learnedPageMaxTokens] - Skip learned candidates above this token size.
 * @param {number} [input.pageTokenCap] - Excerpt oversized page bodies before selection.
 * @param {Function} [input.tokenCounter] - Count tokens in rendered text.
 * @param {string} [input.tokenizerName] - Name of the supplied token counter.
 * @param {boolean} [input.enforceTotalBudget] - Enforce total returned tokens <= budget.
 * @param {boolean} [input.diversify] - Skip near-duplicate learned candidates.
 * @param {boolean} [input.includeCanonicalEvents=true]
 */
const ARCHIVE_CARD_TOKENS = 2000
const CARD_HEADINGS = ['Primary Request and Intent', 'Key Technical Concepts', 'Files and Code', 'Errors and fixes', 'Pending Tasks', 'Current Work', 'Optional Next Step']

/** Project an oversized archive row into a source-marked card; the record file stays intact. */
function archiveCard(row, query) {
  const body = String(row.body ?? row.summary ?? '')
  const lower = body.toLowerCase()
  const terms = memoryQueryTerms(query ?? '', 20).filter((term) => term.length >= 3).sort((a, b) => b.length - a.length)
  const match = terms.map((term) => lower.indexOf(term.toLowerCase())).find((index) => index >= 0)
  if (match !== undefined) {
    const start = Math.max(0, match - 100)
    return `> [archive card; source: ${row.id}; original archive remains intact]\n\n# ${row.title ?? row.id}\n\n${body.slice(start, start + 1200).trimEnd()}\n\n> [end archive card]`
  }
  const sections = []
  for (const heading of CARD_HEADINGS) {
    const start = body.indexOf(`## ${heading}`)
    if (start < 0) continue
    let end = body.length
    for (const other of CARD_HEADINGS) {
      const next = body.indexOf(`## ${other}`, start + 3)
      if (next >= 0) end = Math.min(end, next)
    }
    sections.push(body.slice(start, end).trim())
  }
  const excerpt = sections.length > 0 ? sections.join('\n\n') : body.slice(0, 2000)
  return `> [archive card; source: ${row.id}; original archive remains intact]\n\n# ${row.title ?? row.id}\n\n${excerpt.slice(0, 4000).trimEnd()}\n\n> [end archive card]`
}

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
  const noVisibleScopes = Array.isArray(input.scopes) && !input.scopes.some((scope) => scope === 'workspace' || scope === 'session')
  const queries = typeof input.query === 'string' && input.query.trim() !== ''
    ? [...new Set([input.query, ...(Array.isArray(input.queryAlternatives) ? input.queryAlternatives.filter((q) => typeof q === 'string' && q.trim() && q.length <= 160).slice(0, 3) : [])])]
    : []
  const searchResults = !noVisibleScopes && typeof store.search === 'function' ? queries.map((query) => store.search({ ...filter, query, limit: 8, excludeSuperseded: true }).hits) : []
  const fused = new Map()
  for (const hits of searchResults) for (const [rank, row] of hits.entries()) {
    const entry = fused.get(row.id) ?? { row, score: 0 }
    entry.score += 1 / (60 + rank + 1)
    fused.set(row.id, entry)
  }
  const queryHits = [...fused.values()].sort((a, b) => b.score - a.score).map((entry) => entry.row).filter((row) => {
      if (row.status === 'superseded') return false
      if (input.workspaceKey !== undefined && row.workspaceKey !== input.workspaceKey) return false
      if (input.kind !== undefined && row.kind !== input.kind) return false
      if (Array.isArray(input.scopes) && !input.scopes.includes(row.scope)) return false
      if (row.scope === 'session' && row.sessionId !== input.sessionId) return false
      return true
    }).slice(0, 8)
  const rows = noVisibleScopes ? [] : byId([
    ...store.list({ ...filter, status: 'pinned', limit: 24, includeStatus: true }),
    ...store.list({ ...filter, status: 'open', limit: 16 }),
    ...store.list({ ...filter, limit: 40 }),
    ...queryHits,
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
      const record = typeof store.get === 'function' ? store.get(row.id) : row
      if (record === undefined) continue
      if (row.workspaceKey !== undefined && record.workspaceKey !== row.workspaceKey) continue
      if (row.scope !== undefined && record.scope !== row.scope) continue
      if (row.sessionId !== undefined && record.sessionId !== row.sessionId) continue
      const rawBody = String(record.body ?? record.summary ?? '')
      const estimated = Number.isFinite(row.tokens) ? Number(row.tokens) : Math.ceil(rawBody.length / 4)
      const isArchive = estimated > ARCHIVE_CARD_TOKENS && (row.kind === 'episode' || rawBody.includes('<compacted-summary>') || /^L1 归档/.test(String(row.title ?? '')))
      sources.push({ recordId: row.id, source: isArchive ? 'record-card' : record.body === undefined ? 'record-summary' : 'record', events: 0 })
      pages.push({
        id: row.id,
        title: isArchive ? `[card] ${row.title ?? row.id}` : row.title,
        summary: row.summary,
        useWhen: row.useWhen,
        body: isArchive ? archiveCard({ ...row, body: rawBody }, queries.join(' ')) : rawBody,
        card: isArchive,
        sourceId: isArchive ? row.id : undefined,
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
    queryAlternatives: queries.slice(1),
    learnedRerank: input.learnedRerank,
    learnedTopK: input.learnedTopK,
    alwaysIncludeIds: input.alwaysIncludeIds,
    learnedPageMaxTokens: input.learnedPageMaxTokens,
    retrievedIds: queryHits.map((row) => row.id),
    pageTokenCap: input.pageTokenCap,
    tokenCounter: input.tokenCounter,
    tokenizerName: input.tokenizerName,
    enforceTotalBudget: input.enforceTotalBudget,
    diversify: input.diversify,
  })
  return { ...materialized, sources, pages: pages.length, pager: CONTEXT_PAGER_VERSION }
}
