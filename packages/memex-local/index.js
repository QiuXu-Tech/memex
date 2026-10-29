/**
 * `@qiuxu/memex/local` — filesystem + SQLite backend for the
 * extra-context memory subsystem. Owns `ctx.memory` and nothing else.
 *
 * Storage layout (all under the DSH home unless `root` overrides it):
 *
 *   <root>/index.db                                  SQLite metadata + FTS5 index
 *   <root>/records/<workspaceKey>/<recordId>.md      one human-readable record per file
 *
 * The models, tools, commands and checkpoint policy are separate plugin rows
 * (`./checkpoint`, `./tools`, `./commands`) that consume this service. Keeping
 * the backend free of those surfaces is what makes the store replaceable.
 *
 * @module @qiuxu/memex/local
 */
import z from '@deepseek-ai/schemastery'
import { dshHomePath } from '@deepseek-ai/dsh-home-paths'
import { MemoryStore } from '@qiuxu/memex-seam'
import { LocalStoreCore } from './lib/store.js'

/**
 * Resolve the deployment default levels from config (legacy `defaultMode`
 * accepted too).
 * @param {object} config - Backend config.
 * @returns {{l2: boolean, l3: boolean}} Default levels.
 */
function resolveDefaultLevels(config) {
  const value = String(config.defaultLevels ?? config.defaultMode ?? 'none')
  if (value === 'l2' || value === 'session') return { l2: true, l3: false }
  if (value === 'l3' || value === 'workspace') return { l2: false, l3: true }
  if (value === 'both') return { l2: true, l3: true }
  if (value === 'none' || value === 'off') return { l2: false, l3: false }
  throw new TypeError(`memory: defaultLevels must be "none", "l2", "l3" or "both", got ${JSON.stringify(value)}`)
}

/**
 * Concrete workspace-scoped memory backend.
 *
 * The service opens its SQLite index lazily on first use so plugin activation
 * stays cheap, and it closes the database through the owning fiber's effect.
 */
export default class LocalMemoryStore extends MemoryStore {
  static inject = []

  static Config = z.object({
    /** Directory holding the index and record files. Defaults to `$DSH_HOME/memories`. */
    root: z.string(),
    /** Soft capacity target of the workspace-shared pool, in estimated tokens. */
    capacityTokens: z.number().step(1).min(1).default(100_000_000),
    /** Soft capacity target of one session-private pool, in estimated tokens. */
    sessionCapacityTokens: z.number().step(1).min(1).default(10_000_000),
    /** Cache levels for sessions without a stored choice: none | l2 | l3 | both. */
    defaultLevels: z.string().default('none'),
    /** Sticky-level settings rows untouched for this many days are pruned at open. */
    settingsTtlDays: z.number().step(1).min(1).default(90),
  })

  constructor(ctx, config = {}) {
    super(ctx)
    this.config = {
      root: config.root ?? dshHomePath('memories'),
      capacityTokens: config.capacityTokens ?? 100_000_000,
      sessionCapacityTokens: config.sessionCapacityTokens ?? 10_000_000,
      defaultLevels: resolveDefaultLevels(config),
    }
    this.root = this.config.root
    this.core = new LocalStoreCore({
      root: this.root,
      capacityTokens: this.config.capacityTokens,
      sessionCapacityTokens: this.config.sessionCapacityTokens,
      defaultLevels: this.config.defaultLevels,
      settingsTtlMs: this.config.settingsTtlDays * 24 * 60 * 60 * 1000,
      logger: () => this.ctx.logger,
    })
    ctx.effect(() => () => this.core.close())
  }

  async write(record) {
    return this.core.write(record)
  }

  async get(id) {
    return this.core.get(id)
  }

  async search(query) {
    return this.core.search(query)
  }

  async list(filter) {
    return this.core.list(filter)
  }

  async grep(request) {
    return this.core.grep(request)
  }

  async facets(filter) {
    return this.core.facets(filter)
  }

  async catalog(request) {
    return this.core.catalog(request)
  }

  async forget(id) {
    return this.core.forget(id)
  }

  async setStatus(id, status) {
    return this.core.setStatus(id, status)
  }

  async markRead(ids) {
    return this.core.markRead(ids)
  }

  async appendContextEvents(input) {
    return this.core.appendContextEvents(input)
  }

  async listContextEvents(recordId) {
    return this.core.listContextEvents(recordId)
  }

  async getLevels(sessionId) {
    return this.core.getLevels(sessionId)
  }

  async archiveCold(id) {
    return this.core.archiveCold(id)
  }

  async restoreCold(id) {
    return this.core.restoreCold(id)
  }

  async compressCold(request) {
    return this.core.compressCold(request)
  }

  async gcCold(request) {
    return this.core.gcCold(request)
  }

  async recordCompression(entry) {
    return this.core.recordCompression(entry)
  }

  async compressionStats(sessionId, limit) {
    return this.core.compressionStats(sessionId, limit)
  }

  async enableLevel(sessionId, level) {
    return this.core.enableLevel(sessionId, level)
  }

  async getMode(sessionId) {
    return this.core.getMode(sessionId)
  }

  async setMode(sessionId, mode) {
    return this.core.setMode(sessionId, mode)
  }

  async recordEviction(entry) {
    return this.core.recordEviction(entry)
  }

  async evictionStats(sessionId) {
    return this.core.evictionStats(sessionId)
  }

  async wasArchived(sessionId, compactionId) {
    return this.core.wasArchived(sessionId, compactionId)
  }

  async archiveRegion(input) {
    return this.core.archiveRegion(input)
  }

  async flush() {
    return this.core.flush()
  }
}
