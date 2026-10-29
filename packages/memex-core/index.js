/**
 * Agent-agnostic memory core: record vocabulary, workspace identity, query-term
 * extraction, token accounting, and the model-visible message shape.
 *
 * This module has **no host dependencies** — no Cordis, no DSH packages, no
 * network. The DSH seam (`@qiuxu/memex-seam`) re-exports it and adds the
 * `ctx.memory` service; the MCP server and the Claude Code / Codex adapters use
 * it directly, so every agent integration shares one memory model.
 *
 * @module @qiuxu/memex-core
 */
import { createHash } from 'node:crypto'

/** Source kind carried by every model-visible memory message this subsystem injects. */
export const MEMORY_SOURCE_KIND = 'memory-recall'

/** Closed set of record kinds. A card explains WHEN to read a record; the kind says WHAT it is. */
export const MEMORY_KINDS = Object.freeze([
  'episode',
  'decision',
  'fact',
  'procedure',
  'open-thread',
  'incident',
  'artifact',
])

/** Visibility scopes a record can live in. */
export const MEMORY_SCOPES = Object.freeze(['session', 'workspace'])

/**
 * Legacy single-mode vocabulary, kept so stored settings and older consumers
 * can still be read and migrated onto the sticky cache levels.
 */
export const MEMORY_MODES = Object.freeze(['off', 'session', 'workspace'])

/**
 * Cache-level names for the extra-context hierarchy. L1 is the model's native
 * context window (not stored here); L2 is the session-private extra context;
 * L3 is the workspace-shared extra context.
 */
export const MEMORY_LEVELS = Object.freeze(['l2', 'l3'])

/**
 * Storage scope of one cache level: L2 -> session-private, L3 -> workspace.
 */
export const MEMORY_LEVEL_SCOPE = Object.freeze({ l2: 'session', l3: 'workspace' })

/**
 * Target scope for newly captured context: the deepest enabled level wins
 * (L3 over L2); `undefined` when both levels are off.
 * @param {{l2?: boolean, l3?: boolean}} levels - Enabled levels.
 * @returns {'session' | 'workspace' | undefined} Capture scope.
 */
export function memoryCaptureScope(levels) {
  if (levels?.l3 === true) return 'workspace'
  if (levels?.l2 === true) return 'session'
  return undefined
}

/**
 * Scopes visible to a session given its enabled levels.
 * @param {{l2?: boolean, l3?: boolean}} levels - Enabled levels.
 * @returns {('session'|'workspace')[]} Visible scopes.
 */
export function memoryVisibleScopes(levels) {
  const scopes = []
  if (levels?.l2 === true) scopes.push('session')
  if (levels?.l3 === true) scopes.push('workspace')
  return scopes
}

/**
 * Canonical level list from a stored settings row (sticky booleans).
 * @param {{l2?: number|boolean, l3?: number|boolean}} row - Stored settings.
 * @returns {{l2: boolean, l3: boolean}} Enabled levels.
 */
export function memoryLevelsFromRow(row) {
  return { l2: Number(row?.l2) === 1, l3: Number(row?.l3) === 1 }
}

/** Record lifecycle status. `pinned` records are always shown in the catalog. */
export const MEMORY_STATUSES = Object.freeze(['active', 'open', 'resolved', 'superseded', 'pinned'])

/** Trust level of the record content. `untrusted` content must never be obeyed as instructions. */
export const MEMORY_TRUST = Object.freeze(['trusted', 'untrusted', 'derived'])

/** Longest accepted title / summary / use-when text, in Unicode code points. */
export const MEMORY_TEXT_LIMITS = Object.freeze({
  title: 160,
  summary: 2000,
  useWhen: 300,
  body: 8 * 1024 * 1024,
})

/**
 * Derive the stable workspace key used to partition records.
 *
 * The key is derived from the session working directory, so every session in
 * one workspace shares a memory namespace, and two different checkouts never
 * do. A caller without a working directory falls back to its session id so it
 * still gets a private bucket instead of an error.
 *
 * @param {string | undefined} cwd - Working directory of the calling session.
 * @param {string | undefined} sessionId - Fallback identity for a session without a cwd.
 * @returns {string} A filesystem-safe 16-hex key, or `'global'` for the shared namespace.
 */
export function memoryWorkspaceKey(cwd, sessionId) {
  const source = typeof cwd === 'string' && cwd.length > 0 ? `cwd:${cwd}` : `session:${sessionId ?? ''}`
  return createHash('sha256').update(source).digest('hex').slice(0, 16)
}

/**
 * Create and freeze a model-visible memory message.
 *
 * Memory messages are ordinary user-role messages carrying the
 * {@link MEMORY_SOURCE_KIND} source, so the session log, replay and forks keep
 * working without a new event type. The source payload records which records
 * were shown and why, which makes replay auditable.
 *
 * This helper is the seam-level message shape; the checkpoint policy builds its
 * messages through it so every injected memory message stays identical.
 *
 * @param {object} input - Message input.
 * @param {'checkpoint' | 'catalog' | 'recall' | 'l1-eviction' | 'capacity-notice'} input.form - Which surface this message is.
 * @param {string} input.text - Bounded markdown body describing the recall.
 * @param {object} [input.meta] - Structured provenance for the source payload.
 * @returns {object} A frozen user message ready for `agent/pre-step` or `session.inject`.
 */
