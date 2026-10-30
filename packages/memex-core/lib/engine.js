/**
 * Agent memory engine: one small facade over the core store + model profile.
 *
 * Used by every non-DSH integration (MCP server, Claude Code hooks, Codex
 * helper). It owns:
 *  - a LocalStoreCore rooted at `root` (default `$MEMEX_HOME`),
 *  - the sticky level settings for one session,
 *  - scope selection (deepest enabled level wins),
 *  - profile-aware token accounting for writes and reads,
 *  - catalog / search / grep / open / restore / cold-compress helpers.
 *
 * @module @qiuxu/memex-core/engine
 */
import { existsSync } from 'node:fs'
import { homedir } from 'node:os'
import { join } from 'node:path'
import { LocalStoreCore } from './store.js'
import { materializeStoreContext } from './context-pager.js'
import { memoryCaptureScope, memoryVisibleScopes, memoryWorkspaceKey } from '../index.js'
import { clipToProfileTokens, profileTokens, resolveModelProfile } from './model-profiles.js'

/** Default storage location for non-DSH agents (with legacy DSH_MEMORY_HOME fallback). */
export function defaultMemoryRoot() {
  if (process.env.MEMEX_HOME !== undefined) return process.env.MEMEX_HOME
  if (process.env.DSH_MEMORY_HOME !== undefined) return process.env.DSH_MEMORY_HOME
  const preferred = join(homedir(), '.memex')
  const legacy = join(homedir(), '.dsh-memory')
  return existsSync(legacy) && !existsSync(preferred) ? legacy : preferred
}

/**
 * Facade over one memory root for one agent session.
 */
export class AgentMemory {
  /**
   * @param {object} options - Engine options.
   * @param {string} [options.root] - Storage root (default `$MEMEX_HOME` or `~/.memex`).
   * @param {string} [options.cwd] - Workspace directory used to derive the workspace key.
   * @param {string} [options.workspaceKey] - Explicit workspace key.
   * @param {string} [options.sessionId] - Session identity (for L2).
   * @param {string[]} [options.levels] - Enabled levels (`l2`/`l3`).
   * @param {string} [options.model] - Model id used to resolve the profile.
   * @param {string} [options.agent] - Integration name recorded in provenance.
   * @param {number} [options.capacityTokens] - L3 capacity (default 100M).
   * @param {number} [options.sessionCapacityTokens] - L2 capacity (default 10M).
   * @param {object} [options.profileOverrides] - Per-integration model-profile overrides
   *   (e.g. `{ rerank: { tags: 1.9 }, windowTokens: 128000 }`).
   */
  constructor(options = {}) {
    this.root = options.root ?? defaultMemoryRoot()
    this.cwd = options.cwd ?? process.cwd()
    this.sessionId = options.sessionId ?? process.env.MEMEX_SESSION ?? process.env.DSH_MEMORY_SESSION ?? 'default-session'
    this.workspaceKey = options.workspaceKey ?? memoryWorkspaceKey(this.cwd, this.sessionId)
    this.agent = options.agent ?? 'generic-agent'
    this.modelId = options.model ?? ''
    this.profile = resolveModelProfile(this.modelId, options.profileOverrides ?? {})
    this.store = new LocalStoreCore({
      root: this.root,
      capacityTokens: options.capacityTokens ?? 100_000_000,
      sessionCapacityTokens: options.sessionCapacityTokens ?? 10_000_000,
      defaultLevels: { l2: false, l3: false },
    })
    const requested = Array.isArray(options.levels) && options.levels.length > 0 ? options.levels : this.profile.levels
    for (const level of requested) {
      if (level === 'l2' || level === 'l3') this.store.enableLevel(this.sessionId, level)
    }
    this.close = this.close.bind(this)
  }

  /** Current sticky levels for this session. */
  get levels() {
    return this.store.getLevels(this.sessionId)
  }

