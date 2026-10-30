/**
 * Context materialization (v0 direction: from "memory retrieval" to
 * "extra-context virtualization").
 *
 * A model's true context is an ordered token stream inside one forward pass.
 * The store can only provide pages; this module turns a resident set of pages
 * into a deterministic, budgeted, prompt-cache-friendly materialization. It is
 * the seam where a learned context specialist (encoder / assembler / KV pager)
 * can later replace the heuristic layout without changing callers.
 */
import { createHash } from 'node:crypto'
import { estimateTokens } from '../index.js'

export const CONTEXT_MATERIALIZER_VERSION = '0.11.0'

/**
 * Variants are *layout / specialist* descriptors, not trained models yet.
 * - timeline-exact: chronological verbatim pages, stable index prefix.
 * - edge-attention: chronology with pinned attention edges (first/last).
 * - context-specialist-v1: slot for a transformer context specialist; requires
 *   a host that can page KV blocks. Heuristic fallback is timeline ordering.
 */
export const CONTEXT_VARIANTS = Object.freeze([
  Object.freeze({
    id: 'timeline-exact',
    label: 'Chronological verbatim materialization',
    ordering: 'sequence',
    pinnedEdges: false,
    requiresKV: false,
    description: 'Pages rendered in write/sequence order with a stable index prefix.',
  }),
  Object.freeze({
    id: 'edge-attention',
    label: 'Chronological with attention-edge pinning',
    ordering: 'sequence',
    pinnedEdges: true,
    requiresKV: false,
    description: 'Pinned first/last pages are kept at the attention edges; middle pages fill the budget.',
  }),
  Object.freeze({
    id: 'context-specialist-v1',
    label: 'Transformer context-specialist layout (experimental)',
    ordering: 'salience+sequence',
    pinnedEdges: true,
    requiresKV: true,
    description: 'Interface slot for a learned context encoder/assembler and KV-block paging; heuristic fallback is chronology.',
  }),
])

export function resolveContextVariant(id = 'timeline-exact') {
  return CONTEXT_VARIANTS.find((variant) => variant.id === id) ?? CONTEXT_VARIANTS[0]
}

const pageText = (page) => `${page.id} ${page.title ?? ''} ${page.summary ?? ''} ${page.useWhen ?? ''} ${page.body ?? ''}`
const pageTokens = (page) => Number.isFinite(page.tokenCount) ? Math.max(1, Number(page.tokenCount)) : Math.max(1, estimateTokens(pageText(page)))
const pageSequence = (page, index) => Number.isFinite(page.sequence) ? Number(page.sequence) : (Number.isFinite(page.createdAt) ? Number(page.createdAt) : index)
const pageBody = (page) => String(page.body ?? page.summary ?? '')

function lexicalFeatures(query, page, idf) {
  const tokenize = (value) => String(value ?? '').toLowerCase().match(/[a-z0-9_]+/g) ?? []
  const queryTerms = [...new Set(tokenize(query))]
  const pageTerms = tokenize(`${page.title ?? ''} ${page.body ?? ''} ${page.useWhen ?? ''}`)
  const pageSet = new Set(pageTerms)
  const titleSet = new Set(tokenize(page.title))
  const useSet = new Set(tokenize(page.useWhen))
  let overlap = 0
  let queryNorm = 0
  let bodyNorm = 0
  for (const term of queryTerms) queryNorm += idf.get(term) ?? 0
  for (const term of pageTerms) bodyNorm += idf.get(term) ?? 0
  for (const term of queryTerms) if (pageSet.has(term)) overlap += idf.get(term) ?? 0
  return [
    overlap / (queryNorm || 1),
    overlap / (bodyNorm || 1),
    [...queryTerms].filter((term) => titleSet.has(term)).length / Math.max(1, titleSet.size),
    [...queryTerms].filter((term) => useSet.has(term)).length / Math.max(1, useSet.size),
    Math.min(1, String(page.body ?? '').length / 4000),
    page.kind === 'decision' ? 1 : 0,
    1,
  ]
}

function learnedRerankPages(pages, query, reranker) {
  if (!query || !reranker || !Array.isArray(reranker.weights)) return []
  const tokenize = (value) => String(value ?? '').toLowerCase().match(/[a-z0-9_]+/g) ?? []
  const documents = pages.map((page) => [...new Set(tokenize(`${page.title ?? ''} ${page.body ?? ''} ${page.useWhen ?? ''}`))])
  const documentFrequency = new Map()
  for (const document of documents) for (const term of document) documentFrequency.set(term, (documentFrequency.get(term) ?? 0) + 1)
  const idf = new Map()
  for (const [term, frequency] of documentFrequency) idf.set(term, Math.log((pages.length + 1) / (frequency + 0.5)))
  const bias = Number(reranker.bias ?? 0)
  return pages.map((page) => {
    const features = lexicalFeatures(query, page, idf)
    let score = bias
    for (let index = 0; index < features.length; index += 1) score += features[index] * Number(reranker.weights[index] ?? 0)
    return { page, score }
  }).sort((left, right) => right.score - left.score)
}