export function memoryMessage(input) {
  if (typeof input?.text !== 'string' || input.text.length === 0) {
    throw new TypeError('memory message requires non-empty text')
  }
  return Object.freeze({
    id: `msg_${createHash('sha256').update(`${input.form}\u0000${input.text}\u0000${Date.now()}\u0000${Math.random()}`).digest('hex').slice(0, 20)}`,
    role: 'user',
    content: Object.freeze([Object.freeze({ type: 'text', text: input.text })]),
    source: Object.freeze({
      kind: MEMORY_SOURCE_KIND,
      form: input.form,
      version: 1,
      ...(input.meta ?? {}),
    }),
  })
}

// ── Cordis-free helpers shared by the backend and policy packages ──────────

/** Common query stopwords that carry no retrieval signal. */
const QUERY_STOPWORDS = new Set([
  'the', 'a', 'an', 'and', 'or', 'to', 'of', 'in', 'for', 'with', 'from', 'is', 'are', 'was', 'were',
  'how', 'what', 'when', 'where', 'why', 'which', 'who', 'this', 'that', 'it', 'be', 'can', 'do', 'does',
  '什么', '怎么', '如何', '为什', '是否', '可以', '我们', '你们', '他们', '这个', '那个', '现在', '一下',
  '需要', '应该', '还是', '请问', '帮忙', '有没', '没有', '以及', '然后', '就是', '一个', '这些', '那些',
])

/**
 * Extract bounded, retrieval-oriented terms from a natural-language query.
 *
 * Long natural-language messages are poor full-text queries (especially CJK,
 * where a whole sentence is one huge token), so the store searches over
 * extracted terms instead: latin identifiers, quoted spans, and CJK n-grams.
 * The same helper drives auto-recall so all retrieval paths agree.
 *
 * @param {string} text - Raw query or user message.
 * @param {number} [maxTerms] - Term budget (default 20).
 * @returns {string[]} Deduplicated terms, longest/most specific first.
 */
export function memoryQueryTerms(text, maxTerms = 20) {
  const source = String(text ?? '')
  const terms = []
  const seen = new Set()
  const push = (term) => {
    const value = term.trim()
    if (value.length === 0) return
    const key = value.toLowerCase()
    if (seen.has(key) || QUERY_STOPWORDS.has(key)) return
    seen.add(key)
    terms.push(value)
  }
  // Quoted spans are explicit phrases.
  for (const match of source.matchAll(/[`"“”'']([^`"“”'']{2,60})[`"“”'']/g)) push(match[1])
  // Latin identifiers (paths, error codes, names) keep their punctuation.
  for (const match of source.matchAll(/[A-Za-z][A-Za-z0-9_.:/-]{1,}/g)) {
    push(match[0])
    push(match[0].toLowerCase())
  }
  // CJK n-grams: whole runs (capped), trigrams then bigrams.
  for (const match of source.matchAll(/[\u4e00-\u9fff]{2,}/g)) {
    const run = match[0]
    push(run.slice(0, 12))
    if (run.length >= 3) {
      for (let index = 0; index + 3 <= run.length && index < 10; index += 1) push(run.slice(index, index + 3))
    }
    for (let index = 0; index + 2 <= run.length && index < 10; index += 1) push(run.slice(index, index + 2))
  }
  return terms.slice(0, maxTerms)
}

/**
 * Default retrieval rerank weights (see store.search).
 *
 * Profiles may override individual weights to tune ranking for a model family:
 * e.g. CJK-heavy models boost the cold `abstract` field, tool-oriented models
 * boost `useWhen`, long-context models damp `recency`. The store merges these
 * with `query.rerank`.
 */
export const DEFAULT_RERANK_WEIGHTS = Object.freeze({
  title: 3,
  summary: 1.4,
  useWhen: 1.2,
  tags: 1.6,
  abstract: 0.9,
  body: 4.5,
  coldAnchor: 30,
  recency: 0.4,
  coldPenalty: 0.1,
  bm25: 0.8,
})

/** Approximate token count used for accounting when the caller has no exact number. */
export function estimateTokens(text) {
  return Math.max(1, Math.ceil(String(text ?? '').length / 4))
}

/** Clip a string to a code-point budget, appending an explicit omission marker. */
export function clipText(text, max, marker = '…') {
  const value = String(text ?? '')
  const points = Array.from(value)
  if (points.length <= max) return value
  return `${points.slice(0, Math.max(0, max - marker.length)).join('')}${marker}`
}

/** A stable id for an archived compaction; retrying the same compaction never creates a duplicate. */
export function archiveRecordId(sessionId, compactionId) {
  return `mem_${createHash('sha256').update(`${sessionId}\u0000${compactionId}`).digest('hex').slice(0, 10)}`
}