  /** Scopes visible under the current levels. */
  get scopes() {
    return memoryVisibleScopes(this.levels)
  }

  /** Scope a new record should be captured into (deepest enabled level). */
  captureScope() {
    return memoryCaptureScope(this.levels) ?? 'workspace'
  }

  /** Estimated tokens for a text under the effective model profile. */
  tokens(text) {
    return profileTokens(text, this.profile)
  }

  /**
   * Store one record.
   * @param {object} input - Record input (kind/title/body required).
   * @returns {object} Stored record card.
   */
  write(input) {
    const scope = input?.scope === 'session' || input?.scope === 'workspace' ? input.scope : this.captureScope()
    const body = String(input?.body ?? '')
    return this.store.write({
      ...input,
      scope,
      sessionId: scope === 'session' ? this.sessionId : '',
      workspaceKey: this.workspaceKey,
      tokens: Number.isSafeInteger(input?.tokens) && input.tokens > 0 ? input.tokens : this.tokens(body),
      tags: {
        ...(input?.tags ?? {}),
        agent: [this.agent],
        model: [this.profile.id],
      },
      provenance: {
        ...(input?.provenance ?? {}),
        agent: this.agent,
        model: this.modelId || this.profile.id,
        profile: this.profile.id,
      },
    })
  }

  /** Ranked card-level search over the visible levels. */
  search({ query, limit, kind, status } = {}) {
    return this.store.search({
      query,
      workspaceKey: this.workspaceKey,
      scopes: this.scopes,
      sessionId: this.sessionId,
      limit: limit ?? this.profile.maxSearchResults,
      rerank: this.profile.rerank,
      maxTerms: this.profile.queryTerms?.maxTerms,
      ...(kind === undefined ? {} : { kind }),
      ...(status === undefined ? {} : { status }),
    })
  }

  /**
   * Read one record body.
   * @param {{id: string, offset?: number, limit?: number, maxChars?: number}} request - Open request.
   * @returns {object|undefined} Record with bounded body slice.
   */
  open({ id, offset, limit, maxChars } = {}) {
    const record = this.store.get(id)
    if (record === undefined) return undefined
    const max = Math.min(Math.max(Number(maxChars) || this.profile.openMaxChars, 400), 240_000)
    const lines = Array.from(String(record.body ?? ''))
    const start = Math.max(0, (Number(offset) || 1) - 1)
    const end = Number(limit) > 0 ? Math.min(lines.length, start + (Number(limit) || 400)) : lines.length
    const body = lines.slice(start, end).join('')
    const clipped = clipToProfileTokens(body, Math.max(200, Math.round(max / this.profile.charsPerToken)), this.profile)
    return {
      ...record,
      body: clipped,
      bodyOffset: start + 1,
      bodyLimit: end - start,
      bodyTotalChars: lines.length,
      bodyTruncated: clipped.length < body.length || start > 0 || end < lines.length,
    }
  }

  /** Literal/regex grep across stored bodies. */
  grep({ pattern, limit, id } = {}) {
    return this.store.grep({
      pattern,
      ...(id === undefined ? {} : { id }),
      workspaceKey: this.workspaceKey,
      scopes: this.scopes,
      sessionId: this.sessionId,
      limit: limit ?? 30,
    })
  }

  /** Catalog text + accounting for the visible levels. */
  /**
   * Materialize a resident extra-context window from the current store.
   * This is the pager API; DSH injection can opt in later without changing
   * non-DSH adapters.
   */
  materializeContext(options = {}) {
    return materializeStoreContext({
      store: this.store,
      workspaceKey: options.workspaceKey ?? this.workspaceKey,
      scopes: options.scopes ?? ['session', 'workspace'],
      sessionId: options.sessionId ?? this.sessionId,
      budgetTokens: options.budgetTokens,
      variant: options.variant,
      pinnedIds: options.pinnedIds,
      reserveTokens: options.reserveTokens,
      query: options.query,
      queryAlternatives: options.queryAlternatives,
      learnedRerank: options.learnedRerank,
      learnedTopK: options.learnedTopK,
      alwaysIncludeIds: options.alwaysIncludeIds,
      learnedPageMaxTokens: options.learnedPageMaxTokens,
      pageTokenCap: options.pageTokenCap,
      tokenCounter: options.tokenCounter,
      tokenizerName: options.tokenizerName,
      includeCanonicalEvents: options.includeCanonicalEvents,
      enforceTotalBudget: options.enforceTotalBudget,
      diversify: options.diversify,
    })
  }

