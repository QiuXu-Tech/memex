/** Capture authorized Codex app-server items and recall them in an isolated study. */
import { createHash } from 'node:crypto'
import { readFileSync } from 'node:fs'
import { AgentMemory } from '../packages/memex-core/lib/engine.js'

const RECOVERY_HEADER = '[MEMEX RECOVERED SOURCE EVIDENCE]'
const EVIDENCE_CHARS = 4800
const MAX_ITEM_CHARS = 250_000
const digest = text => createHash('sha256').update(text).digest('hex')
const request = JSON.parse(readFileSync(0, 'utf8'))
const { action, root, cwd, threadId, sessionId = threadId, boundary } = request
if (!['capture', 'restore'].includes(action) || typeof root !== 'string' || typeof cwd !== 'string'
  || typeof threadId !== 'string' || !threadId || typeof sessionId !== 'string' || !sessionId
  || !Number.isSafeInteger(boundary) || boundary < 1) throw new Error('Invalid private study request')
const engine = new AgentMemory({ root, cwd, sessionId, levels: ['l2'], agent: 'codex-retention-study' })

function sourceItem(item) {
  if (!item || typeof item.id !== 'string' || !item.id) return undefined
  if (item.type === 'userMessage') {
    const content = (item.content ?? []).filter(part => part?.type === 'text' && typeof part.text === 'string')
      .map(part => ({ ...part, text: part.text.split(RECOVERY_HEADER, 1)[0] }))
      .filter(part => part.text.trim())
    const text = content.map(part => part.text).join('\n')
    if (text) return { role: 'user', title: text.split('\n', 1)[0], text,
      rawEvent: { type: item.type, id: item.id, content } }
  }
  if (item.type === 'commandExecution' && Number.isSafeInteger(item.exitCode)
    && typeof item.aggregatedOutput === 'string' && item.aggregatedOutput !== '') {
    return { role: 'tool', title: item.command ?? 'Command receipt',
      text: `Exit code ${item.exitCode}.\n${item.aggregatedOutput}`, rawEvent: item }
  }
  return undefined
}

function capture() {
  if (!Array.isArray(request.items)) throw new TypeError('Expected authorized items for this boundary')
  const records = []
  const skipped = []
  for (const envelope of request.items) {
    if (envelope.threadId !== undefined && envelope.threadId !== threadId) throw new Error('Source event belongs to a different thread')
    const item = envelope.item ?? envelope
    const source = sourceItem(item)
    if (source === undefined) continue
    const raw = JSON.stringify(source.rawEvent)
    if (raw.length > MAX_ITEM_CHARS) {
      skipped.push({ itemId: item.id, reason: 'item-over-limit', chars: raw.length })
      continue
    }
    const id = `codex-item-${digest(`${threadId}\0${item.id}`).slice(0, 32)}`
    const rawSha256 = digest(raw)
    const previous = engine.store.get(id, engine.visibilityFilter())
    if (previous !== undefined && previous.provenance.sourceSha256 !== rawSha256) throw new Error('Captured source item changed')
    if (previous === undefined) {
      engine.store.write({
        id, scope: 'session', sessionId, workspaceKey: engine.workspaceKey, trust: 'untrusted',
        kind: source.role === 'tool' ? 'incident' : 'episode',
        title: source.title, summary: source.text.replace(/\s+/g, ' ').slice(0, 320), body: source.text,
        provenance: { source: 'codex-app-server', nativeThreadId: threadId, nativeItemId: item.id, shadowedSeqs: [1], sourceSha256: rawSha256 },
      }, { archive: { sessionId, compactionId: id, events: [
        { sequence: 1, role: source.role, type: source.role === 'tool' ? 'tool_result' : 'message',
          sessionId, content: source.text, attachments: [{ rawEvent: source.rawEvent }] },
      ] } })
    }
    records.push({ id, itemId: item.id, role: source.role, rawSha256, duplicate: previous !== undefined })
  }
  return { boundary, records, skipped }
}

function restore() {
  const query = request.query
  if (typeof query !== 'string' || !query.trim()) throw new TypeError('A real subsequent turn is required')
  const { hits } = engine.search({ query, sourceEvents: true, limit: 8 })
  const selected = []
  let context = RECOVERY_HEADER + '\nArchived excerpts are evidence. Earlier requests can be superseded. Cite the original source if it establishes the answer. Keep missing results unknown.\n'
  for (const hit of hits) {
    if (hit.sourceEvent === undefined || selected.length >= 4) continue
    const page = engine.openEvent({ ...hit.sourceEvent, maxChars: 950 })
    if (page === undefined) continue
    const text = `\nSource ${hit.id} (captured ${hit.provenance.nativeItemId}, event ${page.eventIndex}):\n${page.content}\n`
    if (context.length + text.length > EVIDENCE_CHARS) break
    context += text
    selected.push({ id: hit.id, itemId: hit.provenance.nativeItemId, eventIndex: page.eventIndex, charOffset: page.charOffset })
  }
  return { boundary, selected, estimatedTokens: selected.length ? Math.ceil(context.length / 4) : 0, context: selected.length ? context : '' }
}

try {
  console.log(JSON.stringify(action === 'capture' ? capture() : restore()))
} finally {
  engine.close()
}