function stableHash(text) {
  return createHash('sha256').update(String(text), 'utf8').digest('hex').slice(0, 16)
}

/**
 * Materialize a resident page set into a deterministic context block.
 *
 * @param {object} input
 * @param {Array<object>} input.pages - Resident pages (`id`, `title`, `summary`, `body`, `sequence`/`createdAt`, optional `role`).
 * @param {number} [input.budgetTokens=2400] - Budget for the materialized window.
 * @param {string} [input.variant='timeline-exact'] - One of CONTEXT_VARIANTS.
 * @param {string[]} [input.pinnedIds=[]] - Pages forced into the window.
 * @param {number} [input.reserveTokens=0] - Space reserved for the live question/tail.
 * @returns {{text:string, prefixText:string, stablePrefixHash:string, includedIds:string[], omittedIds:string[], tokens:number, budgetTokens:number, variant:object, order:string[], requiresKV:boolean}}
 */
export function materializeContext(input = {}) {
  const variant = resolveContextVariant(input.variant)
  const budgetTokens = Math.max(0, Number(input.budgetTokens ?? 2400))
  const reserveTokens = Math.max(0, Number(input.reserveTokens ?? 0))
  const usable = Math.max(0, budgetTokens - reserveTokens)
  const pinned = new Set(Array.isArray(input.pinnedIds) ? input.pinnedIds : [])
  // Stable de-duplication: keep the last occurrence of an id, then sort by the
  // original page sequence/creation time.
  const byId = new Map()
  for (const [index, page] of (Array.isArray(input.pages) ? input.pages : []).entries()) {
    if (page === null || typeof page !== 'object' || typeof page.id !== 'string' || page.id.length === 0) continue
    byId.set(page.id, { ...page, sequence: pageSequence(page, index) })
  }
  const sorted = [...byId.values()].sort((left, right) => left.sequence - right.sequence || left.id.localeCompare(right.id))
  const selected = []
  const omitted = []
  let used = 0
  const tryAdd = (page, force = false) => {
    if (selected.some((entry) => entry.id === page.id)) return true
    const tokens = pageTokens(page)
    if (!force && used + tokens > usable) return false
    selected.push(page)
    used += tokens
    return true
  }
  // Pinned pages first (they are the orientation anchors), then chronology.
  for (const page of sorted) if (pinned.has(page.id)) tryAdd(page, true)
  if (variant.pinnedEdges) {
    const first = sorted.find((page) => !selected.some((entry) => entry.id === page.id))
    const last = [...sorted].reverse().find((page) => !selected.some((entry) => entry.id === page.id))
    for (const page of [first, last]) if (page !== undefined) tryAdd(page)
  }
  if (input.query !== undefined && input.learnedRerank !== undefined) {
    const ranked = learnedRerankPages(sorted, String(input.query), input.learnedRerank)
    const topK = Math.max(1, Number.isSafeInteger(input.learnedTopK) ? input.learnedTopK : 1)
    let added = 0
    for (const { page } of ranked) {
      if (selected.some((entry) => entry.id === page.id)) continue
      if (tryAdd(page)) {
        added += 1
        if (added >= topK) break
      }
    }
  }
  for (const page of sorted) {
    if (!tryAdd(page)) omitted.push(page.id)
  }
  selected.sort((left, right) => left.sequence - right.sequence || left.id.localeCompare(right.id))
  const indexLines = selected.map((page) => `- ${page.id} · ${page.title ?? '(untitled)'}${page.useWhen === undefined ? '' : ` — ${page.useWhen}`}`)
  const prefixText = [
    `## Extra-context materialized window (${variant.id})`,
    `<!-- memex-materializer ${CONTEXT_MATERIALIZER_VERSION} -->`,
    ...indexLines,
  ].join('\n')
  const timelineLines = []
  for (const page of selected) {
    const header = page.role === undefined ? `### context page ${page.id}` : `### context page ${page.id} [role=${page.role}]`
    timelineLines.push(header)
    if (page.title !== undefined) timelineLines.push(`Title: ${page.title}`)
    timelineLines.push(pageBody(page))
    timelineLines.push('')
  }
  const timelineText = timelineLines.join('\n').trimEnd()
  const text = `${prefixText}\n\n${timelineText}`.trimEnd()
  const actualTokens = selected.reduce((sum, page) => sum + pageTokens(page), 0) + estimateTokens(prefixText)
  return {
    text,
    prefixText,
    stablePrefixHash: stableHash(prefixText),
    includedIds: selected.map((page) => page.id),
    omittedIds: omitted,
    tokens: actualTokens,
    budgetTokens,
    variant,
    order: selected.map((page) => page.id),
    requiresKV: variant.requiresKV,
  }
}
