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
