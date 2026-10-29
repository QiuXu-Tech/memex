/**
 * Memory seam: the DSH `ctx.memory` service on top of the agent-agnostic core.
 *
 * The Cordis-free vocabulary and helpers (record kinds, workspace identity,
 * query terms, token accounting, message shape) live in
 * `@qiuxu/dsh-memory-core` and are re-exported here, so existing DSH consumers
 * keep one import while non-DSH agents (MCP server, Claude Code, Codex) use the
 * core directly.
 *
 * A backend subclasses {@link MemoryStore} and is loaded as a plugin, which
 * registers the single `ctx.memory` implementation for the composition. Storage,
 * indexing, retention and card generation belong to the backend; policy (when to
 * archive, what to recall, how much catalog to show) belongs to the checkpoint
 * plugin.
 *
 * @module @qiuxu/dsh-memory-seam
 */
import { Service } from '@deepseek-ai/cordis'

export * from '@qiuxu/dsh-memory-core'

/**
 * Abstract workspace-scoped memory store.
 *
 * A backend implements every method and is loaded as a plugin; its constructor
 * calls `super(ctx)` which registers it as `ctx.memory`. Exactly one
 * implementation may be active per context.
 */
export class MemoryStore extends Service {
  /**
   * @param {import('@deepseek-ai/cordis').Context} ctx - Owning Cordis context.
   */
  constructor(ctx) {
    super(ctx, 'memory')
  }

  /**
   * Persist one record (create or replace by id).
   * @param {object} record - Validated record input.
   * @returns {Promise<object>} The stored record with generated id and timestamps.
   */
  async write(_record) {
    throw new Error('memory: write() is not implemented by this backend')
  }

  /** @returns {Promise<object | undefined>} One record including its full body, or undefined. */
  async get(_id) {
    throw new Error('memory: get() is not implemented by this backend')
  }

  /** @returns {Promise<{hits: object[], total: number}>} Ranked card-level hits, never bodies. */
  async search(_query) {
    throw new Error('memory: search() is not implemented by this backend')
  }

  /** @returns {Promise<object[]>} Card-level listing in the requested order. */
  async list(_filter) {
    throw new Error('memory: list() is not implemented by this backend')
  }

  /** @returns {Promise<object[]>} Literal line matches inside stored bodies. */
  async grep(_request) {
    throw new Error('memory: grep() is not implemented by this backend')
  }

  /** @returns {Promise<object>} Facet counts and capacity accounting for a workspace. */
  async facets(_filter) {
    throw new Error('memory: facets() is not implemented by this backend')
  }

  /** @returns {Promise<string>} A bounded markdown catalog of the most useful cards. */
  async catalog(_request) {
    throw new Error('memory: catalog() is not implemented by this backend')
  }

  /** @returns {Promise<boolean>} Whether a record was removed. */
  async forget(_id) {
    throw new Error('memory: forget() is not implemented by this backend')
  }

  /** @returns {Promise<object | undefined>} The updated record. */
  async setStatus(_id, _status) {
    throw new Error('memory: setStatus() is not implemented by this backend')
  }

  /**
   * Move a record out of the hot prompt pool into the cold tier. The record
   * stays searchable/openable by id; only its prompt footprint is released.
   * @param {string} _id - Record id.
   * @returns {Promise<object | undefined>} The updated card, or undefined.
   */
  async archiveCold(_id) {
    throw new Error('memory: archiveCold() is not implemented by this backend')
  }

  /** @returns {Promise<number>} Count of records recorded as read now. */
  async markRead(_ids) {
    throw new Error('memory: markRead() is not implemented by this backend')
  }

  /** @returns {Promise<boolean>} Whether this compaction was already archived. */
  async wasArchived(_sessionId, _compactionId) {
    throw new Error('memory: wasArchived() is not implemented by this backend')
  }

  /** @returns {Promise<object>} The neutral record data extracted from a compacted region. */
  async archiveRegion(_input) {
    throw new Error('memory: archiveRegion() is not implemented by this backend')
  }

  /** @returns {Promise<void>} Flush pending durable state. */
  async flush() {}
}

