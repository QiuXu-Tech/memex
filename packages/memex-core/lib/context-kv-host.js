/**
 * Reference paged-KV / prefix-cache host (context-materialization step 4).
 *
 * This is a runnable host-side reference service, not a model runtime. It owns
 * real paged blocks, an LRU block budget and a prefix -> block map, and exposes
 * the same capability contract as `context-kv.js`. A local inference runtime can
 * implement the same operations over actual KV tensors.
 */
import { CONTEXT_HOST_CAPABILITIES, CONTEXT_KV_VERSION, negotiateContextHost } from './context-kv.js'

export class PagedKvContextHost {
  constructor({ capacityBlocks = 16, blockTokens = 256, capabilities = Object.values(CONTEXT_HOST_CAPABILITIES) } = {}) {
    this.version = CONTEXT_KV_VERSION
    this.capabilities = [...capabilities]
    this.capacityBlocks = Math.max(1, Number(capacityBlocks))
    this.blockTokens = Math.max(1, Number(blockTokens))
    this.blocks = new Map()
    this.prefixes = new Map()
    this.pages = new Map()
    this.clock = 0
  }
  #touch(id) { const block = this.blocks.get(id); if (block !== undefined) { block.lastUsed = ++this.clock; block.uses += 1 } }
  #evictIfNeeded() {
    while (this.blocks.size > this.capacityBlocks) {
      let victim
      for (const block of this.blocks.values()) if (victim === undefined || block.lastUsed < victim.lastUsed) victim = block
      if (victim === undefined) break
      this.blocks.delete(victim.id)
      for (const [key, ids] of this.prefixes) { const next = ids.filter((id) => id !== victim.id); if (next.length === 0) this.prefixes.delete(key); else this.prefixes.set(key, next) }
      for (const [span, ids] of this.pages) { const next = ids.filter((id) => id !== victim.id); if (next.length === 0) this.pages.delete(span); else this.pages.set(span, next) }
    }
  }
  createBlock(id, text) {
    this.blocks.set(id, { id, text: String(text), tokens: Math.ceil(String(text).length / 4), lastUsed: ++this.clock, uses: 0 })
    this.#evictIfNeeded()
    return this.blocks.has(id) ? id : undefined
  }
  registerPrefix(key, texts) {
    const requested = []
    for (const [index, text] of [...texts].entries()) {
      const id = `${key}:block:${index}`
      this.createBlock(id, text)
      requested.push(id)
    }
    const ids = requested.filter((id) => this.blocks.has(id))
    this.prefixes.set(key, ids)
    return [...ids]
  }
  pageIn(span, blockIds) { this.pages.set(span, [...blockIds]); for (const id of blockIds) this.#touch(id); return [...blockIds] }
  pageOut(span) { return this.pages.delete(span) }
  resolvePrefix(key) { const ids = [...(this.prefixes.get(key) ?? [])]; for (const id of ids) this.#touch(id); return ids }
  stats() {
    return { version: this.version, capabilities: this.capabilities, blocks: this.blocks.size, capacityBlocks: this.capacityBlocks, prefixes: this.prefixes.size, pages: this.pages.size }
  }
  negotiation() { return negotiateContextHost(this) }
}