  index({ maxChars } = {}) {
    // Use the profile's catalog budget (tokens × chars/token) as the default
    // prompt-space allocation instead of a fixed 2.4k chars.
    const budgetChars = Math.round((this.profile.catalogTokens ?? 900) * (this.profile.charsPerToken ?? 4))
    const effectiveMaxChars = Math.max(2400, Math.min(24_000, maxChars ?? budgetChars))
    const catalog = this.store.catalog({
      workspaceKey: this.workspaceKey,
      scopes: this.scopes,
      sessionId: this.sessionId,
      maxChars: effectiveMaxChars,
    })
    const facets = this.store.facets({ workspaceKey: this.workspaceKey, scopes: this.scopes, sessionId: this.sessionId })
    return { catalog, facets, levels: this.levels, scopes: this.scopes, profile: this.profile.id, root: this.root }
  }

  /** Card-level listing over the visible levels. */
  list({ kind, status, limit, sort, includeStatus } = {}) {
    return this.store.list({
      workspaceKey: this.workspaceKey,
      scopes: this.scopes,
      sessionId: this.sessionId,
      ...(kind === undefined ? {} : { kind }),
      ...(status === undefined ? {} : { status }),
      ...(limit === undefined ? {} : { limit }),
      ...(sort === undefined ? {} : { sort }),
      ...(includeStatus === undefined ? {} : { includeStatus }),
    })
  }

  /** Remove a record (hot or cold) and its index rows. */
  forget(id) {
    return this.store.forget(id)
  }

  /** Update lifecycle status (pinned records are always catalogued). */
  setStatus(id, status) {
    return this.store.setStatus(id, status)
  }

  /** Move a cold record back to the hot pool. */
  restore(id) {
    return this.store.restoreCold(id)
  }

  /** Lossless cold compression for one visible level. */
  compress({ level = '', targetRatio = 0.6, limit, minAgeMs } = {}) {
    const scope = level === 'l2' ? 'session' : level === 'l3' ? 'workspace' : this.captureScope()
    const report = this.store.compressCold({
      workspaceKey: this.workspaceKey,
      scope,
      sessionId: this.sessionId,
      targetRatio,
      ...(Number.isSafeInteger(limit) ? { limit } : {}),
      ...(Number.isFinite(minAgeMs) ? { minAgeMs } : {}),
    })
    this.store.recordCompression({
      sessionId: this.sessionId,
      level: scope === 'session' ? 'l2' : 'l3',
      strategy: 'cold',
      beforeHot: report.before.hot,
      afterHot: this.store.facets({ workspaceKey: this.workspaceKey, scopes: this.scopes, sessionId: this.sessionId }).hotTokens,
      coldMoved: report.coldMoved.length,
      digests: 0,
      llmCalls: 0,
      errors: [],
    })
    return report
  }

  /** Durable stats for adapters/health output. */
  stats() {
    const { facets, levels, scopes } = this.index()
    return { root: this.root, agent: this.agent, model: this.modelId || this.profile.id, profile: this.profile.id, workspaceKey: this.workspaceKey, sessionId: this.sessionId, levels, scopes, facets }
  }

  close() {
    try {
      this.store.close()
    } catch {
      // Best-effort close for short-lived CLI processes.
    }
  }
}

/** Convenience factory. */
export function createAgentMemory(options) {
  return new AgentMemory(options)
}
