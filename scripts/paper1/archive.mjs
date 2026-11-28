import { randomUUID } from 'node:crypto'
import { existsSync, mkdirSync, readFileSync, renameSync, writeFileSync } from 'node:fs'
import { join } from 'node:path'
import { AgentMemory } from '../../packages/memex-core/lib/engine.js'
import { claimKey, digest } from './verification.mjs'

/**
 * Single-writer research adapter. Raw originals live in real Memex L2 storage;
 * the public catalog records transport metadata, never evaluator answers.
 * setSynchronized(true) is a host assertion that ingestion has no known gaps,
 * not a guess made by the language model. Unknown external changes remain out
 * of scope. Concurrent writers require a transactional ingestion service.
 */
export class EvidenceArchive {
  constructor({ root, cwd, sessionId, pageChars = 12000, maxSourceBytes = 240000 }) {
    this.engine = new AgentMemory({ root, cwd, sessionId, levels: ['l2'] })
    this.epoch = randomUUID()
    this.sessionId = sessionId
    this.pageChars = pageChars
    this.maxSourceBytes = maxSourceBytes
    mkdirSync(root, { recursive: true })
    this.catalogPath = join(root, `p1-catalog-${digest([this.engine.workspaceKey, sessionId]).slice(0, 24)}.json`)
    if (!existsSync(this.catalogPath)) this.save({ schema: 1, synchronized: false, entries: [] })
  }

  catalog() {
    const value = JSON.parse(readFileSync(this.catalogPath, 'utf8'))
    if (value.schema !== 1 || !Array.isArray(value.entries)) throw new Error('invalid source catalog')
    return value
  }

  save(value) {
    const temporary = `${this.catalogPath}.${randomUUID()}.tmp`
    writeFileSync(temporary, JSON.stringify(value))
    renameSync(temporary, this.catalogPath)
  }

  ingest(sources, { recordId = `p1-${randomUUID()}` } = {}) {
    if (!Array.isArray(sources) || !sources.length) throw new TypeError('sources must be a nonempty array')
    const catalog = this.catalog()
    const known = new Map(catalog.entries.map(x => [x.eventId, x]))
    const entries = []
    for (const [index, source] of sources.entries()) {
      if (!source || !['eventId', 'sourceId', 'type', 'scope', 'entity', 'text'].every(k => typeof source[k] === 'string' && source[k].trim())
          || !Number.isSafeInteger(source.sourceSequence) || source.sourceSequence < 1) throw new TypeError('invalid transport source')
      const sourceDigest = digest(source)
      if (known.has(source.eventId)) throw new Error('event identifiers are immutable and may be ingested only once')
      known.set(source.eventId, source)
      entries.push({ eventId: source.eventId, sourceId: source.sourceId, sourceSequence: source.sourceSequence,
        key: claimKey(source), sourceDigest, recordId, eventIndex: index + 1 })
    }
    if (catalog.entries.some(e => e.recordId === recordId)) throw new Error('archive record identifiers are immutable')
    // A crash between the store write and catalog commit leaves an explicitly
    // incomplete view. Never retain the previous "complete" flag across ingest.
    this.save({ ...catalog, synchronized: false })
    this.engine.store.write({
      id: recordId, workspaceKey: this.engine.workspaceKey, scope: 'session', sessionId: this.sessionId,
      kind: 'fact', trust: 'untrusted', title: sources.map(s => `${s.scope} ${s.entity} ${s.type}`).join(' '),
      summary: sources.map(s => s.text).join('\n').slice(0, 1200), body: sources.map(s => JSON.stringify(s)).join('\n'),
      provenance: { shadowedSeqs: sources.map((_, i) => i + 1) },
    }, { archive: { sessionId: this.sessionId, compactionId: recordId,
      events: sources.map((source, i) => ({ sequence: i + 1, role: source.role, type: 'tool_result',
        content: source.text, sessionId: this.sessionId, attachments: [{ rawEvent: source }] })) } })
    this.save({ schema: 1, synchronized: false, entries: [...catalog.entries, ...entries] })
    return entries
  }

  setSynchronized(complete) {
    if (typeof complete !== 'boolean') throw new TypeError('synchronized must be boolean')
    this.save({ ...this.catalog(), synchronized: complete })
  }

  async readView(claim) {
    // Re-read durable metadata on every decision; no notification is required.
    const catalog = this.catalog()
    const key = claimKey(claim)
    const entries = catalog.entries.filter(e => e.key === key)
    const sourceIds = [...new Set(entries.map(e => e.sourceId))]
    const headSequence = Math.max(0, ...entries.map(e => e.sourceSequence))
    const atHead = entries.filter(e => e.sourceSequence === headSequence)
    const commitment = digest(atHead.map(e => [e.eventId, e.sourceDigest]).sort((a, b) => a[0].localeCompare(b[0])))
    return { key, epoch: this.epoch, watermark: digest(catalog.entries), complete: catalog.synchronized === true,
      headCommitment: commitment,
      sourceId: sourceIds.length === 1 ? sourceIds[0] : null,
      headSequence, headEventCount: atHead.length }
  }

  async search({ type, scope, entity, query, limit = 128 }) {
    const key = claimKey({ type, scope, entity })
    const visible = new Set(this.engine.search({ query, limit, includeExpired: true, evidenceSearch: true }).hits.map(h => h.id))
    // These locators come from actual archive ingestion, not from task labels.
    // No version filter: a later replacement or revocation must remain visible.
    return this.catalog().entries.filter(e => e.key === key && visible.has(e.recordId)).slice(0, limit)
      .map(e => ({ eventId: e.eventId, recordId: e.recordId, eventIndex: e.eventIndex, sourceDigest: e.sourceDigest }))
  }

  async open(hit) {
    const entry = this.catalog().entries.find(e => e.eventId === hit.eventId)
    if (!entry || hit.recordId !== entry.recordId || hit.eventIndex !== entry.eventIndex) throw new Error('unknown original locator')
    let charOffset = 0
    let encoded = ''
    for (let pageNumber = 0; pageNumber < 1000; pageNumber++) {
      const page = this.engine.openEvent({ id: entry.recordId, eventIndex: entry.eventIndex, charOffset, maxChars: this.pageChars })
      if (!page || page.recordId !== entry.recordId || page.eventIndex !== entry.eventIndex || page.charOffset !== charOffset) throw new Error('original locator mismatch')
      encoded += page.content
      if (Buffer.byteLength(encoded) > this.maxSourceBytes) throw new Error('source exceeds bounded open budget')
      if (page.nextCharOffset == null) {
        const source = JSON.parse(encoded)
        if (source.eventId !== entry.eventId || digest(source) !== entry.sourceDigest) throw new Error('original integrity mismatch')
        return source
      }
      if (!Number.isSafeInteger(page.nextCharOffset) || page.nextCharOffset <= charOffset) throw new Error('invalid original page continuation')
      charOffset = page.nextCharOffset
    }
    throw new Error('source pagination exhausted')
  }

  close() { this.engine.close() }
}
