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
  const tokenize = tokenizeText
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
  const tokenize = tokenizeText
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
    // Explicit title/useWhen relevance fallback: learned weights are not yet retrained
    // for CJK data, so exact title/useWhen overlap keeps Chinese queries from losing.
    score += 2 * features[2] + features[3]
    return { page, score }
  }).sort((left, right) => right.score - left.score)
}

function tokenizeText(value) {
  const text = String(value ?? '').toLowerCase()
  const tokens = text.match(/[a-z0-9_]+/g) ?? []
  const cjkRuns = text.match(/[\u3400-\u9fff]+/g) ?? []
  for (const run of cjkRuns) {
    for (let index = 0; index < run.length; index += 1) {
      tokens.push(run[index])
      if (index + 1 < run.length) tokens.push(run.slice(index, index + 2))
      if (index + 2 < run.length) tokens.push(run.slice(index, index + 3))
    }
  }
  return tokens
}

function isNearDuplicate(left, right) {
  const terms = (page) => new Set(tokenizeText(`${page.title ?? ''} ${page.summary ?? ''}`))
  const a = terms(left)
  const b = terms(right)
  if (a.size === 0 || b.size === 0) return false
  let shared = 0
  for (const term of a) if (b.has(term)) shared += 1
  return shared / Math.min(a.size, b.size) >= 0.8
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
  const available = Math.max(0, budgetTokens - reserveTokens)
  const pinned = new Set(Array.isArray(input.pinnedIds) ? input.pinnedIds : [])
  const coreIds = new Set(Array.isArray(input.alwaysIncludeIds) ? input.alwaysIncludeIds : [])
  const counter = typeof input.tokenCounter === 'function' ? input.tokenCounter : undefined
  const tokenizerName = typeof input.tokenizerName === 'string' ? input.tokenizerName : (counter === undefined ? 'chars/4' : 'custom')
  const tokenCost = (text) => counter === undefined ? estimateTokens(text) : counter(String(text))
  const pageCost = (page) => Number.isFinite(page.tokenCount) ? Math.max(1, Number(page.tokenCount)) : Math.max(1, tokenCost(pageText(page)))
  const pageTokenCap = Math.max(0, Number.isSafeInteger(input.pageTokenCap) ? input.pageTokenCap : 0)
  const queryForExcerpt = input.query === undefined ? '' : String(input.query)
  const preparePage = (page) => {
    if (pageTokenCap === 0 || pageCost(page) <= pageTokenCap) return page
    const originalBody = pageBody(page)
    const source = page.sourceId ?? page.id
    const maxChars = Math.max(80, pageTokenCap * 4)
    // For oversized records, select a snippet around a query term instead of always
    // taking the head; the full archive file is untouched and the source is marked.
    let start = 0
    if (queryForExcerpt.length > 0) {
      const terms = [...new Set(tokenizeText(queryForExcerpt).filter((term) => term.length >= 2))].sort((a, b) => b.length - a.length)
      const lower = originalBody.toLowerCase()
      for (const term of terms) {
        const index = lower.indexOf(term)
        if (index >= 0) {
          start = Math.max(0, index - Math.floor(maxChars * 0.35))
          break
        }
      }
    }
    const excerpt = originalBody.slice(start, start + maxChars).trimEnd()
    return {
      ...page,
      body: excerpt,
      truncated: true,
      sourceId: source,
      excerptStart: start,
    }
  }

  const byId = new Map()
  for (const [index, page] of (Array.isArray(input.pages) ? input.pages : []).entries()) {
    if (page === null || typeof page !== 'object' || typeof page.id !== 'string' || page.id.length === 0) continue
    byId.set(page.id, { ...page, sequence: pageSequence(page, index) })
  }
  const sorted = [...byId.values()].sort((left, right) => left.sequence - right.sequence || left.id.localeCompare(right.id)).map(preparePage)
  const renderEntries = (entries) => {
    const prefixText = entries.length === 0 ? '' : [
      `## Extra-context materialized window (${variant.id})`,
      `<!-- memex-materializer ${CONTEXT_MATERIALIZER_VERSION} -->`,
      ...entries.map((page) => `- ${page.id} · ${page.title ?? '(untitled)'}${page.useWhen === undefined ? '' : ` — ${page.useWhen}`}`),
    ].join('\n')
    const timelineLines = []
    for (const page of entries) {
      const header = page.role === undefined ? `### context page ${page.id}` : `### context page ${page.id} [role=${page.role}]`
      timelineLines.push(header)
      if (page.title !== undefined) timelineLines.push(`Title: ${page.title}`)
      timelineLines.push(pageBody(page))
      if (page.truncated === true) timelineLines.push(`> [truncated excerpt; source: ${page.sourceId ?? page.id}]`)
      timelineLines.push('')
    }
    const timelineText = timelineLines.join('\n').trimEnd()
    const text = entries.length === 0 ? '' : `${prefixText}\n\n${timelineText}`.trimEnd()
    return { text, prefixText, timelineText }
  }
  const canonicalEntries = (entries) => [...entries].sort((left, right) => left.sequence - right.sequence || left.id.localeCompare(right.id))
  const costFor = (entries) => tokenCost(renderEntries(canonicalEntries(entries)).text)
  const selected = []
  const forced = []
  const omitted = []
  let overBudgetReason = undefined
  const tryAdd = (page, force = false) => {
    if (selected.some((entry) => entry.id === page.id)) return true
    const forceIt = force === true
    if (!forceIt && costFor([...selected, page]) > available) return false
    selected.push(page)
    if (forceIt) {
      forced.push(page.id)
      const reason = coreIds.has(page.id) ? 'core' : pinned.has(page.id) ? 'pinned' : 'forced'
      if (costFor(selected) > available) overBudgetReason = reason
    }
    return true
  }
  // Core-fact pages are guaranteed before ordinary pinned/chronology selection.
  for (const page of sorted) if (coreIds.has(page.id)) tryAdd(page, true)
  for (const page of sorted) if (pinned.has(page.id)) tryAdd(page, true)
  if (variant.pinnedEdges) {
    const first = sorted.find((page) => !selected.some((entry) => entry.id === page.id))
    const last = [...sorted].reverse().find((page) => !selected.some((entry) => entry.id === page.id))
    for (const page of [first, last]) if (page !== undefined) tryAdd(page)
  }
  if (input.query !== undefined && input.learnedRerank !== undefined) {
    const ranked = learnedRerankPages(sorted, String(input.query), input.learnedRerank)
    const topK = Math.max(1, Number.isSafeInteger(input.learnedTopK) ? input.learnedTopK : 1)
    const maxPageTokens = Math.max(0, Number.isSafeInteger(input.learnedPageMaxTokens) ? input.learnedPageMaxTokens : 0)
    const diversify = input.diversify !== false
    // Objective: maximize relevance score first; break ties by lower page cost.
    // Budget remains a hard constraint checked on the final rendered order.
    ranked.sort((left, right) => {
      const leftScore = Number(left.score) || 0
      const rightScore = Number(right.score) || 0
      if (leftScore !== rightScore) return rightScore - leftScore
      return Math.max(1, pageCost(left.page)) - Math.max(1, pageCost(right.page))
    })
    let added = 0
    for (const { page } of ranked) {
      if (selected.some((entry) => entry.id === page.id)) continue
      if (maxPageTokens > 0 && pageCost(page) > maxPageTokens) continue
      if (diversify && selected.some((entry) => isNearDuplicate(entry, page))) continue
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
  const rendered = renderEntries(selected)
  const { text, prefixText, timelineText } = rendered
  const chars = text.length
  const actualTokens = text.length === 0 ? 0 : tokenCost(text)
  const prefixTokens = prefixText.length === 0 ? 0 : tokenCost(prefixText)
  const bodyTokens = selected.reduce((sum, page) => sum + tokenCost(pageBody(page)), 0)
  const pageTokens = bodyTokens
  const overBudgetBy = Math.max(0, actualTokens - available)
  const budgetStatus = selected.length === 0
    ? (available === 0 ? 'empty' : 'empty-budget')
    : (overBudgetBy > 0 ? 'exceeded' : 'ok')
  return {
    text,
    prefixText,
    stablePrefixHash: stableHash(prefixText),
    includedIds: selected.map((page) => page.id),
    omittedIds: omitted,
    forcedIds: forced,
    truncatedIds: selected.filter((page) => page.truncated === true).map((page) => page.sourceId ?? page.id),
    tokens: actualTokens,
    budgetTokens,
    reserveTokens,
    availableTokens: available,
    overBudgetBy,
    overBudgetReason: overBudgetBy > 0 ? (overBudgetReason ?? (forced.length > 0 ? 'forced' : 'budget')) : undefined,
    budgetStatus,
    budgetBreakdown: {
      pageTokens: bodyTokens,
      prefixTokens,
      formatTokens: Math.max(0, actualTokens - prefixTokens - bodyTokens),
      reservedTokens: reserveTokens,
      totalTokens: actualTokens,
      renderedChars: chars,
      chars,
      tokenizer: tokenizerName,
      estimateError: counter === undefined ? 'chars/4 heuristic on final rendered text; tokenizer-specific error not measured' : 'custom tokenizer supplied; final rendered text counted',
    },
    variant,
    order: selected.map((page) => page.id),
    requiresKV: variant.requiresKV,
  }
}
