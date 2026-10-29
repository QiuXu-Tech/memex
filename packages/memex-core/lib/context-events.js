/**
 * Canonical context events (context-materialization step 1).
 *
 * Raw host events are lossy once rendered into markdown cards. This module
 * preserves the exact role/type/content/tool metadata/sequence in a
 * deterministic, checksummed envelope. The store can persist these alongside
 * a record, and the materializer can replay them in order.
 */
import { createHash } from 'node:crypto'

export const CONTEXT_EVENT_ROLES = Object.freeze(['system', 'user', 'assistant', 'tool'])
export const CONTEXT_EVENT_TYPES = Object.freeze(['message', 'tool_call', 'tool_result', 'attachment', 'summary'])

const sha256 = (text) => createHash('sha256').update(String(text), 'utf8').digest('hex')
const contentOf = (value) => typeof value === 'string' ? value : JSON.stringify(value ?? null)

/** Deterministic canonical form used for serialization and checksums. */
export function canonicalContextEvent(input = {}) {
  const role = CONTEXT_EVENT_ROLES.includes(input.role) ? input.role : 'assistant'
  const type = CONTEXT_EVENT_TYPES.includes(input.type) ? input.type : 'message'
  const sequence = Number.isFinite(input.sequence) ? Number(input.sequence) : 0
  const content = contentOf(input.content)
  const toolArguments = input.toolArguments === undefined ? undefined : contentOf(input.toolArguments)
  return {
    id: String(input.id ?? `ctx-${sequence}-${type}`),
    role,
    type,
    sequence,
    sessionId: input.sessionId === undefined ? undefined : String(input.sessionId),
    recordId: input.recordId === undefined ? undefined : String(input.recordId),
    content,
    contentFormat: input.contentFormat === 'json' ? 'json' : 'text',
    toolName: input.toolName === undefined ? undefined : String(input.toolName),
    toolCallId: input.toolCallId === undefined ? undefined : String(input.toolCallId),
    toolArguments,
    attachments: Array.isArray(input.attachments) ? input.attachments : [],
    createdAt: Number.isFinite(input.createdAt) ? Number(input.createdAt) : 0,
  }
}

/** Add the checksum after canonicalization (the checksum covers all other fields). */
export function checksumContextEvent(event) {
  const { checksum: _ignored, ...rest } = event
  return sha256(JSON.stringify(rest))
}

export function serializeContextEvent(event) {
  const canonical = canonicalContextEvent(event)
  return JSON.stringify({ ...canonical, checksum: checksumContextEvent(canonical) })
}

export function deserializeContextEvent(text) {
  const parsed = JSON.parse(String(text))
  const canonical = canonicalContextEvent(parsed)
  const checksum = checksumContextEvent(canonical)
  if (parsed.checksum !== undefined && parsed.checksum !== checksum) throw new Error('context event checksum mismatch')
  return { ...canonical, checksum }
}

/**
 * Convert one DSH session event into zero or more canonical events. This keeps
 * each content block separate so a tool call and its arguments stay exact.
 */
export function canonicalEventsFromDsh(events, options = {}) {
  const output = []
  for (const event of Array.isArray(events) ? events : []) {
    const sequence = Number.isFinite(event?.seq) ? Number(event.seq) : 0
    const message = event?.message
    if (message === undefined) {
      output.push(canonicalContextEvent({ id: `${options.recordId ?? 'record'}:${sequence}:0`, sequence, role: 'assistant', type: 'attachment', content: contentOf(event), sessionId: options.sessionId, recordId: options.recordId, createdAt: event?.time }))
      continue
    }
    const role = CONTEXT_EVENT_ROLES.includes(message.role) ? message.role : 'assistant'
    const blocks = Array.isArray(message.content) ? message.content : []
    if (blocks.length === 0) {
      output.push({ ...canonicalContextEvent({ id: `${sequence}:0`, sequence, role, type: 'message', content: '', sessionId: options.sessionId, recordId: options.recordId, createdAt: event?.time }), checksum: '' })
      continue
    }
    for (const [index, block] of blocks.entries()) {
      const base = { id: `${sequence}:${index}`, sequence, role, sessionId: options.sessionId, recordId: options.recordId, createdAt: event?.time }
      if (block?.type === 'text') {
        output.push(withChecksum({ ...base, type: 'message', content: String(block.text ?? '') }))
      } else if (block?.type === 'tool-call') {
        output.push(withChecksum({ ...base, type: 'tool_call', content: contentOf(block.arguments ?? ''), toolName: block.name, toolCallId: block.id, toolArguments: block.arguments }))
      } else if (role === 'tool' || block?.type === 'tool-result') {
        output.push(withChecksum({ ...base, type: 'tool_result', content: contentOf(block.content ?? block), toolCallId: block.id }))
      } else {
        output.push(withChecksum({ ...base, type: 'attachment', content: contentOf(block), attachments: [{ blockType: block?.type ?? 'unknown' }] }))
      }
    }
  }
  return output.map((event) => ({ ...event, checksum: checksumContextEvent(event) }))
}

function withChecksum(event) {
  const canonical = canonicalContextEvent(event)
  return canonical
}

/** Convert canonical events into materializer pages (verbatim bodies). */
export function eventsToMaterializerPages(events) {
  return (Array.isArray(events) ? events : []).map((event) => ({
    id: String(event.id),
    title: `${event.role}/${event.type}${event.toolName === undefined ? '' : ` ${event.toolName}`}`,
    summary: '',
    body: event.content,
    sequence: Number(event.sequence ?? 0),
    createdAt: Number(event.createdAt ?? 0),
    role: event.role,
  }))
}
